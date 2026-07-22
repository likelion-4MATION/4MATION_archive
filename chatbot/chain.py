"""chain.py — answer() 계약 4필드 초안 (밤1 T5). **동결 아님 — 동결 서명은 사람.**

계약(crawler/DECISIONS.md 07-21 초안): answer(query) -> {text, sources, confidence, route}
  - 4필드 축소 없음 보장, 추가만 가능(본 초안은 관측용 "checks"를 부가).
  - route: "rag" | "link" | "reject" — 본 초안은 훅 자리만(항상 "rag").
    TODO(사람: T3 라우팅 규칙 채택 후): 검색 신호 단독 라우팅은 밤1 실측상 불가
    (reject 기대군도 bf 다수결 10/11 충족·dense 대역 겹침) — 질문 분류 단계가 필요.
  - confidence: 표시용 dense 코사인 top1 (밤1 T2 실측 추천 — AUC merged .716/natural .562).
    **임계값 정책 금지(멘토링 Q12)** — 값은 표기만 하고 분기에 쓰지 않는다.
  - URL·전화번호는 sources에 있는 것만 허용(확정) — 프롬프트 v2 + answer_checks 플래그(차단 아님).

프롬프트 v2 근거(전야 데모 + 밤1 실측): Q3 근거 이탈·URL 날조 → 규칙 1·2·3,
Q1 롤렛의 '과거' 한정 탈락 → 규칙 4, Q6 백만원 단위 오환산(밤1 검증기 발견) → 규칙 5.

사용: python3 chatbot/chain.py   # 관통 3콜(정상·트랩·롤렛) — HCX 예산 총 10콜 내
"""
import json
import os
import pathlib
import sys
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.dont_write_bytecode = True

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "crawler"))
sys.path.insert(0, str(ROOT / "chatbot"))
load_dotenv(ROOT / ".env")  # 키 값은 어떤 로그·에러에도 싣지 않는다

import answer_checks

API_KEY = os.environ["CLOVA_API_KEY"]
API_URL = os.environ["CLOVA_API_URL"]
MODEL_NAME = os.environ.get("CLOVA_MODEL", "(미설정)")

GEN_PARAMS = {"temperature": 0.2, "topP": 0.8, "maxTokens": 512}  # 전야와 동일(재현성)
CALL_BUDGET = 10  # 밤1 예산(재시도 포함) — chatbot/CLAUDE.md v2 금지 5항
_calls = 0

SYS_PROMPT_V2 = (
    "너는 예금보험공사(KDIC) 안내 챗봇이다. 아래 [참고문서]에만 근거해서 답하라.\n"
    "규칙:\n"
    "1. 참고문서에 없는 내용은 답하지 말고 \"안내 문서에서 확인되지 않는 내용입니다\"라고 말하라. "
    "알고 있는 지식으로 보충하지 마라.\n"
    "2. URL·전화번호는 참고문서에 적힌 것만 그대로 옮겨라. 새 URL을 만들지 마라.\n"
    "3. 근거로 쓴 문장 끝마다 [출처N]을 표기하라. 출처 없이 서술하지 마라.\n"
    "4. 참고문서의 서술이 과거형(\"과거에는\")이거나 조건부(\"~인 경우\")면 그 한정을 그대로 유지하라. "
    "현재 사실로 바꾸지 마라.\n"
    "5. 금액·수치는 참고문서 표기 그대로 적어라. 단위 환산을 하지 마라."
)

_searcher = None


def get_searcher():
    global _searcher
    if _searcher is None:
        from rag import Searcher
        _searcher = Searcher(index_dir=str(ROOT / "crawler" / "data" / "index"))
    return _searcher


