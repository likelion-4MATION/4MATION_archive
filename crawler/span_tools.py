# -*- coding: utf-8 -*-
"""스팬 기반 근거 포맷 공용 도구 — ver4 M9-1. **순수 함수만. 부작용 0.**

왜 청크 ID 를 영속 자산의 키로 안 쓰는가 — 앵커 트랙이 **청크 사이즈를 동적으로 스윕**한다.
`chunk_id` 는 고정 식별자가 아니라 **실험 파라미터의 함수**다. 청킹이 바뀌면 `#00`·`#01` 이
통째로 재배치되고, 그 ID 를 박아 둔 CSV 는 조용히 틀린 근거를 가리키게 된다.

대신 **`(doc_id, 텍스트 스니펫)`** 을 쓴다. 둘 다 청킹 불변이다 —
`parent_doc_id` 는 크롤 단위라 재청킹에 안 흔들리고, 스니펫은 원문 문자열이라 경계와 무관하다.

런타임 조인은 **이미 문서 단위**다(`source_doc_id` · `doc_attachments.json` · `eval.py gt_docs`).
따라서 이것은 아키텍처 재작성이 아니라 **컬럼 포맷 이행**이다.

## 직렬화 포맷

    doc_id::스니펫                     스팬 1개
    doc_id::스니펫|doc_id::스니펫       스팬 여러 개

구분자 선택 근거(M9-1 실측) — `doc_id` 문자 집합은 `[-0-9A-Za-z]` 이고,
현행 스니펫 20건에 `::` `|` 둘 다 **출현 0**이다. `,` 는 스니펫 4건에 나오지만
**CSV 인용(`csv` 모듈 기본 QUOTE_MINIMAL)이 처리**하므로 구분자로만 안 쓰면 된다.

- `parse_span` 은 **첫 `::` 에서만** 가른다. `doc_id` 에 `:` 가 못 들어가므로 안전하다.
- 스니펫은 **무편집**이다(J3). 유일성 확보를 목적으로도 자르거나 늘리지 않는다.
"""
from __future__ import annotations

import json
import pathlib

SPAN_SEP = "::"      # doc_id 와 스니펫 사이
SPAN_JOIN = "|"      # 스팬 여러 개 사이 (combos CSV 의 evidence 관행과 동일)


def load_chunks(path) -> dict:
    """`chunk_id -> {"text", "parent_doc_id"}`. 원본을 바꾸지 않는다."""
    out = {}
    with pathlib.Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            out[c["chunk_id"]] = {"text": c["text"], "parent_doc_id": c["parent_doc_id"]}
    return out


def resolve_doc(chunk_id: str, chunks: dict) -> str | None:
    """청크 ID → 소속 문서 ID. 이행의 왼쪽 절반이다. 모르는 ID 면 None."""
    c = chunks.get(chunk_id)
    return c["parent_doc_id"] if c else None


def doc_chunks(doc_id: str, chunks: dict) -> list[str]:
    """그 문서에 속한 청크 ID 목록 (입력 순서 보존)."""
    return [cid for cid, c in chunks.items() if c["parent_doc_id"] == doc_id]


def find_span(doc_id: str, snippet: str, chunks: dict) -> list[str]:
    """`doc_id` 안에서 `snippet` 을 **부분문자열로 포함하는 청크 전부**.

    빈 리스트면 그 문서 안에서 스니펫이 **청크 경계를 넘어간다**는 뜻이다 —
    문서 텍스트에는 있는데 어느 단일 청크에도 온전히 안 들어간 경우. 통과시키지 않는다.
    """
    if not snippet:
        return []
    return [cid for cid in doc_chunks(doc_id, chunks) if snippet in chunks[cid]["text"]]


def find_span_all(snippet: str, chunks: dict) -> list[str]:
    """코퍼스 **전체**에서 스니펫을 포함하는 청크. 유일성 판정의 분모."""
    if not snippet:
        return []
    return [cid for cid, c in chunks.items() if snippet in c["text"]]


def is_unique_pair(doc_id: str, snippet: str, chunks: dict) -> bool:
    """`(doc_id, snippet)` 쌍이 코퍼스 전체에서 **유일하게** 걸리는가.

    스니펫 단독으로 여러 문서에 걸려도 좋다 — 쌍이 한 문서로 좁혀지면 근거는 확정된다.
    판정식: 스니펫을 포함하는 청크들의 **소속 문서 집합이 정확히 `{doc_id}`** 이고
    그 문서 안에서 **한 청크 이상**이 스니펫을 온전히 담고 있다.
    """
    hit = find_span_all(snippet, chunks)
    if not hit:
        return False
    docs = {chunks[c]["parent_doc_id"] for c in hit}
    return docs == {doc_id} and bool(find_span(doc_id, snippet, chunks))


