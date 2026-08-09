# -*- coding: utf-8 -*-
"""큐폼 조합 조회 + 조건부 되묻기 — T3.

슬롯(qform_extract.extract 산출)으로 조합 테이블 14행을 좁히고(survivors),
행이 안 좁혀질 때만 되묻고(next_question), 슬롯을 검색 쿼리에 흘린다(serialize).

되묻기 규칙 (D2 / task_assignment T3):
    sub_task is None      → None (되묻지 않음)  ← 단문 오발동 방지의 핵심
    survivors 수 <= 1     → None
    그 외                  → 되물을 수 있는 슬롯 중 가장 고르게 쪼개는 것을 물음
    최대 2턴. 이후에도 미채움이면 None 으로 진행

되물을 수 있는 슬롯 = schema §3-2 조건부 게이트:
    qualification : sub_task == '반환신청' 일 때만 (2순위)
    subject       : qualification == '대리인' 일 때만 (3순위)
    party·method  : **어떤 경로에서도 되묻지 않음**

통합(§3-1, 확정 B안): survivors() 는 attachments.collect() **후단 필터**로 쓴다.
슬롯이 비면 survivors=전체라 기존 동작으로 자연 복귀(graceful degradation).

**문구는 이 파일이 만들지 않는다(T2·E6).** 이 파일은 "어느 슬롯을 물을지"만 정하고,
문장·표시 문구·정렬은 `qform_ask` + `crawler/data/qform_prompts.csv` 가 소유한다.
판정과 표현을 갈라둬야 LLM 모드(ⓑ)를 붙여도 결정론 주장이 유지된다(T3 AC6).
"""
from __future__ import annotations

import csv
import pathlib
import sys

_BASE = pathlib.Path(__file__).resolve().parent.parent
_COMBOS_CSV = _BASE / "crawler" / "data" / "qform_combos_msdr.csv"

if str(_BASE / "chatbot") not in sys.path:
    sys.path.insert(0, str(_BASE / "chatbot"))
import qform_ask  # noqa: E402  (문구 생성 위임 — 이 파일은 판정만 한다)

SLOT_FIELDS = ("party", "sub_task", "qualification", "subject", "method")

# schema §3-2 되묻기 게이트: (슬롯, 발동 조건). 순서 = 우선순위.
_ASK_GATES = [
    ("qualification", lambda s: s.get("sub_task") == "반환신청"),
    ("subject", lambda s: s.get("qualification") == "대리인"),
]


def _load_combos() -> list[dict]:
    with _COMBOS_CSV.open(encoding="utf-8-sig") as fh:  # BOM 방지
        return list(csv.DictReader(fh))


_COMBOS = _load_combos()


def _toks(v) -> set[str]:
    return {t.strip() for t in (v or "").split(";") if t.strip()}


def _field_ok(slot_val, combo_val) -> bool:
    """한 필드에서 슬롯값이 조합행값과 양립하는가.
    슬롯 None → 제약 없음. 조합 공란/'공통' → 와일드카드. 그외 다중값 overlap."""
    if slot_val is None:
        return True
    ct = _toks(combo_val)
    if not ct or "공통" in ct:  # 조합 와일드카드
        return True
    return bool(_toks(slot_val) & ct)


def survivors(slots: dict, combos: list[dict] | None = None) -> list[dict]:
    """슬롯으로 조합 테이블을 좁힌다. '*'/공란/'공통'은 와일드카드,
    다중값(';')은 하나라도 겹치면 매칭. 슬롯이 전부 비면 전체 반환."""
    rows = _COMBOS if combos is None else combos
    return [c for c in rows
            if all(_field_ok(slots.get(f), c[f]) for f in SLOT_FIELDS)]


def _distinct(rows: list[dict], field: str) -> int:
    """rows 를 field 값(다중값 개별 토큰 기준)으로 몇 갈래로 나누는가."""
    vals = set()
    for c in rows:
        vals |= _toks(c[field]) or {""}
    return len(vals)


def _partition_max(rows: list[dict], field: str) -> int:
    """field 로 나눴을 때 가장 큰 그룹 크기 (작을수록 고르게 쪼갬)."""
    from collections import Counter
    cnt = Counter()
    for c in rows:
        for t in (_toks(c[field]) or {""}):
            cnt[t] += 1
    return max(cnt.values()) if cnt else len(rows)


