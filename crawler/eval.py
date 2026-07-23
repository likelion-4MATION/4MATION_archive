"""검색 평가 — hit@1 · hit@3 · MRR, dense-only vs hybrid(RRF) 비교, MD 리포트.

정답 판정: top-k 청크의 parent_doc_id가 gt_docs에 포함되면 적중(문서 단위).
D1 통과 판정은 대표 6문항 top-3 적중 5+ (representative=True).
오염체크: 국내 보호한도 질문 top-3에 해외 한도 수치 혼입 0건.

지표 집계 방식:
- micro: 문항 단순 평균(기존). 문항 수가 많은 업무·문서에 지표가 쏠린다.
- macro: 그룹(업무/출처)별 평균을 다시 평균. 특정 그룹의 문항 쏠림 영향을 제거한다.
  정답 쏠림(문서 1개가 정답의 25%)·업무 편차(착오송금 44 vs 채무조정 10) 때문에
  micro만 보면 소수 그룹 성능이 종합 지표를 왜곡한다 → macro 병기로 편향 진단.

사용: python eval.py   → 콘솔 요약 + data/eval_report.md
"""

from __future__ import annotations

import collections
import json

import rag

TESTSET = "data/testset_natural_400.jsonl"
REPORT = "data/eval_report.md"
MODES = ["dense", "hybrid", "hybrid_bf"]
KMAX = 10

CONTAM_MARKERS = ["FDIC", "해외 예금", "해외예금", "미국 예금보험", "달러", "US$", "엔화", "위안화"]


def load_testset() -> list[dict]:
    return [json.loads(l) for l in open(TESTSET, encoding="utf-8")]


def first_hit_rank(hits: list[dict], gt: set[str]) -> int:
    """gt_docs에 속한 첫 청크의 1-based 랭크. 없으면 0."""
    for r, c in enumerate(hits, 1):
        if c["parent_doc_id"] in gt:
            return r
    return 0


def eval_mode(searcher: rag.Searcher, testset: list[dict], mode: str) -> dict:
    h1 = h3 = 0
    mrr = 0.0
    per_q = []
    for it in testset:
        gt = set(it["gt_docs"])
        hits = searcher.search(it["question"], k=KMAX, mode=mode)
        rank = first_hit_rank(hits, gt)
        hit1 = rank == 1
        hit3 = 1 <= rank <= 3
        h1 += hit1
        h3 += hit3
        mrr += (1.0 / rank) if rank else 0.0
        per_q.append({"q": it["question"], "rank": rank, "hit3": hit3,
                      "representative": it["representative"],
                      "bf": it["business_function"],
                      "source": it.get("source", "?"),
                      "gt0": it["gt_docs"][0] if it["gt_docs"] else "",
                      "top": hits[:3]})
    n = len(testset)
    return {"mode": mode, "n": n, "hit@1": h1 / n, "hit@3": h3 / n,
            "mrr": mrr / n, "per_q": per_q}


def _row(items: list[dict]) -> dict:
    """문항 리스트 → hit@1·hit@3·MRR (해당 그룹의 micro 지표)."""
    n = len(items)
    return {
        "n": n,
        "hit@1": sum(p["rank"] == 1 for p in items) / n,
        "hit@3": sum(1 <= p["rank"] <= 3 for p in items) / n,
        "mrr": sum((1.0 / p["rank"] if p["rank"] else 0.0) for p in items) / n,
    }


def group_metrics(per_q: list[dict], key: str) -> tuple[dict, dict]:
    """key별 지표 표 + 그룹 단순평균(macro). 반환: (그룹별 rows, macro dict)."""
    groups: dict[str, list] = collections.defaultdict(list)
    for p in per_q:
        groups[p[key]].append(p)
    rows = {g: _row(items) for g, items in groups.items()}
    g = len(rows)
    macro = {m: sum(r[m] for r in rows.values()) / g for m in ("hit@1", "hit@3", "mrr")}
    macro["groups"] = g
    return rows, macro


