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
- **턴 간 슬롯 이월(ver3 T2).** 새 질의에서 못 채운 슬롯을 직전 턴 값으로 메운다.
  LLM 히스토리 주입이 아니라 **상태 재사용**이라 콜이 늘지 않는다. 업무가 바뀌면
  막고(§2-3), 신규 추출이 항상 이월을 이기며, 막히면 슬롯이 비어 첨부가 넓어질 뿐이다.
  정책 값은 `qform_config` 가 소유한다 — 전이 코드를 안 고치고 값만 바꾸기 위해서다.
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
import qform_config  # noqa: E402
import qform_state  # noqa: E402
from qform_extract import IN_SCOPE_BF, extract, in_scope, is_definitional  # noqa: E402

# D2: 되묻기 상한. **값의 주인은 `qform_config` 로 옮겼고(ver3 T2) 이 이름은 별칭이다.**
# `verify_docs.py` 가 `qform_flow.MAX_ASK_TURNS` 를 읽으므로 이름을 없애지 않는다.
MAX_ASK_TURNS = qform_config.MAX_ASK_TURNS
SLOT_FIELDS = qform_state.SLOT_FIELDS

# 슬롯 출처 표기 (트레이스 노출용 — T2)
SRC_NEW, SRC_CARRY, SRC_EMPTY = "신규", "이월", "미채움"

# 되묻기 우회 사유 (트레이스 노출용 — T3)
BYPASS_DEFINITIONAL = "definitional_bypass"


def new_state() -> dict:
    """대화 상태 1건. app 은 이걸 `st.session_state` 에 넣어 들고 다닌다."""
    return {"qform": {f: None for f in SLOT_FIELDS},   # 슬롯
            "ask_turn": 0,                             # 되묻기 턴 수 (최대 2)
            "pending_slot": None,                      # 지금 묻고 있는 슬롯
            "asked": [],                               # 물어본 슬롯 이력 (ver3 T1)
            "bf": None,                                # 1회 계산한 업무 판정
            "base_q": None,                            # 원 질의 (되묻기 병합의 기준)
            "slots_raw": None,                         # extract() 원본(_hits·_scope 보존)
            "turn_no": 0,                              # 질의 턴 번호 (되묻기는 안 센다)
            "slot_turn": {},                           # {슬롯: 설정된 턴} — TTL 판정용
            "slot_origin": {},                         # {슬롯: 신규|이월|미채움} — 트레이스
            "carryover": None,                         # 이월 판정 사유 (트레이스)
            "ask_bypass": None,                        # 되묻기 우회 사유 (ver3 T3)
            "queue": [],                               # 기존 Qform 세부용건 큐 (ver4 K13)
            "unit_queue": [],                          # 절별 BF/OOS 순차 큐
            "routing_history": [],                     # 절별 6-BF/OOS 처리 기록
            "passed": []}                              # pass 로 확정 포기한 슬롯 (ver4 K5)


def _default_classify(query: str):
    from rag import classify_query_bf        # 지연 임포트 — 검색 스택 없이도 모듈은 로드된다
    return classify_query_bf(query)


def _default_answer(query: str, qform: dict):
    import chain                             # 지연 임포트 — 되묻기 턴에는 여기까지 오지 않는다
    return chain.answer_in_scope(query, qform=qform)


def _clean(slots: dict) -> dict:
    """추출기 부가키(_hits/_bf/_scope) 제거 — answer()·survivors() 에 넘길 순수 슬롯."""
    return {f: slots.get(f) for f in SLOT_FIELDS}


def _mark_asked(state: dict, slot) -> None:
    """물어본 슬롯을 이력에 적재. 순서 유지 · 중복 없음."""
    if slot and slot not in state.setdefault("asked", []):
        state["asked"].append(slot)


