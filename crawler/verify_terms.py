#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""용어 판별 사전(qform_terms_v0.csv) 재현 가능 검증 스크립트 — ver4 M1.

출력 5종 (Qform_ver4_task_assignment M1 §3 수용 기준):
  T-AC1. evidence_chunks_v0 의 모든 chunk_id 가 chunks.jsonl 에 실재 (미실재 0)
  T-AC2. source_doc_id 의 모든 doc_id 가 실재 (미실재 0)
  T-AC3. 축자성 — one_line / discriminator 가 근거 청크 원문에 **그대로** 존재 (창작 검출)
  T-AC4. confusable_with 가 실재 term_id 를 가리킴 (dangling 0)
  T-AC5. term 중복 0

축자성 판정 기준 (T-AC3) — **핵심 어구 부분일치가 아니라 완전 부분문자열 일치**를 쓴다:
  - `one_line`      ⊂ `evidence_chunks_v0` 의 **첫 번째** 청크 본문
  - `discriminator` ⊂ `evidence_chunks_v0` 중 **어느 한** 청크 본문

  왜 이렇게 조였나 — 규칙1(코퍼스에 없는 결론을 만들지 않는다)에서 "핵심 어구가 있다"는
  기준은 어구를 골라내는 사람의 재량이 들어가 창작을 통과시킨다. 완전 부분문자열은 재량이
  0이고 기계가 판정한다. **다듬어 매끄럽게 만드는 것도 창작**이므로 통과 못 하는 문구는
  문장을 고치는 게 아니라 코퍼스 문장으로 되돌린다.

  `one_line` 을 첫 번째 청크로 못 박는 이유: 정의가 여러 청크에 흩어져 있을 때
  `one_line` 은 **그중 한 문장에서만** 와야 한다(M1 명세). 컬럼을 늘리지 않고 그 출처를
  고정하려고 `evidence_chunks_v0[0]` 을 one_line 의 출처 자리로 규약화했다.

측정 없이 통과라고 말하지 않는다. 실패 시 종료코드 1.

    python3 crawler/verify_terms.py
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
TERMS = BASE / "data" / "qform_terms_v0.csv"
CHUNKS = BASE / "data" / "chunks.jsonl"

# 태깅 스키마 §2 business_function 허용값 + 코퍼스 실재 업무.
# 지급금 용어 2종의 정의 문단이 '고객 미수령금 신청' 청크에 있어 그 값을 허용한다(M1 보고 §3).
ALLOWED_BF = {
    "착오송금 반환 신청", "예금보험금 안내", "예금자보호제도",
    "채무조정 안내", "고객 미수령금 신청", "은닉재산 신고", "공통",
}
ID_PREFIXES = ("PAY-", "DEBT-")


def toks(s: str) -> list[str]:
    """다중값(;) → 토큰 리스트. 공란 제거. 순서 보존(one_line 출처가 [0] 이라 순서가 의미를 갖는다)."""
    return [t.strip() for t in (s or "").split(";") if t.strip()]


def load():
    rows = list(csv.DictReader(TERMS.open(encoding="utf-8")))
    chunks = {}
    docs = set()
    for line in CHUNKS.open(encoding="utf-8"):
        c = json.loads(line)
        chunks[c["chunk_id"]] = c
        docs.add(c["parent_doc_id"])
    # T-AC3 는 `span_tools` 형태(chunk_id -> {text, parent_doc_id})를 쓴다
    raw = st.load_chunks(CHUNKS)
    return rows, chunks, docs, raw


