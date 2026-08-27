# -*- coding: utf-8 -*-
"""큐폼 되묻기 문구 생성 — T2(템플릿 ⓐ) · T3(LLM ⓑ + 값 고정 가드).

**판정과 문구를 분리한다.** 어느 슬롯을 물을지는 `qform_state.next_question()` 이
결정론으로 정하고(조합 테이블), 이 파일은 **그 판정을 문장으로 바꾸기만** 한다.
LLM 모드(ⓑ)가 붙어도 개입 범위는 이 파일 안쪽 표현 층에 한정된다(T3 AC6).

문구 외부화 (E6 / task_assignment T2):
    v1 은 `qform_state.py` 안에 문장 2개가 상수로 박혀 있어 되묻기가 늘 같은 두 문장이었다.
    이제 문장·표시 문구·근거를 `crawler/data/qform_prompts.csv` 가 소유한다(v3 콘솔 승격 대비).

CSV 컬럼:
    slot            qualification / subject
    sub_task        조건. `*` = 와일드카드 폴백
    prompt_template `{sub_task}` `{qualification}` 등 슬롯값 치환 가능
    value           예시로 쓸 **조합 테이블 값** (행별) — 창작 금지의 앵커
    phrase          그 값의 표시 문구. 부연은 **코퍼스 실재 표현만**
    evidence_chunk  근거 chunk_id (미실재면 공란)

원칙:
- **예시 값은 생존 행에서 추출한다.** CSV 는 문장과 표시 문구·정렬만 담당하며
  선택지 자체를 만들지 않는다. 생존 행에 없는 값은 어떤 경로로도 문구에 오르지 않는다.
- 부연 표현은 코퍼스 실재분만. v1 의 `"비법인단체(동호회 등)"` 는 "동호회" 가
  코퍼스 0청크(창작)라 제거했고, 원문 표현 `"~를 대리하는 경우"` 로 대체했다.
- LLM 호출 0 (템플릿 모드).

LLM 모드 ⓑ (T3):
    **LLM 은 문장을 다듬을 뿐 선택지를 만들지 않는다.** 템플릿 결과를 **항상 먼저** 만들고
    그것을 참고 문장으로 넘긴 뒤, 생성 결과가 가드를 통과할 때만 교체한다. 그래서
    되묻기 **판정**(어느 슬롯·어떤 값)은 두 모드에서 구조적으로 동일하다(AC6).

    가드(생성 직후) — 하나라도 어기면 템플릿으로 폴백하고 사유를 남긴다. 조용히 통과 없음:
        · 전달한 조합 테이블 값이 전부 등장하는가       → missing_value
        · 전달하지 않은 그 슬롯의 값이 등장하는가        → unlisted_value
        · 한 문장인가 / 개행 없는가 / 길이 상한          → multi_sentence · multi_line · too_long
        · 콜 실패 · 예산 소진                          → call_failed · budget_exhausted

    콜 회계는 `chain._llm` 을 재사용해 `chain.CALL_BUDGET` 을 공유한다(별도 예산 금지).
"""
from __future__ import annotations

import csv
import pathlib

_BASE = pathlib.Path(__file__).resolve().parent.parent
_PROMPTS_CSV = _BASE / "crawler" / "data" / "qform_prompts.csv"

WILDCARD = "*"
MAX_EXAMPLES = 3        # 예시 제시형 상한 (v1 동일)


def load_prompts(path: pathlib.Path | None = None) -> list[dict]:
    """CSV 로드. **행 순서를 보존한다** — 예시 노출 순서를 CSV 가 정하기 때문."""
    with (path or _PROMPTS_CSV).open(encoding="utf-8-sig") as fh:  # BOM 방지
        return [r for r in csv.DictReader(fh) if (r.get("slot") or "").strip()]


_ROWS = load_prompts()


class _Blank(dict):
    """`format_map` 용 — 없는 키는 빈 문자열로. 템플릿에 미채움 슬롯이 와도 안 터진다."""

    def __missing__(self, key):
        return ""


def _toks(v) -> set[str]:
    return {t.strip() for t in (v or "").split(";") if t.strip()}


def rows_for(slot: str, sub_task: str | None) -> list[dict]:
    """`slot × sub_task` 행. 없으면 `sub_task='*'` 폴백. CSV 행 순서 그대로."""
    exact = [r for r in _ROWS if r["slot"] == slot and r["sub_task"] == sub_task]
    return exact or [r for r in _ROWS if r["slot"] == slot and r["sub_task"] == WILDCARD]


