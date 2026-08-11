# -*- coding: utf-8 -*-
"""후속 질문 추천 — ver3 T7 B5. **LLM 콜 +0. 전부 결정론.**

답변이 끝난 뒤 "이어서 뭘 물어볼 수 있는지"를 조합 테이블 **잔여 축**에서 뽑는다.
생성 모델을 쓰지 않는 이유는 비용이 아니라 **근거**다 — 모델이 만든 추천은 코퍼스에
없는 절차를 물어보게 만들 수 있고, 그 순간 "근거 있는 안내"라는 주장이 깨진다.
v1 에서 부연 4개가 전부 코퍼스 0청크(창작)로 판명된 이력이 있다(DECISIONS 08-09).

## 값의 출처 (C8 동결 · CLAUDE.md §2-4)

라벨·값은 **`qform_combos_msdr.csv` 생존 행에서만** 온다. 문구를 지어내지 않는다.
`qform_prompts.csv` 에는 `qualification`·`subject` 행밖에 없어 `method`·`sub_task` 의
표시 문구가 **아예 없다.** 그래서 이 모듈은 표시 문구를 만들지 않고 **값 그대로** 넘기며,
사람이 읽을 축 이름(`접수수단` 등)은 화면(`app.py`)이 이미 쓰던 `SLOT_LABEL` 이 붙인다.
판정(여기)과 표현(화면)을 갈라 두는 것은 `qform_state`↔`qform_ask` 와 같은 관행이다.

## 어느 축을 추천하는가

**되묻기가 다루지 않는 축만** 추천한다 — `party` · `sub_task` · `method`.
되묻기는 조합을 **좁히는** 도구(`qualification`·`subject` 만 묻는다, schema §3-2)이고,
후속 추천은 대화를 **이어가는** 도구다. 겹치면 방금 건너뛴 질문을 추천으로 다시 들이민다.

## 커버리지 공백은 정상이다 (§2-5)

조합 테이블은 **14행 = 착오송금 1업무뿐**이다. 다른 업무에서 추천이 **안 뜨는 것이
정상**이며 graceful degradation 이다. 이것을 "커버리지 부족"으로 읽고 다른 업무의
조합 행을 창작하면 안 된다.

    from qform_followup import suggest
    suggest({"party": "송금인", "sub_task": "반환신청", "qualification": "본인",
             "subject": "본인", "method": None}, base_q="착오송금 반환 신청 서류가 뭐예요?")
    # [{"field": "method", "value": "온라인", "query": "착오송금 … 뭐예요? 온라인"}, …]
"""
from __future__ import annotations

import pathlib
import sys

