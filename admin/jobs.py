# -*- coding: utf-8 -*-
"""재빌드·평가 잡 실행기.

`runner.py` 를 서브프로세스로 띄우고 stdout 마커(`__STEP__` / `__RESULT__`)를 **스트리밍**으로
읽어 단계별 진행 상태를 갱신한다. 실제 청킹·인덱싱·평가는 전부 러너가 crawler 코드를
그대로 호출해서 한다(러너 모듈 docstring 참조).

  eval     샌드박스 인덱스에서 평가 → 끝나면 원상복구. **서비스 인덱스 무손상.**
  rebuild  실제 인덱스를 교체. 실패하면 백업에서 자동 복원.
  verify   현재 서비스 인덱스를 그대로 평가. 읽기 전용.
  chain    eval → (판정 게이트) → rebuild → verify 를 한 잡으로 연달아 실행.

체인의 판정 게이트
    1단계 샌드박스 평가의 앵커 hit@5 가 마지막 실측 기준선보다 낮으면 잡을 `awaiting` 으로
    세워 두고 `resume()` 신호를 기다린다. 브라우저를 닫았다 다시 열어도 대기 상태가
    유지된다(상태가 파일에 있으므로). 30분 안에 응답이 없으면 자동 중단한다.

동시 실행은 1건으로 제한된다. `awaiting` 도 점유로 친다.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

import settings

BASE = pathlib.Path(__file__).resolve().parent
JOBS_DIR = BASE / "data" / "jobs"
REPO = settings.REPO
CRAWLER = REPO / "crawler"

_LOCK = threading.Lock()
_CURRENT: dict | None = None

_GATE = threading.Event()          # 체인 판정 게이트 — resume() 가 푼다
_GATE_GO = False
GATE_TIMEOUT = 1800                # 30분

# 단계 이름은 runner.py 가 내보내는 `__STEP__` 문자열과 정확히 같아야 한다
STEPS = {
    "eval": ["현재 상태 백업", "청크 파라미터 주입", "저장된 원문으로 다시 자르기",
             "검색 인덱스 확인", "평가셋 검증", "샌드박스 정리 · 원상복구"],
    "rebuild": ["현재 상태 백업", "청크 파라미터 주입", "저장된 원문으로 다시 자르기",
                "검색 인덱스 확인", "평가셋 검증"],
    "rebuild_recrawl": ["현재 상태 백업", "청크 파라미터 주입", "홈페이지 수집 + 파싱",
                        "검색 인덱스 확인", "평가셋 검증"],
    "verify": ["검색 인덱스 확인", "평가셋 검증"],
    "files": ["현재 상태 백업", "첨부 파일 내려받기", "청크 메타에 연결"],
}

# kind → 단계 구성 [(러너 모드, 화면 라벨)]
PLAN = {
    "eval": [("eval", "테스트셋 검증")],
    "rebuild": [("rebuild", "재청킹 · 재빌드")],
    "verify": [("verify", "현재 인덱스 재검증")],
    "chain": [("eval", "① 테스트셋 검증"),
              ("rebuild", "② 재청킹 · 재빌드"),
              ("verify", "③ 빌드 후 재검증")],
    "recrawl": [("rebuild", "① 원문 재수집 + 재빌드"),
                ("verify", "② 재검증")],
    "files": [("files", "첨부 파일 다시 받기")],
}
# 청크 설정에 변화가 없을 때 체인이 대신 타는 짧은 경로
PLAN_SKIP = [("verify", "재검증 — 청크 설정 변경 없음")]

# 기기 실측(2026-08-19 잡 기록): 재청킹+인덱싱 33초, 평가 33초
# 첨부: 45건 × (REQUEST_INTERVAL 1.5초 + 지터 0~0.7초 + 응답) ≈ 2분
ETA = {"eval": 70, "rebuild": 70, "verify": 35, "files": 130}
ETA_RECRAWL = 600                      # 홈페이지 폴라이트 수집분(재빌드에 더해진다)

CHUNK_KEYS = ("CHUNK_SIZE", "OVERLAP", "MIN_CHUNK", "TABLE_KEEP", "TABLE_GAP_MAX")


def resolve_plan(kind: str, eff: dict | None = None) -> tuple[list, dict]:
    """체인은 **실제로 다시 자를 이유가 있을 때만** 재청킹한다.

    `settings.current()` 는 override — 지금 인덱스가 만들어질 때 쓴 값이고,
    `effective()` 는 override + pending — 관리자가 적용하려는 값이다. 청크 키에서 둘이
    같으면 다시 자를 게 없으므로 재검증만 돌린다(약 35초 vs 175초).

    검색 파라미터(프리셋·⑥ 고급)만 바뀐 경우가 바로 이 경로다 — 러너가
    `apply_search_settings()` 로 그 값을 주입해 평가하므로 재검증만으로 효과가 잡힌다.
    """
    if kind != "chain":
        return PLAN[kind], {}
    cur = settings.current()
    eff = eff if eff is not None else settings.effective()
    diff = sorted(k for k in CHUNK_KEYS if str(cur.get(k)) != str(eff.get(k)))
    dirty = settings.dirty()          # 파라미터가 아니라 입력이 바뀐 경우(첨부 재수집 등)
    if diff or dirty:
        return PLAN["chain"], {"skipped": False, "changed": diff,
                               "dirty": dirty.get("reason") or None}
    return PLAN_SKIP, {"skipped": True, "changed": [], "dirty": None}


def plan_preview(eff: dict | None = None, recrawl: bool = False) -> dict:
    """[한 번에 실행]을 누르면 무엇이 돌지 미리 보여준다(고정 패널용)."""
    stages, info = resolve_plan("chain", eff)
    eta = sum(ETA[m] + (ETA_RECRAWL if (m == "rebuild" and recrawl) else 0)
              for m, _ in stages)
    return {"stages": [l for _, l in stages], "eta_seconds": eta, **info}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def preflight() -> list[str]:
    """실행 전 환경 점검. 막지 않고 경고만 돌려준다."""
    warn = []
    for f in ("pipeline.py", "chunk.py", "rag.py", "crawl_manifest.csv"):
        if not (CRAWLER / f).exists():
            warn.append(f"crawler/{f} 를 찾을 수 없습니다. KDIC_REPO 경로를 확인하세요.")
    gt = CRAWLER / "gt_testset_retrieval_450.jsonl"
    if not gt.exists() and not (CRAWLER / "data" / gt.name).exists():
        warn.append("평가셋(gt_testset_retrieval_450.jsonl)이 없어 평가 단계가 비어서 끝납니다.")
    if not (CRAWLER / "data" / "raw").exists():
        warn.append("data/raw 캐시가 없습니다 — [원문 재수집] 으로 한 번 받아와야 재빌드가 가능합니다.")
    if not (CRAWLER / "data" / "files" / "manifest.json").exists():
        warn.append("첨부 실파일을 아직 받지 않았습니다 — ⑤ 첨부문서 탭의 "
                    "[첨부 파일 다시 받기]를 한 번 눌러야 내려받기가 됩니다.")
    cfg = settings.effective()
    if int(cfg.get("OVERLAP", 100)) == 0:
        warn.append("겹침 0은 코드상 직전 조각을 통째로 복제합니다 — 실행 시 자동으로 1자로 낮춥니다.")
    d = settings.dirty()
    if d:
        warn.append(d.get("reason") or "재청킹이 필요한 변경이 있습니다.")
    return warn


# ── 상태 저장 ───────────────────────────────────────────────────────────
def _write(job: dict) -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(job, ensure_ascii=False, indent=2)
    (JOBS_DIR / f"{job['id']}.json").write_text(body, encoding="utf-8")
    (JOBS_DIR / "latest.json").write_text(body, encoding="utf-8")


def _read(p: pathlib.Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def latest() -> dict | None:
    return _read(JOBS_DIR / "latest.json")


def get(job_id: str) -> dict | None:
    return _read(JOBS_DIR / f"{job_id}.json")


def running() -> dict | None:
    """진행 중이거나 **판정 대기 중**이면 점유로 본다."""
    if _CURRENT and _CURRENT.get("status") in ("running", "awaiting"):
        return _CURRENT
    return None


# ── 실행 ────────────────────────────────────────────────────────────────
def start(kind: str = "rebuild", actor: str = "admin", guard: bool = True,
          recrawl: bool = False) -> dict:
    """`recrawl` 은 **저장되는 값이 아니라 이번 실행의 인자**다.

    예전에는 재빌드 파라미터였는데, 재빌드가 성공하면 `commit_pending()` 이 `override` 로
    승격시켜 그 뒤 모든 재빌드가 계속 홈페이지에 접속했다. 지금은 [원문 재수집] 버튼이
    누를 때만 넘긴다.
    """
    global _CURRENT
    if kind not in PLAN:
        return {"ok": False, "error": f"알 수 없는 작업 종류: {kind}"}
    with _LOCK:
        if running():
            return {"ok": False, "error": "이미 실행 중인 작업이 있습니다.", "job": _CURRENT}
        cfg = settings.effective()
        # 겹침 0은 러너가 1로 낮춰 실행한다(runner.clamp_overlap). 설정에 0이 남으면
        # 재빌드 후 '설정은 0, 실제 코퍼스는 1' 이 되어 기록이 어긋나므로 먼저 맞춰 둔다.
        if int(cfg.get("OVERLAP", 100)) == 0:
            settings.save({"OVERLAP": 1}, "system")
            cfg = settings.effective()

        plan, info = resolve_plan(kind, cfg)
        if kind == "recrawl":
            recrawl = True                       # 이 버튼의 존재 이유
        recrawl = bool(recrawl) and any(m == "rebuild" for m, _ in plan)

        stages = []
        eta = 0
        for mode, label in plan:
            names = STEPS["rebuild_recrawl" if (mode == "rebuild" and recrawl) else mode]
            stages.append({
                "kind": mode, "label": label, "status": "pending",
                "steps": [{"name": n, "status": "pending", "seconds": None} for n in names],
                "metrics": None, "chunks": None, "error": None, "seconds": None,
            })
            eta += ETA_RECRAWL if (mode == "rebuild" and recrawl) else ETA[mode]

        job = {
            "id": uuid.uuid4().hex[:10], "kind": kind, "recrawl": recrawl,
            "status": "running", "actor": actor, "guard": bool(guard),
            "started_at": _now(), "finished_at": None,
            "stage": 0, "stages": stages, "gate": None,
            "skipped_rebuild": bool(info.get("skipped")),
            "changed_chunk_keys": info.get("changed") or [],
            "baseline": settings.measured() or None,
            "eta_seconds": eta,
            "warnings": preflight(),
            "params": {k: cfg[k] for k in CHUNK_KEYS},
            "log": "", "result": None, "error": None,
        }
        _CURRENT = job
        _write(job)
    threading.Thread(target=_run, args=(job, cfg), daemon=True).start()
    return {"ok": True, "job": job}


def resume(job_id: str, go: bool) -> dict:
    """판정 대기 중인 체인을 계속 진행하거나 중단한다."""
    global _GATE_GO
    j = _CURRENT
    if not j or j.get("id") != job_id or j.get("status") != "awaiting":
        return {"ok": False, "error": "판정 대기 중인 작업이 없습니다."}
    _GATE_GO = bool(go)
    _GATE.set()
    return {"ok": True, "go": bool(go)}


def _env() -> dict:
    return {**os.environ, "KDIC_REPO": str(REPO),
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE", "1"),
            "PYTHONPATH": os.pathsep.join([str(CRAWLER), str(REPO / "chatbot"), str(BASE)]),
            "PYTHONUNBUFFERED": "1"}


def _stream(job: dict, stage: dict, cmd: list[str], lines: list[str]) -> tuple[int, dict]:
    """서브프로세스 한 건을 돌리며 이 단계의 steps 를 실시간으로 갱신한다."""
    idx = -1
    t_step = time.time()
    result: dict = {}
    pr = subprocess.Popen(cmd, cwd=str(CRAWLER), env=_env(), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, bufsize=1)
    for raw in pr.stdout:
        line = raw.rstrip("\n")
        lines.append(line)
        if len(lines) > 400:
            del lines[:100]
        if line.startswith("__STEP__ "):
            name = line[9:].strip()
            if 0 <= idx < len(stage["steps"]):
                stage["steps"][idx]["status"] = "done"
                stage["steps"][idx]["seconds"] = round(time.time() - t_step, 1)
            nxt = next((i for i, s in enumerate(stage["steps"])
                        if s["name"] == name and s["status"] == "pending"), None)
            if nxt is None:                # 러너가 목록에 없는 단계를 냈다 — 뒤에 붙인다
                stage["steps"].append({"name": name, "status": "pending", "seconds": None})
                nxt = len(stage["steps"]) - 1
            idx = nxt
            stage["steps"][idx]["status"] = "running"
            t_step = time.time()
        elif line.startswith("__RESULT__ "):
            try:
                result = json.loads(line[11:])
            except json.JSONDecodeError:
                pass
        job["log"] = "\n".join(lines[-120:])
        _write(job)
    pr.wait(timeout=60)
    if 0 <= idx < len(stage["steps"]) and stage["steps"][idx]["status"] == "running":
        stage["steps"][idx]["status"] = "done" if pr.returncode == 0 else "failed"
        stage["steps"][idx]["seconds"] = round(time.time() - t_step, 1)
    return pr.returncode, result


def _gate_check(job: dict, metrics: dict) -> dict | None:
    """1단계 평가가 기준선보다 나쁜가. 나쁘면 게이트 정보를, 아니면 None."""
    base = (job.get("baseline") or {}).get("hit@5")
    got = (metrics or {}).get("hit@5")
    if base is None:
        return {"reason": "no_baseline",
                "text": "비교할 실측 기준선이 없습니다(재빌드 이력 없음). 진행 여부를 확인해 주세요.",
                "base": None, "got": got}
    if got is None:
        return {"reason": "no_metric",
                "text": "평가 지표를 얻지 못했습니다. 진행 여부를 확인해 주세요.",
                "base": base, "got": None}
    if got < base - 1e-9:
        return {"reason": "worse",
                "text": f"검증 결과가 현재보다 나쁩니다 — 앵커 hit@5 {base:.4f} → {got:.4f}.",
                "base": base, "got": got}
    return None


def _run(job: dict, cfg: dict) -> None:
    global _CURRENT
    lines: list[str] = []
    cfg_json = json.dumps({k: cfg[k] for k in CHUNK_KEYS}, ensure_ascii=False)
    try:
        for i, stage in enumerate(job["stages"]):
            job["stage"] = i
            stage["status"] = "running"
            job["status"] = "running"
            t0 = time.time()
            _write(job)

            cmd = [sys.executable, str(BASE / "runner.py"),
                   "--mode", stage["kind"], "--config", cfg_json]
            if stage["kind"] == "rebuild" and job["recrawl"]:
                cmd.append("--recrawl")

            rc, res = _stream(job, stage, cmd, lines)
            stage["seconds"] = round(time.time() - t0, 1)
            stage["metrics"] = (res.get("metrics") or None)
            stage["chunks"] = res.get("chunks")
            job["result"] = res

            if rc != 0 or res.get("status") != "done":
                stage["status"] = "failed"
                stage["error"] = res.get("error") or f"러너가 코드 {rc} 로 종료했습니다."
                job["status"] = "failed"
                job["error"] = stage["error"]
                job["restored"] = res.get("restored", False)
                job["verify"] = res.get("verify")
                job["note"] = res.get("note")
                break

            stage["status"] = "done"
            if stage["kind"] in ("rebuild", "verify"):
                if stage["kind"] == "rebuild":
                    job["committed"] = settings.commit_pending()
                    settings.clear_dirty()      # 다시 잘랐으니 깃발을 내린다
                # baseline 은 **실행 전 스냅샷**이라 덮어쓰지 않는다 — 결과 비교의 기준이다
                settings.record_measured(stage["metrics"] or {}, stage["chunks"])
            elif stage["kind"] == "files":
                # link_files.py 가 parsed 를 고쳐 썼다 — 청크에 반영하려면 다시 잘라야 한다
                job["dirty"] = settings.mark_dirty(
                    "첨부 파일을 다시 받았습니다 — 재청킹해야 청크에 반영됩니다.")
            _write(job)

            # ── 판정 게이트 (체인의 1단계 평가 직후에만) ──────────────
            more = i + 1 < len(job["stages"])
            if job["kind"] == "chain" and stage["kind"] == "eval" and more and job.get("guard"):
                g = _gate_check(job, stage["metrics"] or {})
                if g:
                    _GATE.clear()
                    job["gate"] = {**g, "at": _now(), "job_id": job["id"]}
                    job["status"] = "awaiting"
                    _write(job)
                    if not _GATE.wait(timeout=GATE_TIMEOUT):
                        job["status"] = "aborted"
                        job["error"] = "확인 대기 시간(30분)이 지나 자동 중단했습니다."
                        job["note"] = "서비스 인덱스는 그대로입니다."
                        break
                    if not _GATE_GO:
                        job["status"] = "aborted"
                        job["note"] = "관리자가 중단했습니다. 서비스 인덱스는 그대로입니다."
                        break
                    job["gate"] = {**job["gate"], "decided": "go", "decided_at": _now()}
                    job["status"] = "running"
                    _write(job)
        else:
            job["status"] = "done"
    except subprocess.TimeoutExpired:
        job["status"] = "failed"
        job["error"] = "러너 종료 대기 시간 초과"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = f"{type(e).__name__}: {e}"
    finally:
        for st in job["stages"]:
            if st["status"] == "pending" and job["status"] in ("failed", "aborted"):
                st["status"] = "skipped"
            for s in st["steps"]:
                if s["status"] == "pending" and st["status"] in ("failed", "skipped"):
                    s["status"] = "skipped"
        job["finished_at"] = _now()
        _write(job)
        _CURRENT = job
