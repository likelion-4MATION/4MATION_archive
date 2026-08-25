# -*- coding: utf-8 -*-
"""가중 RRF(α) × 소프트부스트(β) 그리드 A/B — bge-m3 재튜닝용.

동기: bge-m3로 dense가 강해지니, 약한 dense(ko-sroberta) 기준으로 잡힌
  β=0.02 + 동일가중 RRF가 과보정으로 작동 — dense가 1위로 뽑은 정답을
  (a) 소프트부스트가 틀린 업무 문서로 밀어내거나(오분류) (b) BM25/RRF 융합이
  끌어내림(불명). → dense를 얼마나 믿을지(α)와 부스트 강도(β)를 함께 스윕.

파이프라인(공통): dense/sparse 전체 풀 랭크 → 가중 RRF 융합 → 같은 업무 +β →
  doc-cap → top-k.
  · RRF 점수 = α·1/(rrf_k+rank_d) + (1−α)·1/(rrf_k+rank_s)   (α=0.5 현행, α=1.0 dense-only)
  · β = 같은 업무 청크 가산량 (0이면 부스트 없음)

정답 판정: top-k 청크 parent_doc_id ∈ gt_docs (eval_TF와 동일 문서단위).
질의당 dense/sparse 랭크 1회 선계산 → 그리드 재조합은 임베딩 없이 즉시.

사용: cd crawler && python eval_rrf_tune.py
"""
from __future__ import annotations
import collections
import json

import rag

TESTSET = "data/testset_natural_400.jsonl"
KMAX = 10
CAP = rag.BF_DOC_CAP
RRF_K = 60
ALPHAS = [0.5, 0.6, 0.7, 0.8, 1.0]   # dense 가중 (0.5=현행 동일, 1.0=dense-only)
BETAS = [0.0, 0.005, 0.010, 0.020]   # 소프트부스트 강도
CUR = (0.5, 0.020)                    # 현행 배포 조합 (표에 * 표시)


def first_doc_rank(chunks, gt):
    for r, c in enumerate(chunks, 1):
        if c["parent_doc_id"] in gt:
            return r
    return 0


def cap_top(pairs, cap, k):
    if not cap or cap <= 0:
        return pairs[:k]
    seen = collections.Counter(); out = []
    for idx, sc in pairs:
        d = _CH[idx]["parent_doc_id"]
        if seen[d] < cap:
            out.append((idx, sc)); seen[d] += 1
        if len(out) >= k:
            break
    return out


def rank_maps(searcher, query):
    """전체 풀 dense/sparse 랭크 dict (질의당 1회). idx -> 1-based rank."""
    N = len(searcher.chunks)
    d = {idx: r for r, (idx, _) in enumerate(searcher.dense(query, N))}
    s = {idx: r for r, (idx, _) in enumerate(searcher.sparse(query, N))}
    return d, s


def fuse(dmap, smap, alpha, bf, beta):
    idxs = set(dmap) | set(smap)
    sc = {}
    for i in idxs:
        v = 0.0
        if i in dmap:
            v += alpha * 1.0 / (RRF_K + dmap[i] + 1)
        if i in smap:
            v += (1 - alpha) * 1.0 / (RRF_K + smap[i] + 1)
        sc[i] = v
    if bf is not None and beta > 0:
        allow = rag.BF_SHARED_DOCS.get(bf, set())
        for i in sc:
            c = _CH[i]
            if c.get("business_function") == bf or c["parent_doc_id"] in allow:
                sc[i] += beta
    ranked = sorted(sc.items(), key=lambda x: x[1], reverse=True)
    capped = cap_top(ranked, CAP, KMAX)
    return [_CH[i] for i, _ in capped]


