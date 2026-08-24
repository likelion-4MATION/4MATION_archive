"""임의 코퍼스에 대한 5축 그리드서치 — relation 분리 + 두 셋 전이성.

`tune_params.py`는 커밋된 인덱스(`rag.Searcher`)에 묶여 있어 재청킹한 코퍼스를
평가할 수 없다. 이 스크립트는 청크 리스트를 직접 받아 dense/sparse를 새로 만든다.

배경: RRF_ALPHA=0.65 · RRF_K=1 등 현행 값은 **215청크 코퍼스**에서 튜닝됐다
(DECISIONS 08-14 ④). 표 원자성 수정으로 181청크가 되면 최적점이 옮겨갈 수 있다.

측정 규율(08-18 ②와 동일):
  - 주지표는 `single` — gold 1개·앵커 1개라 판정 구조가 재청킹에 불변
  - `and`는 병기하되 gold 병합에 의한 판정 완화가 섞여 있음을 전제
  - 채택은 **두 셋(TEST 430 / VAL 355) 모두 개선되는 값**만. 한쪽 단독 최적은 버린다
  - 최적점이 그리드 경계에 붙으면 범위가 좁다는 신호이므로 확장 재실행

사용:
  cd crawler && python tune_params_v2.py                 # 표 수정 코퍼스(TABLE_GAP_MAX=12)
  cd crawler && python tune_params_v2.py --gap 0         # 옛 청킹 대조
  cd crawler && python tune_params_v2.py --chunks data/chunks.jsonl
"""
from __future__ import annotations
import argparse, collections, itertools, json, pathlib, statistics, time
import numpy as np
import rag, eval as ev3
from tune_params import _topk_lists

GRID = {"alpha": (0.35, 0.50, 0.65, 0.75, 0.85, 0.95, 1.0),
        "rrf_k": (0, 1, 2, 4),
        "bf":    (0.06, 0.09, 0.12, 0.18, 0.24, 0.32),
        "facet": (0.05, 0.10, 0.15, 0.20, 0.30),
        "cap":   (3, 5, 8, 0)}
# 181청크 코퍼스 1차 스윕에서 rrf_k(최대)·bf(최소)·facet(최소) 세 축이 경계에 붙었다.
# 경계 접촉은 최적이 아니라 "그리드가 좁다"는 신호이므로 확장판을 둔다(--wide).
# bf/facet 0.0을 포함하는 이유: 표가 합쳐지면서 부스트 자체가 불필요해졌을 수 있다.
GRID_WIDE = {"alpha": (0.35, 0.50, 0.65, 0.75, 0.85, 1.0),
             "rrf_k": (0, 1, 2, 4, 8, 16, 32, 60),
             "bf":    (0.0, 0.03, 0.06, 0.09, 0.12, 0.18, 0.24),
             "facet": (0.0, 0.02, 0.05, 0.10, 0.15, 0.20),
             "cap":   (3, 5, 8, 0)}
KS = (1, 3, 5, 10)
SETS = ("430", "355")


def load_corpus(gap, path):
    if path:
        return ev3._load_jsonl(pathlib.Path(path))
    from exp_tablefix import variant
    return variant(gap)


def build(chunks, name):
    n_c = len(chunks)
    idx = {c["chunk_id"]: i for i, c in enumerate(chunks)}
    nt = {c["chunk_id"]: ev3._norm_text(c.get("text", "")) for c in chunks}
    doc_of = np.array([c["parent_doc_id"] for c in chunks])
    bfmap = rag.load_bf_map()
    import faq_bf_map as fbm
    bf_of = []
    for c in chunks:
        if bfmap and fbm.is_board(c):
            q = fbm.extract_question(c["text"])
            bf_of.append(bfmap.get(fbm.qhash(fbm.normalize_q(q))) if q else None)
        else:
            bf_of.append(c.get("business_function"))

    items = [r for r in ev3._load_jsonl(pathlib.Path(f"../final_testset/gt_natural{name}.jsonl"))
             if r.get("answerable") is True and ev3._get_gt_chunk_ids(r)]
    qs = [r["question"] for r in items]
    ce = rag.embed_texts([rag.chunk_embed_text(c) for c in chunks])
    qe = rag.embed_texts(qs)
    order = np.argsort(-(qe @ ce.T), axis=1, kind="stable")
    rank_d = np.empty((len(qs), n_c), "int32")
    rank_d[np.arange(len(qs))[:, None], order] = np.arange(n_c)
    from rank_bm25 import BM25Okapi
    bm = BM25Okapi([rag.tokenize(c["text"]) for c in chunks])
    rank_s = np.empty((len(qs), n_c), "int32")
    for i, q in enumerate(qs):
        rank_s[i, np.argsort(bm.get_scores(rag.tokenize(q)))[::-1]] = np.arange(n_c)
    bfm = np.zeros((len(qs), n_c), "float32"); fcm = np.zeros((len(qs), n_c), "float32")
    for i, q in enumerate(qs):
        b = rag.classify_query_bf(q)
        if b is None: continue
        allow = rag.BF_SHARED_DOCS.get(b, set())
        hit = np.array([(bf_of[j] == b) or (chunks[j]["parent_doc_id"] in allow)
                        for j in range(n_c)], dtype=bool)
        bfm[i] = hit
        f = rag.query_facets(q)
        if f:
            fcm[i] = np.array([sum(1 for t in f if t in chunks[j].get("sub_category", ""))
                               for j in range(n_c)], "float32") * hit
    # 판정 조건 — 앵커는 텍스트 매칭이라 재청킹 무관. 미앵커 gold는 원본 프로브 재투영
    base = {c["chunk_id"]: c for c in ev3._load_jsonl(pathlib.Path("data/chunks.jsonl"))}
    bnorm = {k: ev3._norm_text(v["text"]) for k, v in base.items()}
    from exp_overlap import unique_probe
    need = []
    for it in items:
        gold = ev3._get_gt_chunk_ids(it); anc = ev3._get_gt_anchors(it)
        sets = [s for s in ({idx[c] for c in nt if a in nt[c]} for a in anc) if s]
        cov = {c for c in gold if c in bnorm and any(a in bnorm[c] for a in anc)}
        for c in gold:
            if c in cov or c not in base: continue
            p = unique_probe(base[c]["text"], bnorm, c)
            s = {idx[k] for k in nt if p and ev3._norm_text(p) in nt[k]} if p else set()
            if s: sets.append(s)
        need.append((ev3._get_relation(it) == "and", sets, ev3._get_relation_label(it)))
    return dict(rank_d=rank_d, rank_s=rank_s, bf=bfm, fc=fcm, doc_of=doc_of, need=need, n=len(items))


