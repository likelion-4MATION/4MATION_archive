# -*- coding: utf-8 -*-
"""큐폼 대화 상태 전이 — T4 E2E 배선의 코어.

**streamlit 을 모른다.** 화면(app.py)은 렌더와 토글만 맡고, "지금 되물을 것인가 /
답할 것인가"는 전부 여기서 결정한다. 갈라둔 이유는 두 가지다 —
① 전이 규칙을 UI 없이 실측할 수 있다(`verify_qform_e2e.py`, HCX 콜 0)
② 트레이스(T5)가 화면이 아니라 이 층의 반환값에서 조립된다.

흐름 (task_assignment T4-2):

    사용자 입력
      → bf = classify_query_bf(q)          [1회 · MoAI 라우터 주입점]
      → slots = extract(q, business_function=bf)
      → next_question(slots)
          ├ None  → answer(query, qform=slots)        ← 되묻기 종료
          └ 있음  → build_question(mode) 만 하고 **answer() 를 부르지 않는다**
      → 응답을 빈 슬롯에만 반영, 최대 2턴 후 강제 진행

계약:
- **되묻기 턴에는 `answer()` 를 부르지 않는다.** ⓐ 모드 2턴 대화의 HCX 콜은 생성 1콜뿐이다.
- 탈출구(`skip`)는 되묻기 판정을 건너뛰고 곧장 답한다. 슬롯은 유지한 채로 —
  안 좁힌 슬롯은 첨부를 **넓게** 남길 뿐 좁히지 않아 안전하다(graceful degradation).
- **한 번 물은 슬롯은 다시 묻지 않는다(ver3 T1).** 응답이 슬롯을 못 채워도 이력
  `state["asked"]` 에 남겨 후보에서 빼므로, 답을 못 얻은 슬롯에 대화가 갇히지 않는다.
  `asked` 는 슬롯 **값이 아니라 대화 이력**이라 `qform` 밖 최상위 키로 둔다 —
  `_clean()` 을 거치지 않으니 `answer()` 로 새어 나가지 않는다.
- 부스트는 **검색 쿼리에만** 붙는다. 슬롯·업무 판정은 원 질의 기준 그대로다.
"""
from __future__ import annotations

import pathlib
import sys

