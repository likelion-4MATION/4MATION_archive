"""질의측 BF 소스(키워드 vs 라우터) × facet 적용 방식(중첩 vs 분리) A/B.

목적: hit@5 향상폭 측정. rag.py는 건드리지 않고, hybrid_soft의 부스트 단계만
이 스크립트 안에서 복제해 변형을 비교한다(채택 확정 후 rag.py 반영).

두 레버
1) 질의 BF 소스
   - keyword : 현행 rag.classify_query_bf (키워드 점수 + MIN_SCORE/MARGIN, 미달 시 None)
   - router  : predict_query_bf.py 캐시 조인, MSP<θ면 None
2) facet 적용
   - nested   : 현행. facet 부스트가 BF 매칭 브랜치 '안에' 있어 BF가 맞을 때만 발동
                → BF=None이면 facet이 통째로 사장된다.
   - separated: facet을 BF와 독립 축으로 적용. sub_category가 맞으면 BF 무관하게 가산.

기저 랭킹(dense/sparse RRF)은 질의당 1회만 계산하고 부스트 변형만 갈아끼운다 —
config 간 비교가 정확해지고(같은 base) 임베딩 재계산도 없앤다.

사용:
  python predict_query_bf.py            # 선행: 라우터 질의 예측 캐시 생성
  python exp_router_facet.py
  python exp_router_facet.py --gt data/gt_schema_v6.jsonl --depth 50
"""

from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np

import rag
import eval as ev3
from faq_bf_map import normalize_q, qhash

DEFAULT_GT = "data/gt_schema_v6.jsonl"
DEFAULT_QBF = "data/query_bf_router.jsonl"
REPORT_PATH = "data/eval_router_facet_report.md"
THETAS = (0.0, 0.5, 0.7, 0.8, 0.9, 0.95)


def _gold(item: dict) -> list[str]:
    ids = item.get("gt_chunk_ids") or ([item["gt_chunk_id"]] if item.get("gt_chunk_id") else [])
    if isinstance(ids, str):
        ids = [ids]
    return list(dict.fromkeys(ids))


def _base_rrf(searcher, questions: list[str], alpha: float, rrf_k: int) -> list[dict[int, float]]:
    """질의별 기저 RRF(부스트 이전). hybrid_soft의 융합 단계와 동일 계산."""
    n = len(searcher.chunks)
    embs = rag.embed_texts(questions)                    # 배치 임베딩 1회
    _, idx_mat = searcher.index.search(embs, n)
    out = []
    for qi, question in enumerate(questions):
        rrf: dict[int, float] = {}
        for rank, idx in enumerate(idx_mat[qi]):
            if idx >= 0:
                rrf[int(idx)] = rrf.get(int(idx), 0.0) + alpha / (rrf_k + rank + 1)
        scores = searcher.bm25.get_scores(rag.tokenize(question))
        for rank, idx in enumerate(np.argsort(scores)[::-1][:n]):
            rrf[int(idx)] = rrf.get(int(idx), 0.0) + (1.0 - alpha) / (rrf_k + rank + 1)
        out.append(rrf)
    return out


def _rank(searcher, base: dict[int, float], bf: str | None, facets: set,
          facet_mode: str, boost: float, facet_boost: float, depth: int) -> list[str]:
    """부스트 적용 → 정렬 → 문서당 cap → 상위 depth chunk_id."""
    rrf = dict(base)
    allow = rag.BF_SHARED_DOCS.get(bf, set()) if bf else set()
    for idx in rrf:
        chunk = searcher.chunks[idx]
        bf_hit = bf is not None and (searcher._bf[idx] == bf or chunk["parent_doc_id"] in allow)
        if bf_hit:
            rrf[idx] += boost
        if facets:
            # nested: BF가 맞은 청크에만 (현행) / separated: BF와 무관하게 (실험)
            if facet_mode == "separated" or bf_hit:
                hit = sum(1 for t in facets if t in chunk.get("sub_category", ""))
                if hit:
                    rrf[idx] += facet_boost * hit
    ranked = sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)
    capped = searcher._cap_by_doc(ranked, rag.BF_DOC_CAP)[:depth]
    return [searcher.chunks[i]["chunk_id"] for i, _ in capped]


