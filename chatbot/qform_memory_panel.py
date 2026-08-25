# -*- coding: utf-8 -*-
"""메모리 패널 — ver4 M3. **맥락을 LLM 에 숨기지 않고 화면에 꺼내 사용자가 고친다.**

`qform_panel.py`(T6 트레이스 패널)와 **다른 물건이다.** 저쪽은 "한 질의가 어느 층에서
갈렸는가"를 보여주는 진단 화면이고, 이쪽은 "지금 시스템이 무엇을 기억하고 있고
그중 무엇이 실제로 답을 바꾸는가"를 보여주고 **편집시키는** 화면이다. `qform_panel.py`
는 이번 스프린트 동결이라 여기에 얹지 않는다(M0 판정 3).

설계 원칙:
- **streamlit 을 모른다.** 이 파일은 화면 모델(`panel_model`)과 조작(`apply`)만 만든다.
  렌더는 `app.py` 가 얇게 얹는다. 갈라둔 이유는 T4·T6 과 같다 — UI 없이 실측해야 한다.
- **소비처는 A(표시 전용) 고정.** 쿼리 직렬화(B)는 G13 에 걸리고, 생성 프롬프트 주입(C)은
  C1·C2 위반이다. `기억만 함` 구역의 항목은 **이월 허용 여부만** 바꾼다.
- **추가 LLM 콜 0.** 이 파일은 `answer()` 를 어떤 경로로도 부르지 않는다.
- **화면이 거짓말하지 않게 한다.** 모든 항목에 `effect`(고치면 무엇이 바뀌는가)를 달고,
  바뀌는 게 없으면 `actionable=False` 로 내려 회색 처리 대상임을 표시한다.
"""
from __future__ import annotations

import csv
import pathlib
import sys

