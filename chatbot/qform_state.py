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

# schema §3-2 되묻기 게이트 — **ver4 M6-b: 업무명·sub_task 값 하드코딩을 걷어냈다.**
#
# ver3 까지는 `("qualification", lambda s: s.get("sub_task") == "반환신청")` 이었다.
# 실측해 보면 그 조건은 **MSDR 에서 아무것도 막은 적이 없다** — 조합 테이블에서
# 생존 2행 이상이 되는 `sub_task` 가 `반환신청` 뿐이라 `len(surv) <= 1` 조기 종료와
# 완전히 중복이다. 반면 DPIN(`보험금신청`, 생존 8행 · qual 2갈래 · subject 7갈래)에서는
# **좁힐 여지가 MSDR `반환신청` 과 똑같은데 업무명 하드코딩 하나 때문에 영영 안 물었다.**
# 그래서 오분류된 `반환신청` 경로에서만 발동했다(M5 오발동 6/6).
#
# 이제 게이트 조건은 **데이터에서 나온다**:
#   ① `_NEVER_ASK` — 어떤 경로에서도 안 묻는 슬롯 (스키마 §3-2. 슬롯 이름 정책이지
#      업무·sub_task 값이 아니다)
#   ② `_ASK_ORDER` — 선행 관계. 앞 슬롯이 **아직 미정이고 생존 행을 실제로 가르면**
#      뒤 슬롯은 아직 묻지 않는다. "자격을 정해야 피대리인 유형이 의미가 있다"는 관계를
#      값 하드코딩 없이 표현한다
#   ③ 나머지는 기존 그대로 — 생존 행을 실제로 가르는 슬롯만( `_distinct > 1` ), 아직 안 물은 것만
_NEVER_ASK = ("party", "method")
_ASK_ORDER = ("qualification", "subject")

# 하위호환 별칭 — `docs/records/ARCH_통합_v0.md` §3 실배선표와 `verify_docs.py` AC2 가 이 이름을 읽는다.
_ASK_GATES = [(slot, None) for slot in _ASK_ORDER]


def _eligible_slots(slots: dict, surv: list[dict], done) -> list[str]:
    """되물을 수 있는 슬롯. **조건이 전부 조합 테이블에서 나온다**(M6-b)."""
    out = []
    for i, slot in enumerate(_ASK_ORDER):
        if slot in _NEVER_ASK or slots.get(slot) is not None or slot in done:
            continue
        if _distinct(surv, slot) <= 1:          # 이 슬롯으로는 안 갈린다
            continue
        # 선행 슬롯이 **아직 값이 없고** 생존 행을 가르는 동안에는 뒤 슬롯을 묻지 않는다.
        # `done`(물어봤지만 못 채움)을 예외로 두면 안 된다 — ver3 의 `qualification=='대리인'`
        # 조건이 담고 있던 것이 "자격이 정해지기 전에 피대리인 유형을 묻지 않는다"이고,
        # 물어만 보고 못 채운 상태는 정해진 것이 아니다. 예외를 두면 R1(재질문 0)이 깨진다.
        blocked = any(slots.get(p) is None and _distinct(surv, p) > 1
                      for p in _ASK_ORDER[:i])
        if not blocked:
            out.append(slot)
    return out


def _load_combos() -> list[dict]:
    with _COMBOS_CSV.open(encoding="utf-8-sig") as fh:  # BOM 방지
        return list(csv.DictReader(fh))


_COMBOS = _load_combos()

# ver4 M6-c — 업무별 조합 테이블. 되묻기 판정이 **그 업무의 표**를 보게 한다.
# 기본(bf 불명·미등재)은 MSDR 이라 ver1~M6-b 와 동작이 완전히 같다.
_COMBOS_DPIN_CSV = _BASE / "crawler" / "data" / "qform_combos_dpin.csv"


def _load_csv(path) -> list[dict]:
    try:
        with path.open(encoding="utf-8-sig") as fh:
            lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
        return list(csv.DictReader(lines))
    except (FileNotFoundError, OSError):
        return []


_COMBOS_BY_BF = {
    "착오송금 반환 신청": _COMBOS,
    "예금보험금 안내": _load_csv(_COMBOS_DPIN_CSV),
}


def combos_for(bf=None) -> list[dict]:
    """업무별 조합 테이블. 모르는 업무·불명이면 MSDR(기존 동작)."""
    return _COMBOS_BY_BF.get(bf) or _COMBOS


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


def next_question(slots: dict, exclude: set | None = None,
                  combos: list[dict] | None = None) -> dict | None:
    """되묻기 **판정**. None 이면 되묻지 않고 바로 검색.

    슬롯 선택까지가 이 함수의 책임이고, 문구는 `qform_ask.build_question()` 이 만든다.
    여기서 붙는 문구는 **템플릿(ⓐ, 콜 0)** 뿐이다 — LLM 모드(ⓑ)는 호출자가
    `build_question(mode="llm")` 을 따로 부른다. 판정 함수가 LLM 을 부르면 안 된다.

    exclude: 이미 물었던 슬롯 이름 집합 (ver3 T1). 대화 이력은 이 파일이 들고 있지
        않다 — 호출자(`qform_flow`)가 `state["asked"]` 를 넘긴다. 판정 함수를
        무상태로 두려는 것이고, 그래서 **`exclude=None` 이면 ver2 와 완전히 동일**하다.
        물었는데 답을 못 얻은 슬롯을 후보에서 빼야 같은 질문이 반복되지 않는다.

    반환: {"slot", "values", "examples", "remaining", "prompt"}
        values    문구에 오른 조합 테이블 값 (표시 문구의 원본)
        examples  표시 문구 (CSV `phrase`)
        prompt    완성 문장
    """
    # D2: sub_task 미채움이면 되묻지 않는다 (단문 오발동 방지)
    if slots.get("sub_task") is None:
        return None
    surv = survivors(slots, combos)
    if len(surv) <= 1:
        return None

    # 되물을 수 있는 슬롯: 게이트 통과 & 아직 None & surv 를 실제로 가르는 것
    # & 아직 안 물어본 것 (exclude — 재질문 차단)
    done = exclude or ()
    eligible = _eligible_slots(slots, surv, done)
    if not eligible:
        return None  # 더 좁힐 수단 없음 → 진행

    # 가장 고르게 쪼개는 슬롯 (max 그룹 최소화), 동점은 우선순위(`_ASK_ORDER` 순서)
    order = {slot: i for i, slot in enumerate(_ASK_ORDER)}
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
    print(f"\n── AC4. 450셋 되묻기 발동률 (오발동 지표) · QFORM_SCOPE="
          f"{__import__('qform_config').QFORM_SCOPE} ──")
    rows = [json.loads(l) for l in (_BASE / "crawler" / "data" / "testset_natural_450.jsonl").open(encoding="utf-8")]
    fire = fire_ms = 0
    ms_total = 0
    for r in rows:
        slots = extract(r["question"], r["business_function"])
        is_ms = r["business_function"] == "착오송금 반환 신청"
        ms_total += is_ms
        # ver4 M7 — **업무의 표로 판정한다.** MSDR 표에만 대고 재면 예금보험금 질의가
        # 생존 0행이 되어 발동률이 구조적으로 과소 측정된다(스코프 전환 전에는 동일했다).
        if next_question(slots, combos=combos_for(r["business_function"])) is not None:
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
