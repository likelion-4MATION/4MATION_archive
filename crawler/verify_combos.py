#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""큐폼 조합 테이블(qform_combos_msdr.csv) 재현 가능 검증 스크립트 — T1.

출력 4종 (task_assignment.md T1 수용 기준):
  AC1. 14행 · 유상 스키마 허용값 위반 0건 (제도안내/팩스는 T1-b 예외)
  AC2. evidence_chunks_v0 의 모든 chunk_id 가 chunks.jsonl 에 실재 (미실재 0)
  AC3. source_doc_id 의 모든 doc_id 가 실재 (미실재 0)
  AC4. 유상 태깅과 조인 — combo별 매칭 첨부 수가 기대치와 일치

조인 술어(유상 태깅 스키마 §3):
  business_function 정확 · party 공란=와일드카드/그외 정확 · sub_task 정확
  qualification 다중값 overlap(공란=와일드카드)
  subject '공통'=양방향 와일드카드(공란 포함)/그외 overlap
  method 다중값 overlap(공란=와일드카드)
  → outcome/source_doc_id/evidence 는 조인 키 아님(출력·근거용).

측정 없이 통과라고 말하지 않는다. 실패 시 종료코드 1.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
COMBOS = BASE / "data" / "qform_combos_msdr.csv"
CHUNKS = BASE / "data" / "chunks.jsonl"
TAGGING = BASE / "yesom_분기분석" / "attachment_tagging_template.csv"

# 유상 태깅 스키마 §2 허용값. (제도안내·팩스는 T1-b 에서 스키마에 추가되는 예외)
ALLOWED = {
    "business_function": {"착오송금 반환 신청", "예금보험금 안내", "예금자보호제도", "채무조정 안내"},
    "party": {"송금인", "수취인"},  # 공란 허용
    "sub_task": {
        "반환신청", "이의제기", "이체수수료환급", "신청철회", "매입계약해제",
        "수령계좌변경", "대리인변경", "보험금신청", "부보금융회사조회", "부채증명",
        "제도안내",  # T1-b 추가분
    },
    "qualification": {"본인", "대리인"},  # 공란 허용
    "subject": {
        "본인", "대리인", "미성년자", "군복무자", "사망 예금자",
        "국외거주 또는 유학생", "법인", "비법인단체", "공통",
    },
    "method": {"온라인", "방문", "우편", "이메일", "팩스"},  # 팩스 = T1-b 추가분
}
T1B_WHITELIST = {("sub_task", "제도안내"), ("method", "팩스")}

COORD_FIELDS = ("business_function", "party", "sub_task", "qualification", "subject", "method")

EXPECTED_JOIN = {
    "C01": 0, "C02": 5, "C03": 6, "C04": 4, "C05": 4, "C06": 5,
    "C07": 4, "C08": 4, "C09": 1, "C10": 1, "C11": 1, "C12": 1,
    "C13": 1, "C14": 1,
}
EXPECTED_OUTCOME = {"정보": 1, "서류": 8, "서류;정보": 5}


def toks(s: str) -> set[str]:
    """다중값(;) → 토큰 집합. 공란 제거."""
    return {t.strip() for t in (s or "").split(";") if t.strip()}


def joins(combo: dict, att: dict) -> bool:
    """combo 좌표와 attachment 좌표가 조인되는가."""
    if combo["business_function"].strip() != att["business_function"].strip():
        return False
    cp, ap = combo["party"].strip(), att["party"].strip()
    if cp and ap and cp != ap:  # 공란=와일드카드
        return False
    if combo["sub_task"].strip() != att["sub_task"].strip():
        return False
    qc, qa = toks(combo["qualification"]), toks(att["qualification"])
    if qc and qa and not (qc & qa):  # 공란=와일드카드, 그외 overlap
        return False
    sc, sa = toks(combo["subject"]), toks(att["subject"])
    if sc and sa and "공통" not in sc and "공통" not in sa and not (sc & sa):
        return False  # '공통' 양방향 와일드카드, 공란=와일드카드, 그외 overlap
    mc, ma = toks(combo["method"]), toks(att["method"])
    if mc and ma and not (mc & ma):
        return False
    return True