def options(state: dict) -> list[str]:
    """지금 묻고 있는 슬롯의 **선택지 값 목록** (ver3 T5 · 버튼 렌더용).

    **값은 조합 테이블 생존 행에서만 온다(C6).** 라벨을 다듬거나 부연을 붙이지 않는다 —
    v1 에서 부연 4개가 전부 코퍼스 0청크(창작)로 판명된 이력이 있다(DECISIONS 08-09).

    정렬은 `qform_prompts.csv` 행 순서를 따른다. 문구를 가져오는 게 아니라 **순서만**
    빌린다 — 서류가 실제로 갈리는 유형이 앞에 오도록 CSV 가 이미 정해 둔 순서다.
    CSV 에 없는 값은 뒤에 사전순으로 붙인다(누락 방지).

    되묻는 중이 아니면 빈 리스트. LLM 콜 0.
    """
    slot = state.get("pending_slot")
    if not slot:
        return []
    slots = state.get("qform") or {}
    vals = qform_ask.survivor_values(
        slot, qform_state.survivors(slots, qform_state.combos_for(state.get("bf"))))
    rows = qform_ask.rows_for(slot, slots.get("sub_task"))
    covered = {r["value"] for r in rows}
    return [r["value"] for r in rows if r["value"] in vals] + sorted(vals - covered)


def _carryover_gate(cfg: dict, cls_bf, prev_bf, prev: dict) -> tuple[bool, str]:
    """이월을 **허용할지**와 그 사유. 추출 전에 판정되는 부분만 여기서 본다.

    §2-3 업무 전환 방벽: 새마을금고·우체국은 예금자보호에서 비대상, 착오송금에서
    대상이다. 업무가 바뀌었는데 슬롯이 따라오면 답이 정반대로 나간다.
    **오이월은 미이월보다 훨씬 해롭다** — 그래서 애매하면 막는 쪽으로 판정한다(R6).
    """
    if not cfg["SLOT_CARRYOVER"] or cfg["CARRYOVER_SCOPE"] == "off":
        return False, "이월 OFF"
    if not any(prev.get(f) for f in SLOT_FIELDS):
        return False, "직전 슬롯 없음"
    if cfg["CARRYOVER_SCOPE"] == "global":
        return True, "global — 업무 방벽 없음 (데모 비교용)"
    # bf_match(기본). 새 질의가 **다른 업무로 확정**되면 차단한다.
    # 판정 불명(None)은 "직전 문맥의 후속"으로 본다 — 실측상 동일 업무 후속 질의는
    # 거의 전부 불명으로 떨어진다("온라인으로 신청하려면요?" 등). 불명을 차단하면
    # 이월이 사실상 발동하지 않는다.
    if cls_bf is not None and prev_bf is not None and cls_bf != prev_bf:
        return False, f"업무 전환 {prev_bf} → {cls_bf}"
    return True, "동일 업무 문맥"


