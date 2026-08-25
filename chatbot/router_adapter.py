# -*- coding: utf-8 -*-
"""팀 6-BF 라우터를 절별 OOS 오케스트레이터 계약으로 감싼다.

임계값·margin·복수 BF 정책은 이 파일에서 새로 만들지 않는다. 현행 ``rag``가 반환하는
업무 판정을 그대로 소비하며, 팀 라우터가 이후 ``route_query_bf``를 제공하면 그 훅을
우선 사용한다. 현재 BF 쏠림 문제는 의도적으로 이 모듈의 범위 밖이다.
"""
from __future__ import annotations

import pathlib
import sys
from typing import Callable


ROOT = pathlib.Path(__file__).resolve().parent.parent
for _p in (ROOT / "chatbot", ROOT / "crawler"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

CANONICAL_CODES = {
    "예금자보호제도": "deposit_protection",
    "예금보험금 안내": "deposit_insurance_payment",
    "고객 미수령금 신청": "unclaimed_funds",
    "착오송금 반환 신청": "mistaken_transfer",
    "은닉재산 신고": "hidden_assets_report",
    "채무조정 안내": "debt_adjustment",
}


def _keyword_scores(rag, clause: str) -> dict[str, float]:
    q = clause.replace(" ", "")
    return {bf: float(sum(w * q.count(k.replace(" ", "")) for k, w in kws))
            for bf, kws in rag.BF_QUERY_KEYWORDS.items()}


def route_clause(clause: str, *, classify_fn: Callable[[str], str | None] | None = None) -> dict:
    """절 하나 → 트리거 여부, 선택 BF, 6개 점수와 모델 메타.

    ``classify_fn``은 테스트와 향후 팀 라우터 서비스 어댑터 주입점이다. 주입하지 않으면
    현행 라우터 판정을 그대로 사용한다. 경계 수치를 보정하거나 재해석하지 않는다.
    """
    import rag

    result = {
        "clause": clause, "triggered": False, "bf": None, "bf_code": None,
        "scores": {}, "probabilities": {}, "msp": None,
        "source": "unknown", "model_version": None, "error": None,
        "trigger": {"owner": "team_router", "policy": "delegated", "thresholds": {}},
    }
    observe_legacy = False
    try:
        if classify_fn is not None:
            bf = classify_fn(clause)
            result.update({"bf": bf, "triggered": bf is not None, "source": "injected"})
        else:
            # 팀원이 복수 트리거·margin을 포함한 새 계약을 제공하면 그 결과를 그대로 쓴다.
            team_hook = getattr(rag, "route_query_bf", None)
            if callable(team_hook):
                routed = dict(team_hook(clause) or {})
                result.update(routed)
                result["source"] = routed.get("source") or "team_router"
                result["triggered"] = bool(routed.get("triggered"))
                result["bf"] = routed.get("bf") if result["triggered"] else None
            else:
                # 레거시 계약. classify_query_bf의 높은 BF 통과율도 그대로 보존한다.
                bf = rag.classify_query_bf(clause)
                result.update({"bf": bf, "triggered": bf is not None, "source": "legacy"})
                observe_legacy = True

        # 팀 훅이 제공한 판정·점수는 다시 계산하거나 덮어쓰지 않는다. 레거시 계약일 때만
        # 동일 모델의 관측 점수를 진단용으로 덧붙이며, 이 값으로 경계를 재판정하지 않는다.
        router = rag.get_router() if observe_legacy else None
        if observe_legacy and router is not None and hasattr(router, "predict_scores"):
            observed = router.predict_scores([clause])[0]
            result.update({"scores": observed["scores"],
                           "probabilities": observed["probabilities"],
                           "msp": observed["msp"],
                           "model_version": getattr(router, "name", None),
                           "source": "router" if result["source"] == "legacy" else result["source"]})
        elif observe_legacy:
            result["scores"] = _keyword_scores(rag, clause)
            result["model_version"] = "keyword_fallback"
            if result["source"] == "legacy":
                result["source"] = "keyword_fallback"
        if result["source"] == "keyword_fallback":
            result["trigger"]["thresholds"] = {
                "min_score": getattr(rag, "QBF_MIN_SCORE", None),
                "margin": getattr(rag, "QBF_MARGIN", None),
            }
        elif result["source"] in ("router", "legacy"):
            result["trigger"]["thresholds"] = {
                "legacy_msp_min": getattr(rag, "QBF_MSP_MIN", None),
            }
    except Exception as exc:  # 라우터 장애는 RAG로 우회하지 않고 상위에서 PHONE_GUIDE 처리
        result.update({"triggered": False, "bf": None, "error": type(exc).__name__,
                       "source": "router_error"})
    result["bf_code"] = CANONICAL_CODES.get(result.get("bf"))
    return result