def survivor_values(slot: str, survivors: list[dict]) -> set[str]:
    """생존 행이 그 슬롯에서 실제로 갖는 값 집합. `'공통'`(와일드카드)은 제외."""
    vals: set[str] = set()
    for c in survivors:
        vals |= _toks(c.get(slot))
    return vals - {"공통"}


def build_question(slot: str, slots: dict, survivors: list[dict],
                   mode: str = "template", llm_call=None) -> dict:
    """되묻기 문구 1건 생성. **선택지는 생존 행에서만 나온다.**

    mode      "template"(ⓐ, 콜 0) | "llm"(ⓑ, 턴당 1콜)
    llm_call  `(messages) -> (text|None, meta)`. 미지정이면 `chain._llm` 사용.
              검증 하니스가 콜 0으로 가드를 전수 시험하기 위한 주입점이다.

    반환: {"slot", "text", "values", "phrases", "mode", "uncovered",
           "calls", "fallback_reason"}
        values           문구에 오른 조합 테이블 값 (표시 문구의 원본)
        phrases          템플릿 표시 문구
        mode             **요청한** 모드 (폴백해도 바뀌지 않는다)
        calls            이 호출이 쓴 LLM 콜 수 (ⓐ 는 항상 0)
        fallback_reason  None 이면 요청 모드대로 성공. 값이 있으면 템플릿으로 폴백된 사유
        uncovered        CSV 에 표시 문구가 없어 값 그대로 쓴 항목 (기대 0)
    """
    if mode not in ("template", "llm"):
        raise ValueError(f"지원하지 않는 모드: {mode!r} ('template' | 'llm')")

    ask = _template_question(slot, slots, survivors)
    if mode == "template":
        return ask
    return _llm_question(ask, slot, slots, llm_call)


def _template_question(slot: str, slots: dict, survivors: list[dict]) -> dict:
    """템플릿 모드 ⓐ — CSV 조회 + 생존 값 치환. LLM 콜 0. ⓑ 의 폴백 기준이기도 하다."""
    vals = survivor_values(slot, survivors)
    rows = rows_for(slot, slots.get("sub_task"))

    # 정렬은 CSV 행 순서 — 서류가 실제로 갈리는 유형을 앞에 두기 위해.
    ordered = [r for r in rows if r["value"] in vals]
    covered = {r["value"] for r in rows}
    uncovered = sorted(v for v in vals if v not in covered)

    picked_vals = [r["value"] for r in ordered] + uncovered
    picked_phr = [(r["phrase"] or r["value"]) for r in ordered] + uncovered
    values, phrases = picked_vals[:MAX_EXAMPLES], picked_phr[:MAX_EXAMPLES]

    template = rows[0]["prompt_template"] if rows else ""
    head = template.format_map(_Blank({k: v for k, v in slots.items()
                                       if isinstance(v, str)})).strip()
    text = f"{head} (예: {', '.join(phrases)})" if phrases else head

    return {"slot": slot, "text": text, "values": values, "phrases": phrases,
            "mode": "template", "uncovered": uncovered, "remaining": len(survivors),
            "calls": 0, "fallback_reason": None}


# ── LLM 모드 ⓑ — 표현 층에만 개입 ───────────────────────────────────────────
ASK_PARAMS = {"temperature": 0.3, "top_p": 0.8, "max_tokens": 128,
              "thinking": {"type": "disabled"}}
MAX_LEN = 140                 # 가드 상한. 프롬프트에는 120자로 지시해 여유를 둔다.

ASK_SYS_PROMPT = (
    "너는 예금보험공사(KDIC) 안내 챗봇이 사용자에게 되물을 문장을 다듬는 역할이다.\n"
    "규칙:\n"
    "1. [보기]에 적힌 값만 쓴다. 새 보기를 만들거나 [보기]에 없는 유형을 덧붙이지 마라.\n"
    "2. [보기]의 값은 글자 그대로 문장에 전부 포함한다. 줄이거나 바꿔 쓰지 마라.\n"
    "3. 한 문장으로 쓴다. 줄바꿈·목록·머리말·설명을 붙이지 마라.\n"
    "4. 공공기관 안내 톤의 존댓말. 120자 이내.\n"
    "5. 되묻는 질문 문장만 출력한다."
)


def _default_llm(messages: list[dict]):
    """기본 호출 경로 — `chain._llm` 재사용. 예산(`chain.CALL_BUDGET`)을 공유한다."""
    import chain                                  # 지연 임포트: ⓐ 모드는 chain 없이도 돈다
    c0 = chain._calls
    text, meta = chain._llm(messages, req_id="qform-ask", params=ASK_PARAMS)
    return text, {**meta, "calls": chain._calls - c0}


