# -*- coding: utf-8 -*-
"""소프트부스트 vs 하드필터 A/B — 업무 분류 신호를 '제외'가 아니라 'RRF 가산'으로.

동기: 하드필터(hybrid_bf)는 분류가 틀리면(오분류) 정답 문서를 후보에서 아예 배제 →
  실트래픽의 다양한 표현에서 오분류·불명이 늘면 치명적. 소프트부스트는 분류가 틀려도
  정답이 후보에 살아있어 우아하게 열화(graceful degradation)한다.

파이프라인(공통): dense/sparse 전체 풀 → RRF 융합(전 청크 점수 보유) →
  [분류 bf 있으면] 같은 업무 청크에 +β 가산 → 재정렬 → doc-cap → top-k.
  · 하드필터(ref) : rag의 실제 hybrid_bf (같은 업무만 남기고 제외)
  · softboost@β   : 제외 없이 같은 업무에 +β
  · nofilter(β=0) : 부스트 0 = 순수 전체 하이브리드(하한 기준선)

β 스케일 감각: RRF 1위 기여 = 1/(60+1) ≈ 0.0164. β=0.0164는 "top-1 한 번 더" 준 셈.
  β가 매우 크면(≥0.08) 사실상 하드필터에 수렴.

정답 판정: top-k 청크의 parent_doc_id ∈ gt_docs (eval_TF와 동일 문서단위).
사용: cd crawler && python eval_softboost.py
"""
from __future__ import annotations
import collections
import json

import rag

TESTSET = "data/testset_natural_400.jsonl"
KMAX = 10
CAP = rag.BF_DOC_CAP          # 1
RRF_K = 60
BETAS = [0.005, 0.010, 0.020, 0.040, 0.080]


def first_doc_rank(chunks, gt):
    for r, c in enumerate(chunks, 1):
        if c["parent_doc_id"] in gt:
            return r
    return 0


def cap_by_doc(pairs, cap, k):
    if not cap or cap <= 0:
        return pairs[:k]
    seen = collections.Counter()
    out = []
    for idx, sc in pairs:
        d = _CH[idx]["parent_doc_id"]
        if seen[d] < cap:
            out.append((idx, sc)); seen[d] += 1
        if len(out) >= k:
            break
    return out


def base_rrf(searcher, query):
    """분류·부스트와 무관한 전체 RRF 점수 dict (질의당 1회 계산)."""
    N = len(searcher.chunks)
    d = searcher.dense(query, N)
    s = searcher.sparse(query, N)
    rrf = {}
    for rank, (idx, _) in enumerate(d):
        rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, (idx, _) in enumerate(s):
        rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
    return rrf


def boosted_hits(rrf, bf, beta):
    """같은 업무 청크에 +β 가산 후 재정렬 → doc-cap → top-k → chunk 리스트."""
    if bf is not None and beta > 0:
        allow = rag.BF_SHARED_DOCS.get(bf, set())
        rrf = dict(rrf)
        for idx in rrf:
            c = _CH[idx]
            if c.get("business_function") == bf or c["parent_doc_id"] in allow:
                rrf[idx] += beta
    ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)
    capped = cap_by_doc(ranked, CAP, KMAX)
    return [_CH[i] for i, _ in capped]


def cause(qbf, gt_bf):
    if qbf is None:
        return "불명"
    if qbf != gt_bf:
        return "오분류"
    return "정분류"


def evaluate(searcher, testset, method, beta=0.0):
    h1 = h3 = 0; mrr = 0.0
    per_bf = collections.defaultdict(lambda: [0, 0])
    rep_hit = rep_n = 0
    per_q = {}
    for it in testset:
        gt = set(it["gt_docs"])
        if method == "ref":
            hits = searcher.search(it["question"], k=KMAX, mode="hybrid_bf")
        else:
            qbf = rag.classify_query_bf(it["question"])
            bf = None if method == "nofilter" else qbf
            hits = boosted_hits(it["_rrf"], bf, beta)
        r = first_doc_rank(hits, gt)
        hit3 = 1 <= r <= 3
        h1 += (r == 1); h3 += hit3; mrr += (1.0 / r if r else 0.0)
        b = per_bf[it["business_function"]]; b[0] += hit3; b[1] += 1
        if it["representative"]:
            rep_n += 1; rep_hit += hit3
        per_q[it["question"]] = hit3
    n = len(testset)
    lab = method if method not in ("softboost",) else f"boost@{beta:.3f}"
    return {"label": lab, "hit@1": h1 / n, "hit@3": h3 / n, "mrr": mrr / n,
            "rep": f"{rep_hit}/{rep_n}", "per_bf": per_bf, "per_q": per_q}


