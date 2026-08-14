"""KDIC RAG v3 청크 단위 검색 평가.

기존 ``eval.py``의 parent_doc_id 기반 평가는 변경하지 않는다. 이 모듈은
GT의 gold chunk와 검색된 chunk_id를 직접 비교하는 별도 평가기다.

사용 예:
    cd crawler
    python eval_anchor_v3.py --retrieved data/retrieved.jsonl
    python eval_anchor_v3.py --mode hybrid_bf
    python eval_anchor_v3.py --mode hybrid_bf_rerank --limit 30   # 속도 측정용 스모크 테스트

``--retrieved``를 주면 검색을 실행하지 않고 JSONL의 결과를 그대로 평가한다.
각 결과 행은 ``id``와 순위순 ``retrieved_chunk_ids``를 가져야 한다.

``--limit N``을 주면 GT의 처음 N건만 평가한다 — 느린 모드(리랭커 등) 속도 확인용이며,
업무가 뒤섞여 있지 않은 순서라 지표 자체는 대표성이 없다(전체 평가로 재확인할 것).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


KS = (1, 3, 5, 10)
RECALL_KS = (3, 5, 10)
RETRIEVAL_DEPTH = 10


def _default_data_dir() -> Path:
    """스크립트 위치에서 GT v7이 있는 data 폴더를 찾는다."""
    for parent in Path(__file__).resolve().parents:
        data_dir = parent / "data"
        if (data_dir / "gt_relabeled_v7.jsonl").is_file():
            return data_dir
    raise FileNotFoundError("gt_relabeled_v7.jsonl을 포함한 data 폴더를 찾을 수 없습니다.")


def _get_gt_chunk_ids(item: dict) -> list[str]:
    """새 ``gt_chunk_ids`` 우선, 비어 있으면 구형 단일 gold를 사용한다."""
    chunk_ids = item.get("gt_chunk_ids")
    if chunk_ids:
        if isinstance(chunk_ids, str):
            chunk_ids = [chunk_ids]
        return list(dict.fromkeys(chunk_ids))
    chunk_id = item.get("gt_chunk_id")
    return [chunk_id] if chunk_id else []


def _get_relation(item: dict) -> str:
    """null/누락 relation은 확정 스키마의 단일 근거 레코드로 처리한다."""
    relation = item.get("chunk_relation") or "single"
    if relation not in {"single", "or", "and"}:
        raise ValueError(f"{item.get('id')}: unsupported chunk_relation={relation!r}")
    return relation


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
    return _recall_at_k(gold_ids, retrieved_ids, RETRIEVAL_DEPTH)


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
        "mrr": _reciprocal_rank(gold_ids, retrieved_ids[:RETRIEVAL_DEPTH], relation),
    }


def _add_metrics(metrics: dict, values: dict, gold_ids: list[str]) -> None:
    """문항 하나의 결과를 집계 메트릭에 더한다."""
    metrics["n_evaluated"] += 1
    unique_gold_count = len(set(gold_ids))
    metrics["total_gold"] += unique_gold_count
    for key in ("hit@1", "hit@3", "hit@5", "hit@10", "mrr"):
        metrics[key] += values[key]
    for k in RECALL_KS:
        metrics[f"recalled_gold@{k}"] += values[f"recalled_gold@{k}"]
        metrics[f"macro_recall@{k}"] += values[f"recall@{k}"]


def _finalize_metrics(metrics: dict) -> dict:
    """Hit/MRR/MacroRecall은 문항 기준, (micro)Recall은 gold chunk occurrence 기준으로 정규화한다."""
    if metrics["n_evaluated"]:
        denominator = metrics["n_evaluated"]
        for key in ("hit@1", "hit@3", "hit@5", "hit@10", "mrr"):
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
) -> dict:
    """GT와 검색 결과를 결정론적으로 평가한다.

    answerable=false는 모든 Hit@K, Recall@K, MRR의 분모에서 제외된다.
    Recall은 문항 평균이 아니라 전체 gold chunk 기준으로 계산한다.
    ``chunk_metadata``를 주면 기존 방식과 같은 문서 단위 참고 지표도 함께 계산한다.
    """
    retrieved_by_id: dict[str, list[str]] = {}
    for item in retrieved_data:
        item_id = item["id"]
        if item_id in retrieved_by_id:
            raise ValueError(f"duplicate retrieved result id: {item_id}")
        retrieved_by_id[item_id] = item.get("retrieved_chunk_ids", [])

    chunk_to_doc = {item["chunk_id"]: item["parent_doc_id"]
                    for item in (chunk_metadata or [])}
    chunk_metrics = _empty_metrics()
    doc_metrics = _empty_metrics() if chunk_metadata is not None else None
    relation_metrics: dict[str, dict] = {}
    domain_metrics: dict[str, dict] = {}
    audit_rows = []

    for gt_item in gt_data:
        item_id = gt_item["id"]
        gold_ids = _get_gt_chunk_ids(gt_item)
        relation = _get_relation(gt_item)
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
            audit_rows.append({"id": item_id, "answerable": False, "chunk_relation": relation,
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
        for key in ("hit@1", "hit@3", "hit@5", "hit@10", "mrr"):
            chunk_metrics[key] += values[key]
        for k in RECALL_KS:
            chunk_metrics[f"recalled_gold@{k}"] += values[f"recalled_gold@{k}"]
            chunk_metrics[f"macro_recall@{k}"] += values[f"recall@{k}"]

        relation_metrics.setdefault(relation, _empty_metrics())
        relation_metrics[relation]["n_total"] += 1
        _add_metrics(relation_metrics[relation], values, gold_ids)

        domain = gt_item.get("business_function") or "(unknown)"
        domain_metrics.setdefault(domain, _empty_metrics())
        domain_metrics[domain]["n_total"] += 1
        _add_metrics(domain_metrics[domain], values, gold_ids)

        row = {"id": item_id, "answerable": True, "chunk_relation": relation,
               "business_function": domain, "question": gt_item.get("question", ""),
               "gold_chunk_ids": gold_ids, "retrieved_chunk_ids": retrieved_ids,
               "excluded": False, "chunk": values}
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
        "relation_metrics": relation_metrics,
        "domain_metrics": domain_metrics,
        "gold_coverage": gold_coverage,
        "audit_rows": audit_rows,
    }


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _search_results(gt_data: Iterable[dict], mode: str, data_dir: Path) -> list[dict]:
    """기존 검색 구현을 그대로 호출하며 알고리즘이나 라벨은 변경하지 않는다."""
    import rag

    searcher = rag.Searcher(index_dir=str(data_dir / "index"))
    return [{"id": item["id"],
             "retrieved_chunk_ids": [hit["chunk_id"] for hit in searcher.search(
                 item["question"], k=RETRIEVAL_DEPTH, mode=mode)]}
            for item in gt_data]


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
              "| Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |",
              "|---:|---:|---:|---:|---:|",
              f"| {chunk['hit@1']:.3f} | {chunk['hit@3']:.3f} | {chunk['hit@5']:.3f} | {chunk['hit@10']:.3f} | {chunk['mrr']:.3f} |",
              "",
              "| MacroRecall@3 | MacroRecall@5 | MacroRecall@10 |",
              "|---:|---:|---:|",
              f"| {chunk['macro_recall@3']:.3f} | {chunk['macro_recall@5']:.3f} | {chunk['macro_recall@10']:.3f} |",
              "",
              f"- (참고) Micro Recall@10: {chunk['recall@10']:.3f} · gold 총계(occurrence): "
              f"{gold_coverage['gold_chunk_total']} · 미회수(@10): {gold_coverage['missing_gold@10']}", "",
              "## 6. Relation별 결과", "",
              "| relation | 문항수 | Hit@1 | Hit@3 | Hit@5 | MacroRecall@10 | MRR |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for rel in ("single", "or", "and"):
        m = relation_metrics.get(rel)
        if m:
            lines.append(f"| {rel} | {m['n_total']} | {m['hit@1']:.3f} | {m['hit@3']:.3f} | "
                        f"{m['hit@5']:.3f} | {m['macro_recall@10']:.3f} | {m['mrr']:.3f} |")

    lines += ["", "## 7. 도메인별 결과", "",
              "| 업무 | 문항수 | Hit@1 | Hit@3 | Hit@5 | MacroRecall@10 | MRR |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for domain, m in sorted(domain_metrics.items(), key=lambda kv: -kv[1]["n_total"]):
        lines.append(f"| {domain} | {m['n_total']} | {m['hit@1']:.3f} | {m['hit@3']:.3f} | "
                    f"{m['hit@5']:.3f} | {m['macro_recall@10']:.3f} | {m['mrr']:.3f} |")

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


def _print_summary(result: dict, report_path: Path) -> None:
    """콘솔 요약을 항목마다 줄을 나누고, 그룹 사이는 빈 줄로 구분해 가독성 있게 출력한다."""
    m = result["chunk_level"]
    print("=== KDIC v3 평가 결과 ===")
    print()
    _print_group("데이터", [
        ("n_total", str(m["n_total"])),
        ("n_evaluated", str(m["n_evaluated"])),
        ("n_excluded", str(m["n_excluded_unanswerable"])),
        ("n_inconsistent", str(m["n_inconsistent"])),
    ])
    _print_group("Hit@K", [
        ("Hit@1", f"{m['hit@1']:.3f}"),
        ("Hit@3", f"{m['hit@3']:.3f}"),
        ("Hit@5", f"{m['hit@5']:.3f}"),
        ("Hit@10", f"{m['hit@10']:.3f}"),
    ])
    _print_group("MacroRecall", [
        ("@3", f"{m['macro_recall@3']:.3f}"),
        ("@5", f"{m['macro_recall@5']:.3f}"),
        ("@10", f"{m['macro_recall@10']:.3f}  (micro@10={m['recall@10']:.3f})"),
    ])
    _print_group("MRR", [("MRR@10", f"{m['mrr']:.3f}")])
    print(f"report -> {report_path}")


def main() -> None:
    data_dir = _default_data_dir()
    parser = argparse.ArgumentParser(description="KDIC chunk-level retrieval evaluation v3")
    parser.add_argument("--gt", default=data_dir / "gt_relabeled_v7.jsonl", type=Path)
    parser.add_argument("--chunks", default=data_dir / "chunks.jsonl", type=Path)
    parser.add_argument("--retrieved", type=Path,
                        help="id, retrieved_chunk_ids JSONL. 생략하면 현재 rag.Searcher로 검색한다.")
    parser.add_argument("--mode", default="hybrid_bf", help="--retrieved 생략 시 rag 검색 mode")
    parser.add_argument("--report", default=data_dir / "eval_anchor_v3_report.md", type=Path)
    parser.add_argument("--limit", type=int, default=0,
                        help="처음 N건만 평가(스모크 테스트/속도 측정용, 대표성 있는 지표가 아님). 0이면 전체.")
    args = parser.parse_args()

    gt_data = _load_jsonl(args.gt)
    if args.limit:
        gt_data = gt_data[: args.limit]
    if args.retrieved:
        retrieved_data = _load_jsonl(args.retrieved)
        retrieval_source = f"외부 결과 `{args.retrieved}` (검색 미실행)"
    else:
        retrieved_data = _search_results(gt_data, args.mode, data_dir)
        retrieval_source = f"`rag.Searcher.search(question, k=10, mode={args.mode!r})`"
    chunk_metadata = _load_jsonl(args.chunks)
    result = evaluate_retrieval(gt_data, retrieved_data, chunk_metadata)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_report(result, args.report, args.gt, retrieval_source, chunk_metadata)
    _print_summary(result, args.report)


if __name__ == "__main__":
    main()
