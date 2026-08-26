"""KDIC 사용자용 FastAPI + 정적 HTML 진입점.

실행: python -m uvicorn web.main:app --host 127.0.0.1 --port 8501
"""
from __future__ import annotations

import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.schemas import ActionBody, MessageBody, ReportBody, SettingsBody
from web.service import AttachmentNotFound, ChatService, InvalidAction
from web.sessions import SessionNotFound

BASE = pathlib.Path(__file__).resolve().parent
ROOT = BASE.parent


def create_app(service: ChatService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not hasattr(app.state, "chat_service"):
            app.state.chat_service = service or ChatService()
        yield

    application = FastAPI(
        title="예금보험공사 안내 서비스", version="1.0", lifespan=lifespan,
        docs_url="/api/docs", redoc_url=None,
    )
    if service is not None:
        application.state.chat_service = service

    @application.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def chat_service() -> ChatService:
        return application.state.chat_service

    def not_found(exc: Exception) -> HTTPException:
        return HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")

    @application.get("/api/health")
    def health():
        svc = chat_service()
        return {"ok": True, "calls": {"used": svc.backend.call_count,
                                        "budget": svc.backend.call_budget}}

    @application.post("/api/sessions", status_code=201)
    def create_session():
        return chat_service().create_session()

    @application.get("/api/sessions/{session_id}")
    def get_session(session_id: str):
        try:
            return chat_service().get_session(session_id)
        except SessionNotFound as exc:
            raise not_found(exc) from exc

    @application.delete("/api/sessions/{session_id}", status_code=204)
    def delete_session(session_id: str):
        try:
            chat_service().delete_session(session_id)
        except SessionNotFound as exc:
            raise not_found(exc) from exc
        return Response(status_code=204)

    @application.post("/api/sessions/{session_id}/messages")
    def send_message(session_id: str, body: MessageBody):
        try:
            return chat_service().send_message(session_id, body.text, new_topic=body.new_topic)
        except SessionNotFound as exc:
            raise not_found(exc) from exc
        except InvalidAction as exc:
            raise HTTPException(400, str(exc)) from exc

    @application.post("/api/sessions/{session_id}/actions")
    def perform_action(session_id: str, body: ActionBody):
        try:
            return chat_service().perform_action(session_id, body)
        except SessionNotFound as exc:
            raise not_found(exc) from exc
        except (InvalidAction, ValueError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @application.patch("/api/sessions/{session_id}/settings")
    def update_settings(session_id: str, body: SettingsBody):
        try:
            return chat_service().update_settings(session_id, body)
        except SessionNotFound as exc:
            raise not_found(exc) from exc

    @application.post("/api/sessions/{session_id}/reports", status_code=201)
    def create_report(session_id: str, body: ReportBody):
        try:
            saved = chat_service().create_report(session_id, body.target_message_id)
            return {"ok": True, "report_id": saved.get("report_id")}
        except SessionNotFound as exc:
            raise not_found(exc) from exc
        except Exception as exc:
            raise HTTPException(503, "오류 신고를 저장하지 못했습니다.") from exc

    @application.get("/api/sessions/{session_id}/attachments/{attachment_id}")
    def download_attachment(session_id: str, attachment_id: str):
        try:
            path, filename, mime = chat_service().attachment(session_id, attachment_id)
            return FileResponse(path, media_type=mime, filename=filename)
        except SessionNotFound as exc:
            raise not_found(exc) from exc
        except AttachmentNotFound as exc:
            raise HTTPException(404, "첨부파일을 찾을 수 없습니다.") from exc

    @application.get("/")
    def index():
        return FileResponse(BASE / "static" / "index.html")

    application.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
    application.mount("/assets", StaticFiles(directory=ROOT / "chatbot" / "assets"), name="assets")
    return application


app = create_app()