def _slot_values(slot: str) -> set[str]:
    """그 슬롯이 가질 수 있는 조합 테이블 값 전체 (CSV 유래 = 테이블 부분집합, AC4 검증)."""
    return {r["value"] for r in _ROWS if r["slot"] == slot}


def _filled_values(slots: dict) -> set[str]:
    """이미 확정된 슬롯 값 — 대화 맥락상 기정사실이라 '새 선택지'로 보지 않는다."""
    out: set[str] = set()
    for v in slots.values():
        if isinstance(v, str):
            out |= _toks(v)
    return out


def guard(text: str | None, slot: str, values: list[str], slots: dict) -> str | None:
    """생성 문구 검증. 통과면 None, 위반이면 **사유 문자열**을 돌려준다.

    값 고정의 핵심은 두 검사다 — 전달한 값이 다 있는가(선택지 삭제 방지),
    전달하지 않은 그 슬롯의 값이 튀어나왔는가(선택지 창작 방지).
    """
    if not text or not text.strip():
        return "empty_response"
    if "\n" in text.strip():
        return "multi_line"
    t = text.strip()
    if len(t) > MAX_LEN:
        return f"too_long:{len(t)}자>{MAX_LEN}"
    if sum(t.count(c) for c in "?!.") > 1:
        return "multi_sentence"

    missing = [v for v in values if v not in t]
    if missing:
        return "missing_value:" + ",".join(missing)

    rest = t
    for v in sorted(values, key=len, reverse=True):   # 긴 값부터 지워야 부분일치 오탐이 없다
        rest = rest.replace(v, "")
    banned = _slot_values(slot) - set(values) - _filled_values(slots)
    hit = sorted(b for b in banned if b in rest)
    if hit:
        return "unlisted_value:" + ",".join(hit)
    return None


def _llm_question(ask: dict, slot: str, slots: dict, llm_call=None) -> dict:
    """ⓑ — 템플릿 결과를 참고 문장으로 넘겨 **문장만** 다듬는다. 위반이면 ⓐ 로 폴백."""
    out = {**ask, "mode": "llm"}
    known = " · ".join(f"{k}={v}" for k, v in slots.items()
                       if isinstance(v, str) and v and k != slot) or "없음"
    user = (f"[묻는 항목] {slot}\n"
            f"[이미 확인된 것] {known}\n"
            f"[남은 후보] {ask.get('remaining', len(ask['values']))}가지\n"
            f"[보기] {' / '.join(ask['values'])}\n"
            f"[참고 문장] {ask['text']}")
    messages = [{"role": "system", "content": ASK_SYS_PROMPT},
                {"role": "user", "content": user}]

    text, meta = (llm_call or _default_llm)(messages)
    out["calls"] = int(meta.get("calls", 1) if meta else 1)

    if meta and meta.get("error") == "call_budget_exhausted":
        out["fallback_reason"] = "budget_exhausted"
        return out
    if text is None:
        out["fallback_reason"] = "call_failed"
        return out

    reason = guard(text, slot, ask["values"], slots)
    if reason:
        out["fallback_reason"] = reason      # 위반 문구는 버린다 — 사용자에게 노출 금지
        return out

    out["text"] = text.strip()
    out["fallback_reason"] = None
    return out


