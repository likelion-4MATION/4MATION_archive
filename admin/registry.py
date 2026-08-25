# -*- coding: utf-8 -*-
"""파라미터 레지스트리 — 관리자 콘솔의 단일 진실 소스.

**원본 코드를 수정하지 않는다.** 각 파라미터가 어느 모듈의 어느 상수인지만 여기 적어 두고,
값은 `data/admin_config.json` 오버라이드로 관리한다(`settings.py`).

`tier`
    normal   일반 관리자 노출
    advanced 개발자 잠금(⑥ 고급)
    rebuild  변경 시 재빌드 필요(⑦ 문서 처리)
    locked   표시만, 수정 불가

`apply`
    runtime  저장 즉시 다음 질의부터 반영
    rebuild  인덱스/코퍼스 재생성 후 반영
"""
from __future__ import annotations

# ── 파라미터 정의 ────────────────────────────────────────────────────────
# key: (label, type, default, spec, tier, apply, source, help)
P = "param"


def _p(key, label, type_, default, tier, apply, source, help_, **spec):
    return dict(key=key, label=label, type=type_, default=default,
                tier=tier, apply=apply, source=source, help=help_, **spec)


PARAMS = [
    # ── ① 답변 품질 ────────────────────────────────────────────────
    _p("preset", "검색 방식", "enum", "accuracy", "normal", "runtime",
       "crawler/rag.py", "검증된 조합 3종 중 선택. 개별 숫자는 ⑥ 고급 탭에서만 바꿉니다.",
       values=["accuracy", "balanced", "diverse"], tab=1),
    _p("k", "답변에 참고할 문서 수", "int", 3, "normal", "runtime",
       "chatbot/chain.py:answer(k=)", "많을수록 근거가 늘지만 응답이 느려지고 비용이 올라갑니다.",
       min=1, max=5, tab=1),
    _p("maxTokens", "답변 길이 상한", "int", 512, "normal", "runtime",
       "chatbot/chain.py:GEN_PARAMS", "짧으면 빠르고 저렴하지만 답변이 잘릴 수 있습니다.",
       min=256, max=1024, step=128, tab=1),
    _p("temperature", "답변 일관성", "float", 0.2, "normal", "runtime",
       "chatbot/chain.py:GEN_PARAMS", "낮을수록 같은 질문에 항상 같은 답을 합니다.",
       min=0.0, max=1.0, step=0.1, tab=1),
    _p("strictUrl", "링크 검사 엄격도", "bool", True, "normal", "runtime",
       "chatbot/answer_checks.py:allow_context_urls",
       "엄격: 출처 목록에 없는 링크는 본문에 있었더라도 경고 표시(권장).", tab=1),

    # ── ② 응답 속도·비용 ───────────────────────────────────────────
    # OOS 조기차단과 안내처 사용은 확정 정책이라 토글하지 않는다. ⑧ OOS 안내처의
    # 게시·활성 상태가 실제 노출을 결정한다(옛 earlyBlock/linkRoute 설정은 폐기).
    _p("askMode", "되묻기 문구 생성 방식", "enum", "template", "normal", "runtime",
       "chatbot/qform_ask.py:build_question(mode=)",
       "정해진 문구=추가 비용 0 / AI 생성=되물을 때마다 비용 발생.",
       values=["template", "llm"], tab=2),

    # ── ③ 되묻기(큐폼) — chatbot/qform_config.py SPEC 과 1:1 ────────
    _p("QFORM_SCOPE", "되묻기 적용 업무", "enum", "msdr", "normal", "runtime",
       "chatbot/qform_config.py", "착오송금만 / 착오송금+예금보험금.",
       values=["msdr", "msdr+dpin"], tab=3),
    _p("MAX_ASK_TURNS", "되묻기 최대 횟수", "int", 2, "normal", "runtime",
       "chatbot/qform_config.py", "이 횟수에 닿으면 조건이 다 안 채워져도 답변합니다.",
       min=1, max=3, tab=3),
    _p("SLOT_CARRYOVER", "앞 대화 조건 기억", "bool", True, "normal", "runtime",
       "chatbot/qform_config.py", "앞 질문에서 확인한 조건을 다음 질문에도 적용합니다.", tab=3),
    _p("CARRYOVER_TTL", "조건 기억 유효 턴", "int", 3, "normal", "runtime",
       "chatbot/qform_config.py", "기억한 조건을 몇 번의 대화까지 유지할지.", min=1, max=5, tab=3),
    _p("CARRYOVER_SCOPE", "업무가 바뀌면", "enum", "bf_match", "normal", "runtime",
       "chatbot/qform_config.py", "기억 지움(권장) / 그대로 유지 / 기억 안 함.",
       values=["bf_match", "global", "off"], tab=3),
    _p("MAX_QUEUE", "대기 용건 최대 개수", "int", 3, "normal", "runtime",
       "chatbot/qform_config.py", "한 문장에 용건이 여러 개일 때 쌓아둘 개수. 0이면 기능 끔.",
       min=0, max=5, tab=3),
    _p("PANEL_EXPIRED", "만료된 항목 표시", "enum", "gray", "normal", "runtime",
       "chatbot/qform_config.py", "회색으로 남김(권장) / 화면에서 지움.",
       values=["gray", "drop"], tab=3),

    # ── ④ 최신성 가드 ──────────────────────────────────────────────
    _p("guardsEnabled", "가드 기능 사용", "bool", True, "normal", "runtime",
       "admin/guards.py", "끄면 등록된 정정 규칙이 모두 적용되지 않습니다.", tab=4),

    # ── ⑥ 고급 (개발자 잠금) ───────────────────────────────────────
    _p("RRF_ALPHA", "RRF_ALPHA", "float", 0.65, "advanced", "runtime",
       "crawler/rag.py", "의미검색(dense) 비중. 1.0이면 키워드검색 미사용.",
       min=0.5, max=1.0, step=0.05, tab=6),
    _p("RRF_K", "RRF_K", "int", 4, "advanced", "runtime",
       "crawler/rag.py", "순위 결합 상수. 낮을수록 상위 랭크를 더 신뢰.", min=0, max=8, tab=6),
    _p("BF_BOOST", "BF_BOOST", "float", 0.06, "advanced", "runtime",
       "crawler/rag.py", "같은 업무 문서 가산점.", min=0.0, max=0.20, step=0.01, tab=6),
    _p("FACET_BOOST", "FACET_BOOST", "float", 0.05, "advanced", "runtime",
       "crawler/rag.py", "질문 유형(구비서류·절차 등) 일치 가산점.", min=0.0, max=0.30, step=0.01, tab=6),
    _p("BF_DOC_CAP", "BF_DOC_CAP", "int", 5, "advanced", "runtime",
       "crawler/rag.py", "한 문서에서 뽑을 최대 청크 수.", min=1, max=10, tab=6),
    _p("BF_MODE", "BF_MODE", "enum", "soft", "advanced", "runtime",
       "crawler/rag.py", "soft=가산점 / hard=타 업무 제외. hard는 오분류 시 정답을 배제합니다.",
       values=["soft", "hard"], tab=6),
    _p("QBF_MSP_MIN", "QBF_MSP_MIN", "float", 0.70, "advanced", "runtime",
       "crawler/rag.py", "업무 분류기 신뢰 임계값. 미만이면 '불명' 처리.",
       min=0.5, max=0.95, step=0.05, tab=6),
    _p("CALL_BUDGET", "세션당 LLM 콜 상한", "int", 70, "advanced", "runtime",
       "chatbot/chain.py", "안전장치. 소진 시 즉시 중단됩니다.", min=10, max=500, tab=6),

    # ── ⑦ 문서 처리 (재빌드) ───────────────────────────────────────
    _p("CHUNK_SIZE", "조각 크기 상한", "int", 800, "rebuild", "rebuild",
       "crawler/chunk.py", "한 조각의 목표 상한. 문단·섹션 경계를 우선하므로 고정 크기가 아닙니다.",
       min=400, max=1200, step=100, tab=7),
    _p("OVERLAP", "조각끼리 겹치는 분량", "int", 100, "rebuild", "rebuild",
       "crawler/chunk.py",
       "늘려도 정확해지지 않는다는 것이 측정으로 확인됐습니다(100 > 200 > 300). "
       "0은 겹침 없음이 아니라 직전 조각 통째 복제로 동작해 자동으로 1로 낮춰 실행합니다.",
       min=0, max=300, step=5, tab=7),
    _p("MIN_CHUNK", "최소 조각 길이", "int", 60, "rebuild", "rebuild",
       "crawler/chunk.py", "이보다 짧은 조각은 앞 조각에 합칩니다.", min=20, max=150, step=10, tab=7),
    _p("TABLE_KEEP", "표 통째로 유지", "bool", True, "rebuild", "rebuild",
       "crawler/chunk.py:TABLE_GAP_MAX",
       "끄지 마세요 — 여러 업권을 비교하는 질문의 정확도가 0.82에서 0.31로 떨어집니다.", tab=7),
    _p("TABLE_GAP_MAX", "표 사이 본문 흡수 한도", "int", 12, "rebuild", "rebuild",
       "crawler/chunk.py", "'표 → 설명 → 표' 구조에서 몇 줄까지 함께 묶을지.", min=0, max=30, tab=7),
    # `recrawl` 은 여기 없다 — 저장되는 **값**이 아니라 한 번 실행하는 **동작**이기 때문이다.
    # 예전에는 재빌드 파라미터로 두었는데, 재빌드가 성공하면 `commit_pending()` 이 그 값을
    # `override` 로 승격시켜 **그 뒤 모든 재빌드가 계속 홈페이지에 접속**했다. 지금은 고정
    # 패널의 [원문 재수집] 버튼이 잡 인자로만 넘긴다(`jobs.start(..., recrawl=True)`).

    # ── 표시 전용 ─────────────────────────────────────────────────
    _p("embedModel", "임베딩 모델", "text", "dragonkue/BGE-m3-ko", "locked", "rebuild",
       "crawler/rag.py:MODEL_NAME", "변경 시 인덱스 전체 재생성이 필요합니다.", tab=6),
]