def main() -> int:
    # utf-8-sig: BOM 이 첫 컬럼 헤더에 붙는 경우 제거 (attachment_id KeyError 방지)
    combos = list(csv.DictReader(COMBOS.open(encoding="utf-8-sig")))
    atts = list(csv.DictReader(TAGGING.open(encoding="utf-8-sig")))

    chunk_ids: set[str] = set()
    doc_ids: set[str] = set()
    with CHUNKS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            chunk_ids.add(d["chunk_id"])
            doc_ids.add(d["parent_doc_id"])

    ok = True
    print(f"소스: combos={len(combos)}행 · attachments={len(atts)}행 · "
          f"chunks={len(chunk_ids)}청크 / {len(doc_ids)}문서\n")

    # ── AC1. 14행 · 스키마 위반 ────────────────────────────────
    print("── AC1. 행수 · 유상 스키마 허용값 위반 ──")
    row_ok = len(combos) == 14
    print(f"  행수: {len(combos)}  (기대 14)  {'OK' if row_ok else 'DIFF'}")
    violations = []
    t1b_used = set()
    for row in combos:
        for f in COORD_FIELDS:
            field_toks = {row[f].strip()} if f == "business_function" else toks(row[f])
            for tok in field_toks:
                if not tok:
                    continue
                if (f, tok) in T1B_WHITELIST:
                    t1b_used.add((f, tok))
                elif tok not in ALLOWED[f]:
                    violations.append((row["combo_id"], f, tok))
    print(f"  허용값 위반: {len(violations)}건  (기대 0)  {'OK' if not violations else 'DIFF'}")
    for cid, f, tok in violations:
        print(f"     ✗ {cid} {f}={tok!r}")
    print(f"  T1-b 예외값 사용: {sorted(t1b_used)}")
    row_pass = row_ok and not violations
    ok = ok and row_pass

    # ── outcome 분포 (D4 부수 확인) ───────────────────────────
    oc = Counter(r["outcome"].strip() for r in combos)
    oc_ok = dict(oc) == EXPECTED_OUTCOME
    print(f"  outcome 분포: {dict(oc)}  (기대 {EXPECTED_OUTCOME})  {'OK' if oc_ok else 'DIFF'}")
    ok = ok and oc_ok

    # ── AC2. evidence chunk_id 실재 ───────────────────────────
    print("\n── AC2. evidence_chunks_v0 chunk_id 실재 ──")
    ev_total = ev_miss = 0
    for row in combos:
        for ev in (e.strip() for e in row["evidence_chunks_v0"].split("|") if e.strip()):
            ev_total += 1
            if ev not in chunk_ids:
                ev_miss += 1
                print(f"     ✗ {row['combo_id']} 미실재 chunk_id: {ev}")
    print(f"  앵커 {ev_total}개 중 미실재 {ev_miss}건  (기대 0)  {'OK' if ev_miss == 0 else 'DIFF'}")
    ok = ok and ev_miss == 0

    # ── AC3. source_doc_id 실재 ───────────────────────────────
    print("\n── AC3. source_doc_id doc_id 실재 ──")
    sd_total = sd_miss = 0
    for row in combos:
        for sd in toks(row["source_doc_id"]):
            sd_total += 1
            if sd not in doc_ids:
                sd_miss += 1
                print(f"     ✗ {row['combo_id']} 미실재 doc_id: {sd}")
    print(f"  doc 참조 {sd_total}개 중 미실재 {sd_miss}건  (기대 0)  {'OK' if sd_miss == 0 else 'DIFF'}")
    ok = ok and sd_miss == 0

    # ── AC4. 유상 태깅 조인 ───────────────────────────────────
    print("\n── AC4. 유상 태깅과 조인 (combo별 매칭 첨부 수) ──")
    print(f"  {'combo':6} {'실측':>4} {'기대':>4}  판정  매칭 attachment_id")
    join_ok = True
    total = 0
    for row in combos:
        cid = row["combo_id"]
        matched = [a["attachment_id"] for a in atts if joins(row, a)]
        n = len(matched)
        total += n
        exp = EXPECTED_JOIN.get(cid)
        good = n == exp
        join_ok = join_ok and good
        print(f"  {cid:6} {n:>4} {exp if exp is not None else '?':>4}  "
              f"{'OK' if good else 'DIFF':4} {','.join(matched) if matched else '-'}")
    exp_total = sum(EXPECTED_JOIN.values())
    print(f"  {'합계':4} {total:>4} {exp_total:>4}  {'OK' if total == exp_total else 'DIFF'}")
    ok = ok and join_ok and total == exp_total

    print("\n" + ("전체 통과 ✅" if ok else "실패 — 표/태깅 중 하나가 바뀐 것. 멈추고 보고 ⛔"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
