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

## 이행 게이트 (M9-1b J1)

**선언 문서 안에서 스니펫이 정확히 1회** — `resolves_to_chunk()` 가 `None` 이 아닌 것.
코퍼스 전체 히트 문서 수(`hit_docs`)는 **진단값이지 게이트가 아니다.**
구 `chunk_id` 포맷도 텍스트의 코퍼스 유일성을 보증한 적이 없어 **해상도가 동일**하다.
"""
from __future__ import annotations

import json
import pathlib
import re

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


def occurrences_in_doc(doc_id: str, snippet: str, chunks: dict) -> int:
    """그 문서의 청크들에서 스니펫이 나타난 **총 횟수**.

    청크 단위로 세므로, 스니펫이 **청크 경계를 넘어가면 0** 이 나온다 —
    문서 텍스트에는 있는데 어느 단일 청크에도 온전히 안 들어간 경우를 통과시키지 않는다.
    """
    if not snippet:
        return 0
    return sum(chunks[cid]["text"].count(snippet) for cid in doc_chunks(doc_id, chunks))


def hit_docs(snippet: str, chunks: dict) -> list[str]:
    """코퍼스 **전체**에서 스니펫이 걸리는 문서 전량. **진단값이지 게이트가 아니다.**

    2개 이상이어도 이행은 통과한다 — `doc_id` 가 이미 문서를 지정하기 때문이다.
    구 `chunk_id` 포맷도 텍스트의 코퍼스 유일성을 보증한 적이 없다. 해상도는 동일하다.
    """
    if not snippet:
        return []
    seen, out = set(), []
    for cid in chunks:
        if snippet in chunks[cid]["text"]:
            d = chunks[cid]["parent_doc_id"]
            if d not in seen:
                seen.add(d)
                out.append(d)
    return out


def resolves_to_chunk(doc_id: str, snippet: str, chunks: dict) -> str | None:
    """**이행 게이트.** 선언 문서 안에서 스니펫이 **정확히 1회** 나올 때만 그 청크 ID.

    1회 초과(같은 문서 안 중복)·0회(부재 또는 청크 경계 넘음)면 `None`.
    `None` 이 아니라는 것이 "이 스팬은 근거를 한 곳으로 확정한다"는 뜻이다.
    """
    if occurrences_in_doc(doc_id, snippet, chunks) != 1:
        return None
    hits = find_span(doc_id, snippet, chunks)
    return hits[0] if len(hits) == 1 else None


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
# 앵커 스팬 추출 (ver4 M9-2b → M9-3) — **선두 고정을 버리고, 히트 수로 가른다**
#
# M9-2 의 "선두 1문장 + 확장 + 상한" 은 폐기됐다. 그 규칙은 **게이트(청크를 결정하는가)를
# 근거 가치의 대리로 썼고**, 그 결과 청크 선두가 목록 번호인 문서에서 스니펫 `"01"` 이
# 게이트를 통과했다 — 청크는 확정하지만 근거로는 읽을 수 없다. 상한을 올리는 것은
# 그 증상만 덮는다.
#
# M9-2b 앵커 규칙은 **위치를 고정하지 않고** 청크 안의 모든 문장을 후보로 놓은 뒤
# 게이트를 통과하는 것 중 **가장 짧은 것**을 골랐다. 그런데 여전히 `01`·`05`·`06`·`07`
# 같은 목록 번호가 뽑혔다 — "가장 짧다"가 곧 "가장 특징적"이 아니기 때문이다.
#
# M9-3(L1) 은 **정렬 키만** 교체한다: 게이트 통과분 중 **hit_docs 가 가장 적은 것** →
# 동률이면 **가장 짧은 것** → 그래도 동률이면 문서 내 먼저 나온 것.
# `hit_docs` 는 여전히 **게이트가 아니라 정렬 키**다(K3). 게이트는 `resolves_to_chunk` 뿐이다.
# 짧은 쪽을 남기는 것은 재청킹 내성이다 — 짧을수록 한 청크 안에 온전히 남을 확률이 높다.
# ══════════════════════════════════════════════════════════════════════════
SENTENCE_BOUNDARY = re.compile(r"(?<=[.?!])\s+|\n")
"""문장 경계 = 종결부호(`.?!`) 뒤 공백 **또는 개행**. M9-2 정의를 그대로 승계한다.
개행을 넣는 이유는 코퍼스가 **개행 구분 목록**(구비서류 나열)을 많이 쓰기 때문이다."""


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """문장별 `(start, end)` 오프셋. 공백만인 조각은 버린다.

    오프셋으로 다루는 이유 — 후보는 반드시 원문의 **연속 슬라이스**여야 부분문자열이 보장된다.
    문장을 문자열로 쪼갠 뒤 이어 붙이면 사이의 공백·개행이 소실돼 원문과 안 맞는다.
    """
    out, prev = [], 0
    for m in SENTENCE_BOUNDARY.finditer(text):
        if text[prev:m.end()].strip():
            out.append((prev, m.end()))
        prev = m.end()
    if text[prev:].strip():
        out.append((prev, len(text)))
    return out


def _trim(text: str, i: int, j: int) -> str:
    """`text[i:j]` 를 앞뒤 공백만 벗겨 반환. **연속 슬라이스라 부분문자열이 보장된다.**"""
    seg = text[i:j]
    return seg.strip()


def pick_anchor(doc_id: str, chunk_id: str, chunks: dict,
                max_len: int = 200, _trace: dict | None = None) -> str | None:
    """청크를 유일하게 지목하는 **가장 특징적인(코퍼스 히트가 적은) 문장**. 없으면 `None`.

    절차 — **선두 고정 없음**:
      (a) 대상 청크를 `SENTENCE_BOUNDARY` 로 분할
      (b) 각 문장을 후보로 (위치 무관)
      (c) `resolves_to_chunk(doc_id, 후보) == chunk_id` 인 것만 남긴다
      (d) 남은 것 중 **hit_docs 가 가장 적은 것** → 동률이면 **가장 짧은 것** →
          그래도 동률이면 **문서 내 먼저 나온 것**
      (e) 없으면 인접 **2개 연결** → 그래도 없으면 **3개 연결**. `max_len` 초과 후보는 버린다
      (f) 끝내 없으면 `None`

    `hit_docs` 는 **게이트가 아니라 정렬 키**다(K3). 게이트는 여전히
    `resolves_to_chunk != None` 하나뿐이다 — M9-3 판정(L1)으로 정렬 키만 교체했다.

    스팬 조인 구분자 `|` 를 포함하는 후보는 **직렬화 불가**이므로 후보에서 제외한다 —
    `format_span` 이 이미 거절하는 계약(M9-3 판정 A)이다. 근거 가치 규칙이 아니다.

    `_trace` 를 주면 후보 총수·통과 수·연결 단계·선택 길이를 채워 넣는다(보고용).
    """
    ch = chunks.get(chunk_id)
    if ch is None:
        return None
    text = ch["text"]
    sp = sentence_spans(text)
    total = passed = 0
    for k in (1, 2, 3):                       # 1문장 → 2연결 → 3연결
        cands = []
        for a in range(len(sp) - k + 1):
            s = _trim(text, sp[a][0], sp[a + k - 1][1])
            if not s or len(s) > max_len:
                continue
            if SPAN_JOIN in s:                # 직렬화 불가 — `|`는 스팬 조인 구분자(M9-3 판정 A)
                continue
            total += 1
            cands.append((len(s), sp[a][0], s))
        hit = [c for c in cands if resolves_to_chunk(doc_id, c[2], chunks) == chunk_id]
        passed += len(hit)
        if hit:
            # M9-3(L1): hit_docs 오름차순 → 길이 오름차순 → 문서 내 먼저 나온 것
            hit.sort(key=lambda c: (len(hit_docs(c[2], chunks)), c[0], c[1]))
            if _trace is not None:
                _trace.update({"cands": total, "passed": passed,
                               "join": k, "length": hit[0][0]})
            return hit[0][2]
    if _trace is not None:
        _trace.update({"cands": total, "passed": passed, "join": None, "length": 0})
    return None

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

    print("\n── occurrences_in_doc / hit_docs / resolves_to_chunk ──")
    d, s = CASES[0]
    print(f"  occurrences_in_doc {occurrences_in_doc(d, s, chunks)}  (게이트: 정확히 1)")
    print(f"  hit_docs {len(hit_docs(s, chunks))}개  (진단값 · 게이트 아님)")
    print(f"  resolves_to_chunk {resolves_to_chunk(d, s, chunks)}")
    ok_u = resolves_to_chunk(d, s, chunks) is not None
    # 게이트가 실제로 막는가 — 없는 스니펫은 None 이어야 한다
    ok_u &= resolves_to_chunk(d, s + "※없는문구", chunks) is None
    print(f"  부재 스니펫 → None: {resolves_to_chunk(d, s + '※없는문구', chunks) is None}")
    if not ok_u:
        fails.append("게이트")

    print()
    if fails:
        print("어긋난 항목 ⛔")
        for f in fails:
            print(f"  {f}")
        sys.exit(1)
    print("전체 통과 ✅  (순수 함수 · 파일 수정 0)")
    sys.exit(0)