def format_span(doc_id: str, snippet: str) -> str:
    """`(doc_id, snippet)` → 직렬화 문자열. 구분자가 값에 있으면 **거절**한다."""
    if SPAN_SEP in doc_id or SPAN_JOIN in doc_id:
        raise ValueError(f"doc_id 에 구분자가 있다: {doc_id!r}")
    if SPAN_JOIN in snippet:
        raise ValueError(f"스니펫에 스팬 구분자 {SPAN_JOIN!r} 가 있다: {snippet[:40]!r}")
    return f"{doc_id}{SPAN_SEP}{snippet}"


def parse_span(s: str) -> tuple[str, str]:
    """직렬화 문자열 → `(doc_id, snippet)`. **첫 `::` 에서만** 가른다."""
    if SPAN_SEP not in s:
        raise ValueError(f"스팬 포맷이 아니다: {s[:40]!r}")
    doc_id, snippet = s.split(SPAN_SEP, 1)
    return doc_id, snippet


def format_spans(pairs) -> str:
    """`[(doc_id, snippet), …]` → `a::x|b::y`."""
    return SPAN_JOIN.join(format_span(d, s) for d, s in pairs)


def parse_spans(s: str) -> list[tuple[str, str]]:
    """`a::x|b::y` → `[(a,x),(b,y)]`. 빈 문자열은 빈 리스트."""
    return [parse_span(p) for p in (s or "").split(SPAN_JOIN) if p.strip()]


# ══════════════════════════════════════════════════════════════════════════
# 자기검사 (python3 crawler/span_tools.py) — 왕복·유일성만. 파일 수정 0
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    BASE = pathlib.Path(__file__).resolve().parent
    chunks = load_chunks(BASE / "data" / "chunks.jsonl")
    fails = []
    print(f"코퍼스 {len(chunks)}청크 / {len({c['parent_doc_id'] for c in chunks.values()})}문서\n")

    print("── 왕복 (format → parse) ──")
    CASES = [("kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn", "예금보험공사가 해당 금융회사를 대신하여 지급하는 금전"),
             ("kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn",
              "예금자가 국외거주 외국인, 유학생, 상사주재원인 경우")]   # 쉼표 포함
    ok_rt = True
    for d, s in CASES:
        back = parse_span(format_span(d, s))
        hit = back == (d, s)
        ok_rt &= hit
        print(f"  {'OK ' if hit else 'DIFF ⛔'} {d[-34:]:34s} · 쉼표포함={',' in s}")
    if not ok_rt:
        fails.append("왕복")

    print("\n── 다중 스팬 왕복 ──")
    multi = format_spans(CASES)
    ok_m = parse_spans(multi) == CASES
    print(f"  {len(parse_spans(multi))}개 복원 · 일치 {ok_m}")
    if not ok_m:
        fails.append("다중 왕복")

    print("\n── 구분자 거절 ──")
    ok_rej = True
    for bad_d, bad_s in [("a::b", "x"), ("a", "x|y")]:
        try:
            format_span(bad_d, bad_s)
            ok_rej = False
            print(f"  DIFF ⛔ 거절 안 됨: {bad_d!r} / {bad_s!r}")
        except ValueError:
            print(f"  OK  거절: doc={bad_d!r} snip={bad_s[:10]!r}")
    if not ok_rej:
        fails.append("구분자 거절")

    print("\n── find_span / is_unique_pair ──")
    d, s = CASES[0]
    print(f"  find_span 청크 {find_span(d, s, chunks)}")
    print(f"  find_span_all 청크 수 {len(find_span_all(s, chunks))}")
    print(f"  is_unique_pair {is_unique_pair(d, s, chunks)}")
    ok_u = is_unique_pair(d, s, chunks) and len(find_span(d, s, chunks)) == 1
    if not ok_u:
        fails.append("유일성")

    print()
    if fails:
        print("어긋난 항목 ⛔")
        for f in fails:
            print(f"  {f}")
        sys.exit(1)
    print("전체 통과 ✅  (순수 함수 · 파일 수정 0)")
    sys.exit(0)
