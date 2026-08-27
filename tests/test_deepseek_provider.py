from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "chatbot"))
chain = importlib.import_module("chain")
rag_deepseek = importlib.import_module("rag_deepseek")


class _Response:
    status_code = 200
    text = ""

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


def test_deepseek_chat_completions_contract(monkeypatch):
    seen = {}

    def fake_post(url, *, json, timeout, headers):
        seen.update(url=url, payload=json, timeout=timeout, headers=headers)
        return _Response({"choices": [{"message": {"content": "테스트 답변"}}]})

    monkeypatch.setattr(chain, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(chain, "DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
    monkeypatch.setattr(chain, "DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setattr(chain, "_calls", 0)
    monkeypatch.setattr(chain.requests, "post", fake_post)

    text, meta = chain._deepseek(
        [{"role": "user", "content": "테스트"}], "test", chain.GEN_PARAMS
    )

    assert text == "테스트 답변"
    assert meta["model_status"] == 200
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert seen["payload"] == {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": "테스트"}],
        "stream": False,
        "temperature": 0.2,
        "top_p": 0.8,
        "max_tokens": 512,
        "thinking": {"type": "disabled"},
    }


def test_missing_deepseek_key_does_not_attempt_network(monkeypatch):
    monkeypatch.setattr(chain, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(chain, "_calls", 0)

    def fail_post(*_args, **_kwargs):
        raise AssertionError("network must not be called without an API key")

    monkeypatch.setattr(chain.requests, "post", fail_post)
    text, meta = chain._deepseek([{"role": "user", "content": "테스트"}], "test")

    assert text is None
    assert meta["error"] == "missing_deepseek_configuration"
    assert chain._calls == 0


def test_hcx_request_and_response_are_normalized(monkeypatch):
    seen = {}

    def fake_post(url, *, json, timeout, headers):
        seen.update(url=url, payload=json, timeout=timeout, headers=headers)
        return _Response({"result": {"message": {"content": "HCX 테스트 답변"}}})

    monkeypatch.setattr(chain, "HCX_API_KEY", "hcx-test-key")
    monkeypatch.setattr(chain, "HCX_API_URL", "https://clova.test/chat-completions/HCX-003")
    monkeypatch.setattr(chain, "HCX_MODEL", "HCX-003")
    monkeypatch.setattr(chain, "_calls", 0)
    monkeypatch.setattr(chain.requests, "post", fake_post)

    text, meta = chain._hcx(
        [{"role": "user", "content": "테스트"}], "paired", chain.GEN_PARAMS
    )

    assert text == "HCX 테스트 답변"
    assert meta["provider"] == "hcx"
    assert meta["model"] == "HCX-003"
    assert seen["url"] == "https://clova.test/chat-completions/HCX-003"
    assert seen["headers"]["Authorization"] == "Bearer hcx-test-key"
    assert seen["headers"]["X-NCP-CLOVASTUDIO-REQUEST-ID"] == "paired-t1"
    assert seen["payload"] == {
        "messages": [{"role": "user", "content": "테스트"}],
        "temperature": 0.2,
        "topP": 0.8,
        "maxTokens": 512,
    }


def test_deepseek_rag_entrypoint_uses_explicit_provider(monkeypatch):
    hits = [{"page_title": "문서", "text": "근거", "parent_doc_id": "doc-1"}]

    class _Searcher:
        def search(self, query, *, k, mode):
            assert (query, k, mode) == ("질문", 3, "hybrid")
            return hits

    seen = {}

    def fake_deepseek(messages, req_id, params):
        seen.update(messages=messages, req_id=req_id, params=params)
        return "답변", {"model_status": 200, "latency_ms": 1, "error": None}

    monkeypatch.setattr(rag_deepseek.chain, "get_searcher", lambda: _Searcher())
    monkeypatch.setattr(rag_deepseek.chain, "_deepseek", fake_deepseek)

    answer, actual_hits, meta = rag_deepseek.ask_rag("질문")

    assert answer == "답변"
    assert actual_hits == hits
    assert meta["model_status"] == 200
    assert seen["req_id"] == "deepseek-demo-rag"
    assert "[출처1] 문서\n근거" in seen["messages"][1]["content"]
