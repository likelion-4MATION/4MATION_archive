"""KDIC RAG v3 청크 단위 검색 평가.

기존 ``eval.py``의 parent_doc_id 기반 평가는 변경하지 않는다. 이 모듈은
GT의 gold chunk와 검색된 chunk_id를 직접 비교하는 별도 평가기다.

사용 예:
    cd crawler
    python eval_anchor_v3.py --retrieved data/retrieved.jsonl
    python eval_anchor_v3.py --mode hybrid_bf
    python eval_anchor_v3.py --gt gt_testset_retrieval_450.jsonl --score both

``--retrieved``를 주면 검색을 실행하지 않고 JSONL의 결과를 그대로 평가한다.
각 결과 행은 ``id``와 순위순 ``retrieved_chunk_ids``를 가져야 한다.

``--score``로 적중 판정 기준을 고른다.
    chunk_id  gold ``chunk_id`` 완전일치(기존 동작)
    anchor    top-k 청크 텍스트가 ``gt_anchor_span``을 포함(골드텍스트 판정)
    both      둘 다 산출해 병기 — 기본값. 전환 효과를 같은 검색결과 위에서 바로 본다.
앵커 판정은 청크 본문이 필요해 ``--chunks``가 있을 때만 동작하며, ``gt_anchor_span``이
없는 문항은 분모에서 빠진다(미적중으로 세면 라벨 결측이 검색 실패로 둔갑한다).
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable


KS = (1, 3, 5, 10, 30, 50)
RECALL_KS = (3, 5, 10, 30, 50)
RETRIEVAL_DEPTH = 50   # 검색 깊이(recall@30/50 측정 위해 50까지)
MRR_DEPTH = 10        # MRR은 @10 유지
SCORE_MODES = ("chunk_id", "anchor", "both")


def _default_data_dir() -> Path:
    """스크립트 위치에서 GT v6가 있는 data 폴더를 찾는다."""
    for parent in Path(__file__).resolve().parents:
        data_dir = parent / "data"
        if (data_dir / "gt_schema_v6.jsonl").is_file():
            return data_dir
    raise FileNotFoundError("gt_schema_v6.jsonl을 포함한 data 폴더를 찾을 수 없습니다.")


def _get_gt_chunk_ids(item: dict) -> list[str]:
    """새 ``gt_chunk_ids`` 우선, 비어 있으면 구형 단일 gold를 사용한다."""
    chunk_ids = item.get("gt_chunk_ids")
    if chunk_ids:
        if isinstance(chunk_ids, str):
            chunk_ids = [chunk_ids]
        return list(dict.fromkeys(chunk_ids))
    chunk_id = item.get("gt_chunk_id")
    return [chunk_id] if chunk_id else []


# chunk_relation 별칭 → 채점 의미. v9 라벨(gt_natural882)이 gold 간 관계를 더 잘게
# 쪼개 기록하면서 near_dup/duplicate/contained가 등장했다. 셋 다 "gold 중 어느 하나로도
# 답이 된다"는 ANY이며, 실측으로 확인했다 — duplicate는 gold 본문 유사도 1.000(완전
# 동일), near_dup은 0.934~0.996, contained는 앵커가 gold 전부에 들어 있다.
# 알 수 없는 값은 계속 예외로 막는다. 조용히 ANY로 흘리면 스키마 드리프트가 묻힌다.
RELATION_ANY = {"single", "or", "duplicate", "near_dup", "contained"}
RELATION_ALL = {"and"}


def _get_relation_label(item: dict) -> str:
    """원본 chunk_relation 문자열(리포트 분해용). null/누락은 single."""
    return item.get("chunk_relation") or "single"


def _get_relation(item: dict) -> str:
    """채점에 쓰는 정규화 relation — ANY 계열은 'or', ALL은 'and'로 접는다.

    null/누락 relation은 확정 스키마의 단일 근거 레코드로 처리한다.
    """
    label = _get_relation_label(item)
    if label in RELATION_ALL:
        return "and"
    if label in RELATION_ANY:
        # 'single'은 gold 1개 전제라 'or'와 판정이 같지만, 기존 수치·감사 로그와의
        # 연속성을 위해 표기를 보존한다(_hit_at_k에서 둘 다 ANY로 처리).
        return "single" if label == "single" else "or"
    raise ValueError(f"{item.get('id')}: unsupported chunk_relation={label!r}")


def _hit_at_k(gold_ids: list[str], retrieved_ids: list[str], relation: str, k: int) -> bool:
    """single/or는 ANY, and는 ALL 조건으로 청크 hit을 판정한다."""
    if not gold_ids:
        return False
    top_k = set(retrieved_ids[:k])
    if relation in {"single", "or"}:
        return bool(set(gold_ids) & top_k)
    return set(gold_ids).issubset(top_k)


def _recalled_gold_at_k(gold_ids: list[str], retrieved_ids: list[str], k: int) -> int:
    """Top-k에 회수된 서로 다른 gold chunk 수를 반환한다."""
    return len(set(gold_ids) & set(retrieved_ids[:k]))


def _recall_at_k(gold_ids: list[str], retrieved_ids: list[str], k: int) -> float:
    """한 문항의 gold chunk coverage를 반환한다."""
    if not gold_ids:
        return 0.0
    return _recalled_gold_at_k(gold_ids, retrieved_ids, k) / len(set(gold_ids))


def _recall_at_10(gold_ids: list[str], retrieved_ids: list[str]) -> float:
    """Top-10에 회수된 gold chunk 비율(관계와 무관한 gold coverage)이다."""
    return _recall_at_k(gold_ids, retrieved_ids, 10)


def _reciprocal_rank(gold_ids: list[str], retrieved_ids: list[str], relation: str) -> float:
    """ANY는 첫 gold, AND는 마지막 필수 gold가 나온 순위의 역수다."""
    if not gold_ids:
        return 0.0
    gold_set = set(gold_ids)
    seen: set[str] = set()
    for rank, chunk_id in enumerate(retrieved_ids, 1):
        if chunk_id not in gold_set:
            continue
        if relation in {"single", "or"}:
            return 1.0 / rank
        seen.add(chunk_id)
        if seen == gold_set:
            return 1.0 / rank
    return 0.0


# ── 앵커텍스트 판정 (골드텍스트 기준) ───────────────────────────────────────
# chunk_id 완전일치 대신 "top-k 청크 중 하나라도 gt_anchor_span을 포함하는가"로 적중을
# 판정한다(docs/앵커텍스트_정답라벨링_파이프라인.md ⑤). 정답 내용이 여러 청크에 정당히
# 존재하는 경우(FAQ의 www/fins 중복 게재 등) ID 기준이 만들던 오탐이 사라지고,
# 재청킹으로 chunk_id가 밀려도 판정이 유지된다.
#
# 라벨은 `gt_anchors`(리스트) 우선, 없으면 구형 `gt_anchor_span` 1개를 씨앗으로 쓴다.
# gold 청크 전부가 앵커로 덮이지는 않으므로(450셋 555개 중 434개=78.2%), 덮이지 않는
# gold는 chunk_id로 판정하는 하이브리드다. 앵커를 지어내지 않으면서 relation 의미를
# 정확히 지키는 유일한 결정론적 방법 — 라벨이 채워질수록 id 의존분이 저절로 줄어든다.
#
# 판정:
#   single/or : 앵커 하나라도 top-k에서 발견  OR  앵커 없는 gold 하나라도 top-k에 존재
#   and       : 앵커 전부 발견  AND  앵커 없는 gold 전부 top-k에 존재
def _norm_text(text: str) -> str:
    """앵커·청크 텍스트 공통 정규화 — 공백/개행 차이만 흡수하고 문자는 보존."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def _get_gt_anchors(item: dict) -> list[str]:
    """정규화된 앵커 리스트. gt_anchors(신) 우선, gt_anchor_span(구) 폴백."""
    anchors = item.get("gt_anchors")
    if isinstance(anchors, str):
        anchors = [anchors]
    if not anchors:
        span = item.get("gt_anchor_span")
        anchors = [span] if span else []
    return list(dict.fromkeys(_norm_text(a) for a in anchors if a and a.strip()))