def main() -> int:
    rows, chunks, docs, raw = load()
    fails: list[str] = []
    print(f"소스: terms={len(rows)}행 · chunks={len(chunks)}청크 / {len(docs)}문서\n")

    # ── T-AC1. evidence_chunks_v0 실재 ──────────────────────────────────────
    print("── T-AC1. evidence_chunks_v0 chunk_id 실재 ──")
    ev_total = 0
    ev_missing: list[tuple[str, str]] = []
    for r in rows:
        for c in toks(r["evidence_chunks_v0"]):
            ev_total += 1
            if c not in chunks:
                ev_missing.append((r["term_id"], c))
    print(f"  앵커 {ev_total}개 중 미실재 {len(ev_missing)}건  (기대 0)  "
          f"{'OK' if not ev_missing else 'DIFF ⛔'}")
    for tid, c in ev_missing:
        print(f"    {tid}  {c}")
    if ev_missing:
        fails.append("T-AC1 evidence 미실재")

    # ── T-AC2. source_doc_id 실재 ───────────────────────────────────────────
    print("\n── T-AC2. source_doc_id doc_id 실재 ──")
    doc_missing = [(r["term_id"], r["source_doc_id"]) for r in rows
                   if r["source_doc_id"] not in docs]
    print(f"  doc 참조 {len(rows)}개 중 미실재 {len(doc_missing)}건  (기대 0)  "
          f"{'OK' if not doc_missing else 'DIFF ⛔'}")
    for tid, d in doc_missing:
        print(f"    {tid}  {d}")
    if doc_missing:
        fails.append("T-AC2 doc 미실재")

    # ── T-AC3. 축자성 — **스팬 기준** (ver4 M9-1b 개정) ─────────────────────
    #
    # 개정 전: `evidence_chunks_v0[0]` 청크 텍스트에 `one_line` 이 부분문자열로 있는가.
    # 개정 후: `evidence_spans` 의 각 `(doc_id, 스니펫)` 이 **선언 문서 안에서 정확히 1회**
    #          나오는가(`span_tools.resolves_to_chunk` 가 None 이 아님).
    #
    # 왜 옮겼나 — 앵커 트랙이 **청크 사이즈를 동적으로 스윕**한다. `chunk_id` 는 고정
    # 식별자가 아니라 실험 파라미터의 함수라, 재청킹되면 `#00` 이 통째로 재배치되고
    # 이 검사가 조용히 다른 텍스트를 대조하게 된다. `(doc_id, 스니펫)` 은 둘 다 청킹 불변이다.
    #
    # **청크 경계를 넘어가면 통과하지 않는다** — `occurrences_in_doc` 이 청크 단위로 세므로,
    # 문서 텍스트에는 있는데 어느 단일 청크에도 온전히 없으면 0회가 되어 실패한다.
    # 구 포맷과 해상도는 같다: 코퍼스 전체 유일성은 구 `chunk_id` 도 보증한 적이 없다.
    print("\n── T-AC3. 축자성 (evidence_spans · 선언 문서 안에서 정확히 1회) ──")
    print(f"  {'term_id':9} {'term':14} {'스팬':>4} {'해소':>4} {'구 컬럼 기준':>10}  판정")
    bad_verbatim = 0
    legacy_bad = 0
    for r in rows:
        spans = st.parse_spans(r.get("evidence_spans", ""))
        resolved = [st.resolves_to_chunk(d, sn, raw) for d, sn in spans]
        ok_new = bool(spans) and all(c is not None for c in resolved)

        # 3-3 — 개정 전(구 컬럼) 판정을 같이 낸다. 회귀 비교용이며 통과 조건은 아니다.
        ev = toks(r["evidence_chunks_v0"])
        head = chunks.get(ev[0], {}).get("text", "") if ev else ""
        ok_old = (bool(r["one_line"]) and r["one_line"] in head
                  and bool(r["discriminator"])
                  and any(r["discriminator"] in chunks.get(c, {}).get("text", "") for c in ev))
        legacy_bad += (not ok_old)
        bad_verbatim += (not ok_new)
        print(f"  {r['term_id']:9} {r['term']:14} {len(spans):4} "
              f"{sum(1 for c in resolved if c):4} {str(ok_old):>10}  "
              f"{'OK' if ok_new else 'DIFF ⛔ 창작 의심'}")
    print(f"  창작 검출 {bad_verbatim}건  (기대 0)  {'OK' if not bad_verbatim else 'DIFF ⛔'}")
    print(f"  [참고] 개정 전 기준 위반 {legacy_bad}건 — 두 기준이 같은 판정을 내는지 병기")
    if bad_verbatim:
        fails.append("T-AC3 축자성 위반")

    # ── T-AC4. confusable_with dangling ─────────────────────────────────────
    print("\n── T-AC4. confusable_with 참조 무결성 ──")
    ids = {r["term_id"] for r in rows}
    dangling: list[tuple[str, str]] = []
    self_ref: list[str] = []
    conf_total = 0
    for r in rows:
        for c in toks(r["confusable_with"]):
            conf_total += 1
            if c not in ids:
                dangling.append((r["term_id"], c))
            if c == r["term_id"]:
                self_ref.append(r["term_id"])
    print(f"  혼동 참조 {conf_total}개 중 dangling {len(dangling)}건 · 자기참조 {len(self_ref)}건  "
          f"(기대 0/0)  {'OK' if not dangling and not self_ref else 'DIFF ⛔'}")
    for tid, c in dangling:
        print(f"    {tid} → {c}  (미실재)")
    if dangling or self_ref:
        fails.append("T-AC4 confusable dangling")

    # ── T-AC5. term 중복 · id 규약 ──────────────────────────────────────────
    print("\n── T-AC5. term 중복 · term_id 규약 ──")
    dup_term = [t for t, n in Counter(r["term"] for r in rows).items() if n > 1]
    dup_id = [t for t, n in Counter(r["term_id"] for r in rows).items() if n > 1]
    bad_prefix = [r["term_id"] for r in rows if not r["term_id"].startswith(ID_PREFIXES)]
    bad_bf = [(r["term_id"], r["business_function"]) for r in rows
              if r["business_function"] not in ALLOWED_BF]
    print(f"  term 중복 {len(dup_term)}건 · term_id 중복 {len(dup_id)}건  (기대 0/0)  "
          f"{'OK' if not dup_term and not dup_id else 'DIFF ⛔'}")
    print(f"  term_id 네임스페이스 위반 {len(bad_prefix)}건 (PAY-/DEBT-)  (기대 0)  "
          f"{'OK' if not bad_prefix else 'DIFF ⛔'}")
    print(f"  business_function 허용값 위반 {len(bad_bf)}건  (기대 0)  "
          f"{'OK' if not bad_bf else 'DIFF ⛔'}")
    for t in dup_term:
        print(f"    중복 term: {t}")
    for tid, bf in bad_bf:
        print(f"    {tid}  bf={bf}")
    if dup_term or dup_id or bad_prefix or bad_bf:
        fails.append("T-AC5 중복/규약 위반")

    # ── 참고 집계 (판정 아님) ───────────────────────────────────────────────
    print("\n── 참고. 네임스페이스별 행수 · 업무 분포 ──")
    ns = Counter(r["term_id"].split("-")[0] for r in rows)
    bf = Counter(r["business_function"] for r in rows)
    print(f"  네임스페이스: {dict(ns)}")
    print(f"  업무: {dict(bf)}")

    print()
    if fails:
        print("어긋난 AC ⛔")
        for f in fails:
            print(f"  {f}")
        return 1
    print("전체 통과 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
