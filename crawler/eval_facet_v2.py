# -*- coding: utf-8 -*-
"""FACET_BOOST 강화 스윕 — gt_relabeled_v7.jsonl 기준 청크 단위 재현.

기존 eval_facet.py(2026-07-22)는 testset_natural_400 + gt_docs(문서 단위)로 판단해서
"같은 문서 안 어느 청크인가" 문제를 못 봤다. 지금 문제(형제 청크 미세구분)는 청크 단위로만
드러나므로, gt_relabeled_v7.jsonl + eval_anchor_v3.py와 동일한 채점 로직(_get_gt_chunk_ids,
_get_relation, _hit_at_k)을 그대로 재사용해 청크 단위로 다시 스윕한다.

전제(구조적 한계, 실행 전에 확인한 것):
  - 정답 청크의 66%가 sub_category 형제그룹 4개 이상에 속함(같은 FAQ 페이지 여러 Q&A 등).
  - FACET_BOOST는 sub_category 매칭 여부로만 가산하므로, 형제가 전부 같은 sub_category면
    boost를 아무리 키워도 그 그룹 내부에서는 무의미하다(전부 같이 오르니 상대순위 불변).
  - 따라서 이 스윕의 진짜 목적은 "낮은 boost로도 이미 회복 가능한 그룹 간 혼입"과
    "boost로는 원천적으로 불가능한 그룹 내부 혼입"을 분리해서 보여주는 것이다.

사용: cd crawler && python eval_facet_v2.py
"""
from __future__ import annotations
import collections
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

import rag
from eval_anchor_v3 import _get_gt_chunk_ids, _get_relation, _hit_at_k, _recall_at_k

GT_PATH = "data/gt_relabeled_v7.jsonl"
KS = (1, 3, 5, 10)
FACET_BOOSTS = [0.0, 0.03, 0.05, 0.08, 0.12, 0.18, 0.25, 0.35]  # 0.03 = 현행(*)


def fuse(searcher, d_rank: dict, s_rank: dict, bf, facets: set, fboost: float) -> list[int]:
    """rag.Searcher.hybrid_soft + _cap_by_doc를 사전계산된 순위로 재구성(재임베딩 없음)."""
    chunks = searcher.chunks
    alpha, rrf_k = rag.RRF_ALPHA, rag.RRF_K
    idxs = set(d_rank) | set(s_rank)
    sc: dict[int, float] = {}
    for i in idxs:
        v = 0.0
        if i in d_rank:
            v += alpha / (rrf_k + d_rank[i] + 1)
        if i in s_rank:
            v += (1 - alpha) / (rrf_k + s_rank[i] + 1)
        sc[i] = v
    allow = rag.BF_SHARED_DOCS.get(bf, set()) if bf else set()
    for i in sc:
        c = chunks[i]
        in_bf = bf is not None and (c.get("business_function") == bf or c["parent_doc_id"] in allow)
        if in_bf:
            sc[i] += rag.BF_BOOST
            if fboost and facets:
                hit = sum(1 for t in facets if t in c.get("sub_category", ""))
                if hit:
                    sc[i] += fboost * hit
    ranked = sorted(sc.items(), key=lambda x: -x[1])
    capped = searcher._cap_by_doc(ranked, rag.BF_DOC_CAP)
    return [idx for idx, _ in capped[:max(KS)]]


def sibling_bucket(size: int) -> str:
    if size <= 1:
        return "1(유일)"
    if size <= 3:
        return "2-3"
    if size <= 7:
        return "4-7"
    return "8+"