def _split_gold_by_anchor(gold_ids: list[str], anchors: list[str],
                          chunk_text: dict[str, str]) -> list[str]:
    """앵커로 덮이지 않는 gold 청크 — chunk_id 폴백 대상."""
    return [cid for cid in gold_ids
            if not any(a in chunk_text.get(cid, "") for a in anchors)]


def _anchor_found_at_k(anchor: str, retrieved_ids: list[str],
                       chunk_text: dict[str, str], k: int) -> bool:
    return any(anchor in chunk_text.get(cid, "") for cid in retrieved_ids[:k])


def _anchor_hit_at_k(anchors: list[str], unanchored: list[str], retrieved_ids: list[str],
                     chunk_text: dict[str, str], relation: str, k: int) -> bool:
    if not anchors and not unanchored:
        return False
    top_k = set(retrieved_ids[:k])
    if relation == "and":
        return (all(_anchor_found_at_k(a, retrieved_ids, chunk_text, k) for a in anchors)
                and set(unanchored).issubset(top_k))
    return (any(_anchor_found_at_k(a, retrieved_ids, chunk_text, k) for a in anchors)
            or bool(set(unanchored) & top_k))


def _anchor_reciprocal_rank(anchors: list[str], unanchored: list[str],
                            retrieved_ids: list[str], chunk_text: dict[str, str],
                            relation: str) -> float:
    """조건이 충족되는 최초 순위의 역수. and는 마지막 필수 근거가 나온 순위."""
    for rank in range(1, min(len(retrieved_ids), MRR_DEPTH) + 1):
        if _anchor_hit_at_k(anchors, unanchored, retrieved_ids, chunk_text, relation, rank):
            return 1.0 / rank
    return 0.0


def _empty_anchor_metrics() -> dict:
    # Recall은 두지 않는다 — 앵커는 '회수 비율'의 분모가 되는 단위가 아니다.
    # 0.000을 찍으면 chunk_level의 recall과 나란히 놓였을 때 오독되므로 아예 뺀다.
    return {"n_scored": 0, "n_missing_span": 0, "n_full_anchor": 0, "n_id_fallback": 0,
            **{f"hit@{k}": 0.0 for k in KS}, "mrr": 0.0}


def _anchor_metric_values(anchors: list[str], unanchored: list[str], retrieved_ids: list[str],
                          chunk_text: dict[str, str], relation: str) -> dict:
    return {**{f"hit@{k}": _anchor_hit_at_k(anchors, unanchored, retrieved_ids,
                                            chunk_text, relation, k) for k in KS},
            "mrr": _anchor_reciprocal_rank(anchors, unanchored, retrieved_ids,
                                           chunk_text, relation)}


def _add_anchor_metrics(metrics: dict, values: dict) -> None:
    metrics["n_scored"] += 1
    for key in (*(f"hit@{k}" for k in KS), "mrr"):
        metrics[key] += values[key]


def _finalize_anchor_metrics(metrics: dict) -> dict:
    if metrics["n_scored"]:
        for key in (*(f"hit@{k}" for k in KS), "mrr"):
            metrics[key] /= metrics["n_scored"]
    return metrics


def _empty_metrics() -> dict:
    return {
        "n_total": 0,
        "n_evaluated": 0,
        "n_excluded_unanswerable": 0,
        "n_inconsistent": 0,
        **{f"hit@{k}": 0.0 for k in KS},
        **{f"recalled_gold@{k}": 0 for k in RECALL_KS},
        "total_gold": 0,
        **{f"recall@{k}": 0.0 for k in RECALL_KS},
        **{f"macro_recall@{k}": 0.0 for k in RECALL_KS},
        "missing_gold@10": 0,
        "mrr": 0.0,
    }


def _metric_values(gold_ids: list[str], retrieved_ids: list[str], relation: str) -> dict:
    return {
        **{f"hit@{k}": _hit_at_k(gold_ids, retrieved_ids, relation, k) for k in KS},
        **{f"recalled_gold@{k}": _recalled_gold_at_k(gold_ids, retrieved_ids, k)
           for k in RECALL_KS},
        **{f"recall@{k}": _recall_at_k(gold_ids, retrieved_ids, k)
           for k in RECALL_KS},
        # rank cutoff matches RETRIEVAL_DEPTH so MRR stays MRR@10, not MRR@len(retrieved_ids).
        "mrr": _reciprocal_rank(gold_ids, retrieved_ids[:MRR_DEPTH], relation),
    }


