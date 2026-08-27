"""DeepSeek RAG vs 맨몸 대조 데모.

앱의 ``LLM_PROVIDER`` 값과 무관하게 DeepSeek를 명시적으로 호출한다. 결과 파일도
HCX 데모와 분리해 두 모델을 같은 워크트리에서 안전하게 비교할 수 있게 한다.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import chain


ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTSET = ROOT / "crawler" / "data" / "testset_merged.jsonl"
OUT_PATH = pathlib.Path(__file__).resolve().parent / "demo_results_deepseek.jsonl"

SYS_RAG = (
    "너는 예금보험공사 안내 챗봇이다. 아래 참고문서에만 근거해 답하라. "
    "문서에 없으면 모른다고 답하라. 답변 끝에 사용한 출처 번호를 표기하라."
)
SYS_BARE = "너는 예금보험공사 안내 챗봇이다. 간결히 답한다."


def build_context(hits: list[dict]) -> str:
    return "\n\n".join(
        f"[출처{i}] {hit['page_title']}\n{hit['text']}"
        for i, hit in enumerate(hits, 1)
    )


def ask_rag(query: str, k: int = 3,
            req_id: str = "deepseek-demo-rag") -> tuple[str | None, list[dict], dict]:
    hits = chain.get_searcher().search(query, k=k, mode="hybrid")
    user = f"[참고문서]\n{build_context(hits)}\n\n[질문]\n{query}"
    messages = [
        {"role": "system", "content": SYS_RAG},
        {"role": "user", "content": user},
    ]
    answer, meta = chain._deepseek(messages, req_id, chain.GEN_PARAMS)
    return answer, hits, meta


def ask_bare(query: str,
             req_id: str = "deepseek-demo-bare") -> tuple[str | None, dict]:
    messages = [
        {"role": "system", "content": SYS_BARE},
        {"role": "user", "content": query},
    ]
    return chain._deepseek(messages, req_id, chain.GEN_PARAMS)


def load_representative() -> list[dict]:
    rows = [
        json.loads(line)
        for line in TESTSET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [row for row in rows if row.get("representative") is True]


def run_single(query: str) -> None:
    print(f"[single] 모델={chain.DEEPSEEK_MODEL} | Q: {query}")
    answer, hits, meta = ask_rag(query, req_id="deepseek-single-rag")
    print("\n== 검색 top-3 (hybrid) ==")
    for i, hit in enumerate(hits, 1):
        print(f"  {i}. ({hit['_score']:.4f}) {hit['page_title']} | {hit['parent_doc_id']}")
    print(f"\n== RAG 답변 == (status={meta['model_status']}, {meta['latency_ms']}ms)")
    print(answer if answer is not None else f"(실패: {meta['error']})")

    bare_answer, bare_meta = ask_bare(query, req_id="deepseek-single-bare")
    print(f"\n== 맨몸 답변 == (status={bare_meta['model_status']}, {bare_meta['latency_ms']}ms)")
    print(bare_answer if bare_answer is not None else f"(실패: {bare_meta['error']})")
    print(f"\n[calls] 이번 실행 DeepSeek 콜 수(재시도 포함): {chain._calls}")


def run_batch() -> None:
    representatives = load_representative()
    expected = len(representatives) * 2
    print(f"[batch] 대표 {len(representatives)}문항 × {{rag, bare}} — 예상 {expected}콜")
    output = []
    for i, row in enumerate(representatives, 1):
        question, ground_truth = row["question"], row["gt_docs"]
        answer, hits, meta = ask_rag(question, req_id=f"deepseek-b{i:02d}-rag")
        top3 = [
            {field: hit[field] for field in ("page_title", "source_url", "parent_doc_id", "_score")}
            for hit in hits
        ]
        retrieval_hit = bool({hit["parent_doc_id"] for hit in hits} & set(ground_truth))
        output.append({
            "query": question, "mode": "rag", "top3": top3, "answer": answer,
            "gt_docs": ground_truth, "retrieval_hit": retrieval_hit,
            "provider": "deepseek", "model": chain.DEEPSEEK_MODEL,
            "model_status": meta["model_status"], "latency_ms": meta["latency_ms"],
            "error": meta["error"], "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        print(f"  [{i}/{len(representatives)}][rag ] hit={retrieval_hit} "
              f"status={meta['model_status']} {meta['latency_ms']}ms")
        time.sleep(1.0)

        bare_answer, bare_meta = ask_bare(question, req_id=f"deepseek-b{i:02d}-bare")
        output.append({
            "query": question, "mode": "bare", "top3": None, "answer": bare_answer,
            "gt_docs": None, "retrieval_hit": None,
            "provider": "deepseek", "model": chain.DEEPSEEK_MODEL,
            "model_status": bare_meta["model_status"], "latency_ms": bare_meta["latency_ms"],
            "error": bare_meta["error"], "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        print(f"  [{i}/{len(representatives)}][bare] "
              f"status={bare_meta['model_status']} {bare_meta['latency_ms']}ms")
        time.sleep(1.0)

    with OUT_PATH.open("w", encoding="utf-8") as file:
        for row in output:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    hits = sum(1 for row in output if row["mode"] == "rag" and row["retrieval_hit"])
    print(f"[batch] 완료 — {len(output)}행 → {OUT_PATH.name} | "
          f"retrieval hit {hits}/{len(representatives)} | DeepSeek 콜 {chain._calls}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "single"
    if mode == "single":
        run_single(sys.argv[2] if len(sys.argv) > 2 else "예금자보호 한도는 얼마야?")
    elif mode == "batch":
        run_batch()
    else:
        sys.exit('사용법: python3 chatbot/rag_deepseek.py [single ["질문"] | batch]')
