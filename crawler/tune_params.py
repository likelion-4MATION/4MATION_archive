"""검색 파라미터 5축 그리드서치 — 앵커텍스트 판정 기준.

축: RRF_ALPHA · RRF_K · BF_BOOST · FACET_BOOST · BF_DOC_CAP
주지표: 앵커 hit@5 (chunk_id hit@5도 병기)

설계 — 왜 이렇게 빠른가:
  dense/sparse 랭킹은 파라미터와 무관하므로 질의당 1회만 구해 순위행렬로 굳힌다.
  그 뒤 RRF·부스트는 전부 (질의 × 청크) 행렬 연산이라, config마다 재검색·재임베딩이
  없다. 부스트 대상 마스크(업무 일치 / 패싯 일치)도 config와 무관해 미리 굳힌다.

판정은 eval.py chunk 판정과 같은 규약을 쓴다. 다만 매 config마다 dict를 돌리면 느리므로
문항별 '필요 조건 집합'으로 미리 접어 둔다:
  ANY(single/or/near_dup/duplicate/contained): 후보 집합 중 하나라도 top-k와 교차
  AND(and): 모든 필요 집합이 각각 top-k와 교차
  집합 = (그 앵커를 담은 청크들) 또는 (앵커 없는 gold 청크 1개)
이 표현이 eval._anchor_hit_at_k와 동치임은 --verify로 실측 대조한다.

사용:
  python tune_params.py --gt ../final_testset/gt_natural430.jsonl
  python tune_params.py --gt ... --verify        # 평가기와 판정 일치 확인만
  python tune_params.py --gt ... --top 20
"""

from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import time

import numpy as np

import rag
import eval as ev3

# 1차 스윕(alpha≤0.65, rrf_k≥1)에서 최적점이 alpha·rrf_k 양쪽 경계에 붙었다 —
# 경계에 붙은 값은 최적점이 아니라 "그리드가 좁다"는 신호라 범위를 확장했다.
# alpha=1.0은 dense 단독(sparse 가중 0), rrf_k=0은 1/(rank+1)로 상위 랭크를 최대로 신뢰.
GRID = {
    "alpha": (0.35, 0.50, 0.65, 0.75, 0.85, 0.95, 1.0),
    "rrf_k": (0, 1, 2, 4),
    "bf": (0.06, 0.09, 0.12, 0.18, 0.24, 0.32),
    "facet": (0.05, 0.10, 0.15, 0.20, 0.30),
    "cap": (3, 5, 8, 0),          # 0 = 무제한
}
KS = (1, 3, 5, 10)
DEPTH = 50


def _rank_matrix(scores: np.ndarray) -> np.ndarray:
    """행별 내림차순 순위(0-based). scores[q, c] → rank[q, c]."""
    order = np.argsort(-scores, axis=1, kind="stable")
    ranks = np.empty_like(order)
    rows = np.arange(scores.shape[0])[:, None]
    ranks[rows, order] = np.arange(scores.shape[1])[None, :]
    return ranks


