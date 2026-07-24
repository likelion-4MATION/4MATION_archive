"""answer_checks.py — 생성 품질 자동 검증기 골격 (rule-based 3종, HCX 0콜).

멘토링 반영: faithfulness 검증은 answer() 뒤 validation 층위(Q5) · 추가 기능 1순위(Q11).
전부 규칙 기반 — LLM-judge는 설계 메모만(파일 말미 주석). 판정은 "플래그"이며 차단이 아니다.

3종 체크 (밤1 task_assignment T4):
  1) check_urls      — 답변 내 URL ⊆ sources의 source_url (날조 검출; 컨텍스트 본문 URL 허용 옵션)
  2) check_citations — [출처N] 존재·범위(1..k) + 답변 핵심 수치가 인용 청크에 실존하는지 간이 대조
  3) check_numbers   — 답변 내 전화번호·금액이 컨텍스트 어딘가에 실존하는지

소급 실행(전야 데모 rag 6행 판정표):
  python3 chatbot/answer_checks.py
"""
import re

# ── 추출 유틸 ──────────────────────────────────────────────
_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+|(?:[a-z0-9\-]+\.)+(?:or|go|co)\.kr[^\s\)\]\"'<>]*", re.I)
_PHONE_RE = re.compile(r"(?<!\d)\d{2,4}-\d{3,4}(?:-\d{4})?(?!\d)")
# 금액·비율 토큰 — 정규화 텍스트(쉼표·공백 제거, N천만→N000만) 위에서 추출.
# '숫자+단위' 세그먼트 연쇄(1억5000만원 · 325백만원 · 20억)와 단순 원 표기, 비율을 포괄.
_AMOUNT_RE = re.compile(r"(?:\d+(?:\.\d+)?(?:조|억|백만|천만|만))+원?|\d+(?:\.\d+)?원|\d+(?:\.\d+)?%")


def _norm(text: str) -> str:
    """수치 대조용 정규화 — 쉼표·공백 제거, 'N천만'→'N000만' (5,000만 원 ≡ 5천만원)."""
    s = text.replace(",", "").replace(" ", "").replace(" ", "")
    s = re.sub(r"(\d)천만", r"\g<1>000만", s)
    s = re.sub(r"(\d)천(\d{3})", r"\g<1>\g<2>", s)  # 1천500 → 1500
    return s


def _norm_url(u: str) -> str:
    u = u.strip().rstrip(".,;)]\"'")
    u = re.sub(r"^https?://", "", u, flags=re.I)
    u = re.sub(r"^www\.", "", u, flags=re.I)
    return u.rstrip("/").lower()


def _urls(text: str) -> set[str]:
    return {_norm_url(m.group(0)) for m in _URL_RE.finditer(text)}


def _amounts(text: str) -> set[str]:
    """정규화 텍스트에서 금액·비율 토큰. 연도·전화번호 등 단위 없는 수는 제외."""
    return {m.group(0) for m in _AMOUNT_RE.finditer(_norm(text))
            if re.search(r"[조억만원%]", m.group(0))}


_UNIT = {"조": 10**12, "억": 10**8, "백만": 10**6, "천만": 10**7, "만": 10**4}
_SEG_RE = re.compile(r"(\d+(?:\.\d+)?)(조|억|백만|천만|만)?")


def _parse_won(token: str) -> int | None:
    """금액 토큰 → 원 단위 정수. 표기 단위가 달라도 등가 비교 가능하게 한다.
    예: '1125백만원' == '11억2500만원' == 1,125,000,000. 비율(%)·해석 불가는 None."""
    if token.endswith("%") or not re.search(r"[조억만원]", token):
        return None
    total, pos, matched = 0.0, 0, False
    for m in _SEG_RE.finditer(token.rstrip("원")):
        if m.start() != pos:
            return None  # 숫자·단위 외 문자 개입 — 해석 포기
        total += float(m.group(1)) * _UNIT.get(m.group(2) or "", 1)
        pos, matched = m.end(), True
    return int(total) if matched and pos == len(token.rstrip("원")) else None


def _amount_in(token: str, ctx_norm: str, ctx_values: set[int]) -> bool:
    """표기 일치 or 환산 등가 일치 (백만원 단위 원문 ↔ 억·만원 표기 답변 대응)."""
    if token in ctx_norm:
        return True
    v = _parse_won(token)
    return v is not None and v in ctx_values


_REJECTION_RE = re.compile(r"확인되지\s*않는|안내(?:된|되어\s*있는)?\s*내용이\s*아니|답변드리기\s*어렵|소관이?\s*아니")


def _is_rejection(answer: str) -> bool:
    """답변이 '거절/확인불가' 유형인지 패턴으로 감지.

    거절 답변은 인용할 근거 자체가 없는 게 정상이라 [출처N] 미표기가
    검증 실패가 아니다. 이 패턴에 해당하면 check_citations의
    '출처 번호 미표기' 판정을 건너뛴다(다른 위반은 그대로 검사).
    """
    return bool(_REJECTION_RE.search(answer))


# ── 체크 3종 ───────────────────────────────────────────────
def check_urls(answer: str, sources: list[dict], context_text: str | None = None) -> dict:
    """답변 내 URL ⊆ sources의 source_url 집합. context_text 지정 시 본문 유래 URL도 허용.

    한계: 정규화(스킴·www·말미 / 제거) 후 전체 URL 문자열 비교 — 경로 변형·리다이렉트는 오탐 가능.
    """
    allowed = {_norm_url(s["source_url"]) for s in sources if s.get("source_url")}
    if context_text:
        allowed |= _urls(context_text)
    bad = sorted(u for u in _urls(answer) if u not in allowed)
    return {"name": "check_urls", "ok": not bad,
            "violations": [f"출처 밖 URL: {u}" for u in bad]}


