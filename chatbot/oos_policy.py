# -*- coding: utf-8 -*-
"""OOS 세부분류와 결정론적 정책 검증.

LLM은 action 후보와 row_id만 고른다. 연락처·기관·안내문은 게시된 관리자 레지스트리에서만
가져오며, 파싱·검증·시간초과를 포함한 모든 실패는 PHONE_GUIDE로 닫힌다.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parent.parent
for _p in (ROOT / "chatbot", ROOT / "admin"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import oos_store


ACTIONS = ("BOT_FEEDBACK", "REFERRAL", "CASUAL", "FAR_OOS", "PHONE_GUIDE")
OOS_PARAMS = {"temperature": 0.0, "top_p": 0.8, "max_tokens": 80,
              "thinking": {"type": "disabled"},
              "response_format": {"type": "json_object"}}

BOT_TARGET = ("챗봇", "방금 답변", "네 답변", "너의 답변", "출처", "설명한 내용", "답변 내용")
BOT_ERROR = ("틀렸", "오류", "사실과 다르", "이상하", "신고", "잘못 답", "정확하지 않")
SYSTEM_ERROR = ("로그인", "인증번호", "인증 코드", "신청 시스템", "사이트", "접속", "장애")
CASUAL_HELLO = ("안녕", "안녕하세요", "반가워", "hello", "hi", "하이")
CASUAL_THANKS = ("고마워", "감사", "thanks", "thank you")
CASUAL_BYE = ("잘가", "안녕히", "다음에", "bye")
QUESTION_MARKS = ("?", "？")
FINANCE_ADJACENT = (
    "예금", "보험", "금융", "은행", "송금", "계좌", "채무", "대출", "빚", "회생", "파산",
    "보호한도", "미수령", "신고", "포상금", "투자", "증권", "카드", "인증", "로그인",
)

FAR_TEXT = "죄송합니다. 저는 예금보험공사의 예금자보호·예금보험금·미수령금·착오송금 반환지원·은닉재산 신고·채무조정 관련 안내를 도와드릴 수 있습니다."
PHONE_TEXT = "이 질문은 챗봇이 확실하게 자동 안내하기 어렵습니다. 필요한 경우 유선 상담 안내를 확인해 주세요."
REPORT_OK_TEXT = "챗봇 오류 신고가 접수되었습니다. 현재 대화와 답변 처리 기록은 오류 분석을 위해 30일간 보관됩니다."
REPORT_FAIL_TEXT = "오류 신고를 저장하지 못했습니다. 접수된 것으로 처리하지 않았습니다. 잠시 후 다시 시도해 주세요."


def is_bot_feedback(query: str) -> bool:
    q = (query or "").lower()
    # 사이트·인증 장애만 말한 경우 챗봇 답변 오류로 잡지 않는다.
    target = any(x in q for x in BOT_TARGET)
    error = any(x in q for x in BOT_ERROR)
    system_only = any(x in q for x in SYSTEM_ERROR) and not any(x in q for x in ("답변", "출처", "설명"))
    return target and error and not system_only


def casual_kind(query: str) -> str | None:
    q = " ".join((query or "").lower().split()).strip(" .!~")
    if not q or len(q) > 30 or any(mark in q for mark in QUESTION_MARKS):
        return None
    groups = (("hello", CASUAL_HELLO), ("thanks", CASUAL_THANKS), ("bye", CASUAL_BYE))
    for kind, terms in groups:
        if any(t in q for t in terms):
            residue = q
            for term in terms:
                residue = residue.replace(term, "")
            residue = re.sub(r"[\s,.!~ㅋㅎ]+", "", residue)
            if not residue or residue in ("요", "네", "정말", "너무", "많이"):
                return kind
    return None


def far_oos_allowed(query: str) -> bool:
    q = (query or "").lower()
    return not any(term in q for term in FINANCE_ADJACENT)


def _prompt(candidates: list[dict]) -> str:
    registry = json.dumps(candidates, ensure_ascii=False)
    return (
        "너는 예금보험공사 챗봇의 OOS 세부분류기다. 입력은 6개 업무 라우터의 어떤 "
        "트리거도 충족하지 못한 질문이다. 아래 action 하나만 고른다.\n"
        "우선순위: BOT_FEEDBACK > REFERRAL > CASUAL > FAR_OOS > PHONE_GUIDE.\n"
        "BOT_FEEDBACK은 챗봇 답변 대상 신호와 틀림/오류 신호가 모두 있을 때만 고른다. "
        "사이트 로그인·인증·신청시스템 장애는 해당하지 않는다.\n"
        "REFERRAL은 아래 게시 레지스트리 중 정확히 맞는 행이 있을 때만 고르고 row_id를 쓴다.\n"
        "CASUAL은 인사·감사·작별만 있는 짧은 입력에만 쓴다.\n"
        "FAR_OOS는 날씨·요리·스포츠 등 금융과 명백히 무관할 때만 쓴다.\n"
        "조금이라도 불확실하거나 금융 인접 표현이면 PHONE_GUIDE다.\n"
        f"게시 레지스트리: {registry}\n"
        "JSON 한 개만 출력하라. REFERRAL이 아니면 row_id는 null이다. "
        '{"action":"PHONE_GUIDE","row_id":null}'
    )


def parse_candidate(text: str | None) -> dict | None:
    if not text:
        return None
    try:
        data = json.loads(text.strip())
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict) or set(data) - {"action", "row_id"}:
        return None
    if data.get("action") not in ACTIONS:
        return None
    row_id = data.get("row_id")
    if row_id is not None and not isinstance(row_id, str):
        return None
    if data["action"] == "REFERRAL" and not row_id:
        return None
    if data["action"] != "REFERRAL" and row_id is not None:
        return None
    return {"action": data["action"], "row_id": row_id}


def _default_llm(messages: list[dict]):
    import chain
    return chain._llm(messages, req_id="oos", params=OOS_PARAMS)


def classify_oos(query: str, *, llm_call=None) -> dict:
    """OOS action 후보를 만들고 코드 조건으로 재검증한다."""
    # 엄격한 우선순위 두 항목은 결정론적으로 확정해 LLM 변동이 뒤집지 못하게 한다.
    if is_bot_feedback(query):
        return {"action": "BOT_FEEDBACK", "row_id": None, "referral": None,
                "meta": {"source": "deterministic_priority", "error": None}}
    kind = casual_kind(query)
    if kind:
        return {"action": "CASUAL", "row_id": None, "referral": None,
                "meta": {"source": "deterministic_priority", "casual_kind": kind, "error": None}}

    candidates = oos_store.referral_candidates()
    messages = [{"role": "system", "content": _prompt(candidates)},
                {"role": "user", "content": query}]
    try:
        raw = (llm_call or _default_llm)(messages)
        if isinstance(raw, tuple):
            text, llm_meta = raw
        else:
            text, llm_meta = raw, {}
    except Exception as exc:
        text, llm_meta = None, {"error": type(exc).__name__}
    candidate = parse_candidate(text)
    if not candidate:
        return {"action": "PHONE_GUIDE", "row_id": None, "referral": None,
                "meta": {"source": "fallback", "error": llm_meta.get("error") or "invalid_json"}}

    action, row_id = candidate["action"], candidate["row_id"]
    referral = None
    valid = True
    if action == "BOT_FEEDBACK":
        valid = is_bot_feedback(query)
    elif action == "REFERRAL":
        referral = oos_store.referral_for_query(row_id, query)
        valid = referral is not None
    elif action == "CASUAL":
        valid = casual_kind(query) is not None
    elif action == "FAR_OOS":
        valid = far_oos_allowed(query)
    if not valid:
        action, row_id, referral = "PHONE_GUIDE", None, None
    return {"action": action, "row_id": row_id, "referral": referral,
            "meta": {"source": "llm", "error": None if valid else "policy_validation_failed",
                     "llm": llm_meta}}


def build_result(decision: dict, *, report_saved: bool | None = None) -> dict:
    action = decision.get("action") if decision.get("action") in ACTIONS else "PHONE_GUIDE"
    referral = decision.get("referral") if action == "REFERRAL" else None
    phone = oos_store.get_phone_guide(active_only=True) if action == "PHONE_GUIDE" else None
    casual = (decision.get("meta") or {}).get("casual_kind")
    if action == "BOT_FEEDBACK":
        text = REPORT_OK_TEXT if report_saved else REPORT_FAIL_TEXT
    elif action == "REFERRAL" and referral:
        text = referral["message"]
    elif action == "CASUAL":
        text = {"thanks": "감사합니다. 다른 도움이 필요하면 말씀해 주세요.",
                "bye": "이용해 주셔서 감사합니다. 좋은 하루 보내세요."}.get(
                    casual, "안녕하세요. 예금보험공사 관련 내용을 안내해 드릴게요.")
    elif action == "FAR_OOS":
        text = FAR_TEXT
    else:
        action, text = "PHONE_GUIDE", PHONE_TEXT
    return {
        "text": text, "sources": [], "confidence": 0.0, "route": "oos",
        "checks": {"ok": True, "flags": [], "skipped": "정책 고정 응답"},
        "attachments": [], "referral": referral, "phone_guide": phone,
        "_meta": {"action": action, "row_id": decision.get("row_id"),
                  "oos": decision.get("meta") or {}, "latency_ms": None},
    }
