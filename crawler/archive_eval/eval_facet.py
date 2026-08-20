# -*- coding: utf-8 -*-
"""서브인텐트 패싯 부스트 A/B — 업무 내부 형제문서 구분(착오송금 등)용 경량 레버.

배경: hybrid_bf가 업무는 맞히나 업무 내부(신청방법/구비서류/절차/유의사항, 송금인/수취인)를
  못 가림(착오송금 hit@1 0.500). 리랭킹은 무거움 → 결정론 패싯 부스트로 대체 시도.

원리: 기존 bf 소프트부스트(같은 업무 청크 +BF_BOOST) 위에, 질의의 서브인텐트를
  키워드로 잡아 매칭되는 sub_category 청크에만 +FACET_BOOST 추가. 콘텐츠 창작 0
  (기존 sub_category 패싯 활용). 소프트라 오발동 무해. 모델 재실행 없이 랭크 재조합.

FACET_BOOST=0 이면 현행 hybrid_bf와 동일(무개입) → sanity.
사용: cd crawler && python eval_facet.py
"""
from __future__ import annotations
import collections
import json

import rag

TESTSET = "data/testset_natural_400.jsonl"
KMAX = 10
KS = [1, 3, 5]
FACET_BOOSTS = [0.0, 0.005, 0.010, 0.020, 0.030, 0.050, 0.080]
TARGET_BF = "착오송금 반환 신청"

# 질의 서브인텐트 → sub_category에서 찾을 패싯 토큰(문서 타입 구분자)
FACET_RULES = [
    (["서류", "구비", "준비물", "챙기", "제출", "들고", "가지고"], "구비서류"),
    (["신청방법", "어떻게 신청", "어떻게 해", "온라인", "인터넷", "접수"], "신청방법"),
    (["대상", "자격", "누가", "해당", "받을 수 있"], "신청대상"),
    (["절차", "단계", "처리", "과정", "진행"], "절차"),
    (["유의", "주의", "조심", "알아둘"], "유의사항"),
    (["방문", "직접 가", "찾아가", "가서"], "방문접수"),
    (["법령", "규정", "법적"], "관련법령"),
]
# 방향(송금인 vs 수취인) — sub_category의 '착오송금인' / '착오송금수취인'
DIR_RULES = [
    (["받은", "들어온", "잘못 들어", "수취인", "받아버린"], "착오송금수취인"),
    (["보낸", "송금한", "이체한", "내가 보", "잘못 보", "잘못 송금"], "착오송금인"),
]


def query_facets(q: str):
    qn = q.replace(" ", "")
    facets = set()
    for kws, tok in FACET_RULES:
        if any(k.replace(" ", "") in qn for k in kws):
            facets.add(tok)
    for kws, tok in DIR_RULES:
        if any(k.replace(" ", "") in qn for k in kws):
            facets.add(tok); break   # 방향은 하나만
    return facets


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


def fuse(drank, srank, bf, facets, fboost, chunks):
    a, rk = rag.RRF_ALPHA, rag.RRF_K
    idxs = set(drank) | set(srank)
    sc = {}
    for i in idxs:
        v = 0.0
        if i in drank: v += a / (rk + drank[i] + 1)
        if i in srank: v += (1 - a) / (rk + srank[i] + 1)
        sc[i] = v
    allow = rag.BF_SHARED_DOCS.get(bf, set()) if bf else set()
    for i in sc:
        c = chunks[i]
        in_bf = bf is not None and (c.get("business_function") == bf or c["parent_doc_id"] in allow)
        if in_bf:
            sc[i] += rag.BF_BOOST
            if fboost and facets:
                hits = sum(1 for t in facets if t in c.get("sub_category", ""))
                sc[i] += fboost * hits
    ranked = sorted(sc.items(), key=lambda x: x[1], reverse=True)
    return [chunks[i] for i, _ in cap_top(ranked, rag.BF_DOC_CAP, KMAX, chunks)]


def evaluate(testset, chunks, fboost):
    hits = {k: 0 for k in KS}; mrr = 0.0
    bfh = {k: 0 for k in KS}; bfn = 0
    per_q = {}
    for it in testset:
        gt = set(it["gt_docs"])
        hc = fuse(it["_d"], it["_s"], it["_bf"], it["_facets"], fboost, chunks)
        r = first_doc_rank(hc, gt)
        for k in KS:
            if 1 <= r <= k: hits[k] += 1
        mrr += (1.0 / r if r else 0.0)
        per_q[it["question"]] = (1 <= r <= 3)
        if it["business_function"] == TARGET_BF:
            bfn += 1
            for k in KS:
                if 1 <= r <= k: bfh[k] += 1
    n = len(testset)
    return {**{f"hit@{k}": hits[k]/n for k in KS}, "mrr": mrr/n,
            "착오h1": bfh[1]/bfn, "착오h3": bfh[3]/bfn, "per_q": per_q}


def main():
    testset = [json.loads(l) for l in open(TESTSET, encoding="utf-8")]
    searcher = rag.Searcher(); chunks = searcher.chunks; N = len(chunks)
    print(f"평가셋 {len(testset)}건 · {rag.MODEL_NAME} · rrf_k={rag.RRF_K} · alpha={rag.RRF_ALPHA} · BF_BOOST={rag.BF_BOOST}\n")

    for it in testset:
        q = it["question"]
        d = searcher.dense(q, N); s = searcher.sparse(q, N)
        it["_d"] = {int(i): r for r, (i, _) in enumerate(d)}
        it["_s"] = {int(i): r for r, (i, _) in enumerate(s)}
        it["_bf"] = rag.classify_query_bf(q)
        it["_facets"] = query_facets(q)

    base = evaluate(testset, chunks, 0.0)
    hdr = f"{'FACET_BOOST':>12}" + "".join(f"{'hit@'+str(k):>8}" for k in KS) + f"{'MRR':>8}{'착오h1':>7}{'착오h3':>7}"
    print(hdr); print("-"*len(hdr))
    results = {}
    for fb in FACET_BOOSTS:
        m = evaluate(testset, chunks, fb) if fb != 0.0 else base
        results[fb] = m
        star = " *(현행)" if fb == 0.0 else ""
        print(f"{fb:>12.3f}" + "".join(f"{m['hit@'+str(k)]:>8.3f}" for k in KS)
              + f"{m['mrr']:>8.3f}{m['착오h1']:>7.3f}{m['착오h3']:>7.3f}{star}")

    best = max((fb for fb in FACET_BOOSTS if fb != 0.0),
               key=lambda fb: (results[fb]["hit@3"], results[fb]["착오h3"], results[fb]["mrr"]))
    m = results[best]
    g = [q for q in m["per_q"] if m["per_q"][q] and not base["per_q"][q]]
    l = [q for q in m["per_q"] if not m["per_q"][q] and base["per_q"][q]]
    print(f"\n[최적 FACET_BOOST={best}] hit@3 {base['hit@3']:.3f}→{m['hit@3']:.3f} · "
          f"착오h1 {base['착오h1']:.3f}→{m['착오h1']:.3f} · 회복 {len(g)} · 퇴행 {len(l)}")
    for q in g: print(f"   +{q[:52]}")
    for q in l: print(f"   -{q[:52]}")


if __name__ == "__main__":
    main()