def start(state: dict, query: str, *, ask_mode: str = "template", boost: bool = False,
          classify_fn=None, answer_fn=None, llm_call=None, config=None,
          business_function: str | None = None, detect_multi: bool = True) -> dict:
    """새 질의 진입. 업무 판정을 **1회** 계산해 추출기에 주입한다(E3).

    ver3 T2 — **슬롯 이월.** 되묻기로 좁힌 슬롯이 다음 턴에 증발하지 않게 직전 턴
    값을 물려준다. 질의 재작성(LLM)이 아니라 **상태 재사용**이라 새 콜이 0이다.

    불변 조건 셋:
      ① 신규 > 이월 — 새 추출값이 있으면 이월값이 덮지 못한다("아니 수취인 기준으로")
      ② 업무 전환이 방벽 — `_carryover_gate()` (§2-3)
      ③ 실패는 넓어지는 방향 — 이월이 막히면 슬롯이 비어 첨부가 넓게 남을 뿐이다(R6)
    """
    cfg = qform_config.resolve(config)
    prev = dict(state.get("qform") or {})
    prev_bf = state.get("bf")
    prev_turn = dict(state.get("slot_turn") or {})
    turn_no = int(state.get("turn_no") or 0) + 1

    # 상단 절별 라우터가 고른 BF가 있으면 그대로 쓴다. 기존 직접 호출은 None이라 현행
    # classify_fn/_default_classify 경로를 유지한다.
    cls_bf = business_function if business_function is not None \
        else (classify_fn or _default_classify)(query)
    allow, reason = _carryover_gate(cfg, cls_bf, prev_bf, prev)
    # 업무 불명이면 직전 업무를 물려 추출기에 넣는다 — "그럼 법인은요?" 가 스코프
    # 게이트에 걸려 슬롯 0개로 죽는 것을 막는다. 이월이 막힌 턴에서는 상속하지 않는다.
    bf = cls_bf if cls_bf is not None else (prev_bf if allow else None)

    # M8-b — 스코프를 **cfg 에서** 받는다. 기본값이 `msdr` 이라 주입이 없으면 현행과 동일하다.
    slots = extract(query, business_function=bf, scope=cfg.get("QFORM_SCOPE"))
    origin = {f: (SRC_NEW if slots.get(f) else SRC_EMPTY) for f in SLOT_FIELDS}
    slot_turn = {f: turn_no for f in SLOT_FIELDS if slots.get(f)}

    # 스코프 통과 — 신규 추출이 0개면 이 질의가 이 업무 것이라는 증거가 없다.
    # 잡담("오늘 날씨 어때?")도 업무 판정이 불명이라 위 게이트를 통과하는데,
    # 여기서 막지 않으면 직전 슬롯이 통째로 따라붙어 엉뚱한 첨부가 나간다.
    # global 은 방벽 자체를 걷어낸 비교 모드라 이 조건도 건너뛴다.
    evidence = any(slots.get(f) for f in SLOT_FIELDS)
    if allow and not evidence and cfg["CARRYOVER_SCOPE"] != "global":
        allow, reason = False, "신규 추출 0 — 업무 증거 없음"

    expired: dict = {}                         # TTL 만료분 — 패널이 **회색으로 잔류**시킨다(K6)
    if allow:
        carried = 0
        for f in SLOT_FIELDS:
            if slots.get(f) is not None or prev.get(f) is None:
                continue                       # ① 신규가 있으면 이월값이 못 덮는다
            stamp = prev_turn.get(f)
            if stamp is not None and turn_no - stamp > cfg["CARRYOVER_TTL"]:
                # 값은 이월하지 않지만 **화면에서 조용히 지우지는 않는다.**
                # 아무것도 안 했는데 항목이 사라지면 사용자는 버그로 읽는다(K6 조건 ①).
                expired[f] = prev[f]
            if stamp is None or turn_no - stamp > cfg["CARRYOVER_TTL"]:
                continue                       # TTL 만료 · 설정 턴 불명 → 이월 안 함
            slots[f] = prev[f]
            origin[f] = SRC_CARRY
            slot_turn[f] = stamp               # 원래 설정 턴 유지 — 그래야 늙는다
            carried += 1
        reason = f"{reason} · {carried}개 이월" if carried else f"{reason} · 이월 없음"

    slots["_origin"] = origin                  # 부가키 — `_clean()` 이 걸러 answer() 로 안 간다
    slots["_carryover"] = reason
    state.update({"bf": bf, "base_q": query, "qform": _clean(slots),
                  "slots_raw": slots, "ask_turn": 0, "pending_slot": None,
                  "asked": [], "passed": [],   # 새 질의 = 새 되묻기 이력
                  "turn_no": turn_no, "slot_turn": slot_turn,
                  "slot_origin": origin, "carryover": reason,
                  "expired": expired})

    # ver4 K13 — 다중 의도는 **병합하지 않고 큐에 쌓는다.** 지금 처리하는 의도는
    # `extract()` 가 고른 것 그대로이며(=기존 경로 무변경), 나머지만 적재한다.
    # `classify_fn` 을 넘기지 않는다 — 절마다 업무 판정을 돌리면 E3(업무 판정 1회)이
    # 깨진다. 업무 교차 감지는 화면이 명시로 부른다(`detect_intents(q, classify_fn=…)`).
    if detect_multi and cfg.get("MAX_QUEUE", 0):
        import qform_memory_panel              # 지연 임포트 — 순환 참조 방지
        intents = qform_memory_panel.detect_intents(
            query, score_fn=qform_memory_panel.bf_scores, scope=cfg.get("QFORM_SCOPE"))
        if intents["kind"] == "parallel":
            rest = [st for st in intents["sub_tasks"] if st != state["qform"].get("sub_task")]
            qform_memory_panel.enqueue(
                state, [{"sub_task": st, "bf": bf, "text": query} for st in rest],
                config=config)
        state["intents"] = intents
    return _step(state, ask_mode=ask_mode, boost=boost, config=cfg,
                 answer_fn=answer_fn, llm_call=llm_call)


