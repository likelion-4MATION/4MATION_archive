# -*- coding: utf-8 -*-
"""1차 검색 결과로 업무(BF)를 역추론하는 실험 — 키워드 분류기 기권 구간 회수용.

문제(실측): 키워드 분류기 classify_query_bf()는 점수·마진 임계에 못 미치면 None을
반환하고, 그러면 업무 부스트가 통째로 안 걸린다. 기권 구간을 뜯어보면 대부분 '모호'가
아니라 '사전에 걸리는 말이 아예 없는 경우'라 임계값 조정으로는 손쓸 수 없다.

처방: 의사 적합성 피드백(pseudo-relevance feedback).
    1) 부스트 없이 1차 융합 → 상위 N개
    2) 그 N개의 business_function을 순위 가중 투표 → 우세 업무가 임계 이상이면 채택
    3) 그 업무로 부스트를 걸어 2차 랭킹
키워드가 확신할 때는 그대로 쓰고, 기권할 때만 역추론값을 쓴다. 학습·추가 임베딩이
필요 없고 1차 랭킹을 재사용하므로 비용이 사실상 0이다.

주의 - 라벨 누수 금지: 정답 business_function을 절대 쓰지 않는다. 오직 검색 결과에서만
추론하므로 실제 배포 경로에서 그대로 동작한다.

이 실험으로 찾은 QBF_PRF_TOPN/QBF_PRF_MIN_SHARE·Searcher._infer_bf_from_pool()은
crawler/rag.py에 이미 반영돼 있다. 이 스크립트는 그 반영분을 재검증하는 A/B 하네스다.

팀 규율 준수: TEST/VAL 두 셋 모두 개선되는 값만 채택.

사용: cd crawler && python eval_prf_bf.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import rag
from eval_anchor_span_multi import RETRIEVAL_DEPTH, _item_metrics, _norm

TEST_GT = "data/gt_natural430_curated.jsonl"
VAL_GT = "data/gt_natural355.jsonl"
KS = (1, 3, 5, 10)

# (투표에 쓸 상위 N, 우세 임계) — 임계는 1위 업무 득표 비중
CONFIGS = [
    (None, None),   # 현행(역추론 없음)
    (3, 0.50), (3, 0.67),
    (5, 0.40), (5, 0.50), (5, 0.60),
    (10, 0.40), (10, 0.50),
]


def prepare(gt, searcher):
    n = len(searcher.chunks)
    out = []
    for item in gt:
        q = item["question"]
        out.append({
            "item": item,
            "d": {int(i): r for r, (i, _) in enumerate(searcher.dense(q, n))},
            "s": {int(i): r for r, (i, _) in enumerate(searcher.sparse(q, n))},
            "kw_bf": rag.classify_query_bf(q),
            "facets": rag.query_facets(q),
        })
    return out


def base_scores(d_rank, s_rank) -> dict[int, float]:
    sc: dict[int, float] = {}
    for i in set(d_rank) | set(s_rank):
        v = 0.0
        if i in d_rank:
            v += rag.RRF_ALPHA / (rag.RRF_K + d_rank[i] + 1)
        if i in s_rank:
            v += (1 - rag.RRF_ALPHA) / (rag.RRF_K + s_rank[i] + 1)
        sc[i] = v
    return sc


def infer_bf(chunks, sc: dict[int, float], top_n: int, thresh: float) -> str | None:
    """1차 상위 N개의 business_function을 순위 가중 투표해 우세 업무를 고른다."""
    ranked = sorted(sc.items(), key=lambda x: -x[1])[:top_n]
    if not ranked:
        return None
    votes: dict[str, float] = defaultdict(float)
    total = 0.0
    for rank, (i, _) in enumerate(ranked, 1):
        bf = chunks[i].get("business_function")
        if not bf:
            continue
        w = 1.0 / rank          # 상위일수록 큰 표
        votes[bf] += w
        total += w
    if not votes or total <= 0:
        return None
    best, best_v = max(votes.items(), key=lambda x: x[1])
    return best if (best_v / total) >= thresh else None


def rank_ids(chunks, rec, top_n, thresh) -> list[str]:
    sc = base_scores(rec["d"], rec["s"])
    bf = rec["kw_bf"]
    if bf is None and top_n is not None:
        bf = infer_bf(chunks, sc, top_n, thresh)

    if bf is not None and rag.BF_BOOST > 0:
        allow = rag.BF_SHARED_DOCS.get(bf, set())
        facets = rec["facets"]
        for i in sc:
            c = chunks[i]
            if c.get("business_function") == bf or c["parent_doc_id"] in allow:
                sc[i] += rag.BF_BOOST
                if rag.FACET_BOOST and facets:
                    h = sum(1 for t in facets if t in c.get("sub_category", ""))
                    if h:
                        sc[i] += rag.FACET_BOOST * h

    ranked = sorted(sc.items(), key=lambda x: -x[1])
    if rag.BF_DOC_CAP:
        seen: dict[str, int] = {}
        capped = []
        for idx, v in ranked:
            d = chunks[idx]["parent_doc_id"]
            if seen.get(d, 0) < rag.BF_DOC_CAP:
                capped.append((idx, v))
                seen[d] = seen.get(d, 0) + 1
        ranked = capped
    return [chunks[i]["chunk_id"] for i, _ in ranked[:RETRIEVAL_DEPTH]]


def evaluate(prepared, chunks, chunk_text, top_n, thresh) -> dict:
    agg = {f"hit@{k}": 0 for k in KS}
    agg["mrr"] = 0.0
    n = 0
    abstain_hit = abstain_n = 0
    recovered = 0
    for rec in prepared:
        if rec["kw_bf"] is None and top_n is not None:
            if infer_bf(chunks, base_scores(rec["d"], rec["s"]), top_n, thresh):
                recovered += 1
        ids = rank_ids(chunks, rec, top_n, thresh)
        v = _item_metrics(rec["item"], ids, chunk_text, id_fallback=True)
        n += 1
        for k in KS:
            agg[f"hit@{k}"] += v[f"hit@{k}"]
        agg["mrr"] += v["mrr"]
        if rec["kw_bf"] is None:
            abstain_n += 1
            abstain_hit += v["hit@5"]
    res = {k: val / n for k, val in agg.items()}
    res["n"] = n
    res["abstain_hit5"] = abstain_hit / abstain_n if abstain_n else 0.0
    res["abstain_n"] = abstain_n
    res["recovered"] = recovered
    return res


def run(gt_path, label, searcher, chunks, chunk_text) -> dict:
    gt = [json.loads(l) for l in open(gt_path, encoding="utf-8") if l.strip()]
    gt = [x for x in gt if x.get("answerable") is True]
    prepared = prepare(gt, searcher)
    n_abs = sum(1 for r in prepared if r["kw_bf"] is None)
    print(f"\n{'='*78}\n[{label}] {gt_path} · {len(gt)}건 · 키워드 기권 {n_abs}건"
          f"({n_abs/len(gt)*100:.1f}%)\n{'='*78}")
    print(f"{'topN':>5}{'임계':>7}" + "".join(f"{'hit@'+str(k):>9}" for k in KS)
          + f"{'mrr':>9}{'기권구간hit5':>13}{'역추론성공':>11}")
    out = {}
    for top_n, th in CONFIGS:
        r = evaluate(prepared, chunks, chunk_text, top_n, th)
        out[(top_n, th)] = r
        cells = "".join(f"{r[f'hit@{k}']:>9.3f}" for k in KS) + f"{r['mrr']:>9.3f}"
        head = f"{'현행':>12}" if top_n is None else f"{top_n:>5}{th:>7.2f}"
        print(f"{head}{cells}{r['abstain_hit5']:>13.3f}{r['recovered']:>11}")
    return out


def main() -> None:
    searcher = rag.Searcher()
    chunks = searcher.chunks
    chunk_text = {c["chunk_id"]: _norm(c.get("text", "")) for c in chunks}
    print(f"현행 파라미터: alpha={rag.RRF_ALPHA} rrf_k={rag.RRF_K} bf={rag.BF_BOOST} "
          f"facet={rag.FACET_BOOST} cap={rag.BF_DOC_CAP}")

    test = run(TEST_GT, "TEST", searcher, chunks, chunk_text)
    val = run(VAL_GT, "VAL", searcher, chunks, chunk_text)

    print(f"\n{'='*78}\n두 셋 전이성 판정 (현행 대비 hit@5 증감)\n{'='*78}")
    t0, v0 = test[(None, None)]["hit@5"], val[(None, None)]["hit@5"]
    print(f"{'topN':>5}{'임계':>7}{'TEST':>11}{'VAL':>11}   판정")
    for key in CONFIGS:
        if key == (None, None):
            continue
        dt, dv = test[key]["hit@5"] - t0, val[key]["hit@5"] - v0
        verdict = "채택 가능(둘 다 개선)" if dt > 0 and dv > 0 else "한쪽만/악화"
        print(f"{key[0]:>5}{key[1]:>7.2f}{dt:>+11.4f}{dv:>+11.4f}   {verdict}")


if __name__ == "__main__":
    main()