# hit 누산은 KS 전체를 돈다. hit@30/hit@50이 빠져 있어 chunk/doc 레벨에서 항상
# 0.0000으로 찍혔고, "top-50에도 없음"으로 오독될 수 있었다(리랭커 헤드룸 산정 시 실제로 걸림).
_HIT_KEYS = tuple(f"hit@{k}" for k in KS) + ("mrr",)


def _add_metrics(metrics: dict, values: dict, gold_ids: list[str]) -> None:
    """문항 하나의 결과를 집계 메트릭에 더한다."""
    metrics["n_evaluated"] += 1
    unique_gold_count = len(set(gold_ids))
    metrics["total_gold"] += unique_gold_count
    for key in _HIT_KEYS:
        metrics[key] += values[key]
    for k in RECALL_KS:
        metrics[f"recalled_gold@{k}"] += values[f"recalled_gold@{k}"]
        metrics[f"macro_recall@{k}"] += values[f"recall@{k}"]


def _finalize_metrics(metrics: dict) -> dict:
    """Hit/MRR/MacroRecall은 문항 기준, (micro)Recall은 gold chunk occurrence 기준으로 정규화한다."""
    if metrics["n_evaluated"]:
        denominator = metrics["n_evaluated"]
        for key in _HIT_KEYS:
            metrics[key] /= denominator
        for k in RECALL_KS:
            metrics[f"macro_recall@{k}"] /= denominator
    if metrics["total_gold"]:
        denominator = metrics["total_gold"]
        for k in RECALL_KS:
            metrics[f"recall@{k}"] = metrics[f"recalled_gold@{k}"] / denominator
    metrics["missing_gold@10"] = metrics["total_gold"] - metrics["recalled_gold@10"]
    return metrics


def _parent_ids(
    chunk_ids: list[str],
    chunk_to_doc: dict[str, str],
    missing_prefix: str = "__missing__",
) -> list[str]:
    """알 수 없는 gold는 절대 검색에 매칭되지 않는 별도 식별자로 보존한다."""
    return list(dict.fromkeys(chunk_to_doc.get(chunk_id, f"{missing_prefix}:{chunk_id}")
                              for chunk_id in chunk_ids))


