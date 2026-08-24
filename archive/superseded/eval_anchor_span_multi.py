"""KDIC RAG 정답 텍스트(span) 기준 검색 평가 — and/or relation의 다중 span 지원판.

``eval_anchor_span.py``는 문항당 span이 하나(``gt_anchor_span``)뿐이라는
한계 때문에, ``chunk_relation="and"``에서 주 span 이외의 필수 청크는 여전히
chunk_id로만 판정했다. 이 모듈은 ``build_gt_natural450_multi.py``가 만든
``gt_anchor_spans``(청크별 span 리스트, gt_chunk_ids와 같은 순서)를 사용해
and/or 모두 진짜 텍스트 기준으로 채점한다.

판정 규칙:
  - relation == "and": gt_anchor_spans의 모든 span이 각각(서로 다른 검색
    결과 안에서든 같은 결과 안에서든 상관없이) top-k 안에서 발견되어야
    hit이다.
  - 그 외(single/or/null 등): 하나라도 top-k 안에서 발견되면 hit이다(ANY).
  - gt_anchor_spans가 리스트가 아니라 문자열이면(= and/or가 아닌 문항)
    원소 1개짜리 리스트로 취급한다. 필드 자체가 없으면 구형
    ``gt_anchor_span``으로 폴백한다.

한계:
  - and 문항의 "주 span 이외" 청크 span은 사람이 새로 라벨링한 것이 아니라
    build_gt_natural450_multi.py가 자동으로 채운 값이다(원문과 완전히
    같은 문구가 있으면 재사용, 없으면 청크 전체 텍스트로 대체). 청크
    전체를 span으로 쓴 경우, 리청킹으로 그 청크가 더 잘게 쪼개지면 새
    청크 어느 것도 원래 청크 "전체"를 포함하지 못해 다시 miss가 될 수
    있다 — chunk_id 직접비교보다는 낫지만 완전한 해법은 아니다.
  - evidence_type="inferable"인 일부 문항은 애초에 원문 그대로 인용 가능한
    정답 텍스트가 없어(계산·추론이 필요) gt_anchor_span 자체가 null이다.
    이런 문항은 검색 품질과 무관하게 항상 miss로 집계된다 — "span 없음"
    섹션에 별도로 모아 misses(진짜 검색 실패)와 섞이지 않게 한다.
  - retrieved_chunk_id -> 본문 조회는 여전히 ``--chunks`` 스냅샷에
    의존한다(``n_missing_chunk_text``로 확인).

사용 예:
    cd crawler
    python eval_anchor_span_multi.py --retrieved data/retrieved.jsonl
    python eval_anchor_span_multi.py --mode hybrid_bf
    python eval_anchor_span_multi.py --mode hybrid_bf --limit 30
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
    for parent in Path(__file__).resolve().parents:
        data_dir = parent / "data"
        if (data_dir / "chunks.jsonl").is_file():
            return data_dir
    raise FileNotFoundError("chunks.jsonl을 포함한 data 폴더를 찾을 수 없습니다.")


def _norm(text: str | None) -> str:
    """공백 차이를 무시하는 정규화. build_gt_v3.py의 norm()과 동일한 규칙이다."""
    return "".join((text or "").split())


def _get_gt_spans(item: dict) -> list[str]:
    """gt_anchor_spans(리스트/문자열) 우선, 없으면 구형 gt_anchor_span으로 폴백한다."""
    spans = item.get("gt_anchor_spans")
    if spans is None:
        spans = item.get("gt_anchor_span")
    if spans is None:
        return []
    if isinstance(spans, str):
        return [spans] if spans else []
    return [s for s in spans if s]


def _get_gt_chunk_ids(item: dict) -> list[str]:
    chunk_ids = item.get("gt_chunk_ids")
    if chunk_ids:
        if isinstance(chunk_ids, str):
            chunk_ids = [chunk_ids]
        return list(dict.fromkeys(chunk_ids))
    chunk_id = item.get("gt_chunk_id")
    return [chunk_id] if chunk_id else []


def _relation_mode(item: dict) -> str:
    """'and'만 다중 근거 결합(ALL)으로, 나머지는 전부 ANY로 취급한다."""
    return "and" if item.get("chunk_relation") == "and" else "any"


def _rank_of_span_hit(span_norm: str, retrieved_ids: list[str],
                       chunk_text: dict[str, str], depth: int) -> int:
    """span이 처음 발견된 순위(1-base)를 반환한다. 못 찾으면 0."""
    if not span_norm:
        return 0
    for rank, chunk_id in enumerate(retrieved_ids[:depth], 1):
        text = chunk_text.get(chunk_id)
        if text and span_norm in text:
            return rank
    return 0


def _id_hit_at_k(gold_ids: list[str], retrieved_ids: list[str], mode: str, k: int) -> bool:
    """비교용 참고 지표: chunk_id 직접비교(기존 eval_anchor_v3.py) 방식."""
    if not gold_ids:
        return False
    top_k = set(retrieved_ids[:k])
    if mode == "and":
        return set(gold_ids).issubset(top_k)
    return bool(set(gold_ids) & top_k)


def _rank_of_id_hit(chunk_id: str, retrieved_ids: list[str], depth: int) -> int:
    """chunk_id가 처음 나온 순위(1-base). 못 찾으면 0."""
    for rank, cid in enumerate(retrieved_ids[:depth], 1):
        if cid == chunk_id:
            return rank
    return 0


def _item_metrics(item: dict, retrieved_ids: list[str], chunk_text: dict[str, str],
                  id_fallback: bool = False) -> dict:
    spans_norm = [_norm(s) for s in _get_gt_spans(item)]
    spans_norm = [s for s in spans_norm if s]
    gold_ids = _get_gt_chunk_ids(item)
    mode = _relation_mode(item)

    ranks = [_rank_of_span_hit(s, retrieved_ids, chunk_text, RETRIEVAL_DEPTH) for s in spans_norm]

    if id_fallback and not spans_norm and gold_ids:
        # evidence_type=inferable(계산·추론형)은 정답 문장이 원문에 없어 스팬이 구조적으로
        # 비어 있다. 스팬 0개를 그대로 두면 무조건 미적중이 되는데 이는 검색 실패가 아니라
        # 측정 결함이므로, 이때만 gold chunk_id 등장 여부로 대체 판정한다(팀 하이브리드 규약).
        ranks = [_rank_of_id_hit(cid, retrieved_ids, RETRIEVAL_DEPTH) for cid in gold_ids]

    found_ranks = [r for r in ranks if r > 0]

    hits = {}
    for k in KS:
        found_at_k = [r for r in ranks if 0 < r <= k]
        if mode == "and":
            hits[f"hit@{k}"] = bool(ranks) and len(found_at_k) == len(ranks)
        else:
            hits[f"hit@{k}"] = bool(found_at_k)

    if mode == "and":
        # 모든 span이 등장해야 만족되므로, 그 시점은 "가장 늦게 처음 나온 span의 순위"다.
        mrr = 1.0 / max(ranks) if ranks and all(r > 0 for r in ranks) else 0.0
    else:
        mrr = 1.0 / min(found_ranks) if found_ranks else 0.0

    recall = {f"recall@{k}": (len([r for r in ranks if 0 < r <= k]) / len(ranks) if ranks else 0.0)
              for k in RECALL_KS}

    id_hits = {f"id_hit@{k}": _id_hit_at_k(gold_ids, retrieved_ids, mode, k) for k in KS}

    return {**hits, "mrr": mrr, **recall, "ranks": ranks, **id_hits,
            "gold_ids": gold_ids, "relation_mode": mode,
            "n_spans": len(spans_norm), "n_spans_found": len(found_ranks)}


def _empty_metrics() -> dict:
    return {
        "n_total": 0, "n_evaluated": 0, "n_excluded_unanswerable": 0,
        "n_inconsistent": 0, "n_no_span": 0, "n_missing_chunk_text": 0,
        **{f"hit@{k}": 0.0 for k in KS},
        **{f"id_hit@{k}": 0.0 for k in KS},
        **{f"recalled@{k}": 0 for k in RECALL_KS},
        "total_spans": 0,
        **{f"recall@{k}": 0.0 for k in RECALL_KS},
        **{f"macro_recall@{k}": 0.0 for k in RECALL_KS},
        "mrr": 0.0,
    }


def _add_metrics(metrics: dict, values: dict) -> None:
    metrics["n_evaluated"] += 1
    metrics["total_spans"] += values["n_spans"]
    for k in KS:
        metrics[f"hit@{k}"] += values[f"hit@{k}"]
        metrics[f"id_hit@{k}"] += values[f"id_hit@{k}"]
    metrics["mrr"] += values["mrr"]
    for k in RECALL_KS:
        recovered = round(values[f"recall@{k}"] * values["n_spans"])
        metrics[f"recalled@{k}"] += recovered
        metrics[f"macro_recall@{k}"] += values[f"recall@{k}"]
    if values["n_spans"] == 0:
        metrics["n_no_span"] += 1


def _finalize_metrics(metrics: dict) -> dict:
    if metrics["n_evaluated"]:
        denom = metrics["n_evaluated"]
        for k in KS:
            metrics[f"hit@{k}"] /= denom
            metrics[f"id_hit@{k}"] /= denom
        metrics["mrr"] /= denom
        for k in RECALL_KS:
            metrics[f"macro_recall@{k}"] /= denom
    if metrics["total_spans"]:
        for k in RECALL_KS:
            metrics[f"recall@{k}"] = metrics[f"recalled@{k}"] / metrics["total_spans"]
    return metrics


def evaluate_span_retrieval(gt_data: Iterable[dict], retrieved_data: Iterable[dict],
                             chunk_metadata: Iterable[dict], id_fallback: bool = False) -> dict:
    """GT의 gt_anchor_spans(청크별 span 리스트)와 검색된 청크 본문을 비교해 채점한다.

    answerable=false는 분모에서 제외한다. chunk_metadata는 chunk 본문 조회(채점용)와
    business_function 조회(오류 분석용)에 함께 쓴다.
    """
    retrieved_by_id: dict[str, list[str]] = {}
    for item in retrieved_data:
        item_id = item["id"]
        if item_id in retrieved_by_id:
            raise ValueError(f"duplicate retrieved result id: {item_id}")
        retrieved_by_id[item_id] = item.get("retrieved_chunk_ids", [])

    chunk_metadata = list(chunk_metadata)
    chunk_text: dict[str, str] = {c["chunk_id"]: _norm(c.get("text", "")) for c in chunk_metadata}

    metrics = _empty_metrics()
    relation_metrics: dict[str, dict] = {}
    domain_metrics: dict[str, dict] = {}
    audit_rows = []

    for gt_item in gt_data:
        item_id = gt_item["id"]
        retrieved_ids = retrieved_by_id.get(item_id, [])
        answerable = gt_item.get("answerable") is True
        metrics["n_total"] += 1

        if not answerable:
            metrics["n_excluded_unanswerable"] += 1
            if _get_gt_spans(gt_item):
                metrics["n_inconsistent"] += 1
            audit_rows.append({"id": item_id, "answerable": False, "excluded": True})
            continue

        missing_text_ids = [cid for cid in retrieved_ids[:RETRIEVAL_DEPTH] if cid not in chunk_text]
        metrics["n_missing_chunk_text"] += len(missing_text_ids)

        values = _item_metrics(gt_item, retrieved_ids, chunk_text, id_fallback)
        if not values["gold_ids"]:
            metrics["n_inconsistent"] += 1
        _add_metrics(metrics, values)

        relation = gt_item.get("chunk_relation") or "single"
        relation_metrics.setdefault(relation, _empty_metrics())
        relation_metrics[relation]["n_total"] += 1
        _add_metrics(relation_metrics[relation], values)

        domain = gt_item.get("business_function") or "(unknown)"
        domain_metrics.setdefault(domain, _empty_metrics())
        domain_metrics[domain]["n_total"] += 1
        _add_metrics(domain_metrics[domain], values)

        audit_rows.append({
            "id": item_id, "answerable": True, "excluded": False,
            "chunk_relation": relation, "relation_mode": values["relation_mode"],
            "business_function": domain, "question": gt_item.get("question", ""),
            "evidence_type": gt_item.get("evidence_type"),
            "gold_chunk_ids": values["gold_ids"], "retrieved_chunk_ids": retrieved_ids,
            "span_ranks": values["ranks"], "no_span": values["n_spans"] == 0,
            "n_spans": values["n_spans"], "n_spans_found": values["n_spans_found"],
            "missing_text_ids": missing_text_ids,
            "hit": {f"hit@{k}": values[f"hit@{k}"] for k in KS},
            "id_hit": {f"id_hit@{k}": values[f"id_hit@{k}"] for k in KS},
            "recall": {f"recall@{k}": values[f"recall@{k}"] for k in RECALL_KS},
            "mrr": values["mrr"],
        })

    _finalize_metrics(metrics)
    for m in relation_metrics.values():
        _finalize_metrics(m)
    for m in domain_metrics.values():
        _finalize_metrics(m)

    return {"overall": metrics, "relation_metrics": relation_metrics,
            "domain_metrics": domain_metrics, "audit_rows": audit_rows}


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


def _error_analysis(rows: list[dict], chunk_to_bf: dict[str, str]) -> dict:
    """미적중(top-3 밖) 문항의 원인·혼입 패턴을 집계한다.

    span 자체가 없는 문항(no_span)은 검색 품질과 무관하게 항상 miss이므로
    여기서 제외하고 별도 섹션(no_span_rows)으로 다룬다.
    """
    misses = [row for row in rows if not row["excluded"] and not row["no_span"]
              and not row["hit"]["hit@3"]]
    no_span_rows = [row for row in rows if not row["excluded"] and row["no_span"]]
    by_domain: dict[str, int] = {}
    for row in misses:
        by_domain[row["business_function"]] = by_domain.get(row["business_function"], 0) + 1

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

    worst = [row for row in misses if not row["hit"]["hit@10"]][:8]
    return {"misses": misses, "no_span_rows": no_span_rows, "by_domain": by_domain,
            "cause": cause, "intruders": intruders, "cross_flow": cross_flow, "worst": worst}


def write_report(result: dict, output_path: Path, gt_path: Path, retrieval_source: str,
                  chunk_metadata: list[dict]) -> None:
    """eval_anchor_v3_report.md와 같은 구성(개요/데이터/파라미터/지표/결과/오류분석/부록)의 span판 리포트."""
    m = result["overall"]
    relation_metrics = result["relation_metrics"]
    domain_metrics = result["domain_metrics"]
    rows = result["audit_rows"]
    chunk_to_bf = {c["chunk_id"]: c.get("business_function", "(unknown)") for c in chunk_metadata}

    try:
        import rag
        retriever_desc = (f"RRF(k={rag.RRF_K}, alpha={rag.RRF_ALPHA}) + "
                          f"BF_MODE={rag.BF_MODE}(cap={rag.BF_DOC_CAP}, boost={rag.BF_BOOST}, "
                          f"facet={rag.FACET_BOOST})")
        embedding_desc = rag.MODEL_NAME
    except Exception:
        retriever_desc = "정보 없음(외부 검색 결과 사용)"
        embedding_desc = "정보 없음(외부 검색 결과 사용)"

    lines = ["# KDIC 검색 평가 리포트 — span 기준(다중 span, and/or 지원)", "",
              "## 1. 개요", "",
              "정답 텍스트(`gt_anchor_spans`)가 검색된 청크 본문에 포함되는지로 hit을 판정한다.",
              "gold `chunk_id`를 직접 비교하는 기존 `eval_anchor_v3.py`와 달리, 청크 재분할로",
              "chunk_id가 바뀌어도 내용이 같으면 hit으로 잡힌다. `and`는 필요한 span 전부,",
              "`or`/`single`은 하나만 발견되면 hit이다. `id_hit@k`는 기존 chunk_id 직접비교",
              "결과를 참고용으로 함께 계산한 것이다.", "",
              "## 2. 평가 대상 / 데이터 구성", "",
              f"- GT 라벨: `{gt_path}`",
              f"- 전체 {m['n_total']}건 · 평가 대상(answerable=true) {m['n_evaluated']}건 · "
              f"제외(answerable=false) {m['n_excluded_unanswerable']}건 · "
              f"라벨 불일치 {m['n_inconsistent']}건",
              f"- 평가 대상 중 span 없음(라벨에 인용 가능한 정답 텍스트가 없음): "
              f"{m['n_no_span']}건 — 8절 참고(검색 품질과 무관하게 항상 miss로 집계됨)",
              f"- retrieved 상위 {RETRIEVAL_DEPTH} 내 chunk_id → 본문 조회 실패 연인원: "
              f"{m['n_missing_chunk_text']}건 (0이 아니면 chunks.jsonl 스냅샷과 검색 인덱스 "
              "버전이 다를 수 있으니 먼저 확인할 것)", ""]
    lines += _pct_table({rel: rm["n_total"] for rel, rm in relation_metrics.items()},
                        m["n_evaluated"], ("relation", "문항수"))
    lines += ["",
              "## 3. 실험 파라미터", "",
              f"- Corpus: {len(chunk_metadata)}개 청크 (`chunks.jsonl`)",
              f"- Retriever: {retriever_desc}",
              f"- Embedding: {embedding_desc}",
              f"- 검색 단위: chunk 검색 결과 + 정답 텍스트(span) 본문 포함 여부로 채점",
              f"- 검색 소스: {retrieval_source}",
              f"- Top-K: {RETRIEVAL_DEPTH}", "",
              "## 4. 평가 지표 및 판정 기준", "",
              "- Hit@1/3/5/10: Top-K 안에서 relation 조건을 만족하며 gold span이 발견되는지",
              "  (분모: 평가 대상 문항수). `and`는 필요한 span 전부, 그 외는 하나만 발견되면 hit.",
              "- Macro Recall@3/5/10: 문항별 recall(Top-K에서 회수한 span 비율)의 문항 평균. 주지표.",
              "- (참고) Micro Recall@3/5/10: 전체 span occurrence 기준 합산 recall. 문항당 span",
              "  개수가 많을수록(주로 `and`) 가중치가 커짐 — 보조지표로만 사용.",
              "- MRR: `and`는 마지막으로 발견된 필수 span의 순위, 그 외는 처음 발견된 span의",
              "  순위의 역수, Top-10까지만 본다(MRR@10).",
              "- id_hit@k: gold `chunk_id`를 직접 비교하는 기존 방식(참고용, 10절 비교표).",
              "- answerable=false 문항은 전 지표의 분모에서 제외.",
              "- span 없음 문항은 분모에 포함되지만(n_evaluated) 항상 hit=False로 집계된다", ""]
    lines += ["## 5. 전체 평가 결과", "",
              "| Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |",
              "|---:|---:|---:|---:|---:|",
              f"| {m['hit@1']:.3f} | {m['hit@3']:.3f} | {m['hit@5']:.3f} | {m['hit@10']:.3f} | "
              f"{m['mrr']:.3f} |",
              "",
              "| MacroRecall@3 | MacroRecall@5 | MacroRecall@10 |",
              "|---:|---:|---:|",
              f"| {m['macro_recall@3']:.3f} | {m['macro_recall@5']:.3f} | "
              f"{m['macro_recall@10']:.3f} |",
              "",
              f"- (참고) Micro Recall@10: {m['recall@10']:.3f} · span 총계(occurrence): "
              f"{m['total_spans']} · 회수(@10): {m['recalled@10']}", ""]

    lines += ["## 6. Relation별 결과", "",
              "| relation | 문항수 | Hit@1 | Hit@3 | Hit@5 | MacroRecall@10 | MRR |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for rel, rm in sorted(relation_metrics.items(), key=lambda kv: -kv[1]["n_total"]):
        lines.append(f"| {rel} | {rm['n_total']} | {rm['hit@1']:.3f} | {rm['hit@3']:.3f} | "
                    f"{rm['hit@5']:.3f} | {rm['macro_recall@10']:.3f} | {rm['mrr']:.3f} |")

    lines += ["", "## 7. 도메인별 결과", "",
              "| 업무 | 문항수 | Hit@1 | Hit@3 | Hit@5 | MacroRecall@10 | MRR |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for domain, dm in sorted(domain_metrics.items(), key=lambda kv: -kv[1]["n_total"]):
        lines.append(f"| {domain} | {dm['n_total']} | {dm['hit@1']:.3f} | {dm['hit@3']:.3f} | "
                    f"{dm['hit@5']:.3f} | {dm['macro_recall@10']:.3f} | {dm['mrr']:.3f} |")

    err = _error_analysis(rows, chunk_to_bf)
    no_span_rows = err["no_span_rows"]
    lines += ["", "## 8. span 없음 라벨", "",
              f"{len(no_span_rows)}건 — 원문에 그대로 인용 가능한 정답 텍스트가 없어(주로 "
              "`evidence_type=inferable`, 계산·추론형 답변) gt_anchor_span 자체가 비어 있다.",
              "검색이 아무리 정확해도 이 문항들은 항상 miss로 집계되므로, 전체 Hit/MRR을",
              f"{len(no_span_rows)}/{m['n_evaluated']}건만큼 구조적으로 낮춘다. span을 소급",
              "라벨링하거나 별도 분모로 빼고 보는 것을 검토할 것.", ""]
    if no_span_rows:
        lines += ["| id | relation | evidence_type | gold chunk IDs | question |",
                  "|---|---|---|---|---|"]
        for row in no_span_rows:
            lines.append(f"| {row['id']} | {row['chunk_relation']} | {row['evidence_type']} | "
                        f"{_format_ids(row['gold_chunk_ids'])} | {row['question']} |")

    n_miss = len(err["misses"])
    n_scoreable = m["n_evaluated"] - len(no_span_rows)
    lines += ["", "## 9. 오류 분석", "",
              f"- 미적중(top-3 밖) {n_miss}건 / 채점 가능 문항 {n_scoreable}건 "
              f"({n_miss / n_scoreable * 100 if n_scoreable else 0:.1f}%, span 없음 제외)", ""]
    if err["cause"]:
        lines += ["### 9-1. 미적중 원인 분포", "",
                  "정분류: gt 업무 청크가 top-3 안에 있으나 순위/청킹 문제로 span을 못 찾음. "
                  "오분류: top-3 전부 다른 업무 청크로 채워짐.", ""]
        lines += _pct_table(err["cause"], n_miss, ("원인", "건수"))

    lines += ["", "### 9-2. 업무별 미적중", "",
              "| 업무 | 문항수 | 미적중 | 미적중률 |", "|---|---:|---:|---:|"]
    for domain, count in sorted(err["by_domain"].items(), key=lambda kv: -kv[1]):
        total = domain_metrics[domain]["n_total"]
        lines.append(f"| {domain} | {total} | {count} | {count / total * 100 if total else 0:.1f}% |")

    if err["intruders"]:
        lines += ["", "### 9-3. 혼입 문서 랭킹 (미적중 top-3를 잠식한 다른 업무 청크)", "",
                  "| 청크 ID | 출현 | 업무 |", "|---|---:|---|"]
        for cid, count in sorted(err["intruders"].items(), key=lambda kv: -kv[1])[:15]:
            lines.append(f"| `{cid}` | {count} | {chunk_to_bf.get(cid, '(unknown)')} |")

    if err["cross_flow"]:
        lines += ["", "### 9-4. 업무 간 혼입 흐름 (정답 업무 → top-1 업무)", "",
                  "| 정답 업무 | → top-1 업무 | 건수 |", "|---|---|---:|"]
        for (gt_bf, top1_bf), count in sorted(err["cross_flow"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {gt_bf} | {top1_bf} | {count} |")

    if err["worst"]:
        lines += ["", "### 9-5. 대표 실패 사례 (gold span이 top-10에도 없음)", ""]
        for row in err["worst"]:
            lines += [f"- **[{row['business_function']}] {row['id']}** ({row['chunk_relation']}) "
                     f"— {row['question']}",
                     f"  - gold chunk IDs: {_format_ids(row['gold_chunk_ids'])}",
                     f"  - span 발견({row['n_spans_found']}/{row['n_spans']}), 순위: "
                     f"{row['span_ranks']}",
                     f"  - top-3: {_format_ids(row['retrieved_chunk_ids'][:3])}"]

    lines += ["", "## 10. 개선 우선순위", ""]
    priorities = []
    for domain, count in sorted(err["by_domain"].items(), key=lambda kv: -kv[1])[:3]:
        total = domain_metrics[domain]["n_total"]
        priorities.append(f"'{domain}' 업무 — 미적중 {count}/{total}건"
                          f"({count / total * 100 if total else 0:.1f}%)로 가장 취약함")
    and_m = relation_metrics.get("and")
    if and_m and and_m["hit@3"] < m["hit@3"]:
        priorities.append(f"`and` relation(다중 span 필요) Hit@3={and_m['hit@3']:.3f}로 "
                          f"전체 평균({m['hit@3']:.3f})보다 낮음 — MacroRecall@10="
                          f"{and_m['macro_recall@10']:.3f}로 부분 회수는 되고 있어 다중 청크"
                          " 동시 회수 전략(top-k 확대/쿼리 분해) 점검 필요")
    if err["intruders"]:
        top_intruder = max(err["intruders"].items(), key=lambda kv: kv[1])
        priorities.append(f"`{top_intruder[0]}` 청크가 미적중 {top_intruder[1]}건에서 top-3를 잠식 "
                          f"— 업무 분류/부스트 파라미터 재검토 대상 1순위")
    if no_span_rows:
        priorities.append(f"span 없는 라벨 {len(no_span_rows)}건은 검색과 무관하게 항상 miss — "
                          "8절 목록부터 소급 라벨링하면 즉시 Hit/MRR이 개선됨")
    lines += [f"{i}. {p}" for i, p in enumerate(priorities, 1)] or ["_미적중 사례 없음._"]

    lines += ["", "## 11. span 기준 vs chunk_id 기준 비교 (참고)", "",
              "chunk_id 직접비교(기존 방식) 대비 span 기준 채점의 거품/회수(percentage points):",
              "",
              "| 지표 | span 기준 | chunk_id 기준 | 차이(span - id, pp) |",
              "|---|---:|---:|---:|"]
    for key in ("hit@1", "hit@3", "hit@5", "hit@10"):
        id_key = f"id_{key}"
        bubble = (m[key] - m[id_key]) * 100
        lines.append(f"| {key} | {m[key]:.3f} | {m[id_key]:.3f} | {bubble:+.1f}pp |")

    lines += ["", "## 부록. 문항별 라벨과 검색 청크", "",
              "| id | answerable | relation(mode) | 업무 | gold chunk IDs | span 발견(회수/필요) | "
              "각 span 순위 | Top-10 retrieved chunk IDs | span Hit@1/3/5/10 | id Hit@1/3/5/10 |",
              "|---|---|---|---|---|---:|---|---|---|---|"]
    for row in rows:
        if row["excluded"]:
            lines.append(f"| {row['id']} | false | - | - | - | - | - | - | excluded | excluded |")
            continue
        span_hits = "/".join(str(int(row["hit"][f"hit@{k}"])) for k in KS)
        id_hits = "/".join(str(int(row["id_hit"][f"id_hit@{k}"])) for k in KS)
        rank_str = ",".join(str(r) if r else "-" for r in row["span_ranks"]) or "-"
        lines.append(
            "| {id} | true | {relation}({mode}) | {bf} | {gold} | {nf}/{n} | {ranks} | "
            "{retrieved} | {span_hits} | {id_hits} |".format(
                id=row["id"], relation=row["chunk_relation"], mode=row["relation_mode"],
                bf=row["business_function"], gold=_format_ids(row["gold_chunk_ids"]),
                nf=row["n_spans_found"], n=row["n_spans"], ranks=rank_str,
                retrieved=_format_ids(row["retrieved_chunk_ids"][:RETRIEVAL_DEPTH]),
                span_hits=span_hits, id_hits=id_hits))

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_group(title: str, rows: list[tuple[str, str]]) -> None:
    print(f"[{title}]")
    label_width = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"  {label.ljust(label_width)} : {value}")
    print()


def _print_summary(result: dict, report_path: Path) -> None:
    m = result["overall"]
    print("=== KDIC span 기준(다중 span) 평가 결과 ===")
    print()
    _print_group("데이터", [
        ("n_total", str(m["n_total"])),
        ("n_evaluated", str(m["n_evaluated"])),
        ("n_excluded", str(m["n_excluded_unanswerable"])),
        ("n_inconsistent", str(m["n_inconsistent"])),
        ("n_no_span", str(m["n_no_span"])),
        ("n_missing_chunk_text", str(m["n_missing_chunk_text"])),
    ])
    _print_group("Hit@K (span 기준 / id 기준)", [
        (f"Hit@{k}", f"{m[f'hit@{k}']:.3f} / {m[f'id_hit@{k}']:.3f}") for k in KS
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
    parser = argparse.ArgumentParser(description="KDIC span(정답 텍스트) 기준 검색 평가 — 다중 span 지원")
    parser.add_argument("--gt", default=data_dir / "gt_natural450_multi.jsonl", type=Path)
    parser.add_argument("--chunks", default=data_dir / "chunks.jsonl", type=Path)
    parser.add_argument("--retrieved", type=Path,
                        help="id, retrieved_chunk_ids JSONL. 생략하면 현재 rag.Searcher로 검색한다.")
    parser.add_argument("--mode", default="hybrid_bf", help="--retrieved 생략 시 rag 검색 mode")
    parser.add_argument("--report", default=data_dir / "eval_anchor_span_multi_report.md", type=Path)
    parser.add_argument("--limit", type=int, default=0,
                        help="처음 N건만 평가(스모크 테스트용, 대표성 있는 지표가 아님). 0이면 전체.")
    parser.add_argument("--id-fallback", action="store_true",
                        help="스팬이 아예 없는 문항(evidence_type=inferable 등)만 gold chunk_id "
                             "등장 여부로 대체 판정한다. 기본 꺼짐(기존 리포트와 동일).")
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

    result = evaluate_span_retrieval(gt_data, retrieved_data, chunk_metadata, args.id_fallback)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_report(result, args.report, args.gt, retrieval_source, chunk_metadata)
    _print_summary(result, args.report)


if __name__ == "__main__":
    main()
