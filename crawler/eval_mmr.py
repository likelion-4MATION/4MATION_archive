# -*- coding: utf-8 -*-
"""MMR-only(팀원 구성) vs 현행 hybrid_bf 재현 검증 — bge-m3, hit@1/3/5/10 동시 측정.

배경: 타 브랜치 팀원이 "bf·cap 없이 MMR만 + bge-m3"로 정확도 95%를 보고.
  우리 핵심 지표는 hit@3인데, 95%가 (a) 같은 k에서 MMR이 실제로 이긴 건지
  (b) 그냥 bge-m3에 k를 키운 hit@10인지 가려야 함 -> 여러 k를 한 번에 측정.

비교 구성(전부 현재 인덱스=bge-m3 기준):
  - hybrid_bf(ours)    : 현행 배포(소프트부스트 + doc-cap). searcher.search 사용.
  - hybrid_nobf_nocap  : bf/ cap 없는 순수 하이브리드 top-k (MMR 효과 분리 대조군)
  - mmr_nobf_nocap@L   : 팀원 구성 — bf없음/cap없음, 하이브리드 풀(FETCH_K)->MMR->top-k
  - dense_only         : 순수 dense top-k (모델 상한 참고)

정답 판정: top-k 청크의 parent_doc_id in gt_docs (문서 단위, eval_TF 동일).
사용: cd crawler && python eval_mmr.py
"""
from __future__ import annotations
import json

import numpy as np
import rag

TESTSET = "data/testset_natural_400.jsonl"
EMB_PATH = "data/index/emb.npy"
FETCH_K = 20
KMAX = 10
LAMBDAS = [0.3, 0.5, 0.7]
KS = [1, 3, 5, 10]


def first_doc_rank(chunks, gt):
    for r, c in enumerate(chunks, 1):
        if c["parent_doc_id"] in gt:
            return r
    return 0


def _mmr(cand_idx, k, qvec, E, lam):
    if not cand_idx:
        return []
    Ec = E[cand_idx]
    rel = Ec @ qvec
    sim = Ec @ Ec.T
    m = len(cand_idx)
    selected = [int(np.argmax(rel))]
    remaining = set(range(m)) - set(selected)
    while remaining and len(selected) < k:
        best, best_s = None, -1e18
        for j in remaining:
            red = max(sim[j][s] for s in selected)
            sc = lam * rel[j] - (1 - lam) * red
            if sc > best_s:
                best_s, best = sc, j
        selected.append(best); remaining.discard(best)
    return [cand_idx[i] for i in selected]


def eval_ranks(rank_fn, testset):
    hits = {k: 0 for k in KS}
    mrr = 0.0; rep_h = rep_n = 0
    for it in testset:
        r = rank_fn(it)
        for k in KS:
            if 1 <= r <= k:
                hits[k] += 1
        mrr += (1.0 / r if r else 0.0)
        if it["representative"]:
            rep_n += 1; rep_h += (1 <= r <= 3)
    n = len(testset)
    return {**{f"hit@{k}": hits[k] / n for k in KS}, "mrr": mrr / n,
            "rep": f"{rep_h}/{rep_n}"}


def main():
    testset = [json.loads(l) for l in open(TESTSET, encoding="utf-8")]
    searcher = rag.Searcher()
    E = np.load(EMB_PATH)
    assert E.shape[0] == len(searcher.chunks), "emb.npy와 chunk_meta 정렬 불일치(재빌드?)"
    print(f"평가셋 {len(testset)}건 · 모델 {rag.MODEL_NAME} · dim {E.shape[1]} · FETCH_K={FETCH_K}\n")

    for it in testset:
        q = it["question"]
        it["_pool"] = [i for i, _ in searcher.hybrid(q, FETCH_K, bf=None)]
        it["_qvec"] = rag.embed_texts([q])[0]

    runs = {}

    def r_hybrid_bf(it):
        return first_doc_rank(searcher.search(it["question"], k=KMAX, mode="hybrid_bf"),
                              set(it["gt_docs"]))
    runs["hybrid_bf(ours)"] = eval_ranks(r_hybrid_bf, testset)

    def r_hybrid_nobf(it):
        hits = [searcher.chunks[i] for i, _ in searcher.hybrid(it["question"], KMAX, bf=None)]
        return first_doc_rank(hits, set(it["gt_docs"]))
    runs["hybrid_nobf_nocap"] = eval_ranks(r_hybrid_nobf, testset)

    def r_dense(it):
        hits = [searcher.chunks[i] for i, _ in searcher.dense(it["question"], KMAX)]
        return first_doc_rank(hits, set(it["gt_docs"]))
    runs["dense_only"] = eval_ranks(r_dense, testset)

    for lam in LAMBDAS:
        def r_mmr(it, lam=lam):
            sel = _mmr(it["_pool"], KMAX, it["_qvec"], E, lam)
            return first_doc_rank([searcher.chunks[i] for i in sel], set(it["gt_docs"]))
        runs[f"mmr_nobf_nocap@{lam}"] = eval_ranks(r_mmr, testset)

    hdr = f"{'구성':22}" + "".join(f"{'hit@'+str(k):>8}" for k in KS) + f"{'MRR':>8}{'대표6':>6}"
    print(hdr); print("-" * len(hdr))
    for name, m in runs.items():
        line = f"{name:22}" + "".join(f"{m['hit@'+str(k)]:>8.3f}" for k in KS)
        print(line + f"{m['mrr']:>8.3f}{m['rep']:>6}")

    print("\n해석: 팀원 95%가 mmr행의 어느 hit@k인지 대조 · 같은 k에서 mmr vs hybrid_nobf로 MMR 순기여 확인.")


if __name__ == "__main__":
    main()
