"""검색 평가(원인분석판) — dense / hybrid / hybrid_bf 비교 + 미적중 원인 분석.

eval.py의 업데이트(hybrid_bf 하드필터 모드 + 하드필터 효과 비교)를 이 파일에도 반영.
※ hybrid_bf = 업무 하드필터 + doc-count cap(rag.BF_DOC_CAP, 문서당 top-k 청크 제한) 결합.
차이점: 원인 분석(error_analysis)·D1 판정·미적중 리포팅을 **ANALYZE_MODE(기본 hybrid_bf)**
기준으로 수행 → 실제 배포 모드(필터 적용)에서 무엇이 왜 틀리는지 진단.

정답 판정: top-k 청크의 parent_doc_id가 gt_docs에 포함되면 적중(문서 단위).
각 미적중 문항에 질의 업무 분류 결과(classify_query_bf)를 병기 →
  · 불명(None): 필터 미적용(전체 검색) → 혼입 잔존 원인
  · 오분류: 엉뚱한 업무로 필터 → 정답 배제 원인
  · 정분류인데 미적중: 업무 내부 랭킹/청킹 문제

산출물:
- data/eval_report.md          : 종합 지표 리포트
- data/error_analysis_TF.md    : ANALYZE_MODE 기준 미적중 원인 분석
"""

from __future__ import annotations

import collections
import json
import pathlib

import rag

TESTSET = "data/testset_natural_400.jsonl"
REPORT = "data/eval_report.md"
ERR_REPORT = "data/error_analysis_TF.md"
MODES = ["dense", "hybrid", "hybrid_bf"]
ANALYZE_MODE = "hybrid_bf"      # 원인분석·D1판정·미적중 리포팅 기준 모드
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
                      "qbf": rag.classify_query_bf(it["question"]),  # 질의 업무 분류
                      "top": hits[:3]})
    n = len(testset)
    return {"mode": mode, "n": n, "hit@1": h1 / n, "hit@3": h3 / n,
            "mrr": mrr / n, "per_q": per_q}


def _row(items: list[dict]) -> dict:
    n = len(items)
    return {
        "n": n,
        "hit@1": sum(p["rank"] == 1 for p in items) / n,
        "hit@3": sum(1 <= p["rank"] <= 3 for p in items) / n,
        "mrr": sum((1.0 / p["rank"] if p["rank"] else 0.0) for p in items) / n,
    }


def group_metrics(per_q: list[dict], key: str) -> tuple[dict, dict]:
    groups: dict[str, list] = collections.defaultdict(list)
    for p in per_q:
        groups[p[key]].append(p)
    rows = {g: _row(items) for g, items in groups.items()}
    g = len(rows)
    macro = {m: sum(r[m] for r in rows.values()) / g for m in ("hit@1", "hit@3", "mrr")}
    macro["groups"] = g
    return rows, macro


def contamination_check(searcher: rag.Searcher, mode: str = ANALYZE_MODE) -> dict:
    q = "예금자 보호 한도는 얼마인가요?"
    hits = searcher.search(q, k=3, mode=mode)
    flagged = []
    for c in hits:
        found = [m for m in CONTAM_MARKERS if m in c["text"]]
        if found:
            flagged.append({"chunk_id": c["chunk_id"], "markers": found})
    return {"query": q, "mode": mode, "flagged": flagged,
            "top3": [f"{c['business_function']}/{c['page_title']}" for c in hits]}


