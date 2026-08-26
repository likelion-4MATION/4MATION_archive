"""메모리 기반 대화 세션 저장소.

PoC 서버 한 프로세스 안에서만 상태를 유지한다. 각 세션은 별도 잠금을 가져 같은
대화에 대한 중복 요청이 상태 전이를 엇갈리게 만들지 않는다.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class SessionRecord:
    session_id: str
    flow: dict
    history: list[dict] = field(default_factory=list)
    needs_regen: bool = False
    settings: dict = field(default_factory=lambda: {
        "ask_mode": "template",
        "boost": False,
        "qform_scope": "msdr",
        "show_trace": False,
    })
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def touch(self, now: Callable[[], float] = time.time) -> None:
        self.updated_at = now()


class SessionNotFound(KeyError):
    pass


class SessionStore:
    def __init__(self, flow_factory: Callable[[], dict], *, ttl_seconds: int = 60 * 60 * 8,
                 now: Callable[[], float] = time.time):
        self._flow_factory = flow_factory
        self._ttl = ttl_seconds
        self._now = now
        self._items: dict[str, SessionRecord] = {}
        self._lock = threading.RLock()

    def _purge_locked(self) -> int:
        cutoff = self._now() - self._ttl
        expired = [sid for sid, rec in self._items.items() if rec.updated_at < cutoff]
        for sid in expired:
            del self._items[sid]
        return len(expired)

    def create(self) -> SessionRecord:
        with self._lock:
            self._purge_locked()
            sid = f"sess_{uuid.uuid4().hex[:16]}"
            rec = SessionRecord(session_id=sid, flow=self._flow_factory())
            rec.created_at = rec.updated_at = self._now()
            self._items[sid] = rec
            return rec

    def get(self, session_id: str) -> SessionRecord:
        with self._lock:
            self._purge_locked()
            rec = self._items.get(session_id)
            if rec is None:
                raise SessionNotFound(session_id)
            rec.touch(self._now)
            return rec

    def delete(self, session_id: str) -> None:
        with self._lock:
            if self._items.pop(session_id, None) is None:
                raise SessionNotFound(session_id)

    def purge(self) -> int:
        with self._lock:
            return self._purge_locked()

