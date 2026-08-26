"""사용자용 챗봇 API 요청 스키마."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    new_topic: bool = False


class ActionBody(BaseModel):
    type: Literal["choose", "skip", "pass", "edit", "regenerate", "next_unit", "memory"]
    value: str | None = Field(default=None, max_length=500)
    field: str | None = Field(default=None, max_length=80)
    op: Literal["edit", "clear", "pass", "drop", "move"] | None = None
    index: int | None = Field(default=None, ge=0)
    delta: int = Field(default=-1, ge=-10, le=10)


class SettingsBody(BaseModel):
    ask_mode: Literal["template", "llm"] | None = None
    boost: bool | None = None
    qform_scope: Literal["msdr", "msdr+dpin"] | None = None
    show_trace: bool | None = None


class ReportBody(BaseModel):
    target_message_id: str | None = Field(default=None, max_length=80)

