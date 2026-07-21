"""검색 평가 — hit@1 · hit@3 · MRR, dense-only vs hybrid(RRF) 비교, MD 리포트.

정답 판정: top-k 청크의 parent_doc_id가 gt_docs에 포함되면 적중(문서 단위).
D1 통과 판정은 대표 6문항 top-3 적중 5+ (representative=True).
오염체크: 국내 보호한도 질문 top-3에 해외 한도 수치 혼입 0건.

지표 집계 방식:
- micro: 문항 단순 평균(기존). 문항 수가 많은 업무·문서에 지표가 쏠린다.
- macro: 그룹(업무/출처)별 평균을 다시 평균. 특정 그룹의 문항 쏠림 영향을 제거한다.
  정답 쏠림(문서 1개가 정답의 25%)·업무 편차(착오송금 44 vs 채무조정 10) 때문에
  micro만 보면 소수 그룹 성능이 종합 지표를 왜곡한다 → macro 병기로 편향 진단.

산출물:
- data/eval_report.md    : 종합 지표 리포트(기존)
- data/error_analysis.md : 미적중(top-3 밖) 문항의 top-3 혼입 원인 분석(신규)

사용: python eval.py   → 콘솔 요약 + 위 두 리포트
"""

from __future__ import annotations

import collections
import json
import pathlib

import rag

TESTSET = "data/testset_natural_300_v2.jsonl"
REPORT = "data/eval_report.md"
ERR_REPORT = "data/error_analysis.md"
MODES = ["dense", "hybrid"]
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
                      "gt": it["gt_docs"],
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
         f"- 평가셋: {results['dense']['n']}건 · 임베딩: `{rag.MODEL_NAME}` · 융합: RRF(k=60)",
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
    for m in MODES:
        _, mac = group_metrics(results[m]["per_q"], "bf")
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
    pathlib.Path(REPORT).write_text("\n".join(L) + "\n", encoding="utf-8")


def _tag(chunk: dict, gt: set[str], q_bf: str) -> str:
    """top-k 청크가 정답인지, 타업무 혼입인지, 동일업무 오답인지 라벨."""
    if chunk["parent_doc_id"] in gt:
        return "✅정답"
    if chunk["business_function"] != q_bf:
        return "⚠️타업무혼입"
    return "❌동일업무오답"