def write_report(results: dict[str, dict], rep6: dict, contam: dict) -> None:
    L = ["# 검색 평가 리포트", "",
         f"- 평가셋: {results['dense']['n']}건 · 임베딩: `{rag.MODEL_NAME}` · 융합: RRF(k=60)",
         "", "## 전체 지표 — micro(문항 평균)", "",
         "| mode | hit@1 | hit@3 | MRR |", "|---|---|---|---|"]
    for m in MODES:
        r = results[m]
        L.append(f"| {m} | {r['hit@1']:.3f} | {r['hit@3']:.3f} | {r['mrr']:.3f} |")

    L += ["", "## 종합 지표 — micro vs macro(업무별 평균)", "",
          "| mode | hit@3 micro | hit@3 macro | MRR micro | MRR macro |",
          "|---|---|---|---|---|"]
    for m in MODES:
        _, mac = group_metrics(results[m]["per_q"], "bf")
        r = results[m]
        L.append(f"| {m} | {r['hit@3']:.3f} | {mac['hit@3']:.3f} | "
                 f"{r['mrr']:.3f} | {mac['mrr']:.3f} |")

    L += ["", f"## 업무별 세분 지표 ({ANALYZE_MODE})", "",
          "| 업무 | 문항수 | hit@1 | hit@3 | MRR |", "|---|---|---|---|---|"]
    rows_bf, _ = group_metrics(results[ANALYZE_MODE]["per_q"], "bf")
    for bf, r in sorted(rows_bf.items(), key=lambda x: -x[1]["n"]):
        L.append(f"| {bf} | {r['n']} | {r['hit@1']:.3f} | {r['hit@3']:.3f} | {r['mrr']:.3f} |")

    L += ["", f"## 출처별 세분 지표 ({ANALYZE_MODE})", "",
          "| source | 문항수 | hit@1 | hit@3 | MRR |", "|---|---|---|---|---|"]
    rows_src, _ = group_metrics(results[ANALYZE_MODE]["per_q"], "source")
    for s, r in sorted(rows_src.items(), key=lambda x: -x[1]["n"]):
        L.append(f"| {s} | {r['n']} | {r['hit@1']:.3f} | {r['hit@3']:.3f} | {r['mrr']:.3f} |")

    L += ["", f"## 대표 6문항 top-3 적중 (D1 판정: 5+ / {ANALYZE_MODE})", "",
          "| 업무 | 질문 | dense | hybrid | hybrid_bf |", "|---|---|---|---|---|"]
    dmap = {p["q"]: p["rank"] for p in results["dense"]["per_q"]}
    hmap = {p["q"]: p["rank"] for p in results["hybrid"]["per_q"]}
    for p in results[ANALYZE_MODE]["per_q"]:
        if not p["representative"]:
            continue
        L.append(f"| {p['bf']} | {p['q']} | {dmap.get(p['q'],0) or '미적중'} | "
                 f"{hmap.get(p['q'],0) or '미적중'} | {p['rank'] or '미적중'} |")
    L += ["", f"- **{ANALYZE_MODE} 대표 top-3 적중: {rep6[ANALYZE_MODE]}/6** · "
          f"hybrid: {rep6['hybrid']}/6 · dense: {rep6['dense']}/6",
          "", f"## 오염체크 — 국내 보호한도 질문 top-3 ({contam['mode']})", "",
          f"- 질의: {contam['query']}", f"- top-3: {contam['top3']}",
          f"- 해외 수치 혼입: **{len(contam['flagged'])}건** "
          f"{contam['flagged'] if contam['flagged'] else '(없음)'}"]
    pathlib.Path(REPORT).write_text("\n".join(L) + "\n", encoding="utf-8")


def _tag(chunk: dict, gt: set[str], q_bf: str) -> str:
    if chunk["parent_doc_id"] in gt:
        return "✅정답"
    if chunk["business_function"] != q_bf:
        return "⚠️타업무혼입"
    return "❌동일업무오답"


def _cause(p: dict) -> str:
    """미적중 원인 태그 — 질의 분류 관점."""
    qbf, bf = p["qbf"], p["bf"]
    if qbf is None:
        return "불명(필터 미적용)"
    if qbf != bf:
        return f"오분류(→{qbf}, 정답배제 위험)"
    return "정분류(업무내 랭킹/청킹)"


