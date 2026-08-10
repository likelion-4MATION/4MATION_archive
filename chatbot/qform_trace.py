# -*- coding: utf-8 -*-
"""큐폼 트레이스 수집기 — 업무 신호 층 (T1).

한 질의가 **어느 층에서 어떤 근거로 갈렸는지**를 화면에 보이게 하기 위한 재계산 모듈.

설계 원칙 (CLAUDE.md §0-2 · §2-1 / task_assignment E2·E4):
- **`rag.py` 는 한 줄도 고치지 않는다.** 계측 코드를 파이프라인에 심는 대신, `rag` 의
  **상수를 import 해서 판정을 재계산**한다. 트레이스를 꺼도 파이프라인 동작이 v1과 동일해야 한다.
- 재계산은 `rag.classify_query_bf()` 와 **판정이 갈리면 안 된다.** 갈리는 순간 트레이스가
  거짓말을 한다 → 450셋 전건 정합을 이 파일의 하니스가 검증한다(AC1).
- LLM 호출 0. 전부 결정론.

`bf_debug()` 반환:
    {"bf":       판정 업무 또는 None,
     "scores":   {업무: 점수},
     "hits":     {업무: [(키워드, 가중치, 등장횟수)]},   # 점수 기여분 = 가중치 × 등장횟수
     "margin":   1위 - 2위 점수,
     "verdict":  "확정" | "마진미달" | "점수미달",
     "reason":   판정 사유 한 줄 (패널 노출용)}

주의: `rag.classify_query_bf` 는 키워드 **등장 횟수**를 곱해 점수를 낸다
(`w * q.count(k)`). 그래서 `hits` 는 (키워드, 가중치)가 아니라 **등장횟수까지** 담는다 —
반복 등장 질의에서 점수 합이 재구성되지 않으면 패널이 근거를 틀리게 설명한다.
"""
from __future__ import annotations

import pathlib
import sys

