# -*- coding: utf-8 -*-
"""설정 저장소 + 런타임 주입.

**원본 코드를 절대 수정하지 않는다.** 관리자가 바꾼 값은 `data/admin_config.json` 에만
쌓이고, 챗봇이 뜰 때 `apply_runtime()` 이 모듈 상수에 주입한다.

  admin_config.json = {"override": {...}, "pending": {...}, "history": [...]}

  override  현재 적용 중인 값 (runtime 반영 완료)
  pending   저장은 됐지만 재빌드 대기 중인 값 (청크 파라미터)
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
from datetime import datetime, timezone

import registry

BASE = pathlib.Path(__file__).resolve().parent
DATA = BASE / "data"
CONFIG_PATH = DATA / "admin_config.json"
REPO = pathlib.Path(os.environ.get("KDIC_REPO", BASE.parent)).resolve()

_LOCK = threading.Lock()
_EMPTY = {"override": {}, "pending": {}, "history": [], "measured": {}, "dirty": {},
          "measured_history": []}

# 실측 이력에 함께 남기는 설정 스냅샷 — 콜 수·응답시간·비용은 실측이 아니라 설정에서
# 계산되는 값이라, 그때 무슨 설정이었는지를 같이 적어 둬야 나중에 다시 계산할 수 있다.
OPS_KEYS = ("earlyBlock", "askMode", "QFORM_SCOPE", "MAX_ASK_TURNS", "maxTokens",
            "k", "CHUNK_SIZE", "OVERLAP", "TABLE_KEEP")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        return json.loads(json.dumps(_EMPTY))
    try:
        d = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(_EMPTY))
    for k, v in _EMPTY.items():
        d.setdefault(k, json.loads(json.dumps(v)))
    # 레지스트리에서 사라진 키는 걸러 낸다(예: 파라미터에서 버튼으로 옮긴 `recrawl`).
    # 파일은 건드리지 않고 읽을 때만 정리한다 — 다음 save() 때 자연히 사라진다.
    for slot in ("override", "pending"):
        d[slot] = {k: v for k, v in (d.get(slot) or {}).items() if k in registry.BY_KEY}
    # 이력이 없던 시절의 단일 실측 기록도 '역대 최고'를 따질 때 한 지점으로 세어야 한다.
    # 파일은 건드리지 않고 읽을 때만 채운다 — 다음 record_measured() 때 자연히 저장된다.
    if d["measured"] and not d["measured_history"]:
        d["measured_history"] = [json.loads(json.dumps(d["measured"]))]
    return d


def _save_raw(d: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)          # 원자적 교체 — 저장 중 크래시에도 파일이 안 깨진다


def current() -> dict:
    """지금 서비스에 적용 중인 설정(= 기본값 + override)."""
    return registry.resolve(load()["override"])


def effective() -> dict:
    """관리자가 보는 값(= override + pending). 재빌드 전이라도 화면에는 이 값이 보인다."""
    d = load()
    return registry.resolve({**d["override"], **d["pending"]})


def save(changes: dict, actor: str = "admin") -> dict:
    """변경 저장. 재빌드 항목은 `pending` 으로 격리한다.

    반환: {"applied": {...}, "pending": {...}, "invalid": [...]}
    """
    invalid = registry.validate(changes)
    bad = {b["key"] for b in invalid}
    ok = {k: v for k, v in changes.items() if k not in bad and k in registry.BY_KEY}

    applied = {k: v for k, v in ok.items() if k not in registry.REBUILD_KEYS}
    pending = {k: v for k, v in ok.items() if k in registry.REBUILD_KEYS}

    with _LOCK:
        d = load()
        before = registry.resolve({**d["override"], **d["pending"]})
        d["override"].update(applied)
        d["pending"].update(pending)
        if applied or pending:
            d["history"].insert(0, {
                "at": _now(), "actor": actor,
                "changes": [{"key": k, "from": before.get(k), "to": v}
                            for k, v in {**applied, **pending}.items()],
                "rebuild_required": bool(pending),
            })
            d["history"] = d["history"][:200]
        _save_raw(d)

    if applied:
        apply_runtime()
    return {"applied": applied, "pending": pending, "invalid": invalid}


def record_measured(metrics: dict, chunks: int | None = None) -> dict:
    """재빌드·재검증이 성공하면 그때 실측된 지표를 남긴다.

    이 값이 있으면 대시보드의 '현재 정확도'가 **추정표가 아니라 실제 측정치**가 된다.
    코퍼스를 바꾼 뒤에도 화면이 옛 기준선을 계속 보여주는 문제를 막는다.

    최신 1건은 `measured` 에 그대로 두고(기존 화면들이 이 자리를 본다), 같은 기록을
    `measured_history` 에도 쌓는다. **덮어쓰기만 하면 '역대 최고'를 알 수 없다** —
    직전 값과 비교만 되고, 지난달에 더 좋았다는 사실은 화면에서 사라진다.
    """
    with _LOCK:
        d = load()
        cfg = registry.resolve(d["override"])
        rec = {**(metrics or {}), "chunks": chunks, "at": _now(),
               "cfg": {k: cfg.get(k) for k in OPS_KEYS}}
        d["measured"] = rec
        d["measured_history"] = ([rec] + [h for h in d["measured_history"]
                                          if h.get("at") != rec["at"]])[:100]
        _save_raw(d)
    return d["measured"]


def measured() -> dict:
    return load().get("measured") or {}


def measured_history() -> list[dict]:
    """실측 기록 전부 (최신 순). '역대 최고' 는 이 목록에서만 나온다."""
    return list(load().get("measured_history") or [])


# ── 재청킹이 필요한 상태 표시 ───────────────────────────────────────────
def mark_dirty(reason: str) -> dict:
    """파라미터가 아닌 **입력 자체**가 바뀌었을 때 세우는 깃발.

    첨부 파일을 다시 받으면 `link_files.py` 가 `data/parsed/*.json` 을 고쳐 쓴다.
    청크 파라미터는 그대로라 체인의 경로 판정만으로는 '변경 없음 → 재검증만' 이 되는데,
    실제로는 다시 잘라야 그 정보가 청크에 들어간다. 그래서 따로 기록해 둔다.
    """
    with _LOCK:
        d = load()
        d["dirty"] = {"reason": reason, "at": _now()}
        _save_raw(d)
    return d["dirty"]


def dirty() -> dict:
    return load().get("dirty") or {}


def clear_dirty() -> None:
    with _LOCK:
        d = load()
        d["dirty"] = {}
        _save_raw(d)


def commit_pending() -> dict:
    """재빌드 성공 후 호출 — pending 을 override 로 승격."""
    with _LOCK:
        d = load()
        moved = dict(d["pending"])
        d["override"].update(moved)
        d["pending"] = {}
        if moved:
            d["history"].insert(0, {"at": _now(), "actor": "system",
                                    "changes": [{"key": k, "to": v} for k, v in moved.items()],
                                    "note": "재빌드 완료 — 반영됨"})
        _save_raw(d)
    apply_runtime()
    return moved


def discard_pending() -> dict:
    with _LOCK:
        d = load()
        dropped, d["pending"] = d["pending"], {}
        _save_raw(d)
    return dropped


def rollback(index: int = 0) -> dict:
    """history[index] 의 변경을 되돌린다(from 값으로 복원)."""
    with _LOCK:
        d = load()
        if index >= len(d["history"]):
            return {}
        entry = d["history"][index]
        restore = {c["key"]: c.get("from") for c in entry["changes"]
                   if "from" in c and c["key"] in registry.BY_KEY}
        for k, v in restore.items():
            if v is None or v == registry.DEFAULTS.get(k):
                d["override"].pop(k, None)
                d["pending"].pop(k, None)
            elif k in registry.REBUILD_KEYS:
                d["pending"][k] = v
            else:
                d["override"][k] = v
        d["history"].insert(0, {"at": _now(), "actor": "admin",
                                "changes": [{"key": k, "to": v} for k, v in restore.items()],
                                "note": f"되돌리기 (#{index})"})
        _save_raw(d)
    apply_runtime()
    return restore


# ── 런타임 주입 ─────────────────────────────────────────────────────────
def apply_runtime() -> list[str]:
    """모듈 상수에 현재 설정을 주입한다. 파일을 고치지 않고 메모리 값만 바꾼다.

    챗봇 프로세스와 콘솔이 **같은 프로세스**일 때만 즉시 반영된다. 분리 운영이면
    챗봇 쪽에서 기동 시 이 함수를 부르거나 설정 변경 신호를 받아 재호출해야 한다.
    """
    import sys
    for p in (REPO / "crawler", REPO / "chatbot"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    cfg = current()
    touched: list[str] = []

    try:                                        # 검색
        import rag
        for key in ("RRF_ALPHA", "RRF_K", "BF_BOOST", "FACET_BOOST",
                    "BF_DOC_CAP", "BF_MODE", "QBF_MSP_MIN"):
            if hasattr(rag, key):
                setattr(rag, key, cfg[key])
                touched.append(f"rag.{key}")
    except Exception as e:                      # 검색 스택 미로딩 환경에서도 콘솔은 떠야 한다
        touched.append(f"rag: skip({type(e).__name__})")

    try:                                        # 생성
        import chain
        chain.GEN_PARAMS["maxTokens"] = int(cfg["maxTokens"])
        chain.GEN_PARAMS["temperature"] = float(cfg["temperature"])
        chain.CALL_BUDGET = int(cfg["CALL_BUDGET"])
        touched += ["chain.GEN_PARAMS", "chain.CALL_BUDGET"]
    except Exception as e:
        touched.append(f"chain: skip({type(e).__name__})")

    try:                                        # 큐폼 — 이미 SPEC/resolve 패턴이 있다
        import qform_config
        for key in ("SLOT_CARRYOVER", "CARRYOVER_TTL", "CARRYOVER_SCOPE",
                    "MAX_ASK_TURNS", "QFORM_SCOPE", "MAX_QUEUE", "PANEL_EXPIRED"):
            if hasattr(qform_config, key):
                setattr(qform_config, key, cfg[key])
                touched.append(f"qform_config.{key}")
    except Exception as e:
        touched.append(f"qform_config: skip({type(e).__name__})")

    return touched


def qform_override() -> dict:
    """`qform_config.resolve()` 에 그대로 넘길 수 있는 dict."""
    cfg = current()
    return {k: cfg[k] for k in ("SLOT_CARRYOVER", "CARRYOVER_TTL", "CARRYOVER_SCOPE",
                                "MAX_ASK_TURNS", "QFORM_SCOPE", "MAX_QUEUE", "PANEL_EXPIRED")}


def chunk_env() -> dict:
    """재빌드 잡에 넘길 환경변수 — `crawler/chunk.py` 가 읽도록 패치 없이 주입한다."""
    cfg = effective()
    return {
        "KDIC_CHUNK_SIZE": str(int(cfg["CHUNK_SIZE"])),
        "KDIC_OVERLAP": str(int(cfg["OVERLAP"])),
        "KDIC_MIN_CHUNK": str(int(cfg["MIN_CHUNK"])),
        "KDIC_TABLE_GAP_MAX": (str(int(cfg["TABLE_GAP_MAX"])) if cfg["TABLE_KEEP"] else "off"),
    }
