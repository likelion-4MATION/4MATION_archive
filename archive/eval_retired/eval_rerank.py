# -*- coding: utf-8 -*-
"""리랭킹 실험 (로컬 cross-encoder) — hybrid_bf vs hybrid_bf_rr 비교.

파이프라인(합의된 설계):
  검색(hybrid_bf, 업무 하드필터) → uncapped 후보 N=30 → 리랭크 → post-cap(문서당 1) → top-k
  * cap을 리랭크 '뒤'에 적용: 리랭커가 문서의 최적 청크를 직접 고르게 하고, 그 다음 문서 다양성 정리.
  * rag.py의 hybrid_bf(하드필터+cap)는 건드리지 않음. 여기서만 실험.

리랭커 백엔드:
  현재 = 로컬 cross-encoder(sentence-transformers). NCP CLOVA Re-ranking으로 갈 땐
  rerank_scores() 한 함수만 API 호출로 교체하면 됨(인터페이스 동일).

사용: cd crawler && python eval_rerank.py
필요: pip install sentence-transformers (모델 최초 실행 시 다운로드)
"""
from __future__ import annotations
import collections
import json
import sys
import time

import rag

TESTSET = "data/testset_natural_300_v3.jsonl"
RERANK_MODEL = "Dongjin-kr/ko-reranker"   # 한국어 reranker(bge 기반). 필요시 교체.
POOL_N = 30      # 리랭크 입력 후보 수(uncapped)
CAP = 1          # 리랭크 후 parent_doc_id당 청크 수
KMAX = 10        # 순위 계산 상한

_ce = None


def _get_ce():
    global _ce
    if _ce is None:
        from sentence_transformers import CrossEncoder
        _ce = CrossEncoder(RERANK_MODEL, max_length=512)
    return _ce


def rerank_scores(query: str, passages: list[str]) -> list[float]:
    """(질의, 지문) 관련도 점수. 높을수록 관련. NCP 전환 시 이 함수만 교체."""
    if not passages:
        return []
    ce = _get_ce()
    return list(ce.predict([[query, p] for p in passages]))


def first_hit_rank(hits, gt):
    for r, c in enumerate(hits, 1):
        if c["parent_doc_id"] in gt:
            return r
    return 0


def cap_by_doc(chunks, cap):
    if not cap or cap <= 0:
        return chunks
    seen = collections.Counter()
    out = []
    for c in chunks:
        d = c["parent_doc_id"]
        if seen[d] < cap:
            out.append(c)
            seen[d] += 1
    return out


def rr_search(searcher, query):
    """hybrid_bf_rr: uncapped 풀 → 리랭크 → post-cap → top-k."""
    bf = rag.classify_query_bf(query)
    pool = searcher.hybrid(query, POOL_N, bf=bf)          # uncapped 후보 (idx, score)
    chunks = [dict(searcher.chunks[i]) for i, _ in pool]
    if not chunks:
        return []
    passages = [rag.chunk_embed_text(c) for c in chunks]  # 제목+본문
    scores = rerank_scores(query, passages)
    order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    ranked = [chunks[i] for i in order]
    return cap_by_doc(ranked, CAP)[:KMAX]


def evaluate(searcher, testset, mode):
    h1 = h3 = 0
    mrr = 0.0
    per_bf = collections.defaultdict(lambda: [0, 0])   # [h3, n]
    rep_hit = rep_n = 0
    per_q = []
    t0 = time.time()
    total = len(testset)
    for i, it in enumerate(testset, 1):
        gt = set(it["gt_docs"])
        if mode == "hybrid_bf_rr":
            hits = rr_search(searcher, it["question"])
            if i % 25 == 0 or i == total:   # 진행 표시(리랭크는 느림)
                el = time.time() - t0
                print(f"  [rerank] {i}/{total}  ({el:.0f}s, {el/i:.2f}s/q)", flush=True)
        else:
            hits = searcher.search(it["question"], k=KMAX, mode=mode)
        r = first_hit_rank(hits, gt)
        hit1, hit3 = (r == 1), (1 <= r <= 3)
        h1 += hit1; h3 += hit3; mrr += (1.0 / r if r else 0.0)
        b = per_bf[it["business_function"]]
        b[0] += hit3; b[1] += 1
        if it["representative"]:
            rep_n += 1; rep_hit += hit3
        per_q.append({"q": it["question"], "bf": it["business_function"],
                      "rank": r, "hit3": hit3})
    n = len(testset)
    return {"mode": mode, "hit@1": h1 / n, "hit@3": h3 / n, "mrr": mrr / n,
            "rep": f"{rep_hit}/{rep_n}", "per_bf": per_bf, "per_q": per_q}


def main():
    testset = [json.loads(l) for l in open(TESTSET, encoding="utf-8")]
    searcher = rag.Searcher()

    base = evaluate(searcher, testset, "hybrid_bf")
    rr = evaluate(searcher, testset, "hybrid_bf_rr")

    print(f"평가셋 {len(testset)}건 · 리랭커 {RERANK_MODEL} · pool={POOL_N} cap={CAP}\n")
    print(f"{'mode':14} {'hit@1':>7} {'hit@3':>7} {'MRR':>7} {'대표6':>6}")
    for r in (base, rr):
        print(f"{r['mode']:14} {r['hit@1']:>7.3f} {r['hit@3']:>7.3f} {r['mrr']:>7.3f} {r['rep']:>6}")

    print(f"\n[업무별 hit@3 — hybrid_bf → hybrid_bf_rr]")
    for bf in sorted(base["per_bf"], key=lambda b: -base["per_bf"][b][1]):
        bh, bn = base["per_bf"][bf]
        rh, rn = rr["per_bf"][bf]
        print(f"  {bf:16} {bh/bn:.3f} -> {rh/rn:.3f}  ({rh/rn - bh/bn:+.3f})")

    d3 = rr["hit@3"] - base["hit@3"]
    d1 = rr["hit@1"] - base["hit@1"]
    print(f"\n[요약] hit@3 {base['hit@3']:.3f} -> {rr['hit@3']:.3f} ({d3:+.3f}) · "
          f"hit@1 {d1:+.3f} · 대표6 {base['rep']} -> {rr['rep']}")

    # 리랭크로 새로 회복/새로 깨진 문항 (순증감 진단)
    brank = {p["q"]: p["hit3"] for p in base["per_q"]}
    gained = [p["q"] for p in rr["per_q"] if p["hit3"] and not brank.get(p["q"])]
    lost = [p["q"] for p in rr["per_q"] if not p["hit3"] and brank.get(p["q"])]
    print(f"\n새로 적중(회복): {len(gained)} · 새로 미적중(퇴행): {len(lost)}")
    if lost:
        print("  [퇴행 문항]")
        for q in lost:
            print(f"    - {q}")


if __name__ == "__main__":
    main()