def next_question(slots: dict) -> dict | None:
    """되묻기 **판정**. None 이면 되묻지 않고 바로 검색.

    슬롯 선택까지가 이 함수의 책임이고, 문구는 `qform_ask.build_question()` 이 만든다.
    여기서 붙는 문구는 **템플릿(ⓐ, 콜 0)** 뿐이다 — LLM 모드(ⓑ)는 호출자가
    `build_question(mode="llm")` 을 따로 부른다. 판정 함수가 LLM 을 부르면 안 된다.
    반환: {"slot", "values", "examples", "remaining", "prompt"}
        values    문구에 오른 조합 테이블 값 (표시 문구의 원본)
        examples  표시 문구 (CSV `phrase`)
        prompt    완성 문장
    """
    # D2: sub_task 미채움이면 되묻지 않는다 (단문 오발동 방지)
    if slots.get("sub_task") is None:
        return None
    surv = survivors(slots)
    if len(surv) <= 1:
        return None

    # 되물을 수 있는 슬롯: 게이트 통과 & 아직 None & surv 를 실제로 가르는 것
    eligible = [
        slot for slot, gate in _ASK_GATES
        if gate(slots) and slots.get(slot) is None and _distinct(surv, slot) > 1
    ]
    if not eligible:
        return None  # 더 좁힐 수단 없음 → 진행

    # 가장 고르게 쪼개는 슬롯 (max 그룹 최소화), 동점은 우선순위(_ASK_GATES 순서)
    order = {slot: i for i, (slot, _) in enumerate(_ASK_GATES)}
    slot = min(eligible, key=lambda s: (_partition_max(surv, s), order[s]))

    ask = qform_ask.build_question(slot, slots, surv)   # 문구 생성은 전적으로 위임
    return {"slot": slot, "values": ask["values"], "examples": ask["phrases"],
            "remaining": len(surv), "prompt": ask["text"]}


def serialize(slots: dict) -> str:
    """슬롯 → 검색 쿼리에 덧붙일 문자열 (기획서 §8 ① 쿼리 직렬화).
    비어있지 않은 슬롯 값을 표기순으로 이어붙인다. 다중값은 공백 전개."""
    parts: list[str] = []
    for f in SLOT_FIELDS:
        v = slots.get(f)
        if v:
            parts.extend(t for t in v.split(";") if t.strip())
    return " ".join(parts)