def reply(state: dict, text: str, *, value: str | None = None,
          ask_mode: str = "template", boost: bool = False,
          answer_fn=None, llm_call=None, config=None) -> dict:
    """되묻기 응답 반영. **빈 슬롯만 채운다** — 이미 확정된 값을 덮어쓰지 않는다.

    후속 답변("대리인이요")만으로는 스코프 게이트에 걸리므로 원 질의와 합쳐
    업무를 명시로 넘긴다. 되묻기는 sub_task 가 잡혔을 때만 발동하므로 이 시점의
    업무는 착오송금으로 확정돼 있다.

    **슬롯이 채워졌든 아니든 물었던 슬롯은 `asked` 에 적재한다(T1).** 못 채웠을 때
    적재하는 쪽이 핵심이다 — 채워진 슬롯은 `next_question` 이 어차피 안 고르지만,
    못 채운 슬롯은 조건이 그대로라 같은 질문이 무한히 재발동한다.

    value: 선택지 버튼 경로(ver3 T5). 주면 **자연어 추출을 경유하지 않고** 지금 묻는
        슬롯에 값을 직접 넣는다 — 값이 enum 에서 직접 오므로 오추출이 구조적으로 0 이다.
        `options()` 밖 값은 무시하고 자연어 경로로 되돌린다(C6 가드). 조용히 통과시키지
        않으려고 `_hits` 에 출처를 남긴다.
    """
    origin = dict(state.get("slot_origin") or {})
    slot_turn = dict(state.get("slot_turn") or {})
    turn_no = int(state.get("turn_no") or 0)
    slot = state.get("pending_slot")

    if value is not None and slot and value in set(options(state)):
        # 버튼 경로 — extract() 를 부르지 않는다. 트레이스가 보는 slots_raw 도 같이 갱신해야
        # "무엇이 채워졌나"가 화면과 어긋나지 않는다(트레이스는 slots_raw 를 읽는다).
        merged = dict(state.get("slots_raw") or {})
        merged["_hits"] = {**(merged.get("_hits") or {}), slot: ["⟵선택지 버튼"]}
        if not state["qform"].get(slot):
            state["qform"][slot] = value
            merged[slot] = value
            origin[slot] = SRC_NEW
            slot_turn[slot] = turn_no
    else:
        # 스코프 안이면 **상태의 업무를 그대로** 쓴다(M5 확장 대비). 스코프 밖이면 기존처럼
        # 착오송금으로 명시 — 후속 답변("대리인이요")만으로는 게이트에 걸리기 때문이다.
        # 기본 스코프(msdr)에서는 되묻기 대화의 bf 가 착오송금이라 **동작이 완전히 같다**.
        _bf = state.get("bf")
        _scope = qform_config.resolve(config).get("QFORM_SCOPE")
        merged = extract(f"{state['base_q']} {text}",
                         business_function=_bf if (_bf and in_scope(_bf, _scope)) else IN_SCOPE_BF,
                         scope=_scope)
        for f in SLOT_FIELDS:
            if not state["qform"].get(f) and merged.get(f):
                state["qform"][f] = merged[f]
                origin[f] = SRC_NEW          # 되묻기로 채운 값도 '신규'다
                slot_turn[f] = turn_no       # 이 턴에 설정됨 → TTL 이 여기서부터 센다
    # 되묻기 응답은 원 질의와 합쳐 다시 추출하므로 이월분이 merged 에는 없다.
    # 트레이스가 이월 표기를 잃지 않도록 확정 슬롯 기준으로 출처를 되살린다.
    merged["_origin"] = {f: origin.get(f, SRC_EMPTY) if state["qform"].get(f) else SRC_EMPTY
                         for f in SLOT_FIELDS}
    merged["_carryover"] = state.get("carryover")
    state.update({"slots_raw": merged, "slot_origin": merged["_origin"],
                  "slot_turn": slot_turn})
    _mark_asked(state, state.get("pending_slot"))
    return _step(state, ask_mode=ask_mode, boost=boost, config=config,
                 answer_fn=answer_fn, llm_call=llm_call)