_BASE = pathlib.Path(__file__).resolve().parent.parent
for _p in (_BASE / "chatbot", _BASE / "crawler"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# rag 는 **읽기만** 한다 (상수 import). 함수 교체·전역 심기 금지 — CLAUDE.md §2-1.
#
# rag.py 최상단이 faiss/numpy 를 import 하지만, 분류 상수와 classify_query_bf 는 둘을
# 전혀 쓰지 않는다(순수 문자열 연산 — replace/count/sorted). 검색 스택이 깔리지 않은
# 환경에서도 정합 검증(AC1)이 돌아야 하므로, **실제로 없는 패키지만** 빈 스텁으로 얹어
# 상수 로딩을 통과시킨다. 판정 셈법에 개입할 여지가 없고 rag.py 는 무수정이다.
RAG_STUBBED: tuple[str, ...] = ()


def _load_rag():
    global RAG_STUBBED
    try:
        import rag as _r
    except ModuleNotFoundError:
        import importlib.util
        import types
        absent = [n for n in ("faiss", "numpy") if importlib.util.find_spec(n) is None]
        if not absent:
            raise                       # 다른 이유의 실패는 숨기지 않는다
        for n in absent:
            sys.modules[n] = types.ModuleType(n)
        RAG_STUBBED = tuple(absent)
        import rag as _r
    return _r


rag = _load_rag()
BF_QUERY_KEYWORDS = rag.BF_QUERY_KEYWORDS
QBF_MIN_SCORE = rag.QBF_MIN_SCORE
QBF_MARGIN = rag.QBF_MARGIN

__all__ = ["bf_debug", "BF_QUERY_KEYWORDS", "QBF_MIN_SCORE", "QBF_MARGIN", "RAG_STUBBED"]


def bf_debug(query: str) -> dict:
    """`rag.classify_query_bf()` 판정을 **점수 내역과 함께** 재계산한다 (rag.py 무수정).

    셈법은 원본과 동일해야 한다:
        q = query.replace(" ", "");  score(bf) = Σ w × q.count(kw 공백제거)
        1위 점수 < QBF_MIN_SCORE      → None (점수미달)
        1위 - 2위 < QBF_MARGIN        → None (마진미달)
        그 외                          → 1위 업무
    """
    q = (query or "").replace(" ", "")

    scores: dict[str, int] = {}
    hits: dict[str, list[tuple[str, int, int]]] = {}
    for bf, kws in BF_QUERY_KEYWORDS.items():
        total, hit = 0, []
        for kw, w in kws:
            n = q.count(kw.replace(" ", ""))
            if n:
                hit.append((kw, w, n))
                total += w * n
        scores[bf] = total
        if hit:
            hits[bf] = sorted(hit, key=lambda h: -(h[1] * h[2]))

    # 정렬은 원본과 동일하게 (동점은 BF_QUERY_KEYWORDS 삽입순 유지 — sorted 는 안정 정렬)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top, top_sc = ranked[0]
    second, sec_sc = ranked[1] if len(ranked) > 1 else (None, 0)
    margin = top_sc - sec_sc

    if top_sc < QBF_MIN_SCORE:
        verdict = "점수미달"
        reason = f"최고 {top} {top_sc}점 < 최소 {QBF_MIN_SCORE}점 → 업무 불명"
    elif len(ranked) > 1 and margin < QBF_MARGIN:
        verdict = "마진미달"
        reason = (f"1위 {top} {top_sc}점 · 2위 {second} {sec_sc}점 · "
                  f"마진 {margin} < {QBF_MARGIN} → 업무 불명")
    else:
        verdict = "확정"
        reason = (f"{top} {top_sc}점 (최소 {QBF_MIN_SCORE} 충족) · "
                  f"2위 {second} {sec_sc}점 · 마진 {margin} ≥ {QBF_MARGIN} → 확정")

    return {"bf": top if verdict == "확정" else None,
            "scores": scores, "hits": hits,
            "margin": margin, "verdict": verdict, "reason": reason}


# ══════════════════════════════════════════════════════════════════════════
# T5 — 층별 트레이스 수집
# ══════════════════════════════════════════════════════════════════════════
# 층 순서는 **T6 패널 카드 · T7 §1 다이어그램과 1:1 대응**한다. 여기서 바꾸면 셋 다 바꾼다.
LAYER_ORDER = ("gate", "bf", "slots", "combos", "ask",
               "search", "generate", "attachments", "checks")
LAYER_LABEL = {"gate": "소관 게이트", "bf": "업무 신호", "slots": "슬롯 추출",
               "combos": "조합 생존", "ask": "되묻기", "search": "검색",
               "generate": "생성", "attachments": "첨부", "checks": "검증"}
# 결정론 구간(LLM 콜 0) — 패널의 "콜 0" 배지 대상
DETERMINISTIC = ("bf", "slots", "combos", "search", "attachments", "checks")

SKIP_PENDING = "생략 (되묻기 턴 — 미실행)"
SKIP_REJECT = "생략 (소관 밖)"

# 슬롯 출처 표기 (ver3 T2) — 값의 주인은 `qform_flow`, 여기서는 표기만 맞춘다.
ORIGIN_NEW, ORIGIN_CARRY, ORIGIN_EMPTY = "신규", "이월", "미채움"


def bf_debug_of(query: str) -> dict:
    """`bf_debug` 의 별칭 — `collect()` 안에서 동명 파라미터에 가려지는 것을 피한다."""
    return bf_debug(query)


def _default_search(query: str, k: int = 3):
    """검색 hits 조달 — `answer()` 가 hits 를 돌려주지 않아 **결정론 재호출**로 얻는다.

    같은 쿼리·같은 k·같은 mode 라 `answer()` 내부 결과와 동일하다. LLM 콜 0
    (`rag.py` 무수정 원칙에서 허용하는 순수 함수 재호출 — CLAUDE.md §2-1).
    """
    import chain
    return chain.get_searcher().search(query, k=k, mode="hybrid_bf")


def _forms(atts: list) -> set:
    """확장자를 접은 canonical 서식 집합 (hwp/pdf 중복 접기 — verify_qform_integration 동일)."""
    return {pathlib.Path(a["orig_filename"]).stem for a in atts if a.get("orig_filename")}


def _no_ask_reason(slots: dict, surv: list, turn: int | None) -> str:
    """되묻지 **않은** 사유를 결정론으로 되짚는다 — 패널에서 '왜 안 물었나'가 보여야 한다."""
    import qform_state
    if not slots.get("sub_task"):
        return "sub_task 미상 → 되묻지 않음 (D2 · 단문 오발동 방지)"
    if len(surv) <= 1:
        return f"생존 {len(surv)}행 — 더 좁힐 것이 없음"
    if turn is not None and turn >= 2:
        return "되묻기 상한 2턴 도달 → 미채움이어도 진행"
    if qform_state.next_question(slots) is None:
        return "되물을 수 있는 슬롯 없음 (조건부 게이트 미통과)"
    return "탈출구 — 사용자가 건너뜀"


def collect(query: str, bf_debug: dict, slots: dict, surv: list | None,
            ask: dict | None, result: dict | None, boost_on: bool, *,
            search_q: str | None = None, hits: list | None = None,
            search_fn=None, hcx_calls: int | None = None,
            ask_turn: int | None = None, slot_origin: dict | None = None) -> dict:
    """질의 1건의 층별 트레이스를 조립한다. **LLM 콜 0.**

    파이프라인에 계측을 심지 않는다(E2). 값은 셋 중 하나로만 얻는다 —
    ① `answer()` 반환에서 읽기 ② `extract()` 반환에서 읽기 ③ 결정론 함수 재호출.

    result=None  되묻기 턴 (아직 `answer()` 를 부르지 않았다) → 검색 이후 층은 "생략"
    route=reject 소관 밖 → 검색·생성·첨부 층은 "생략"

    slot_origin  {슬롯: 신규|이월|미채움} (ver3 T2). 생략하면 `slots["_origin"]` 에서
        읽고, 그것도 없으면 값 유무로 신규/미채움만 되짚는다 — ver2 호출부가 인자를
        안 넘겨도 깨지지 않아야 하기 때문이다.
    """
    import attachments as _att
    import qform_state

    meta = (result or {}).get("_meta") or {}
    route = (result or {}).get("route")
    pending = result is None
    rejected = route == "reject"
    search_q = search_q or query
    raw = slots or {}
    clean = {f: raw.get(f) for f in qform_state.SLOT_FIELDS}
    surv = qform_state.survivors(clean) if surv is None else surv

    L: dict[str, dict] = {}

    # ── 소관 게이트 — `_meta` 읽기 ──────────────────────────────────────────
    L["gate"] = {
        "status": SKIP_PENDING if pending else "수집",
        "label": meta.get("cls_label"), "reason": meta.get("cls_reason"),
        "route": route, "parse_fail": meta.get("cls_parse_fail") or 0,
        "latency_ms": meta.get("cls_latency_ms"),
        "calls": meta.get("cls_calls") or 0,
    }

    # ── 업무 신호 — rag 상수로 재계산 (T1) ─────────────────────────────────
    L["bf"] = {"status": "수집", "calls": 0, **(bf_debug or bf_debug_of(query))}

    # ── 슬롯 추출 — `extract()` 반환 읽기 ──────────────────────────────────
    # 출처(신규/이월/미채움)는 ver3 T2. 이월이 왜 됐는지/안 됐는지가 안 보이면
    # "첨부가 왜 좁아졌나"를 시연에서 설명할 수 없다.
    origin = slot_origin or raw.get("_origin") or {
        f: ORIGIN_NEW if clean.get(f) else ORIGIN_EMPTY for f in qform_state.SLOT_FIELDS}
    origin = {f: origin.get(f, ORIGIN_EMPTY) for f in qform_state.SLOT_FIELDS}
    L["slots"] = {
        "status": "수집", "calls": 0, "slots": clean,
        "triggers": raw.get("_hits") or {}, "scope": raw.get("_scope"),
        "bf_used": raw.get("_bf"), "filled": sum(1 for v in clean.values() if v),
        "origin": origin,
        "carried": sum(1 for v in origin.values() if v == ORIGIN_CARRY),
        "carryover": raw.get("_carryover"),
    }

    # ── 조합 생존 — `survivors()` 재호출로 추이 재구성 ──────────────────────
    trail, acc = [("전체", len(qform_state._COMBOS))], {}
    for f in qform_state.SLOT_FIELDS:
        if clean.get(f):
            acc[f] = clean[f]
            trail.append((f"{f}={clean[f]}", len(qform_state.survivors(acc))))
    L["combos"] = {
        "status": "수집", "calls": 0, "total": len(qform_state._COMBOS),
        "trail": trail, "remaining": len(surv),
        "combo_ids": [c["combo_id"] for c in surv],
    }

    # ── 되묻기 — T3·T4 반환 읽기 ───────────────────────────────────────────
    if ask:
        L["ask"] = {
            "status": "수집", "fired": True, "slot": ask.get("slot"),
            "turn": ask_turn, "remaining": ask.get("remaining"),
            "reason": f"생존 {ask.get('remaining')}행 · {ask.get('slot')} 미상 → 되물음",
            "mode": ask.get("mode"), "calls": ask.get("calls") or 0,
            "fallback_reason": ask.get("fallback_reason"),
            "values": ask.get("values"), "prompt": ask.get("text"),
        }
    else:
        L["ask"] = {
            "status": "수집", "fired": False, "slot": None, "turn": ask_turn,
            "remaining": len(surv), "reason": _no_ask_reason(clean, surv, ask_turn),
            "mode": None, "calls": 0, "fallback_reason": None,
            "values": [], "prompt": None,
        }

    # ── 검색 — 결정론 재호출 (LLM 콜 0) ───────────────────────────────────
    if pending or rejected:
        L["search"] = {"status": SKIP_PENDING if pending else SKIP_REJECT, "calls": 0,
                       "docs": [], "k": meta.get("k"), "boost_applied": bool(boost_on),
                       "search_q": search_q, "search_bf": None, "bf_drift": False}
        hits = hits or []
    else:
        if hits is None:
            hits = (search_fn or _default_search)(search_q, meta.get("k") or 3)
        # 부스트 ON 이면 검색측은 **바뀐 쿼리**로 업무를 다시 분류한다(rag.search 내부).
        # app 이 쓴 bf 와 갈릴 수 있어 두 값을 나란히 남긴다 — 패널이 거짓말하지 않도록.
        s_bf = bf_debug_of(search_q)["bf"]
        L["search"] = {
            "status": "수집", "calls": 0, "k": meta.get("k") or 3,
            "boost_applied": bool(boost_on), "search_q": search_q,
            "search_bf": s_bf, "bf_drift": s_bf != (bf_debug or {}).get("bf"),
            "docs": [{"title": h.get("page_title"), "doc_id": h.get("parent_doc_id"),
                      "score": h.get("_score"), "business_function": h.get("business_function"),
                      "sub_category": h.get("sub_category")} for h in hits],
        }

    # ── 생성 — `_meta` 읽기 + app 층 콜 회계 ───────────────────────────────
    gate_c, ask_c = L["gate"]["calls"], L["ask"]["calls"]
    gen_c = None if hcx_calls is None else max(0, hcx_calls - gate_c - ask_c)
    text = (result or {}).get("text")
    L["generate"] = {
        "status": SKIP_PENDING if pending else (SKIP_REJECT if rejected else "수집"),
        "calls": 0 if rejected else gen_c, "latency_ms": meta.get("latency_ms"),
        "hcx_status": meta.get("hcx_status"), "error": meta.get("error"),
        "chars": len(text) if isinstance(text, str) else None,
    }

    # ── 첨부 — `collect(hits, qform=None)` 재호출로 필터 전/후 대비 ─────────
    if pending or rejected:
        L["attachments"] = {"status": SKIP_PENDING if pending else SKIP_REJECT, "calls": 0,
                            "before_forms": None, "before_files": None,
                            "after_forms": None, "after_files": None, "final": []}
    else:
        before = _att.collect(hits, qform=None)
        after = result.get("attachments") or []
        L["attachments"] = {
            "status": "수집", "calls": 0,
            "before_forms": len(_forms(before)), "before_files": len(before),
            "after_forms": len(_forms(after)), "after_files": len(after),
            "final": [{"doc_title": a.get("doc_title"), "label": a.get("label"),
                       "file": a.get("orig_filename")} for a in after],
        }

    # ── 검증 — `checks` 읽기 ───────────────────────────────────────────────
    checks = (result or {}).get("checks") or {}
    L["checks"] = {
        "status": SKIP_PENDING if pending else "수집", "calls": 0,
        "ok": checks.get("ok"), "flags": checks.get("flags") or [],
        "skipped": checks.get("skipped"),
    }

    return {
        "query": query, "search_q": search_q, "boost_on": bool(boost_on),
        "pending": pending, "rejected": rejected,
        "calls": {"total": hcx_calls, "gate": gate_c, "ask": ask_c, "generate": gen_c,
                  "deterministic": list(DETERMINISTIC)},
        "layers": {k: L[k] for k in LAYER_ORDER},
    }


# ══════════════════════════════════════════════════════════════════════════
# 검증 하니스 (python3 chatbot/qform_trace.py) — T1·T5 AC 실측 출력
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import hashlib
    import json

    import qform_state
    from qform_extract import extract

    classify_query_bf = rag.classify_query_bf

    TESTSET = _BASE / "crawler" / "data" / "testset_natural_450.jsonl"
    rows = [json.loads(l) for l in TESTSET.open(encoding="utf-8")]
    SLOT_FIELDS = qform_state.SLOT_FIELDS
    fails: list[tuple[str, str, str]] = []   # (AC, 기대, 실측)

    def _clean(s: dict) -> dict:
        return {f: s.get(f) for f in SLOT_FIELDS}

    print(f"업무 신호 층 검증 · 450셋 {len(rows)}건 로드 "
          f"(QBF_MIN_SCORE={QBF_MIN_SCORE} · QBF_MARGIN={QBF_MARGIN} · "
          f"업무 {len(BF_QUERY_KEYWORDS)}종)")
    if RAG_STUBBED:
        print(f"  ⚠ 이 환경에 {', '.join(RAG_STUBBED)} 미설치 → 빈 스텁으로 rag 상수만 로드했다.")
        print("    classify_query_bf 는 순수 문자열 연산이라 판정에 영향 없음(검색 스택은 미가동).")
    print()

    # ── AC1. 450셋 전건 재계산 == rag.classify_query_bf ─────────────────────
    # 재계산이 원본과 갈리면 트레이스가 거짓말을 한다. 이 태스크의 핵심 AC.
    print("── AC1. 재계산 판정 정합 (vs rag.classify_query_bf) ──")
    from collections import Counter
    mis = []
    verdicts = Counter()
    for r in rows:
        q = r["question"]
        d = bf_debug(q)
        verdicts[d["verdict"]] += 1
        if d["bf"] != classify_query_bf(q):
            mis.append((q, d["bf"], classify_query_bf(q)))
    print(f"  450셋 질의: 불일치 {len(mis)}건 (기대 0)")
    for q, got, want in mis[:5]:
        print(f"    ✗ {q[:40]:40} 재계산={got} · 원본={want}")

    # 부스트 ON 쿼리(= base + serialize)도 같은 분류기를 탄다 → 정합 표본 확장
    boosted = []
    for r in rows:
        q = r["question"]
        slots = extract(q, business_function=classify_query_bf(q))
        extra = qform_state.serialize(_clean(slots))
        if extra:
            boosted.append(f"{q} {extra}")
    mis_b = [b for b in boosted if bf_debug(b)["bf"] != classify_query_bf(b)]
    print(f"  부스트 변형 {len(boosted)}건: 불일치 {len(mis_b)}건 (기대 0)")
    ac1 = not mis and not mis_b
    print(f"  판정 분포(450): " + " · ".join(f"{k} {v}건" for k, v in verdicts.most_common()))
    print(f"  → AC1 {'OK' if ac1 else 'DIFF ⛔'}")
    if not ac1:
        fails.append(("AC1", "불일치 0", f"450셋 {len(mis)}건 · 부스트변형 {len(mis_b)}건"))

    # ── AC1-b. 센티널 리팩터 회귀 — 주입/미주입 결과 동일 ────────────────────
    # `business_function=None` 명시(= 계산했고 불명)와 인자 생략(= 폴백 계산)이
    # 같은 슬롯을 내야 한다. 다르면 app 배선을 바꾼 순간 추출 결과가 변한다.
    print("\n── AC1-b. 인자 생략 vs bf 주입 — extract() 결과 동일 ──")
    diff_slots = []
    for r in rows:
        q = r["question"]
        a = _clean(extract(q))
        b = _clean(extract(q, business_function=classify_query_bf(q)))
        if a != b:
            diff_slots.append((q, a, b))
    ac1b = not diff_slots
    print(f"  450셋 슬롯 불일치: {len(diff_slots)}건 (기대 0)  → {'OK' if ac1b else 'DIFF ⛔'}")
    for q, a, b in diff_slots[:5]:
        print(f"    ✗ {q[:36]:36} 생략={a} · 주입={b}")
    if not ac1b:
        fails.append(("AC1-b", "슬롯 불일치 0", f"{len(diff_slots)}건"))

    # ── AC2. rag.py 무변경 ──────────────────────────────────────────────────
    # git 실행 금지(CLAUDE.md §0-1)라 여기서는 해시만 남긴다. diff 확인은 사람이 한다.
    print("\n── AC2. rag.py 무변경 ──")
    ragsrc = (_BASE / "crawler" / "rag.py").read_bytes()
    print(f"  crawler/rag.py sha256 {hashlib.sha256(ragsrc).hexdigest()[:16]} · {len(ragsrc)}bytes")
    print("  이 파일은 rag 상수를 **읽기만** 한다 (BF_QUERY_KEYWORDS · QBF_MIN_SCORE · QBF_MARGIN)")
    print("  → 사람 확인: `git diff crawler/rag.py` 가 비어 있을 것 (git 실행은 CLAUDE.md §0-1로 금지)")

    # ── AC3. extract() 경로 classify_query_bf 호출 횟수 ─────────────────────
    # rag 모듈 속성을 하니스 안에서만 감싼다(앱·파이프라인 미개입). 끝나면 원복.
    print("\n── AC3. extract() 경로 classify_query_bf 호출 횟수 (계측) ──")
    _orig = rag.classify_query_bf
    _n = [0]

    def _counted(qq):
        _n[0] += 1
        return _orig(qq)

    Q_BF = "착오송금 반환 신청 서류가 뭐예요?"          # bf 확정되는 질의
    Q_NONE = next((r["question"] for r in rows if classify_query_bf(r["question"]) is None), None)
    rag.classify_query_bf = _counted
    try:
        _n[0] = 0
        extract(Q_BF)
        c_old = _n[0]                                   # v1 경로: 폴백 1콜

        _n[0] = 0
        _bf = rag.classify_query_bf(Q_BF)
        extract(Q_BF, business_function=_bf)
        c_new = _n[0]                                   # 신경로: app 1콜 + extract 0콜

        _n[0] = 0
        _bf2 = rag.classify_query_bf(Q_BF)
        extract(Q_BF)                                   # 주입 누락(잘못된 배선)
        c_bad = _n[0]

        c_none = None
        if Q_NONE is not None:
            _n[0] = 0
            _bfn = rag.classify_query_bf(Q_NONE)        # → None
            extract(Q_NONE, business_function=_bfn)     # 센티널 구별 → 재계산 안 함
            c_none = _n[0]
    finally:
        rag.classify_query_bf = _orig                   # 원복 (전역 심기 금지)

    print(f"  v1 경로   extract(q)                       → {c_old}콜")
    print(f"  신경로    bf=classify(q); extract(q, bf=bf) → {c_new}콜  (기대 1)")
    print(f"  주입 누락 bf=classify(q); extract(q)        → {c_bad}콜  (가드가 무는지 확인, 기대 2)")
    if c_none is not None:
        print(f"  bf 불명   bf=None 주입 @ \"{Q_NONE[:24]}…\"   → {c_none}콜  (기대 1 · 센티널 없으면 2)")
    ac3 = (c_new == 1) and (c_bad == 2) and (c_none in (None, 1))
    print(f"  → AC3 {'OK' if ac3 else 'DIFF ⛔'}")
    if not ac3:
        fails.append(("AC3", "신경로 1콜 · 불명 주입 1콜", f"신경로 {c_new}콜 · 불명 {c_none}콜"))

    # ── AC4. 부스트 ON/OFF 에서 app 이 쓰는 bf 동일 ──────────────────────────
    # app 은 bf 를 **base_q 에서 1회** 계산해 extract 에 주입한다. 부스트는 검색 쿼리만
    # 바꾸므로 슬롯·트레이스가 보는 bf 는 토글과 무관해야 한다.
    print("\n── AC4. 부스트 ON/OFF — app 이 사용하는 bf 동일 ──")

    def app_path(query: str, boost: bool):
        """app.py 배선 재현: bf 1회 계산 → extract 주입 → (부스트면) 검색 쿼리만 확장."""
        bf = classify_query_bf(query)                   # ← MoAI 라우터가 꽂힐 자리
        slots = _clean(extract(query, business_function=bf))
        search_q = query
        if boost:
            extra = qform_state.serialize(slots)
            if extra:
                search_q = f"{query} {extra}"
            return bf, slots, search_q
        return bf, slots, search_q

    off = [app_path(r["question"], False) for r in rows]
    on = [app_path(r["question"], True) for r in rows]
    bf_diff = [r["question"] for r, a, b in zip(rows, off, on) if a[0] != b[0]]
    slot_diff = [r["question"] for r, a, b in zip(rows, off, on) if a[1] != b[1]]
    ac4 = not bf_diff and not slot_diff
    print(f"  app 사용 bf 불일치: {len(bf_diff)}건 · 슬롯 불일치: {len(slot_diff)}건 (기대 0)"
          f"  → {'OK' if ac4 else 'DIFF ⛔'}")
    if not ac4:
        fails.append(("AC4", "bf·슬롯 불일치 0", f"bf {len(bf_diff)}건 · 슬롯 {len(slot_diff)}건"))

    # 잔여 갭(측정치) — 검색측 ②는 rag.search 내부 호출이라 이번 스프린트에서 못 없앤다.
    ms = [(r, a, b) for r, a, b in zip(rows, off, on)
          if r["business_function"] == "착오송금 반환 신청"]
    drift = [(r["question"], a[0], classify_query_bf(b[2]))
             for r, a, b in zip(rows, off, on) if a[0] != classify_query_bf(b[2])]
    drift_ms = [d for d in drift if any(d[0] == r["question"] for r, _, _ in ms)]
    print(f"  [참고·잔여 갭] 부스트 ON 시 **검색측** bf(rag.search 내부 재분류)가 app bf 와"
          f" 갈리는 질의: 전체 {len(drift)}건 / 착오송금 {len(drift_ms)}건")
    for q, a, b in drift[:3]:
        print(f"    · {q[:34]:34} app={a} · 검색측={b}")
    print("    (rag.py·chain.py 무수정 제약상 이번 스프린트 범위 밖 — 부스트 기본 OFF 로 회피)")

    # ── 샘플 트레이스 (패널에 나갈 형태 확인) ────────────────────────────────
    print("\n── 샘플: 점수 내역 재계산 (패널 노출 형태) ──")
    for q in ["착오송금 반환 신청 서류가 뭐예요?", "예금보호한도가 얼마인가요?",
              "반환 신청 어떻게 해요?"]:
        d = bf_debug(q)
        print(f"  \"{q}\"")
        print(f"    판정 {d['bf']} [{d['verdict']}] · {d['reason']}")
        for bf, hs in sorted(d["hits"].items(), key=lambda x: -d["scores"][x[0]]):
            trig = ", ".join(f"{k}×{n}(w{w})" if n > 1 else f"{k}(w{w})" for k, w, n in hs)
            print(f"      {d['scores'][bf]:>2}점  {bf:12} ← {trig}")

    # ── 판정 ────────────────────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════
    # T5 — 트레이스 수집기
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "═" * 68)
    print("T5 — 층별 트레이스 수집")
    print("═" * 68)

    import ast

    import attachments as _att
    import qform_ask
    import qform_flow

    # 고정 hits — 착오송금 첨부 보유 3문서의 실제 청크 (verify_qform_integration 동일 기준)
    MS_DOCS = {"kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn",
               "kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn",
               "kdic-fins-ir-aplygudn-MtrsVstRcptGudn-selectScrn"}
    FIXED_HITS = [json.loads(l) for l in
                  (_BASE / "crawler" / "data" / "chunks.jsonl").open(encoding="utf-8")
                  if json.loads(l)["parent_doc_id"] in MS_DOCS]

    search_calls = [0]

    def stub_search(q, k=3):
        # 실앱에서는 트레이스의 재호출과 answer() 내부 검색이 **같은 hits** 를 낸다
        # (같은 쿼리·k·mode·결정론). 스텁도 stub_answer 와 같은 집합을 써야 필터 전/후가
        # 같은 기준으로 비교된다 — 어긋나면 "필터 후가 더 많다" 같은 거짓 대비가 나온다.
        search_calls[0] += 1
        return FIXED_HITS

    ANSWER_CALLS: list[tuple] = []

    def stub_answer(q, qform):
        ANSWER_CALLS.append((q, dict(qform)))
        return {"text": "(스텁 답변)", "sources": [], "confidence": 0.5, "route": "rag",
                "checks": {"ok": True, "flags": []},
                "attachments": _att.collect(FIXED_HITS, qform=qform),
                "_meta": {"cls_label": "정상", "cls_reason": "소관 업무", "cls_calls": 1,
                          "cls_parse_fail": 0, "cls_latency_ms": 300, "hcx_status": 200,
                          "latency_ms": 1200, "error": None, "k": 3, "qform": qform}}

    def trace_of(state, ev, *, boost=False, hcx_calls=2):
        """app 층이 할 조립을 그대로 재현 — 전이 이벤트 + 상태에서 트레이스를 만든다."""
        return collect(
            state["base_q"], bf_debug(state["base_q"]), state["slots_raw"],
            ev.get("survivors"), ev.get("ask"), ev.get("result"), boost,
            search_q=ev.get("search_q"), search_fn=stub_search,
            hcx_calls=hcx_calls, ask_turn=state["ask_turn"])

    # ── AC1. 트레이스 수집이 HCX 콜을 늘리지 않음 ───────────────────────────
    print("\n── AC1. 트레이스 수집 = LLM 콜 0 ──")
    tsrc = ast.parse((_BASE / "chatbot" / "qform_trace.py").read_text(encoding="utf-8"))
    main_ids = set()
    for n in tsrc.body:
        if isinstance(n, ast.If) and isinstance(n.test, ast.Compare) \
                and getattr(n.test.left, "id", None) == "__name__":
            main_ids.update(id(x) for x in ast.walk(n))
    banned_calls = []
    for n in ast.walk(tsrc):
        if isinstance(n, ast.Call) and id(n) not in main_ids:
            f = n.func
            nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if nm in ("_hcx", "answer", "classify", "post"):
                banned_calls.append((nm, n.lineno))
    ANSWER_CALLS.clear()
    st_a = qform_flow.new_state()
    ev_a = qform_flow.start(st_a, "착오송금 반환 신청 서류가 뭐예요?",
                            classify_fn=rag.classify_query_bf, answer_fn=stub_answer)
    before_ans = len(ANSWER_CALLS)
    tr_a = trace_of(st_a, ev_a)
    ac1t = not banned_calls and len(ANSWER_CALLS) == before_ans
    print(f"  런타임 코드 내 LLM 호출({', '.join(('_hcx', 'answer', 'classify'))}) : "
          f"{len(banned_calls)}곳 (기대 0)")
    print(f"  collect() 실행 중 answer() 추가 호출: {len(ANSWER_CALLS) - before_ans}회 (기대 0)")
    print(f"  검색 재호출 {search_calls[0]}회 — 결정론(rag 순수 함수), LLM 콜 아님"
          f"  → {'OK' if ac1t else 'DIFF ⛔'}")
    if not ac1t:
        fails.append(("T5-AC1", "LLM 콜 0", f"{banned_calls}"))

    # ── AC2. rag.py · chain.py 무변경 ──────────────────────────────────────
    print("\n── AC2. rag.py · chain.py 무변경 ──")
    for rel in ("crawler/rag.py", "chatbot/chain.py"):
        b = (_BASE / rel).read_bytes()
        print(f"  {rel:18} sha256 {hashlib.sha256(b).hexdigest()[:16]} · {len(b)}bytes")
    print("  이 모듈은 chain 에서 get_searcher() 만 **읽기 호출**한다 (계측 심기·리턴값 추가 없음)")
    print("  → 사람 확인: `git diff crawler/rag.py chatbot/chain.py` 가 비어 있을 것")

    # ── AC3. 트레이스 ON/OFF 시 답변·첨부·콜수 동일 ────────────────────────
    print("\n── AC3. 트레이스 ON/OFF — 답변·첨부·콜수 동일 ──")
    SCRIPT = ["착오송금 반환 신청하려는데 필요한 서류 알려주세요", "대리인이 신청해요", "법인이요"]

    def replay(trace_on: bool):
        ANSWER_CALLS.clear()
        s, evs, trs = qform_flow.new_state(), [], []
        ev = qform_flow.start(s, SCRIPT[0], classify_fn=rag.classify_query_bf,
                              answer_fn=stub_answer)
        evs.append(ev)
        if trace_on:
            trs.append(trace_of(s, ev))
        for rep in SCRIPT[1:]:
            if ev["kind"] != "ask":
                break
            ev = qform_flow.reply(s, rep, answer_fn=stub_answer)
            evs.append(ev)
            if trace_on:
                trs.append(trace_of(s, ev))
        last = evs[-1]
        return (list(ANSWER_CALLS), last["result"]["text"],
                sorted((a["doc_id"], a["orig_filename"]) for a in last["result"]["attachments"]),
                trs)

    off_calls, off_text, off_att, _ = replay(False)
    on_calls, on_text, on_att, traces = replay(True)
    ac3 = off_calls == on_calls and off_text == on_text and off_att == on_att
    print(f"  answer() 호출 인자 동일: {off_calls == on_calls} · 답변 동일: {off_text == on_text}")
    print(f"  첨부 동일: {off_att == on_att} ({len(on_att)}건) · answer 콜수 {len(off_calls)}={len(on_calls)}"
          f"  → {'OK' if ac3 else 'DIFF ⛔'}")
    print("  (트레이스는 answer() **이후**에 반환값으로 조립된다 — 파이프라인에 개입 지점이 없다)")
    if not ac3:
        fails.append(("T5-AC3", "ON/OFF 동일", "상이"))

    # ── AC4. reject 경로 부분 트레이스 ─────────────────────────────────────
    print("\n── AC4. reject 경로 — 크래시 없이 부분 트레이스 ──")
    reject_result = {"text": "죄송합니다…", "sources": [], "confidence": 0.0, "route": "reject",
                     "checks": {"ok": True, "flags": [], "skipped": "고정 거절 문구"},
                     "attachments": [],
                     "_meta": {"cls_label": "소관밖", "cls_reason": "타기관 소관",
                               "cls_calls": 1, "cls_parse_fail": 0, "cls_latency_ms": 280,
                               "latency_ms": 280, "k": 3}}
    QR = "미국 은행에 넣은 예금도 보호되나요?"
    tr_r = collect(QR, bf_debug(QR), extract(QR, business_function=rag.classify_query_bf(QR)),
                   None, None, reject_result, False, search_fn=stub_search, hcx_calls=1)
    skipped = [k for k in ("search", "generate", "attachments")
               if tr_r["layers"][k]["status"].startswith("생략")]
    ac4t = skipped == ["search", "generate", "attachments"] and tr_r["layers"]["gate"]["label"] == "소관밖"
    print(f"  {'층':12} 상태")
    for k in LAYER_ORDER:
        print(f"  {LAYER_LABEL[k]:12} {tr_r['layers'][k]['status']}")
    print(f"  → {'OK' if ac4t else 'DIFF ⛔'}  (검색·생성·첨부 3층 생략 표기)")

    # 되묻기 턴(답변 전) 부분 트레이스도 크래시 없어야 한다
    st_p = qform_flow.new_state()
    ev_p = qform_flow.start(st_p, "착오송금 반환 신청 서류가 뭐예요?",
                            classify_fn=rag.classify_query_bf, answer_fn=stub_answer)
    tr_p = trace_of(st_p, ev_p, hcx_calls=0)
    ac4p = (ev_p["kind"] == "ask" and tr_p["pending"]
            and tr_p["layers"]["ask"]["fired"] and tr_p["layers"]["combos"]["remaining"] == 7)
    print(f"  [되묻기 턴] pending={tr_p['pending']} · 되묻기 발동={tr_p['layers']['ask']['fired']} · "
          f"생존 {tr_p['layers']['combos']['remaining']}행 · 검색층 \"{tr_p['layers']['search']['status']}\""
          f"  → {'OK' if ac4p else 'DIFF ⛔'}")
    if not (ac4t and ac4p):
        fails.append(("T5-AC4", "생략 표기·무크래시", f"{skipped}"))

    # ── AC5. 첨부 필터 전/후 재현 (11서식 / 24파일 기준값) ──────────────────
    print("\n── AC5. 첨부 필터 전/후 재현 ──")
    tr_full = collect("착오송금 반환 신청 서류가 뭐예요?",
                      bf_debug("착오송금 반환 신청 서류가 뭐예요?"),
                      {**{f: None for f in qform_state.SLOT_FIELDS},
                       "party": "송금인", "sub_task": "반환신청",
                       "qualification": "대리인", "subject": "법인"},
                      None, None,
                      stub_answer("착오송금 반환 신청 서류가 뭐예요?",
                                  {"party": "송금인", "sub_task": "반환신청",
                                   "qualification": "대리인", "subject": "법인", "method": None}),
                      False, hits=FIXED_HITS, hcx_calls=2)
    A = tr_full["layers"]["attachments"]
    ac5t = A["before_forms"] == 11 and A["before_files"] == 24
    print(f"  필터 전 {A['before_forms']}서식 / {A['before_files']}파일  (기준 11서식 / 24파일)")
    print(f"  필터 후 {A['after_forms']}서식 / {A['after_files']}파일  (조합 C04 · 법인 대리)")
    print(f"  → {'OK' if ac5t else 'DIFF ⛔'}")
    if not ac5t:
        fails.append(("T5-AC5", "11서식/24파일", f"{A['before_forms']}서식/{A['before_files']}파일"))

    # ── 층 구성 · 콜 회계 (T6 패널 · T7 §1 과 1:1) ─────────────────────────
    print("\n── 층 구성과 콜 회계 (T6 패널 카드 순서) ──")
    tr = traces[-1]
    print(f"  {'#':>2} {'층':12} {'콜':>3}  요약")
    for i, k in enumerate(LAYER_ORDER, 1):
        lay = tr["layers"][k]
        c = lay.get("calls")
        summary = {
            "gate": lambda: f"{lay['label']} — {lay['reason']}",
            "bf": lambda: f"{lay['bf']} [{lay['verdict']}] 마진 {lay['margin']}",
            "slots": lambda: (f"{lay['filled']}/5 채움 · scope={lay['scope']}"
                              f" · 이월 {lay['carried']}개 ({lay['carryover']})"),
            "combos": lambda: " → ".join(f"{n}" for _, n in lay["trail"]) +
                              f"  ({', '.join(lay['combo_ids'])})",
            "ask": lambda: (f"{lay['slot']} 물음 ({lay['mode']})" if lay["fired"]
                            else lay["reason"]),
            "search": lambda: f"top-{lay['k']} · 부스트 {lay['boost_applied']}"
                              + (" · bf 갈림 ⚠" if lay["bf_drift"] else ""),
            "generate": lambda: f"{lay['latency_ms']}ms · {lay['chars']}자",
            "attachments": lambda: f"{lay['before_forms']}서식/{lay['before_files']}파일 "
                                   f"→ {lay['after_forms']}서식/{lay['after_files']}파일",
            "checks": lambda: f"ok={lay['ok']} · 플래그 {len(lay['flags'])}건",
        }[k]()
        badge = "콜0" if k in DETERMINISTIC else (str(c) if c is not None else "?")
        print(f"  {i:>2} {LAYER_LABEL[k]:12} {badge:>3}  {summary}")
    print(f"  총 HCX {tr['calls']['total']}콜 = 게이트 {tr['calls']['gate']} + "
          f"되묻기 {tr['calls']['ask']} + 생성 {tr['calls']['generate']}")
    print(f"  결정론 구간 {len(DETERMINISTIC)}층은 전부 콜 0 (재계산·반환값 읽기)")

    print()
    if fails:
        print("어긋난 AC ⛔")
        print(f"  {'AC':8} {'기대':22} 실측")
        for ac, want, got in fails:
            print(f"  {ac:8} {want:22} {got}")
        sys.exit(1)
    print("전체 통과 ✅  (LLM 호출 0 — 결정론 재계산만)")
    sys.exit(0)