def evaluate_retrieval(
    gt_data: Iterable[dict],
    retrieved_data: Iterable[dict],
    chunk_metadata: Iterable[dict] | None = None,
    score: str = "both",
) -> dict:
    """GT와 검색 결과를 결정론적으로 평가한다.

    answerable=false는 모든 Hit@K, Recall@K, MRR의 분모에서 제외된다.
    Recall은 문항 평균이 아니라 전체 gold chunk 기준으로 계산한다.
    ``chunk_metadata``를 주면 기존 방식과 같은 문서 단위 참고 지표도 함께 계산한다.

    ``score``: 적중 판정 기준.
      - ``chunk_id``: gold chunk_id 완전일치(기존 동작).
      - ``anchor``  : top-k 청크 텍스트가 ``gt_anchor_span``을 포함하는지(골드텍스트).
      - ``both``    : 둘 다 산출(기본). 전환 효과를 나란히 보기 위한 모드.
    앵커 판정은 청크 본문이 필요하므로 ``chunk_metadata`` 없이는 건너뛴다.
    """
    if score not in SCORE_MODES:
        raise ValueError(f"score must be one of {SCORE_MODES}, got {score!r}")
    retrieved_by_id: dict[str, list[str]] = {}
    for item in retrieved_data:
        item_id = item["id"]
        if item_id in retrieved_by_id:
            raise ValueError(f"duplicate retrieved result id: {item_id}")
        retrieved_by_id[item_id] = item.get("retrieved_chunk_ids", [])

    chunk_meta_list = list(chunk_metadata) if chunk_metadata is not None else None
    chunk_to_doc = {item["chunk_id"]: item["parent_doc_id"]
                    for item in (chunk_meta_list or [])}
    chunk_metrics = _empty_metrics()
    doc_metrics = _empty_metrics() if chunk_meta_list is not None else None
    relation_metrics: dict[str, dict] = {}
    domain_metrics: dict[str, dict] = {}
    audit_rows = []

    # 앵커 판정용 정규화 본문 — 청크당 1회만 정규화하고 문항마다 재사용.
    anchor_on = score in ("anchor", "both") and chunk_meta_list is not None
    chunk_text = ({c["chunk_id"]: _norm_text(c.get("text", "")) for c in chunk_meta_list}
                  if anchor_on else {})
    anchor_metrics = _empty_anchor_metrics() if anchor_on else None
    anchor_relation_metrics: dict[str, dict] = {}
    # 앵커 채점 대상(=span 보유) 문항만 모은 chunk_id 기준 수치. 두 판정의 Δ를 같은
    # 모집단 위에서 내기 위한 baseline — 전체 n_evaluated와 비교하면 라벨 결측분이
    # 판정 차이로 섞여 들어간다. hit@k·mrr 키가 같아 앵커 누산기를 그대로 재사용한다.
    chunk_on_anchor = _empty_anchor_metrics() if anchor_on else None
    chunk_on_anchor_relation: dict[str, dict] = {}

    for gt_item in gt_data:
        item_id = gt_item["id"]
        gold_ids = _get_gt_chunk_ids(gt_item)
        relation = _get_relation(gt_item)          # 채점용(ANY/ALL로 정규화)
        rel_label = _get_relation_label(gt_item)   # 리포트 분해용(원본 표기 보존)
        retrieved_ids = retrieved_by_id.get(item_id, [])
        answerable = gt_item.get("answerable") is True
        chunk_metrics["n_total"] += 1
        if doc_metrics is not None:
            doc_metrics["n_total"] += 1

        if not answerable:
            chunk_metrics["n_excluded_unanswerable"] += 1
            if doc_metrics is not None:
                doc_metrics["n_excluded_unanswerable"] += 1
            if gold_ids:
                chunk_metrics["n_inconsistent"] += 1
                if doc_metrics is not None:
                    doc_metrics["n_inconsistent"] += 1
            audit_rows.append({"id": item_id, "answerable": False, "chunk_relation": rel_label,
                               "gold_chunk_ids": gold_ids, "retrieved_chunk_ids": retrieved_ids,
                               "excluded": True})
            continue

        chunk_metrics["n_evaluated"] += 1
        if not gold_ids:
            chunk_metrics["n_inconsistent"] += 1
            if doc_metrics is not None:
                doc_metrics["n_inconsistent"] += 1
        values = _metric_values(gold_ids, retrieved_ids, relation)
        # n_evaluated is incremented above to preserve the explicit
        # answerable=true denominator, including an invalid no-gold label.
        chunk_metrics["total_gold"] += len(set(gold_ids))
        for key in _HIT_KEYS:
            chunk_metrics[key] += values[key]
        for k in RECALL_KS:
            chunk_metrics[f"recalled_gold@{k}"] += values[f"recalled_gold@{k}"]
            chunk_metrics[f"macro_recall@{k}"] += values[f"recall@{k}"]

        relation_metrics.setdefault(rel_label, _empty_metrics())
        relation_metrics[rel_label]["n_total"] += 1
        _add_metrics(relation_metrics[rel_label], values, gold_ids)

        domain = gt_item.get("business_function") or "(unknown)"
        domain_metrics.setdefault(domain, _empty_metrics())
        domain_metrics[domain]["n_total"] += 1
        _add_metrics(domain_metrics[domain], values, gold_ids)

        row = {"id": item_id, "answerable": True, "chunk_relation": rel_label,
               "business_function": domain, "question": gt_item.get("question", ""),
               "gold_chunk_ids": gold_ids, "retrieved_chunk_ids": retrieved_ids,
               "excluded": False, "chunk": values}

        if anchor_on:
            anchors = _get_gt_anchors(gt_item)
            unanchored = _split_gold_by_anchor(gold_ids, anchors, chunk_text)
            if not anchors and not unanchored:
                # 앵커도 gold도 없으면 판정 근거가 없다 — 미적중으로 세면 라벨 결측이
                # 검색 실패로 둔갑하므로 분모에서 빼고 건수로만 드러낸다.
                anchor_metrics["n_missing_span"] += 1
                row["anchor"] = None
            else:
                anchor_values = _anchor_metric_values(anchors, unanchored, retrieved_ids,
                                                      chunk_text, relation)
                _add_anchor_metrics(anchor_metrics, anchor_values)
                # 순수 앵커 판정분과 chunk_id 폴백이 섞인 분량을 나눠 센다 —
                # 이 비율이 라벨 작업 잔량이자 수치의 id 의존도다.
                if unanchored:
                    anchor_metrics["n_id_fallback"] += 1
                else:
                    anchor_metrics["n_full_anchor"] += 1
                anchor_relation_metrics.setdefault(rel_label, _empty_anchor_metrics())
                _add_anchor_metrics(anchor_relation_metrics[rel_label], anchor_values)
                # 같은 문항의 chunk_id 판정도 별도 누산 → Δ가 동일 모집단 기준이 된다.
                _add_anchor_metrics(chunk_on_anchor, values)
                chunk_on_anchor_relation.setdefault(rel_label, _empty_anchor_metrics())
                _add_anchor_metrics(chunk_on_anchor_relation[rel_label], values)
                row["anchor"] = anchor_values
        if doc_metrics is not None:
            gold_doc_ids = _parent_ids(gold_ids, chunk_to_doc, "__missing_gold__")
            retrieved_doc_ids = _parent_ids(retrieved_ids, chunk_to_doc, "__missing_retrieved__")
            doc_values = _metric_values(gold_doc_ids, retrieved_doc_ids, relation)
            _add_metrics(doc_metrics, doc_values, gold_doc_ids)
            row["gold_parent_doc_ids"] = gold_doc_ids
            row["doc"] = doc_values
        audit_rows.append(row)

    _finalize_metrics(chunk_metrics)
    if doc_metrics is not None:
        _finalize_metrics(doc_metrics)
    for metrics in relation_metrics.values():
        _finalize_metrics(metrics)
    for metrics in domain_metrics.values():
        _finalize_metrics(metrics)
    if anchor_metrics is not None:
        _finalize_anchor_metrics(anchor_metrics)
        _finalize_anchor_metrics(chunk_on_anchor)
        for metrics in anchor_relation_metrics.values():
            _finalize_anchor_metrics(metrics)
        for metrics in chunk_on_anchor_relation.values():
            _finalize_anchor_metrics(metrics)

    gold_coverage = {
        "gold_chunk_total": chunk_metrics["total_gold"],
        "recalled_gold@3": chunk_metrics["recalled_gold@3"],
        "recalled_gold@5": chunk_metrics["recalled_gold@5"],
        "recalled_gold@10": chunk_metrics["recalled_gold@10"],
        "missing_gold@10": chunk_metrics["missing_gold@10"],
        "gold_coverage@10": chunk_metrics["recall@10"],
    }

    return {
        "chunk_level": chunk_metrics,
        "document_level": doc_metrics,
        "anchor_level": anchor_metrics,
        "anchor_relation_metrics": anchor_relation_metrics,
        "chunk_on_anchor_subset": chunk_on_anchor,
        "chunk_on_anchor_subset_relation": chunk_on_anchor_relation,
        "relation_metrics": relation_metrics,
        "domain_metrics": domain_metrics,
        "gold_coverage": gold_coverage,
        "audit_rows": audit_rows,
        "score_mode": score,
    }


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _search_results(gt_data: Iterable[dict], mode: str, data_dir: Path) -> list[dict]:
    """검색 실행. mode='hybrid_bf'는 gold business_function을 주입해 순수 검색기만 평가한다.

    라우터는 별도 테스트셋에서 평가 중 → 여기선 classify_query_bf(질의 분류)를 태우지 않고
    레코드의 gold business_function을 주입한다. 배포 soft 경로(hybrid_soft+cap)를 그대로 복제.
    """
    import rag

    searcher = rag.Searcher(index_dir=str(data_dir / "index"))

    def gold_injected(question: str, gold_bf: str) -> list[str]:
        # rag.search(mode='hybrid_bf') under BF_MODE='soft' 의 복제 — 단 bf=gold
        pool = searcher.hybrid_soft(question, len(searcher.chunks),
                                    bf=gold_bf, boost=rag.BF_BOOST)
        capped = searcher._cap_by_doc(pool, rag.BF_DOC_CAP)[:RETRIEVAL_DEPTH]
        return [searcher.chunks[idx]["chunk_id"] for idx, _ in capped]

    results = []
    for item in gt_data:
        if mode == "hybrid_bf":
            rids = gold_injected(item["question"], item["business_function"])
        else:
            rids = [hit["chunk_id"] for hit in
                    searcher.search(item["question"], k=RETRIEVAL_DEPTH, mode=mode)]
        results.append({"id": item["id"], "retrieved_chunk_ids": rids})
    return results