def evaluate(testset, alpha, beta):
    h1 = h3 = 0; mrr = 0.0; rep_h = rep_n = 0
    per_q = {}
    for it in testset:
        gt = set(it["gt_docs"])
        hits = fuse(it["_d"], it["_s"], alpha, it["_qbf"], beta)
        r = first_doc_rank(hits, gt)
        hit3 = 1 <= r <= 3
        h1 += (r == 1); h3 += hit3; mrr += (1.0 / r if r else 0.0)
        if it["representative"]:
            rep_n += 1; rep_h += hit3
        per_q[it["question"]] = hit3
    n = len(testset)
    return {"a": alpha, "b": beta, "hit@1": h1 / n, "hit@3": h3 / n,
            "mrr": mrr / n, "rep": f"{rep_h}/{rep_n}", "per_q": per_q}


def main():
    global _CH
    testset = [json.loads(l) for l in open(TESTSET, encoding="utf-8")]
    searcher = rag.Searcher()
    _CH = searcher.chunks

    for it in testset:
        it["_d"], it["_s"] = rank_maps(searcher, it["question"])
        it["_qbf"] = rag.classify_query_bf(it["question"])
        gt_bf = it["business_function"]
        it["_cause"] = ("불명" if it["_qbf"] is None
                        else "오분류" if it["_qbf"] != gt_bf else "정분류")

    mis = [it["question"] for it in testset if it["_cause"] == "오분류"]
    unk = [it["question"] for it in testset if it["_cause"] == "불명"]

    runs = [evaluate(testset, a, b) for a in ALPHAS for b in BETAS]

    print(f"평가셋 {len(testset)}건 · 모델 {rag.MODEL_NAME} · cap={CAP} · RRF_K={RRF_K}")
    print(f"오분류 {len(mis)}건 · 불명 {len(unk)}건 · 정분류 "
          f"{sum(1 for it in testset if it['_cause']=='정분류')}건")
    print(f"(α=dense가중 0.5동일~1.0denseonly · β=부스트 · *=현행배포)\n")

    print(f"{'α':>4} {'β':>6} {'hit@1':>7} {'hit@3':>7} {'MRR':>7} {'대표6':>5}"
          f" {'오분류':>7} {'불명':>7}")
    cur = next(r for r in runs if (r['a'], r['b']) == CUR)
    for r in sorted(runs, key=lambda r: (-r["hit@3"], -r["hit@1"])):
        mh = sum(r["per_q"][q] for q in mis)
        uh = sum(r["per_q"][q] for q in unk)
        star = "*" if (r["a"], r["b"]) == CUR else " "
        print(f"{r['a']:>4.1f} {r['b']:>6.3f} {r['hit@1']:>7.3f} {r['hit@3']:>7.3f}"
              f" {r['mrr']:>7.3f} {r['rep']:>5} {mh:>4}/{len(mis):<2} {uh:>3}/{len(unk):<2} {star}")

    best = max(runs, key=lambda r: (r["hit@3"], r["hit@1"], r["mrr"]))
    print(f"\n[최적 α={best['a']} β={best['b']}]  vs  [현행 α={CUR[0]} β={CUR[1]}]")
    print(f"  hit@1 {cur['hit@1']:.3f} -> {best['hit@1']:.3f}   "
          f"hit@3 {cur['hit@3']:.3f} -> {best['hit@3']:.3f}   "
          f"MRR {cur['mrr']:.3f} -> {best['mrr']:.3f}")
    gained = [q for q in best["per_q"] if best["per_q"][q] and not cur["per_q"][q]]
    lost = [q for q in best["per_q"] if not best["per_q"][q] and cur["per_q"][q]]
    print(f"  회복 {len(gained)} · 퇴행 {len(lost)}")
    for q in gained:
        c = next(it["_cause"] for it in testset if it["question"] == q)
        print(f"    +[{c}] {q[:48]}")
    for q in lost:
        c = next(it["_cause"] for it in testset if it["question"] == q)
        print(f"    -[{c}] {q[:48]}")


if __name__ == "__main__":
    main()