def main():
    global _CH
    testset = [json.loads(l) for l in open(TESTSET, encoding="utf-8")]
    searcher = rag.Searcher()
    _CH = searcher.chunks

    # 질의당 RRF·분류 1회 선계산 (β 스윕 재사용)
    for it in testset:
        it["_rrf"] = base_rrf(searcher, it["question"])
        it["_qbf"] = rag.classify_query_bf(it["question"])
        it["_cause"] = cause(it["_qbf"], it["business_function"])

    runs = [evaluate(searcher, testset, "ref"),
            evaluate(searcher, testset, "nofilter")]
    for b in BETAS:
        runs.append(evaluate(searcher, testset, "softboost", b))

    ref = runs[0]
    # 오분류/불명 문항 집합 (하드필터가 배제/무필터로 취약한 곳)
    mis_qs = [it["question"] for it in testset if it["_cause"] == "오분류"]
    unk_qs = [it["question"] for it in testset if it["_cause"] == "불명"]

    print(f"평가셋 {len(testset)}건 · cap={CAP} · RRF_K={RRF_K}")
    print(f"오분류 {len(mis_qs)}건 · 불명 {len(unk_qs)}건 · 정분류 "
          f"{sum(1 for it in testset if it['_cause']=='정분류')}건\n")
    print(f"{'method':12} {'hit@1':>7} {'hit@3':>7} {'MRR':>7} {'대표6':>6}"
          f" {'오분류':>7} {'불명':>6} {'vs_ref':>12}")
    for r in runs:
        mh = sum(r["per_q"][q] for q in mis_qs)
        uh = sum(r["per_q"][q] for q in unk_qs)
        gained = sum(1 for q, v in r["per_q"].items() if v and not ref["per_q"][q])
        lost = sum(1 for q, v in r["per_q"].items() if not v and ref["per_q"][q])
        vs = f"+{gained}/-{lost}" if r is not ref else "--"
        print(f"{r['label']:12} {r['hit@1']:>7.3f} {r['hit@3']:>7.3f} {r['mrr']:>7.3f}"
              f" {r['rep']:>6} {mh:>4}/{len(mis_qs):<2} {uh:>3}/{len(unk_qs):<2} {vs:>12}")

    # 최적 β(hit@3) 상세
    best = max(runs[2:], key=lambda r: (r["hit@3"], r["hit@1"]))
    print(f"\n[업무별 hit@3 — ref → {best['label']}]")
    for bf in sorted(ref["per_bf"], key=lambda b: -ref["per_bf"][b][1]):
        rh, rn = ref["per_bf"][bf]; bh, bn = best["per_bf"][bf]
        print(f"  {bf:16} {rh/rn:.3f} -> {bh/bn:.3f}  ({bh/bn - rh/rn:+.3f})")

    print(f"\n[{best['label']} 오분류 {len(mis_qs)}건 회복 상세]  (ref=하드필터)")
    for q in mis_qs:
        print(f"  ref={'O' if ref['per_q'][q] else 'X'} best={'O' if best['per_q'][q] else 'X'}  {q[:46]}")

    lost = [q for q in best["per_q"] if not best["per_q"][q] and ref["per_q"][q]]
    print(f"\n[{best['label']} 퇴행 {len(lost)}건 — ref는 맞았는데 소프트부스트가 놓침]")
    for q in lost:
        print(f"  {q[:52]}  (원인={next(it['_cause'] for it in testset if it['question']==q)})")


if __name__ == "__main__":
    main()
