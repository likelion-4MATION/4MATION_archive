"""앵커(청크) 단위 검색 eval — gold 업무 주입 + 배포 soft 경로 그대로.

전제(대화 합의):
  - 라우터는 별도 테스트셋에서 평가 중 → 여기선 순수 검색기만 본다.
  - 따라서 질의 업무를 classify_query_bf로 뽑지 않고 **gold(trainset business_function)를 주입**.
  - 검색기는 배포 모드 그대로: hybrid_bf = BF_MODE"soft"(+BF_BOOST) + facet + doc-cap.
    (rag.search()가 내부에서 classify_query_bf를 부르므로, gold 주입 위해 soft 경로를 직접 복제.)
  - GT는 judge_label.py 산출 gt_chunk_id(청크 단위). answerable=false는 검색 eval에서 제외.

북극성 = recall@10.
  이유: 파이프라인이 2단(임베딩 top10 → LLM 큐폼 셀렉터). 검색기의 임무는 gold를 1등에
  올리는 게 아니라 top-10 안에 넣는 것. hit@1/@3/MRR은 셀렉터 여유분 참고용 보조지표.

산출: data/eval_anchor_report.md + 콘솔 요약.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib

import rag

KS = (1, 3, 5, 10)
KMAX = max(KS)


def gold_injected_search(searcher: "rag.Searcher", query: str, gold_bf: str, k: int):
    """rag.search(mode='hybrid_bf') under BF_MODE='soft' 의 정확한 복제 — 단 bf=gold.

    배포 경로: pool = hybrid_soft(q, 전체, bf, boost=BF_BOOST) → _cap_by_doc(·, BF_DOC_CAP) → [:k]
    """
    pool = searcher.hybrid_soft(
        query, len(searcher.chunks), bf=gold_bf,
        boost=rag.BF_BOOST, alpha=rag.RRF_ALPHA,
    )
    capped = searcher._cap_by_doc(pool, rag.BF_DOC_CAP)[:k]
    return [searcher.chunks[idx] for idx, _ in capped]


def rank_of(hits: list[dict], key: str, gt_vals) -> int:
    gt = gt_vals if isinstance(gt_vals, (set, list, tuple)) else {gt_vals}
    gt = set(gt)
    for r, c in enumerate(hits, 1):
        if c.get(key) in gt:
            return r
    return 0


def summarize(ranks: list[int]) -> dict:
    n = len(ranks)
    out = {f"recall@{k}": sum(1 for r in ranks if 1 <= r <= k) / n for k in KS}
    out["hit@1"] = out["recall@1"]
    out["mrr@10"] = sum((1.0 / r if 1 <= r <= KMAX else 0.0) for r in ranks) / n
    out["n"] = n
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="gt_labeled.jsonl")
    ap.add_argument("--report", default="eval_anchor_report.md")
    ap.add_argument("--min-conf", type=float, default=0.0,
                    help="confidence 컷(HCX-003은 1.0/0.0 이분값이라 0 권장). 더 나은 모델이면 상향")
    ap.add_argument("--allow-cross", action="store_true",
                    help="cross_domain=true 라벨도 eval에 포함(기본: 검수대기로 제외)")
    args = ap.parse_args()

    labels = [json.loads(l) for l in open(args.labels, encoding="utf-8")]
    answerable = [x for x in labels if x.get("answerable") and x.get("gt_chunk_id")]
    rejects = [x for x in labels if not x.get("answerable")]
    # 검수대기: 스팬 verbatim 실패 or (기본) 크로스도메인 — 죽은 confidence 대신 이 플래그로 게이팅
    def _needs_review(x):
        if not x.get("span_verbatim_ok"):
            return True
        if x.get("cross_domain") and not args.allow_cross:
            return True
        return x.get("confidence", 1.0) < args.min_conf
    review = [x for x in answerable if _needs_review(x)]
    usable = [x for x in answerable if not _needs_review(x)]
    lowconf = review        # 리포트 호환용 별칭

    searcher = rag.Searcher()

    chunk_ranks, doc_ranks = [], []
    per_bf = collections.defaultdict(list)
    cross_ranks, incorp_ranks = [], []      # 크로스도메인 vs 동일도메인 분리
    gt_doc_of = {}
    for c in searcher.chunks:
        gt_doc_of[c["chunk_id"]] = c["parent_doc_id"]

    for x in usable:
        hits = gold_injected_search(searcher, x["question"], x["business_function"], KMAX)
        gold_ids = x.get("gt_chunk_ids") or ([x["gt_chunk_id"]] if x.get("gt_chunk_id") else [])
        cr = rank_of(hits, "chunk_id", gold_ids)
        gt_doc = {gt_doc_of.get(g, "") for g in gold_ids}
        dr = rank_of(hits, "parent_doc_id", gt_doc)      # 옛 doc단위 지표(거품 비교용)
        chunk_ranks.append(cr)
        doc_ranks.append(dr)
        per_bf[x["business_function"]].append(cr)
        (cross_ranks if x.get("cross_domain") else incorp_ranks).append(cr)

    chunk_m = summarize(chunk_ranks)
    doc_m = summarize(doc_ranks)

    L = ["# 앵커(청크) 단위 검색 eval — gold 주입 · hybrid_bf(soft)", "",
         f"- 임베딩 `{rag.MODEL_NAME}` · RRF(k={rag.RRF_K}, α={rag.RRF_ALPHA}) · "
         f"BF_MODE={rag.BF_MODE}(boost={rag.BF_BOOST}) · facet={rag.FACET_BOOST} · cap={rag.BF_DOC_CAP}",
         f"- 라벨 {len(labels)}건 = 답가능 {len(answerable)}(사용 {len(usable)} / "
         f"검수대기 {len(review)}[span실패·크로스]) + 답없음 {len(rejects)}(거절 eval行)",
         "",
         "## 청크 단위 (신규 GT — 정답 청크 자체를 top-k에)", "",
         "| 지표 | 값 |", "|---|---|"]
    for k in KS:
        L.append(f"| recall@{k} | {chunk_m[f'recall@{k}']:.3f} |")
    L.append(f"| MRR@10 | {chunk_m['mrr@10']:.3f} |")

    L += ["", "## 참고: 문서 단위 (옛 hit@k 방식 — 거품 비교)", "",
          "| 지표 | 청크단위 | 문서단위 | 차이(거품) |", "|---|---|---|---|"]
    for k in KS:
        cs, ds = chunk_m[f"recall@{k}"], doc_m[f"recall@{k}"]
        L.append(f"| recall@{k} | {cs:.3f} | {ds:.3f} | {ds-cs:+.3f} |")
    L.append(f"| MRR@10 | {chunk_m['mrr@10']:.3f} | {doc_m['mrr@10']:.3f} | "
             f"{doc_m['mrr@10']-chunk_m['mrr@10']:+.3f} |")

    L += ["", "## 업무별 recall@10 (청크 단위)", "", "| 업무 | n | recall@10 | MRR@10 |", "|---|---|---|---|"]
    for bf, rs in sorted(per_bf.items(), key=lambda x: -len(x[1])):
        m = summarize(rs)
        L.append(f"| {bf} | {m['n']} | {m['recall@10']:.3f} | {m['mrr@10']:.3f} |")

    if cross_ranks:
        cm, im = summarize(cross_ranks), summarize(incorp_ranks)
        L += ["", "## 크로스도메인 분리 (정답 청크가 gold 업무와 다른 태그)", "",
              "| 구분 | n | recall@10 |", "|---|---|---|",
              f"| 동일도메인 | {im['n']} | {im['recall@10']:.3f} |",
              f"| 크로스도메인 | {cm['n']} | {cm['recall@10']:.3f} |",
              "",
              "> soft 모드라 크로스도메인도 후보에 남음. 이 값이 낮으면 dense가 타업무 정답을 "
              "못 끌어오는 것 → 리랭커/부스트 조정 신호(태그 문제 아님)."]

    pathlib.Path(args.report).write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"[앵커 eval · gold주입 · {rag.BF_MODE}] 사용 {chunk_m['n']}건")
    for k in KS:
        print(f"  recall@{k:<2} = {chunk_m[f'recall@{k}']:.3f}")
    print(f"  MRR@10   = {chunk_m['mrr@10']:.3f}")
    print(f"  (참고 문서단위 recall@10 = {doc_m['recall@10']:.3f} · "
          f"거품 {doc_m['recall@10']-chunk_m['recall@10']:+.3f})")
    print(f"  답없음 {len(rejects)}건 거절 eval行 · 검수대기 {len(review)}건(span실패·크로스)")
    print(f"리포트 → {args.report}")


if __name__ == "__main__":
    main()
