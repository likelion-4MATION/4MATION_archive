# -*- coding: utf-8 -*-
"""rrf_k 스윕 A/B — bge-m3에서 RRF 상수(k)가 정확도에 미치는 영향 검증.

배경: 타 브랜치 팀원이 순수 hybrid + RRF(k=5)로 hit@3 0.930 보고(우리 k=60).
  강한 dense(bge-m3)에선 낮은 rrf_k가 상위 랭크를 강하게 신뢰 -> 융합이 날카로워짐.
  우리 데이터 개선(재태깅+gt교정) 위에서 rrf_k를 낮추면 더 오르는지, 그리고
  bf 장치(soft+cap)가 여전히 값을 하는지 함께 확인.

구성(현재 인덱스=bge-m3, 현재 400셋=재태깅/ gt교정 반영):
  - hybrid_nobf      : 순수 하이브리드(동일가중 RRF, bf/cap 없음) = 팀원식. rag.hybrid.
  - hybrid_bf(ours)  : 소프트부스트(alpha=RRF_ALPHA, boost=BF_BOOST) + doc-cap.
각 구성을 rrf_k in {5,10,20,40,60} 로 스윕. 정답 판정 문서단위(eval_TF 동일).

사용: cd crawler && python eval_rrfk.py
"""
from __future__ import annotations
import collections
import json

import rag

TESTSET = "data/testset_natural_400.jsonl"
KMAX = 10
KS = [1, 3, 5]
RRF_KS = [5, 10, 20, 40, 60]
CAP = rag.BF_DOC_CAP


def first_doc_rank(chunks, gt):
    for r, c in enumerate(chunks, 1):
        if c["parent_doc_id"] in gt:
            return r
    return 0


def cap_top(pairs, cap, k, chunks):
    if not cap or cap <= 0:
        return pairs[:k]
    seen = collections.Counter(); out = []
    for idx, sc in pairs:
        d = chunks[idx]["parent_doc_id"]
        if seen[d] < cap:
            out.append((idx, sc)); seen[d] += 1
        if len(out) >= k:
            break
    return out


def run(searcher, testset, mode, rrf_k):
    N = len(searcher.chunks)
    hits = {k: 0 for k in KS}; mrr = 0.0; rep_h = rep_n = 0
    for it in testset:
        gt = set(it["gt_docs"]); q = it["question"]
        if mode == "hybrid_nobf":
            pairs = searcher.hybrid(q, KMAX, pool=N, rrf_k=rrf_k, bf=None)
            hc = [searcher.chunks[i] for i, _ in pairs]
        else:  # hybrid_bf (soft + cap)
            bf = rag.classify_query_bf(q)
            pool = searcher.hybrid_soft(q, N, rrf_k=rrf_k, bf=bf, boost=rag.BF_BOOST)
            hc = [searcher.chunks[i] for i, _ in cap_top(pool, CAP, KMAX, searcher.chunks)]
        r = first_doc_rank(hc, gt)
        for k in KS:
            if 1 <= r <= k:
                hits[k] += 1
        mrr += (1.0 / r if r else 0.0)
        if it["representative"]:
            rep_n += 1; rep_h += (1 <= r <= 3)
    n = len(testset)
    return {**{f"hit@{k}": hits[k] / n for k in KS}, "mrr": mrr / n, "rep": f"{rep_h}/{rep_n}"}


def main():
    testset = [json.loads(l) for l in open(TESTSET, encoding="utf-8")]
    searcher = rag.Searcher()
    print(f"평가셋 {len(testset)}건 · 모델 {rag.MODEL_NAME} · alpha={rag.RRF_ALPHA} · boost={rag.BF_BOOST} · cap={CAP}")
    print(f"(현행 배포 = hybrid_bf · rrf_k=60)\n")
    hdr = f"{'구성':16}{'rrf_k':>6}" + "".join(f"{'hit@'+str(k):>8}" for k in KS) + f"{'MRR':>8}{'대표6':>6}"
    print(hdr); print("-" * len(hdr))
    best = None
    for mode in ["hybrid_nobf", "hybrid_bf"]:
        for rk in RRF_KS:
            m = run(searcher, testset, mode, rk)
            star = " *" if (mode == "hybrid_bf" and rk == 60) else ""
            print(f"{mode:16}{rk:>6}" + "".join(f"{m['hit@'+str(k)]:>8.3f}" for k in KS)
                  + f"{m['mrr']:>8.3f}{m['rep']:>6}{star}")
            if best is None or m["hit@3"] > best[2]["hit@3"]:
                best = (mode, rk, m)
        print()
    b = best
    print(f"[최고 hit@3] {b[0]} · rrf_k={b[1]} → hit@1 {b[2]['hit@1']:.3f} · hit@3 {b[2]['hit@3']:.3f} · MRR {b[2]['mrr']:.3f}")
    print(" * = 현행 배포 기준값")


if __name__ == "__main__":
    main()
