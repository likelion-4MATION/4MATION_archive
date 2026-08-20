"""soft Hit@5 실패 문항 전수 분석 — 실패 유형을 먼저 세고 나서 실험한다."""
import sys, json, pathlib, collections
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from eval_anchor_gold import evaluate, load

D = pathlib.Path(__file__).resolve().parent / "data"
gt = [g for g in load(D / "gt_natural450_v10_anchor.jsonl") if g.get("answerable") is True]
chunks = load(D / "chunks.jsonl")
ret = load(D / (sys.argv[1] if len(sys.argv) > 1 else "retrieved_top30_kunam.jsonl"))
rows, _, _ = evaluate(gt, chunks, ret)
cid = [c["chunk_id"] for c in chunks]
pos = {c: i for i, c in enumerate(cid)}
z = np.load(D / "qscore_cache.npz", allow_pickle=False)
dense, sparse, ids = z["dense"], z["sparse"], list(z["ids"])
qi = {q: i for i, q in enumerate(ids)}
by = {c["chunk_id"]: c for c in chunks}

def ranks(v):  # chunk index -> 1-based rank
    o = np.argsort(v)[::-1]
    return {int(c): r for r, c in enumerate(o, 1)}

fails = [r for r in rows if not (0 < r["soft_rank"] <= 5)]
print(f"평가 {len(rows)}건 · soft Hit@5 {1-len(fails)/len(rows):.3f} · 실패 {len(fails)}건\n")

cat = collections.Counter()
lines = []
for r in fails:
    i = qi[r["id"]]
    dr, sr = ranks(dense[i]), ranks(sparse[i])
    rel = [c for c, g in zip(ret and [x["retrieved_chunk_ids"] for x in ret][0], []) ] # noop
    # relevant 집합 재구성
    relset = [c for c in cid if r["rels"][ret and 0] if False] # noop
    retids = {x["id"]: x["retrieved_chunk_ids"] for x in ret}[r["id"]]
    relset = [c for j, c in enumerate(retids) if r["rels"][j] > 0]
    # top-30 밖 relevant 는 rels로 알 수 없으므로 gt에서 다시
    g = next(x for x in gt if x["id"] == r["id"])
    norm = lambda s: "".join((s or "").split())
    span = norm(g.get("gt_anchor_span"))
    hosts = [c["chunk_id"] for c in chunks if span and span in norm(c["text"])]
    allrel = set(hosts) | {c for c in (g.get("gt_chunk_ids") or []) if c in pos}
    best_d = min(dr[pos[c]] for c in allrel)
    best_s = min(sr[pos[c]] for c in allrel)
    inpool = r["soft_rank"] if r["soft_rank"] else 0
    if best_d > 30 and best_s > 30: k = "dense/BM25 모두 놓침"
    elif inpool: k = "top-30에는 있으나 top-5 밖"
    elif best_d <= 5: k = "dense는 잡았지만 융합에서 밀림"
    elif best_s <= 5: k = "BM25는 잡았지만 융합에서 밀림"
    else: k = "양쪽 다 상위권 아님"
    cat[k] += 1
    top5 = [f"{by[c]['page_title'][:18]}|{by[c].get('sub_category','')[:10]}" for c in r["top5"]]
    lines.append(f"[{k}] {r['id']} {r['bf']}\n  Q: {r['q']}\n  gold: "
                 f"{[by[c]['page_title'][:18] for c in list(allrel)[:3]]} (n={len(allrel)})\n"
                 f"  dense best rank {best_d} · bm25 best rank {best_s} · fused rank {inpool or '>30'}\n"
                 f"  top5: {top5}")
print("=== 유형 분포 ===")
for k, v in cat.most_common(): print(f"  {k}: {v}건")
print()
print("\n".join(lines))
