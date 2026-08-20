# -*- coding: utf-8 -*-
"""MMR(다양성) 재랭킹 실험 — and 문항의 '상보적 청크가 밀려남' 회수용. (기각)

문제: and 문항 실패 다수가 "필요 스팬 하나는 top-5 안인데 나머지가 6~10위"였다.
and 질문은 서로 다른 내용의 청크 2~4개를 동시에 top-5에 넣어야 하는데, 상위가 서로
비슷한 청크로 채워지면 상보적인 청크가 경계 밖으로 밀린다.

처방: MMR(Carbonell & Goldstein 1998) — 이미 뽑은 것과 비슷한 청크에 벌점을 줘
중복을 걷어내고 상보적 청크를 끌어올린다.
    MMR(c) = beta * rel(c) - (1 - beta) * max_sim(c, selected)
beta=1.0이면 현행(순수 관련도 순)과 완전히 동일하다.

형제 전파(eval_sibling_boost.py)와 정반대 방향이다. 그쪽은 같은 문서 청크를 더
끌어올려 실패했고(주지표 single이 밀려남), 이쪽은 중복을 덜어내 자리를 만든다.

결과: 기각(hit@5 기준). hit@5는 어떤 beta에서도 개선 없음. 단 hit@3은 beta=0.8에서
TEST/VAL 두 셋 모두 개선됐다 — top-3 UI라면 재검토 가치 있음.

사용: cd crawler && python eval_mmr_rerank.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

import rag
from eval_anchor_span_multi import RETRIEVAL_DEPTH, _item_metrics, _norm

TEST_GT = "data/gt_natural430_curated.jsonl"
VAL_GT = "data/gt_natural355.jsonl"
BETAS = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5]
POOL = 30       # MMR로 재정렬할 후보 풀 크기
KS = (1, 3, 5, 10)


def prepare(gt, searcher):
    n = len(searcher.chunks)
    out = []
    for item in gt:
        q = item["question"]
        out.append({
            "item": item,
            "d": {int(i): r for r, (i, _) in enumerate(searcher.dense(q, n))},
            "s": {int(i): r for r, (i, _) in enumerate(searcher.sparse(q, n))},
            "bf": rag.classify_query_bf(q),
            "facets": rag.query_facets(q),
        })
    return out


def fused_scores(chunks, d_rank, s_rank, bf, facets) -> dict[int, float]:
    sc: dict[int, float] = {}
    for i in set(d_rank) | set(s_rank):
        v = 0.0
        if i in d_rank:
            v += rag.RRF_ALPHA / (rag.RRF_K + d_rank[i] + 1)
        if i in s_rank:
            v += (1 - rag.RRF_ALPHA) / (rag.RRF_K + s_rank[i] + 1)
        sc[i] = v
    if bf is not None and rag.BF_BOOST > 0:
        allow = rag.BF_SHARED_DOCS.get(bf, set())
        for i in sc:
            c = chunks[i]
            if c.get("business_function") == bf or c["parent_doc_id"] in allow:
                sc[i] += rag.BF_BOOST
                if rag.FACET_BOOST and facets:
                    hit = sum(1 for t in facets if t in c.get("sub_category", ""))
                    if hit:
                        sc[i] += rag.FACET_BOOST * hit
    return sc


def apply_cap(ranked: list[tuple[int, float]], chunks) -> list[tuple[int, float]]:
    if not rag.BF_DOC_CAP:
        return ranked
    seen: dict[str, int] = {}
    out = []
    for idx, score in ranked:
        d = chunks[idx]["parent_doc_id"]
        if seen.get(d, 0) < rag.BF_DOC_CAP:
            out.append((idx, score))
            seen[d] = seen.get(d, 0) + 1
    return out


def select(chunks, vecs, sc: dict[int, float], beta: float) -> list[str]:
    ranked = apply_cap(sorted(sc.items(), key=lambda x: -x[1]), chunks)
    if beta >= 1.0:
        return [chunks[i]["chunk_id"] for i, _ in ranked[:RETRIEVAL_DEPTH]]

    pool = ranked[:POOL]
    if not pool:
        return []
    vals = np.array([v for _, v in pool], dtype=np.float32)
    lo, hi = float(vals.min()), float(vals.max())
    rel = {i: (1.0 if hi == lo else (v - lo) / (hi - lo)) for i, v in pool}

    idxs = [i for i, _ in pool]
    mat = vecs[idxs]                      # 정규화된 임베딩 → 내적이 코사인
    sim = mat @ mat.T
    pos = {ix: p for p, ix in enumerate(idxs)}

    selected: list[int] = []
    remaining = set(idxs)
    while remaining and len(selected) < RETRIEVAL_DEPTH:
        best, best_score = None, None
        for i in remaining:
            if selected:
                redundancy = max(float(sim[pos[i], pos[j]]) for j in selected)
            else:
                redundancy = 0.0
            score = beta * rel[i] - (1.0 - beta) * redundancy
            if best_score is None or score > best_score:
                best, best_score = i, score
        selected.append(best)
        remaining.discard(best)
    return [chunks[i]["chunk_id"] for i in selected]


def evaluate(prepared, chunks, vecs, chunk_text, beta) -> dict:
    agg = {f"hit@{k}": 0 for k in KS}
    agg["mrr"] = 0.0
    by_rel: dict[str, list[int]] = {}
    n = 0
    for p in prepared:
        sc = fused_scores(chunks, p["d"], p["s"], p["bf"], p["facets"])
        ids = select(chunks, vecs, sc, beta)
        v = _item_metrics(p["item"], ids, chunk_text)
        n += 1
        for k in KS:
            agg[f"hit@{k}"] += v[f"hit@{k}"]
        agg["mrr"] += v["mrr"]
        rel = p["item"].get("chunk_relation") or "single"
        by_rel.setdefault(rel, []).append(1 if v["hit@5"] else 0)
    res = {k: val / n for k, val in agg.items()}
    res["n"] = n
    res["rel"] = {r: (sum(x) / len(x), len(x)) for r, x in by_rel.items()}
    return res


def run(gt_path, label, searcher, chunks, vecs, chunk_text) -> dict:
    gt = [json.loads(l) for l in open(gt_path, encoding="utf-8") if l.strip()]
    gt = [x for x in gt if x.get("answerable") is True]
    print(f"\n{'='*74}\n[{label}] {gt_path} · 평가 대상 {len(gt)}건\n{'='*74}")
    prepared = prepare(gt, searcher)
    print(f"{'beta':>6}" + "".join(f"{'hit@'+str(k):>9}" for k in KS) + f"{'mrr':>9}   relation별 hit@5")
    out = {}
    for b in BETAS:
        r = evaluate(prepared, chunks, vecs, chunk_text, b)
        out[b] = r
        rel = "  ".join(f"{k}={v[0]:.3f}({v[1]})" for k, v in sorted(r["rel"].items()))
        cells = "".join(f"{r[f'hit@{k}']:>9.3f}" for k in KS) + f"{r['mrr']:>9.3f}"
        star = "  *현행" if b == 1.0 else ""
        print(f"{b:>6.2f}{cells}   {rel}{star}")
    return out


def main() -> None:
    searcher = rag.Searcher()
    chunks = searcher.chunks
    vecs = searcher.index.reconstruct_n(0, searcher.index.ntotal).astype(np.float32)
    chunk_text = {c["chunk_id"]: _norm(c.get("text", "")) for c in chunks}
    print(f"현행 파라미터: alpha={rag.RRF_ALPHA} rrf_k={rag.RRF_K} bf={rag.BF_BOOST} "
          f"facet={rag.FACET_BOOST} cap={rag.BF_DOC_CAP} · MMR pool={POOL}")

    test = run(TEST_GT, "TEST", searcher, chunks, vecs, chunk_text)
    val = run(VAL_GT, "VAL", searcher, chunks, vecs, chunk_text)

    print(f"\n{'='*74}\n두 셋 전이성 판정 (현행 beta=1.0 대비 hit@5 증감)\n{'='*74}")
    t0, v0 = test[1.0]["hit@5"], val[1.0]["hit@5"]
    print(f"{'beta':>6}{'TEST':>10}{'VAL':>10}   판정")
    for b in BETAS:
        dt, dv = test[b]["hit@5"] - t0, val[b]["hit@5"] - v0
        verdict = "기준" if b == 1.0 else ("채택 가능(둘 다 개선)" if dt > 0 and dv > 0 else "한쪽만/악화")
        print(f"{b:>6.2f}{dt:>+10.4f}{dv:>+10.4f}   {verdict}")


if __name__ == "__main__":
    main()
