# -*- coding: utf-8 -*-
"""복합질의를 처리 순서가 보존된 절 목록으로 나눈다.

과분리는 한 질문의 의미를 깨므로 명시적 문장부호·접속 표지만 보수적으로 사용한다.
분리하지 못하면 통짜 한 절을 반환하며, 합쳐 답하지 않는 정책은 오케스트레이터가 지킨다.
"""
from __future__ import annotations

import re
import uuid


_EXPLICIT = re.compile(r"\s*(?:그리고|또한|그리구|및)\s+")
_PUNCT = re.compile(r"(?<=[?!.。！？])\s+")
_REQUEST_AND = re.compile(r"(?P<head>.+?(?:알려\s*주|설명해\s*주|확인해\s*주))고\s+(?P<tail>.+)")
# 절 하나가 **독립 용건**인지 가르는 표지 — 물음표 또는 존댓말 의문·요청 어미.
# 마침표로 끝나는 평서문("공동인증서가 없습니다.")은 뒤 질문의 배경 설명이지 용건이 아니다.
_ASK_END = re.compile(
    r"(?:[?？!！]|나요|가요|까요|은가|는가|어요|해요|주세요|주십시오|주시겠|"
    r"알려\s*줘|알려\s*주|해\s*줘|궁금|문의)\s*[.。]?$")


def _merge_context(parts: list[str]) -> list[str]:
    """물음·요청 표지가 없는 절은 **뒤 절의 배경**으로 붙인다.

    `_PUNCT` 가 마침표에서도 자르기 때문에 "공동인증서가 없습니다. 어디서 받을 수
    있나요?" 같은 한 질문이 두 용건으로 쪼개졌다. 두 절이 같은 문서를 가리키니
    답변까지 똑같이 두 번 나온다 — 과분리는 이 모듈이 피하려던 바로 그 실패다.
    "A 알려주세요. B 알려주세요." 처럼 양쪽 다 요청이면 그대로 둘로 남는다.
    """
    out: list[str] = []
    buf = ""
    for part in parts:
        merged = f"{buf} {part}".strip() if buf else part
        if _ASK_END.search(part):
            out.append(merged)
            buf = ""
        else:
            buf = merged
    if buf:                         # 끝까지 물음 표지가 없으면 통짜로 남긴다
        out.append(buf)
    return out


def _finish_request(text: str) -> str:
    s = text.strip(" ,")
    if re.search(r"(?:알려\s*주|설명해\s*주|확인해\s*주)$", s):
        return s + "세요"
    return s


def split_clauses(query: str, *, max_units: int = 5) -> list[str]:
    query = " ".join(str(query or "").split()).strip()
    if not query:
        return []
    parts = [query]
    for pattern in (_PUNCT, _EXPLICIT):
        split = []
        for part in parts:
            split.extend(x.strip() for x in pattern.split(part) if x.strip())
        parts = split

    parts = _merge_context(parts)

    # 확정안 예시와 같은 "알려주고 … 알려줘" 병렬 요청. 한 번에 하나씩 보수적으로 푼다.
    expanded = []
    for part in parts:
        rest = part
        while len(expanded) < max_units - 1:
            match = _REQUEST_AND.fullmatch(rest)
            if not match:
                break
            expanded.append(_finish_request(match.group("head")))
            rest = match.group("tail").strip()
        if rest:
            expanded.append(rest)
    return expanded[:max_units] or [query]


def make_units(query: str, *, max_units: int = 5) -> list[dict]:
    return [{"unit_id": f"unit_{uuid.uuid4().hex[:12]}", "order": i, "text": clause}
            for i, clause in enumerate(split_clauses(query, max_units=max_units), 1)]


if __name__ == "__main__":          # python chatbot/query_units.py
    # 과분리(한 질문이 두 용건으로 갈려 같은 답이 두 번 나오는 것)를 막는지 본다.
    one = ["공동인증서가 없습니다. 어디서 받을 수 있나요?",
           "서비스 운영시간이 아니라고 나옵니다. 어떻게 하나요?",
           "착오송금 반환 신청 서류가 뭐예요?",
           "공동인증서의 유효기간이 아직 남아 있는데도 불구하고 자꾸 폐기되었다고 나옵니다."]
    two = ["예금보호한도가 얼마인가요? 착오송금 반환은 어떻게 신청하나요?",
           "예금보호한도 알려주세요. 착오송금 반환 방법도 알려주세요.",
           "예금보호한도가 얼마인가요 그리고 미수령금은 어떻게 조회하나요?"]
    for q in one:
        got = split_clauses(q)
        assert len(got) == 1, (q, got)
    for q in two:
        got = split_clauses(q)
        assert len(got) == 2, (q, got)
    print("query_units self-check ok")