_BASE = pathlib.Path(__file__).resolve().parent.parent
for _p in (_BASE / "chatbot", _BASE / "crawler"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import qform_state  # noqa: E402

SLOT_FIELDS = qform_state.SLOT_FIELDS

# 후속 추천 대상 축 — **되묻기가 건드리지 않는 것들.** 순서 = 추천 우선순위.
# sub_task 가 먼저인 이유: "무엇을 할지"가 "어떻게 접수할지"보다 큰 갈래다.
# 세부주제를 모르는 상태에서 접수수단부터 권하면 순서가 거꾸로다.
FOLLOWUP_FIELDS = ("sub_task", "method", "party")

MAX_SUGGESTIONS = 3     # 명세 T7 B5 — 최대 3개


def _split(value) -> list[str]:
    """다중값(';') 을 **등장 순서 그대로** 나눈다.

    `qform_state._toks()` 를 쓰지 않는 이유: 그건 집합을 돌려주는데, 파이썬은 문자열
    해시를 프로세스마다 무작위화한다(PYTHONHASHSEED). 집합을 순회해 목록을 만들면
    **추천 순서가 실행마다 바뀐다** — 시연이 결정론이라는 주장이 거기서 깨진다.
    """
    return [t.strip() for t in str(value or "").split(";") if t.strip()]


def _values_in(surv: list[dict], field: str) -> list[str]:
    """생존 행이 그 축에서 갖는 값. **조합 테이블 등장 순서 유지**(결정론).
    `'공통'`(와일드카드)과 공란은 값이 아니라 '제약 없음'이라 제외한다."""
    seen: list[str] = []
    for row in surv:
        for tok in _split(row.get(field)):
            if tok != "공통" and tok not in seen:
                seen.append(tok)
    return seen


def suggest(slots: dict, *, base_q: str | None = None,
            max_n: int = MAX_SUGGESTIONS) -> list[dict]:
    """후속 질문 후보. **LLM 콜 0.** 없으면 빈 리스트 — 그것이 오류가 아니라 정상이다.

    반환 항목: {"field": 축, "value": 조합 테이블 값, "query": 클릭 시 보낼 질의}

    query 는 **직전 질의(사용자 본인의 말) + 조합 테이블 값**이다. 값만 보내면
    검색 쿼리가 "온라인" 한 단어가 되어 검색이 망가진다. 여기서 새로 만드는 낱말은 없다 —
    부스트(`qform_state.serialize`)가 슬롯을 쿼리에 덧붙이는 것과 같은 방식이다.
    """
    clean = {f: (slots or {}).get(f) for f in SLOT_FIELDS}
    surv = qform_state.survivors(clean)

    # 아무것도 안 좁혀졌으면 추천하지 않는다.
    #   ① 타 업무·소관 밖은 스코프 게이트로 슬롯이 전부 None → 생존 전체 → 여기서 걸린다(AC7-2)
    #   ② 착오송금이어도 아직 아무 축도 안 정해졌으면 추천은 그냥 목록 나열이라 쓸모가 없다
    if not surv or len(surv) == len(qform_state._COMBOS):
        return []

    out: list[dict] = []
    for field in FOLLOWUP_FIELDS:
        if clean.get(field) is not None:
            continue                       # 이미 정해진 축은 이어갈 것이 없다
        for value in _values_in(surv, field):
            q = f"{base_q} {value}".strip() if base_q else value
            out.append({"field": field, "value": value, "query": q})
            if len(out) >= max_n:
                return out
    return out


# ══════════════════════════════════════════════════════════════════════════
# 자기검사 (python3 chatbot/qform_followup.py) — AC7-1·7-2·7-3 실측
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import itertools

    import qform_trace
    from qform_extract import extract

    classify = qform_trace.rag.classify_query_bf
    COMBOS = qform_state._COMBOS
    TABLE = {f: {t for c in COMBOS for t in _split(c[f])} - {"공통"} for f in SLOT_FIELDS}
    fails: list[tuple[str, str, str]] = []
    Q = "착오송금 반환 신청 서류가 뭐예요?"

    print(f"후속 질문 추천 — 자기검사 (조합 테이블 {len(COMBOS)}행 · 최대 {MAX_SUGGESTIONS}개)\n")

    # ── AC7-1. LLM 진입점 없음 ─────────────────────────────────────────────
    print("── AC7-1 추천 생성 HCX 콜 +0 ──")
    # 하니스 블록은 제외하고 **런타임 코드만** 본다 — 안 그러면 아래 금칙어 목록
    # 자체가 걸려서 자기 자신을 오탐한다.
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    runtime_src = src.split('if __name__ == "__main__":')[0]
    banned = [w for w in ("import chain", "_hcx", "requests") if w in runtime_src]
    ac1 = not banned and "chain" not in sys.modules
    print(f"  모듈 내 LLM 진입점 {banned or '없음'} · chain 로딩={'chain' in sys.modules}"
          f"  → {'OK' if ac1 else 'DIFF ⛔'}")
    if not ac1:
        fails.append(("AC7-1", "콜 +0", str(banned)))

    # ── AC7-2. 착오송금 외 업무는 빈 리스트 (에러가 아니다) ──────────────────
    print("\n── AC7-2 6업무 스모크 — 착오송금 외 빈 리스트 ──")
    SMOKE = [
        ("착오송금 반환 신청", "착오송금 반환 신청 서류가 뭐예요?"),
        ("예금자보호제도", "예금보호한도가 얼마인가요?"),
        ("예금보험금 안내", "예금보험금은 어떻게 신청하나요?"),
        ("고객 미수령금 신청", "미수령금은 어떻게 찾나요?"),
        ("채무조정 안내", "채무조정 신청하려면 어떻게 해요?"),
        ("은닉재산 신고", "은닉재산 신고하면 포상금 얼마나 받나요?"),
        ("(소관 밖)", "오늘 날씨 어때?"),
    ]
    ac2 = True
    print(f"  {'업무':18} {'추천':>4}  값")
    for bf, q in SMOKE:
        s = {f: v for f, v in extract(q, business_function=classify(q)).items()
             if f in SLOT_FIELDS}
        r = suggest(s, base_q=q)
        if bf != "착오송금 반환 신청" and r:
            ac2 = False
        print(f"  {bf:18} {len(r):>4}  {[x['value'] for x in r] or '—'}")
    print(f"  → {'OK' if ac2 else 'DIFF ⛔'}  (안 뜨는 것이 정상 — 조합 테이블 14행 = 1업무, §2-5)")
    if not ac2:
        fails.append(("AC7-2", "타업무 빈 리스트", "추천 발생"))

    # ── AC7-3. 추천 값은 전부 조합 테이블 값 ────────────────────────────────
    print("\n── AC7-3 추천 값 = 조합 테이블 값 (부분채움 격자 전수) ──")
    outside, seen = [], {f: set() for f in SLOT_FIELDS}
    for c in COMBOS:
        for keep in itertools.chain.from_iterable(
                itertools.combinations(SLOT_FIELDS, k) for k in range(len(SLOT_FIELDS) + 1)):
            s = {f: (c[f] or None) if f in keep else None for f in SLOT_FIELDS}
            for it in suggest(s, base_q=Q):
                seen[it["field"]].add(it["value"])
                if it["value"] not in TABLE[it["field"]]:
                    outside.append((it["field"], it["value"]))
    ac3 = not outside
    for f in FOLLOWUP_FIELDS:
        if seen[f]:
            print(f"  {f:10} {sorted(seen[f])}")
    print(f"  테이블 밖 값 {len(outside)}건 (기대 0)  → {'OK' if ac3 else 'DIFF ⛔'}")
    if not ac3:
        fails.append(("AC7-3", "테이블 밖 0", str(outside[:3])))

    # ── 결정론. 값 순서가 실행마다 같아야 한다 ───────────────────────────────
    # `_toks()`(집합)를 쓰면 여기서 깨진다 — 파이썬이 문자열 해시를 무작위화하므로
    # 프로세스마다 추천 순서가 달라진다. `_split()` 로 순서를 보존하는 이유다.
    print("\n── 결정론 — 추천 순서 고정 ──")
    PROBE = {"party": "수취인", "sub_task": None, "qualification": None,
             "subject": None, "method": None}
    seq = [x["value"] for x in suggest(PROBE, base_q=Q)]
    ac4 = seq == [x["value"] for x in suggest(PROBE, base_q=Q)]
    print(f"  {seq}  → {'OK' if ac4 else 'DIFF ⛔'}")
    print("  ※ 프로세스 간 동일성: PYTHONHASHSEED 를 바꿔 재실행해도 같아야 한다")

    print()
    if fails:
        print("어긋난 AC ⛔")
        for ac, want, got in fails:
            print(f"  {ac:8} 기대 {want:18} 실측 {got}")
        sys.exit(1)
    print("전체 통과 ✅  (LLM 콜 0 — 조합 테이블 조회만)")
    sys.exit(0)