def check_citations(answer: str, hits: list[dict]) -> dict:
    """[출처N] 표기 존재 + 범위 1..len(hits) + 답변 금액 토큰이 인용 청크 안에 실존하는지 간이 대조.

    한계: 수치 대조는 표기 변형(한글 숫자 등)에 취약 — 부재 판정은 '의심 플래그'로 해석할 것.
    """
    cites = [int(n) for n in re.findall(r"\[출처(\d+)\]", answer)]
    v = []
    if not cites and not _is_rejection(answer):
        v.append("출처 번호 미표기")
    bad_range = [n for n in cites if not 1 <= n <= len(hits)]
    if bad_range:
        v.append(f"범위 밖 인용: {bad_range} (유효 1..{len(hits)})")
    valid = [n for n in cites if 1 <= n <= len(hits)]
    if valid:
        cited_text = "\n".join(hits[n - 1]["text"] for n in set(valid))
        cited_norm = _norm(cited_text)
        cited_vals = {v_ for a in _amounts(cited_text) if (v_ := _parse_won(a)) is not None}
        missing = sorted(a for a in _amounts(answer) if not _amount_in(a, cited_norm, cited_vals))
        if missing:
            v.append(f"인용 청크에 수치 부재: {missing}")
    return {"name": "check_citations", "ok": not v, "violations": v}


def check_numbers(answer: str, context_text: str) -> dict:
    """답변 내 전화번호·금액이 컨텍스트(top-k 본문 전체)에 실존하는지 — 표기·환산 등가 모두 인정."""
    ctx_norm = _norm(context_text)
    ctx_vals = {v_ for a in _amounts(context_text) if (v_ := _parse_won(a)) is not None}
    ctx_phones = set(_PHONE_RE.findall(context_text))
    v = [f"컨텍스트에 없는 전화번호: {p}" for p in sorted(set(_PHONE_RE.findall(answer)) - ctx_phones)]
    v += [f"컨텍스트에 없는 금액·비율: {a}" for a in sorted(_amounts(answer))
          if not _amount_in(a, ctx_norm, ctx_vals)]
    return {"name": "check_numbers", "ok": not v, "violations": v}


def run_all(answer: str, hits: list[dict], sources: list[dict] | None = None,
            allow_context_urls: bool = False) -> dict:
    """3종 일괄 실행 → 플래그 목록. 차단하지 않는다(호출부가 표시·로깅에만 사용)."""
    if sources is None:
        sources = [{"title": h.get("page_title"), "url": h.get("source_url"),
                    "source_url": h.get("source_url")} for h in hits]
    context = "\n\n".join(h["text"] for h in hits)
    results = [
        check_urls(answer, sources, context_text=context if allow_context_urls else None),
        check_citations(answer, hits),
        check_numbers(answer, context),
    ]
    flags = [f"{r['name']}: {msg}" for r in results for msg in r["violations"]]
    return {"ok": not flags, "flags": flags, "results": {r["name"]: r for r in results}}


# ── 소급 실행: 전야 demo_results.jsonl rag 6행 판정표 ──────
def _retro_main() -> None:
    import json
    import os
    import pathlib
    import sys

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    root = pathlib.Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "crawler"))
    from rag import Searcher

    s = Searcher(index_dir=str(root / "crawler" / "data" / "index"))
    demo = [json.loads(l) for l in
            (root / "chatbot" / "demo_results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rag_rows = [r for r in demo if r["mode"] == "rag"]
    print(f"[retro] 전야 rag {len(rag_rows)}행 — 컨텍스트는 동일 쿼리 재검색으로 복원(인덱스 결정성 전제)\n")
    for i, row in enumerate(rag_rows, 1):
        hits = s.search(row["query"], k=3, mode="hybrid")
        same = [h["parent_doc_id"] for h in hits] == [t["parent_doc_id"] for t in row["top3"]]
        strict = run_all(row["answer"], hits, allow_context_urls=False)
        loose = run_all(row["answer"], hits, allow_context_urls=True)
        print(f"Q{i}. {row['query']}  (top3 복원 일치: {'예' if same else '아니오 — 판정 신뢰 주의'})")
        if strict["ok"]:
            print("   플래그 없음")
        for f in strict["flags"]:
            extra = "" if f in loose["flags"] else "  ← 본문 URL 허용 시 해소"
            print(f"   ⚑ {f}{extra}")
        print()


# ── LLM-judge 설계 메모 (콜 0 — 구현 아님) ─────────────────
# · 층위: rule-based 3종 통과분에만 2차로 적용(비용 절감). 입력: 질문 · top-k 본문 · 답변.
# · 판정 3축: ① 근거성(답변 문장별 출처 청크 지목 가능?) ② 완결성(질문 핵심에 답했나)
#   ③ 한정 보존(원문의 과거형·조건이 답변에서 현재 사실화되지 않았나 — 전야 롤렛 A 사례).
# · 출력: {faithful: bool, 위반 문장 목록, 사유 한 줄} — 정책(차단)이 아니라 플래그.
# · 모델: HCX 자체 재사용 시 자기평가 편향 유의 — 프롬프트에 "답변 작성자가 아니라 감사자" 역할 고정.
# · 예산: 문항당 1콜 — 배치 평가는 트랩셋 검수 확정 후.

if __name__ == "__main__":
    _retro_main()