def run(B, alpha, rrf_k, bf, facet, cap, K=5):
    s = (alpha / (rrf_k + B["rank_d"] + 1) + (1 - alpha) / (rrf_k + B["rank_s"] + 1)
         + bf * B["bf"] + facet * B["fc"])
    tops = _topk_lists(s, B["doc_of"], cap, K, tie=B["rank_d"])
    per = collections.defaultdict(lambda: [0, 0])
    for (is_and, sets, lab), t in zip(B["need"], tops):
        per[lab][1] += 1
        if not sets: continue
        pos = set(t)
        per[lab][0] += bool(all(pos & x for x in sets) if is_and else any(pos & x for x in sets))
    out = {l: a / b for l, (a, b) in per.items()}
    out["_all"] = sum(a for a, _ in per.values()) / sum(b for _, b in per.values())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=int, default=12)
    ap.add_argument("--chunks", default=None)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--wide", action="store_true", help="경계 확장 그리드")
    ap.add_argument("--report", default="data/tune_v2_report.md")
    args = ap.parse_args()
    global GRID
    if args.wide: GRID = GRID_WIDE
    chunks = load_corpus(args.gap, args.chunks)
    print(f"[corpus] {len(chunks)}청크 · 최대 {max(len(c['text']) for c in chunks):,}자")
    B = {n: build(chunks, n) for n in SETS}
    for n in SETS: print(f"[gt] {n}: {B[n]['n']}문항")
    cur = (rag.RRF_ALPHA, rag.RRF_K, rag.BF_BOOST, rag.FACET_BOOST, rag.BF_DOC_CAP)
    print(f"\n[현행 파라미터 {cur}]")
    for n in SETS:
        r = run(B[n], *cur)
        print(f"  {n}: 전체 {r['_all']:.4f} · single {r.get('single',float('nan')):.4f}"
              f" · and {r.get('and',float('nan')):.4f}")
    combos = list(itertools.product(*(GRID[k] for k in ("alpha","rrf_k","bf","facet","cap"))))
    print(f"\n[grid] {len(combos)} configs × {len(SETS)} sets")
    t0 = time.perf_counter(); res = {}
    for i, cfg in enumerate(combos, 1):
        res[cfg] = {n: run(B[n], *cfg) for n in SETS}
        if i % 800 == 0: print(f"  {i}/{len(combos)} · {time.perf_counter()-t0:.0f}s")
    print(f"[grid] 완료 {time.perf_counter()-t0:.0f}s\n")
    sng = lambda cfg, n: res[cfg][n].get("single", 0.0)
    rank = sorted(res, key=lambda c: -min(sng(c, "430"), sng(c, "355")))
    print("=== single 두 셋 min 기준 상위 (주지표) ===")
    print(f"  {'(alpha,rrf_k,bf,facet,cap)':<30}{'430 sng':>9}{'355 sng':>9}{'min':>9}{'430 전체':>10}{'430 and':>9}")
    seen = set(); shown = 0
    for c in rank:
        key = c[:4]
        if key in seen: continue
        seen.add(key)
        print(f"  {str(c):<30}{sng(c,'430'):>9.4f}{sng(c,'355'):>9.4f}"
              f"{min(sng(c,'430'),sng(c,'355')):>9.4f}{res[c]['430']['_all']:>10.4f}"
              f"{res[c]['430'].get('and',0):>9.4f}")
        shown += 1
        if shown >= args.top: break
    print(f"\n  현행 {cur} → 430 sng {sng(cur,'430'):.4f} · 355 sng {sng(cur,'355'):.4f}"
          f" · min {min(sng(cur,'430'),sng(cur,'355')):.4f} (순위 {rank.index(cur)+1}/{len(rank)})")
    best = rank[0]; axes = ("alpha","rrf_k","bf","facet","cap")
    ix = {a: GRID[a].index(best[i]) for i, a in enumerate(axes)}
    print("\n=== 최적점 이웃 (±1칸, 430 single / 355 single) — 고립 스파이크 판별 ===")
    for i, a in enumerate(axes):
        cells = []
        for d in (-1, 0, 1):
            j = ix[a] + d
            if 0 <= j < len(GRID[a]):
                k = tuple(GRID[x][ix[x]] if x != a else GRID[a][j] for x in axes)
                cells.append(f"{GRID[a][j]}:{sng(k,'430'):.3f}/{sng(k,'355'):.3f}")
        print(f"  {a:<6} " + " · ".join(cells))
    pathlib.Path(args.report).write_text(json.dumps(
        {str(k): v for k, v in res.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[out] {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
