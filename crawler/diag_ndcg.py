"""nDCG@5 병목 분해 — 손실을 '순서'와 '회수'로 쪼개고, 정답 위에 올라온 청크의 패턴을 센다.

Hit@5(soft) 0.920 vs nDCG@5 0.705의 간극은 두 원인이 섞여 있다:
  (a) 순서 손실 — top-5 안에 있지만 3~5위로 밀림
  (b) 회수 손실 — relevant가 여러 개인데 top-5에 일부만 들어옴 (nDCG의 ideal은 전부 요구)
둘은 처방이 다르다(리랭킹 vs 다양성/확장). 먼저 비중부터 잰다.
"""
import io, json, sys, math, collections, pathlib
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from eval_anchor_gold import evaluate, load, ndcg

D = pathlib.Path(__file__).resolve().parent / "data"
gt = [g for g in load(D / "gt_natural450_v10_anchor.jsonl") if g.get("answerable") is True]
chunks = load(D / "chunks.jsonl")
ret = load(D / sys.argv[1] if len(sys.argv) > 1 else D / "retrieved_top30_kunam.jsonl")
rows, _, _ = evaluate(gt, chunks, ret)
by_id = {c["chunk_id"]: c for c in chunks}
idx_of = {c["chunk_id"]: i for i, c in enumerate(chunks)}
retmap = {r["id"]: r["retrieved_chunk_ids"] for r in ret}
z = np.load(D / "qscore_cache.npz", allow_pickle=False)
dense, sparse = z["dense"], z["sparse"]
qpos = {q: i for i, q in enumerate(z["ids"])}
drank = {i: {c: r for r, c in enumerate(np.argsort(dense[i])[::-1], 1)} for i in range(len(dense))}
srank = {i: {c: r for r, c in enumerate(np.argsort(sparse[i])[::-1], 1)} for i in range(len(sparse))}

dcg = lambda rs: sum(r / math.log2(i + 2) for i, r in enumerate(rs))
n = len(rows)

# ── 1. 손실 분해 ────────────────────────────────────────────────────────
tot_a = tot_c = 0.0
buckets = collections.Counter()
order_loss_rows, recall_loss_rows = [], []
for r in rows:
    rels = r["rels"]
    ideal = dcg(sorted(rels, reverse=True)[:5])
    if not ideal:
        continue
    a = dcg(rels[:5]) / ideal                       # 실제
    c = dcg(sorted(rels[:5], reverse=True)) / ideal  # top-5 구성은 그대로, 순서만 최적
    tot_a += a; tot_c += c
    r["ndcg5"], r["ceil5"] = a, c
    lo, lr = c - a, 1 - c
    if lo > 1e-9: order_loss_rows.append((lo, r))
    if lr > 1e-9: recall_loss_rows.append((lr, r))
    buckets[("완전" if a > 0.999 else "순서손실 우세" if lo >= lr else "회수손실 우세")] += 1

print(f"=== nDCG@5 손실 분해 (n={n}) ===")
print(f"실제 nDCG@5        {tot_a/n:.3f}")
print(f"top-5 순서만 최적화 {tot_c/n:.3f}  ← 리랭킹으로 도달 가능한 천장")
print(f"손실 총 {1-tot_a/n:.3f} = 순서 {tot_c/n-tot_a/n:.3f} + 회수 {1-tot_c/n:.3f}")
print("  회수 = relevant가 top-5 밖(또는 top-30 안 다른 자리)에 남아 ideal을 못 채움")
for k, v in buckets.most_common():
    print(f"  {k}: {v}건 ({v/n:.1%})")

# ── 2. relevant 개수별 ──────────────────────────────────────────────────
print("\n=== relevant 청크 수(n_rel)별 ===")
print("| n_rel | 문항 | nDCG@5 | 순서천장 | soft Hit@5 | top-5에 든 relevant 평균 |")
print("|---:|---:|---:|---:|---:|---:|")
g = collections.defaultdict(list)
for r in rows:
    if "ndcg5" in r: g[min(r["n_rel"], 4)].append(r)
for k in sorted(g):
    rs = g[k]
    inn = sum(sum(1 for x in r["rels"][:5] if x) for r in rs) / len(rs)
    print(f"| {k}{'+' if k == 4 else ''} | {len(rs)} | {sum(r['ndcg5'] for r in rs)/len(rs):.3f} | "
          f"{sum(r['ceil5'] for r in rs)/len(rs):.3f} | "
          f"{sum(1 for r in rs if 0 < r['soft_rank'] <= 5)/len(rs):.3f} | {inn:.2f} |")

# ── 3. 앵커가 3~5위로 밀린 문항: 위에 올라온 침입자 패턴 ────────────────
print("\n=== 앵커가 3~5위 (n=%d) — 그 위를 차지한 청크의 정체 ===" %
      sum(1 for r in rows if 3 <= r["rank"] <= 5))
pat = collections.Counter()
lendiff, dr_int, dr_anc, sr_int, sr_anc = [], [], [], [], []
samples = []
for r in rows:
    if not (3 <= r["rank"] <= 5):
        continue
    qi = qpos[r["id"]]
    order = retmap[r["id"]]
    anc = order[r["rank"] - 1]
    ai = idx_of[anc]
    ac = by_id[anc]
    ups = []
    for cid in order[:r["rank"] - 1]:
        c, ci = by_id[cid], idx_of[cid]
        tags = []
        if r["rels"][order.index(cid)]: tags.append("relevant(등급1)")
        if c["parent_doc_id"] == ac["parent_doc_id"]: tags.append("같은문서")
        elif c.get("business_function") != ac.get("business_function"): tags.append("타업무")
        else: tags.append("동업무 형제문서")
        if len(c["text"]) < len(ac["text"]) * 0.6: tags.append("짧은청크")
        if drank[qi][ci] < drank[qi][ai] and srank[qi][ci] > srank[qi][ai]: tags.append("dense만 우세")
        if srank[qi][ci] < srank[qi][ai] and drank[qi][ci] > drank[qi][ai]: tags.append("BM25만 우세")
        for t in tags: pat[t] += 1
        lendiff.append(len(c["text"]) / max(len(ac["text"]), 1))
        dr_int.append(drank[qi][ci]); sr_int.append(srank[qi][ci])
        ups.append((cid, tags))
    dr_anc.append(drank[qi][ai]); sr_anc.append(srank[qi][ai])
    samples.append((r, ups))
tot_up = sum(len(u) for _, u in samples)
print(f"침입 청크 총 {tot_up}건")
for k, v in pat.most_common():
    print(f"  {k}: {v} ({v/tot_up:.1%})")
print(f"길이비(침입/앵커) 중앙값 {np.median(lendiff):.2f}")
print(f"앵커 dense순위 중앙값 {np.median(dr_anc):.0f} · 침입자 {np.median(dr_int):.0f}")
print(f"앵커 BM25순위 중앙값 {np.median(sr_anc):.0f} · 침입자 {np.median(sr_int):.0f}")

print("\n--- 사례 8건 ---")
for r, ups in samples[:8]:
    print(f"[{r['bf']}] {r['id']} rank={r['rank']} · {r['q'][:46]}")
    for cid, tags in ups:
        print(f"    ↑ {cid} :: {', '.join(tags)}")
