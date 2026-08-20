# -*- coding: utf-8 -*-
"""span 채점 기준 파라미터 재튜닝 — BF_DOC_CAP / BF_BOOST(β) / RRF_ALPHA(α) / FACET_BOOST.

배경: 이 네 파라미터의 기존 "최적값"은 서로 다른 채점 기준으로 나왔다.
  - RRF_ALPHA=0.6, BF_BOOST=0.005: eval_rrf_tune.py, 문서 단위(parent_doc_id ∈ gt_docs) 채점.
  - FACET_BOOST≈0.1: eval_facet_v2.py, chunk_id 직접비교(eval_anchor_v3._hit_at_k) 채점.
  - BF_DOC_CAP=5: 전용 스윕 스크립트가 없다(eval_cap.py는 cap 1~3만 문서 단위로 스윕했고
    현재 값 5는 그 결과 목록에 없다 — 다른 근거로 정해진 값으로 보인다).
채점 기준을 span(``gt_anchor_spans``, ``gt_natural450_multi.jsonl``)으로 바꾸면 이
네 값이 그대로 최적일 이유가 없다. eval_anchor_span_multi.py의 판정 로직
(``_item_metrics`` — and는 ALL, or/single은 ANY, 청크 본문에 span이 실제로
있는지로 hit 판정)을 그대로 재사용해 span 기준으로 다시 스윕한다.

방식: 질의당 dense/sparse 전체 풀 랭크·업무분류·패싯을 1회만 계산해 재사용하고
(eval_facet_v2.py와 동일한 절약 방식), 4개 파라미터를 축별로(다른 값은 현재값
고정) 스윕한다. 4차원 완전 그리드는 비용이 커서, 기존 eval_rrf_tune/eval_facet_v2와
같은 좌표별 스윕 방식을 그대로 따랐다 — 상호작용(예: cap과 facet의 결합효과)까지
보려면 유망한 후보로 좁힌 뒤 2차 교차 스윕을 별도로 돌릴 것.

사용: cd crawler && python eval_span_tune.py
"""
from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

import rag
from eval_anchor_span_multi import RETRIEVAL_DEPTH, _item_metrics, _norm

GT_PATH = "data/gt_natural430_curated.jsonl"
KS = (1, 3, 5, 10)

CUR_ALPHA = rag.RRF_ALPHA      # 0.6
CUR_BOOST = rag.BF_BOOST       # 0.04
CUR_FACET = rag.FACET_BOOST    # 0.05
CUR_CAP = rag.BF_DOC_CAP       # 5
RRF_K = rag.RRF_K              # 스윕 대상 아님 — 현재값 고정

