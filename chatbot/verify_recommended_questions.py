# -*- coding: utf-8 -*-
"""추천 질문 검증 — 화면에 뜨는 질문이 전부 **크롤링 원문에 실제로 있는 문장**인지 확인한다.

`app.py` 는 streamlit 을 import 하는 즉시 페이지를 그리므로, 질문 선택 로직 블록만
떼어 exec 한다(선택 로직에 streamlit 의존이 없다는 사실 자체도 이 검증이 지킨다).

핵심 불변식: 추천 질문 = 코퍼스 부분문자열. 하나라도 창작되면 여기서 깨진다.
"""
from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHIPS = [("착오송금 반환 신청", ""), ("예금자보호제도", ""), ("예금보험금 안내", ""),
         ("고객 미수령금 신청", ""), ("채무조정 안내", ""), ("은닉재산 신고", "")]


def _load():
    src = (ROOT / "chatbot" / "app.py").read_text(encoding="utf-8")
    block = src[src.index("_POLITE_Q_RE"):src.index("def _render_question_cards")]
    g = {"re": re, "json": json, "ROOT": ROOT, "EXAMPLE_CHIPS": CHIPS}
    exec(block, g)
    return g


def main() -> None:
    g = _load()
    rep = g["_load_representative_domain_questions"]()
    trending = g["_load_trending_questions"]()

    corpus = "\n".join(
        json.loads(line).get("text") or ""
        for line in (ROOT / "crawler" / "data" / "chunks.jsonl").open(encoding="utf-8")
    ) + "\n" + "\n".join(
        json.loads(line).get("origin_question") or ""
        for line in (ROOT / "crawler" / "data" / "testset_natural_450.jsonl").open(encoding="utf-8")
    )

    for label, _ in CHIPS:
        qs = rep.get(label) or []
        assert qs, f"{label}: 추천 질문 0건"
        assert len(qs) == len(set(qs)), f"{label}: 중복 질문"
        for q in qs:
            assert q in corpus, f"{label}: 코퍼스에 없는 질문 — {q}"
        print(f"[OK] {label} ({len(qs)}건)")
        for q in qs:
            print(f"   - {q}")

    assert len(trending) == len(set(trending)), "지금 뜨는 검색어 중복"
    assert {q for q in trending} <= {q for qs in rep.values() for q in qs}, \
        "지금 뜨는 검색어가 업무별 풀 밖의 문장을 쓴다"
    assert len({next(l for l, _ in CHIPS if q in (rep.get(l) or [])) for q in trending}) == len(trending), \
        "지금 뜨는 검색어가 한 업무에 몰려 있다"
    print(f"\n[OK] 지금 뜨는 검색어 ({len(trending)}건, 업무별 1건씩)")
    for q in trending:
        print(f"   - {q}")


if __name__ == "__main__":
    main()
