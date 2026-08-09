# -*- coding: utf-8 -*-
"""큐폼 되묻기 문구 생성 — T2(템플릿 ⓐ).

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
                   mode: str = "template") -> dict:
    """되묻기 문구 1건 생성. **선택지는 생존 행에서만 나온다.**

    반환: {"slot", "text", "values", "phrases", "mode", "uncovered"}
        values     문구에 오른 조합 테이블 값 (표시 문구의 원본)
        phrases    실제 노출 문구
        uncovered  CSV 에 표시 문구가 없어 값 그대로 쓴 항목 (기대 0)
    """
    if mode != "template":
        raise ValueError(f"지원하지 않는 모드: {mode!r} (T2 는 'template' 만)")

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
            "mode": "template", "uncovered": uncovered}


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

    print()
    if fails:
        print("어긋난 AC ⛔")
        print(f"  {'AC':6} {'기대':22} 실측")
        for ac, want, got in fails:
            print(f"  {ac:6} {want:22} {got}")
        sys.exit(1)
    print("전체 통과 ✅  (되묻기 문구 LLM 호출 0 — 템플릿 모드 ⓐ)")
    sys.exit(0)
