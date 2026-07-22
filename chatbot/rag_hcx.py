"""rag_hcx.py — 맨몸 HCX vs RAG(top-3) 대조 데모 (실전2 ③ 야간 런).

프로덕션 아님 — 관측·기록용. 검색은 crawler/rag.py의 계약 동결된 Searcher를 소비만 한다.
(계약: search(query, k, mode) -> list[dict], 리스트 순서=랭크, hybrid _score=RRF라 임계값 비교 금지 — 표기만)

사용법:
  python3 chatbot/rag_hcx.py single ["질문"]   # 단건 관통: RAG vs 맨몸 대조 출력 (HCX 2콜, 파일 미기록)
  python3 chatbot/rag_hcx.py batch             # 대표 6문항 × {rag, bare} = 12콜 → chatbot/demo_results.jsonl
"""
import json
import os
import pathlib
import sys
import time

# 네트워크는 CLOVA API 1곳만 — HF 허브 재검증·다운로드 차단(임베딩 모델은 로컬 캐시 사용)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.dont_write_bytecode = True

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "crawler"))  # rag.py 무수정 원칙 — 경로는 실행 스크립트 쪽에서 조정
load_dotenv(ROOT / ".env")  # 키 값은 어떤 로그·에러 메시지에도 싣지 않는다

API_KEY = os.environ["CLOVA_API_KEY"]
API_URL = os.environ["CLOVA_API_URL"]
MODEL_NAME = os.environ.get("CLOVA_MODEL", "(미설정)")

TESTSET = ROOT / "crawler" / "data" / "testset_merged.jsonl"
OUT_PATH = pathlib.Path(__file__).resolve().parent / "demo_results.jsonl"

# 파라미터 고정 (재현성 우선 — task_assignment T2)
GEN_PARAMS = {"temperature": 0.2, "topP": 0.8, "maxTokens": 512}
SYS_RAG = (
    "너는 예금보험공사 안내 챗봇이다. 아래 참고문서에만 근거해 답하라. "
    "문서에 없으면 모른다고 답하라. 답변 끝에 사용한 출처 번호를 표기하라."
)
SYS_BARE = "너는 예금보험공사 안내 챗봇이다. 간결히 답한다."  # smoke_hcx.py와 동일(대조군)

CALL_BUDGET = 20  # 재시도 포함 총 상한 (chatbot/CLAUDE.md 금지 5항)
_calls = 0

_searcher = None


def get_searcher():
    """Searcher 1회 생성 후 재사용 (임베딩 모델 로드 비용)."""
    global _searcher
    if _searcher is None:
        from rag import Searcher
        _searcher = Searcher(index_dir=str(ROOT / "crawler" / "data" / "index"))
    return _searcher


def _hcx(messages: list[dict], req_id: str) -> tuple[str | None, dict]:
    """HCX 1회 호출 + 실패 시 콜당 1회 재시도. (답변텍스트|None, 호출메타) 반환.

    예외 문자열에는 URL이 포함될 수 있어 타입명만 기록한다(.env 내용 로그 금지).
    """
    global _calls
    meta = {"hcx_status": None, "latency_ms": None, "error": None}
    for attempt in (1, 2):
        if _calls >= CALL_BUDGET:
            meta["error"] = "call_budget_exhausted"
            return None, meta
        _calls += 1
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "X-NCP-CLOVASTUDIO-REQUEST-ID": f"{req_id}-t{attempt}",
        }
        t0 = time.time()
        try:
            r = requests.post(
                API_URL, headers=headers,
                json={"messages": messages, **GEN_PARAMS}, timeout=30,
            )
            meta["latency_ms"] = int((time.time() - t0) * 1000)
            meta["hcx_status"] = r.status_code
            if r.status_code == 200:
                return r.json()["result"]["message"]["content"], meta
            meta["error"] = f"http_{r.status_code}:" + r.text[:200].replace("\n", " ")
        except Exception as e:
            meta["latency_ms"] = int((time.time() - t0) * 1000)
            meta["error"] = f"exception:{type(e).__name__}"
        time.sleep(5 if meta["hcx_status"] == 429 else 2)  # 재시도 전 대기(429는 길게)
    return None, meta


def build_context(hits: list[dict]) -> str:
    return "\n\n".join(f"[출처{i}] {h['page_title']}\n{h['text']}" for i, h in enumerate(hits, 1))


