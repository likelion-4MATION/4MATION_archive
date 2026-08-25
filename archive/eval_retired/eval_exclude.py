# -*- coding: utf-8 -*-
"""문서 제외 ablation 평가 — 특정 doc을 검색에서 빼고 재측정.

목적: selectFaqNramtAply(38청크 블랙홀)가 없었다면 검색이 얼마나 나아지는지의 '상한선'.
- 인덱스 재구축 없이 검색 결과에서 제외 doc의 청크를 걸러내고 pool을 넓혀 backfill.
- 공정성: 제외 doc은 gt_docs에서도 빼고 채점(그 doc으로 맞혔다고 인정하지 않음).
  단독 gt였던 문항은 채점 제외(현재 테스트셋엔 0건).

주의: 이것은 진단용 ablation이지 배포용 수정이 아니다. 이 문서는 32개 문항의
정답이기도 하므로 실제 해법은 '삭제'가 아니라 'Q&A 단위 재청킹'이다.

사용:
  python eval_exclude.py                                  # 기본 제외 doc
  python eval_exclude.py kdic-fins-cm-bbs-selectFaqNramtAply   # 제외 doc 지정
"""
from __future__ import annotations
import collections
import json
import sys

import numpy as np
import rag

TESTSET = "data/testset_natural_300_v2.jsonl"   # 라벨 교정본
DEFAULT_EXCLUDE = ["kdic-fins-cm-bbs-selectFaqNramtAply"]
MODES = ["dense", "hybrid"]
KMAX = 10


class ExcludingSearcher(rag.Searcher):
    """지정한 parent_doc_id의 청크를 검색 결과에서 제외(인덱스엔 그대로, 결과에서 skip)."""

    def __init__(self, exclude: set[str], index_dir: str = rag.INDEX_DIR):
        super().__init__(index_dir)
        self.exclude_idx = {i for i, c in enumerate(self.chunks)
                            if c["parent_doc_id"] in exclude}
        self._pad = len(self.exclude_idx) + 5   # backfill 여유

    def dense(self, query, k: int = 10):
        q = rag.embed_texts([query])
        D, I = self.index.search(q, min(k + self._pad, len(self.chunks)))
        out = [(int(i), float(d)) for i, d in zip(I[0], D[0])
               if i >= 0 and int(i) not in self.exclude_idx]
        return out[:k]

    def sparse(self, query, k: int = 10):
        if self.bm25 is None:
            return []
        scores = self.bm25.get_scores(rag.tokenize(query))
        order = np.argsort(scores)[::-1]
        out = [(int(i), float(scores[i])) for i in order
               if int(i) not in self.exclude_idx]
        return out[:k]


def first_hit_rank(hits, gt):
    for r, c in enumerate(hits, 1):
        if c["parent_doc_id"] in gt:
            return r
    return 0


def run(searcher, testset, mode, exclude):
    h1 = h3 = 0
    mrr = 0.0
    per_bf = collections.defaultdict(lambda: [0, 0, 0.0, 0])  # h1,h3,mrr,n
    scored = 0
    for it in testset:
        gt = set(it["gt_docs"]) - exclude   # 제외 doc은 정답에서도 제거
        if not gt:                          # 단독 gt였던 문항은 채점 제외
            continue
        scored += 1
        hits = searcher.search(it["question"], k=KMAX, mode=mode)
        r = first_hit_rank(hits, gt)
        hit1, hit3 = (r == 1), (1 <= r <= 3)
        h1 += hit1; h3 += hit3; mrr += (1.0 / r if r else 0.0)
        b = per_bf[it["business_function"]]
        b[0] += hit1; b[1] += hit3; b[2] += (1.0 / r if r else 0.0); b[3] += 1
    return {"n": scored, "hit@1": h1 / scored, "hit@3": h3 / scored,
            "mrr": mrr / scored, "per_bf": per_bf}


def main():
    exclude = set(sys.argv[1:]) or set(DEFAULT_EXCLUDE)
    testset = [json.loads(l) for l in open(TESTSET, encoding="utf-8")]
    searcher = ExcludingSearcher(exclude)

    print(f"제외 문서: {sorted(exclude)}")
    print(f"제외 청크 수: {len(searcher.exclude_idx)} / 전체 {len(searcher.chunks)}")
    print(f"평가셋: {TESTSET} ({len(testset)}건)\n")

    print(f"{'mode':8} {'n':>4} {'hit@1':>7} {'hit@3':>7} {'MRR':>7}")
    results = {}
    for m in MODES:
        r = run(searcher, testset, m, exclude)
        results[m] = r
        print(f"{m:8} {r['n']:>4} {r['hit@1']:>7.3f} {r['hit@3']:>7.3f} {r['mrr']:>7.3f}")

    print(f"\n[업무별 hit@3 (hybrid, 제외 후)]")
    for bf, b in sorted(results["hybrid"]["per_bf"].items(), key=lambda x: -x[1][3]):
        h1, h3, mr, n = b
        print(f"  {bf:16} n={n:3d}  hit@3={h3/n:.3f}  MRR={mr/n:.3f}")

    miss = results["hybrid"]["n"] - round(results["hybrid"]["hit@3"] * results["hybrid"]["n"])
    print(f"\nhybrid 미적중: {miss}건 / {results['hybrid']['n']}  "
          f"(참고: 제외 전 v2 기준 77/300)")
    print("주의: 진단용 ablation. 실제 해법은 삭제가 아니라 selectFaqNramtAply의 Q&A 단위 재청킹.")


if __name__ == "__main__":
    main()
