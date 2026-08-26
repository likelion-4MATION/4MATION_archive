"""Streamlit 상태를 대체하는 사용자용 챗봇 서비스 계층."""
from __future__ import annotations

import copy
import pathlib
import re
import sys
import threading
import uuid
from datetime import datetime, timezone

from web.recommendations import RecommendationCatalog
from web.sessions import SessionNotFound, SessionRecord, SessionStore

ROOT = pathlib.Path(__file__).resolve().parent.parent
for _path in (ROOT / "chatbot", ROOT / "crawler", ROOT / "admin"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

SLOT_LABEL = {"party": "역할", "sub_task": "세부주제", "qualification": "자격",
              "subject": "주체", "method": "접수수단"}
ROUTE_LABEL = {"rag": "문서 기반 답변", "link": "타기관 안내", "reject": "소관 밖",
               "oos": "안내 범위 밖 처리"}
_HTTP_RE = re.compile(r"^http_(\d{3})")


class InvalidAction(ValueError):
    pass


class AttachmentNotFound(FileNotFoundError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _humanize_error(code) -> str:
    code = str(code or "")
    if code == "call_budget_exhausted":
        return "이번 서버의 모델 호출 예산을 모두 사용했습니다. 잠시 후 관리자에게 문의해 주세요."
    match = _HTTP_RE.match(code)
    if match:
        return f"모델 서버에서 응답을 받지 못했습니다 (통신 오류 {match.group(1)}). 잠시 후 다시 시도해 주세요."
    if code.startswith("exception:"):
        return "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
    return "일시적인 오류로 답변을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."


class RuntimeBackend:
    """기존 Q-Form·오케스트레이터 모듈을 그대로 호출하는 얇은 어댑터."""

    def __init__(self):
        import settings
        settings.apply_runtime()

        import chain
        import orchestrator
        import oos_store
        import qform_flow
        import qform_followup
        import qform_memory_panel
        import qform_trace

        self.chain = chain
        self.orchestrator = orchestrator
        self.oos_store = oos_store
        self.qform_flow = qform_flow
        self.qform_followup = qform_followup
        self.qmp = qform_memory_panel
        self.qform_trace = qform_trace
        self.settings_store = settings

    def new_flow(self) -> dict:
        return self.qform_flow.new_state()

    def config(self, ui_settings: dict) -> dict:
        config = self.settings_store.qform_override()
        config["QFORM_SCOPE"] = ui_settings["qform_scope"]
        return config

    def start(self, flow: dict, text: str, ui: dict, report_context: dict) -> dict:
        return self.orchestrator.start_turn(
            flow, text, ask_mode=ui["ask_mode"], boost=ui["boost"],
            config=self.config(ui), report_context=report_context,
        )

    def reply(self, flow: dict, text: str, ui: dict, *, value: str | None = None) -> dict:
        return self.qform_flow.reply(
            flow, text, value=value, ask_mode=ui["ask_mode"], boost=ui["boost"],
            config=self.config(ui),
        )

    def skip(self, flow: dict, ui: dict) -> dict:
        return self.qform_flow.skip(flow, boost=ui["boost"], config=self.config(ui))

    def edit(self, flow: dict, field: str, value: str | None, ui: dict) -> dict:
        return self.qform_flow.edit(
            flow, field, value, source="웹 슬롯 수정", ask_mode=ui["ask_mode"],
            config=self.config(ui),
        )

    def answer_now(self, flow: dict, ui: dict) -> dict:
        return self.qform_flow.answer_now(flow, boost=ui["boost"])

    def next_unit(self, flow: dict, ui: dict, report_context: dict) -> dict | None:
        return self.orchestrator.next_unit(
            flow, ask_mode=ui["ask_mode"], boost=ui["boost"],
            config=self.config(ui), report_context=report_context,
        )

    def memory(self, flow: dict, op: str, **kwargs) -> dict:
        return self.qmp.apply(flow, op, **kwargs)

    def options(self, flow: dict) -> list[str]:
        return self.qform_flow.options(flow)

    def memory_model(self, flow: dict, ui: dict) -> dict:
        return self.qmp.panel_model(flow, config=self.config(ui))

    def followups(self, slots: dict) -> list[dict]:
        return self.qform_followup.suggest(slots)

    def trace(self, flow: dict, event: dict, calls: int, boost: bool) -> dict | None:
        try:
            return self.qform_trace.collect(
                flow.get("base_q") or "", self.qform_trace.bf_debug(flow.get("base_q") or ""),
                flow.get("slots_raw") or {}, event.get("survivors"), event.get("ask"),
                event.get("result"), boost, search_q=event.get("search_q"),
                hcx_calls=calls, ask_turn=flow.get("ask_turn") or 0,
            )
        except Exception as exc:  # 진단 실패가 사용자 대화를 막지 않는다
            return {"error": type(exc).__name__, "layers": {}}

    @property
    def call_count(self) -> int:
        return int(self.chain._calls)

    @property
    def call_budget(self) -> int:
        return int(self.chain.CALL_BUDGET)

    @property
    def model_name(self) -> str:
        return str(self.chain.MODEL_NAME)

    def create_report(self, payload: dict, session_id: str, target_message_id: str) -> dict:
        return self.oos_store.create_report(
            payload, session_id=session_id, report_path="web_button",
            target_message_id=target_message_id,
        )


class ChatService:
    def __init__(self, backend=None, *, ttl_seconds: int = 60 * 60 * 8,
                 catalog: RecommendationCatalog | None = None):
        self.backend = backend or RuntimeBackend()
        self.sessions = SessionStore(self.backend.new_flow, ttl_seconds=ttl_seconds)
        self.catalog = catalog or RecommendationCatalog()
        # chain._calls와 검색·모델 객체는 프로세스 전역이다. 1차 PoC는 생성 경로를 직렬화한다.
        self._inference_lock = threading.Lock()

    def create_session(self) -> dict:
        rec = self.sessions.create()
        return self.snapshot(rec)

    def delete_session(self, session_id: str) -> None:
        self.sessions.delete(session_id)

    def get_session(self, session_id: str) -> dict:
        return self.snapshot(self.sessions.get(session_id))

    @staticmethod
    def _append(history: list[dict], turn: dict) -> dict:
        item = {
            **turn,
            "message_id": turn.get("message_id") or f"msg_{uuid.uuid4().hex[:16]}",
            "timestamp": turn.get("timestamp") or _utc_now(),
        }
        history.append(item)
        return item

    @staticmethod
    def _last_answer_id(history: list[dict]) -> str:
        for turn in reversed(history):
            if turn.get("role") == "answer":
                return str(turn.get("message_id") or "")
        return ""

    def _report_context(self, rec: SessionRecord, flow: dict, history: list[dict],
                        target_message_id: str | None = None) -> dict:
        return {
            "session_id": rec.session_id,
            "target_message_id": target_message_id or self._last_answer_id(history),
            "payload": {
                "conversation": history,
                "model_version": self.backend.model_name,
                "qform": flow.get("qform"),
                "slot_origin": flow.get("slot_origin"),
                "queue": flow.get("unit_queue"),
                "qform_queue": flow.get("queue"),
                "routing_history": flow.get("routing_history"),
                "call_count": self.backend.call_count,
            },
        }

    def _record_event(self, history: list[dict], flow: dict, event: dict,
                      ui: dict, calls: int) -> None:
        trace = self.backend.trace(flow, event, calls, ui["boost"]) if ui["show_trace"] else None
        if event["kind"] == "ask":
            ask = event.get("ask") or {}
            self._append(history, {
                "role": "ask", "prompt": event["prompt"],
                "remaining": event.get("remaining"), "mode": ask.get("mode"),
                "calls": ask.get("calls"), "fallback": ask.get("fallback_reason"),
                "options": self.backend.options(flow), "trace": trace,
                "unit": event.get("unit"), "routing": event.get("routing"),
            })
            return
        slots = dict(event.get("slots") or {})
        self._append(history, {
            "role": "answer", "r": event["result"], "slots": slots,
            "search_q": event.get("boosted"), "query": event.get("search_q"),
            "trace": trace, "followups": self.backend.followups(slots),
            "unit": event.get("unit"), "routing": event.get("routing"),
        })

    def send_message(self, session_id: str, text: str, *, new_topic: bool = False) -> dict:
        rec = self.sessions.get(session_id)
        text = text.strip()
        if not text:
            raise InvalidAction("질문을 입력해 주세요.")
        with rec.lock:
            flow = copy.deepcopy(rec.flow)
            history = copy.deepcopy(rec.history)
            target = self._last_answer_id(history)
            self._append(history, {"role": "user", "text": text})
            calls_before = self.backend.call_count
            with self._inference_lock:
                if flow.get("pending_slot") and not new_topic:
                    event = self.backend.reply(flow, text, rec.settings)
                else:
                    event = self.backend.start(
                        flow, text, rec.settings,
                        self._report_context(rec, flow, history, target),
                    )
            self._record_event(history, flow, event, rec.settings,
                               self.backend.call_count - calls_before)
            rec.flow, rec.history = flow, history
            rec.needs_regen = False
            rec.touch()
            return self.snapshot(rec)

    def perform_action(self, session_id: str, body) -> dict:
        rec = self.sessions.get(session_id)
        with rec.lock:
            flow = copy.deepcopy(rec.flow)
            history = copy.deepcopy(rec.history)
            calls_before = self.backend.call_count
            event = None
            action = body.type

            if action == "choose":
                if not flow.get("pending_slot") or not body.value:
                    raise InvalidAction("현재 선택할 조건이 없습니다.")
                self._append(history, {"role": "user", "text": body.value})
                with self._inference_lock:
                    event = self.backend.reply(flow, body.value, rec.settings, value=body.value)
                rec.needs_regen = False
            elif action == "skip":
                if not flow.get("pending_slot"):
                    raise InvalidAction("현재 건너뛸 질문이 없습니다.")
                self._append(history, {"role": "user", "text": "잘 모르겠어요 — 이대로 답변받기"})
                with self._inference_lock:
                    event = self.backend.skip(flow, rec.settings)
                rec.needs_regen = False
            elif action == "pass":
                field = body.field or flow.get("pending_slot")
                if not field:
                    raise InvalidAction("건너뛸 조건이 없습니다.")
                self._append(history, {"role": "user", "text": "이건 넘어갈게요"})
                self.backend.memory(flow, "pass", field=field)
                rec.needs_regen = False
            elif action == "edit":
                if not body.field:
                    raise InvalidAction("수정할 조건이 없습니다.")
                event = self.backend.edit(flow, body.field, body.value, rec.settings)
                label = SLOT_LABEL.get(body.field, body.field)
                note = f"{label} · {body.value}(으)로 변경" if body.value else f"'{label}' 조건 해제"
                self._append(history, {"role": "user", "text": note})
                if event.get("kind") == "ready":
                    event = None
                    rec.needs_regen = True
                else:
                    rec.needs_regen = False
            elif action == "regenerate":
                if not rec.needs_regen:
                    raise InvalidAction("다시 생성할 변경사항이 없습니다.")
                with self._inference_lock:
                    event = self.backend.answer_now(flow, rec.settings)
                rec.needs_regen = False
            elif action == "next_unit":
                if not flow.get("unit_queue") or flow.get("pending_slot"):
                    raise InvalidAction("대기 중인 다음 용건이 없습니다.")
                with self._inference_lock:
                    event = self.backend.next_unit(
                        flow, rec.settings, self._report_context(rec, flow, history),
                    )
                rec.needs_regen = False
            elif action == "memory":
                if not body.op:
                    raise InvalidAction("메모리 조작 종류가 없습니다.")
                kwargs = {}
                if body.field is not None:
                    kwargs["field"] = body.field
                if body.value is not None:
                    kwargs["value"] = body.value
                if body.index is not None:
                    kwargs["index"] = body.index
                if body.op == "move":
                    kwargs["delta"] = body.delta
                self.backend.memory(flow, body.op, **kwargs)
            else:
                raise InvalidAction(f"지원하지 않는 동작입니다: {action}")

            if event is not None:
                self._record_event(history, flow, event, rec.settings,
                                   self.backend.call_count - calls_before)
            rec.flow, rec.history = flow, history
            rec.touch()
            return self.snapshot(rec)

    def update_settings(self, session_id: str, body) -> dict:
        rec = self.sessions.get(session_id)
        with rec.lock:
            updates = body.model_dump(exclude_none=True)
            rec.settings.update(updates)
            rec.touch()
            return self.snapshot(rec)

    def create_report(self, session_id: str, target_message_id: str | None = None) -> dict:
        rec = self.sessions.get(session_id)
        with rec.lock:
            target = target_message_id or self._last_answer_id(rec.history)
            context = self._report_context(rec, rec.flow, rec.history, target)
            return self.backend.create_report(context["payload"], rec.session_id, target)

    @staticmethod
    def _public_attachment(message_id: str, index: int, item: dict, session_id: str) -> dict:
        attachment_id = f"{message_id}-{index}"
        return {
            "id": attachment_id,
            "label": item.get("label") or item.get("orig_filename") or "첨부파일",
            "filename": item.get("orig_filename") or "attachment",
            "kind": item.get("doc_kind"), "size": item.get("file_size"),
            "mime": item.get("mime") or "application/octet-stream",
            "available": bool(item.get("available") and item.get("abs_path")),
            "source_url": item.get("source_url") or "",
            "download_url": f"/api/sessions/{session_id}/attachments/{attachment_id}",
        }

    def _public_turn(self, rec: SessionRecord, turn: dict) -> dict:
        base = {k: turn.get(k) for k in ("role", "message_id", "timestamp")}
        if turn.get("role") == "user":
            return {**base, "text": turn.get("text") or ""}
        if turn.get("role") == "ask":
            return {**base, "prompt": turn.get("prompt") or "", "remaining": turn.get("remaining"),
                    "options": list(turn.get("options") or []), "trace": turn.get("trace")}

        result = turn.get("r") or {}
        meta = result.get("_meta") or {}
        attachments = [
            self._public_attachment(str(turn.get("message_id")), i, item, rec.session_id)
            for i, item in enumerate(result.get("attachments") or [])
        ]
        return {
            **base,
            "text": result.get("text"),
            "error_text": _humanize_error(meta.get("error")) if result.get("text") is None else None,
            "route": result.get("route"), "route_label": ROUTE_LABEL.get(result.get("route"), result.get("route")),
            "confidence": result.get("confidence"), "latency_ms": meta.get("latency_ms"),
            "sources": result.get("sources") or [], "checks": result.get("checks") or {},
            "attachments": attachments, "slots": turn.get("slots") or {},
            "followups": turn.get("followups") or [], "search_q": turn.get("search_q"),
            "retrieval": meta.get("retrieval") or [], "action": meta.get("action"),
            "referral": result.get("referral"), "phone_guide": result.get("phone_guide"),
            "trace": turn.get("trace"),
        }

    def snapshot(self, rec: SessionRecord) -> dict:
        with rec.lock:
            history = [self._public_turn(rec, turn) for turn in rec.history]
            try:
                memory = self.backend.memory_model(rec.flow, rec.settings) if rec.history else {"zones": []}
            except Exception:
                memory = {"zones": []}
            pending = None
            if rec.flow.get("pending_slot"):
                pending = {
                    "field": rec.flow["pending_slot"],
                    "label": SLOT_LABEL.get(rec.flow["pending_slot"], rec.flow["pending_slot"]),
                    "options": self.backend.options(rec.flow),
                }
            remaining = max(0, self.backend.call_budget - self.backend.call_count)
            return {
                "session_id": rec.session_id,
                "history": history,
                "state": {
                    "pending": pending, "needs_regen": rec.needs_regen,
                    "slots": rec.flow.get("qform") or {},
                    "queue_size": len(rec.flow.get("unit_queue") or []),
                    "memory": memory, "settings": dict(rec.settings),
                    "calls": {"used": self.backend.call_count,
                              "budget": self.backend.call_budget, "remaining": remaining},
                },
                "recommendations": self.catalog.payload(rec.history),
            }

    def attachment(self, session_id: str, attachment_id: str) -> tuple[pathlib.Path, str, str]:
        rec = self.sessions.get(session_id)
        with rec.lock:
            for turn in rec.history:
                if turn.get("role") != "answer":
                    continue
                message_id = str(turn.get("message_id"))
                for index, item in enumerate((turn.get("r") or {}).get("attachments") or []):
                    if attachment_id != f"{message_id}-{index}":
                        continue
                    path = pathlib.Path(str(item.get("abs_path") or "")).resolve()
                    if not item.get("available") or not path.is_file():
                        raise AttachmentNotFound(attachment_id)
                    # 크롤러가 내려받은 공개 첨부 산출물 밖의 임의 파일은 내려주지 않는다.
                    allowed = ((ROOT / "crawler" / "data" / "files").resolve(),)
                    if not any(path == root or root in path.parents for root in allowed):
                        raise AttachmentNotFound(attachment_id)
                    return path, str(item.get("orig_filename") or path.name), \
                        str(item.get("mime") or "application/octet-stream")
        raise AttachmentNotFound(attachment_id)