# ══════════════════════════════════════════════════════════════════════════
# 검증 하니스 (python3 chatbot/qform_state.py) — AC 실측 출력
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import json

    from qform_extract import extract   # sys.path 는 위에서 이미 잡았다

    print(f"조합 테이블 {len(_COMBOS)}행 로드\n")

    # ── AC1. 14행 되묻기 시뮬레이션 (0턴7/1턴1/2턴6, 평균0.93 기대) ──────────
    print("── AC1. 14행 되묻기 시뮬레이션 ──")
    from collections import Counter
    turn_dist = Counter()
    detail = []
    for target in _COMBOS:
        slots = {f: None for f in SLOT_FIELDS}
        slots["sub_task"] = target["sub_task"]  # 최소 트리거: sub_task 만 알려짐
        turns = 0
        while turns < 2:  # D2: 최대 2턴
            q = next_question(slots)
            if q is None:
                break
            # 시뮬 응답 = target 행의 해당 슬롯 실제값
            ans = sorted(_toks(target[q["slot"]]) - {"공통"})
            slots[q["slot"]] = ans[0] if ans else target[q["slot"]]
            turns += 1
        turn_dist[turns] += 1
        detail.append((target["combo_id"], target["sub_task"], turns))
    for cid, st, t in detail:
        print(f"  {cid}  {st:8}  {t}턴")
    n = len(_COMBOS)
    avg = sum(t for _, _, t in detail) / n
    exp = {0: 7, 1: 1, 2: 6}
    got = {k: turn_dist.get(k, 0) for k in (0, 1, 2)}
    ok1 = got == exp and abs(avg - 0.93) < 0.005
    print(f"  분포: 0턴 {got[0]}행 / 1턴 {got[1]}행 / 2턴 {got[2]}행 · 평균 {avg:.2f}턴")
    print(f"  기대: 0턴 7 / 1턴 1 / 2턴 6 · 평균 0.93   →  {'OK' if ok1 else 'DIFF ⛔ (멈추고 보고)'}")

    # ── AC2. sub_task=None → next_question 항상 None ────────────────────────
    print("\n── AC2. sub_task=None 이면 next_question 항상 None ──")
    none_cases = [
        {"party": None, "sub_task": None, "qualification": None, "subject": None, "method": None},
        {"party": "송금인", "sub_task": None, "qualification": "대리인", "subject": "법인", "method": "온라인"},
        {"party": "수취인", "sub_task": None, "qualification": None, "subject": "공통", "method": "방문;온라인"},
    ]
    ac2 = all(next_question(c) is None for c in none_cases)
    print(f"  테스트 {len(none_cases)}종 전부 None: {'OK' if ac2 else 'DIFF'}")

    # ── AC3. method 는 어떤 경로에서도 되묻지 않음 ─────────────────────────
    print("\n── AC3. method 는 되묻지 않음 ──")
    asked_slots = set()
    # 시뮬 전 경로 + 부분 채움 조합을 훑어 next_question 이 낸 slot 수집
    probe = []
    for c in _COMBOS:
        for keep in ([], ["qualification"], ["qualification", "subject"]):
            s = {f: None for f in SLOT_FIELDS}
            s["sub_task"] = c["sub_task"]
            for k in keep:
                ans = sorted(_toks(c[k]) - {"공통"})
                s[k] = ans[0] if ans else None
            probe.append(s)
    for s in probe:
        q = next_question(s)
        if q:
            asked_slots.add(q["slot"])
    ac3 = "method" not in asked_slots and "party" not in asked_slots
    print(f"  되물은 슬롯 종류: {sorted(asked_slots)}  → method 없음: {'OK' if ac3 else 'DIFF'}")

    # ── AC4. 450셋 되묻기 발동률 (오발동 지표, 낮을수록 정상) ────────────────
    print("\n── AC4. 450셋 되묻기 발동률 (오발동 지표) ──")
    rows = [json.loads(l) for l in (_BASE / "crawler" / "data" / "testset_natural_450.jsonl").open(encoding="utf-8")]
    fire = fire_ms = 0
    ms_total = 0
    for r in rows:
        slots = extract(r["question"], r["business_function"])
        is_ms = r["business_function"] == "착오송금 반환 신청"
        ms_total += is_ms
        if next_question(slots) is not None:
            fire += 1
            fire_ms += is_ms
    print(f"  전체 450: {fire}건 발동 ({fire/len(rows)*100:.1f}%)")
    print(f"  착오송금 {ms_total}건 중: {fire_ms}건 발동 ({fire_ms/ms_total*100:.1f}%)")
    print(f"  (sub_task=None·타업무는 발동 안 함 → 발동은 '반환신청+미상세'에 국한)")

    # ── AC5. extract() 경유 멀티턴 — 회귀 방지 ──────────────────────────────
    # AC1 은 sub_task 를 직접 주입하므로 추출기를 안 거친다. 그래서 "qualification 을
    # 답하면 subject 까지 같이 박혀 2번째 턴이 죽는" 버그(백필)를 못 잡았다.
    # 여기서는 실제 대화처럼 extract() 를 태워서 2턴이 살아있는지 본다.
    print("\n── AC5. extract() 경유 멀티턴 (2번째 턴 생존 확인) ──")
    Q = "착오송금 반환 신청 서류가 뭐예요?"
    scripted = [
        # (되묻기 응답, 기대 되묻기 슬롯 순서, 기대 최종 생존 행수)
        ("대리인이 신청해요", ["qualification", "subject"], 6),
        ("본인이요", ["qualification"], 1),
    ]
    ac5 = True
    for reply, want_slots, want_surv in scripted:
        slots = {f: v for f, v in extract(Q).items() if f in SLOT_FIELDS}
        asked, turns = [], 0
        while turns < 2:
            nq = next_question(slots)
            if not nq:
                break
            asked.append(nq["slot"])
            merged = extract(f"{Q} {reply}", business_function="착오송금 반환 신청")
            for f in SLOT_FIELDS:                      # 기존 값 보존, 빈 칸만 채움
                if not slots.get(f) and merged.get(f):
                    slots[f] = merged[f]
            turns += 1
        n = len(survivors(slots))
        hit = asked == want_slots and n == want_surv
        ac5 &= hit
        print(f"  '{reply}' → 되물음 {asked} · 생존 {n}행 "
              f"(기대 {want_slots} · {want_surv}행)  {'OK' if hit else 'DIFF'}")
    print("  ※ subject 를 qualification 으로 백필하면 이 AC 가 깨진다 (qform_extract §3 주석)")

    allok = ok1 and ac2 and ac3 and ac5
    print("\n" + ("전체 통과 ✅" if allok else "실패 — 기대치와 불일치 ⛔"))
    sys.exit(0 if allok else 1)