def ask_rag(query: str, k: int = 3, req_id: str = "demo-rag") -> tuple[str | None, list[dict], dict]:
    """Searcher hybrid top-k → 컨텍스트 조립 → HCX. (답변텍스트, hits, 호출메타) 반환."""
    hits = get_searcher().search(query, k=k, mode="hybrid")
    user = f"[참고문서]\n{build_context(hits)}\n\n[질문]\n{query}"
    messages = [{"role": "system", "content": SYS_RAG}, {"role": "user", "content": user}]
    answer, meta = _hcx(messages, req_id)
    return answer, hits, meta


def ask_bare(query: str, req_id: str = "demo-bare") -> tuple[str | None, dict]:
    """컨텍스트 없이 최소 시스템 프롬프트로 HCX 호출 (대조군)."""
    messages = [{"role": "system", "content": SYS_BARE}, {"role": "user", "content": query}]
    return _hcx(messages, req_id)


def load_representative() -> list[dict]:
    rows = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in rows if r.get("representative") is True]


def run_single(query: str) -> None:
    print(f"[single] 모델={MODEL_NAME} | Q: {query}")
    answer, hits, meta = ask_rag(query, req_id="demo-single-rag")
    print("\n== 검색 top-3 (hybrid) ==")
    for i, h in enumerate(hits, 1):
        print(f"  {i}. ({h['_score']:.4f}) {h['page_title']}  | {h['parent_doc_id']}")
    print(f"\n== RAG 답변 == (status={meta['hcx_status']}, {meta['latency_ms']}ms)")
    print(answer if answer is not None else f"(실패: {meta['error']})")
    b_answer, b_meta = ask_bare(query, req_id="demo-single-bare")
    print(f"\n== 맨몸 답변 == (status={b_meta['hcx_status']}, {b_meta['latency_ms']}ms)")
    print(b_answer if b_answer is not None else f"(실패: {b_meta['error']})")
    print(f"\n[calls] 이번 실행 HCX 콜 수(재시도 포함): {_calls}")


def run_batch() -> None:
    reps = load_representative()
    print(f"[batch] 대표 {len(reps)}문항 × {{rag, bare}} — 예상 {len(reps) * 2}콜 (상한 {CALL_BUDGET})")
    rows_out = []
    for i, r in enumerate(reps, 1):
        q, gt = r["question"], r["gt_docs"]

        answer, hits, meta = ask_rag(q, req_id=f"demo-b{i:02d}-rag")
        top3 = [{f: h[f] for f in ("page_title", "source_url", "parent_doc_id", "_score")} for h in hits]
        hit = bool({h["parent_doc_id"] for h in hits} & set(gt))
        rows_out.append({
            "query": q, "mode": "rag", "top3": top3, "answer": answer,
            "gt_docs": gt, "retrieval_hit": hit,
            "hcx_status": meta["hcx_status"], "latency_ms": meta["latency_ms"],
            "error": meta["error"], "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        print(f"  [{i}/{len(reps)}][rag ] hit={hit} status={meta['hcx_status']} {meta['latency_ms']}ms")
        time.sleep(1.0)

        b_answer, b_meta = ask_bare(q, req_id=f"demo-b{i:02d}-bare")
        rows_out.append({
            "query": q, "mode": "bare", "top3": None, "answer": b_answer,
            "gt_docs": None, "retrieval_hit": None,
            "hcx_status": b_meta["hcx_status"], "latency_ms": b_meta["latency_ms"],
            "error": b_meta["error"], "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        print(f"  [{i}/{len(reps)}][bare] status={b_meta['hcx_status']} {b_meta['latency_ms']}ms")
        time.sleep(1.0)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for row in rows_out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    n_hit = sum(1 for row in rows_out if row["mode"] == "rag" and row["retrieval_hit"])
    print(f"[batch] 완료 — {len(rows_out)}행 → {OUT_PATH.name} | retrieval hit {n_hit}/{len(reps)} | HCX 콜 {_calls}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "single"
    if mode == "single":
        run_single(sys.argv[2] if len(sys.argv) > 2 else "예금자보호 한도는 얼마야?")
    elif mode == "batch":
        run_batch()
    else:
        sys.exit("사용법: python3 chatbot/rag_hcx.py [single [\"질문\"] | batch]")