def main() -> None:
    gt_all = [json.loads(l) for l in open(GT_PATH, encoding="utf-8") if l.strip()]
    gt = [x for x in gt_all if x.get("answerable") is True]
    print(f"평가 대상(answerable=true) {len(gt)}건 / 전체 {len(gt_all)}건\n")

    searcher = rag.Searcher()
    chunks = searcher.chunks
    N = len(chunks)
    by_subcat_size = collections.Counter(c.get("sub_category") for c in chunks)

    # 질의당 dense/sparse 순위 + 업무분류 + 패싯 + gold/relation 사전계산(1회만, 스윕 재사용)
    prepared = []
    for it in gt:
        q = it["question"]
        d = searcher.dense(q, N)
        s = searcher.sparse(q, N)
        gold_ids = _get_gt_chunk_ids(it)
        relation = _get_relation(it)
        gold_idx0 = next((i for i, c in enumerate(chunks) if c["chunk_id"] == gold_ids[0]), None)
        gold_subcat_size = by_subcat_size.get(chunks[gold_idx0].get("sub_category")) if gold_idx0 is not None else 1
        prepared.append({
            "d": {int(i): r for r, (i, _) in enumerate(d)},
            "s": {int(i): r for r, (i, _) in enumerate(s)},
            "bf": rag.classify_query_bf(q),
            "facets": rag.query_facets(q),
            "gold_ids": gold_ids,
            "relation": relation,
            "domain": it.get("business_function") or "(unknown)",
            "bucket": sibling_bucket(gold_subcat_size),
        })
    print("전처리 완료(임베딩 1회) — 스윕 시작\n")

    def evaluate(fboost: float) -> dict:
        hit = {k: 0 for k in KS}
        by_domain = collections.defaultdict(lambda: {k: 0 for k in KS} | {"n": 0})
        by_bucket = collections.defaultdict(lambda: {"hit3": 0, "n": 0})
        for p in prepared:
            retrieved_idx = fuse(searcher, p["d"], p["s"], p["bf"], p["facets"], fboost)
            retrieved_ids = [chunks[i]["chunk_id"] for i in retrieved_idx]
            for k in KS:
                if _hit_at_k(p["gold_ids"], retrieved_ids, p["relation"], k):
                    hit[k] += 1
                    by_domain[p["domain"]][k] += 1
            by_domain[p["domain"]]["n"] += 1
            by_bucket[p["bucket"]]["n"] += 1
            if _hit_at_k(p["gold_ids"], retrieved_ids, p["relation"], 3):
                by_bucket[p["bucket"]]["hit3"] += 1
        n = len(prepared)
        return {"hit": {k: hit[k] / n for k in KS}, "by_domain": by_domain, "by_bucket": by_bucket, "n": n}

    results = {fb: evaluate(fb) for fb in FACET_BOOSTS}

    print(f"{'FACET_BOOST':>12}" + "".join(f"{'hit@'+str(k):>9}" for k in KS))
    print("-" * (12 + 9 * len(KS)))
    for fb in FACET_BOOSTS:
        m = results[fb]["hit"]
        star = "  *(현행)" if fb == 0.03 else ("  (무개입)" if fb == 0.0 else "")
        print(f"{fb:>12.3f}" + "".join(f"{m[k]:>9.3f}" for k in KS) + star)

    best = max(FACET_BOOSTS, key=lambda fb: (results[fb]["hit"][3], results[fb]["hit"][1]))
    print(f"\n[hit@3 기준 최적] FACET_BOOST={best} (현행 0.03 대비 "
          f"{results[best]['hit'][3] - results[0.03]['hit'][3]:+.3f}pp)")

    print("\n=== 형제그룹 크기별 hit@3 (최적 boost 적용) — 구조적 한계 확인용 ===")
    print(f"{'그룹크기':>10}{'문항수':>8}{'hit@3':>9}")
    for bucket in ("1(유일)", "2-3", "4-7", "8+"):
        b = results[best]["by_bucket"].get(bucket, {"n": 0, "hit3": 0})
        rate = b["hit3"] / b["n"] if b["n"] else 0.0
        print(f"{bucket:>10}{b['n']:>8}{rate:>9.3f}")

    print("\n=== 업무별 hit@3 (현행 0.03 vs 최적) ===")
    print(f"{'업무':<16}{'문항수':>7}{'현행(0.03)':>12}{'최적':>9}{'변화':>9}")
    for domain in sorted(results[0.03]["by_domain"], key=lambda d: -results[0.03]["by_domain"][d]["n"]):
        n = results[0.03]["by_domain"][domain]["n"]
        cur = results[0.03]["by_domain"][domain][3] / n
        opt = results[best]["by_domain"][domain][3] / n
        print(f"{domain:<16}{n:>7}{cur:>12.3f}{opt:>9.3f}{opt-cur:>+9.3f}")


if __name__ == "__main__":
    main()