def build(gt_path: str, qbf_path: str | None):
    searcher = rag.Searcher()
    chunks = searcher.chunks
    n_c = len(chunks)
    cid_index = {c["chunk_id"]: i for i, c in enumerate(chunks)}
    doc_of = np.array([c["parent_doc_id"] for c in chunks])
    norm_text = [ev3._norm_text(c.get("text", "")) for c in chunks]

    rows = [json.loads(l) for l in
            pathlib.Path(gt_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    items = [r for r in rows if r.get("answerable") is True and ev3._get_gt_chunk_ids(r)]
    questions = [r["question"] for r in items]
    n_q = len(items)
    print(f"[gt] {gt_path} · {len(rows)}행 → 평가 {n_q}문항")

    # ── 질의 BF: 라우터 캐시가 있으면 조인, 없으면 현행 분류기 호출 ──
    qbf: list[str | None] = []
    cache = {}
    if qbf_path and pathlib.Path(qbf_path).exists():
        cache = {r["qhash"]: (r["bf"], r["msp"]) for r in
                 (json.loads(l) for l in
                  pathlib.Path(qbf_path).read_text(encoding="utf-8").splitlines() if l.strip())}
    for q in questions:
        h = ev3._norm_text(q)
        from faq_bf_map import normalize_q, qhash
        key = qhash(normalize_q(q))
        if key in cache:
            bf, msp = cache[key]
            qbf.append(bf if msp >= rag.QBF_MSP_MIN else None)
        else:
            qbf.append(rag.classify_query_bf(q))
    print(f"[qbf] 분류 완료 · None {sum(1 for b in qbf if b is None)}건")

    # ── dense/sparse 순위행렬 (파라미터 무관, 1회) ──
    # 순위는 반드시 실제 경로와 같은 방식으로 얻는다. 점수를 재계산해 정렬하면
    # 동점 처리가 갈려(BM25는 0점 동점이 대량) 상위 랭크가 어긋난다.
    #   dense : faiss index.search가 돌려준 순서 그대로 (rag.dense와 동일)
    #   sparse: np.argsort(scores)[::-1] — 동점을 인덱스 역순으로 깬다 (rag.sparse와 동일)
    t0 = time.perf_counter()
    embs = rag.embed_texts(questions)
    _, idx = searcher.index.search(embs, n_c)
    rank_d = np.empty((n_q, n_c), dtype="int32")
    rows = np.arange(n_q)[:, None]
    rank_d[rows, idx] = np.arange(n_c)[None, :]
    rank_s = np.empty((n_q, n_c), dtype="int32")
    for q, question in enumerate(questions):
        order = np.argsort(searcher.bm25.get_scores(rag.tokenize(question)))[::-1]
        rank_s[q, order] = np.arange(n_c)
    print(f"[base] 순위행렬 {n_q}x{n_c} · {time.perf_counter() - t0:.1f}s")

    # ── 부스트 마스크 (config 무관) ──
    bf_mask = np.zeros((n_q, n_c), dtype="float32")
    facet_mask = np.zeros((n_q, n_c), dtype="float32")
    for qi, (bf, q) in enumerate(zip(qbf, questions)):
        if bf is None:
            continue
        allow = rag.BF_SHARED_DOCS.get(bf, set())
        hit = np.array([(searcher._bf[i] == bf) or (chunks[i]["parent_doc_id"] in allow)
                        for i in range(n_c)], dtype=bool)
        bf_mask[qi] = hit
        facets = rag.query_facets(q)
        if facets:
            # 현행(nested) 규약: facet은 업무가 맞은 청크에만 가산.
            cnt = np.array([sum(1 for t in facets if t in chunks[i].get("sub_category", ""))
                            for i in range(n_c)], dtype="float32")
            facet_mask[qi] = cnt * hit

    # ── 문항별 판정 조건 집합 ──
    # 두 판정 모두 같은 표현으로 접는다 — ANY는 "집합 중 하나라도 top-k와 교차",
    # AND는 "모든 집합이 각각 top-k와 교차". chunk_id 판정은 gold 하나가 곧 한 집합이다.
    need: list[tuple[bool, list[set[int]]]] = []   # 앵커 판정
    need_id: list[tuple[bool, list[set[int]]]] = []  # chunk_id 판정
    for r in items:
        gold = ev3._get_gt_chunk_ids(r)
        gold_i = {cid_index[c] for c in gold if c in cid_index}
        rel = ev3._get_relation(r)
        is_and = rel == "and"
        anchors = ev3._get_gt_anchors(r)
        sets: list[set[int]] = []
        for a in anchors:
            s = {i for i in range(n_c) if a in norm_text[i]}
            if s:
                sets.append(s)
        covered = set().union(*sets) if sets else set()
        for c in gold:
            i = cid_index.get(c)
            if i is not None and i not in covered:
                sets.append({i})          # 앵커 없는 gold → chunk_id 폴백
        need.append((is_and, sets))
        # AND면 gold 각각이 필수 조건 → 싱글톤 집합들. ANY면 gold 전체가 후보 1집합.
        need_id.append((is_and, [{i} for i in gold_i] if is_and else ([gold_i] if gold_i else [])))
    return dict(searcher=searcher, n_q=n_q, n_c=n_c, doc_of=doc_of,
                rank_d=rank_d, rank_s=rank_s, bf_mask=bf_mask, facet_mask=facet_mask,
                need=need, need_id=need_id, items=items)


def _topk_lists(scores: np.ndarray, doc_of: np.ndarray, cap: int, depth: int,
                tie: np.ndarray | None = None) -> list[list[int]]:
    """행별 상위 정렬 + 문서당 cap 적용 → 인덱스 리스트.

    ``tie``(보통 dense 순위)를 주면 동점을 그 순서로 깬다. rag.hybrid_soft가 dense
    순위대로 dict에 키를 넣고 stable sort하므로, 동점 처리를 맞추지 않으면 RRF_K가
    작을 때(동점이 잦다) 상위 랭크가 어긋나 hit@1이 달라진다.
    """
    out = []
    # cap이 걸리면 앞에서 잘리므로 여유 있게 후보를 뽑는다.
    take = scores.shape[1] if cap else min(depth, scores.shape[1])
    if tie is None:
        order = np.argsort(-scores, axis=1, kind="stable")[:, :take]
    else:
        order = np.stack([np.lexsort((tie[q], -scores[q])) for q in range(scores.shape[0])])[:, :take]
    for row in order:
        if not cap:
            out.append(row[:depth].tolist())
            continue
        seen: dict[str, int] = {}
        keep = []
        for i in row:
            d = doc_of[i]
            if seen.get(d, 0) < cap:
                keep.append(int(i))
                seen[d] = seen.get(d, 0) + 1
                if len(keep) == depth:
                    break
        out.append(keep)
    return out


def _score(need, tops) -> dict:
    m = {f"hit@{k}": 0 for k in KS}
    m["mrr"] = 0.0
    n = len(need)
    for (is_and, sets), ranked in zip(need, tops):
        if not sets:
            continue
        pos = {c: r for r, c in enumerate(ranked, 1)}
        # 각 조건 집합이 충족되는 최초 순위
        firsts = [min((pos[c] for c in s if c in pos), default=None) for s in sets]
        if is_and:
            need_rank = None if any(f is None for f in firsts) else max(firsts)
        else:
            ok = [f for f in firsts if f is not None]
            need_rank = min(ok) if ok else None
        if need_rank is None:
            continue
        for k in KS:
            if need_rank <= k:
                m[f"hit@{k}"] += 1
        if need_rank <= 10:
            m["mrr"] += 1.0 / need_rank
    return {k: v / n for k, v in m.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True)
    ap.add_argument("--qbf", default="data/query_bf_router_450.jsonl")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--verify", action="store_true", help="평가기와 판정 동치 확인만")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    B = build(args.gt, args.qbf)

    def run(alpha, rrf_k, bf, facet, cap):
        s = (alpha / (rrf_k + B["rank_d"] + 1)
             + (1.0 - alpha) / (rrf_k + B["rank_s"] + 1)
             + bf * B["bf_mask"] + facet * B["facet_mask"])
        tops = _topk_lists(s, B["doc_of"], cap, DEPTH, tie=B["rank_d"])
        return _score(B["need"], tops), _score(B["need_id"], tops)

    if args.verify:
        # 현행 파라미터로 이 스크립트의 판정이 eval.py chunk 판정과 같은지 대조
        a, i = run(rag.RRF_ALPHA, rag.RRF_K, rag.BF_BOOST, rag.FACET_BOOST, rag.BF_DOC_CAP)
        s = B["searcher"]
        ret = [{"id": it["id"],
                "retrieved_chunk_ids": [h["chunk_id"] for h in
                                        s.search(it["question"], k=DEPTH, mode="hybrid_bf")]}
               for it in B["items"]]
        chunks = [json.loads(l) for l in
                  pathlib.Path("data/chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        r = ev3.evaluate_retrieval(B["items"], ret, chunks, score="both")
        print("\n=== 동치 확인 (현행 파라미터) ===")
        print(f"{'지표':<8}{'tune_params':>13}{'eval.py':>16}{'차':>9}")
        for k in ("hit@1", "hit@3", "hit@5", "hit@10", "mrr"):
            print(f"{k:<8}{a[k]:>13.4f}{r['anchor_level'][k]:>16.4f}{a[k]-r['anchor_level'][k]:>+9.4f}")
        return 0

    combos = list(itertools.product(*(GRID[k] for k in ("alpha", "rrf_k", "bf", "facet", "cap"))))
    print(f"[grid] {len(combos)} configs")
    t0 = time.perf_counter()
    res = []
    for n, (alpha, rrf_k, bf, facet, cap) in enumerate(combos, 1):
        anc, cid = run(alpha, rrf_k, bf, facet, cap)
        res.append(dict(alpha=alpha, rrf_k=rrf_k, bf=bf, facet=facet, cap=cap,
                        **{f"a_{k}": v for k, v in anc.items()},
                        **{f"c_{k}": v for k, v in cid.items()}))
        if n % 200 == 0:
            print(f"  {n}/{len(combos)} · {time.perf_counter()-t0:.0f}s")
    print(f"[grid] 완료 {time.perf_counter()-t0:.0f}s")

    res.sort(key=lambda r: -r["a_hit@5"])
    cur = next(r for r in res if (r["alpha"], r["rrf_k"], r["bf"], r["facet"], r["cap"])
               == (rag.RRF_ALPHA, rag.RRF_K, rag.BF_BOOST, rag.FACET_BOOST, rag.BF_DOC_CAP))
    print(f"\n현행: alpha={cur['alpha']} rrf_k={cur['rrf_k']} bf={cur['bf']} "
          f"facet={cur['facet']} cap={cur['cap']} → 앵커 hit@5 {cur['a_hit@5']:.4f} "
          f"(순위 {res.index(cur)+1}/{len(res)})")
    print(f"\n{'#':<4}{'alpha':>7}{'rrf_k':>6}{'bf':>6}{'facet':>7}{'cap':>5}"
          f"{'a_hit@1':>9}{'a_hit@3':>9}{'a_hit@5':>9}{'a_hit@10':>9}{'a_mrr':>8}{'c_hit@5':>9}")
    for i, r in enumerate(res[:args.top], 1):
        print(f"{i:<4}{r['alpha']:>7}{r['rrf_k']:>6}{r['bf']:>6}{r['facet']:>7}{r['cap']:>5}"
              f"{r['a_hit@1']:>9.4f}{r['a_hit@3']:>9.4f}{r['a_hit@5']:>9.4f}"
              f"{r['a_hit@10']:>9.4f}{r['a_mrr']:>8.4f}{r['c_hit@5']:>9.4f}")

    # 플래토 점검 — 최적점의 이웃(각 축 한 칸)이 같이 높은가. 고립 스파이크면 채택 금지.
    best = res[0]
    axes = ("alpha", "rrf_k", "bf", "facet", "cap")
    idx = {a: GRID[a].index(best[a]) for a in axes}
    print(f"\n=== 최적점 이웃 (각 축 ±1칸) — 고립 스파이크 판별 ===")
    lut = {(r["alpha"], r["rrf_k"], r["bf"], r["facet"], r["cap"]): r for r in res}
    for a in axes:
        vals = []
        for d in (-1, 0, 1):
            j = idx[a] + d
            if 0 <= j < len(GRID[a]):
                key = tuple(GRID[x][idx[x]] if x != a else GRID[a][j] for x in axes)
                vals.append(f"{GRID[a][j]}:{lut[key]['a_hit@5']:.4f}")
        print(f"  {a:<6} {' · '.join(vals)}")

    if args.report:
        pathlib.Path(args.report).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
        print(f"\n[out] {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
