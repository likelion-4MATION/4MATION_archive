# -*- coding: utf-8 -*-
"""KDIC 챗봇 관리자 콘솔 — FastAPI.

실행:
    cd admin
    pip install -r requirements.txt
    KDIC_REPO=/path/to/4MATION uvicorn main:app --reload --port 8600

챗봇(Streamlit)과 별도 프로세스로 뜬다. 설정은 `data/admin_config.json` 에 저장되고,
챗봇 쪽은 기동 시 `settings.apply_runtime()` 을 호출해 읽어 간다(README §연동).
"""
from __future__ import annotations

import pathlib

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import attachments as att
import guards
import jobs
import metrics
import registry
import settings

BASE = pathlib.Path(__file__).resolve().parent
app = FastAPI(title="KDIC 챗봇 관리자 콘솔", version="1.0")


# ── 스키마 ──────────────────────────────────────────────────────────────
class SaveBody(BaseModel):
    changes: dict
    actor: str = "admin"


class ProjectBody(BaseModel):
    values: dict = {}


class GuardBody(BaseModel):
    guard: dict
    actor: str = "admin"


class JobBody(BaseModel):
    kind: str = "rebuild"
    actor: str = "admin"
    guard: bool = True          # 체인 1단계가 나쁘면 멈추고 확인받는다
    recrawl: bool = False       # 이번 실행에만 적용 — 저장되지 않는다


class ResumeBody(BaseModel):
    go: bool = True


class LabelBody(BaseModel):
    key: str
    label: str = ""


class HideBody(BaseModel):
    key: str
    hidden: bool = True


class ReplaceBody(BaseModel):
    key: str
    filename: str = ""
    note: str = ""


class ExtraBody(BaseModel):
    doc_id: str = ""
    label: str
    kind: str = "url"
    url: str = ""
    filename: str = ""
    note: str = ""


class LinkBody(BaseModel):
    link: dict


# ── 설정 ────────────────────────────────────────────────────────────────
@app.get("/api/schema")
def api_schema():
    """파라미터 정의 + 프리셋 + 업무 목록 — 프런트가 UI를 이걸로 그린다."""
    return {
        "params": registry.PARAMS,
        "presets": registry.PRESETS,
        "rebuild_keys": sorted(registry.REBUILD_KEYS),
        "business": guards.BUSINESS,
        "guard_kinds": [{"key": k, "label": guards.KIND_LABEL[k]} for k in guards.KINDS],
        "limits": {"statement": guards.MAX_STATEMENT, "total": guards.MAX_TOTAL},
        "golden": registry.GOLDEN,
    }


@app.get("/api/state")
def api_state():
    d = settings.load()
    cfg = settings.effective()
    changed = [k for k in registry.BY_KEY
               if str(cfg.get(k)) != str(registry.DEFAULTS.get(k))]
    return {
        "values": {k: cfg[k] for k in registry.BY_KEY},
        "override": d["override"], "pending": d["pending"],
        "changed_from_default": changed,
        "custom_search": registry.is_custom_search(d["override"]),
        "invalid": cfg.get("_invalid", []),
        "history": d["history"][:20],
        "golden_diff": registry.golden_diff(cfg),
    }


@app.post("/api/save")
def api_save(body: SaveBody):
    res = settings.save(body.changes, body.actor)
    res["state"] = api_state()
    return res


@app.post("/api/rollback/{index}")
def api_rollback(index: int):
    return {"restored": settings.rollback(index), "state": api_state()}


@app.post("/api/pending/discard")
def api_discard():
    return {"dropped": settings.discard_pending(), "state": api_state()}


@app.post("/api/project")
def api_project(body: ProjectBody):
    """저장하지 않고 예상 결과만 계산 — 사이드 고정 패널이 매 변경마다 호출한다."""
    d = settings.load()
    merged = registry.resolve({**d["override"], **d["pending"], **body.values})
    saved = settings.effective()
    changed = [k for k in registry.BY_KEY if str(merged.get(k)) != str(saved.get(k))]
    return {"changed": changed,
            "rebuild_required": sorted(set(changed) & registry.REBUILD_KEYS),
            "projection": metrics.projection(merged, changed, saved=saved),
            "measured": settings.measured(),
            "plan": jobs.plan_preview(merged)}      # [한 번에 실행] 이 무엇을 돌릴지


# ── 최신성 가드 ─────────────────────────────────────────────────────────
@app.get("/api/guards")
def api_guards():
    return {"guards": guards.list_all(), "stats": guards.stats()}


