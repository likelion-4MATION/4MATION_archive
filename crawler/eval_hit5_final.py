"""최종 후보 확정 — 전체 + 홀짝 분할 교차확인(과적합 감시). 판정은 soft Hit@5."""
import sys, math, pathlib
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rag
from eval_fusion_sweep import Fuser, get_cache, D
from eval_anchor_gold import evaluate, load, ndcg
from eval_hit5 import metrics, mcnemar

gt = [g for g in load(D / "gt_natural450_v10_anchor.jsonl") if g.get("answerable") is True]
chunks = load(D / "chunks.jsonl")
dense, sparse, toks = get_cache(gt, chunks)
fuser = Fuser(chunks)
bfs = [rag.classify_query_bf(g["question"]) for g in gt]
facs = [rag.query_facets(g["question"]) for g in gt]

def run(**kw):
    gs = {}
    for k in [k for k in kw if k.startswith("g_")]:
        n = k[2:]; gs[n] = getattr(rag, n); setattr(rag, n, kw.pop(k))
    ret = [{"id": g["id"], "retrieved_chunk_ids":
            fuser.rank(i, dense, sparse, toks[i], bf=bfs[i], facets=facs[i], **kw)}
           for i, g in enumerate(gt)]
    rows, _, _ = evaluate(gt, chunks, ret)
    for n, v in gs.items(): setattr(rag, n, v)
    return rows

CAND = [
    ("baseline", {}),
    ("cap=3", dict(cap=3)),
    ("cap=3 +alpha .55", dict(cap=3, alpha=0.55)),
    ("cap=3 +tw .08", dict(cap=3, title_w=0.08)),
    ("cap=3 +alpha .55 +tw .08", dict(cap=3, alpha=0.55, title_w=0.08)),
    ("cap=4", dict(cap=4)),
]
base = None
print("| 변형 | softH@5 | 짝수반 | 홀수반 | softH@1 | nDCG@5 | H@30 | win/los, p |")
print("|---|---:|---:|---:|---:|---:|---:|---|")
for name, kw in CAND:
    rows = run(**kw)
    if base is None: base = rows
    m = metrics(rows)
    ev = metrics([r for i, r in enumerate(rows) if i % 2 == 0])["S5"]
    od = metrics([r for i, r in enumerate(rows) if i % 2 == 1])["S5"]
    w, l, p = mcnemar(base, rows, lambda r: 0 < r["soft_rank"] <= 5)
    print(f"| {name} | {m['S5']:.4f} | {ev:.4f} | {od:.4f} | {m['S1']:.4f} | "
          f"{m['nDCG5']:.4f} | {m['S30']:.4f} | {w}/{l}, p={p:.3f} |")