_BASE = pathlib.Path(__file__).resolve().parent.parent
for _p in (_BASE / "chatbot", _BASE / "crawler"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import qform_config  # noqa: E402
import qform_flow  # noqa: E402
import qform_state  # noqa: E402
from qform_extract import extract  # noqa: E402

SLOT_FIELDS = qform_state.SLOT_FIELDS

# ── 구역 라벨. **task_assignment §3-1 표의 문구와 글자 그대로 일치해야 한다(A3-1).** ──
ZONE_APPLIED = "적용 중"
ZONE_REMEMBERED = "기억만 함"
ZONE_QUEUED = "대기 중인 용건"
ZONES = (ZONE_APPLIED, ZONE_REMEMBERED, ZONE_QUEUED)

# 상태 배지
ST_ACTIVE = "적용"
ST_EXPIRED = "만료"                      # TTL 초과 — 회색 잔류, 조용한 삭제 금지
ST_NOT_APPLICABLE = "이 업무엔 적용 안 됨"   # bf_match 방벽이 막은 축

# 업무별 조합 테이블 (attachments 와 같은 원천. 여기서는 **축 사용 여부**만 읽는다)
COMBO_TABLES = {
    "착오송금 반환 신청": _BASE / "crawler" / "data" / "qform_combos_msdr.csv",
    "예금보험금 안내": _BASE / "crawler" / "data" / "qform_combos_dpin.csv",
}

SLOT_LABEL = {"party": "역할", "sub_task": "세부 용건", "qualification": "자격",
              "subject": "주체", "method": "신청 수단"}

# 고치면 실제로 바뀌는 것 (§3-1). 화면에 그대로 노출한다.
SLOT_EFFECT = "첨부 후단 필터 · 되묻기 판정"
BF_EFFECT = "이월 허용 여부만 (검색·생성 불개입)"
DOC_EFFECT = "없음 — 표시 전용"
QUEUE_EFFECT = "처리 순서 · 큐 제외"

_table_cache: dict | None = None


def _load_tables() -> dict:
    """bf -> 조합행. `#` 주석행은 건너뛴다(dpin CSV 머리의 party 미사용 사유)."""
    global _table_cache
    if _table_cache is None:
        out = {}
        for bf, path in COMBO_TABLES.items():
            try:
                with path.open(encoding="utf-8-sig") as fh:
                    lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
                out[bf] = list(csv.DictReader(lines))
            except (FileNotFoundError, OSError):
                continue
        _table_cache = out
    return _table_cache


def used_slots(bf: str | None) -> tuple[str, ...]:
    """그 업무의 조합 테이블이 **실제로 쓰는 축**만 반환한다.

    빈 축을 패널에 남기면 사용자가 채울 수 있는 것처럼 보이고, 그 자리에 오추출이
    들어앉는다(규칙6). 예금보험금은 `party` 가 전 행 공란이라 여기서 빠진다(M2 판정 1).
    업무를 모르면 전 축을 보여준다 — 숨기는 쪽이 더 위험하다.
    """
    rows = _load_tables().get(bf)
    if not rows:
        return tuple(SLOT_FIELDS)
    return tuple(f for f in SLOT_FIELDS if any((r.get(f) or "").strip() for r in rows))


# ══════════════════════════════════════════════════════════════════════════
# 다중 의도 감지 (K13) — 결정론. LLM 콜 0
# ══════════════════════════════════════════════════════════════════════════
_SPLIT_TOKENS = ("그리고", "이랑", "랑 ", "하고 ", " 및 ", ",", "또한", "그리구")
CROSS_PROMPT_HEAD = "말씀하신 내용에 두 가지 제도가 걸쳐 있습니다. 나눠서 안내드릴게요."


def split_clauses(query: str) -> list[str]:
    """접속 표지로 절을 가른다. 표지가 없으면 통짜 1개."""
    parts = [query]
    for tok in _SPLIT_TOKENS:
        nxt = []
        for p in parts:
            nxt.extend(x for x in p.split(tok) if x.strip())
        parts = nxt
    return [p.strip() for p in parts if p.strip()]


def bf_scores(query: str) -> dict:
    """업무별 키워드 점수. **`rag.BF_QUERY_KEYWORDS` 를 읽기만 한다** (rag.py 동결).

    `classify_query_bf()` 는 1등 하나만 돌려주므로 "두 업무가 동시에 걸렸다"를 못 본다.
    교차 판정은 순위가 아니라 **동시 득점**이 필요해서 원천 표를 직접 채점한다.
    """
    try:
        import rag
    except Exception:
        return {}
    q = query.replace(" ", "")
    return {bf: sum(w * q.count(k.replace(" ", "")) for k, w in kws)
            for bf, kws in rag.BF_QUERY_KEYWORDS.items()}


def cross_bfs(query: str, *, score_fn=None) -> list[str]:
    """동시에 득점한 업무 목록(점수 내림차순). 2개 이상이면 **복합형 의심**이다.

    문턱은 `rag.QBF_MIN_SCORE` 를 그대로 쓴다 — 분류기가 "이 정도면 이 업무"라고 본
    기준을 교차 판정에서 낮추면 오발동이 폭증한다.
    """
    scores = (score_fn or bf_scores)(query)
    if not scores:
        return []
    try:
        import rag
        floor = rag.QBF_MIN_SCORE
    except Exception:
        floor = 1
    hit = [(bf, sc) for bf, sc in scores.items() if sc >= floor]
    return [bf for bf, _ in sorted(hit, key=lambda x: -x[1])]


def detect_intents(query: str, *, classify_fn=None, score_fn=None, scope=None) -> dict:
    """질의에서 의도를 뽑는다. **union 병합을 하지 않기 위한 감지**다(K13).

    **`sub_task` 는 절 단위로 `extract()` 를 다시 돌려 모은다.** 새 우선순위를 만들지 않고
    기존 추출기의 규칙 순서를 재사용하는 것이 핵심이다 — `_SUBTASK_RULES` 를 직접 훑어
    전부 모으면 **`제도안내` 가 같이 걸린다.** 그 규칙은 주석이 밝히듯 `fallback` 이고
    어휘가 넓어서("뭐예요"·"절차"·"얼마"), 단일 의도 질의도 전부 다중으로 오판한다
    (CLAUDE.md §6 함정).

    병렬형 판정 — **둘 다** 만족해야 한다. 오발동이 미발동보다 해롭다(규칙6):
      ① 접속 표지로 절이 **2개 이상**으로 갈린다
      ② 절별 `sub_task` 가 **2종 이상 서로 다르다**

    교차형 판정 — **절 분리에 기대지 않는다.** "착오송금 신청했는데 그 은행이 파산하면…"
    처럼 접속 표지 없이 두 제도가 걸리는 문장이 정확히 이 유형이라, 절을 못 가르면 놓친다.
    대신 `rag.BF_QUERY_KEYWORDS` 로 **동시 득점한 업무 수**를 본다(`cross_bfs`).

    반환 `{"clauses", "per_clause", "sub_tasks", "bfs", "kind": "single|parallel|cross"}`
    """
    clauses = split_clauses(query)
    sub_tasks: list[str] = []
    per_clause: list[tuple[str, str | None]] = []
    for cl in clauses:
        st = extract(cl, None, scope=scope).get("sub_task")
        per_clause.append((cl, st))
        if st and st not in sub_tasks:
            sub_tasks.append(st)                      # 발화 순서 · 중복 제거

    bfs = cross_bfs(query, score_fn=score_fn) if (score_fn or classify_fn) else []
    if classify_fn is not None and not bfs:
        for cl in clauses:                            # 폴백 — 점수표가 없을 때
            b = classify_fn(cl)
            if b and b not in bfs:
                bfs.append(b)

    multi = len(clauses) >= 2 and len(sub_tasks) >= 2
    kind = "single"
    if len(bfs) >= 2:
        kind = "cross"          # 복합형 의심 — 순서를 되묻는다
    elif multi:
        kind = "parallel"       # 병렬형 — 1번째 처리, 나머지 큐
    return {"clauses": clauses, "per_clause": per_clause,
            "sub_tasks": sub_tasks, "bfs": bfs, "kind": kind}


def cross_prompt(bfs: list[str]) -> str:
    """업무 교차 되묻기 문구. **`나눠서 안내드릴게요` 가 핵심이다** — 못 알아들어서
    묻는 게 아니라 분리해서 정확히 답하려고 묻는 것임을 드러낸다(K13).
    선택지는 감지된 업무명 그대로다. 창작 문구를 붙이지 않는다."""
    return CROSS_PROMPT_HEAD


# ══════════════════════════════════════════════════════════════════════════
# 큐 조작 (§3-4) — state["queue"] 리스트 1개
# ══════════════════════════════════════════════════════════════════════════
def enqueue(state: dict, items: list[dict], *, config=None) -> list[dict]:
    """대기 용건 적재. `MAX_QUEUE` 를 넘으면 넘치는 만큼 버린다(조용히 늘지 않게)."""
    cfg = qform_config.resolve(config)
    q = state.setdefault("queue", [])
    for it in items:
        if len(q) >= cfg["MAX_QUEUE"]:
            break
        if any(x.get("sub_task") == it.get("sub_task") and x.get("bf") == it.get("bf")
               for x in q):
            continue
        q.append(dict(it))
    return q


def queue_drop(state: dict, index: int) -> list[dict]:
    """❌ 큐에서 제외. K4 의 X 와 같은 의미다 — 이 용건은 다음으로 끌고 가지 마라."""
    q = state.setdefault("queue", [])
    if 0 <= index < len(q):
        q.pop(index)
    return q


def queue_move(state: dict, index: int, delta: int) -> list[dict]:
    """✏️ 처리 순서 변경."""
    q = state.setdefault("queue", [])
    j = index + delta
    if 0 <= index < len(q) and 0 <= j < len(q):
        q[index], q[j] = q[j], q[index]
    return q


# ══════════════════════════════════════════════════════════════════════════
# 화면 모델
# ══════════════════════════════════════════════════════════════════════════
def _slot_status(state: dict, field: str, cfg: dict, visible: tuple) -> str:
    if field not in visible:
        return ST_NOT_APPLICABLE
    stamp = (state.get("slot_turn") or {}).get(field)
    turn_no = int(state.get("turn_no") or 0)
    if stamp is not None and turn_no - stamp > cfg["CARRYOVER_TTL"]:
        return ST_EXPIRED
    return ST_ACTIVE


def panel_model(state: dict, *, config=None) -> dict:
    """패널 3구역 화면 모델. **순수 함수 — 상태를 바꾸지 않는다.**

    각 항목에 `effect`(고치면 무엇이 바뀌나)와 `actionable`(정말 바뀌나)을 단다.
    `actionable=False` 인 항목은 화면에서 회색으로 내린다 — 고치면 답이 바뀔 거라는
    기대를 만들지 않기 위해서다.
    """
    cfg = qform_config.resolve(config)
    bf = state.get("bf")
    visible = used_slots(bf)
    slots = state.get("qform") or {}
    passed = set(state.get("passed") or ())

    expired = state.get("expired") or {}
    applied = []
    for f in SLOT_FIELDS:
        status = _slot_status(state, f, cfg, visible)
        value = slots.get(f)
        if f in expired and value is None:
            # TTL 만료 — 값은 안 쓰지만 **마지막 값을 회색으로 남긴다**(K6 조건 ①).
            status, value = ST_EXPIRED, expired[f]
        if status == ST_NOT_APPLICABLE and not value:
            continue                       # 이 업무에서 안 쓰는 빈 축은 아예 안 그린다
        applied.append({
            "zone": ZONE_APPLIED, "field": f, "label": SLOT_LABEL.get(f, f),
            "value": value, "status": status,
            "passed": f in passed,
            "effect": SLOT_EFFECT if status == ST_ACTIVE else "없음 — 이 턴에는 안 쓰인다",
            "actionable": status == ST_ACTIVE,
            "ops": ("edit", "clear", "pass") if status == ST_ACTIVE else ("edit",),
        })

    remembered = [
        {"zone": ZONE_REMEMBERED, "field": "bf", "label": "업무",
         "value": bf, "status": ST_ACTIVE if bf else ST_EXPIRED,
         "effect": BF_EFFECT, "actionable": bool(bf), "ops": ("clear",)},
        {"zone": ZONE_REMEMBERED, "field": "last_docs", "label": "직전 참조 문서",
         "value": list(state.get("last_docs") or []), "status": ST_ACTIVE,
         "effect": DOC_EFFECT, "actionable": False, "ops": ()},
    ]

    queued = [
        {"zone": ZONE_QUEUED, "index": i, "label": it.get("sub_task") or "(미분류)",
         "value": it.get("text"), "bf": it.get("bf"), "status": ST_ACTIVE,
         "effect": QUEUE_EFFECT, "actionable": True, "ops": ("move", "drop")}
        for i, it in enumerate(state.get("queue") or [])
    ]

    return {"zones": [
        {"name": ZONE_APPLIED, "items": applied},
        {"name": ZONE_REMEMBERED, "items": remembered},
        {"name": ZONE_QUEUED, "items": queued},
    ], "ttl": cfg["CARRYOVER_TTL"], "expired_policy": cfg["PANEL_EXPIRED"]}


def effect_table(state: dict, *, config=None) -> list[tuple[str, str, str, bool]]:
    """(구역, 항목, 고치면 바뀌는 것, 정말 바뀌나) — 문서·검증용 평탄화."""
    m = panel_model(state, config=config)
    return [(z["name"], it["label"], it["effect"], it["actionable"])
            for z in m["zones"] for it in z["items"]]


# ══════════════════════════════════════════════════════════════════════════
# 조작 디스패치 — 화면이 부르는 유일한 진입점. **answer() 를 부르지 않는다.**
# ══════════════════════════════════════════════════════════════════════════
def apply(state: dict, op: str, **kw) -> dict:
    """패널 조작 1건. `answer()` 는 어느 분기에서도 호출되지 않는다(A3-2·F8)."""
    if op == "edit":
        return qform_flow.edit(state, kw["field"], kw.get("value"))
    if op == "clear":                       # ❌ 오염 차단 (K4)
        if kw["field"] == "bf":
            state["bf"] = None
            return {"kind": "ready", "field": "bf", "value": None}
        return qform_flow.edit(state, kw["field"], None)
    if op == "pass":                        # ⏭ 재질문 차단 (K5)
        return qform_flow.pass_slot(state, kw["field"])
    if op == "drop":
        return {"kind": "ready", "queue": queue_drop(state, kw["index"])}
    if op == "move":
        return {"kind": "ready", "queue": queue_move(state, kw["index"], kw.get("delta", -1))}
    raise ValueError(f"알 수 없는 조작: {op!r}")
