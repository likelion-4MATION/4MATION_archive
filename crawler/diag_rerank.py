# -*- coding: utf-8 -*-
"""리랭킹 퇴행 12문항 진단 — 왜 gt가 top-3 밖으로 밀렸는지.

hybrid_bf에선 맞혔는데 hybrid_bf_rr에서 깨진 12건만 리랭크하여
  · gt_docs / 질의 업무 분류
  · hybrid_bf(리랭크 전) gt 순위
  · 리랭크 top-6 (점수·태그·문서) + gt 문서가 몇 위로 밀렸는지
를 출력. 12 x 30 = 360회 추론이라 빠름.

사용: cd crawler && python diag_rerank.py   (eval_rerank.py와 같은 폴더/환경)
"""
from __future__ import annotations
import json
import rag

RERANK_MODEL = "Dongjin-kr/ko-reranker"   # eval_rerank.py와 동일
TESTSET = "data/testset_natural_300_v3.jsonl"
POOL_N = 30
CAP = 1
KMAX = 10

QUESTIONS = [
    "제가 든 보험도 보험사가 망하면 보상받을 수 있는 건가요?",
    "돈 잘못 보낸 지 꽤 됐는데 지금 접수해도 되나?",
    "예보에 잘못 보낸 돈 신청을 넣기 전에 먼저 거쳐야 하는 절차가 있나요?",
    "그 재산 정보를 어떻게 알았는지까지 밝혀야 신고가 되나요?",
    "잘못 들어온 돈을 돌려달라는데 억울한 사정이 있으면 어디에 이의를 낼 수 있어요?",
    "군대에 있는 아들 대신 안 찾아간 돈을 받으려면 뭘 준비해야 하나요?",
    "본인이 못 가고 다른 사람이 대신 못 찾은 돈을 받으러 가면 뭘 들고 가야 하나요?",
    "증권사에 넣어둔 돈도 보호가 되나요? 어떤 경우에요?",
    "본인이 미수령금 신청할 때 준비물은요?",
    "이의제기 서류 뭐 필요해요?",
    "수수료 환급 온라인으로 돼요?",
    "신고 접수되면 어떻게 처리돼요?",
]

_ce = None


def get_ce():
    global _ce
    if _ce is None:
        from sentence_transformers import CrossEncoder
        _ce = CrossEncoder(RERANK_MODEL, max_length=512)
    return _ce


def first_doc_rank(items, gt):
    """items=[(chunk, score) or chunk]; gt 문서의 1-based 순위(문서단위). 없으면 0."""
    for r, x in enumerate(items, 1):
        c = x[0] if isinstance(x, tuple) else x
        if c["parent_doc_id"] in gt:
            return r
    return 0


def cap_by_doc(pairs, cap):
    """[(chunk, score)] 에서 parent_doc_id당 cap개까지."""
    if not cap or cap <= 0:
        return pairs
    seen = {}
    out = []
    for c, s in pairs:
        d = c["parent_doc_id"]
        if seen.get(d, 0) < cap:
            out.append((c, s)); seen[d] = seen.get(d, 0) + 1
    return out


def tag(c, gt):
    return "✅gt" if c["parent_doc_id"] in gt else "  ·"


def main():
    ts = {json.loads(l)["question"]: json.loads(l)
          for l in open(TESTSET, encoding="utf-8")}
    searcher = rag.Searcher()
    ce = get_ce()

    for q in QUESTIONS:
        it = ts.get(q)
        if it is None:
            print(f"\n[질문 미발견] {q}")
            continue
        gt = set(it["gt_docs"])
        bf = rag.classify_query_bf(q)

        # hybrid_bf (리랭크 전) — gt 순위
        base = searcher.search(q, KMAX, mode="hybrid_bf")
        base_rank = first_doc_rank(base, gt)

        # 리랭크 (uncapped pool → rerank → post-cap)
        pool = searcher.hybrid(q, POOL_N, bf=bf)
        chunks = [dict(searcher.chunks[i]) for i, _ in pool]
        scores = ce.predict([[q, rag.chunk_embed_text(c)] for c in chunks])
        order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
        ranked = [(chunks[i], float(scores[i])) for i in order]
        capped = cap_by_doc(ranked, CAP)
        rr_rank = first_doc_rank(capped[:KMAX], gt)

        # gt 문서의 리랭크 최고점(있으면)
        gt_best = max((s for c, s in ranked if c["parent_doc_id"] in gt), default=None)

        print("\n" + "=" * 78)
        print(f"Q: {q}")
        print(f"   업무={it['business_function']} · 질의분류={bf} · gt={it['gt_docs']}")
        print(f"   hybrid_bf gt순위={base_rank or '미적중'}  →  rerank gt순위={rr_rank or '미적중(3위밖)'}"
              f"   (gt 리랭크최고점={gt_best if gt_best is None else round(gt_best,2)})")
        print(f"   리랭크 top-6 (post-cap):")
        for i, (c, s) in enumerate(capped[:6], 1):
            print(f"     {i}. [{tag(c,gt)}] {s:6.2f}  {c['business_function']}/{c['page_title']}"
                  f"  `{c['parent_doc_id']}`")


if __name__ == "__main__":
    main()
