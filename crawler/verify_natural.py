"""testset_natural.jsonl 정합성 게이트 — 자연어화 셋이 merged와 페어 성립하는지 전수 검증.

게이트:
  G1 커버리지    merged 150행 전부가 natural에 1:1 존재 (origin_question 키)
  G2 스키마      6필드 고정 (question/gt_docs/business_function/source/representative/origin_question)
  G3 불변성      gt_docs·business_function·source·representative == merged (대표 6은 질문도 동일)
  G4 유일성      natural 질문 내부 중복 0 · 비대표 질문이 원본 질문과 교차 0
  G5 코퍼스      모든 gt_docs가 chunks.jsonl의 parent_doc_id에 존재
  G6 복붙        자연어 질문 ↔ gt 청크의 공백제거 최장공통부분문자열 < 12자 (자기참조 누수 방지)

사용: crawler/ 에서  python verify_natural.py
"""

from __future__ import annotations

import difflib
import json
import statistics
import sys
from collections import Counter

NATURAL = "data/testset_natural.jsonl"
MERGED = "data/testset_merged.jsonl"
CHUNKS = "data/chunks.jsonl"
LCS_LIMIT = 12

FIELDS = sorted(["question", "gt_docs", "business_function", "source", "representative", "origin_question"])


def norm(s: str) -> str:
    return "".join(s.split())


def main() -> None:
    nat = [json.loads(l) for l in open(NATURAL, encoding="utf-8")]
    mer = [json.loads(l) for l in open(MERGED, encoding="utf-8")]
    chunks = [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]
    corpus: dict[str, list[str]] = {}
    for c in chunks:
        corpus.setdefault(c["parent_doc_id"], []).append(c["text"])
    fails: list[str] = []

    # G1 커버리지 (순서 무관, origin_question 기준 1:1)
    nmap = {r["origin_question"]: r for r in nat}
    miss = [m["question"] for m in mer if m["question"] not in nmap]
    if len(nat) != len(mer) or miss:
        fails.append(f"G1 커버리지: natural {len(nat)} vs merged {len(mer)}, 누락 {miss[:3]}")
    print(f"[G1] merged {len(mer)} ↔ natural {len(nat)} · 누락 {len(miss)}건")

    # G2 + G3
    bad2, bad3 = [], []
    for m in mer:
        r = nmap.get(m["question"])
        if r is None:
            continue
        if sorted(r) != FIELDS:
            bad2.append(r["origin_question"][:20])
        if (r["gt_docs"] != m["gt_docs"] or r["business_function"] != m["business_function"]
                or r["source"] != m["source"] or r["representative"] != m["representative"]
                or (m["representative"] and r["question"] != m["question"])):
            bad3.append(m["question"][:20])
    if bad2:
        fails.append(f"G2 스키마: {bad2[:3]}")
    if bad3:
        fails.append(f"G3 불변성: {bad3[:3]}")
    print(f"[G2] 스키마 위반 {len(bad2)}건 · [G3] 불변성 위반 {len(bad3)}건")

    # G4 유일성
    dup = [q for q, c in Counter(r["question"] for r in nat).items() if c > 1]
    origin_qs = {m["question"] for m in mer}
    cross = [r["question"] for r in nat if not r["representative"] and r["question"] in origin_qs]
    if dup or cross:
        fails.append(f"G4 유일성: dup={dup[:2]} cross={cross[:2]}")
    print(f"[G4] 내부 중복 {len(dup)}건 · 원본 교차 {len(cross)}건")

    # G5 코퍼스
    out = [(r["origin_question"][:20], d) for r in nat for d in r["gt_docs"] if d not in corpus]
    if out:
        fails.append(f"G5 코퍼스: {out[:3]}")
    print(f"[G5] 코퍼스 밖 gt {len(out)}건")

    # G6 복붙 (비대표만 — 대표 6은 원문 유지가 사양)
    worst: list[tuple[int, str, str]] = []
    for r in nat:
        if r["representative"]:
            continue
        qn = norm(r["question"])
        best, snip = 0, ""
        for d in r["gt_docs"]:
            for t in corpus.get(d, []):
                tn = norm(t)
                m = difflib.SequenceMatcher(None, qn, tn).find_longest_match(0, len(qn), 0, len(tn))
                if m.size > best:
                    best, snip = m.size, qn[m.a:m.a + m.size]
        worst.append((best, snip, r["question"][:24]))
    worst.sort(reverse=True)
    viol = [w for w in worst if w[0] >= LCS_LIMIT]
    print(f"[G6] 복붙(공백제거 LCS ≥{LCS_LIMIT}자) 위반 {len(viol)}건 · 최장 {worst[0][0]}자 '{worst[0][1]}'")
    if viol:
        fails.append(f"G6 복붙: " + "; ".join(f"{b}자 '{s}' ({q})" for b, s, q in viol[:3]))

    # 스타일 통계 (참고)
    ol = statistics.median(len(m["question"]) for m in mer if not m["representative"])
    nl = statistics.median(len(r["question"]) for r in nat if not r["representative"])
    print(f"[통계] 질문 길이 중앙값 {ol:.0f} → {nl:.0f}자 · 물음표 비율 "
          f"{sum('?' in m['question'] for m in mer) / len(mer):.0%} → {sum('?' in r['question'] for r in nat) / len(nat):.0%}")

    if fails:
        print("\n❌ 게이트 실패:")
        for f_ in fails:
            print("  -", f_)
        sys.exit(1)
    print("\n✅ 모든 게이트 통과")


if __name__ == "__main__":
    main()
