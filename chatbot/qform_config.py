# -*- coding: utf-8 -*-
"""큐폼 대화 정책 파라미터 — ver3 T2.

**종합 단계의 관리자 콘솔이 읽을 자리를 지금 만들어 둔다.** 이번 스프린트에서 쓰는
경로는 두 개뿐이다 — ① 모듈 기본값 ② 호출자(사이드바·하니스) 오버라이드.
DB·원격 설정 로딩은 이번 범위 밖이며, `resolve()` 가 그 주입점이 된다.

왜 상수를 `qform_flow` 밖으로 빼는가:
- `MAX_ASK_TURNS` 가 `qform_flow` 안에 있으면 값을 바꾸려고 **전이 코드를 건드려야** 한다.
  정책과 전이를 갈라둬야 콘솔이 전이 코드를 모른 채 값만 만질 수 있다.
- T4 하니스가 `SLOT_CARRYOVER=False` 회귀(AC2-5)를 돌리려면 값 주입이 필요하다.

호환: `qform_flow.MAX_ASK_TURNS` 는 **별칭으로 유지**한다(`verify_docs.py` 가 읽는다).

    from qform_config import resolve
    cfg = resolve({"CARRYOVER_TTL": 4})     # 검증 + 기본값 병합
    cfg["CARRYOVER_TTL"]                    # 4
    resolve({"CARRYOVER_TTL": 99})          # 허용범위 밖 → 기본값 3 으로 되돌리고 통과
"""
from __future__ import annotations

# ── 기본값 (task_assignment T2 표) ──────────────────────────────────────────
SLOT_CARRYOVER = True          # 슬롯 이월 사용 여부
CARRYOVER_TTL = 3              # 슬롯이 설정된 후 몇 턴까지 유효한가 (K6: 2→3)
CARRYOVER_SCOPE = "bf_match"   # 업무 전환 시 정책
MAX_ASK_TURNS = 2              # 되묻기 상한 (qform_flow 에서 이관)

MAX_QUEUE = 3                  # '대기 중인 용건' 큐 최대 길이 (K13)
PANEL_EXPIRED = "gray"         # TTL 만료 항목 처리 — 회색 잔류 / 즉시 삭제

SCOPE_VALUES = ("bf_match", "global", "off")
EXPIRED_VALUES = ("gray", "drop")

# 콘솔이 읽을 메타. 라벨·허용값·설명이 코드와 한 곳에 있어야 UI 가 값을 창작하지 않는다.
SPEC: dict[str, dict] = {
    "SLOT_CARRYOVER": {
        "label": "슬롯 이월", "type": "bool", "default": SLOT_CARRYOVER,
        "help": "직전 턴에서 확정된 슬롯을 새 질의에 물려준다. OFF 면 ver2 와 동작이 같다.",
    },
    "CARRYOVER_TTL": {
        "label": "이월 유효 턴", "type": "int", "default": CARRYOVER_TTL, "range": (1, 5),
        "help": "슬롯이 설정된 턴으로부터 몇 턴 뒤까지 물려줄지. 2 면 설정 후 2턴까지.",
    },
    "CARRYOVER_SCOPE": {
        "label": "업무 전환 정책", "type": "enum", "default": CARRYOVER_SCOPE,
        "values": SCOPE_VALUES,
        "help": ("bf_match=업무가 바뀌면 이월 차단(기본) · global=업무 무시하고 이월"
                 "(데모 비교용) · off=이월 안 함"),
    },
    "MAX_ASK_TURNS": {
        "label": "되묻기 상한", "type": "int", "default": MAX_ASK_TURNS, "range": (1, 3),
        "help": "한 질의에서 되물을 수 있는 최대 턴 수. 상한에 닿으면 미채움이어도 진행한다.",
    },
    # ── ver4 M3 메모리 패널 파라미터 ────────────────────────────────────────
    "MAX_QUEUE": {
        "label": "대기 용건 최대", "type": "int", "default": MAX_QUEUE, "range": (0, 5),
        "help": ("다중 의도에서 '대기 중인 용건' 구역에 쌓아 둘 최대 개수. "
                 "0 이면 큐를 쓰지 않는다(ver3 동작)."),
    },
    "PANEL_EXPIRED": {
        "label": "만료 항목 처리", "type": "enum", "default": PANEL_EXPIRED,
        "values": EXPIRED_VALUES,
        "help": ("gray=TTL 만료 항목을 회색으로 남긴다(기본) · drop=화면에서 지운다. "
                 "조용한 삭제는 '아무것도 안 했는데 사라졌다'로 읽혀 기본값이 gray 다."),
    },
}

DEFAULTS: dict = {k: v["default"] for k, v in SPEC.items()}


def validate(values: dict) -> list[tuple[str, object, str]]:
    """허용범위 위반 목록 [(키, 받은값, 사유)]. `resolve()` 가 이걸로 기본값 복귀를 판단한다."""
    bad: list[tuple[str, object, str]] = []
    for key, got in (values or {}).items():
        spec = SPEC.get(key)
        if spec is None:
            bad.append((key, got, "미정의 파라미터"))
            continue
        if spec["type"] == "bool":
            if not isinstance(got, bool):
                bad.append((key, got, "bool 아님"))
        elif spec["type"] == "int":
            lo, hi = spec["range"]
            if not isinstance(got, int) or isinstance(got, bool) or not (lo <= got <= hi):
                bad.append((key, got, f"정수 {lo}~{hi} 밖"))
        elif spec["type"] == "enum":
            if got not in spec["values"]:
                bad.append((key, got, f"허용값 {spec['values']} 밖"))
    return bad


