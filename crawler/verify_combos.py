#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""큐폼 조합 테이블 재현 가능 검증 스크립트 — T1(MSDR) + ver4 M2(DPIN).

검증 대상 2종:
  `data/qform_combos_msdr.csv`  착오송금 반환 신청 14행 — **ver1 실측 근거. 판정치 무변동이 회귀 기준**
  `data/qform_combos_dpin.csv`  예금보험금 안내 9행 — ver4 M2 신설

네임스페이스는 **파일 분리 + `combo_id` prefix**로 담보한다(§9-7 결정). MSDR 은 `C01~C14`,
DPIN 은 `DPIN-C01~`. 두 파일의 `combo_id` 교집합이 0인지 AC5 가 검사한다.

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

import span_tools as st

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
COMBOS_MSDR = BASE / "data" / "qform_combos_msdr.csv"
COMBOS_DPIN = BASE / "data" / "qform_combos_dpin.csv"
COMBOS = COMBOS_MSDR          # 하위호환 별칭
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

EXPECTED_JOIN = {          # MSDR — ver1 실측. **이 값이 바뀌면 회귀다**
    "C01": 0, "C02": 5, "C03": 6, "C04": 4, "C05": 4, "C06": 5,
    "C07": 4, "C08": 4, "C09": 1, "C10": 1, "C11": 1, "C12": 1,
    "C13": 1, "C14": 1,
}
EXPECTED_OUTCOME = {"정보": 1, "서류": 8, "서류;정보": 5}

# DPIN — ver4 M2 신설. 재료는 `DpsmIbamtAplyPossDcmnt` 단일 문서의 canonical 첨부 5건
# (ATT-15~19). 좁힘은 5 → 1~3건이다.
EXPECTED_JOIN_DPIN = {
    "DPIN-C01": 0, "DPIN-C02": 1, "DPIN-C03": 2, "DPIN-C04": 1, "DPIN-C05": 2,
    "DPIN-C06": 1, "DPIN-C07": 3, "DPIN-C08": 1, "DPIN-C09": 0,
}
EXPECTED_OUTCOME_DPIN = {"정보": 2, "서류": 3, "서류;정보": 4}

# 조합 테이블 행 수 경고등 (task_assignment M2-3). 넘으면 작성을 멈추고 판정 에스컬레이션.
ROW_WARN = 15

TABLES = [
    {"name": "MSDR · 착오송금 반환 신청", "path": COMBOS_MSDR, "prefix": "C",
     "rows": 14, "outcome": EXPECTED_OUTCOME, "join": EXPECTED_JOIN},
    {"name": "DPIN · 예금보험금 안내", "path": COMBOS_DPIN, "prefix": "DPIN-C",
     "rows": 9, "outcome": EXPECTED_OUTCOME_DPIN, "join": EXPECTED_JOIN_DPIN},
]


def read_rows(path) -> list[dict]:
    """조합 CSV 로더. **`#` 로 시작하는 줄은 주석**으로 보고 건너뛴다.

    `qform_combos_dpin.csv` 머리에 `party` 미사용 사유가 주석으로 적혀 있다(08-18 판정 1).
    MSDR 파일에는 주석이 없어 이 함수는 그쪽에서 무동작이다 — 동결 파일 무변경.
    """
    with path.open(encoding="utf-8-sig") as fh:
        lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


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