def skip(state: dict, *, boost: bool = False, answer_fn=None, config=None) -> dict:
    """탈출구 — 되묻기 판정을 건너뛰고 **즉시** 답한다. 슬롯은 유지."""
    cfg = config if isinstance(config, dict) and "MAX_ASK_TURNS" in config \
        else qform_config.resolve(config)
    state["pending_slot"] = None
    state["ask_turn"] = cfg["MAX_ASK_TURNS"]  # 이후 재발동 차단
    return _finalize(state, boost=boost, answer_fn=answer_fn)


def _try_ask(state: dict, *, ask_mode: str, llm_call, cfg: dict) -> dict | None:
    """되묻기 **판정 + 문구**. 되물을 것이 없으면 `None`. **`answer()` 를 부르지 않는다.**

    `_step`(없으면 답변까지 간다)과 `edit`(없으면 거기서 멈춘다)이 이 함수를 공유한다.
    갈라 두면 "칩으로 고쳤을 때"와 "되묻기로 답했을 때"의 판정이 어긋날 수 있다.
    """
    # 정의형 질의는 되묻지 않는다(T3). 개념을 물었는데 신청 절차 슬롯을 채우라고
    # 요구하면 안 된다. **슬롯은 지우지 않는다** — `skip` 과 같은 취급이라 안 좁힌
    # 슬롯이 첨부를 넓게 남길 뿐이다(graceful degradation).
    # 스코프 게이트는 `extract()`·`chain.answer()` 쪽에 그대로 살아 있다 — 여기서
    # 건너뛰는 것은 **되묻기뿐**이라 소관 밖 정의형 질의는 여전히 reject 된다.
    bypass = BYPASS_DEFINITIONAL if is_definitional(state.get("base_q") or "") else None
    state["ask_bypass"] = bypass
    if isinstance(state.get("slots_raw"), dict):
        state["slots_raw"]["_ask_bypass"] = bypass
    if bypass:
        state["pending_slot"] = None
        return None

    combos = qform_state.combos_for(state.get("bf"))   # M6-c — 업무의 표를 본다
    nq = (qform_state.next_question(state["qform"], exclude=set(state.get("asked") or ()),
                                    combos=combos)
          if state["ask_turn"] < cfg["MAX_ASK_TURNS"] else None)
    if nq is None:
        state["pending_slot"] = None
        return None

    surv = qform_state.survivors(state["qform"], combos)
    ask = qform_ask.build_question(nq["slot"], state["qform"], surv,
                                   mode=ask_mode, llm_call=llm_call)
    state["ask_turn"] += 1
    state["pending_slot"] = nq["slot"]
    return {"kind": "ask", "slot": nq["slot"], "prompt": ask["text"],
            "remaining": nq["remaining"], "turn": state["ask_turn"],
            "survivors": surv, "ask": ask}


def _step(state: dict, *, ask_mode: str, boost: bool, answer_fn, llm_call,
          config=None) -> dict:
    """되묻기 판정 → 분기. 턴 상한에 닿거나 **물을 슬롯이 동나면** 미채움이어도 진행한다.

    `asked` 제외 후 후보가 없으면 `next_question` 이 None 을 돌려주므로,
    `MAX_ASK_TURNS` 도달과 **같은 경로**로 답변 턴에 들어간다(T1-④).
    """
    cfg = config if isinstance(config, dict) and "MAX_ASK_TURNS" in config \
        else qform_config.resolve(config)
    ev = _try_ask(state, ask_mode=ask_mode, llm_call=llm_call, cfg=cfg)
    return ev if ev is not None else _finalize(state, boost=boost, answer_fn=answer_fn)