def resolve(override: dict | None = None) -> dict:
    """기본값 + 오버라이드 병합. **허용범위 밖 값은 기본값으로 되돌리고 통과시킨다.**

    예외를 던지지 않는 이유: 이 값은 사이드바(사람 입력)에서도 온다. 잘못된 값 하나로
    대화가 죽는 것보다 기본값으로 돌아가는 쪽이 낫다 — 되돌린 사실은 `_invalid` 로 남긴다.
    """
    cfg = dict(DEFAULTS)
    bad = validate(override or {})
    bad_keys = {k for k, _, _ in bad}
    for key, got in (override or {}).items():
        if key in SPEC and key not in bad_keys:
            cfg[key] = got
    cfg["_invalid"] = bad
    return cfg


# ══════════════════════════════════════════════════════════════════════════
# 자기검사 (python3 chatbot/qform_config.py)
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    fails: list[tuple[str, str, str]] = []
    print("큐폼 대화 정책 파라미터 — 자기검사\n")

    print(f"  {'파라미터':18} {'기본값':10} {'허용값':28} 의미")
    for k, s in SPEC.items():
        allowed = (str(s.get("values")) if s["type"] == "enum"
                   else (f"{s['range'][0]}~{s['range'][1]}" if s["type"] == "int" else "bool"))
        print(f"  {k:18} {str(s['default']):10} {allowed:28} {s['label']}")

    print("\n── AC. 기본값이 명세서 표와 일치 ──")
    WANT = {"SLOT_CARRYOVER": True, "CARRYOVER_TTL": 3,
            "CARRYOVER_SCOPE": "bf_match", "MAX_ASK_TURNS": 2,
            "MAX_QUEUE": 3, "PANEL_EXPIRED": "gray"}
    got = {k: v for k, v in resolve().items() if k != "_invalid"}
    ok_def = got == WANT
    print(f"  {got}\n  기대 {WANT}  → {'OK' if ok_def else 'DIFF ⛔'}")
    if not ok_def:
        fails.append(("기본값", str(WANT), str(got)))

    print("\n── AC. 허용범위 밖 값은 기본값 복귀 (예외 없음) ──")
    CASES = [
        ({"CARRYOVER_TTL": 99}, "CARRYOVER_TTL", 3),
        ({"CARRYOVER_TTL": 0}, "CARRYOVER_TTL", 3),
        ({"CARRYOVER_SCOPE": "무엇"}, "CARRYOVER_SCOPE", "bf_match"),
        ({"MAX_ASK_TURNS": 9}, "MAX_ASK_TURNS", 2),
        ({"SLOT_CARRYOVER": "예"}, "SLOT_CARRYOVER", True),
        ({"MAX_QUEUE": 99}, "MAX_QUEUE", 3),
        ({"PANEL_EXPIRED": "숨김"}, "PANEL_EXPIRED", "gray"),
        ({"없는키": 1}, None, None),
    ]
    ok_clamp = True
    for ov, key, want in CASES:
        c = resolve(ov)
        hit = True if key is None else c[key] == want
        ok_clamp &= hit and bool(c["_invalid"])
        print(f"  {str(ov):28} → {key}={c.get(key)} · 위반기록 {len(c['_invalid'])}건 "
              f"{'OK' if hit else 'DIFF ⛔'}")
    if not ok_clamp:
        fails.append(("범위 클램프", "기본값 복귀", "복귀 실패"))

    print("\n── AC. 정상 오버라이드는 그대로 통과 ──")
    c = resolve({"SLOT_CARRYOVER": False, "CARRYOVER_TTL": 5, "CARRYOVER_SCOPE": "global"})
    ok_ov = (c["SLOT_CARRYOVER"] is False and c["CARRYOVER_TTL"] == 5
             and c["CARRYOVER_SCOPE"] == "global" and not c["_invalid"])
    print(f"  {{'SLOT_CARRYOVER': False, 'CARRYOVER_TTL': 5, 'CARRYOVER_SCOPE': 'global'}}"
          f" → 위반 {len(c['_invalid'])}건  {'OK' if ok_ov else 'DIFF ⛔'}")
    if not ok_ov:
        fails.append(("오버라이드", "그대로 통과", str(c)))

    print("\n── AC. qform_flow.MAX_ASK_TURNS 하위호환 별칭 ──")
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import qform_flow
    ok_alias = qform_flow.MAX_ASK_TURNS == MAX_ASK_TURNS
    print(f"  qform_flow.MAX_ASK_TURNS={qform_flow.MAX_ASK_TURNS} · "
          f"qform_config.MAX_ASK_TURNS={MAX_ASK_TURNS}  → {'OK' if ok_alias else 'DIFF ⛔'}")
    print("  (verify_docs.py 가 qform_flow.MAX_ASK_TURNS 를 읽는다 — 이름을 없애면 깨진다)")
    if not ok_alias:
        fails.append(("별칭", "동일", "불일치"))

    print()
    if fails:
        print("어긋난 AC ⛔")
        for ac, want, gotv in fails:
            print(f"  {ac:12} 기대 {want} · 실측 {gotv}")
        sys.exit(1)
    print("전체 통과 ✅  (LLM 콜 0 — 순수 값 검증)")
    sys.exit(0)
