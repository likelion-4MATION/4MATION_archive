# -*- coding: utf-8 -*-
"""큐폼 E2E 배선 검증 — T4 AC 실측.

`qform_flow` 는 streamlit 을 모르므로 UI 없이 전이 규칙을 그대로 돌려볼 수 있다.
`answer()` 는 **주입 스텁**으로 대체해 HCX 콜 0 으로 검증한다 —
"되묻기 턴에 answer() 를 부르지 않는다"는 계약은 호출 횟수를 세면 그만이고,
그게 AC1 의 실체다.

첨부(AC6)는 스텁이 아니라 **실제 `attachments.collect()`** 를 돌린다. 네트워크가
필요 없는 순수 로컬 조인이라, 부스트 OFF 에서 v1 과 첨부가 같은지 진짜로 비교할 수 있다.

실행: python3 chatbot/verify_qform_e2e.py
"""
from __future__ import annotations

import json
import pathlib
import sys

_BASE = pathlib.Path(__file__).resolve().parent.parent
for _p in (_BASE / "chatbot", _BASE / "crawler"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import qform_trace  # noqa: E402  (rag 상수 로더 — 검색 스택 없는 환경도 통과시킨다)
import attachments  # noqa: E402
import qform_ask  # noqa: E402
import qform_flow  # noqa: E402
import qform_state  # noqa: E402
from qform_extract import extract  # noqa: E402

classify_query_bf = qform_trace.rag.classify_query_bf
SLOT_FIELDS = qform_state.SLOT_FIELDS
fails: list[tuple[str, str, str]] = []

# ── 답변 스텁 — 호출 인자를 그대로 기록한다 (콜 0) ────────────────────────────
CALLS: list[tuple[str, dict]] = []


def stub_answer(query: str, qform: dict) -> dict:
    CALLS.append((query, dict(qform)))
    return {"text": "(스텁 답변)", "sources": [], "confidence": 0.0, "route": "rag",
            "checks": {"ok": True, "flags": []}, "_meta": {"latency_ms": 0}}


def run(script: list[str], *, boost=False, ask_mode="template", skip_at=None,
        llm_call=None) -> tuple[dict, list[dict]]:
    """대화 1건 재생. script[0]=최초 질의, 이후는 되묻기 응답.
    skip_at=n 이면 n번째 되묻기에서 탈출구를 누른다."""
    st, evs = qform_flow.new_state(), []
    kw = dict(ask_mode=ask_mode, boost=boost, answer_fn=stub_answer, llm_call=llm_call)
    ev = qform_flow.start(st, script[0], **kw)
    evs.append(ev)
    for i, reply in enumerate(script[1:], 1):
        if ev["kind"] != "ask":
            break
        if skip_at == i:
            ev = qform_flow.skip(st, boost=boost, answer_fn=stub_answer)
        else:
            ev = qform_flow.reply(st, reply, **kw)
        evs.append(ev)
    if ev["kind"] == "ask" and skip_at == "end":
        evs.append(qform_flow.skip(st, boost=boost, answer_fn=stub_answer))
    return st, evs


print("큐폼 E2E 전이 검증 — HCX 콜 0 (answer 스텁 · 첨부는 실제 collect)\n")

# ── AC1. 2턴 대화에서 생성 콜 1회 · 되묻기 턴에 answer() 미호출 ──────────────
print("── AC1. 되묻기 2턴 = 생성 콜 1회 (ⓐ 모드) ──")
CALLS.clear()
st1, ev1 = run(["착오송금 반환 신청하려는데 필요한 서류 알려주세요", "대리인이 신청해요", "법인이요"])
kinds = [e["kind"] for e in ev1]
ask_calls = sum(e["ask"]["calls"] for e in ev1 if e["kind"] == "ask")
ac1 = kinds == ["ask", "ask", "answer"] and len(CALLS) == 1 and ask_calls == 0
print(f"  전이: {' → '.join(kinds)}")
print(f"  answer() 호출 {len(CALLS)}회 (기대 1) · 되묻기 문구 LLM 콜 {ask_calls} (기대 0)")
print(f"  되묻기 2턴 동안 answer() 호출 {kinds[:2].count('answer')}회 (기대 0)"
      f"  → {'OK' if ac1 else 'DIFF ⛔'}")
if not ac1:
    fails.append(("AC1", "ask,ask,answer · 콜1", f"{kinds} · {len(CALLS)}회"))

# ⓑ 모드 콜 회계 — 되묻기 턴당 +1, 생성은 그대로 1
CALLS.clear()
_, ev1b = run(["착오송금 반환 신청하려는데 필요한 서류 알려주세요", "대리인이 신청해요", "법인이요"],
              ask_mode="llm",
              llm_call=lambda m: ("법인, 비법인단체, 미성년자 중 누구를 대리해 신청하시나요?",
                                  {"error": None, "calls": 1}))
b_ask = sum(e["ask"]["calls"] for e in ev1b if e["kind"] == "ask")
print(f"  [참고] ⓑ 모드 같은 대화: 되묻기 콜 {b_ask} + 생성 {len(CALLS)} = 총 {b_ask + len(CALLS)}콜")

# ── AC2. 최대 2턴 후 슬롯 미채움이어도 진행 ─────────────────────────────────
print("\n── AC2. 2턴 후 미채움이어도 진행 ──")
CALLS.clear()
st2, ev2 = run(["착오송금 반환 신청 서류가 뭐예요?", "글쎄요", "잘 모르겠어요"])
kinds2 = [e["kind"] for e in ev2]
unfilled = [f for f in ("qualification", "subject") if st2["qform"][f] is None]
ac2 = kinds2 == ["ask", "ask", "answer"] and len(CALLS) == 1 and st2["ask_turn"] == 2
print(f"  전이: {' → '.join(kinds2)} · ask_turn={st2['ask_turn']} · 미채움 슬롯 {unfilled}")
print(f"  3번째 되묻기 없이 답변 진행 · 생존 {len(qform_state.survivors(st2['qform']))}행"
      f"  → {'OK' if ac2 else 'DIFF ⛔'}")
if not ac2:
    fails.append(("AC2", "2턴 후 answer", f"{kinds2} · turn={st2['ask_turn']}"))

# ── AC3. 탈출구 — 즉시 답변 · 되묻기 재발동 없음 ────────────────────────────
print("\n── AC3. 탈출구 (즉시 답변 · 재발동 없음) ──")
CALLS.clear()
st3, ev3 = run(["착오송금 반환 신청 서류가 뭐예요?", "…"], skip_at=1)
kinds3 = [e["kind"] for e in ev3]
# 탈출 후 같은 상태에서 한 번 더 진행시켜도 되묻기가 다시 뜨면 안 된다
again = qform_flow._step(st3, ask_mode="template", boost=False,
                         answer_fn=stub_answer, llm_call=None)
ac3 = (kinds3 == ["ask", "answer"] and st3["pending_slot"] is None
       and again["kind"] == "answer")
surv3 = len(qform_state.survivors(st3["qform"]))
print(f"  전이: {' → '.join(kinds3)} · pending={st3['pending_slot']} · 생존 {surv3}행(유지)")
print(f"  탈출 후 재진입: {again['kind']} (기대 answer)  → {'OK' if ac3 else 'DIFF ⛔'}")
if not ac3:
    fails.append(("AC3", "ask,answer · 재발동 없음", f"{kinds3} · {again['kind']}"))

# ── AC4. sub_task=None 질의에 되묻기 미발동 ────────────────────────────────
print("\n── AC4. sub_task=None 이면 되묻기 미발동 ──")
CALLS.clear()
NO_ASK = ["예금보험공사가 뭐하는 곳인가요", "가지급금이 뭔가요?", "안녕하세요"]
bad4 = []
for qq in NO_ASK:
    _, ev = run([qq])
    if ev[0]["kind"] != "answer":
        bad4.append((qq, ev[0]["kind"]))
ac4 = not bad4
print(f"  {len(NO_ASK)}건 전부 즉시 답변: {'OK' if ac4 else 'DIFF ⛔'}  (되묻기 발동 {len(bad4)}건)")
for qq, k in bad4:
    print(f"    ✗ {qq} → {k}")
if not ac4:
    fails.append(("AC4", "되묻기 0건", f"{len(bad4)}건 발동"))

# ── AC5. 소관밖·타업무 — 큐폼 미개입 ───────────────────────────────────────
print("\n── AC5. 타업무·소관밖 질의에 큐폼 미개입 ──")
OUT_Q = ["예금보호한도가 얼마인가요?", "채무조정 신청하려면 어떻게 해요?",
         "은닉재산 신고하면 포상금 얼마나 받나요?", "예금보험금은 어떻게 신청하나요?",
         "가지급금이 뭔가요?", "오늘 날씨 어때?"]
bad5 = []
for qq in OUT_Q:
    CALLS.clear()
    _, ev = run([qq])
    sent_q, sent_qform = CALLS[0]
    if ev[0]["kind"] != "answer" or sent_q != qq or any(sent_qform.values()):
        bad5.append((qq, sent_q != qq, {k: v for k, v in sent_qform.items() if v}))
ac5 = not bad5
print(f"  {len(OUT_Q)}건: 되묻기 0 · 검색 쿼리 무변형 · 슬롯 전부 None"
      f"  → {'OK' if ac5 else 'DIFF ⛔'}")
for row in bad5:
    print(f"    ✗ {row}")
print("  (슬롯이 전부 None 이면 attachments 후단 필터가 통과 모드로 동작 — 타 업무 서식 유지)")
if not ac5:
    fails.append(("AC5", "큐폼 미개입", f"{len(bad5)}건 개입"))

# ── AC6. 부스트 OFF 에서 v1 과 답변 입력·첨부 동일 ──────────────────────────
print("\n── AC6. 부스트 OFF — v1 대비 검색 쿼리·슬롯·첨부 동일 ──")


def v1_path(query: str, replies: list[str]) -> tuple[str, dict]:
    """v1(Qform_ver1) 배선 재현 — bf 미주입, next_question 루프, 부스트 없음."""
    slots = {f: v for f, v in extract(query).items() if f in SLOT_FIELDS}
    turns = 0
    while turns < 2:
        nq = qform_state.next_question(slots)
        if nq is None:
            break
        if turns >= len(replies):
            break
        merged = extract(f"{query} {replies[turns]}", business_function="착오송금 반환 신청")
        for f in SLOT_FIELDS:
            if not slots.get(f) and merged.get(f):
                slots[f] = merged[f]
        turns += 1
    return query, slots


CHUNKS = _BASE / "crawler" / "data" / "chunks.jsonl"
MS_DOCS = {"kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn",
           "kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn",
           "kdic-fins-ir-aplygudn-MtrsVstRcptGudn-selectScrn"}
hits = [json.loads(l) for l in CHUNKS.open(encoding="utf-8")
        if json.loads(l)["parent_doc_id"] in MS_DOCS]


def att_key(qform):
    return sorted((a["doc_id"], a["orig_filename"]) for a in attachments.collect(hits, qform=qform))


SCRIPTS = [
    ("착오송금 반환 신청 서류가 뭐예요?", ["본인이 직접 신청해요"]),
    ("착오송금 반환 신청하려는데 필요한 서류 알려주세요", ["대리인이 신청해요", "법인이요"]),
    ("착오송금 반환 신청 서류 알려주세요", ["제가 대신 접수해요", "미성년자 자녀 대신이에요"]),
    ("법인이 잘못 송금했는데 반환 신청 서류가 뭔가요?", []),
    ("착오송금 반환 신청을 철회하고 싶어요", []),
    ("착오송금 반환 요구에 이의제기하고 싶습니다", []),
    ("예금보호한도가 얼마인가요?", []),
    ("채무조정 신청하려면 어떻게 해요?", []),
]
bad6 = []
print(f"  {'질의':44} {'검색쿼리':6} {'슬롯':5} {'첨부':>5}")
for qq, replies in SCRIPTS:
    CALLS.clear()
    run([qq] + replies, boost=False)
    v2_q, v2_slots = CALLS[-1]
    v1_q, v1_slots = v1_path(qq, replies)
    same_q, same_s = v2_q == v1_q, v2_slots == v1_slots
    a1, a2 = att_key(v1_slots), att_key(v2_slots)
    same_a = a1 == a2
    if not (same_q and same_s and same_a):
        bad6.append((qq, same_q, same_s, same_a))
    print(f"  {qq[:44]:44} {'동일' if same_q else '다름✗':6} "
          f"{'동일' if same_s else '다름✗':5} {len(a2):>3}건 {'동일' if same_a else '다름✗'}")
ac6 = not bad6
print(f"  → {'OK' if ac6 else 'DIFF ⛔'}  (첨부는 실제 attachments.collect() 결과 비교)")
if not ac6:
    fails.append(("AC6", "v1 동일", f"{len(bad6)}건 상이"))

# 부스트 ON 은 검색 쿼리만 바뀌고 슬롯·첨부는 그대로여야 한다
CALLS.clear()
run(["착오송금 반환 신청 서류가 뭐예요?", "본인이 직접 신청해요"], boost=True)
b_q, b_slots = CALLS[-1]
CALLS.clear()
run(["착오송금 반환 신청 서류가 뭐예요?", "본인이 직접 신청해요"], boost=False)
o_q, o_slots = CALLS[-1]
print(f"  [부스트 ON] 검색어 \"{b_q}\"")
print(f"             슬롯 {'동일' if b_slots == o_slots else '다름✗'} · "
      f"첨부 {'동일' if att_key(b_slots) == att_key(o_slots) else '다름✗'} (쿼리만 바뀐다)")

# ── AC7. 시험 질의셋 A~G 무크래시 ──────────────────────────────────────────
print("\n── AC7. 시험 질의셋 A~G 무크래시 ──")
QSET = {
    "A": ["착오송금 반환지원 제도가 뭔가요?", "착오송금 반환 신청을 철회하고 싶어요",
          "부당이득반환채권 매입계약을 해제하려면 어떻게 하나요?", "반환금 받을 계좌를 바꾸고 싶어요",
          "위임한 대리인을 다른 사람으로 변경하려면?", "착오송금 반환 요구에 이의제기하고 싶습니다",
          "착오송금 반환하면서 낸 이체수수료 환급받을 수 있나요?"],
    "B": ["착오송금 반환 신청 서류가 뭐예요?"],
    "C": ["착오송금 반환 신청하려는데 필요한 서류 알려주세요", "착오송금 반환 신청 서류 알려주세요"],
    "D": ["법인이 잘못 송금했는데 반환 신청 서류가 뭔가요?",
          "미성년자 자녀 대신 착오송금 반환 신청하려면 뭐가 필요해요?",
          "비법인단체를 대리해서 착오송금 반환 신청하는 서류는?",
          "착오송금 반환 신청 온라인으로 하려는데 서류가 뭐죠?"],
    "E": ["예금보호한도가 얼마인가요?", "채무조정 신청하려면 어떻게 해요?",
          "은닉재산 신고하면 포상금 얼마나 받나요?", "예금보험금은 어떻게 신청하나요?",
          "가지급금이 뭔가요?"],
    "F": ["착오송금 한도가 얼마까지예요?", "착오송금 언제까지 신청해야 하나요?",
          "보이스피싱 당했는데 착오송금 반환지원 신청되나요?",
          "토스로 연락처 송금했는데 반환 신청할 수 있나요?",
          "새마을금고로 잘못 보냈는데 반환지원 되나요?"],
    "G": ["대리인이 방문해서 착오송금 반환 신청할 때 서류는?",
          "미성년자 대신 착오송금 반환 신청 구비서류"],
}
REPLIES = ["대리인이 신청해요", "법인이요"]      # 되묻기가 뜨면 이 대본으로 이어간다
crash, rows7 = [], []
for grp, qs in QSET.items():
    turns = []
    for qq in qs:
        for boost in (False, True):
            for mode in ("template", "llm"):
                try:
                    stub_llm = (lambda m: ("법인, 비법인단체, 미성년자 중 누구를 대리해 "
                                           "신청하시나요?", {"error": None, "calls": 1}))
                    s, evs = run([qq] + REPLIES, boost=boost, ask_mode=mode,
                                 llm_call=stub_llm if mode == "llm" else None)
                    if boost is False and mode == "template":
                        turns.append(sum(1 for e in evs if e["kind"] == "ask"))
                except Exception as e:  # noqa: BLE001
                    crash.append((grp, qq, boost, mode, f"{type(e).__name__}: {e}"))
    rows7.append((grp, len(qs), turns))
print(f"  {'그룹':4} {'질의':>4} {'되묻기 턴 수 (ⓐ·부스트OFF)':30}")
for grp, n, turns in rows7:
    print(f"  {grp:4} {n:>4}건 {str(turns):30}")
ac7 = not crash
combos = sum(len(v) for v in QSET.values()) * 4
print(f"  {combos}조합(질의×부스트2×모드2) 실행 · 예외 {len(crash)}건  → {'OK' if ac7 else 'DIFF ⛔'}")
for c in crash[:5]:
    print(f"    ✗ {c}")
if not ac7:
    fails.append(("AC7", "예외 0", f"{len(crash)}건"))

# ── 판정 ────────────────────────────────────────────────────────────────
print()
if fails:
    print("어긋난 AC ⛔")
    print(f"  {'AC':6} {'기대':26} 실측")
    for ac, want, got in fails:
        print(f"  {ac:6} {want:26} {got}")
    sys.exit(1)
print("전체 통과 ✅  (HCX 콜 0 — answer 스텁 · 첨부는 실제 collect 비교)")
sys.exit(0)