@app.post("/api/guards")
def api_guard_upsert(body: GuardBody):
    res = guards.upsert(body.guard, body.actor)
    if not res.get("ok"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.post("/api/guards/{gid}/status/{status}")
def api_guard_status(gid: str, status: str):
    res = guards.set_status(gid, status)
    if not res.get("ok"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.delete("/api/guards/{gid}")
def api_guard_delete(gid: str):
    if not guards.delete(gid):
        raise HTTPException(404, "가드를 찾을 수 없습니다.")
    return {"ok": True}


@app.post("/api/guards/preview")
def api_guard_preview(body: GuardBody):
    """저장 전 미리보기 — 어떤 질문에 걸리고 프롬프트에 뭐가 들어가는지 보여준다."""
    g = {**body.guard, "status": "approved"}
    err = guards.validate(g, guards.list_all())
    samples = [f"{t} 관련해서 알려주세요" for t in (g.get("triggers") or [])[:3]]
    return {"errors": err,
            "prompt_block": guards.prompt_block([g]) if not err else "",
            "whitelist": sorted(guards.numeric_whitelist([g])),
            "samples": samples}


# ── 첨부문서 · 링크 ─────────────────────────────────────────────────────
@app.get("/api/attachments")
def api_attachments():
    att.ensure_seed()
    return att.list_all()


@app.post("/api/attachments/label")
def api_att_label(body: LabelBody):
    res = att.set_label(body.key, body.label) if body.label else att.reset_label(body.key)
    if not res.get("ok"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.post("/api/attachments/hide")
def api_att_hide(body: HideBody):
    return att.set_hidden(body.key, body.hidden)


@app.post("/api/attachments/replace")
def api_att_replace(body: ReplaceBody):
    """구 문서를 새 파일로 교체 / filename 이 비면 교체 취소."""
    res = att.set_replace(body.key, body.filename, body.note) if body.filename \
        else att.clear_replace(body.key)
    if not res.get("ok"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.get("/api/attachments/source/{key}")
def api_att_source(key: str):
    """크롤러가 받아 둔 **원본 첨부 파일**을 그대로 내려준다 (읽기 전용)."""
    p = att.source_path(key)
    if not p:
        raise HTTPException(404, "원본 파일이 없습니다. fetch_attachments.py 산출물을 확인하세요.")
    return FileResponse(p, filename=p.name)


@app.get("/api/attachments/resolved/{doc_id}")
def api_att_resolved(doc_id: str):
    """챗봇이 쓸 최종 첨부 목록 — 숨김 제외 · 교체 반영 · 관리자 추가 포함."""
    return {"doc_id": doc_id, "items": att.resolved(doc_id)}


@app.post("/api/attachments/clean")
def api_att_clean():
    return att.bulk_clean()


@app.post("/api/attachments/upload")
async def api_att_upload(file: UploadFile = File(...)):
    data = await file.read()
    res = att.save_upload(file.filename or "unnamed", data)
    if not res.get("ok"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.get("/api/attachments/file/{name}")
def api_att_file(name: str):
    p = att.upload_path(name)
    if not p:
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    return FileResponse(p, filename=name.split("_", 1)[-1])


@app.post("/api/attachments/extra")
def api_att_extra(body: ExtraBody):
    res = att.add_extra(body.doc_id, body.label, body.kind,
                        body.url, body.filename, body.note)
    if not res.get("ok"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.delete("/api/attachments/extra/{item_id}")
def api_att_extra_del(item_id: str):
    if not att.delete_extra(item_id):
        raise HTTPException(404, "항목을 찾을 수 없습니다.")
    return {"ok": True}


@app.post("/api/links")
def api_link_upsert(body: LinkBody):
    res = att.upsert_link(body.link)
    if not res.get("ok"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.delete("/api/links/{link_id}")
def api_link_del(link_id: str):
    if not att.delete_link(link_id):
        raise HTTPException(404, "링크를 찾을 수 없습니다.")
    return {"ok": True}


# ── 잡 ──────────────────────────────────────────────────────────────────
@app.get("/api/job")
def api_job_latest():
    return {"running": jobs.running(), "latest": jobs.latest(),
            "preflight": jobs.preflight()}


@app.get("/api/job/{job_id}")
def api_job(job_id: str):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return j


@app.post("/api/job")
def api_job_start(body: JobBody):
    if body.kind not in jobs.PLAN:
        raise HTTPException(400, f"kind 는 {', '.join(jobs.PLAN)} 중 하나여야 합니다.")
    res = jobs.start(body.kind, body.actor, body.guard, body.recrawl)
    if not res.get("ok"):
        return JSONResponse(status_code=409, content=res)
    return res


@app.post("/api/job/{job_id}/resume")
def api_job_resume(job_id: str, body: ResumeBody):
    """판정 게이트에서 멈춘 체인을 계속 진행(go=true)하거나 중단(go=false)한다."""
    res = jobs.resume(job_id, body.go)
    if not res.get("ok"):
        return JSONResponse(status_code=409, content=res)
    return res


# ── 대시보드 ────────────────────────────────────────────────────────────
@app.get("/api/dashboard")
def api_dashboard():
    return {
        "corpus": metrics.corpus(),
        "attachments": metrics.attachments(),
        "freshness": metrics.freshness(),
        "health": metrics.health(),
        "business": metrics.business_mix(),
        "guards": guards.stats(),
        "evidence": {"preset": metrics.ACC_PRESET, "k": metrics.ACC_K,
                     "chunk": metrics.ACC_CHUNK, "baseline": metrics.BASELINE,
                     "current": metrics.current_point()},
    }


# ── 정적 서빙 ───────────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

# 기동 시 저장된 설정을 즉시 주입 (같은 프로세스에서 챗봇을 함께 띄우는 경우 대비)
settings.apply_runtime()
