"""페어 평가 — 원본 vs 변형(자연어화/패러프라이즈) 질문쌍의 검색 랭크 비교.

변형 파일: 각 행에 origin_question 필드를 가진 jsonl
  (예: data/testset_natural.jsonl 150건, data/testset_para20.jsonl 20건)
같은 gt_docs 기준으로 origin_question과 question(변형)을 각각 검색해
문항 단위 paired 델타를 산출한다. 코퍼스/인덱스는 현행 그대로 사용.

사용:
  python eval_pair.py                                   # 기본: data/testset_natural.jsonl
  python eval_pair.py data/testset_para20.jsonl         # 파일 지정
  python eval_pair.py <variant.jsonl> <report.md>       # 리포트 경로까지 지정

전제: crawler/ 디렉토리에서 실행, data/index/ 빌드 완료 상태.
"""

from __future__ import annotations

import json
import pathlib
import sys

import rag
from eval import first_hit_rank, group_metrics  # 현행 eval.py 재사용

KMAX = 10
MODES = ["dense", "hybrid"]


def load(path: str) -> list[dict]:
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    missing = [r["question"][:20] for r in rows if "origin_question" not in r]
    if missing:
        sys.exit(f"[중단] origin_question 필드 없는 행 {len(missing)}건: {missing[:3]} …")
    return rows


def run_pairs(searcher: rag.Searcher, rows: list[dict]) -> list[dict]:
    per = []
    for it in rows:
        gt = set(it["gt_docs"])
        rec = {"q": it["question"], "oq": it["origin_question"],
               "bf": it["business_function"], "source": it.get("source", "?"),
               "representative": it.get("representative", False),
               "identity": it["question"] == it["origin_question"]}
        for mode in MODES:
            ro = first_hit_rank(searcher.search(it["origin_question"], k=KMAX, mode=mode), gt)
            rv = first_hit_rank(searcher.search(it["question"], k=KMAX, mode=mode), gt)
            rec[f"o_{mode}"] = ro
            rec[f"v_{mode}"] = rv
        per.append(rec)
    return per


def _metrics(per: list[dict], prefix: str, mode: str) -> dict:
    n = len(per)
    ranks = [p[f"{prefix}_{mode}"] for p in per]
    return {"hit@1": sum(r == 1 for r in ranks) / n,
            "hit@3": sum(1 <= r <= 3 for r in ranks) / n,
            "mrr": sum((1.0 / r if r else 0.0) for r in ranks) / n}


def main() -> None:
    variant_path = sys.argv[1] if len(sys.argv) > 1 else "data/testset_natural.jsonl"
    report_path = sys.argv[2] if len(sys.argv) > 2 else "data/pair_report.md"
    rows = load(variant_path)
    searcher = rag.Searcher()
    per = run_pairs(searcher, rows)
    n = len(per)
    n_id = sum(p["identity"] for p in per)

    L = [f"# 페어 평가 리포트 — 원본 vs 변형", "",
         f"- 변형셋: `{variant_path}` · {n}쌍 (동일문항 {n_id}건 포함) · k={KMAX} · 문서 단위 판정", ""]

    # 1. 종합 (micro)
    L += ["## 종합 지표 (micro)", "",
          "| mode | 셋 | hit@1 | hit@3 | MRR |", "|---|---|---|---|---|"]
    print(f"페어 {n}건 (동일문항 {n_id})\n{'mode':8}{'셋':>8}{'hit@1':>8}{'hit@3':>8}{'MRR':>8}")
    for mode in MODES:
        for pref, name in (("o", "원본"), ("v", "변형")):
            m = _metrics(per, pref, mode)
            L.append(f"| {mode} | {name} | {m['hit@1']:.3f} | {m['hit@3']:.3f} | {m['mrr']:.3f} |")
            print(f"{mode:8}{name:>8}{m['hit@1']:>8.3f}{m['hit@3']:>8.3f}{m['mrr']:>8.3f}")

    # 2. 업무별 macro (hybrid, 변형)
    for key, title in (("bf", "업무별"), ("source", "출처별")):
        L += ["", f"## {title} hit@3 (hybrid) — 원본 vs 변형", "",
              f"| {title[:-1]} | n | 원본 | 변형 | Δ |", "|---|---|---|---|---|"]
        groups: dict[str, list] = {}
        for p in per:
            groups.setdefault(p[key], []).append(p)
        for g, items in sorted(groups.items(), key=lambda x: -len(x[1])):
            o = sum(1 <= p["o_hybrid"] <= 3 for p in items) / len(items)
            v = sum(1 <= p["v_hybrid"] <= 3 for p in items) / len(items)
            L.append(f"| {g} | {len(items)} | {o:.3f} | {v:.3f} | {v - o:+.3f} |")

    # 3. 대표 6문항 판정 (변형셋 기준 — 동일문항이면 원본 판정과 같음)
    rep = [p for p in per if p["representative"]]
    if rep:
        hit = sum(1 <= p["v_hybrid"] <= 3 for p in rep)
        L += ["", f"## 대표 {len(rep)}문항 (hybrid, 변형): **{hit}/{len(rep)}**"]

    # 4. 페어 이동 요약 + 하락/상승 목록 (hybrid)
    down = [p for p in per if not p["identity"] and 1 <= p["o_hybrid"] <= 3 and not 1 <= p["v_hybrid"] <= 3]
    up = [p for p in per if not p["identity"] and not 1 <= p["o_hybrid"] <= 3 and 1 <= p["v_hybrid"] <= 3]
    L += ["", f"## 페어 이동 (hybrid hit@3 기준): 하락 {len(down)} · 상승 {len(up)} · 유지 {n - n_id - len(down) - len(up)}", ""]
    for name, lst in (("하락", down), ("상승", up)):
        if not lst:
            continue
        L += [f"### {name} 페어", "", "| 원본 | 변형 | o→v rank |", "|---|---|---|"]
        for p in sorted(lst, key=lambda x: x["v_hybrid"] or 99):
            L.append(f"| {p['oq'][:34]} | {p['q'][:34]} | {p['o_hybrid'] or '미'}→{p['v_hybrid'] or '미'} |")
        L.append("")

    # 5. 전체 페어 랭크 표
    L += ["## 전체 페어 랭크 (dense o→v / hybrid o→v)", "",
          "| # | src | 변형 질문 | dense | hybrid |", "|---|---|---|---|---|"]
    for i, p in enumerate(per):
        L.append(f"| {i:03d} | {p['source'][:6]} | {p['q'][:38]} "
                 f"| {p['o_dense'] or '미'}→{p['v_dense'] or '미'} | {p['o_hybrid'] or '미'}→{p['v_hybrid'] or '미'} |")

    pathlib.Path(report_path).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n하락 {len(down)} · 상승 {len(up)} (hybrid hit@3)")
    if rep:
        print(f"대표 {len(rep)}문항(변형): {sum(1 <= p['v_hybrid'] <= 3 for p in rep)}/{len(rep)}")
    print(f"리포트 → {report_path}")


if __name__ == "__main__":
    main()
