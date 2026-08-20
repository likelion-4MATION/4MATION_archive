# -*- coding: utf-8 -*-
"""형제 청크(같은 parent_doc) 점수 전파 실험 — and 문항의 '간발의 차' 회수용. (기각)

문제: and 문항 실패 다수가 "필요 스팬 하나는 top-5 안인데 나머지가 6~10위"였다.
같은 문서의 형제 청크가 top-5 경계 바로 밖에 걸린다.

착안: 어떤 문서의 청크가 강하게 매칭되면 그 문서의 다른 청크도 관련 있을 확률이
높다(cluster hypothesis). 문서 단위 점수를 만들어 소량을 형제에게 전파한다.
  doc_score(d) = max(chunk score in d)
  final(c) = score(c) + LAMBDA * doc_score(parent(c))
LAMBDA=0이면 현행과 완전히 동일하다.

결과: 기각. TEST/VAL 두 셋 모두 λ>0에서 단조 하락하고, 재청킹에 불변인 주지표
single이 밀려난다. 다시 파지 않기 위해 남겨둔다.

사용: cd crawler && python eval_sibling_boost.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import rag
from eval_anchor_span_multi import RETRIEVAL_DEPTH, _item_metrics, _norm

TEST_GT = "data/gt_natural430_curated.jsonl"
VAL_GT = "data/gt_natural355.jsonl"
LAMBDAS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50]
KS = (1, 3, 5, 10)


def prepare(gt: list[dict], searcher: "rag.Searcher") -> list[dict]:
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


def fuse(chunks, d_rank, s_rank, bf, facets, lam) -> list[str]:
    idxs = set(d_rank) | set(s_rank)
    sc: dict[int, float] = {}
    for i in idxs:
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

    if lam > 0:
        doc_best: dict[str, float] = {}
        for i, v in sc.items():
            d = chunks[i]["parent_doc_id"]
            if v > doc_best.get(d, 0.0):
                doc_best[d] = v
        for i in sc:
            sc[i] += lam * doc_best[chunks[i]["parent_doc_id"]]

    ranked = sorted(sc.items(), key=lambda x: -x[1])
    if rag.BF_DOC_CAP:
        seen: dict[str, int] = {}
        capped = []
        for idx, score in ranked:
            d = chunks[idx]["parent_doc_id"]
            if seen.get(d, 0) < rag.BF_DOC_CAP:
                capped.append((idx, score))
                seen[d] = seen.get(d, 0) + 1
        ranked = capped
    return [chunks[i]["chunk_id"] for i, _ in ranked[:RETRIEVAL_DEPTH]]


def evaluate(prepared, chunks, chunk_text, lam) -> dict:
    agg = {f"hit@{k}": 0 for k in KS}
    agg["mrr"] = 0.0
    by_rel: dict[str, list[int]] = {}
    n = 0
    for p in prepared:
        ids = fuse(chunks, p["d"], p["s"], p["bf"], p["facets"], lam)
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


def run(gt_path: str, label: str, searcher, chunks, chunk_text) -> dict:
    gt = [json.loads(l) for l in open(gt_path, encoding="utf-8") if l.strip()]
    gt = [x for x in gt if x.get("answerable") is True]
    print(f"\n{'='*70}\n[{label}] {gt_path} · 평가 대상 {len(gt)}건\n{'='*70}")
    prepared = prepare(gt, searcher)
    header = f"{'lambda':>8}" + "".join(f"{'hit@'+str(k):>9}" for k in KS) + f"{'mrr':>9}   relation별 hit@5"
    print(header)
    results = {}
    for lam in LAMBDAS:
        r = evaluate(prepared, chunks, chunk_text, lam)
        results[lam] = r
        rel = "  ".join(f"{k}={v[0]:.3f}({v[1]})" for k, v in sorted(r["rel"].items()))
        cells = "".join(f"{r[f'hit@{k}']:>9.3f}" for k in KS) + f"{r['mrr']:>9.3f}"
        star = "  *현행" if lam == 0.0 else ""
        print(f"{lam:>8.2f}{cells}   {rel}{star}")
    return results


def main() -> None:
    searcher = rag.Searcher()
    chunks = searcher.chunks
    chunk_text = {c["chunk_id"]: _norm(c.get("text", "")) for c in chunks}
    print(f"현행 파라미터: alpha={rag.RRF_ALPHA} rrf_k={rag.RRF_K} "
          f"bf={rag.BF_BOOST} facet={rag.FACET_BOOST} cap={rag.BF_DOC_CAP}")

    test = run(TEST_GT, "TEST", searcher, chunks, chunk_text)
    val = run(VAL_GT, "VAL", searcher, chunks, chunk_text)

    print(f"\n{'='*70}\n두 셋 전이성 판정 (현행 lambda=0 대비 hit@5 증감)\n{'='*70}")
    t0, v0 = test[0.0]["hit@5"], val[0.0]["hit@5"]
    print(f"{'lambda':>8}{'TEST':>10}{'VAL':>10}   판정")
    for lam in LAMBDAS:
        dt = test[lam]["hit@5"] - t0
        dv = val[lam]["hit@5"] - v0
        ok = "채택 가능(둘 다 개선)" if dt > 0 and dv > 0 else ("한쪽만/악화" if lam else "기준")
        print(f"{lam:>8.2f}{dt:>+10.4f}{dv:>+10.4f}   {ok}")


if __name__ == "__main__":
    main()