BY_KEY = {p["key"]: p for p in PARAMS}
DEFAULTS = {p["key"]: p["default"] for p in PARAMS}
REBUILD_KEYS = {p["key"] for p in PARAMS if p["apply"] == "rebuild"}

# ── 검색 프리셋 (crawler/data/tune_v2_summary.md 실측 상위 조합) ──────────
PRESETS = {
    "accuracy": dict(label="정확도 우선", RRF_ALPHA=0.65, RRF_K=4, BF_BOOST=0.06,
                     FACET_BOOST=0.05, BF_DOC_CAP=5,
                     desc="표준적인 질문에서 가장 정확합니다"),
    "balanced": dict(label="균형", RRF_ALPHA=0.65, RRF_K=4, BF_BOOST=0.03,
                     FACET_BOOST=0.05, BF_DOC_CAP=5,
                     desc="질문 유형이 골고루 섞일 때 가장 안정적입니다"),
    "diverse": dict(label="다양성 우선", RRF_ALPHA=0.65, RRF_K=2, BF_BOOST=0.03,
                    FACET_BOOST=0.10, BF_DOC_CAP=3,
                    desc="한 문서에 몰리지 않고 여러 문서를 보여줍니다"),
}


# ── 기준 설정 (초기화 버튼) ─────────────────────────────────────────────
# "지금까지 나온 가장 좋은 조합"으로 되돌리는 지점. 기본값과 거의 같고 `k` 만 다르다 —
# 같은 코퍼스에서 hit@3 0.8108 < hit@5 0.9081 이라 근거 포함률이 높은 쪽을 고른 것이다.
GOLDEN = {
    "label": "기준 설정 (앵커 hit@5 0.9081)",
    "value": 0.9081,
    "metric": "anchor hit@5",
    "chunks": 181,
    "src": "exp_tablefix (181청크 · 표 유지 on) · 검색 5축은 tune_params_v2 8,064조합 그리드",
    "caveat": "이 0.9081은 **181청크** 코퍼스에서 잰 값입니다. 판정 잣대(앵커 hit@5)는 "
              "지금 대시보드와 같지만 코퍼스가 다릅니다 — 되돌린 뒤 [한 번에 실행]으로 "
              "현재 코퍼스에서 다시 재세요.",
    "values": {**DEFAULTS, "k": 5},
}