def _hcx(messages: list[dict], req_id: str) -> tuple[str | None, dict]:
    """smoke_hcx.py 검증 구조. 실패 시 콜당 1회 재시도. 예외는 타입명만 기록(.env 보호)."""
    global _calls
    meta = {"hcx_status": None, "latency_ms": None, "error": None}
    for attempt in (1, 2):
        if _calls >= CALL_BUDGET:
            meta["error"] = "call_budget_exhausted"
            return None, meta
        _calls += 1
        t0 = time.time()
        try:
            r = requests.post(API_URL, json={"messages": messages, **GEN_PARAMS}, timeout=30, headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "X-NCP-CLOVASTUDIO-REQUEST-ID": f"{req_id}-t{attempt}",
            })
            meta["latency_ms"] = int((time.time() - t0) * 1000)
            meta["hcx_status"] = r.status_code
            if r.status_code == 200:
                return r.json()["result"]["message"]["content"], meta
            meta["error"] = f"http_{r.status_code}:" + r.text[:200].replace("\n", " ")
        except Exception as e:
            meta["latency_ms"] = int((time.time() - t0) * 1000)
            meta["error"] = f"exception:{type(e).__name__}"
        time.sleep(5 if meta["hcx_status"] == 429 else 2)
    return None, meta


def _confidence(query: str) -> float:
    """표시용 confidence — dense 코사인 top1 (T2 추천). 정책 분기에 쓰지 말 것(Q12)."""
    d1 = get_searcher().search(query, k=1, mode="dense")
    return round(float(d1[0]["_score"]), 4) if d1 else 0.0


def _route(query: str, hits: list[dict]) -> str:
    """라우팅 훅 — 초안은 항상 "rag".

    TODO(사람 채택 후 활성화 — exp/night1_report.md T3):
      · 1안: 질문 분류(소관밖/모호/정상) 선행 — 검색 신호 단독으로는 분리 불가(밤1 실측).
      · 보조 신호: top-3 bf 만장일치(정상 강화) · 질문 의도 bf ≠ top-3 다수 bf(미적중 시그니처).
    """
    return "rag"


def answer(query: str, k: int = 3) -> dict:
    """계약 4필드 + 부가(checks·메타). URL은 sources에서만 조립(모델 생성 금지)."""
    hits = get_searcher().search(query, k=k, mode="hybrid")
    context = "\n\n".join(f"[출처{i}] {h['page_title']}\n{h['text']}" for i, h in enumerate(hits, 1))
    messages = [{"role": "system", "content": SYS_PROMPT_V2},
                {"role": "user", "content": f"[참고문서]\n{context}\n\n[질문]\n{query}"}]
    text, meta = _hcx(messages, req_id="chain")

    sources, seen = [], set()
    for h in hits:
        if h["parent_doc_id"] not in seen:
            seen.add(h["parent_doc_id"])
            sources.append({"title": h["page_title"], "url": h["source_url"], "doc_id": h["parent_doc_id"]})

    checks = (answer_checks.run_all(text, hits, allow_context_urls=False)  # 확정(사람 결정): sources 밖 URL은 본문 유래여도 플래그
              if text is not None else {"ok": False, "flags": ["생성 실패 — 검증 생략"], "results": {}})
    return {
        "text": text,
        "sources": sources,
        "confidence": _confidence(query),
        "route": _route(query, hits),
        "checks": checks,           # 부가 필드(계약 외 추가 — 축소 아님)
        "_meta": {"model": MODEL_NAME, **meta, "k": k},
    }


if __name__ == "__main__":
    probes = [
        ("정상", "예금보험금은 어떻게 신청하나요?"),
        ("트랩(해외)", "미국 FDIC의 예금 보호한도는 얼마인가요?"),
        ("롤렛(보호한도)", "예금자 보호 한도는 얼마인가요?"),
    ]
    for label, q in probes:
        r = answer(q)
        print(f"══ [{label}] {q}")
        print(f"   route={r['route']} · confidence(dense cos)={r['confidence']}"
              f" · status={r['_meta']['hcx_status']} · {r['_meta']['latency_ms']}ms")
        print(f"   sources: " + " | ".join(s["title"] for s in r["sources"]))
        print(f"   checks: {'통과' if r['checks']['ok'] else r['checks']['flags']}")
        print(f"   답변: {r['text']}\n")
    print(f"[calls] 이번 실행 HCX 콜(재시도 포함): {_calls} / 예산 {CALL_BUDGET}")