ALPHAS = [0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
BOOSTS = [0.0, 0.005, 0.010, 0.020, 0.040]
FACETS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
CAPS = [1, 2, 3, 5, 8, None]


def fuse(chunks, d_rank, s_rank, bf, facets, alpha, boost, facet_boost, cap) -> list[str]:
    """hybrid_soft(rag.py) + facet 부스트 + doc-cap을 사전계산 랭크로 재구성(재임베딩 없음)."""
    idxs = set(d_rank) | set(s_rank)
    sc: dict[int, float] = {}
    for i in idxs:
        v = 0.0
        if i in d_rank:
            v += alpha / (RRF_K + d_rank[i] + 1)
        if i in s_rank:
            v += (1 - alpha) / (RRF_K + s_rank[i] + 1)
        sc[i] = v
    if bf is not None and boost > 0:
        allow = rag.BF_SHARED_DOCS.get(bf, set())
        for i in sc:
            c = chunks[i]
            if c.get("business_function") == bf or c["parent_doc_id"] in allow:
                sc[i] += boost
                if facet_boost and facets:
                    hit = sum(1 for t in facets if t in c.get("sub_category", ""))
                    if hit:
                        sc[i] += facet_boost * hit
    ranked = sorted(sc.items(), key=lambda x: -x[1])
    if cap:
        seen: dict[str, int] = {}
        capped = []
        for idx, score in ranked:
            d = chunks[idx]["parent_doc_id"]
            if seen.get(d, 0) < cap:
                capped.append((idx, score))
                seen[d] = seen.get(d, 0) + 1
        ranked = capped
    return [chunks[i]["chunk_id"] for i, _ in ranked[:RETRIEVAL_DEPTH]]


def prepare(gt: list[dict], searcher: "rag.Searcher") -> list[dict]:
    """질의당 dense/sparse 전체 풀 랭크·업무분류·패싯을 1회 계산해 캐시한다."""
    N = len(searcher.chunks)
    prepared = []
    for item in gt:
        q = item["question"]
        d = {int(i): r for r, (i, _) in enumerate(searcher.dense(q, N))}
        s = {int(i): r for r, (i, _) in enumerate(searcher.sparse(q, N))}
        prepared.append({
            "item": item, "d": d, "s": s,
            "bf": rag.classify_query_bf(q),
            "facets": rag.query_facets(q),
        })
    return prepared


def evaluate(prepared: list[dict], chunks, chunk_text, alpha, boost, facet_boost, cap) -> dict:
    agg = {f"hit@{k}": 0.0 for k in KS}
    agg["mrr"] = 0.0
    n = 0
    for p in prepared:
        retrieved_ids = fuse(chunks, p["d"], p["s"], p["bf"], p["facets"],
                              alpha, boost, facet_boost, cap)
        values = _item_metrics(p["item"], retrieved_ids, chunk_text)
        n += 1
        for k in KS:
            agg[f"hit@{k}"] += values[f"hit@{k}"]
        agg["mrr"] += values["mrr"]
    return {**{k: v / n for k, v in agg.items()}, "n": n}


def _print_axis(title: str, values: list, cur_value, results: list[dict]) -> None:
    print(f"\n[{title}]")
    header = f"{'value':>10}" + "".join(f"{'hit@'+str(k):>9}" for k in KS) + f"{'mrr':>9}"
    print(header)
    for v, r in zip(values, results):
        label = "none" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
        star = "  *(현행)" if v == cur_value else ""
        cells = "".join(f"{r[f'hit@{k}']:>9.3f}" for k in KS) + f"{r['mrr']:>9.3f}"
        print(f"{label:>10}{cells}{star}")
    best_idx = max(range(len(results)), key=lambda i: (results[i]["hit@3"], results[i]["hit@1"], results[i]["mrr"]))
    best, best_v = results[best_idx], values[best_idx]
    cur_r = results[values.index(cur_value)] if cur_value in values else None
    if cur_r is not None:
        print(f"  -> 현재값 {cur_value} 대비 최고 hit@3: {best_v} "
              f"({cur_r['hit@3']:.3f} -> {best['hit@3']:.3f}, {best['hit@3']-cur_r['hit@3']:+.3f})")


def main() -> None:
    gt_all = [json.loads(l) for l in open(GT_PATH, encoding="utf-8") if l.strip()]
    gt = [x for x in gt_all if x.get("answerable") is True]
    print(f"평가셋: {GT_PATH} · 평가 대상(answerable=true) {len(gt)}건 / 전체 {len(gt_all)}건")
    print(f"현재값: alpha={CUR_ALPHA} boost={CUR_BOOST} facet={CUR_FACET} cap={CUR_CAP} "
          f"(rrf_k={RRF_K}, 스윕 대상 아님)")

    searcher = rag.Searcher()
    chunks = searcher.chunks
    chunk_text = {c["chunk_id"]: _norm(c.get("text", "")) for c in chunks}

    print("\n질의당 dense/sparse 전체 풀 랭크 계산 중(1회, 스윕 재사용)...")
    prepared = prepare(gt, searcher)
    print("계산 완료 — 축별 스윕 시작")

    r_alpha = [evaluate(prepared, chunks, chunk_text, a, CUR_BOOST, CUR_FACET, CUR_CAP) for a in ALPHAS]
    _print_axis("RRF_ALPHA (dense 가중, boost/facet/cap = 현행 고정)", ALPHAS, CUR_ALPHA, r_alpha)

    r_boost = [evaluate(prepared, chunks, chunk_text, CUR_ALPHA, b, CUR_FACET, CUR_CAP) for b in BOOSTS]
    _print_axis("BF_BOOST (업무 소프트부스트, alpha/facet/cap = 현행 고정)", BOOSTS, CUR_BOOST, r_boost)

    r_facet = [evaluate(prepared, chunks, chunk_text, CUR_ALPHA, CUR_BOOST, f, CUR_CAP) for f in FACETS]
    _print_axis("FACET_BOOST (서브인텐트 부스트, alpha/boost/cap = 현행 고정)", FACETS, CUR_FACET, r_facet)

    r_cap = [evaluate(prepared, chunks, chunk_text, CUR_ALPHA, CUR_BOOST, CUR_FACET, c) for c in CAPS]
    _print_axis("BF_DOC_CAP (문서당 청크 캡, alpha/boost/facet = 현행 고정)", CAPS, CUR_CAP, r_cap)

    print("\n[참고] 이 스크립트는 축별(다른 값 고정) 스윕이라 파라미터 간 상호작용은 안 본다.")
    print("      각 축에서 유망한 값이 나오면 그 조합만 따로 evaluate()로 교차 확인할 것.")


if __name__ == "__main__":
    main()
