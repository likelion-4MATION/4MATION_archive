# -*- coding: utf-8 -*-
"""문서측 임베딩 입력 강화 A/B — title+본문 vs +breadcrumb / +sub_category.

배경(규남 진단): 착오송금 '유의사항' page_title이 착오송금인용/수취인용 두 문서에 동일 →
  현재 임베딩 입력(title+본문)만으론 형제 구분 불가. 변별 신호(착오송금인/수취인)는
  breadcrumb·sub_category 메타에 이미 존재 → 문서측 입력에 주입하면 벡터가 벌어짐.
  콘텐츠 창작 0(기존 메타 활용). 쿼리측은 그대로(비대칭) → no-creation 원칙 준수.

측정: 현행 파이프라인(가중RRF alpha·부스트·cap·rrf_k, hybrid_bf) 그대로,
  dense 임베딩 행렬만 변형별로 교체. hit@1/3/5·MRR·착오송금 세분·회복/퇴행.
  BM25(sparse)는 본문 기반이라 불변 → dense 입력 효과만 격리.

사용: cd crawler && python eval_embedinput.py   (bge-m3 재임베딩 포함, 로컬 실행)
"""
from __future__ import annotations
import collections
import json

import numpy as np
import rag

TESTSET = "data/testset_natural_400.jsonl"
KMAX = 10
KS = [1, 3, 5]
VARIANTS = ["cur", "breadcrumb", "sub_category"]
TARGET_BF = "착오송금 반환 신청"


def bc_str(c):
    b = c.get("breadcrumb", "")
    return " > ".join(b) if isinstance(b, list) else (b or "")


def doc_input(c, mode):
    title = c.get("page_title", ""); text = c["text"]
    base = f"{title}\n{text}" if title else text
    if mode == "breadcrumb" and bc_str(c):
        return f"{bc_str(c)}\n{base}"
    if mode == "sub_category" and c.get("sub_category"):
        return f"{c['sub_category']}\n{base}"
    return base


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


def fuse(drank, srank, bf, chunks):
    """가중 RRF(alpha) + 소프트부스트 + cap → 상위 chunk 리스트 (hybrid_bf 재현)."""
    idxs = set(drank) | set(srank)
    a, rk = rag.RRF_ALPHA, rag.RRF_K
    sc = {}
    for i in idxs:
        v = 0.0
        if i in drank: v += a / (rk + drank[i] + 1)
        if i in srank: v += (1 - a) / (rk + srank[i] + 1)
        sc[i] = v
    if bf is not None and rag.BF_BOOST > 0:
        allow = rag.BF_SHARED_DOCS.get(bf, set())
        for i in sc:
            c = chunks[i]
            if c.get("business_function") == bf or c["parent_doc_id"] in allow:
                sc[i] += rag.BF_BOOST
    ranked = sorted(sc.items(), key=lambda x: x[1], reverse=True)
    capped = cap_top(ranked, rag.BF_DOC_CAP, KMAX, chunks)
    return [chunks[i] for i, _ in capped]


def evaluate(testset, chunks, E, sranks):
    hits = {k: 0 for k in KS}; mrr = 0.0
    bf_hits = {k: 0 for k in KS}; bf_n = 0
    per_q = {}
    for it in testset:
        gt = set(it["gt_docs"])
        qv = it["_qv"]
        scores = E @ qv
        order = np.argsort(scores)[::-1]
        drank = {int(idx): r for r, idx in enumerate(order)}
        hc = fuse(drank, sranks[it["question"]], it["_bf"], chunks)
        r = first_doc_rank(hc, gt)
        for k in KS:
            if 1 <= r <= k: hits[k] += 1
        mrr += (1.0 / r if r else 0.0)
        per_q[it["question"]] = (1 <= r <= 3)
        if it["business_function"] == TARGET_BF:
            bf_n += 1
            for k in KS:
                if 1 <= r <= k: bf_hits[k] += 1
    n = len(testset)
    return {**{f"hit@{k}": hits[k]/n for k in KS}, "mrr": mrr/n,
            "착오h1": bf_hits[1]/bf_n, "착오h3": bf_hits[3]/bf_n, "per_q": per_q}


def main():
    testset = [json.loads(l) for l in open(TESTSET, encoding="utf-8")]
    searcher = rag.Searcher()
    chunks = searcher.chunks
    N = len(chunks)
    print(f"평가셋 {len(testset)}건 · 모델 {rag.MODEL_NAME} · rrf_k={rag.RRF_K} · alpha={rag.RRF_ALPHA}\n")

    # 쿼리벡터 + 질의분류 + sparse 랭크(불변) 선계산
    sranks = {}
    for it in testset:
        q = it["question"]
        it["_qv"] = rag.embed_texts([q])[0]
        it["_bf"] = rag.classify_query_bf(q)
        s = searcher.sparse(q, N)
        sranks[q] = {int(i): r for r, (i, _) in enumerate(s)}

    results = {}
    for mode in VARIANTS:
        E = rag.embed_texts([doc_input(c, mode) for c in chunks])  # 정규화됨
        results[mode] = evaluate(testset, chunks, E, sranks)

    cur = results["cur"]
    hdr = f"{'입력변형':14}" + "".join(f"{'hit@'+str(k):>8}" for k in KS) + f"{'MRR':>8}{'착오h1':>7}{'착오h3':>7}"
    print(hdr); print("-"*len(hdr))
    for mode in VARIANTS:
        m = results[mode]
        print(f"{mode:14}" + "".join(f"{m['hit@'+str(k)]:>8.3f}" for k in KS)
              + f"{m['mrr']:>8.3f}{m['착오h1']:>7.3f}{m['착오h3']:>7.3f}")

    for mode in VARIANTS:
        if mode == "cur": continue
        m = results[mode]
        g = [q for q in m["per_q"] if m["per_q"][q] and not cur["per_q"][q]]
        l = [q for q in m["per_q"] if not m["per_q"][q] and cur["per_q"][q]]
        print(f"\n[{mode} vs cur] hit@3 {cur['hit@3']:.3f} -> {m['hit@3']:.3f} · 회복 {len(g)} · 퇴행 {len(l)}")
        for q in g: print(f"   +{q[:52]}")
        for q in l: print(f"   -{q[:52]}")


if __name__ == "__main__":
    main()