def _format_ids(chunk_ids: list[str]) -> str:
    return "<br>".join(f"`{chunk_id}`" for chunk_id in chunk_ids) or "-"


def _pct_table(counter: dict, total: int, headers: tuple[str, str]) -> list[str]:
    lines = [f"| {headers[0]} | {headers[1]} |", "|---|---:|"]
    for key, count in sorted(counter.items(), key=lambda kv: -kv[1]):
        pct = count / total * 100 if total else 0.0
        lines.append(f"| {key} | {count} ({pct:.1f}%) |")
    return lines


def _error_analysis(rows: list[dict], chunk_to_bf: dict[str, str] | None) -> dict:
    """미적중(top-3 밖) 문항의 원인·혼입 패턴을 집계한다.

    chunk_to_bf가 없으면(청크 메타 미제공) 목록만 반환하고 도메인 분류는 생략한다.
    """
    misses = [row for row in rows if not row["excluded"] and not row["chunk"]["hit@3"]]
    by_domain: dict[str, int] = {}
    for row in misses:
        by_domain[row["business_function"]] = by_domain.get(row["business_function"], 0) + 1

    if chunk_to_bf is None:
        return {"misses": misses, "by_domain": by_domain, "cause": {}, "intruders": {},
                "cross_flow": {}, "worst": [row for row in misses if not row["chunk"]["hit@10"]][:8]}

    cause: dict[str, int] = {}
    intruders: dict[str, int] = {}
    cross_flow: dict[tuple[str, str], int] = {}
    for row in misses:
        top3 = row["retrieved_chunk_ids"][:3]
        top3_bf = [chunk_to_bf.get(cid, "(unknown)") for cid in top3]
        gt_bf = row["business_function"]
        reason = "정분류(업무 내 랭킹·청킹)" if gt_bf in top3_bf else "오분류(다른 업무로 혼입)"
        cause[reason] = cause.get(reason, 0) + 1
        for cid, bf in zip(top3, top3_bf):
            if bf != gt_bf:
                intruders[cid] = intruders.get(cid, 0) + 1
        if top3_bf and top3_bf[0] != gt_bf:
            key = (gt_bf, top3_bf[0])
            cross_flow[key] = cross_flow.get(key, 0) + 1

    worst = [row for row in misses if not row["chunk"]["hit@10"]][:8]
    return {"misses": misses, "by_domain": by_domain, "cause": cause,
            "intruders": intruders, "cross_flow": cross_flow, "worst": worst}


