# -*- coding: utf-8 -*-
"""절별 6-BF → Qform/RAG 또는 OOS 정책을 실행하는 최상위 오케스트레이터."""
from __future__ import annotations

import pathlib
import sys
import time
from typing import Callable


ROOT = pathlib.Path(__file__).resolve().parent.parent
for _p in (ROOT / "chatbot", ROOT / "crawler", ROOT / "admin"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import oos_policy
import oos_store
import qform_config
import qform_flow
from query_units import make_units
from router_adapter import route_clause


def ensure_state(flow: dict) -> dict:
    flow.setdefault("unit_queue", [])
    flow.setdefault("routing_history", [])
    return flow


def _report(decision: dict, report_context: dict | None) -> bool:
    if decision.get("action") != "BOT_FEEDBACK" or not report_context:
        return False
    try:
        oos_store.create_report(
            report_context.get("payload") or report_context,
            session_id=str(report_context.get("session_id") or "anonymous"),
            report_path="natural_language",
            target_message_id=str(report_context.get("target_message_id") or ""),
        )
        return True
    except Exception:
        return False


def _scoped_answer(answer_fn, clause: str, bf: str, slots: dict) -> dict:
    if answer_fn is not None:
        return answer_fn(clause, bf, slots)
    import chain
    return chain.answer_in_scope(clause, bf=bf, qform=slots)


def _process(flow: dict, unit: dict, *, ask_mode: str, boost: bool, config,
             llm_call=None, answer_fn=None, report_context: dict | None = None) -> dict:
    t0 = time.time()
    routing = unit["routing"]
    flow["routing_history"].append({"unit_id": unit["unit_id"], "order": unit["order"],
                                    "text": unit["text"], **routing})
    if routing.get("triggered") and routing.get("bf"):
        bf = routing["bf"]
        ev = qform_flow.start(
            flow, unit["text"], ask_mode=ask_mode, boost=boost, config=config,
            business_function=bf, detect_multi=False,
            answer_fn=lambda q, slots: _scoped_answer(answer_fn, q, bf, slots),
        )
    else:
        # 라우터 자체 장애는 세부분류 LLM으로 숨기지 않고 최종 안전값으로 바로 닫는다.
        if routing.get("error"):
            decision = {"action": "PHONE_GUIDE", "row_id": None, "referral": None,
                        "meta": {"source": "router_failure", "error": routing["error"]}}
        else:
            decision = oos_policy.classify_oos(unit["text"], llm_call=llm_call)
        saved = _report(decision, report_context) if decision.get("action") == "BOT_FEEDBACK" else None
        result = oos_policy.build_result(decision, report_saved=saved)
        flow.update({"base_q": unit["text"], "bf": None, "pending_slot": None,
                     "ask_turn": 0, "qform": {f: None for f in qform_flow.SLOT_FIELDS}})
        ev = {"kind": "answer", "result": result, "slots": {}, "search_q": unit["text"],
              "boosted": None, "survivors": []}

    ev["unit"] = {k: unit[k] for k in ("unit_id", "order", "text")}
    ev["routing"] = routing
    ev["queue_size"] = len(flow.get("unit_queue") or [])
    if ev.get("result"):
        ev["result"].setdefault("_meta", {})["routing"] = routing
        ev["result"]["_meta"]["unit"] = ev["unit"]
        ev["result"]["_meta"]["latency_ms"] = int((time.time() - t0) * 1000)
    return ev


def start_turn(flow: dict, query: str, *, ask_mode: str = "template", boost: bool = False,
               config=None, route_fn: Callable[[str], dict] | None = None, llm_call=None,
               answer_fn=None, report_context: dict | None = None) -> dict:
    """새 사용자 입력을 전 절 라우팅한 뒤 첫 절만 처리하고 나머지를 큐에 둔다."""
    ensure_state(flow)
    cfg = qform_config.resolve(config)
    # 기존 Qform의 MAX_QUEUE는 세부용건 큐 설정이지 절별 라우팅 상한이 아니다.
    # 이를 재사용하면 네 번째 이후 절이 라우팅도 되기 전에 사라지므로 분리한다.
    units = make_units(query, max_units=50)
    routed = []
    for unit in units:
        unit = dict(unit)
        unit["routing"] = (route_fn or route_clause)(unit["text"])
        routed.append(unit)
    if not routed:
        routed = [{"unit_id": "unit_empty", "order": 1, "text": query,
                   "routing": {"triggered": False, "bf": None, "scores": {},
                               "error": "empty_query", "source": "input"}}]
    flow["unit_queue"] = routed[1:]
    flow["last_units"] = [{k: u[k] for k in ("unit_id", "order", "text", "routing")} for u in routed]
    return _process(flow, routed[0], ask_mode=ask_mode, boost=boost, config=cfg,
                    llm_call=llm_call, answer_fn=answer_fn, report_context=report_context)


def next_unit(flow: dict, *, ask_mode: str = "template", boost: bool = False,
              config=None, llm_call=None, answer_fn=None,
              report_context: dict | None = None) -> dict | None:
    """순차 큐의 다음 절을 하나 처리한다."""
    ensure_state(flow)
    if not flow["unit_queue"]:
        return None
    unit = flow["unit_queue"].pop(0)
    return _process(flow, unit, ask_mode=ask_mode, boost=boost,
                    config=qform_config.resolve(config), llm_call=llm_call,
                    answer_fn=answer_fn, report_context=report_context)
