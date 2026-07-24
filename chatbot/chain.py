"""chain.py — answer() 4필드 + LLM 질문 분류 라우팅 (07-22 route 세션).

계약(임시 동결, DECISIONS.md 07-22): answer(query) -> {text, sources, confidence, route}
  - 4필드 축소 금지 · 부가(checks/_meta/attachments)만 추가 가능. route 내부 구현만 교체 가능.
  - attachments(부가): 근거 문서 첨부 목록(청크 태깅 우선 + 문서 폴백, attachments.collect).
    검색 hits만 소비 → HCX 추가 콜 0. reject 경로는 []. 스키마는 attachments.py._fmt 참조.
  - 새 흐름: **분류(1콜) → [소관밖] 고정 거절 문구 즉시 반환(검색·생성·검증 생략)
    / [정상·모호] 검색 → 생성(1콜) → 검증**. 분류 라벨·사유는 _meta에 기록.
  - confidence: 표시용 dense 코사인 top1("관련 문서 유사도" — 정책 분기 금지, Q12).
    reject 경로는 검색 생략이므로 0.0 고정.
  - 분류 JSON 파싱 실패 시 1회 재시도, 재실패는 안전 기본값 "정상"(과차단 방지) + _meta 기록.
  - CALL_BUDGET=70 (07-22 route 세션, 재시도 포함) — 소진 시 즉시 중단.

프롬프트 v2(생성) 근거: 전야 Q3 근거 이탈·URL 날조 → 규칙 1·2·3, Q1 롤렛 '과거' 한정
탈락 → 규칙 4, Q6 백만원 단위 오환산 → 규칙 5. (밤1 관통 실측 유지)

사용:
  python3 chatbot/chain.py               # 관통 3문항(정상·트랩·롤렛) — 새 흐름 데모
  python3 chatbot/chain.py cls "질문"    # 분류만 1건 (1~2콜)
  python3 chatbot/chain.py smoke        # T1 분류 스모크 3문항 (3콜)
  python3 chatbot/chain.py e2e          # T3 트랩셋 20문항 E2E → exp/route_e2e_results.jsonl
  python3 chatbot/chain.py clsdemo      # T4 정상 6문항 분류만 (6콜)
"""
import json
import os
import pathlib
import re
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
import attachments  # 근거 문서 첨부 조회(청크 태깅 우선 + 문서 폴백) — 순수 로컬, 계약 부가 필드

API_KEY = os.environ["CLOVA_API_KEY"]
API_URL = os.environ["CLOVA_API_URL"]
MODEL_NAME = os.environ.get("CLOVA_MODEL", "(미설정)")

GEN_PARAMS = {"temperature": 0.2, "topP": 0.8, "maxTokens": 512}  # 생성(전야와 동일 — 재현성)
CLS_PARAMS = {"temperature": 0.1, "topP": 0.8, "maxTokens": 128}  # 분류(JSON 한 줄 — 결정성 우선)
CALL_BUDGET = 70  # 07-22 route 세션 예산(재시도 포함) — chatbot/CLAUDE.md v3 금지 5항
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

# 분류 프롬프트 — 트랩셋 문항 원문 인용 금지(과적합 방지), 소관 업무의 일반 서술만 사용.
# 수정 이력: v1 초안 (07-22 route 세션 — 수정권 1회 미사용)
CLS_PROMPT = (
    "너는 예금보험공사(KDIC) 안내 챗봇의 질문 분류기다. 사용자 질문 1건을 아래 3분류 중 하나로 판정한다.\n\n"
    "[정상] — 예금보험공사 소관 업무에 대한 질문. 소관 업무: 예금자보호제도(국내 부보금융회사 예금의 "
    "보호 대상·보호한도), 예금보험금·개산지급금·가지급금의 지급과 신청, 고객 미수령금 조회·신청, "
    "착오송금 반환지원, 부실관련자 은닉재산 신고와 포상금, 부실 금융회사 관련 채무조정·신용회복지원.\n\n"
    "[모호] — 소관 업무와 관련돼 보이나 판단이 어려운 질문. 두 업무를 섞어 물었거나, 업무 경계가 "
    "불분명하거나, 특정 수치·규정이 지금도 맞는지 확인하는 질문.\n\n"
    "[소관밖] — 예금보험공사 소관이 아닌 질문. 외국의 예금보호 제도나 외국 소재 금융기관의 예금, "
    "국내은행 해외지점에 맡긴 예금, 타기관 소관 업무(세금·환급은 국세청, 보이스피싱 피해구제는 "
    "금융감독원·경찰, 투자 손실 보상은 해당 없음, 전세보증금 보증은 HUG 등, 휴면예금은 서민금융진흥원), "
    "금융과 무관한 일반 질문.\n\n"
    "판단이 서지 않으면 \"모호\"를 택한다(\"소관밖\" 단정은 확실할 때만).\n\n"
    "출력 규칙: 아래 형식의 JSON 한 개만 출력한다. 백틱·코드블록·설명·머리말을 붙이지 마라.\n"
    "{\"label\": \"정상\" 또는 \"모호\" 또는 \"소관밖\", \"reason\": \"판정 사유 한 줄\"}"
)