def edit(state: dict, field: str, value: str | None = None, *,
         source: str = "슬롯 칩 수정", ask_mode: str = "template",
         llm_call=None, config=None) -> dict:
    """슬롯 1개를 고치거나(`value`) 해제하고(`value=None`) **되묻기 판정만** 다시 돈다.

    기획서 §7 "조용히 반영 금지"는 ver2 에서 절반만 지켜졌다 — 슬롯이 **보이지만
    고칠 수는 없었다.** 이 함수가 나머지 절반이다.

    **`answer()` 를 부르지 않는다** (08-11 결정 · AC6-5). 명세 B3-1 은 `_step` 재실행을
    적었지만 `_step` 은 되물을 것이 없으면 `_finalize` 로 빠져 생성 콜을 쓴다. 칩을
    만지작거릴 때마다 예산이 새면 안 되므로, 재생성은 사용자가 명시로 요청할 때만
    한다(`answer_now`). ⓐ 모드에서 이 함수의 HCX 콜은 **0**이다.

    **해제(`value=None`)의 의미가 ver4 에서 바뀌었다 — K4.** X 는 "그만 물어봐"가 아니라
    **메모리 오염 차단**이다: "이 값을 다음 용건으로 끌고 가지 마라". 그래서 지우자마자
    다시 묻지 않는다. 재질문 차단은 X 가 아니라 `pass_slot()` 이 맡는다(K5).

    | | ver3 (개정 전) | **ver4 (개정 후)** |
    |---|---|---|
    | X 직후 | 해당 슬롯 되묻기 즉시 재발동 | **아무 것도 묻지 않음.** 값만 None |
    | `asked` | 그 슬롯을 제거 | **건드리지 않음** |
    | `ask_turn` | `len(asked)` 로 무름 | **무르지 않음** |
    | `answer()` | 0회 | **0회 (F8 유지)** |

    ⚠ **X 이후 재질문 여부는 슬롯이 어떻게 채워졌느냐에 따라 갈린다. 의도된 비대칭이며
    버그가 아니다.**

    | 슬롯이 채워진 경로 | `asked` | X 이후 |
    |---|---|---|
    | 되묻기로 채움 | 이미 기록됨 | **다시 안 물음** — 결과적으로 pass 와 동일 |
    | 첫 발화에서 추출 | 기록 없음 | **다시 물을 수 있음** — 새 용건이 그 슬롯을 요구하면 |

    두 번째 줄이 K4 의 의도에 정확히 맞는다. 오염만 끊고, 새 용건에 필요한 것은 새로 묻는다.
    첫 줄은 "이미 한 번 물어본 것을 또 묻지 않는다"는 기존 원칙이 이기는 자리이며,
    사용자가 다시 답하고 싶으면 ✏️ 수정으로 값을 직접 넣으면 된다.

    반환: `{"kind": "ask", …}` 되물을 것이 생김 (**값 설정 경로에서만**. 콜 0 · ⓐ)
          `{"kind": "ready", …}` 되물을 것 없음 → 화면이 '다시 답변받기' 를 노출한다
    """
    if field not in SLOT_FIELDS:
        raise ValueError(f"슬롯이 아니다: {field!r} (허용 {SLOT_FIELDS})")
    cfg = config if isinstance(config, dict) and "MAX_ASK_TURNS" in config \
        else qform_config.resolve(config)

    origin = dict(state.get("slot_origin") or {})
    slot_turn = dict(state.get("slot_turn") or {})
    raw = dict(state.get("slots_raw") or {})
    hits = dict(raw.get("_hits") or {})

    state.setdefault("qform", {})[field] = value
    raw[field] = value
    if value is None:
        origin[field] = SRC_EMPTY
        slot_turn.pop(field, None)
        hits.pop(field, None)
        # K4 — `asked` · `ask_turn` 을 건드리지 않는다. 되묻기를 재발동시키지 않기 위해서다.
        # (ver3 는 여기서 asked 제거 + ask_turn 되감기를 했다 → 즉시 재질문)
    else:
        origin[field] = SRC_NEW
        slot_turn[field] = int(state.get("turn_no") or 0)
        hits[field] = [f"⟵{source}"]      # 트레이스가 출처를 정확히 말해야 한다

    raw["_hits"] = hits
    raw["_origin"] = origin
    state.update({"slots_raw": raw, "slot_origin": origin, "slot_turn": slot_turn})

    if value is None:
        # K4 — 해제는 침묵한다. 되묻기 판정 자체를 돌리지 않는다.
        state["pending_slot"] = None
        return {"kind": "ready", "field": field, "value": None,
                "slots": dict(state["qform"]),
                "survivors": qform_state.survivors(state["qform"])}

    ev = _try_ask(state, ask_mode=ask_mode, llm_call=llm_call, cfg=cfg)
    if ev is not None:
        return ev
    return {"kind": "ready", "field": field, "value": value,
            "slots": dict(state["qform"]),
            "survivors": qform_state.survivors(state["qform"])}


