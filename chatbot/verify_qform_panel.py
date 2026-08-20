# -*- coding: utf-8 -*-
"""메모리 패널 검증 — ver4 M3 (A3-1 ~ A3-9). **HCX 콜 0.**

streamlit 렌더는 눈으로만 확인되므로, 상태 전이·화면 모델을 **UI 없이 호출 가능한
순수 함수**로 갈라 두고 여기서 실측한다(`qform_memory_panel.panel_model` / `apply`).
렌더(`app.py`)는 이 모델을 그리기만 하는 얇은 층이다.

`answer()` 호출 횟수를 전부 센다 — A3-2·A3-6·A3-8 이 여기 걸린다.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

_BASE = pathlib.Path(__file__).resolve().parent.parent
for _p in (_BASE / "chatbot", _BASE / "crawler"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import qform_ask  # noqa: E402
import qform_config  # noqa: E402
import qform_flow  # noqa: E402
import qform_memory_panel as P  # noqa: E402
import qform_state  # noqa: E402
import qform_trace  # noqa: E402

classify_query_bf = qform_trace.rag.classify_query_bf
SL = qform_flow.SLOT_FIELDS
CALLS: list = []


def answer_fn(query, qform):
    CALLS.append((query, dict(qform)))
    return {"text": "(스텁)", "sources": [], "confidence": 0.0, "route": "rag",
            "checks": {"ok": True, "flags": []}, "attachments": [],
            "_meta": {"latency_ms": 0}}


ROWS: list[tuple[str, str, str, bool]] = []


def check(ac: str, want: str, got: str, ok: bool) -> None:
    ROWS.append((ac, want, got, bool(ok)))


def confirmed(q="착오송금 반환 신청 서류가 뭐예요?", replies=("대리인이 신청해요", "법인이요")):
    st = qform_flow.new_state()
    qform_flow.start(st, q, classify_fn=classify_query_bf, answer_fn=answer_fn)
    for r in replies:
        qform_flow.reply(st, r, answer_fn=answer_fn)
    return st


print("━━━ 메모리 패널 검증 — HCX 콜 0 (answer 스텁) ━━━")
print(f"TTL={qform_config.CARRYOVER_TTL} · MAX_ASK_TURNS={qform_config.MAX_ASK_TURNS} · "
      f"MAX_QUEUE={qform_config.MAX_QUEUE}\n")

# ── A3-1. 3구역 렌더 · 라벨이 명세 문구와 일치 ────────────────────────────
st = confirmed()
model = P.panel_model(st)
names = [z["name"] for z in model["zones"]]
ok1 = names == ["적용 중", "기억만 함", "대기 중인 용건"]
check("A3-1", "구역 3개 · 명세 문구 일치", f"{names}", ok1)

# 표시하는 모든 항목에 '고치면 무엇이 바뀌는가' 가 붙어 있는가
eff = P.effect_table(st)
ok1b = all(e for _, _, e, _ in eff)
check("A3-1b", "전 항목에 effect 표기", f"{len(eff)}개 항목 · 누락 {sum(1 for _,_,e,_ in eff if not e)}건", ok1b)

# ── A3-2. X = 오염 차단 (재발동 0 · asked/ask_turn 무변동 · answer() 0회) ──
st2 = confirmed()
before_asked, before_turn = list(st2["asked"]), st2["ask_turn"]
n0 = len(CALLS)
ev = P.apply(st2, "clear", field="subject")
ok2 = (ev["kind"] == "ready" and st2["pending_slot"] is None
       and st2["qform"]["subject"] is None
       and st2["asked"] == before_asked and st2["ask_turn"] == before_turn
       and len(CALLS) == n0)
check("A3-2", "X → 재발동 0 · asked·턴 무변동 · answer() 0회",
      f"{ev['kind']} · pending={st2['pending_slot']} · asked {before_asked}→{st2['asked']} · "
      f"턴 {before_turn}→{st2['ask_turn']} · answer() {len(CALLS)-n0}회", ok2)

# ── A3-3. pass = 재질문 차단 ──────────────────────────────────────────────
st3 = qform_flow.new_state()
ev3 = qform_flow.start(st3, "착오송금 반환 신청 서류가 뭐예요?",
                       classify_fn=classify_query_bf, answer_fn=answer_fn)
asked_slot = ev3.get("slot")
n0 = len(CALLS)
P.apply(st3, "pass", field=asked_slot)
nq = qform_state.next_question(st3["qform"], exclude=set(st3["asked"]))
ok3 = (asked_slot in st3["asked"] and asked_slot in st3["passed"]
       and (nq is None or nq["slot"] != asked_slot) and len(CALLS) == n0)
check("A3-3", "pass → 해당 슬롯 재질문 0",
      f"pass({asked_slot}) · asked={st3['asked']} · 다음 질문={nq['slot'] if nq else None} · "
      f"answer() {len(CALLS)-n0}회", ok3)

# ── A3-4. TTL=3 이월 3턴 생존 · 만료 항목 회색 잔류(삭제 0) ───────────────
TTL = qform_config.CARRYOVER_TTL
st4 = confirmed()
origins = []
for _ in range(TTL + 1):
    qform_flow.start(st4, "그럼 준비물은요?", classify_fn=classify_query_bf, answer_fn=answer_fn)
    origins.append(st4["slot_origin"].get("subject"))
m4 = P.panel_model(st4)
item = next((i for z in m4["zones"] if z["name"] == "적용 중"
             for i in z["items"] if i["field"] == "subject"), None)
ok4 = (origins[:TTL - 1] == [qform_flow.SRC_CARRY] * (TTL - 1)
       and origins[-1] == qform_flow.SRC_EMPTY
       and item is not None and item["status"] == P.ST_EXPIRED
       and item["value"] == "법인" and item["actionable"] is False)
check("A3-4", f"TTL={TTL} 이월 생존 · 만료 회색 잔류(삭제 0)",
      f"origin {origins} · 패널 subject={item and item['value']}"
      f"({item and item['status']}) 잔류={item is not None}", ok4)

# ── A3-5. 업무 전환 → '이 업무엔 적용 안 됨' · 오이월 0 ────────────────────
st5 = confirmed()
qform_flow.start(st5, "예금보험금 신청 서류가 뭐예요?", classify_fn=lambda q: "예금보험금 안내",
                 answer_fn=answer_fn)
m5 = P.panel_model(st5)
party = next((i for z in m5["zones"] if z["name"] == "적용 중"
              for i in z["items"] if i["field"] == "party"), None)
mis = [f for f in SL if st5["qform"].get(f) and f not in P.used_slots(st5["bf"])]
ok5 = (st5["bf"] == "예금보험금 안내"
       and "party" not in P.used_slots("예금보험금 안내")
       and (party is None or party["status"] == P.ST_NOT_APPLICABLE)
       and not mis)
check("A3-5", "업무 전환 표기 · 오이월 0",
      f"bf={st5['bf']} · 노출축={P.used_slots(st5['bf'])} · "
      f"party항목={party and party['status']} · 오이월 {len(mis)}건", ok5)

# ── A3-6. 다중 의도 → 큐 적재 · answer() 1회 · 반환 4필드 무변경 ──────────
CALLS.clear()
st6 = qform_flow.new_state()
ev6 = qform_flow.start(st6, "이의제기 방법이랑 수령계좌 변경도 같이 알려주세요",
                       classify_fn=classify_query_bf, answer_fn=answer_fn)
res = ev6.get("result") or {}
FIELDS4 = {"text", "sources", "confidence", "route"}
ok6 = (len(st6["queue"]) >= 1 and len(CALLS) == 1
       and FIELDS4 <= set(res) and ev6["kind"] == "answer")
check("A3-6", "큐 적재 · answer() 1회 · 4필드 무변경",
      f"큐 {len(st6['queue'])}건({[q['sub_task'] for q in st6['queue']]}) · "
      f"answer() {len(CALLS)}회 · 4필드 {sorted(FIELDS4 & set(res))}", ok6)

# 큐 조작 — ✏️ 순서 변경 / ❌ 제외
P.enqueue(st6, [{"sub_task": "신청철회", "bf": st6["bf"], "text": "x"}])
q_before = [q["sub_task"] for q in st6["queue"]]
P.apply(st6, "move", index=0, delta=1)
q_moved = [q["sub_task"] for q in st6["queue"]]
P.apply(st6, "drop", index=0)
ok6b = q_moved == list(reversed(q_before)) and len(st6["queue"]) == len(q_before) - 1
check("A3-6b", "큐 ✏️순서변경 · ❌제외",
      f"{q_before} → move {q_moved} → drop {[q['sub_task'] for q in st6['queue']]}", ok6b)

# ── A3-7. 업무 교차 → 순서 되묻기 · '나눠서 안내드릴게요' ──────────────────
CROSS = "착오송금 신청했는데 그 은행이 파산하면 예금자보호 한도는 어떻게 되나요?"
det = P.detect_intents(CROSS, score_fn=P.bf_scores)
prompt = P.cross_prompt(det["bfs"])
ok7 = det["kind"] == "cross" and "나눠서 안내드릴게요" in prompt and len(det["bfs"]) >= 2
check("A3-7", "교차 감지 · 문구에 '나눠서 안내드릴게요'",
      f"kind={det['kind']} · bfs={det['bfs']} · 문구포함={'나눠서 안내드릴게요' in prompt}", ok7)

# ── A3-8. [이대로 답변받기] — 즉시 답변 · 재발동 없음 ─────────────────────
CALLS.clear()
st8 = qform_flow.new_state()
ev8 = qform_flow.start(st8, "착오송금 반환 신청 서류가 뭐예요?",
                       classify_fn=classify_query_bf, answer_fn=answer_fn)
was_ask = ev8["kind"] == "ask"
ev8b = qform_flow.skip(st8, answer_fn=answer_fn)
ev8c = qform_flow.edit(st8, "method", "온라인")
ok8 = (was_ask and ev8b["kind"] == "answer" and len(CALLS) == 1
       and st8["pending_slot"] is None and ev8c["kind"] == "ready")
check("A3-8", "즉시 답변 · 되묻기 재발동 없음",
      f"ask→{ev8b['kind']} · answer() {len(CALLS)}회 · 이후 pending={st8['pending_slot']}", ok8)

# ── A3-9. 선택지 버튼 값이 조합 테이블 밖으로 안 나감 ─────────────────────
outside = []
for combos, tag in ((qform_state._COMBOS, "MSDR"),
                    (P._load_tables().get("예금보험금 안내") or [], "DPIN")):
    allowed = {f: set() for f in SL}
    for c in combos:
        for f in SL:
            allowed[f] |= qform_state._toks(c[f])
    for f in SL:
        vals = qform_ask.survivor_values(f, combos)
        outside += [(tag, f, v) for v in vals if v not in allowed[f]]
ok9 = not outside
check("A3-9", "버튼 값 ⊆ 조합 테이블", f"테이블 밖 값 {len(outside)}건", ok9)

# ── 화면 모델 — '고치면 무엇이 바뀌는가' 표 ────────────────────────────────
print("── 패널 항목 · 고치면 무엇이 바뀌는가 ──")
print(f"  {'구역':12} {'항목':14} {'고치면 바뀌는 것':28} 정말 바뀌나")
for zone, label, effect, act in P.effect_table(st6):
    print(f"  {zone:12} {label:14} {effect:28} {'○' if act else '× (회색)'}")

print("\n── 판정 ──")
print(f"  {'AC':7} {'기대':40} {'실측':58} 판정")
for ac, want, got, ok in ROWS:
    print(f"  {ac:7} {want[:40]:40} {got[:58]:58} {'✅' if ok else '⛔'}")
n_ok = sum(1 for *_, ok in ROWS if ok)
print(f"\n  {n_ok}/{len(ROWS)} 통과")

fp = hashlib.sha256("\n".join(f"{a}|{w}|{g}|{o}" for a, w, g, o in ROWS)
                    .encode("utf-8")).hexdigest()[:16]
print(f"  결과 지문 sha256 {fp}")

bad = [r for r in ROWS if not r[3]]
print()
if bad:
    print("어긋난 AC ⛔")
    for ac, want, got, _ in bad:
        print(f"  {ac:7} 기대 {want} · 실측 {got}")
    sys.exit(1)
print(f"전체 통과 ✅  (answer() 스텁 · HCX 콜 0 · chain 로딩={'chain' in sys.modules})")
sys.exit(0)
