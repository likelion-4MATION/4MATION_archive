from __future__ import annotations

import json
from types import SimpleNamespace

from chatbot import build_judge_batches, eval_answers


def test_p1_sample_meets_documented_strata():
    rows = eval_answers._jsonl(eval_answers.TESTSET)
    sampled = eval_answers._sample(rows, 150, 20260826)

    by_bf = {}
    for row in sampled:
        by_bf[row["business_function"]] = by_bf.get(row["business_function"], 0) + 1
    assert len(sampled) == 150
    assert all(count >= 20 for count in by_bf.values())
    assert sum(row["chunk_relation"] == "and" for row in sampled) >= 25
    assert sum(row["cross_domain"] is True for row in sampled) >= 10
    assert sum(row["evidence_type"] == "inferable" for row in sampled) >= 10
    assert sum(row["answerable"] is False for row in sampled) == 2


def test_judge_batch_blinds_provider_names_and_writes_key(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    context = {
        "item_id": "q1", "question": "질문", "answerable": True,
        "span_verbatim_ok": True, "gt_anchor_span": "정답 구절",
        "context_sha": "same", "context": "[출처1] 근거",
    }
    (data_dir / "contexts.jsonl").write_text(
        json.dumps(context, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    answers = [
        {"item_id": "q1", "repeat_idx": 0, "provider": "hcx", "context_sha": "same",
         "answer": "첫 번째 원본", "error": None},
        {"item_id": "q1", "repeat_idx": 0, "provider": "deepseek", "context_sha": "same",
         "answer": "두 번째 원본", "error": None},
    ]
    (data_dir / "answers.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in answers),
        encoding="utf-8",
    )
    out_dir = tmp_path / "judge"
    paths = build_judge_batches.build(SimpleNamespace(
        data_dir=str(data_dir), out_dir=str(out_dir), batch_size=1,
        repeat_idx=0, seed=20260826, overwrite=False,
    ))

    text = paths[0].read_text(encoding="utf-8")
    item_section = text.split("=== 문항 1 ===", 1)[1]
    assert "provider" not in item_section.lower()
    assert "<답변 A>" in item_section and "<답변 B>" in item_section
    key = json.loads((out_dir / "key.json").read_text(encoding="utf-8"))
    assert set(key["items"]["q1"].values()) == {"hcx", "deepseek"}


def test_answer_runner_searches_once_and_calls_both_providers(monkeypatch, tmp_path):
    source = [{
        "id": "q1", "question": "같은 질문", "business_function": "업무",
        "answerable": True, "evidence_type": "direct", "chunk_relation": "single",
        "cross_domain": False, "span_verbatim_ok": True, "gt_anchor_span": "근거",
    }]

    class Searcher:
        calls = 0

        def search(self, query, k, mode):
            self.calls += 1
            assert (query, k, mode) == ("같은 질문", 3, "hybrid")
            return [{"chunk_id": "c1", "page_title": "문서", "text": "동일 근거"}]

    searcher = Searcher()
    providers = []
    monkeypatch.setattr(eval_answers, "_jsonl", lambda _path: source)
    monkeypatch.setattr(eval_answers.chain, "get_searcher", lambda: searcher)
    monkeypatch.setattr(
        eval_answers.chain, "_provider_settings",
        lambda provider: ("key", "https://example.test", provider + "-model"),
    )

    def fake_llm(messages, req_id, params, *, provider):
        providers.append(provider)
        assert "동일 근거" in messages[1]["content"]
        return provider + " 답변", {
            "model": provider + "-model", "latency_ms": 1,
            "model_status": 200, "error": None,
        }

    monkeypatch.setattr(eval_answers.chain, "_llm", fake_llm)
    monkeypatch.setattr(eval_answers.chain, "CALL_BUDGET", 70)
    monkeypatch.setattr(eval_answers.chain, "_calls", 0)
    args = SimpleNamespace(
        n=1, repeat=1, seed=20260826, k=3, provider="both",
        out_dir=str(tmp_path / "run"), delay=0.0, dry_run=False, overwrite=False,
    )
    contexts_path, answers_path = eval_answers.run(args)

    assert searcher.calls == 1
    assert providers == ["hcx", "deepseek"]
    contexts = [json.loads(line) for line in contexts_path.read_text().splitlines()]
    answers = [json.loads(line) for line in answers_path.read_text().splitlines()]
    assert len({row["context_sha"] for row in answers}) == 1
    assert answers[0]["context_sha"] == contexts[0]["context_sha"]