def golden_diff(cfg: dict) -> list[dict]:
    """현재 설정이 기준 설정과 어디서 다른가 — 되돌리기 버튼이 무엇을 바꿀지."""
    out = []
    for key, want in GOLDEN["values"].items():
        spec = BY_KEY.get(key)
        if not spec or spec["tier"] == "locked":
            continue
        if str(cfg.get(key)) != str(want):
            out.append({"key": key, "label": spec["label"],
                        "from": cfg.get(key), "to": want,
                        "rebuild": key in REBUILD_KEYS})
    return out


def validate(values: dict) -> list[dict]:
    """허용범위 위반 목록. qform_config.validate() 와 같은 관용 정책 — 예외를 던지지 않는다."""
    bad = []
    for key, got in (values or {}).items():
        spec = BY_KEY.get(key)
        if spec is None:
            bad.append(dict(key=key, got=got, why="미정의 파라미터"))
            continue
        if spec["tier"] == "locked":
            bad.append(dict(key=key, got=got, why="수정 불가 항목"))
        elif spec["type"] == "bool" and not isinstance(got, bool):
            bad.append(dict(key=key, got=got, why="켬/끔 값이 아님"))
        elif spec["type"] in ("int", "float"):
            try:
                v = float(got)
            except (TypeError, ValueError):
                bad.append(dict(key=key, got=got, why="숫자가 아님"))
                continue
            lo, hi = spec.get("min"), spec.get("max")
            if lo is not None and v < lo or hi is not None and v > hi:
                bad.append(dict(key=key, got=got, why=f"허용범위 {lo}~{hi} 밖"))
        elif spec["type"] == "enum" and got not in spec.get("values", []):
            bad.append(dict(key=key, got=got, why=f"허용값 {spec.get('values')} 밖"))
    return bad