def contamination_check(searcher: rag.Searcher) -> dict:
    q = "예금자 보호 한도는 얼마인가요?"
    hits = searcher.search(q, k=3, mode="hybrid")
    flagged = []
    for c in hits:
        found = [m for m in CONTAM_MARKERS if m in c["text"]]
        if found:
            flagged.append({"chunk_id": c["chunk_id"], "markers": found})
    return {"query": q, "flagged": flagged,
            "top3": [f"{c['business_function']}/{c['page_title']}" for c in hits]}


def write_report(results: dict[str, dict], rep6: dict, contam: dict) -> None:
    L = ["# 검색 평가 리포트 (D1)", "",
         f"- 평가셋: {results['dense']['n']}건 · 임베딩: `{rag.MODEL_NAME}` · 융합: RRF(k={rag.RRF_K})",
         "", "## 전체 지표 (dense vs hybrid) — micro(문항 평균)", "",
         "| mode | hit@1 | hit@3 | MRR |", "|---|---|---|---|"]
    for m in MODES:
        r = results[m]
        L.append(f"| {m} | {r['hit@1']:.3f} | {r['hit@3']:.3f} | {r['mrr']:.3f} |")

    # macro(업무별 평균) — 정답/업무 쏠림 보정 지표
    L += ["", "## 종합 지표 — micro vs macro(업무별 평균)", "",
          "> macro는 6개 업무의 지표를 각각 구해 단순평균. 문항 쏠림(착오송금 29%)을 제거한 값.",
          "", "| mode | hit@3 micro | hit@3 macro | MRR micro | MRR macro |",
          "|---|---|---|---|---|"]
    macro_bf = {}
    for m in MODES:
        _, mac = group_metrics(results[m]["per_q"], "bf")
        macro_bf[m] = mac
        r = results[m]
        L.append(f"| {m} | {r['hit@3']:.3f} | {mac['hit@3']:.3f} | "
                 f"{r['mrr']:.3f} | {mac['mrr']:.3f} |")

    # 업무별 세분 (hybrid)
    L += ["", "## 업무별 세분 지표 (hybrid)", "",
          "| 업무 | 문항수 | hit@1 | hit@3 | MRR |", "|---|---|---|---|---|"]
    rows_bf, _ = group_metrics(results["hybrid"]["per_q"], "bf")
    for bf, r in sorted(rows_bf.items(), key=lambda x: -x[1]["n"]):
        L.append(f"| {bf} | {r['n']} | {r['hit@1']:.3f} | {r['hit@3']:.3f} | {r['mrr']:.3f} |")

    # 출처별 세분 (hybrid) — 질의 유형(키워드형 vs 자연어) 성능차 진단
    L += ["", "## 출처별 세분 지표 (hybrid)", "",
          "| source | 문항수 | hit@1 | hit@3 | MRR |", "|---|---|---|---|---|"]
    rows_src, macro_src = group_metrics(results["hybrid"]["per_q"], "source")
    for s, r in sorted(rows_src.items(), key=lambda x: -x[1]["n"]):
        L.append(f"| {s} | {r['n']} | {r['hit@1']:.3f} | {r['hit@3']:.3f} | {r['mrr']:.3f} |")

    L += ["", "## 대표 6문항 top-3 적중 (D1 통과 판정: 5+ / hybrid)", "",
          "| 업무 | 질문 | dense rank | hybrid rank |", "|---|---|---|---|"]
    dmap = {p["q"]: p["rank"] for p in results["dense"]["per_q"]}
    for p in results["hybrid"]["per_q"]:
        if not p["representative"]:
            continue
        L.append(f"| {p['bf']} | {p['q']} | {dmap.get(p['q'],0) or '미적중'} | "
                 f"{p['rank'] or '미적중'} |")
    L += ["", f"- **hybrid 대표 top-3 적중: {rep6['hybrid']}/6** · dense: {rep6['dense']}/6",
          "", "## 오염체크 — 국내 보호한도 질문 top-3", "",
          f"- 질의: {contam['query']}", f"- top-3: {contam['top3']}",
          f"- 해외 수치 혼입: **{len(contam['flagged'])}건** "
          f"{contam['flagged'] if contam['flagged'] else '(없음)'}"]
    import pathlib
    pathlib.Path(REPORT).write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    testset = load_testset()
    searcher = rag.Searcher()

    results = {m: eval_mode(searcher, testset, m) for m in MODES}
    rep6 = {m: sum(1 for p in results[m]["per_q"] if p["representative"] and p["hit3"])
            for m in MODES}
    contam = contamination_check(searcher)
    write_report(results, rep6, contam)

    print(f"평가셋 {len(testset)}건 · 임베딩 {rag.MODEL_NAME} · RRF(k={rag.RRF_K})\n")
    print(f"{'mode':8} {'hit@1':>7} {'hit@3':>7} {'MRR':>7}")
    for m in MODES:
        r = results[m]
        print(f"{m:8} {r['hit@1']:>7.3f} {r['hit@3']:>7.3f} {r['mrr']:>7.3f}")

    # micro vs macro (업무별 평균) — 쏠림 보정
    print(f"\n[micro vs macro(업무별 평균)]")
    print(f"{'mode':8} {'h3_micro':>9} {'h3_macro':>9} {'mrr_micro':>10} {'mrr_macro':>10}")
    for m in MODES:
        _, mac = group_metrics(results[m]["per_q"], "bf")
        r = results[m]
        print(f"{m:8} {r['hit@3']:>9.3f} {mac['hit@3']:>9.3f} "
              f"{r['mrr']:>10.3f} {mac['mrr']:>10.3f}")

    # 업무별 세분 (hybrid)
    print(f"\n[업무별 hit@3 (hybrid)]")
    rows_bf, _ = group_metrics(results["hybrid"]["per_q"], "bf")
    for bf, r in sorted(rows_bf.items(), key=lambda x: -x[1]["n"]):
        print(f"  {bf:16} n={r['n']:3d}  hit@3={r['hit@3']:.3f}  MRR={r['mrr']:.3f}")

    # 출처별 세분 (hybrid)
    print(f"\n[출처별 hit@3 (hybrid)]")
    rows_src, _ = group_metrics(results["hybrid"]["per_q"], "source")
    for s, r in sorted(rows_src.items(), key=lambda x: -x[1]["n"]):
        print(f"  {s:14} n={r['n']:3d}  hit@3={r['hit@3']:.3f}  MRR={r['mrr']:.3f}")

    # 하드필터 효과 — 업무별 hit@3: hybrid → hybrid_bf
    if "hybrid_bf" in results:
        print(f"\n[하드필터 효과 — 업무별 hit@3: hybrid → hybrid_bf]")
        rb, _ = group_metrics(results["hybrid"]["per_q"], "bf")
        rf, _ = group_metrics(results["hybrid_bf"]["per_q"], "bf")
        for bf in sorted(rb, key=lambda x: -rb[x]["n"]):
            h, fv = rb[bf]["hit@3"], rf[bf]["hit@3"]
            print(f"  {bf:16} {h:.3f} -> {fv:.3f}  ({fv-h:+.3f})")
        oh, of = results["hybrid"]["hit@3"], results["hybrid_bf"]["hit@3"]
        print(f"  {'전체':16} {oh:.3f} -> {of:.3f}  ({of-oh:+.3f})")

    print(f"\n대표 6문항 top-3 적중  hybrid={rep6['hybrid']}/6  dense={rep6['dense']}/6"
          f"  → D1 판정 {'통과' if rep6['hybrid']>=5 else '미통과'}")
    print(f"오염체크(국내 보호한도 top-3 해외수치): {len(contam['flagged'])}건 "
          f"→ {'통과' if not contam['flagged'] else '실패'}")
    # 대표문항 미적중 상세
    miss = [p for p in results["hybrid"]["per_q"] if p["representative"] and not p["hit3"]]
    for p in miss:
        print(f"  [미적중] {p['q']} → top3: "
              + " | ".join(f"{c['business_function']}/{c['page_title']}" for c in p["top"]))
    print(f"\n리포트 → {REPORT}")


if __name__ == "__main__":
    main()
