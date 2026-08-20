"""cap 변형 A/B — 절단(cap) vs 밀어내기(capq).

cap: 문서당 cap개 초과 청크를 목록에서 제거 → top-5 다양성↑, 대신 Hit@30 recall 손실.
capq: 초과분을 제거하지 않고 뒤로 미룸(순열) → top-30 구성이 그대로라 Hit@30 무손실.
"""
import sys, pathlib, collections
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rag
from eval_fusion_sweep import Fuser, get_cache, D
from eval_anchor_gold import evaluate, load
from eval_hit5 import metrics, mcnemar

gt = [g for g in load(D / "gt_natural450_v10_anchor.jsonl") if g.get("answerable") is True]
chunks = load(D / "chunks.jsonl")
dense, sparse, toks = get_cache(gt, chunks)
fuser = Fuser(chunks)
doc = {c["chunk_id"]: c["parent_doc_id"] for c in chunks}
bfs = [rag.classify_query_bf(g["question"]) for g in gt]
facs = [rag.query_facets(g["question"]) for g in gt]


def defer(order, cap):
    """문서당 cap개를 넘는 청크는 버리지 않고 뒤로 미룬다(라운드 단위 인터리브)."""
    seen, head, tail = collections.Counter(), [], []
    for c in order:
        d = doc[c]
        if seen[d] < cap:
            head.append(c); seen[d] += 1
        else:
            tail.append(c)
    return head + (defer(tail, cap) if tail else [])


def run(cap=0, capq=0, **kw):
    ret = []
    for i, g in enumerate(gt):
        o = fuser.rank(i, dense, sparse, toks[i], bf=bfs[i], facets=facs[i],
                       k=len(chunks), cap=cap, **kw)
        if capq:
            o = defer(o, capq)
        ret.append({"id": g["id"], "retrieved_chunk_ids": o[:30]})
    rows, _, _ = evaluate(gt, chunks, ret)
    return rows


base = run()
print("| 변형 | softH@5 | 짝수반 | 홀수반 | softH@1 | nDCG@5 | H@30 | win/los, p |")
print("|---|---:|---:|---:|---:|---:|---:|---|")
for name, kw in [("baseline", {}), ("cap=3(절단)", dict(cap=3)),
                 *[(f"capq={c}(밀어내기)", dict(capq=c)) for c in (1, 2, 3, 4)]]:
    rows = run(**kw)
    m = metrics(rows)
    ev = metrics([r for i, r in enumerate(rows) if i % 2 == 0])["S5"]
    od = metrics([r for i, r in enumerate(rows) if i % 2 == 1])["S5"]
    w, l, p = mcnemar(base, rows, lambda r: 0 < r["soft_rank"] <= 5)
    print(f"| {name} | {m['S5']:.4f} | {ev:.4f} | {od:.4f} | {m['S1']:.4f} | "
          f"{m['nDCG5']:.4f} | {m['S30']:.4f} | {w}/{l}, p={p:.3f} |")
