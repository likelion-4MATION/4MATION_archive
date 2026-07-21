# -*- coding: utf-8 -*-
"""doc-count cap A/B 실험 — hybrid_bf 위에 문서당 top-k 청크 수 제한을 얹어 비교.

배경: 미적중 정분류 38건의 top-3가 100% 동일업무오답(몬스터 문서가 슬롯 독점).
      hit@k는 문서 단위 판정이라 같은 문서 청크로 top-3를 채우면 슬롯 낭비 →
      parent_doc_id당 청크 수를 cap개로 제한하면 서로 다른 문서가 더 들어와 gt 진입 확률↑.

방식: 인덱스/필터 불변. searcher.search(mode=hybrid_bf)로 깊은 풀(POOL_K)을 받아
      parent_doc_id별 cap개까지만 남기고 재순위 → hit@1/hit@3/MRR·대표6·업무별 비교.
      결정론적·저비용(후처리 한 겹). cap=None(현행) 대비 cap 1/2/3.

사용: cd crawler && python eval_cap.py
"""
from __future__ import annotations
import collections
import json

import rag

TESTSET = "data/testset_natural_300_v2.jsonl"
MODE = "hybrid_bf"
CAPS = [None, 1, 2, 3]
POOL_K = 50   # cap 적용 전 확보할 후보 깊이
KMAX = 10     # 순위 계산 상한(hit@3는 이 안에서)


def first_hit_rank(hits, gt):
    for r, c in enumerate(hits, 1):
        if c["parent_doc_id"] in gt:
            return r
    return 0


def cap_hits(hits, cap):
    """parent_doc_id당 cap개까지만 순서 유지하며 남김."""
    if cap is None:
        return hits
    seen = collections.Counter()
    out = []
    for c in hits:
        d = c["parent_doc_id"]
        if seen[d] < cap:
            out.append(c)
            seen[d] += 1
    return out


def evaluate(searcher, testset, cap):
    h1 = h3 = 0
    mrr = 0.0
    per_bf = collections.defaultdict(lambda: [0, 0])   # [h3, n]
    rep_hit = rep_n = 0
    for it in testset:
        gt = set(it["gt_docs"])
        raw = searcher.search(it["question"], k=POOL_K, mode=MODE)
        hits = cap_hits(raw, cap)[:KMAX]
        r = first_hit_rank(hits, gt)
        hit1, hit3 = (r == 1), (1 <= r <= 3)
        h1 += hit1; h3 += hit3; mrr += (1.0 / r if r else 0.0)
        b = per_bf[it["business_function"]]
        b[0] += hit3; b[1] += 1
        if it["representative"]:
            rep_n += 1; rep_hit += hit3
    n = len(testset)
    return {"cap": cap, "hit@1": h1 / n, "hit@3": h3 / n, "mrr": mrr / n,
            "rep": f"{rep_hit}/{rep_n}", "per_bf": per_bf}


def main():
    testset = [json.loads(l) for l in open(TESTSET, encoding="utf-8")]
    searcher = rag.Searcher()
    res = [evaluate(searcher, testset, c) for c in CAPS]

    print(f"평가셋 {len(testset)}건 · mode={MODE} · pool={POOL_K}\n")
    print(f"{'cap':>5} {'hit@1':>7} {'hit@3':>7} {'MRR':>7} {'대표6':>6}")
    for r in res:
        cap = "none" if r["cap"] is None else str(r["cap"])
        print(f"{cap:>5} {r['hit@1']:>7.3f} {r['hit@3']:>7.3f} {r['mrr']:>7.3f} {r['rep']:>6}")

    # 업무별 hit@3: cap별 나란히
    bfs = sorted(res[0]["per_bf"], key=lambda b: -res[0]["per_bf"][b][1])
    print(f"\n[업무별 hit@3 — cap none → 1/2/3]")
    header = "  " + f"{'업무':16}" + "".join(f"{('none' if c is None else c):>8}" for c in CAPS)
    print(header)
    for bf in bfs:
        cells = ""
        for r in res:
            h3, nn = r["per_bf"][bf]
            cells += f"{h3/nn:>8.3f}"
        print(f"  {bf:16}{cells}")

    base = res[0]
    print("\n[요약] no-cap 대비 Δhit@3")
    for r in res[1:]:
        print(f"  cap={r['cap']}: {base['hit@3']:.3f} → {r['hit@3']:.3f} "
              f"({r['hit@3']-base['hit@3']:+.3f}) · hit@1 {r['hit@1']-base['hit@1']:+.3f} "
              f"· 대표6 {r['rep']}")


if __name__ == "__main__":
    main()