def check_table(spec: dict, atts: list, chunk_ids: set, doc_ids: set,
                raw_chunks: dict) -> tuple[bool, list]:
    """한 조합 테이블에 대해 AC1~AC4 를 돌린다. (통과여부, 행) 반환."""
    combos = read_rows(spec["path"])
    ok = True
    print(f"\n{'═' * 78}")
    print(f"■ {spec['name']}  —  {spec['path'].name}  ({len(combos)}행)")
    print("═" * 78)

    # ── AC1. 행수 · 스키마 위반 ────────────────────────────────
    print("── AC1. 행수 · 유상 스키마 허용값 위반 ──")
    row_ok = len(combos) == spec["rows"]
    print(f"  행수: {len(combos)}  (기대 {spec['rows']})  {'OK' if row_ok else 'DIFF'}")
    warn = len(combos) > ROW_WARN
    print(f"  경고등 {ROW_WARN}행: {'초과 ⚠ 판정 에스컬레이션' if warn else '이내'}")
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
    ok = ok and row_ok and not violations and not warn

    # ── outcome 분포 (D4) ─────────────────────────────────────
    oc = Counter(r["outcome"].strip() for r in combos)
    oc_ok = dict(oc) == spec["outcome"]
    print(f"  outcome 분포: {dict(oc)}  (기대 {spec['outcome']})  {'OK' if oc_ok else 'DIFF'}")
    ok = ok and oc_ok

    # ── 네임스페이스 prefix ───────────────────────────────────
    bad_ns = [r["combo_id"] for r in combos if not r["combo_id"].startswith(spec["prefix"])]
    if spec["prefix"] == "C":     # MSDR 은 DPIN- 로 시작하면 안 된다
        bad_ns = [c for c in bad_ns] + [r["combo_id"] for r in combos
                                        if r["combo_id"].startswith("DPIN-")]
    print(f"  combo_id 네임스페이스(`{spec['prefix']}`) 위반: {len(bad_ns)}건  (기대 0)  "
          f"{'OK' if not bad_ns else 'DIFF'}")
    ok = ok and not bad_ns

    # ── AC2. 근거 실재 — **스팬 기준으로 격상** (ver4 M9-2b) ──────────────
    #
    # 현행(ver1~M9-2): `evidence_chunks_v0` 의 chunk_id 가 chunks.jsonl 에 **있는가**.
    #   → 청크 ID 존재만 본다. **텍스트를 대조하지 않는다.**
    # 개정(M9-2b): `evidence_spans` 의 각 `(doc_id, 스니펫)` 이 **선언 문서 안에 정확히 1회**
    #   있는가(`span_tools.resolves_to_chunk != None`). **텍스트 실재 대조로 격상**(M9-0 판정 4).
    #
    # 왜 — 앵커 트랙이 청크 사이즈를 스윕한다. `chunk_id` 는 실험 파라미터의 함수라
    # 재청킹되면 ID 가 재배치되고 이 검사가 조용히 다른 텍스트를 통과시킨다.
    #
    # **정본은 신 컬럼 단독이다(K2).** 구 컬럼 판정은 참고 출력이며 **종료코드에 반영하지 않는다** —
    # 재청킹으로 구 기준이 전부 실패해도 이 스크립트는 통과해야 한다.
    # `evidence_spans` 가 없는 표(MSDR·동결)는 **구 검사로 폴백**하고 그 사실을 출력한다.
    has_spans = any((row.get("evidence_spans") or "").strip() for row in combos)
    print("\n── AC2. 근거 실재 " + ("(evidence_spans · 선언 문서 내 정확히 1회) ──"
                                  if has_spans else "(evidence_chunks_v0 · 폴백) ──"))
    if not has_spans:
        print("  ⚠ 이 표에는 `evidence_spans` 가 없다 → **구 검사(chunk_id 실재)로 폴백**한다.")
        print("    (동결 자산이라 이행 대상이 아니다 — 다음 스프린트 동결 해제 시 처리)")
        ev_total = ev_miss = 0
        for row in combos:
            for ev in (e.strip() for e in row["evidence_chunks_v0"].split("|") if e.strip()):
                ev_total += 1
                if ev not in chunk_ids:
                    ev_miss += 1
                    print(f"     ✗ {row['combo_id']} 미실재 chunk_id: {ev}")
        print(f"  앵커 {ev_total}개 중 미실재 {ev_miss}건  (기대 0)  "
              f"{'OK' if ev_miss == 0 else 'DIFF'}")
        ok = ok and ev_miss == 0
    else:
        sp_total = sp_miss = 0
        for row in combos:
            for doc_id, snip in st.parse_spans(row.get("evidence_spans", "")):
                sp_total += 1
                if st.resolves_to_chunk(doc_id, snip, raw_chunks) is None:
                    sp_miss += 1
                    print(f"     ✗ {row['combo_id']} 미해소 스팬: {doc_id}::{snip[:30]}")
        print(f"  스팬 {sp_total}개 중 미해소 {sp_miss}건  (기대 0)  "
              f"{'OK' if sp_miss == 0 else 'DIFF'}")
        ok = ok and sp_miss == 0
        # 구 컬럼 — **참고 출력만.** 종료코드에 반영하지 않는다(K2)
        old_total = old_miss = 0
        for row in combos:
            for ev in (e.strip() for e in row["evidence_chunks_v0"].split("|") if e.strip()):
                old_total += 1
                old_miss += (ev not in chunk_ids)
        print(f"  [참고] 구 컬럼 chunk_id {old_total}개 중 미실재 {old_miss}건 "
              f"— 종료코드 미반영(재청킹 시 여기부터 깨진다)")

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
    print(f"  {'combo':9} {'실측':>4} {'기대':>4}  판정  매칭 attachment_id")
    join_ok = True
    total = 0
    for row in combos:
        cid = row["combo_id"]
        matched = [a["attachment_id"] for a in atts if joins(row, a)]
        n = len(matched)
        total += n
        exp = spec["join"].get(cid)
        good = n == exp
        join_ok = join_ok and good
        print(f"  {cid:9} {n:>4} {exp if exp is not None else '?':>4}  "
              f"{'OK' if good else 'DIFF':4} {','.join(matched) if matched else '-'}")
    exp_total = sum(spec["join"].values())
    print(f"  {'합계':7} {total:>4} {exp_total:>4}  {'OK' if total == exp_total else 'DIFF'}")
    ok = ok and join_ok and total == exp_total
    return ok, combos


def main() -> int:
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

    raw_chunks = st.load_chunks(CHUNKS)      # 스팬 검사용 (chunk_id -> text/parent_doc_id)
    print(f"소스: attachments={len(atts)}행 · chunks={len(chunk_ids)}청크 / {len(doc_ids)}문서")

    ok = True
    tables = {}
    for spec in TABLES:
        t_ok, rows = check_table(spec, atts, chunk_ids, doc_ids, raw_chunks)
        tables[spec["prefix"]] = rows
        ok = ok and t_ok

    # ── AC5. 네임스페이스 무충돌 (파일 분리 + prefix 로 담보) ──
    print(f"\n{'═' * 78}")
    print("── AC5. combo_id 네임스페이스 무충돌 ──")
    ids = [set(r["combo_id"] for r in rows) for rows in tables.values()]
    clash = ids[0] & ids[1] if len(ids) == 2 else set()
    print(f"  MSDR {len(ids[0])}개 · DPIN {len(ids[1])}개 · 교집합 {len(clash)}건  (기대 0)  "
          f"{'OK' if not clash else 'DIFF'}")
    if clash:
        print(f"     ✗ 충돌: {sorted(clash)}")
    ok = ok and not clash

    print("\n" + ("전체 통과 ✅" if ok else "실패 — 표/태깅 중 하나가 바뀐 것. 멈추고 보고 ⛔"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