def write_report(result: dict, output_path: Path, gt_path: Path, retrieval_source: str,
                  chunk_metadata: list[dict] | None = None) -> None:
    """새 v3 결과 전용 Markdown 보고서를 저장한다."""
    chunk = result["chunk_level"]
    doc = result["document_level"]
    relation_metrics = result["relation_metrics"]
    domain_metrics = result["domain_metrics"]
    gold_coverage = result["gold_coverage"]
    rows = result["audit_rows"]
    chunk_to_bf = ({c["chunk_id"]: c.get("business_function", "(unknown)") for c in chunk_metadata}
                   if chunk_metadata else None)

    try:
        import rag
        retriever_desc = (f"RRF(k={rag.RRF_K}, alpha={rag.RRF_ALPHA}) + "
                          f"BF_MODE={rag.BF_MODE}(cap={rag.BF_DOC_CAP})")
        embedding_desc = rag.MODEL_NAME
    except Exception:
        retriever_desc = "정보 없음(외부 검색 결과 사용)"
        embedding_desc = "정보 없음(외부 검색 결과 사용)"

    lines = ["# KDIC 검색 평가 리포트 v3", "",
              "## 1. 개요", "",
              "청크 단위 검색 평가 — gold `chunk_id`를 직접 비교해 기존 `parent_doc_id` 기준 평가가",
              "안고 있던 '같은 문서면 적중' 거품을 배제하고 실제 청크 적중률을 측정한다.", "",
              "## 2. 평가 대상 / 데이터 구성", "",
              f"- GT 라벨: `{gt_path}`",
              f"- 전체 {chunk['n_total']}건 · 평가 대상(answerable=true) {chunk['n_evaluated']}건 · "
              f"제외(answerable=false) {chunk['n_excluded_unanswerable']}건 · 라벨 불일치 {chunk['n_inconsistent']}건",
              ""]
    lines += _pct_table({rel: m["n_total"] for rel, m in relation_metrics.items()},
                        chunk["n_evaluated"], ("relation", "문항수"))
    lines += ["",
              "## 3. 실험 파라미터", "",
              f"- Corpus: {len(chunk_metadata)}개 청크 (`chunks.jsonl`)" if chunk_metadata is not None
              else "- Corpus: 정보 없음(청크 메타 미제공)",
              f"- Retriever: {retriever_desc}",
              f"- Embedding: {embedding_desc}",
              f"- 검색 단위: chunk (기존 parent_doc_id 평가와 별도)",
              f"- 검색 소스: {retrieval_source}",
              f"- Top-K: {RETRIEVAL_DEPTH}", "",
              "## 4. 평가 지표 및 판정 기준", "",
              "- Hit@1/3/5/10: Top-K 안에 gold가 relation 조건을 만족하며 존재하는지 (분모: 평가 대상 문항수).",
              "- Macro Recall@3/5/10: 문항별 recall(Top-K에서 회수한 gold 비율)의 문항 평균. 주지표.",
              "- (참고) Micro Recall@3/5/10: 전체 gold occurrence 기준 합산 recall. 문항당 gold 개수가 많을수록 가중치가 커짐 — 보조지표로만 사용.",
              "- Gold Coverage: 전체 gold chunk occurrence 중 Top-10에서 회수되지 못한 비율(`missing_gold@10`).",
              "- MRR: relation 조건을 만족하는 gold가 처음 나온 순위의 역수, Top-10까지만 본다(MRR@10).",
              "- relation 판정: `single`/`or`는 ANY(하나만 맞아도 적중), `and`는 ALL(전부 맞아야 적중); null/누락은 single.",
              "- answerable=false 문항은 Hit@K·Recall@K·MRR 분모에서 제외.", "",
              "## 5. 전체 평가 결과", "",
              "| Hit@1 | Hit@3 | Hit@5 | Hit@10 | Hit@30 | Hit@50 | MRR@10 |",
              "|---:|---:|---:|---:|---:|---:|---:|",
              f"| {chunk['hit@1']:.3f} | {chunk['hit@3']:.3f} | {chunk['hit@5']:.3f} | "
              f"{chunk['hit@10']:.3f} | {chunk['hit@30']:.3f} | {chunk['hit@50']:.3f} | {chunk['mrr']:.3f} |",
              "",
              "| MacroRecall@3 | MacroRecall@5 | MacroRecall@10 | MacroRecall@30 | MacroRecall@50 |",
              "|---:|---:|---:|---:|---:|",
              f"| {chunk['macro_recall@3']:.3f} | {chunk['macro_recall@5']:.3f} | "
              f"{chunk['macro_recall@10']:.3f} | {chunk['macro_recall@30']:.3f} | {chunk['macro_recall@50']:.3f} |",
              "",
              "> recall@50 = 리랭커 천장. @10→@30→@50 증가폭이 크면 top-k 확대(리랭커 후보) 이득.",
              "",
              f"- (참고) Micro Recall@10: {chunk['recall@10']:.3f} · gold 총계(occurrence): "
              f"{gold_coverage['gold_chunk_total']} · 미회수(@10): {gold_coverage['missing_gold@10']}", "",
              "## 6. Relation별 결과", "",
              "| relation | 문항수 | Hit@5 | Hit@10 | MacroRecall@10 | MacroRecall@30 | MacroRecall@50 | MRR@10 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for rel in ("single", "or", "and"):
        m = relation_metrics.get(rel)
        if m:
            lines.append(f"| {rel} | {m['n_total']} | {m['hit@5']:.3f} | {m['hit@10']:.3f} | "
                        f"{m['macro_recall@10']:.3f} | {m['macro_recall@30']:.3f} | "
                        f"{m['macro_recall@50']:.3f} | {m['mrr']:.3f} |")

    lines += ["", "## 7. 도메인별 결과", "",
              "| 업무 | 문항수 | Hit@5 | Hit@10 | MacroRecall@10 | MacroRecall@30 | MacroRecall@50 | MRR@10 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for domain, m in sorted(domain_metrics.items(), key=lambda kv: -kv[1]["n_total"]):
        lines.append(f"| {domain} | {m['n_total']} | {m['hit@5']:.3f} | {m['hit@10']:.3f} | "
                    f"{m['macro_recall@10']:.3f} | {m['macro_recall@30']:.3f} | "
                    f"{m['macro_recall@50']:.3f} | {m['mrr']:.3f} |")

    err = _error_analysis(rows, chunk_to_bf)
    n_miss = len(err["misses"])
    lines += ["", "## 8. 오류 분석", "",
              f"- 미적중(top-3 밖) {n_miss}건 / 평가 대상 {chunk['n_evaluated']}건 "
              f"({n_miss / chunk['n_evaluated'] * 100 if chunk['n_evaluated'] else 0:.1f}%)", ""]
    if err["cause"]:
        lines += ["### 8-1. 미적중 원인 분포", "",
                  "정분류: gt 업무 청크가 top-3 안에 있으나 순위/청킹 문제로 놓침. "
                  "오분류: top-3 전부 다른 업무 청크로 채워짐. "
                  "(업무 분류기가 적용됐는지까지는 이 표만으로 알 수 없음 — 세부 조사는 수작업 검토 필요.)", ""]
        lines += _pct_table(err["cause"], n_miss, ("원인", "건수"))
    else:
        lines += ["_청크 메타(`--chunks`)가 없어 원인 분류를 생략함._"]

    lines += ["", "### 8-2. 업무별 미적중", "",
              "| 업무 | 문항수 | 미적중 | 미적중률 |", "|---|---:|---:|---:|"]
    for domain, count in sorted(err["by_domain"].items(), key=lambda kv: -kv[1]):
        total = domain_metrics[domain]["n_total"]
        lines.append(f"| {domain} | {total} | {count} | {count / total * 100 if total else 0:.1f}% |")

    if err["intruders"]:
        lines += ["", "### 8-3. 혼입 문서 랭킹 (미적중 top-3를 잠식한 다른 업무 청크)", "",
                  "| 청크 ID | 출현 | 업무 |", "|---|---:|---|"]
        for cid, count in sorted(err["intruders"].items(), key=lambda kv: -kv[1])[:15]:
            lines.append(f"| `{cid}` | {count} | {chunk_to_bf.get(cid, '(unknown)')} |")

    if err["cross_flow"]:
        lines += ["", "### 8-4. 업무 간 혼입 흐름 (정답 업무 → top-1 업무)", "",
                  "| 정답 업무 | → top-1 업무 | 건수 |", "|---|---|---:|"]
        for (gt_bf, top1_bf), count in sorted(err["cross_flow"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {gt_bf} | {top1_bf} | {count} |")

    if err["worst"]:
        lines += ["", "### 8-5. 대표 실패 사례 (gold가 top-10에도 없음)", ""]
        for row in err["worst"]:
            lines += [f"- **[{row['business_function']}] {row['id']}** — {row['question']}",
                     f"  - gold: {_format_ids(row['gold_chunk_ids'])}",
                     f"  - top-3: {_format_ids(row['retrieved_chunk_ids'][:3])}"]

    lines += ["", "## 9. 개선 우선순위", ""]
    priorities = []
    for domain, count in sorted(err["by_domain"].items(), key=lambda kv: -kv[1])[:3]:
        total = domain_metrics[domain]["n_total"]
        priorities.append(f"'{domain}' 업무 — 미적중 {count}/{total}건"
                          f"({count / total * 100 if total else 0:.1f}%)로 가장 취약함")
    and_m = relation_metrics.get("and")
    if and_m and and_m["hit@3"] < chunk["hit@3"]:
        priorities.append(f"`and` relation(다중 근거 필요) Hit@3={and_m['hit@3']:.3f}로 "
                          f"전체 평균({chunk['hit@3']:.3f})보다 낮음 — 다중 청크 회수 전략 점검 필요")
    if err["intruders"]:
        top_intruder = max(err["intruders"].items(), key=lambda kv: kv[1])
        priorities.append(f"`{top_intruder[0]}` 청크가 미적중 {top_intruder[1]}건에서 top-3를 잠식 "
                          f"— 업무 분류/부스트 파라미터 재검토 대상 1순위")
    lines += [f"{i}. {p}" for i, p in enumerate(priorities, 1)] or ["_미적중 사례 없음._"]

    if doc is not None:
        lines += ["", "## 10. 참고", "",
                  "기존 document-level(같은 `parent_doc_id`면 적중) 판정과 비교한 거품(percentage points):", "",
                  "| 지표 | chunk-level | document-level | 문서 단위 거품 |",
                  "|---|---:|---:|---:|"]
        for key in ("hit@1", "hit@3", "hit@5", "recall@10", "mrr"):
            bubble = (doc[key] - chunk[key]) * 100
            lines.append(f"| {key} | {chunk[key]:.3f} | {doc[key]:.3f} | {bubble:+.1f}pp |")

    lines += _anchor_report_lines(result)

    lines += ["", "## 부록. 문항별 라벨과 검색 청크", "",
              "| id | answerable | relation | gold chunk IDs | Top-10 retrieved chunk IDs | chunk Hit@1/3/5/10 | doc Hit@1/3/5/10 |",
              "|---|---|---|---|---|---|---|"]
    for row in rows:
        if row["excluded"]:
            chunk_hits = doc_hits = "excluded"
        else:
            chunk_hits = "/".join(str(int(row["chunk"][f"hit@{k}"])) for k in KS)
            doc_hits = ("/".join(str(int(row["doc"][f"hit@{k}"])) for k in KS)
                        if "doc" in row else "-")
        lines.append("| {id} | {answerable} | {relation} | {gold} | {retrieved} | {chunk_hits} | {doc_hits} |".format(
            id=row["id"], answerable=str(row["answerable"]).lower(), relation=row["chunk_relation"],
            gold=_format_ids(row["gold_chunk_ids"]),
            retrieved=_format_ids(row["retrieved_chunk_ids"][:RETRIEVAL_DEPTH]),
            chunk_hits=chunk_hits, doc_hits=doc_hits))

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_group(title: str, rows: list[tuple[str, str]]) -> None:
    """제목 아래 key: value를 한 줄씩 나열하고, 라벨 너비를 맞춘 표 느낌으로 출력한다."""
    print(f"[{title}]")
    label_width = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"  {label.ljust(label_width)} : {value}")
    print()  # 다음 그룹과 빈 줄 하나(연속 줄바꿈 두 번) 간격.


def _anchor_report_lines(result: dict) -> list[str]:
    """앵커텍스트 판정 결과 — chunk_id 판정과 나란히 놓아 전환 효과를 드러낸다."""
    anchor = result.get("anchor_level")
    if not anchor:
        return []
    # Δ는 '앵커 채점 대상 문항'이라는 동일 모집단 위에서 낸다. 전체 n_evaluated 기준
    # chunk_id 수치와 비교하면 라벨 결측분이 판정 차이로 섞인다.
    base_all = result["chunk_on_anchor_subset"]
    chunk = result["chunk_level"]
    n_scored = anchor["n_scored"] or 1
    lines = ["", "## 앵커텍스트(골드텍스트) 판정", "",
             "적중 = top-k 청크가 `gt_anchors`를 포함하는지로 판정(공백 정규화 후 부분문자열).",
             "정답 내용이 여러 청크에 정당히 존재해도 적중으로 잡히며, 재청킹으로 `chunk_id`가",
             "밀려도 판정이 유지된다. 출처: `docs/앵커텍스트_정답라벨링_파이프라인.md` ⑤.", "",
             "- `single`/`or`: 앵커 하나라도 발견되면 적중",
             "- `and`: 앵커 **전부** 발견 + 앵커 없는 gold 청크 **전부** top-k에 존재",
             "- 앵커가 덮지 않는 gold 청크는 `chunk_id`로 판정한다(하이브리드). 앵커를 지어내지",
             "  않으면서 relation 의미를 지키는 방식이며, 라벨이 채워질수록 id 의존분이 줄어든다.", "",
             f"- 채점 {anchor['n_scored']}문항 "
             f"(앵커만으로 판정 {anchor['n_full_anchor']} · chunk_id 폴백 섞임 {anchor['n_id_fallback']}) "
             f"· 근거 없음 {anchor['n_missing_span']}문항(분모 제외)",
             f"- **id 의존도: {anchor['n_id_fallback'] / n_scored:.1%}** — 이 비율이 0에 가까울수록 "
             f"수치가 순수 앵커 판정이다. 잔여 라벨 작업량의 지표이기도 하다.",
             f"- 아래 표의 두 열과 Δ는 모두 **앵커 채점 대상 {anchor['n_scored']}문항** 기준이다"
             f" (참고: 전체 {chunk['n_evaluated']}문항 기준 chunk_id hit@5 = {chunk['hit@5']:.3f}).", "",
             "| 지표 | chunk_id 기준 | 앵커텍스트 기준 | Δ |", "|---|---:|---:|---:|"]
    for key in ("hit@1", "hit@3", "hit@5", "hit@10", "mrr"):
        lines.append(f"| {key} | {base_all[key]:.3f} | {anchor[key]:.3f} | "
                     f"{anchor[key] - base_all[key]:+.3f} |")
    rel = result.get("anchor_relation_metrics") or {}
    base_rel = result.get("chunk_on_anchor_subset_relation") or {}
    if rel:
        lines += ["", "### relation별 hit@5", "",
                  "| relation | 문항 | chunk_id | 앵커텍스트 | Δ |", "|---|---:|---:|---:|---:|"]
        for name, m in sorted(rel.items()):
            base = base_rel.get(name, {}).get("hit@5", 0.0)
            lines.append(f"| {name} | {m['n_scored']} | {base:.3f} | {m['hit@5']:.3f} | "
                         f"{m['hit@5'] - base:+.3f} |")
        lines += ["",
                  "`and`는 ALL 조건(앵커 전부 + 앵커 없는 gold 전부)으로 판정한다. 앵커 라벨이",
                  "부족한 만큼 chunk_id 판정에 수렴하므로, 위 'id 의존도'와 함께 읽을 것 —",
                  "라벨을 채우면 이 수치가 재청킹에도 견디는 값으로 바뀐다.",
                  "잔여 라벨 작업량은 `promote_gt_anchors.py`가 gold 청크 단위로 보고한다."]
    return lines


def _print_summary(result: dict, report_path: Path) -> None:
    """콘솔 요약을 항목마다 줄을 나누고, 그룹 사이는 빈 줄로 구분해 가독성 있게 출력한다."""
    m = result["chunk_level"]
    anchor = result.get("anchor_level")
    print("=== KDIC v3 평가 결과 ===")
    print()
    _print_group("데이터", [
        ("n_total", str(m["n_total"])),
        ("n_evaluated", str(m["n_evaluated"])),
        ("n_excluded", str(m["n_excluded_unanswerable"])),
        ("n_inconsistent", str(m["n_inconsistent"])),
        ("score_mode", result.get("score_mode", "chunk_id")),
    ])
    if anchor:
        base = result["chunk_on_anchor_subset"]   # 동일 모집단(앵커 채점 대상) baseline
        _print_group(f"Hit@K — chunk_id vs 앵커텍스트 (앵커 채점 {anchor['n_scored']}문항 기준)", [
            (f"Hit@{k}", f"{base[f'hit@{k}']:.3f}  ->  {anchor[f'hit@{k}']:.3f}"
                         f"  ({anchor[f'hit@{k}'] - base[f'hit@{k}']:+.3f})")
            for k in (1, 3, 5, 10)
        ] + [("MRR@10", f"{base['mrr']:.3f}  ->  {anchor['mrr']:.3f}"
                        f"  ({anchor['mrr'] - base['mrr']:+.3f})"),
             ("앵커 채점/결측", f"{anchor['n_scored']} / {anchor['n_missing_span']}"),
             ("순수앵커/id폴백", f"{anchor['n_full_anchor']} / {anchor['n_id_fallback']}"
                            f"  (id 의존도 {anchor['n_id_fallback'] / (anchor['n_scored'] or 1):.1%})")])
    if result.get("score_mode") != "anchor":
        # anchor 모드에서는 위 비교 그룹이 이미 chunk_id 열을 담고 있어 중복이다.
        _print_group("Hit@K (chunk_id 기준)", [
            ("Hit@1", f"{m['hit@1']:.3f}"),
            ("Hit@3", f"{m['hit@3']:.3f}"),
            ("Hit@5", f"{m['hit@5']:.3f}"),
            ("Hit@10", f"{m['hit@10']:.3f}"),
        ])
    _print_group("MacroRecall", [
        ("@3", f"{m['macro_recall@3']:.3f}"),
        ("@5", f"{m['macro_recall@5']:.3f}"),
        ("@10", f"{m['macro_recall@10']:.3f}  (micro@10={m['recall@10']:.3f})"),
        ("@30", f"{m['macro_recall@30']:.3f}"),
        ("@50", f"{m['macro_recall@50']:.3f}  <- 리랭커 천장"),
    ])
    _print_group("MRR", [("MRR@10", f"{m['mrr']:.3f}")])
    print(f"report -> {report_path}")


def main() -> None:
    data_dir = _default_data_dir()
    parser = argparse.ArgumentParser(description="KDIC chunk-level retrieval evaluation v3")
    parser.add_argument("--gt", default=data_dir / "gt_schema_v6.jsonl", type=Path)
    parser.add_argument("--chunks", default=data_dir / "chunks.jsonl", type=Path)
    parser.add_argument("--retrieved", type=Path,
                        help="id, retrieved_chunk_ids JSONL. 생략하면 현재 rag.Searcher로 검색한다.")
    parser.add_argument("--mode", default="hybrid_bf", help="--retrieved 생략 시 rag 검색 mode")
    parser.add_argument("--report", default=data_dir / "eval_anchor_v3_report.md", type=Path)
    parser.add_argument("--score", default="both", choices=SCORE_MODES,
                        help="적중 판정 기준. chunk_id=gold ID 완전일치만 산출 · "
                             "anchor=앵커텍스트를 주 기준으로 보고 · both=둘 다 병기(기본). "
                             "anchor/both는 산출 지표가 같고 콘솔 표시만 다르다 — "
                             "chunk_id 지표는 오류 분석·감사표에 필요해 항상 계산된다.")
    args = parser.parse_args()

    gt_data = _load_jsonl(args.gt)
    if args.retrieved:
        retrieved_data = _load_jsonl(args.retrieved)
        retrieval_source = f"외부 결과 `{args.retrieved}` (검색 미실행)"
    else:
        retrieved_data = _search_results(gt_data, args.mode, data_dir)
        retrieval_source = f"`rag.Searcher.search(question, k=10, mode={args.mode!r})`"
    chunk_metadata = _load_jsonl(args.chunks)
    result = evaluate_retrieval(gt_data, retrieved_data, chunk_metadata, score=args.score)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_report(result, args.report, args.gt, retrieval_source, chunk_metadata)
    _print_summary(result, args.report)


if __name__ == "__main__":
    main()