def write_error_analysis(results: dict[str, dict], mode: str = ANALYZE_MODE) -> dict:
    """ANALYZE_MODE 기준 미적중 원인 분석 → data/error_analysis_TF.md."""
    hy = results[mode]["per_q"]
    dmap = {p["q"]: p["rank"] for p in results["dense"]["per_q"]}
    miss = [p for p in hy if not (1 <= p["rank"] <= 3)]
    n, m = len(hy), len(miss)

    L = [f"# 오류 분석 리포트 — {mode} 기준", "",
         f"- 대상: 전체 {n}건 중 **미적중 {m}건** · 미적중률 {m / n:.1%}",
         f"- 미적중 = gt_docs 문서가 {mode} top-3 밖. `rank=0` 은 top-10 내에도 정답 문서 없음.",
         "- 태그: **✅정답** / **⚠️타업무혼입** / **❌동일업무오답**.",
         "- 원인(질의 분류): **불명**(필터 미적용) / **오분류**(엉뚱한 업무로 필터) / "
         "**정분류**(업무 내부 랭킹·청킹 문제).",
         ""]

    # 0. 원인 분포 (하드필터 진단의 핵심)
    cause = collections.Counter(_cause(p).split("(")[0] for p in miss)
    L += ["## 0. 미적중 원인 분포", "", "| 원인 | 건수 |", "|---|---|"]
    for c, v in cause.most_common():
        L.append(f"| {c} | {v} |")

    # 1. 업무별 미적중
    bf_tot = collections.Counter(p["bf"] for p in hy)
    bf_miss = collections.Counter(p["bf"] for p in miss)
    L += ["", "## 1. 업무별 미적중", "", "| 업무 | 문항 | 미적중 | 미적중률 |", "|---|---|---|---|"]
    for bf in sorted(bf_tot, key=lambda b: -(bf_miss[b] / bf_tot[b])):
        t, ms = bf_tot[bf], bf_miss[bf]
        L.append(f"| {bf} | {t} | {ms} | {ms / t:.1%} |")

    # 2. 혼입 문서 랭킹
    cont = collections.Counter()
    cont_bf: dict[str, str] = {}
    for p in miss:
        gt = set(p["gt"])
        for c in p["top"]:
            if c["parent_doc_id"] not in gt:
                cont[c["parent_doc_id"]] += 1
                cont_bf[c["parent_doc_id"]] = c["business_function"]
    L += ["", "## 2. 혼입 문서 랭킹 (미적중 top-3를 잠식한 오답 문서)", "",
          "| 혼입 문서 | 출현 | 소속 업무 |", "|---|---|---|"]
    for doc, cnt in cont.most_common(15):
        L.append(f"| `{doc}` | {cnt} | {cont_bf[doc]} |")

    # 3. 업무 간 혼입 흐름
    flow = collections.Counter()
    for p in miss:
        if p["top"] and p["top"][0]["business_function"] != p["bf"]:
            flow[(p["bf"], p["top"][0]["business_function"])] += 1
    L += ["", "## 3. 업무 간 혼입 흐름 (top-1이 엉뚱한 업무)", "",
          "| 정답 업무 | → top-1 업무 | 건수 |", "|---|---|---|"]
    for (fr, to), cnt in flow.most_common():
        L.append(f"| {fr} | {to} | {cnt} |")

    # 4. 문항별 상세 (원인 태그 포함)
    L += ["", "## 4. 미적중 문항 상세", ""]
    for p in sorted(miss, key=lambda x: (x["bf"], x["source"], x["q"])):
        gt = set(p["gt"])
        L.append(f"### [{p['bf']} · {p['source']}] {p['q']}")
        L.append(f"- 정답 gt_docs: {p['gt']}")
        L.append(f"- 질의분류: {p['qbf']} · **원인: {_cause(p)}**")
        L.append(f"- dense rank: {dmap.get(p['q'], 0) or '미적중'} · "
                 f"{mode} rank: {p['rank'] or '미적중(top10밖)'}")
        L.append(f"- {mode} top-3:")
        for i, c in enumerate(p["top"], 1):
            L.append(f"  {i}. [{_tag(c, gt, p['bf'])}] {c['business_function']} / "
                     f"{c['page_title']}  `{c['parent_doc_id']}`")
        L.append("")

    pathlib.Path(ERR_REPORT).write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"miss": m, "n": n, "cause": dict(cause),
            "top_contam": cont.most_common(3)}