def write_error_analysis(results: dict[str, dict]) -> dict:
    """미적중(top-3 밖) 문항의 top-3 혼입 원인 분석 → data/error_analysis.md.

    반환: 콘솔 요약용 통계 dict.
    """
    hy = results["hybrid"]["per_q"]
    dmap = {p["q"]: p["rank"] for p in results["dense"]["per_q"]}
    miss = [p for p in hy if not (1 <= p["rank"] <= 3)]  # hit@3 실패
    n, m = len(hy), len(miss)

    L = ["# 오류 분석 리포트 — hybrid 기준", "",
         f"- 대상: 전체 {n}건 중 **미적중 {m}건** · 미적중률 {m / n:.1%}",
         "- 미적중 = gt_docs 문서가 hybrid top-3 밖. `rank=0` 은 top-10 내에도 정답 문서 없음.",
         "- 태그: **✅정답** / **⚠️타업무혼입**(다른 업무 문서가 올라옴) / "
         "**❌동일업무오답**(같은 업무의 다른 문서).",
         ""]

    # 1. 업무별 미적중
    bf_tot = collections.Counter(p["bf"] for p in hy)
    bf_miss = collections.Counter(p["bf"] for p in miss)
    L += ["## 1. 업무별 미적중", "", "| 업무 | 문항 | 미적중 | 미적중률 |", "|---|---|---|---|"]
    for bf in sorted(bf_tot, key=lambda b: -(bf_miss[b] / bf_tot[b])):
        t, ms = bf_tot[bf], bf_miss[bf]
        L.append(f"| {bf} | {t} | {ms} | {ms / t:.1%} |")

    # 2. 혼입 문서 랭킹 (미적중 문항 top-3를 차지한 오답 문서)
    contam = collections.Counter()
    contam_bf: dict[str, str] = {}
    for p in miss:
        gt = set(p["gt"])
        for c in p["top"]:
            if c["parent_doc_id"] not in gt:
                contam[c["parent_doc_id"]] += 1
                contam_bf[c["parent_doc_id"]] = c["business_function"]
    L += ["", "## 2. 혼입 문서 랭킹 (미적중 문항 top-3를 잠식한 오답 문서)", "",
          "| 혼입 문서 | 출현 | 소속 업무 |", "|---|---|---|"]
    for doc, cnt in contam.most_common(15):
        L.append(f"| `{doc}` | {cnt} | {contam_bf[doc]} |")

    # 3. 업무 간 혼입 흐름 (top-1 기준)
    flow = collections.Counter()
    for p in miss:
        if p["top"] and p["top"][0]["business_function"] != p["bf"]:
            flow[(p["bf"], p["top"][0]["business_function"])] += 1
    L += ["", "## 3. 업무 간 혼입 흐름 (미적중 문항의 top-1이 엉뚱한 업무를 가리킨 경우)", "",
          "| 정답 업무 | → top-1 업무 | 건수 |", "|---|---|---|"]
    for (fr, to), cnt in flow.most_common():
        L.append(f"| {fr} | {to} | {cnt} |")

    # 4. 문항별 상세
    L += ["", "## 4. 미적중 문항 상세", ""]
    for p in sorted(miss, key=lambda x: (x["bf"], x["source"], x["q"])):
        gt = set(p["gt"])
        L.append(f"### [{p['bf']} · {p['source']}] {p['q']}")
        L.append(f"- 정답 gt_docs: {p['gt']}")
        L.append(f"- dense rank: {dmap.get(p['q'], 0) or '미적중'} · "
                 f"hybrid rank: {p['rank'] or '미적중(top10밖)'}")
        L.append("- hybrid top-3:")
        for i, c in enumerate(p["top"], 1):
            L.append(f"  {i}. [{_tag(c, gt, p['bf'])}] {c['business_function']} / "
                     f"{c['page_title']}  `{c['parent_doc_id']}`")
        L.append("")

    pathlib.Path(ERR_REPORT).write_text("\n".join(L) + "\n", encoding="utf-8")
    cross = sum(flow.values())
    return {"miss": m, "n": n, "cross": cross,
            "top_contam": contam.most_common(3)}


def main() -> None:
    testset = load_testset()
    searcher = rag.Searcher()

    results = {m: eval_mode(searcher, testset, m) for m in MODES}
    rep6 = {m: sum(1 for p in results[m]["per_q"] if p["representative"] and p["hit3"])
            for m in MODES}
    contam = contamination_check(searcher)
    write_report(results, rep6, contam)
    err = write_error_analysis(results)

    print(f"평가셋 {len(testset)}건 · 임베딩 {rag.MODEL_NAME} · RRF(k=60)\n")
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

    print(f"\n대표 6문항 top-3 적중  hybrid={rep6['hybrid']}/6  dense={rep6['dense']}/6"
          f"  → D1 판정 {'통과' if rep6['hybrid']>=5 else '미통과'}")
    print(f"오염체크(국내 보호한도 top-3 해외수치): {len(contam['flagged'])}건 "
          f"→ {'통과' if not contam['flagged'] else '실패'}")
    # 대표문항 미적중 상세
    miss = [p for p in results["hybrid"]["per_q"] if p["representative"] and not p["hit3"]]
    for p in miss:
        print(f"  [미적중] {p['q']} → top3: "
              + " | ".join(f"{c['business_function']}/{c['page_title']}" for c in p["top"]))

    # 오류분석 요약
    print(f"\n[오류분석] 미적중 {err['miss']}/{err['n']}건 · 업무간 혼입 {err['cross']}건")
    if err["top_contam"]:
        top = " | ".join(f"{d}({c})" for d, c in err["top_contam"])
        print(f"  최다 혼입 문서 top3: {top}")

    print(f"\n리포트 → {REPORT}")
    print(f"오류분석 → {ERR_REPORT}")


if __name__ == "__main__":
    main()