# ══════════════════════════════════════════════════════════════════════════
# 검증 하니스 (python3 chatbot/qform_ask.py) — T2 AC 실측 출력
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import ast
    import json
    import sys
    from collections import Counter

    sys.path.insert(0, str(_BASE / "chatbot"))
    import qform_state
    from qform_extract import extract

    COMBOS = qform_state._COMBOS
    SLOT_FIELDS = qform_state.SLOT_FIELDS
    CHUNKS = _BASE / "crawler" / "data" / "chunks.jsonl"
    fails: list[tuple[str, str, str]] = []

    print(f"되묻기 문구 CSV {len(_ROWS)}행 로드 · 조합 테이블 {len(COMBOS)}행\n")

    # ── AC1. qform_state.py 에 문구 문자열 리터럴 0개 ────────────────────────
    # 판정 로직에 필요한 데이터 리터럴(조합 테이블 값·슬롯명·구분자)은 남아야 한다.
    # 검사 범위 = **런타임 코드**. docstring 과 `__main__` 검증 하니스는 제외한다
    #   (하니스의 print 라벨·테스트 질의는 사용자에게 나가는 되묻기 문구가 아니다).
    # '문구'의 판별 기준: 물음표를 포함하거나, 한글이면서 공백을 포함 = 읽히는 문장.
    print("── AC1. qform_state.py 문구 리터럴 0개 (런타임 코드 한정) ──")
    src = (_BASE / "chatbot" / "qform_state.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    skip: set[int] = set()                       # docstring · __main__ 블록 노드 id
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                skip.add(id(body[0].value))
    def _is_main_guard(t) -> bool:
        return (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
                and t.left.id == "__name__" and len(t.comparators) == 1
                and isinstance(t.comparators[0], ast.Constant)
                and t.comparators[0].value == "__main__")

    for node in tree.body:
        if isinstance(node, ast.If) and _is_main_guard(node.test):
            skip.update(id(s) for s in ast.walk(node))

    def _is_sentence(s: str) -> bool:
        han = any("가" <= ch <= "힣" for ch in s)
        return "?" in s or (han and " " in s)

    lits = [n for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in skip and _is_sentence(n.value)]
    ac1 = not lits
    print(f"  문구로 판정된 리터럴: {len(lits)}개 (기대 0)  → {'OK' if ac1 else 'DIFF ⛔'}")
    for n in lits[:5]:
        print(f"    ✗ L{n.lineno}  {n.value[:50]!r}")
    if not ac1:
        fails.append(("AC1", "문구 리터럴 0개", f"{len(lits)}개"))

    # ── AC2. 14행 되묻기 시뮬레이션 (판정 회귀 가드) ─────────────────────────
    print("\n── AC2. 14행 되묻기 시뮬레이션 (문구를 바꿔도 판정 불변) ──")
    turn_dist = Counter()
    for target in COMBOS:
        s = {f: None for f in SLOT_FIELDS}
        s["sub_task"] = target["sub_task"]
        turns = 0
        while turns < 2:
            q = qform_state.next_question(s)
            if q is None:
                break
            ans = sorted(_toks(target[q["slot"]]) - {"공통"})
            s[q["slot"]] = ans[0] if ans else target[q["slot"]]
            turns += 1
        turn_dist[turns] += 1
    got = {k: turn_dist.get(k, 0) for k in (0, 1, 2)}
    avg = sum(k * v for k, v in turn_dist.items()) / len(COMBOS)
    ac2 = got == {0: 7, 1: 1, 2: 6} and abs(avg - 0.93) < 0.005
    print(f"  0턴 {got[0]} / 1턴 {got[1]} / 2턴 {got[2]} · 평균 {avg:.2f}턴")
    print(f"  기대 0턴 7 / 1턴 1 / 2턴 6 · 0.93  → {'OK' if ac2 else 'DIFF ⛔'}")
    if not ac2:
        fails.append(("AC2", "0턴7/1턴1/2턴6·0.93", f"{got} · {avg:.2f}"))

    # ── AC3. 450셋 되묻기 발동률 (오발동 지표) ───────────────────────────────
    print("\n── AC3. 450셋 되묻기 발동률 ──")
    rows450 = [json.loads(l) for l in
               (_BASE / "crawler" / "data" / "testset_natural_450.jsonl").open(encoding="utf-8")]
    fire = sum(1 for r in rows450
               if qform_state.next_question(extract(r["question"], r["business_function"])) is not None)
    rate = fire / len(rows450) * 100
    ac3 = fire == 9 and abs(rate - 2.0) < 0.05
    print(f"  {fire}건 / {len(rows450)}건 = {rate:.1f}%  (기대 9건 · 2.0%)  → {'OK' if ac3 else 'DIFF ⛔'}")
    if not ac3:
        fails.append(("AC3", "9건 · 2.0%", f"{fire}건 · {rate:.1f}%"))

    # ── AC4. 문구 선택지가 전부 조합 테이블 값 (창작 0) ──────────────────────
    print("\n── AC4. 선택지 = 조합 테이블 값 (창작 0) ──")
    table_vals = {slot: set().union(*[_toks(c[slot]) for c in COMBOS]) - {"공통"}
                  for slot in ("qualification", "subject")}
    bad_csv = [(r["slot"], r["value"]) for r in _ROWS
               if r["value"] not in table_vals.get(r["slot"], set())]
    # 실제 생성 경로에서 나온 선택지도 전수 확인 (14행 시뮬 + 450셋 발동분)
    seen_vals, seen_uncov = set(), []
    def _walk(slots0):
        s = dict(slots0)
        for _ in range(2):
            nq = qform_state.next_question(s)
            if nq is None:
                return
            ask = build_question(nq["slot"], s, qform_state.survivors(s))
            seen_vals.update(ask["values"])
            seen_uncov.extend(ask["uncovered"])
            vs = sorted(survivor_values(nq["slot"], qform_state.survivors(s)))
            s[nq["slot"]] = vs[0] if vs else None
            if s[nq["slot"]] is None:
                return
    for c in COMBOS:
        _walk({**{f: None for f in SLOT_FIELDS}, "sub_task": c["sub_task"]})
    for r in rows450:
        _walk({f: v for f, v in extract(r["question"], r["business_function"]).items()
               if f in SLOT_FIELDS})
    bad_gen = sorted(v for v in seen_vals
                     if not any(v in tv for tv in table_vals.values()))
    ac4 = not bad_csv and not bad_gen and not seen_uncov
    print(f"  CSV value 중 조합 테이블 밖: {len(bad_csv)}건 · "
          f"생성 문구 선택지 {len(seen_vals)}종 중 테이블 밖: {len(bad_gen)}건 · "
          f"표시 문구 미등록: {len(set(seen_uncov))}건  → {'OK' if ac4 else 'DIFF ⛔'}")
    for x in (bad_csv + [("생성", v) for v in bad_gen])[:5]:
        print(f"    ✗ {x}")
    if not ac4:
        fails.append(("AC4", "창작 0", f"CSV {len(bad_csv)} · 생성 {len(bad_gen)} · 미등록 {len(set(seen_uncov))}"))

    # ── AC5. evidence_chunk 실재 ────────────────────────────────────────────
    print("\n── AC5. evidence_chunk 실재 (또는 공란) ──")
    chunks = {json.loads(l)["chunk_id"]: json.loads(l) for l in CHUNKS.open(encoding="utf-8")}
    missing = sorted({r["evidence_chunk"] for r in _ROWS
                      if r["evidence_chunk"] and r["evidence_chunk"] not in chunks})
    blank = sum(1 for r in _ROWS if not r["evidence_chunk"])
    ac5 = not missing
    print(f"  앵커 {len({r['evidence_chunk'] for r in _ROWS if r['evidence_chunk']})}종 · "
          f"미실재 {len(missing)}건 · 공란 {blank}행  → {'OK' if ac5 else 'DIFF ⛔'}")
    for m in missing[:5]:
        print(f"    ✗ 미실재 {m}")
    if not ac5:
        fails.append(("AC5", "미실재 0", f"{len(missing)}건"))

    # ── AC6. 부연 표현 코퍼스 실재 판정 ─────────────────────────────────────
    print("\n── AC6. 부연 표현 코퍼스 실재 판정 ──")
    print(f"  {'slot':13} {'조합값':13} {'표시 문구':26} {'부연':16} 판정")
    for r in _ROWS:
        if r["sub_task"] != "*" and any(  # 같은 (slot,value) 중복 출력 방지
                x["slot"] == r["slot"] and x["value"] == r["value"] and x["sub_task"] == "*"
                for x in _ROWS):
            continue
        phrase, value = r["phrase"], r["value"]
        extra = phrase.replace(value, "").strip() or "—"
        ev = chunks.get(r["evidence_chunk"], {}).get("text", "")
        if phrase == value:
            verdict = "부연 없음(값 그대로)"
        elif phrase in ev:
            verdict = "✅ 원문 실재"
        elif extra != "—" and any(extra in c["text"] for c in chunks.values()):
            verdict = "△ 패턴 실재·값 표기 상이"
        else:
            verdict = "✗ 코퍼스 미실재"
        print(f"  {r['slot']:13} {value:13} {phrase:26} {extra:16} {verdict}")

    print("\n  [v1 하드코딩 부연 표현 — 코퍼스 판정과 처리]")
    print(f"  {'v1 문구':22} {'부연부':10} {'코퍼스':>7}  {'판정':14} 현재 문구")
    V1 = [("qualification", "본인", "본인이 직접 신청", "직접 신청"),
          ("qualification", "대리인", "대리인이 대신 신청", "대신 신청"),
          ("subject", "비법인단체", "비법인단체(동호회 등)", "동호회"),
          ("subject", "국외거주 또는 유학생", "국외거주·유학생", "국외거주·유학생")]
    for slot, value, v1phrase, probe in V1:
        n = sum(1 for c in chunks.values() if probe in c["text"])
        now = next((r["phrase"] for r in _ROWS if r["slot"] == slot and r["value"] == value), "—")
        verdict = "✗ 미실재(창작)" if n == 0 else "✅ 실재"
        act = "그대로 유지" if now == v1phrase else f"→ {now}"
        print(f"  {v1phrase:22} {probe:10} {n:>5}청크  {verdict:14} {act}")
    print("  ※ \"동호회\"는 코퍼스 0청크 = 창작이었다. 원문은 \"비법인단체를 대리하는 경우\"(#05)")
    print("  ※ 조합값 \"국외거주 또는 유학생\"의 코퍼스 원문 표기는 \"해외거주자\"(#09) — 표기 상이")

    # ── 실제 생성 문구 샘플 ─────────────────────────────────────────────────
    print("\n── 생성 문구 샘플 (2턴 대화) ──")
    demo = {f: None for f in SLOT_FIELDS}
    demo.update(extract("착오송금 반환 신청 서류가 뭐예요?", "착오송금 반환 신청"))
    demo = {f: demo.get(f) for f in SLOT_FIELDS}
    for turn in (1, 2):
        nq = qform_state.next_question(demo)
        if nq is None:
            break
        print(f"  {turn}턴 [{nq['slot']}·생존 {nq['remaining']}행]  {nq['prompt']}")
        demo[nq["slot"]] = "대리인" if nq["slot"] == "qualification" else "법인"
    print(f"  → 최종 생존 {len(qform_state.survivors(demo))}행")

    # ══════════════════════════════════════════════════════════════════════
    # T3 — LLM 모드 ⓑ + 값 고정 가드 (기본 실행은 **콜 0**. 실콜은 --live)
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 68)
    print("T3 — 되묻기 LLM 모드 ⓑ · 값 고정 가드")
    print("═" * 68)

    # 되묻기가 실제로 걸리는 상태 2종 (1턴·2턴)
    S1 = {f: None for f in SLOT_FIELDS}
    S1.update({k: v for k, v in extract("착오송금 반환 신청 서류가 뭐예요?",
                                        "착오송금 반환 신청").items() if k in SLOT_FIELDS})
    S2 = {**S1, "qualification": "대리인"}
    SCENES = [("1턴 qualification", S1), ("2턴 subject", S2)]

    calls_seen = [0]

    def stub(reply=None, *, error=None, calls=1):
        """주입용 가짜 LLM. 실제 콜 0으로 가드 전 분기를 시험한다."""
        def _call(messages):
            calls_seen[0] += 1
            return reply, {"error": error, "calls": calls}
        return _call

    # ── AC1. ⓐ 모드는 LLM 콜 0 ──────────────────────────────────────────────
    print("\n── AC1. ⓐ 템플릿 모드 LLM 콜 0 ──")
    calls_seen[0] = 0
    tmpl_calls = 0
    for name, s in SCENES:
        nq = qform_state.next_question(s)
        a = build_question(nq["slot"], s, qform_state.survivors(s),
                           mode="template", llm_call=stub("호출되면 안 된다"))
        tmpl_calls += a["calls"]
    # next_question() 경로도 확인 — 판정 함수가 LLM 을 부르면 안 된다
    for _, s in SCENES:
        qform_state.next_question(s)
    ac1b = calls_seen[0] == 0 and tmpl_calls == 0
    print(f"  llm_call 실제 호출 {calls_seen[0]}회 · 보고된 calls 합 {tmpl_calls} (기대 0/0)"
          f"  → {'OK' if ac1b else 'DIFF ⛔'}")
    if not ac1b:
        fails.append(("T3-AC1", "ⓐ 콜 0", f"{calls_seen[0]}회"))

    # ── AC2. ⓑ 모드 되묻기 턴당 콜 1 ────────────────────────────────────────
    print("\n── AC2. ⓑ 모드 턴당 콜 정확히 1 ──")
    calls_seen[0] = 0
    good = {"qualification": "반환신청은 본인이 하시나요, 아니면 대리인이 하시나요?",
            "subject": "법인, 비법인단체, 미성년자 중 누구를 대리해 신청하시는지 알려주시겠어요?"}
    per_turn, ac2_ok = [], True
    for name, s in SCENES:
        nq = qform_state.next_question(s)
        r = build_question(nq["slot"], s, qform_state.survivors(s),
                           mode="llm", llm_call=stub(good[nq["slot"]]))
        per_turn.append((name, r["calls"], r["fallback_reason"]))
        ac2_ok &= (r["calls"] == 1 and r["fallback_reason"] is None)
        print(f"  {name:18} 콜 {r['calls']} · 폴백 {r['fallback_reason']} · \"{r['text'][:44]}…\"")
    print(f"  총 {calls_seen[0]}콜 / 되묻기 2턴  → {'OK' if ac2_ok else 'DIFF ⛔'}")
    if not ac2_ok:
        fails.append(("T3-AC2", "턴당 콜 1·폴백 없음", str(per_turn)))

    # ── AC3. 가드 위반 → 100% 템플릿 폴백 ───────────────────────────────────
    print("\n── AC3. 가드 위반 시 템플릿 폴백 (위반 문구 미노출) ──")
    s = S2                                   # subject 되묻기 (보기 = 법인·비법인단체·미성년자)
    nq = qform_state.next_question(s)
    surv = qform_state.survivors(s)
    tmpl = build_question(nq["slot"], s, surv, mode="template")["text"]
    CASES = [
        ("값 누락", "법인, 비법인단체 중 누구를 대리해 신청하시나요?", "missing_value"),
        ("목록 밖 값 창작", "법인, 비법인단체, 미성년자, 군복무자 중 누구를 대리하시나요?", "unlisted_value"),
        ("두 문장", "법인, 비법인단체, 미성년자 중 하나를 고르세요. 어느 쪽인가요?", "multi_sentence"),
        ("개행·목록", "누구를 대리하시나요?\n- 법인\n- 비법인단체\n- 미성년자", "multi_line"),
        ("길이 초과", "법인, 비법인단체, 미성년자 " + "안내해 드리겠습니다 " * 25 + "?", "too_long"),
        ("빈 응답", "   ", "empty_response"),
        ("콜 실패", None, "call_failed"),
    ]
    ac3 = True
    print(f"  {'위반 유형':16} {'기대 사유':16} {'실측 사유':22} 노출 문구")
    for label, reply, want in CASES:
        r = build_question(nq["slot"], s, surv, mode="llm", llm_call=stub(reply))
        got = r["fallback_reason"] or "—"
        hit = got.split(":")[0] == want and r["text"] == tmpl
        ac3 &= hit
        print(f"  {label:16} {want:16} {got[:22]:22} {'템플릿✅' if r['text'] == tmpl else '위반문구✗'}")
    # 예산 소진
    r = build_question(nq["slot"], s, surv, mode="llm",
                       llm_call=stub(None, error="call_budget_exhausted", calls=0))
    bud = r["fallback_reason"] == "budget_exhausted" and r["text"] == tmpl
    ac3 &= bud
    print(f"  {'예산 소진':16} {'budget_exhausted':16} {r['fallback_reason'][:22]:22} "
          f"{'템플릿✅' if r['text'] == tmpl else '위반문구✗'}")
    print(f"  → {'OK' if ac3 else 'DIFF ⛔'}  (폴백 {len(CASES) + 1}종 전부 템플릿 복귀)")
    if not ac3:
        fails.append(("T3-AC3", "위반 전건 폴백", "일부 미폴백"))

    # 가드가 정상 문장을 물지 않는지 (과탐지 회귀) — 템플릿 문구 자기 검사
    print("\n  [가드 과탐지 확인] 템플릿 문구 자신이 가드를 통과하는가")
    over = []
    for name, sc in SCENES:
        q = qform_state.next_question(sc)
        a = build_question(q["slot"], sc, qform_state.survivors(sc), mode="template")
        v = guard(a["text"], q["slot"], a["values"], sc)
        over.append((name, v))
        print(f"    {name:18} {'통과 ✅' if v is None else '오탐 ✗ ' + v}")
    ac3b = all(v is None for _, v in over)
    if not ac3b:
        fails.append(("T3-AC3b", "템플릿 문구 가드 통과", str(over)))

    # ── AC4. 폴백 사유가 트레이스에 실릴 형태로 남는가 ───────────────────────
    print("\n── AC4. 폴백 사유 기록 (트레이스 필드) ──")
    r_ok = build_question(nq["slot"], s, surv, mode="llm", llm_call=stub(good["subject"]))
    r_fb = build_question(nq["slot"], s, surv, mode="llm", llm_call=stub("법인만 알려주세요?"))
    ac4b = (r_ok["mode"] == "llm" and r_ok["fallback_reason"] is None
            and r_fb["mode"] == "llm" and r_fb["fallback_reason"].startswith("missing_value")
            and all(k in r_fb for k in ("mode", "calls", "fallback_reason")))
    print(f"  성공: ask_mode={r_ok['mode']} · ask_calls={r_ok['calls']} · fallback={r_ok['fallback_reason']}")
    print(f"  폴백: ask_mode={r_fb['mode']} · ask_calls={r_fb['calls']} · fallback={r_fb['fallback_reason']}")
    print(f"  (요청 모드는 폴백해도 'llm' 로 남는다 — 패널에서 ⓐ/ⓑ 구별 가능)  → {'OK' if ac4b else 'DIFF ⛔'}")
    if not ac4b:
        fails.append(("T3-AC4", "사유 기록", str(r_fb.get("fallback_reason"))))

    # ── AC5. 모드 전환이 대화 상태를 깨지 않음 ──────────────────────────────
    print("\n── AC5. 모드 전환 시 슬롯·생존 행 불변 ──")
    import copy
    ac5 = True
    for name, sc in SCENES:
        before_s, before_v = copy.deepcopy(sc), copy.deepcopy(qform_state.survivors(sc))
        q = qform_state.next_question(sc)
        for m, cb in (("template", None), ("llm", stub(good[q["slot"]])), ("llm", stub("깨진 응답"))):
            build_question(q["slot"], sc, qform_state.survivors(sc), mode=m, llm_call=cb)
        same = sc == before_s and qform_state.survivors(sc) == before_v
        ac5 &= same
        print(f"  {name:18} 3회 전환 후 슬롯·생존 행 불변: {'OK' if same else 'DIFF ⛔'}")
    if not ac5:
        fails.append(("T3-AC5", "상태 불변", "슬롯/생존 변형"))

    # ── AC6. 판정은 두 모드에서 동일 — 문구만 다름 ──────────────────────────
    print("\n── AC6. 판정 동일 (14행 전수 · 슬롯·값·생존 수) ──")
    diff = []
    for c in COMBOS:
        st = {**{f: None for f in SLOT_FIELDS}, "sub_task": c["sub_task"]}
        for _ in range(2):
            q = qform_state.next_question(st)
            if q is None:
                break
            sv = qform_state.survivors(st)
            a = build_question(q["slot"], st, sv, mode="template")
            b = build_question(q["slot"], st, sv, mode="llm",
                               llm_call=stub(good.get(q["slot"], "법인, 비법인단체, 미성년자 중 누구를 대리하시나요?")))
            if (a["slot"], a["values"], a["remaining"]) != (b["slot"], b["values"], b["remaining"]):
                diff.append((c["combo_id"], q["slot"]))
            vs = sorted(survivor_values(q["slot"], sv))
            st[q["slot"]] = vs[0] if vs else None
            if st[q["slot"]] is None:
                break
    ac6 = not diff
    print(f"  14행 전수 · 판정(slot·values·remaining) 불일치 {len(diff)}건 (기대 0)"
          f"  → {'OK' if ac6 else 'DIFF ⛔'}")
    print("  (LLM 은 text 만 바꾼다 — 어느 슬롯을 어떤 값으로 물을지는 조합 테이블이 정한다)")
    if not ac6:
        fails.append(("T3-AC6", "판정 불일치 0", f"{len(diff)}건"))

    print(f"\n  이 구간 실제 LLM 콜: 0 (전부 주입 스텁) · chain 미임포트")

    # ── --live: 선택된 LLM 스모크 (되묻기 2턴 = 2콜) ────────────────────────
    if "--live" in sys.argv:
        print(f"\n── [--live] 실제 {chain.LLM_PROVIDER} 되묻기 생성 (2콜 예정) ──")
        import chain
        c0 = chain._calls
        for name, sc in SCENES:
            q = qform_state.next_question(sc)
            r = build_question(q["slot"], sc, qform_state.survivors(sc), mode="llm")
            print(f"  {name:18} 콜 {r['calls']} · 폴백 {r['fallback_reason']}")
            print(f"    ⓐ {build_question(q['slot'], sc, qform_state.survivors(sc))['text']}")
            print(f"    ⓑ {r['text']}")
        print(f"  누적 {chain.LLM_PROVIDER} 콜 {chain._calls} / 예산 {chain.CALL_BUDGET} (이번 구간 +{chain._calls - c0})")
        if chain._calls >= chain.CALL_BUDGET:
            print("  ⛔ 예산 소진 — 즉시 중단하고 보고할 것")
    else:
        print("\n  실제 LLM 스모크는 생략됨. 환경이 준비된 곳에서:")
        print("    python3 chatbot/qform_ask.py --live      # 되묻기 2턴 = LLM 2콜")

    print()
    if fails:
        print("어긋난 AC ⛔")
        print(f"  {'AC':8} {'기대':22} 실측")
        for ac, want, got in fails:
            print(f"  {ac:8} {want:22} {got}")
        sys.exit(1)
    print("전체 통과 ✅  (ⓐ 콜 0 · ⓑ 턴당 1콜 · 가드 8종 전부 템플릿 폴백)")
    sys.exit(0)