def _metrics(items: list[dict], retrieved: list[list[str]]) -> dict:
    n = len(items)
    m = {}
    for k in (1, 3, 5, 10):
        m[f"hit@{k}"] = sum(ev3._hit_at_k(_gold(it), r, ev3._get_relation(it), k)
                            for it, r in zip(items, retrieved)) / n
    for k in (5, 10, 30, 50):
        m[f"recall@{k}"] = sum(ev3._recall_at_k(_gold(it), r, k)
                               for it, r in zip(items, retrieved)) / n
    rr = 0.0
    for it, r in zip(items, retrieved):
        gold = set(_gold(it))
        for pos, cid in enumerate(r[:10], 1):
            if cid in gold:
                rr += 1.0 / pos
                break
    m["mrr@10"] = rr / n
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default=DEFAULT_GT)
    ap.add_argument("--qbf", default=DEFAULT_QBF)
    ap.add_argument("--depth", type=int, default=50)
    ap.add_argument("--report", default=REPORT_PATH)
    ap.add_argument("--facet-sweep", type=float, default=None, metavar="THETA",
                    help="지정한 라우터 θ에 대해 FACET_BOOST를 스윕(중첩 vs 분리). "
                         "facet 분리가 현행 세기(0.02)에서만 무효인지, 축 자체가 무효인지 판별.")
    args = ap.parse_args()

    gt = [json.loads(l) for l in
          pathlib.Path(args.gt).read_text(encoding="utf-8").splitlines() if l.strip()]
    items = [it for it in gt if _gold(it)]
    questions = [it["question"] for it in items]
    print(f"[gt] {args.gt} · 전체 {len(gt)} · gold 보유 {len(items)}")

    qbf_cache = {r["qhash"]: (r["bf"], r["msp"]) for r in
                 (json.loads(l) for l in
                  pathlib.Path(args.qbf).read_text(encoding="utf-8").splitlines() if l.strip())}
    missing = [q for q in questions if qhash(normalize_q(q)) not in qbf_cache]
    if missing:
        raise SystemExit(f"[중단] 라우터 질의 예측 캐시 미매핑 {len(missing)}건 — "
                         f"predict_query_bf.py를 --gt {args.gt}로 재실행하세요.")

    searcher = rag.Searcher()
    print(f"[index] 청크 {len(searcher.chunks)} · bf_map {len(searcher.bf_map)}")

    kw_bf = [rag.classify_query_bf(q) for q in questions]
    rt_bf = [qbf_cache[qhash(normalize_q(q))] for q in questions]
    facets = [rag.query_facets(q) for q in questions]

    print("[base] 기저 RRF 계산 중 (질의당 1회)…")
    base = _base_rrf(searcher, questions, rag.RRF_ALPHA, rag.RRF_K)

    # (표시명, 질의BF 리스트, facet 모드, facet 부스트)
    configs: list[tuple[str, list[str | None], str, float]] = []
    if args.facet_sweep is None:
        configs += [("keyword · nested (현행)", kw_bf, "nested", rag.FACET_BOOST),
                    ("keyword · separated", kw_bf, "separated", rag.FACET_BOOST)]
        for th in THETAS:
            gated = [b if m >= th else None for b, m in rt_bf]
            configs.append((f"router θ={th:.2f} · nested", gated, "nested", rag.FACET_BOOST))
            configs.append((f"router θ={th:.2f} · separated", gated, "separated", rag.FACET_BOOST))
    else:
        th = args.facet_sweep
        gated = [b if m >= th else None for b, m in rt_bf]
        for fb in (0.0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30):
            for fmode in ("nested", "separated"):
                configs.append((f"router θ={th:.2f} · {fmode} · FACET={fb:.2f}", gated, fmode, fb))

    results = {}
    for name, bfs, fmode, fb in configs:
        retrieved = [_rank(searcher, base[i], bfs[i], facets[i], fmode,
                           rag.BF_BOOST, fb, args.depth)
                     for i in range(len(items))]
        results[name] = _metrics(items, retrieved)
        print(f"  {name:<40} hit@5={results[name]['hit@5']:.3f}")

    baseline = results[configs[0][0]]
    cols = ["hit@1", "hit@3", "hit@5", "hit@10", "mrr@10", "recall@10", "recall@50"]
    lines = ["# 질의 BF 소스 × facet 적용 방식 A/B\n",
             f"- GT: `{args.gt}` · 평가 {len(items)}문항 (gold 보유)",
             f"- 검색 깊이 {args.depth} · BF_BOOST={rag.BF_BOOST} · FACET_BOOST={rag.FACET_BOOST} "
             f"· RRF_ALPHA={rag.RRF_ALPHA} · RRF_K={rag.RRF_K} · BF_DOC_CAP={rag.BF_DOC_CAP}",
             "- 기저 RRF는 전 config 공유(동일 base) — 차이는 부스트 단계에서만 발생\n",
             "| config | " + " | ".join(cols) + " | Δhit@5 |",
             "|---|" + "---:|" * (len(cols) + 1)]
    for name, m in results.items():
        row = " | ".join(f"{m[c]:.3f}" for c in cols)
        d = m["hit@5"] - baseline["hit@5"]
        lines.append(f"| {name} | {row} | {d:+.3f} |")
    report = "\n".join(lines) + "\n"
    pathlib.Path(args.report).write_text(report, encoding="utf-8")

    print("\n" + report)
    print(f"[out] {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
