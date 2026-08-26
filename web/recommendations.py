"""저장소 원문만 사용하는 추천 질문 공급자."""
from __future__ import annotations

import json
import pathlib
import re
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent

EXAMPLE_CHIPS = [
    ("착오송금 반환 신청", "착오송금 반환 신청 서류가 뭐예요?"),
    ("예금자보호제도", "예금보호한도가 얼마인가요?"),
    ("예금보험금 안내", "예금보험금은 어떻게 신청하나요?"),
    ("고객 미수령금 신청", "고객 미수령금은 어떻게 조회하고 신청하나요?"),
    ("채무조정 안내", "채무조정 신청하려면 어떻게 해요?"),
    ("은닉재산 신고", "은닉재산 신고하면 포상금 얼마나 받나요?"),
]
LANDING_LABELS = ("예금보험금 안내", "고객 미수령금 신청", "착오송금 반환 신청")

_POLITE_RE = re.compile(r"(요|니까)\?$")
_CONFIRM_RE = re.compile(r"시겠(습니까|어요|나요)\?$")
_FAQ_RE = re.compile(r"질문\s*\n(.+?)\n\s*답변", re.S)


def _polite(value: str) -> bool:
    value = value.strip()
    return bool(_POLITE_RE.search(value)) and not _CONFIRM_RE.search(value)


class RecommendationCatalog:
    def __init__(self, root: pathlib.Path = ROOT):
        self.root = root
        self._loaded = False
        self._lock = threading.Lock()
        self._trending: list[str] = []
        self._context: dict[str, list[str]] = {}
        self._representative: dict[str, list[str]] = {}

    def _load(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            trending: list[str] = []
            try:
                path = self.root / "crawler" / "data" / "chunks.jsonl"
                for line in path.open(encoding="utf-8"):
                    row = json.loads(line)
                    if "FAQ" not in str(row.get("page_title") or ""):
                        continue
                    match = _FAQ_RE.search(str(row.get("text") or ""))
                    if match:
                        question = match.group(1).strip()
                        if _polite(question) and question not in trending:
                            trending.append(question)
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                trending = []

            context: dict[str, list[str]] = {}
            representative: dict[str, list[str]] = {}
            try:
                path = self.root / "crawler" / "data" / "testset_natural_450.jsonl"
                for line in path.open(encoding="utf-8"):
                    row = json.loads(line)
                    bf = row.get("business_function")
                    question = str(row.get("question") or "").strip()
                    origin = str(row.get("origin_question") or "").strip()
                    if bf and question and _polite(question):
                        bucket = context.setdefault(str(bf), [])
                        if question not in bucket and len(bucket) < 5:
                            bucket.append(question)
                    if bf and origin and _polite(origin):
                        bucket = representative.setdefault(str(bf), [])
                        if origin not in bucket and len(bucket) < 6:
                            bucket.append(origin)
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                context, representative = {}, {}

            self._trending = trending[:6]
            self._context = context
            self._representative = representative
            self._loaded = True

    def payload(self, history: list[dict]) -> dict:
        self._load()
        current_bf = None
        for turn in reversed(history):
            if turn.get("role") != "answer":
                continue
            routing = turn.get("routing") or ((turn.get("r") or {}).get("_meta") or {}).get("routing")
            if routing and routing.get("triggered"):
                current_bf = routing.get("bf")
            break
        contextual = list(self._context.get(current_bf) or self._trending)
        return {
            "landing": [
                {"label": label, "question": question}
                for label in LANDING_LABELS
                for chip_label, question in EXAMPLE_CHIPS
                if label == chip_label
            ],
            "context_title": "현재 질문과 비슷한 질문" if current_bf else "지금 뜨는 검색어",
            "context": contextual,
            "domains": [
                {"label": label, "questions": list(self._representative.get(label) or [question])}
                for label, question in EXAMPLE_CHIPS
            ],
        }