def main() -> None:
    testset = load_testset()
    searcher = rag.Searcher()

    results = {m: eval_mode(searcher, testset, m) for m in MODES}
    rep6 = {m: sum(1 for p in results[m]["per_q"] if p["representative"] and p["hit3"])
            for m in MODES}
    contam = contamination_check(searcher, ANALYZE_MODE)
    write_report(results, rep6, contam)
    err = write_error_analysis(results, ANALYZE_MODE)

    print(f"평가셋 {len(testset)}건 · 임베딩 {rag.MODEL_NAME} · RRF(k=60)\n")
    print(f"{'mode':10} {'hit@1':>7} {'hit@3':>7} {'MRR':>7}")
    for m in MODES:
        r = results[m]
        print(f"{m:10} {r['hit@1']:>7.3f} {r['hit@3']:>7.3f} {r['mrr']:>7.3f}")

    print(f"\n[micro vs macro(업무별 평균)]")
    print(f"{'mode':10} {'h3_micro':>9} {'h3_macro':>9} {'mrr_micro':>10} {'mrr_macro':>10}")
    for m in MODES:
        _, mac = group_metrics(results[m]["per_q"], "bf")
        r = results[m]
        print(f"{m:10} {r['hit@3']:>9.3f} {mac['hit@3']:>9.3f} "
              f"{r['mrr']:>10.3f} {mac['mrr']:>10.3f}")

    print(f"\n[업무별 hit@3 ({ANALYZE_MODE})]")
    rows_bf, _ = group_metrics(results[ANALYZE_MODE]["per_q"], "bf")
    for bf, r in sorted(rows_bf.items(), key=lambda x: -x[1]["n"]):
        print(f"  {bf:16} n={r['n']:3d}  hit@3={r['hit@3']:.3f}  MRR={r['mrr']:.3f}")

    print(f"\n[출처별 hit@3 ({ANALYZE_MODE})]")
    rows_src, _ = group_metrics(results[ANALYZE_MODE]["per_q"], "source")
    for s, r in sorted(rows_src.items(), key=lambda x: -x[1]["n"]):
        print(f"  {s:14} n={r['n']:3d}  hit@3={r['hit@3']:.3f}  MRR={r['mrr']:.3f}")

    # 하드필터 효과 — 업무별 hit@3: hybrid → hybrid_bf
    print(f"\n[하드필터 효과 — 업무별 hit@3: hybrid → hybrid_bf]")
    rb, _ = group_metrics(results["hybrid"]["per_q"], "bf")
    rf, _ = group_metrics(results["hybrid_bf"]["per_q"], "bf")
    for bf in sorted(rb, key=lambda x: -rb[x]["n"]):
        h, fv = rb[bf]["hit@3"], rf[bf]["hit@3"]
        print(f"  {bf:16} {h:.3f} -> {fv:.3f}  ({fv-h:+.3f})")
    oh, of = results["hybrid"]["hit@3"], results["hybrid_bf"]["hit@3"]
    print(f"  {'전체':16} {oh:.3f} -> {of:.3f}  ({of-oh:+.3f})")

    print(f"\n대표 6문항 top-3 적중  dense={rep6['dense']}/6  hybrid={rep6['hybrid']}/6  "
          f"hybrid_bf={rep6['hybrid_bf']}/6  → D1 판정({ANALYZE_MODE}) "
          f"{'통과' if rep6[ANALYZE_MODE]>=5 else '미통과'}")
    print(f"오염체크({contam['mode']}, 국내 보호한도 top-3 해외수치): "
          f"{len(contam['flagged'])}건 → {'통과' if not contam['flagged'] else '실패'}")

    # 대표문항 미적중 상세 (ANALYZE_MODE 기준 + 원인)
    miss = [p for p in results[ANALYZE_MODE]["per_q"] if p["representative"] and not p["hit3"]]
    for p in miss:
        print(f"  [미적중/{_cause(p)}] {p['q']} → top3: "
              + " | ".join(f"{c['business_function']}/{c['page_title']}" for c in p["top"]))

    # 오류분석 요약
    print(f"\n[오류분석/{ANALYZE_MODE}] 미적중 {err['miss']}/{err['n']}건 · 원인 {err['cause']}")
    if err["top_contam"]:
        top = " | ".join(f"{d}({c})" for d, c in err["top_contam"])
        print(f"  최다 혼입 문서 top3: {top}")

    print(f"\n리포트 → {REPORT}")
    print(f"오류분석 → {ERR_REPORT}")


if __name__ == "__main__":
    main()
