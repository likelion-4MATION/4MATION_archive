# -*- coding: utf-8 -*-
"""큐폼 멀티턴 전이 검증 — ver3 T1·T2·T3 의 AC 실측. **HCX 콜 0.**

ver2 의 `verify_qform_e2e.py` 는 **단일 질의 안의** 되묻기 전이를 잰다.
이 파일은 그 위층 — **질의와 질의 사이**에서 일어나는 일을 잰다.

    반복질문(T1)   같은 슬롯을 두 번 묻지 않는가          R1~R3
    슬롯 이월(T2)  턴을 넘어 슬롯이 살아남는가 · 오이월 0   C1~C7
    정의형(T3)     개념 질의가 되묻기를 안 맞는가          D1~D8

왜 신규 파일인가 (task_assignment §T4 · CLAUDE.md §0-2):
`verify_qform_e2e.py` 는 **ver2 검증 자산이라 무변경**이다. 멀티턴 AC 를 거기 얹으면
ver2 기준선이 흐려진다. 갈라 두면 "ver2 가 재던 것"과 "ver3 이 새로 재는 것"이 분리된다.

콜 0 을 지키는 법:
- `answer_fn` 을 스텁으로 **주입**한다 → `chain` 이 아예 로드되지 않는다(AC4-1 에서 확인)
- `classify_fn` 은 `rag.classify_query_bf` 를 주입한다 — 결정론 키워드 매칭이라 콜이 아니다
- 첨부는 스텁이 아니라 **실제 `attachments.collect()`** 를 돌린다. 순수 로컬 조인이라
  이월 ON/OFF 첨부 건수를 진짜로 비교할 수 있다(AC2-6)

실행: python3 chatbot/verify_qform_multiturn.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

_BASE = pathlib.Path(__file__).resolve().parent.parent
for _p in (_BASE / "chatbot", _BASE / "crawler"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import qform_trace  # noqa: E402  (rag 상수 로더 — 검색 스택 없는 환경도 통과시킨다)
import attachments  # noqa: E402
import qform_config  # noqa: E402
import qform_flow  # noqa: E402
import qform_state  # noqa: E402
from qform_extract import is_definitional  # noqa: E402

classify_query_bf = qform_trace.rag.classify_query_bf
SL = qform_flow.SLOT_FIELDS
MAX_ASK = qform_config.MAX_ASK_TURNS

# ── 답변 스텁 — 호출 인자를 그대로 기록한다 (콜 0) ────────────────────────────
CALLS: list[tuple[str, dict]] = []

# 첨부 비교용 고정 hits — 착오송금 첨부 보유 3문서의 실제 청크
# (verify_qform_e2e · qform_trace 하니스와 같은 기준. 검색을 타지 않으므로 결정론)
MS_DOCS = {"kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn",
           "kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn",
           "kdic-fins-ir-aplygudn-MtrsVstRcptGudn-selectScrn"}
HITS = [json.loads(l) for l in
        (_BASE / "crawler" / "data" / "chunks.jsonl").open(encoding="utf-8")
        if json.loads(l)["parent_doc_id"] in MS_DOCS]


def stub_answer(query: str, qform: dict) -> dict:
    CALLS.append((query, dict(qform)))
    return {"text": "(스텁 답변)", "sources": [], "confidence": 0.0, "route": "rag",
            "checks": {"ok": True, "flags": []},
            "attachments": attachments.collect(HITS, qform=qform),
            "_meta": {"latency_ms": 0}}


def run(turns: list[tuple[str, list[str]]], *, config=None,
        force_answer: bool = False) -> tuple[dict, list[dict]]:
    """대화 1건 재생. `turns = [(질의, [되묻기 응답…]), …]` — 상태를 **이어서** 굴린다.

    force_answer: 대본이 끝났는데 아직 되묻기 중이면 탈출구를 눌러 답변까지 간다.
        이월 ON/OFF 첨부 건수를 비교하려면 양쪽 다 답변 턴에 닿아야 한다.
    """
    st, out = qform_flow.new_state(), []
    for query, replies in turns:
        asked_seq: list[str] = []
        ask_calls = 0
        ev = qform_flow.start(st, query, classify_fn=classify_query_bf,
                              answer_fn=stub_answer, config=config)
        if ev["kind"] == "ask":
            asked_seq.append(ev["slot"])
            ask_calls += ev["ask"]["calls"]        # ⓐ 템플릿이면 0 이어야 한다
        for r in replies:
            if ev["kind"] != "ask":
                break
            ev = qform_flow.reply(st, r, answer_fn=stub_answer, config=config)
            if ev["kind"] == "ask":
                asked_seq.append(ev["slot"])
                ask_calls += ev["ask"]["calls"]
        pending = ev["kind"] == "ask"
        if pending and force_answer:
            ev = qform_flow.skip(st, answer_fn=stub_answer, config=config)
        result = ev.get("result") or {}
        out.append({
            "q": query, "kind": ev["kind"], "pending": pending, "asked_seq": asked_seq,
            "slots": dict(st["qform"]), "origin": dict(st["slot_origin"]),
            "asked": list(st["asked"]), "ask_turn": st["ask_turn"], "bf": st["bf"],
            "why": st["carryover"], "bypass": st["ask_bypass"],
            "atts": len(result.get("attachments") or []) if ev["kind"] == "answer" else None,
            "ask_calls": ask_calls,
        })
    return st, out


def carried(rec: dict) -> list[str]:
    return [f for f in SL if rec["origin"].get(f) == qform_flow.SRC_CARRY]


def dup(seq: list[str]) -> int:
    return len(seq) - len(set(seq))


def fmt_slots(slots: dict) -> str:
    v = [f"{f}={slots[f]}" for f in SL if slots.get(f)]
    return "{" + ", ".join(v) + "}" if v else "{}"


# ── 판정 적재 ───────────────────────────────────────────────────────────────
ROWS: list[tuple[str, str, str, str, bool]] = []   # (시나리오, AC, 기대, 실측, 통과)


def check(sid: str, ac: str, want: str, got: str, ok: bool) -> None:
    ROWS.append((sid, ac, want, got, bool(ok)))


ATT_ROWS: list[tuple[str, int, int, str]] = []     # (시나리오, OFF, ON, 비고)
OFF = {"SLOT_CARRYOVER": False}

print("━━━ 큐폼 멀티턴 전이 검증 — HCX 콜 0 (answer 스텁 · 첨부는 실제 collect) ━━━")
print(f"조합 테이블 {len(qform_state._COMBOS)}행 · 고정 hits {len(HITS)}청크 · "
      f"MAX_ASK_TURNS={MAX_ASK}\n")

# ══════════════════════════════════════════════════════════════════════════
# R — 반복질문 (T1)
# ══════════════════════════════════════════════════════════════════════════
Q_DOC = "착오송금 반환 신청 서류가 뭐예요?"
Q_DOC2 = "착오송금 반환 신청하려는데 필요한 서류 알려주세요"

# R1 — 되묻기에 무관한 답변. 같은 슬롯을 다시 묻지 않고 진행해야 한다.
_, r1 = run([(Q_DOC, ["날씨가 좋네요"])])
check("R1", "AC1-1", "재질문 0", f"재질문 {dup(r1[0]['asked_seq'])}",
      dup(r1[0]["asked_seq"]) == 0 and r1[0]["kind"] == "answer")

# R2 — 3턴 연속 무응답성 답변. 상한 안에서 답변에 도달해야 한다.
_, r2 = run([(Q_DOC, ["글쎄요", "잘 모르겠어요", "음"])])
ok_r2 = (r2[0]["kind"] == "answer" and r2[0]["ask_turn"] <= MAX_ASK
         and dup(r2[0]["asked_seq"]) == 0)
check("R2", "AC1-2", f"답변 도달 · 턴≤{MAX_ASK}",
      f"{r2[0]['kind']} · 턴 {r2[0]['ask_turn']} · 재질문 {dup(r2[0]['asked_seq'])}", ok_r2)

# R3 — 물을 슬롯을 전부 소진하면 답변 턴으로 진입한다.
_, r3 = run([(Q_DOC2, ["대리인이 신청해요", "글쎄요", "모르겠어요"])])
ok_r3 = (r3[0]["asked"] == ["qualification", "subject"] and r3[0]["kind"] == "answer"
         and dup(r3[0]["asked_seq"]) == 0)
check("R3", "AC1-1·2", "asked 2종 소진→답변",
      f"asked={r3[0]['asked']} · {r3[0]['kind']}", ok_r3)

# ══════════════════════════════════════════════════════════════════════════
# C — 슬롯 이월 (T2)
# ══════════════════════════════════════════════════════════════════════════
CONFIRM = (Q_DOC, ["대리인이 신청해요", "법인이요"])          # 되묻기 2턴으로 확정되는 선행 턴

# C1 — 동일 업무 2턴. 직전 확정 슬롯이 유지된다.
_, c1_on = run([CONFIRM, ("온라인으로 신청하려면요?", [])], force_answer=True)
_, c1_off = run([CONFIRM, ("온라인으로 신청하려면요?", [])], config=OFF, force_answer=True)
check("C1", "AC2-1", "이월 ≥1", f"이월 {carried(c1_on[1])}", bool(carried(c1_on[1])))
ATT_ROWS.append(("C1", c1_off[1]["atts"], c1_on[1]["atts"], "동일 업무 후속(온라인)"))

# C2 — 되묻기 확정 → 후속 질의. 슬롯 유지 + 첨부 좁힘.
_, c2_on = run([(Q_DOC2, ["대리인이 신청해요", "법인이요"]), ("그럼 준비물은요?", [])],
               force_answer=True)
_, c2_off = run([(Q_DOC2, ["대리인이 신청해요", "법인이요"]), ("그럼 준비물은요?", [])],
                config=OFF, force_answer=True)
ok_c2 = bool(carried(c2_on[1])) and c2_on[1]["atts"] < c2_off[1]["atts"]
check("C2", "AC2-1·6", "이월 ≥1 · 첨부 ON<OFF",
      f"이월 {len(carried(c2_on[1]))}개 · 첨부 {c2_off[1]['atts']}→{c2_on[1]['atts']}", ok_c2)
ATT_ROWS.append(("C2", c2_off[1]["atts"], c2_on[1]["atts"], "확정 후 후속(준비물)"))

# C3 — 업무 전환(착오송금 → 미수령금). 오이월이 있으면 답이 정반대로 나간다(§2-3).
_, c3 = run([CONFIRM, ("미수령금은 어떻게 찾나요?", [])], force_answer=True)
check("C3", "AC2-2", "오이월 0",
      f"오이월 {len(carried(c3[1]))} · {c3[1]['why']}", not carried(c3[1]))

# C4 — 착오송금 → 소관 밖 → 착오송금. 잡담 턴에도 복귀 턴에도 오이월이 없어야 한다.
_, c4 = run([CONFIRM, ("오늘 날씨 어때?", []), (Q_DOC, [])], force_answer=True)
ok_c4 = not carried(c4[1]) and not carried(c4[2])
check("C4", "AC2-2", "오이월 0 (2턴)",
      f"소관밖 {len(carried(c4[1]))} · 복귀 {len(carried(c4[2]))}", ok_c4)

# C5 — 이월 상태에서 슬롯 정정. **신규 추출이 이월값을 항상 이긴다.**
_, c5 = run([CONFIRM, ("미성년자 자녀 대신이면 서류가 뭔가요?", [])], force_answer=True)
ok_c5 = (c5[0]["slots"]["subject"] == "법인"
         and c5[1]["slots"]["subject"] == "미성년자"
         and c5[1]["origin"]["subject"] == qform_flow.SRC_NEW)
check("C5", "AC2-3", "법인→미성년자(신규)",
      f"{c5[0]['slots']['subject']}→{c5[1]['slots']['subject']}"
      f"({c5[1]['origin']['subject']})", ok_c5)

# C6 — TTL 초과. 기본 TTL=2 → 설정 후 2턴까지 살고 3번째 후속에서 끊긴다.
FU = ("그럼 준비물은요?", [])
_, c6 = run([CONFIRM, FU, FU, FU], force_answer=True)
seq6 = [rec["origin"].get("subject") for rec in c6]
ok_c6 = seq6 == [qform_flow.SRC_NEW, qform_flow.SRC_CARRY,
                 qform_flow.SRC_CARRY, qform_flow.SRC_EMPTY]
check("C6", "AC2-4", f"TTL={qform_config.CARRYOVER_TTL} 후 만료",
      " → ".join(s or "-" for s in seq6), ok_c6)

# C7 — 이월 OFF 회귀. ver2 `start()` 는 상태를 통째로 덮었으므로
#      "멀티턴 OFF" 는 "매 턴 새 상태로 시작" 과 결과가 같아야 한다.
REG = [(Q_DOC, ["대리인이 신청해요", "법인이요"]),
       ("온라인으로 신청하려면요?", []),
       ("예금보호한도가 얼마인가요?", []),
       ("그럼 법인은요?", []),
       ("착오송금 반환 신청을 철회하고 싶어요", []),
       ("오늘 날씨 어때?", [])]
CALLS.clear()
_, c7_seq = run(REG, config=OFF, force_answer=True)
c7_calls = list(CALLS)
c7_fresh, fresh_calls = [], []
for turn in REG:                                   # 매 턴 새 상태 = ver2 동작
    CALLS.clear()
    _, one = run([turn], force_answer=True)
    c7_fresh.append(one[0]["slots"])
    fresh_calls.extend(CALLS)
ok_c7 = [r["slots"] for r in c7_seq] == c7_fresh and c7_calls == fresh_calls
check("C7", "AC2-5", "ver2 등가 (슬롯·인자)",
      f"슬롯 {'동일' if [r['slots'] for r in c7_seq] == c7_fresh else '상이'} · "
      f"answer 인자 {'동일' if c7_calls == fresh_calls else '상이'}", ok_c7)

# ══════════════════════════════════════════════════════════════════════════
# D — 정의형 예외 (T3)
# ══════════════════════════════════════════════════════════════════════════
DEF_Q = {
    "D1": "부당이득반환채권이 뭐예요?",
    "D2": "착오송금이란 무엇인가요?",
    "D3": "가지급금이 뭔가요?",
    "D4": "예금자보호제도란 무엇인가요?",
    "D5": "비법인단체가 뭔가요?",
}
for sid, q in DEF_Q.items():
    _, d = run([(q, [])])
    ok = d[0]["kind"] == "answer" and d[0]["bypass"] == qform_flow.BYPASS_DEFINITIONAL
    check(sid, "AC3-1", "되묻기 0 · 우회",
          f"{d[0]['kind']} · {d[0]['bypass']}", ok)

# D6~D8 — "얼마"·"언제까지"는 정의형이 아니다. 여기서 오판하면 제도안내 어휘가
#          통째로 우회에 딸려 들어가 스코프 게이트가 무력화된다(CLAUDE.md §3).
CTR_Q = {
    "D6": "착오송금 한도가 얼마까지예요?",
    "D7": "착오송금 언제까지 신청해야 하나요?",
    "D8": "이체수수료 환급이 얼마나 되나요?",
}
for sid, q in CTR_Q.items():
    _, d = run([(q, [])])
    ok = not is_definitional(q) and d[0]["bypass"] is None
    check(sid, "AC3-4", "정의형 아님",
          f"정의형={is_definitional(q)} · bypass={d[0]['bypass']}", ok)

# ══════════════════════════════════════════════════════════════════════════
# E — 슬롯 칩 수정 (T6)
# ══════════════════════════════════════════════════════════════════════════
# E1 — 해제하면 되묻기가 **다시 뜬다**. 안 뜨면 "보이지만 고칠 수 없다"가 그대로다.
CALLS.clear()
st_e, _ = run([CONFIRM], force_answer=True)
before_e = dict(st_e["qform"])
turn_before, asked_before = st_e["ask_turn"], list(st_e["asked"])
ans_before = len(CALLS)
ev_e = qform_flow.edit(st_e, "subject", None)
ok_e1 = (ev_e["kind"] == "ask" and ev_e["slot"] == "subject"
         and st_e["qform"]["subject"] is None and before_e["subject"] == "법인")
check("E1", "AC6-1", "해제→되묻기 재발동",
      f"subject {before_e['subject']}→{st_e['qform']['subject']} · {ev_e['kind']}"
      f"({ev_e.get('slot')})", ok_e1)

# E2 — 해제한 슬롯이 `asked` 에서 빠지고, **상한에 닿아 있던 대화가 다시 물을 수 있다.**
#      해제 직전 ask_turn 은 상한(2)이었다. `edit` 이 턴을 하나 무르지 않으면
#      `_try_ask` 가 상한에 걸려 None 을 내고, 해제해도 영영 안 물어본다.
#      (해제 후 곧바로 재질문이 나가며 ask_turn 이 다시 +1 되므로 최종값은 2 다)
ok_e2 = ("subject" in asked_before and "subject" not in st_e["asked"]
         and turn_before == MAX_ASK and st_e["pending_slot"] == "subject"
         and st_e["ask_turn"] <= MAX_ASK)
check("E2", "AC6-2", "asked 정리 · 상한서 재질문",
      f"asked {asked_before}→{st_e['asked']} · 턴 {turn_before}(상한)→{st_e['ask_turn']} · "
      f"pending={st_e['pending_slot']}", ok_e2)

# E3 — `edit()` 은 answer() 를 부르지 않는다. 칩을 만질 때마다 예산이 새면 안 된다.
ok_e3 = len(CALLS) == ans_before and "chain" not in sys.modules
check("E3", "AC6-5", "edit() HCX 콜 0",
      f"answer() 추가 호출 {len(CALLS) - ans_before}회 · chain 로딩={'chain' in sys.modules}",
      ok_e3)

# E4 — 되물을 것이 없으면 'ready' 로 멈춘다(자동 재생성 안 함). 재답변은 명시 요청으로만.
st_r, _ = run([CONFIRM], force_answer=True)
n_before = len(CALLS)
ev_r = qform_flow.edit(st_r, "method", "온라인")     # 값 설정 → 되물을 것이 없다
ok_e4 = (ev_r["kind"] == "ready" and st_r["qform"]["method"] == "온라인"
         and len(CALLS) == n_before)
ev_rr = qform_flow.answer_now(st_r, answer_fn=stub_answer)   # 사용자가 명시로 요청
ok_e4 &= ev_rr["kind"] == "answer" and len(CALLS) == n_before + 1
check("E4", "AC6-5", "ready→명시 재답변",
      f"{ev_r['kind']} · 자동생성 0회 · answer_now 후 {len(CALLS) - n_before}회", ok_e4)

# E5 — 해제한 슬롯을 **버튼으로 다시 고를 수 있다**(T5 선택지가 살아 있는가).
opts_e = qform_flow.options(st_e)
ok_e5 = bool(opts_e) and "법인" in opts_e
check("E5", "AC6-2", "해제 후 선택지 복구",
      f"{len(opts_e)}개 · 법인 포함={'법인' in opts_e}", ok_e5)

# ══════════════════════════════════════════════════════════════════════════
# AC4-1 — HCX 콜 0 확인
# ══════════════════════════════════════════════════════════════════════════
chain_loaded = "chain" in sys.modules
ask_llm_calls = 0
for turns in ([(Q_DOC2, ["대리인이 신청해요", "법인이요"])],):
    _, probe = run(turns)
    ask_llm_calls += sum(r["ask_calls"] for r in probe)
check("콜회계", "AC4-1", "chain 미로딩 · 되묻기 콜 0",
      f"chain 로딩={chain_loaded} · 되묻기 LLM 콜 {ask_llm_calls}",
      not chain_loaded and ask_llm_calls == 0)

# ══════════════════════════════════════════════════════════════════════════
# 출력
# ══════════════════════════════════════════════════════════════════════════
print("━━━ 멀티턴 전이 검증 (HCX 콜 0) ━━━")
print(f"  {'시나리오':8} {'대상 AC':9} {'기대':24} {'실측':46} 판정")
for sid, ac, want, got, ok in ROWS:
    print(f"  {sid:8} {ac:9} {want:24} {got:46} {'✅' if ok else '⛔'}")
passed = sum(1 for *_, ok in ROWS if ok)
print(f"\n  {passed}/{len(ROWS)} 통과")

print("\n━━━ 첨부 건수 — 이월 ON/OFF 병기 ━━━")
print(f"  {'시나리오':8} {'OFF':>5} {'ON':>5}  비고")
for sid, off, on, note in ATT_ROWS:
    print(f"  {sid:8} {off:>5} {on:>5}  {note}")
print("  (검색을 바꾸지 않았으므로 450셋 회귀 대상이 아니다 — 동작 확인용 병기: §0-2·R3)")

print("\n━━━ 이월 사유 (결정론) ━━━")
for sid, recs in (("C1", c1_on), ("C3", c3), ("C4", c4), ("C6", c6)):
    for i, rec in enumerate(recs[1:], 2):
        print(f"  {sid} {i}턴  bf={str(rec['bf'])[:18]:20} {rec['why']}")

# 재실행 동일성(AC4-4) 확인용 지문 — 두 번 돌려 이 값이 같으면 결정론이다.
fp = hashlib.sha256(
    "\n".join(f"{s}|{a}|{w}|{g}|{o}" for s, a, w, g, o in ROWS).encode("utf-8")
).hexdigest()[:16]
print(f"\n  결과 지문 sha256 {fp}  (AC4-4: 재실행 시 동일해야 한다)")

fails = [(s, a, w, g) for s, a, w, g, ok in ROWS if not ok]
print()
if fails:
    print("어긋난 AC ⛔")
    print(f"  {'시나리오':8} {'AC':9} {'기대':24} 실측")
    for s, a, w, g in fails:
        print(f"  {s:8} {a:9} {w:24} {g}")
    sys.exit(1)
print(f"전체 통과 ✅  ({passed}/{len(ROWS)} · HCX 콜 0 — answer 스텁 · 첨부는 실제 collect)")
sys.exit(0)