_BASE = pathlib.Path(__file__).resolve().parent.parent
for _p in (_BASE / "chatbot", _BASE / "crawler"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import qform_ask  # noqa: E402
import qform_state  # noqa: E402
from qform_extract import IN_SCOPE_BF, extract  # noqa: E402

MAX_ASK_TURNS = 2          # D2: 되묻기 상한
SLOT_FIELDS = qform_state.SLOT_FIELDS


def new_state() -> dict:
    """대화 상태 1건. app 은 이걸 `st.session_state` 에 넣어 들고 다닌다."""
    return {"qform": {f: None for f in SLOT_FIELDS},   # 슬롯
            "ask_turn": 0,                             # 되묻기 턴 수 (최대 2)
            "pending_slot": None,                      # 지금 묻고 있는 슬롯
            "asked": [],                               # 물어본 슬롯 이력 (ver3 T1)
            "bf": None,                                # 1회 계산한 업무 판정
            "base_q": None,                            # 원 질의 (되묻기 병합의 기준)
            "slots_raw": None}                         # extract() 원본(_hits·_scope 보존)


def _default_classify(query: str):
    from rag import classify_query_bf        # 지연 임포트 — 검색 스택 없이도 모듈은 로드된다
    return classify_query_bf(query)


def _default_answer(query: str, qform: dict):
    import chain                             # 지연 임포트 — 되묻기 턴에는 여기까지 오지 않는다
    return chain.answer(query, qform=qform)


def _clean(slots: dict) -> dict:
    """추출기 부가키(_hits/_bf/_scope) 제거 — answer()·survivors() 에 넘길 순수 슬롯."""
    return {f: slots.get(f) for f in SLOT_FIELDS}


def _mark_asked(state: dict, slot) -> None:
    """물어본 슬롯을 이력에 적재. 순서 유지 · 중복 없음."""
    if slot and slot not in state.setdefault("asked", []):
        state["asked"].append(slot)


def start(state: dict, query: str, *, ask_mode: str = "template", boost: bool = False,
          classify_fn=None, answer_fn=None, llm_call=None) -> dict:
    """새 질의 진입. 업무 판정을 **1회** 계산해 추출기에 주입한다(E3)."""
    bf = (classify_fn or _default_classify)(query)
    slots = extract(query, business_function=bf)
    state.update({"bf": bf, "base_q": query, "qform": _clean(slots),
                  "slots_raw": slots, "ask_turn": 0, "pending_slot": None,
                  "asked": []})          # 새 질의 = 새 되묻기 이력
    return _step(state, ask_mode=ask_mode, boost=boost,
                 answer_fn=answer_fn, llm_call=llm_call)


def reply(state: dict, text: str, *, ask_mode: str = "template", boost: bool = False,
          answer_fn=None, llm_call=None) -> dict:
    """되묻기 응답 반영. **빈 슬롯만 채운다** — 이미 확정된 값을 덮어쓰지 않는다.

    후속 답변("대리인이요")만으로는 스코프 게이트에 걸리므로 원 질의와 합쳐
    업무를 명시로 넘긴다. 되묻기는 sub_task 가 잡혔을 때만 발동하므로 이 시점의
    업무는 착오송금으로 확정돼 있다.

    **슬롯이 채워졌든 아니든 물었던 슬롯은 `asked` 에 적재한다(T1).** 못 채웠을 때
    적재하는 쪽이 핵심이다 — 채워진 슬롯은 `next_question` 이 어차피 안 고르지만,
    못 채운 슬롯은 조건이 그대로라 같은 질문이 무한히 재발동한다.
    """
    merged = extract(f"{state['base_q']} {text}", business_function=IN_SCOPE_BF)
    for f in SLOT_FIELDS:
        if not state["qform"].get(f) and merged.get(f):
            state["qform"][f] = merged[f]
    state["slots_raw"] = merged
    _mark_asked(state, state.get("pending_slot"))
    return _step(state, ask_mode=ask_mode, boost=boost,
                 answer_fn=answer_fn, llm_call=llm_call)


def skip(state: dict, *, boost: bool = False, answer_fn=None) -> dict:
    """탈출구 — 되묻기 판정을 건너뛰고 **즉시** 답한다. 슬롯은 유지."""
    state["pending_slot"] = None
    state["ask_turn"] = MAX_ASK_TURNS        # 이후 재발동 차단
    return _finalize(state, boost=boost, answer_fn=answer_fn)


def _step(state: dict, *, ask_mode: str, boost: bool, answer_fn, llm_call) -> dict:
    """되묻기 판정 → 분기. 턴 상한에 닿거나 **물을 슬롯이 동나면** 미채움이어도 진행한다.

    `asked` 제외 후 후보가 없으면 `next_question` 이 None 을 돌려주므로,
    `MAX_ASK_TURNS` 도달과 **같은 경로**로 답변 턴에 들어간다(T1-④).
    """
    nq = (qform_state.next_question(state["qform"], exclude=set(state.get("asked") or ()))
          if state["ask_turn"] < MAX_ASK_TURNS else None)
    if nq is None:
        state["pending_slot"] = None
        return _finalize(state, boost=boost, answer_fn=answer_fn)

    surv = qform_state.survivors(state["qform"])
    ask = qform_ask.build_question(nq["slot"], state["qform"], surv,
                                   mode=ask_mode, llm_call=llm_call)
    state["ask_turn"] += 1
    state["pending_slot"] = nq["slot"]
    return {"kind": "ask", "slot": nq["slot"], "prompt": ask["text"],
            "remaining": nq["remaining"], "turn": state["ask_turn"],
            "survivors": surv, "ask": ask}


def _finalize(state: dict, *, boost: bool, answer_fn) -> dict:
    """검색·생성. 부스트가 켜져 있으면 슬롯을 **검색 쿼리에만** 직렬화해 덧붙인다."""
    slots = dict(state["qform"])
    search_q, boosted = state["base_q"], None
    if boost:
        extra = qform_state.serialize(slots)
        if extra:
            search_q = f"{state['base_q']} {extra}"
            boosted = search_q
    result = (answer_fn or _default_answer)(search_q, slots)
    return {"kind": "answer", "result": result, "slots": slots,
            "search_q": search_q, "boosted": boosted,
            "survivors": qform_state.survivors(slots)}
