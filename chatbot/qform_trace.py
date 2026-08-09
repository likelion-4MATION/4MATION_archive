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
# 검증 하니스 (python3 chatbot/qform_trace.py) — T1 AC 실측 출력
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
    print()
    if fails:
        print("어긋난 AC ⛔")
        print(f"  {'AC':6} {'기대':22} 실측")
        for ac, want, got in fails:
            print(f"  {ac:6} {want:22} {got}")
        sys.exit(1)
    print("전체 통과 ✅  (LLM 호출 0 — 결정론 재계산만)")
    sys.exit(0)