def resolve(override: dict | None = None) -> dict:
    """기본값 + 오버라이드 병합. **범위 밖 값은 기본값으로 되돌리고 통과시킨다.**

    예외를 던지지 않는 이유는 `qform_config.resolve()` 와 같다 — 잘못된 값 하나로
    콘솔이 죽는 것보다 기본값으로 돌아가는 쪽이 낫다. 되돌린 사실은 `_invalid` 에 남긴다.
    """
    cfg = dict(DEFAULTS)
    bad = validate(override or {})
    bad_keys = {b["key"] for b in bad}
    for key, got in (override or {}).items():
        if key in BY_KEY and key not in bad_keys:
            cfg[key] = got
    # 프리셋 → 검색 5축 전개 (고급 탭에서 개별 지정한 값이 우선)
    pre = PRESETS.get(cfg.get("preset"), PRESETS["accuracy"])
    for axis in ("RRF_ALPHA", "RRF_K", "BF_BOOST", "FACET_BOOST", "BF_DOC_CAP"):
        if axis not in (override or {}):
            cfg[axis] = pre[axis]
    cfg["_invalid"] = bad
    return cfg


def is_custom_search(override: dict) -> bool:
    """고급 탭에서 검색 5축을 직접 건드렸는가 — '검증된 프리셋 아님' 배지 조건."""
    return any(k in (override or {}) for k in
               ("RRF_ALPHA", "RRF_K", "BF_BOOST", "FACET_BOOST", "BF_DOC_CAP"))