def pass_slot(state: dict, field: str) -> dict:
    """⏭ pass — **이 슬롯은 답하지 않겠다.** 값을 `None` 으로 확정하고 `asked` 에 기록한다.

    K5 로 X 와 역할이 갈렸다. X(`edit(f, None)`)는 오염 차단이라 `asked` 를 안 건드리고,
    pass 는 **재질문 차단**이라 `asked` 에 남긴다. 이 경로는 ver3 에도 사실상 있었다 —
    되묻기에 "잘 모르겠어요"로 답하면 `reply()` 가 `_mark_asked()` 를 불렀다.
    이번 작업은 그것을 **버튼으로 명시 노출**하는 것이고, 여기서는 그 경로를 함수로 고정한다.

    `answer()` 를 부르지 않는다(F8). 되묻기도 새로 띄우지 않는다 — 지금 묻던 슬롯을
    포기한 것이므로 다음 판정은 사용자의 다음 입력에서 돈다.
    """
    if field not in SLOT_FIELDS:
        raise ValueError(f"슬롯이 아니다: {field!r} (허용 {SLOT_FIELDS})")
    state.setdefault("qform", {})[field] = None
    raw = dict(state.get("slots_raw") or {})
    raw[field] = None
    origin = dict(state.get("slot_origin") or {})
    origin[field] = SRC_EMPTY
    raw["_origin"] = origin
    slot_turn = dict(state.get("slot_turn") or {})
    slot_turn.pop(field, None)
    _mark_asked(state, field)                       # ← X 와 갈리는 유일한 지점
    passed = state.setdefault("passed", [])
    if field not in passed:
        passed.append(field)
    if state.get("pending_slot") == field:
        state["pending_slot"] = None
    state.update({"slots_raw": raw, "slot_origin": origin, "slot_turn": slot_turn})
    return {"kind": "ready", "field": field, "value": None, "passed": list(passed),
            "slots": dict(state["qform"]),
            "survivors": qform_state.survivors(state["qform"])}


def cancel(state: dict, *, config=None) -> None:
    """되묻기 중단 — **답변을 만들지 않고** 일반 대화 상태로 돌아간다 (맥락 칩 취소).

    `skip()` 과 같은 상태 전이(pending 해제 + 재발동 차단)를 하되 `_finalize()` 를
    부르지 않는다 — HCX 콜 0. 슬롯은 유지한다: 사용자가 이미 고른 조건까지 지우면
    취소가 아니라 초기화다(그건 '새로운 대화 시작하기' 쪽 일이다).
    """
    cfg = config if isinstance(config, dict) and "MAX_ASK_TURNS" in config         else qform_config.resolve(config)
    state["pending_slot"] = None
    state["ask_turn"] = cfg["MAX_ASK_TURNS"]


def answer_now(state: dict, *, boost: bool = False, answer_fn=None) -> dict:
    """현재 슬롯 그대로 답변 턴을 돈다 — 슬롯 칩 수정 뒤 '다시 답변받기'(T6).

    `skip()` 과 다른 점: **`ask_turn` 을 상한으로 밀지 않는다.** 탈출구는 "더 묻지 마"
    라는 뜻이지만 재답변은 아니다 — 이후에 다른 슬롯을 해제하면 다시 물을 수 있어야 한다.
    """
    state["pending_slot"] = None
    return _finalize(state, boost=boost, answer_fn=answer_fn)


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
