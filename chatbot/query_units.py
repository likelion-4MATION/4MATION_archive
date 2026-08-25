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
