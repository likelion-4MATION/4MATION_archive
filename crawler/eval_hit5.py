"""soft Hit@5 최적화 스윕 — eval_fusion_sweep의 시뮬레이터(파리티 448/448)를 재사용한다.

판정 기준: soft Hit@5 우선, Hit@1/nDCG@5/Hit@30 병기, soft Hit@5 McNemar.
"""
import sys, math, pathlib, argparse, collections, itertools
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rag
from eval_fusion_sweep import Fuser, get_cache, D
from eval_anchor_gold import evaluate, load, ndcg, wilson


def metrics(rows):
    n = len(rows)
    m = {f"H{k}": sum(1 for r in rows if 0 < r["rank"] <= k) / n for k in (1, 5, 30)}
    for k in (1, 3, 5, 30):
        m[f"S{k}"] = sum(1 for r in rows if 0 < r["soft_rank"] <= k) / n
    m["nDCG5"] = sum(ndcg(r["rels"], 5) for r in rows) / n
    return m


def mcnemar(base, new, key):
    b = {r["id"]: key(r) for r in base}
    win = sum(1 for r in new if key(r) and not b.get(r["id"]))
    los = sum(1 for r in new if not key(r) and b.get(r["id"]))
    n = win + los
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(min(win, los) + 1)) / 2 ** n) if n else 1.0
    return win, los, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", default="cap")
    a = ap.parse_args()
    gt = [g for g in load(D / "gt_natural450_v10_anchor.jsonl") if g.get("answerable") is True]
    chunks = load(D / "chunks.jsonl")
    dense, sparse, toks = get_cache(gt, chunks)
    fuser = Fuser(chunks)
    bfs = [rag.classify_query_bf(g["question"]) for g in gt]
    facs = [rag.query_facets(g["question"]) for g in gt]

    def run(**kw):
        # g_XXX 키는 rag 모듈 전역(BF_BOOST 등) — Fuser.rank가 호출 시점에 읽으므로 이렇게만 바꾸면 된다.
        gsave = {}
        for k in [k for k in kw if k.startswith("g_")]:
            name = k[2:]; gsave[name] = getattr(rag, name); setattr(rag, name, kw.pop(k))
        ret = [{"id": g["id"], "retrieved_chunk_ids":
                fuser.rank(i, dense, sparse, toks[i], bf=bfs[i], facets=facs[i], **kw)}
               for i, g in enumerate(gt)]
        rows, _, _ = evaluate(gt, chunks, ret)
        for name, v in gsave.items():
            setattr(rag, name, v)
        return rows

    GRIDS = {
        "cap": [(f"cap={c}", dict(cap=c)) for c in (0, 1, 2, 3, 4, 5, 6, 8)],
        "rrfk": [(f"RRF_K={k}", dict(rrf_k=k)) for k in (1, 2, 3, 4, 5, 8, 12, 20, 40, 60)],
        "alpha": [(f"alpha={x}", dict(alpha=x)) for x in (0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8)],
        "densew": [(f"DENSE_W={x}", dict(dense_w=x)) for x in (0.3, 0.4, 0.5, 0.6, 0.7)],
        "titlew": [(f"TITLE_W={x}", dict(title_w=x)) for x in (0.0, 0.02, 0.04, 0.08, 0.12)],
        "bfboost": [(f"BF_BOOST={x}", dict(g_BF_BOOST=x)) for x in (0.0, 0.02, 0.04, 0.06, 0.08, 0.12)],
        "facet": [(f"FACET_BOOST={x}", dict(g_FACET_BOOST=x)) for x in (0.0, 0.05, 0.1, 0.15, 0.2, 0.3)],
        "cap3x": [("cap=3", dict(cap=3))]
                 + [(f"cap=3 alpha={x}", dict(cap=3, alpha=x)) for x in (0.5, 0.55, 0.65)]
                 + [(f"cap=3 rrfk={x}", dict(cap=3, rrf_k=x)) for x in (4, 6, 8)]
                 + [(f"cap=3 dw={x}", dict(cap=3, dense_w=x)) for x in (0.4, 0.6)]
                 + [(f"cap=3 tw={x}", dict(cap=3, title_w=x)) for x in (0.08, 0.12)]
                 + [(f"cap=3 facet={x}", dict(cap=3, g_FACET_BOOST=x)) for x in (0.15, 0.2)]
                 + [(f"cap=3 bf={x}", dict(cap=3, g_BF_BOOST=x)) for x in (0.06, 0.08)],
    }
    variants = [("baseline", {})] + GRIDS[a.grid]
    base_rows = None
    print(f"\n=== grid: {a.grid} ===")
    print("| 변형 | softH@5 | softH@1 | nDCG@5 | H@1 | H@5 | H@30 | softH@5 win/los, p |")
    print("|---|---:|---:|---:|---:|---:|---:|---|")
    for name, kw in variants:
        rows = run(**kw)
        if base_rows is None:
            base_rows = rows
        m = metrics(rows)
        c = ""
        if rows is not base_rows:
            w, l, p = mcnemar(base_rows, rows, lambda r: 0 < r["soft_rank"] <= 5)
            c = f"{w}/{l}, p={p:.3f}" + ("" if p < 0.05 else " ns")
        print(f"| {name} | {m['S5']:.4f} | {m['S1']:.4f} | {m['nDCG5']:.4f} | "
              f"{m['H1']:.3f} | {m['H5']:.3f} | {m['S30']:.3f} | {c} |")


if __name__ == "__main__":
    main()
