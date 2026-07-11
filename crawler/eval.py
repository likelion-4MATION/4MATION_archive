"""검색 평가 — hit@1 · hit@3 · MRR, dense-only vs hybrid(RRF) 비교, MD 리포트.

정답 판정: top-k 청크의 parent_doc_id가 gt_docs에 포함되면 적중(문서 단위).
D1 통과 판정은 대표 6문항 top-3 적중 5+ (representative=True).
오염체크: 국내 보호한도 질문 top-3에 해외 한도 수치 혼입 0건.

사용: python eval.py   → 콘솔 요약 + data/eval_report.md
"""

from __future__ import annotations

import json

import rag

TESTSET = "data/testset.jsonl"
REPORT = "data/eval_report.md"
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
                      "bf": it["business_function"], "top": hits[:3]})
    n = len(testset)
    return {"mode": mode, "n": n, "hit@1": h1 / n, "hit@3": h3 / n,
            "mrr": mrr / n, "per_q": per_q}


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
         "", "## 전체 지표 (dense vs hybrid)", "",
         "| mode | hit@1 | hit@3 | MRR |", "|---|---|---|---|"]
    for m in MODES:
        r = results[m]
        L.append(f"| {m} | {r['hit@1']:.3f} | {r['hit@3']:.3f} | {r['mrr']:.3f} |")
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

    print(f"평가셋 {len(testset)}건 · 임베딩 {rag.MODEL_NAME} · RRF(k=60)\n")
    print(f"{'mode':8} {'hit@1':>7} {'hit@3':>7} {'MRR':>7}")
    for m in MODES:
        r = results[m]
        print(f"{m:8} {r['hit@1']:>7.3f} {r['hit@3']:>7.3f} {r['mrr']:>7.3f}")
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