# 고정 거절 문구 — answer_checks._is_rejection() 매칭 필수(T2에서 0콜 검증). URL·전화번호 금지.
REJECT_TEXT = "죄송합니다. 해당 내용은 예금보험공사 소관이 아니거나 안내 문서에서 확인되지 않는 내용입니다."

_searcher = None


def get_searcher():
    global _searcher
    if _searcher is None:
        from rag import Searcher
        _searcher = Searcher(index_dir=str(ROOT / "crawler" / "data" / "index"))
    return _searcher


def _hcx(messages: list[dict], req_id: str, params: dict = GEN_PARAMS) -> tuple[str | None, dict]:
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
            r = requests.post(API_URL, json={"messages": messages, **params}, timeout=30, headers={
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


def _parse_cls(text: str | None) -> dict | None:
    """분류 응답에서 JSON 1개 추출. 라벨 3값 검증 실패 시 None."""
    if not text:
        return None
    m = re.search(r"\{.*?\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    if d.get("label") in ("정상", "모호", "소관밖"):
        return {"label": d["label"], "reason": str(d.get("reason", ""))[:200]}
    return None


def classify(query: str) -> tuple[str, str, dict]:
    """LLM 질문 분류 (기본 1콜). JSON 파싱 실패 시 1회 재시도, 재실패는 안전 기본값 '정상'.

    반환: (label, reason, meta) — meta에 콜 수·파싱 실패 횟수·지연 기록.
    """
    global _calls
    messages = [{"role": "system", "content": CLS_PROMPT}, {"role": "user", "content": query}]
    meta = {"cls_calls": 0, "cls_parse_fail": 0, "cls_latency_ms": 0, "cls_error": None}
    for _ in (1, 2):  # 파싱 실패 재시도 1회(HTTP 재시도는 _hcx 내부에서 별도)
        c0 = _calls
        text, m = _hcx(messages, req_id="cls", params=CLS_PARAMS)
        meta["cls_calls"] += _calls - c0
        meta["cls_latency_ms"] += m["latency_ms"] or 0
        meta["cls_error"] = m["error"]
        parsed = _parse_cls(text)
        if parsed:
            return parsed["label"], parsed["reason"], meta
        if text is not None:
            meta["cls_parse_fail"] += 1
        if m["error"] == "call_budget_exhausted":
            break
    return "정상", "분류 실패 — 안전 기본값(과차단 방지)", meta


def _route(label: str) -> str:
    """분류 라벨 → 라우트 매핑 (07-22 확정: 소관밖→reject, 정상·모호→rag).

    "link"는 미구현 훅 유지 — 타기관 안내 URL 목록 확보 후 소관밖 세분화 예정.
    """
    return "reject" if label == "소관밖" else "rag"


def _reject_result(label: str, reason: str, cls_meta: dict, k: int) -> dict:
    """reject 경로 반환 조립 — 검색·생성·검증 생략. 계약 4필드 + checks/_meta 완비(T2 검증 대상)."""
    return {
        "text": REJECT_TEXT,
        "sources": [],
        "confidence": 0.0,
        "route": "reject",
        "checks": {"ok": True, "flags": [], "skipped": "고정 거절 문구"},  # 모델 생성물 아님 — 검증 비대상
        "attachments": [],  # 소관 밖 — 반환 첨부 없음(계약 부가 필드)
        "_meta": {"model": MODEL_NAME, "cls_label": label, "cls_reason": reason, **cls_meta,
                  "latency_ms": cls_meta.get("cls_latency_ms"), "k": k},
    }


def answer(query: str, k: int = 3) -> dict:
    """계약 4필드 + 부가(checks/_meta). 분류 선행 — 소관밖은 검색·생성 없이 즉시 거절."""
    label, reason, cls_meta = classify(query)
    route = _route(label)
    if route == "reject":
        return _reject_result(label, reason, cls_meta, k)

    hits = get_searcher().search(query, k=k, mode="hybrid_bf")
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
    # 근거 문서 첨부 조회 — 청크 태깅 우선, 없으면 문서 단위 폴백. 검색 hits만 사용(추가 콜 0).
    attach = attachments.collect(hits)
    return {
        "text": text,
        "sources": sources,
        "confidence": _confidence(query),
        "route": route,
        "checks": checks,           # 부가 필드(계약 외 추가 — 축소 아님)
        "attachments": attach,      # 부가 필드 — 근거 문서 첨부(다운로드용). 없으면 []
        "_meta": {"model": MODEL_NAME, "cls_label": label, "cls_reason": reason, **cls_meta, **meta, "k": k},
    }


def _confidence(query: str) -> float:
    """표시용 confidence — dense 코사인 top1 (T2 추천). 정책 분기에 쓰지 말 것(Q12)."""
    d1 = get_searcher().search(query, k=1, mode="dense")
    return round(float(d1[0]["_score"]), 4) if d1 else 0.0


def _print_calls() -> None:
    print(f"[calls] 이번 실행 HCX 콜(재시도 포함): {_calls} / 예산 {CALL_BUDGET}")


# ── 실행 모드 (T1 스모크 · T3 E2E · T4 정상 분류) ───────────────────────
def run_cls_one(query: str) -> None:
    label, reason, meta = classify(query)
    print(f"[cls] {query}\n  → {label} ({reason})  콜 {meta['cls_calls']} · 파싱실패 {meta['cls_parse_fail']} · {meta['cls_latency_ms']}ms")


def run_smoke() -> None:
    """T1 분류 스모크 — 트랩셋·데모셋 밖 신규 3문항(기대: 정상/소관밖/모호)."""
    for expect, q in [("정상", "예금자보호제도란 무엇인가요?"),
                      ("소관밖", "자동차 보험료 할인은 어디에 문의해야 하나요?"),
                      ("모호", "예금 이자에 붙는 세금은 얼마인가요?")]:
        label, reason, meta = classify(q)
        mark = "일치" if label == expect else f"불일치(기대 {expect})"
        print(f"[smoke] {q}\n  → {label} [{mark}] ({reason})  콜 {meta['cls_calls']} · 파싱실패 {meta['cls_parse_fail']}")
    _print_calls()


def run_e2e() -> None:
    """T3 — 트랩셋 20문항 전부 answer() E2E → exp/route_e2e_results.jsonl."""
    traps = [json.loads(l) for l in (ROOT / "exp" / "trapset_v0.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    out_path = ROOT / "exp" / "route_e2e_results.jsonl"
    global _calls
    rows = []
    for i, t in enumerate(traps, 1):
        c0 = _calls
        t0 = time.time()
        r = answer(t["query"])
        m = r["_meta"]
        rows.append({
            "id": i, "query": t["query"], "expected_route": t["expected_route"],
            "cls_label": m.get("cls_label"), "cls_reason": m.get("cls_reason"),
            "route": r["route"], "text": r["text"],
            "checks_flags": r["checks"]["flags"],
            "hcx_calls_this_q": _calls - c0,
            "latency_ms": int((time.time() - t0) * 1000),
            # 부가(분석용)
            "trap_type": t["trap_type"], "cls_parse_fail": m.get("cls_parse_fail", 0),
            "confidence": r["confidence"],
        })
        print(f"  [{i:2d}/20] {t['trap_type']:7} 기대={t['expected_route']:7} → cls={m.get('cls_label')} route={r['route']}"
              f" 콜+{_calls - c0} (누계 {_calls})")
        time.sleep(0.5)
    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    n_rej = sum(1 for r in rows if r["route"] == "reject")
    print(f"[e2e] {len(rows)}행 → {out_path.name} · reject {n_rej} / rag {len(rows) - n_rej}")
    _print_calls()


def run_clsdemo() -> None:
    """T4 — 전야 데모 정상 6문항(demo_results.jsonl rag 행, 읽기만) 분류만 실행."""
    demo = [json.loads(l) for l in (ROOT / "chatbot" / "demo_results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    queries = [r["query"] for r in demo if r["mode"] == "rag"]
    fp = 0
    for q in queries:
        label, reason, meta = classify(q)
        if label == "소관밖":
            fp += 1
        print(f"[정상문항] {q}\n  → {label} ({reason})")
    print(f"[clsdemo] 정상 6문항 중 소관밖 오분류(false positive): {fp}건")
    _print_calls()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if cmd == "cls":
        run_cls_one(sys.argv[2] if len(sys.argv) > 2 else "예금자 보호 한도는 얼마인가요?")
        _print_calls()
    elif cmd == "smoke":
        run_smoke()
    elif cmd == "e2e":
        run_e2e()
    elif cmd == "clsdemo":
        run_clsdemo()
    elif cmd == "demo":
        for lab, q in [("정상", "예금보험금은 어떻게 신청하나요?"),
                       ("트랩(해외)", "미국 FDIC의 예금 보호한도는 얼마인가요?"),
                       ("롤렛(보호한도)", "예금자 보호 한도는 얼마인가요?")]:
            r = answer(q)
            print(f"══ [{lab}] {q}")
            print(f"   route={r['route']} (cls={r['_meta'].get('cls_label')}) · confidence={r['confidence']}"
                  f" · checks={'통과' if r['checks']['ok'] else r['checks']['flags']}")
            print(f"   답변: {r['text']}\n")
        _print_calls()
    else:
        sys.exit("사용법: python3 chatbot/chain.py [demo|cls \"질문\"|smoke|e2e|clsdemo]")
