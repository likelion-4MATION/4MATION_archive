from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from web.main import create_app
from web.service import ChatService


def result(text="답변입니다.", *, attachments=None):
    return {
        "text": text,
        "sources": [{"title": "안내 문서", "url": "https://example.test", "doc_id": "doc-1"}],
        "confidence": 0.82,
        "route": "rag",
        "checks": {"ok": True, "flags": []},
        "attachments": attachments or [],
        "_meta": {"latency_ms": 12, "retrieval": []},
    }


class FakeCatalog:
    def payload(self, _history):
        return {"landing": [], "context_title": "추천", "context": [], "domains": []}


class FakeBackend:
    def __init__(self):
        self._calls = 0
        self.reported = []

    def new_flow(self):
        return {"qform": {}, "pending_slot": None, "unit_queue": [], "queue": []}

    def start(self, flow, text, _ui, _report_context):
        if text == "explode":
            flow["mutated"] = True
            raise RuntimeError("boom")
        if text == "ask":
            flow["pending_slot"] = "qualification"
            return {"kind": "ask", "prompt": "신청 자격을 선택해 주세요.", "remaining": 2,
                    "ask": {"mode": "template", "calls": 0, "fallback_reason": None}}
        self._calls += 1
        attachments = None
        if text == "attachment":
            attachments = [{"available": True, "abs_path": str(Path(__file__).resolve()),
                            "orig_filename": "test_web_api.py", "mime": "text/x-python"}]
        return {"kind": "answer", "result": result(attachments=attachments), "slots": {},
                "search_q": text, "boosted": None, "survivors": []}

    def reply(self, flow, text, _ui, *, value=None):
        flow["pending_slot"] = None
        flow["qform"] = {"qualification": value or text}
        self._calls += 1
        return {"kind": "answer", "result": result("조건을 반영한 답변입니다."),
                "slots": dict(flow["qform"]), "search_q": text,
                "boosted": None, "survivors": []}

    def skip(self, flow, _ui):
        flow["pending_slot"] = None
        self._calls += 1
        return {"kind": "answer", "result": result("건너뛴 답변입니다."), "slots": {},
                "search_q": "ask", "boosted": None, "survivors": []}

    def edit(self, flow, field, value, _ui):
        flow.setdefault("qform", {})[field] = value
        flow["pending_slot"] = None
        return {"kind": "ready", "field": field, "value": value, "slots": flow["qform"]}

    def answer_now(self, flow, _ui):
        self._calls += 1
        return {"kind": "answer", "result": result("재생성 답변입니다."),
                "slots": dict(flow.get("qform") or {}), "search_q": "q",
                "boosted": None, "survivors": []}

    def next_unit(self, flow, _ui, _report_context):
        flow["unit_queue"] = []
        return {"kind": "answer", "result": result("다음 용건입니다."), "slots": {},
                "search_q": "next", "boosted": None, "survivors": []}

    def memory(self, flow, op, **kwargs):
        if op == "pass":
            flow["pending_slot"] = None
        return {"kind": "ready", **kwargs}

    def options(self, flow):
        return ["본인", "대리인"] if flow.get("pending_slot") else []

    def memory_model(self, _flow, _ui):
        return {"zones": []}

    def followups(self, _slots):
        return []

    def trace(self, *_args, **_kwargs):
        return {"layers": {}}

    @property
    def call_count(self):
        return self._calls

    @property
    def call_budget(self):
        return 70

    @property
    def model_name(self):
        return "fake"

    def create_report(self, payload, session_id, target_message_id):
        self.reported.append((payload, session_id, target_message_id))
        return {"report_id": "rpt_test"}


def client_and_service():
    service = ChatService(FakeBackend(), catalog=FakeCatalog())
    return TestClient(create_app(service), raise_server_exceptions=False), service


def test_session_answer_and_delete():
    client, _service = client_and_service()
    created = client.post("/api/sessions", json={})
    assert created.status_code == 201
    sid = created.json()["session_id"]

    answered = client.post(f"/api/sessions/{sid}/messages", json={"text": "질문"})
    assert answered.status_code == 200
    assert [turn["role"] for turn in answered.json()["history"]] == ["user", "answer"]
    assert answered.json()["history"][-1]["text"] == "답변입니다."

    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_static_response_has_browser_security_headers():
    client, _service = client_and_service()
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_sidebar_uses_plain_list_and_collapsible_memory():
    root = Path(__file__).resolve().parents[1]
    html = (root / "web" / "static" / "index.html").read_text(encoding="utf-8")
    script = (root / "web" / "static" / "app.js").read_text(encoding="utf-8")

    assert '<ul id="question-history"' in html
    assert '<details id="memory-section"' in html
    assert "고치면 →" not in script


def test_attachment_cannot_escape_crawler_file_directory():
    client, _service = client_and_service()
    sid = client.post("/api/sessions", json={}).json()["session_id"]
    snapshot = client.post(
        f"/api/sessions/{sid}/messages", json={"text": "attachment"},
    ).json()
    attachment = snapshot["history"][-1]["attachments"][0]

    assert attachment["available"] is True
    assert client.get(attachment["download_url"]).status_code == 404


def test_qform_choose_and_regenerate():
    client, _service = client_and_service()
    sid = client.post("/api/sessions", json={}).json()["session_id"]

    asked = client.post(f"/api/sessions/{sid}/messages", json={"text": "ask"}).json()
    assert asked["state"]["pending"]["options"] == ["본인", "대리인"]

    answered = client.post(
        f"/api/sessions/{sid}/actions", json={"type": "choose", "value": "본인"},
    ).json()
    assert answered["state"]["pending"] is None
    assert answered["history"][-1]["text"] == "조건을 반영한 답변입니다."

    edited = client.post(
        f"/api/sessions/{sid}/actions",
        json={"type": "edit", "field": "qualification", "value": None},
    ).json()
    assert edited["state"]["needs_regen"] is True

    regenerated = client.post(
        f"/api/sessions/{sid}/actions", json={"type": "regenerate"},
    ).json()
    assert regenerated["state"]["needs_regen"] is False
    assert regenerated["history"][-1]["text"] == "재생성 답변입니다."


def test_settings_report_and_atomic_failure():
    client, service = client_and_service()
    sid = client.post("/api/sessions", json={}).json()["session_id"]

    settings = client.patch(
        f"/api/sessions/{sid}/settings", json={"boost": True, "qform_scope": "msdr+dpin"},
    ).json()["state"]["settings"]
    assert settings["boost"] is True
    assert settings["qform_scope"] == "msdr+dpin"

    report = client.post(f"/api/sessions/{sid}/reports", json={})
    assert report.status_code == 201
    assert report.json() == {"ok": True, "report_id": "rpt_test"}

    before = service.get_session(sid)["history"]
    failed = client.post(f"/api/sessions/{sid}/messages", json={"text": "explode"})
    assert failed.status_code == 500
    assert service.get_session(sid)["history"] == before


def test_input_validation():
    client, _service = client_and_service()
    sid = client.post("/api/sessions", json={}).json()["session_id"]
    assert client.post(f"/api/sessions/{sid}/messages", json={"text": ""}).status_code == 422
    assert client.post(f"/api/sessions/{sid}/actions", json={"type": "choose"}).status_code == 400
    assert client.patch(f"/api/sessions/{sid}/settings", json={"qform_scope": "all"}).status_code == 422
