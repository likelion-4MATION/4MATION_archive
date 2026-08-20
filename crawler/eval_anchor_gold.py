"""앵커 스팬 기준 평가 — chunk_id가 아니라 gold 앵커 텍스트 포함 여부로 판정한다.

재청킹으로 chunk_id가 바뀌어도 지표가 깨지지 않는다(phantom chunk 문제의 근본 해결).
"""
import argparse, json, io, sys, collections, pathlib, math
sys.stdout.reconfigure(encoding="utf-8")

KS = (1, 3, 5, 10, 30)
norm = lambda s: "".join((s or "").split())

# 등급 relevance: 앵커 보유 청크=2(정답 근거), GT가 함께 라벨한 gt_chunk_ids=1(답변 가능).
# strict Hit만 보면 GT 스스로 relevant로 표시한 청크를 1위로 뽑아도 실패로 세게 된다.
REL_HOST, REL_GT = 2, 1


def wilson(k, n, z=1.96):
    """이항비율 Wilson 95% CI — n=448에서 정규근사보다 안전하고 한 줄이다."""
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def ndcg(rels, k):
    """rels = 검색 순위대로의 등급 리스트. 이상 정렬 대비 정규화."""
    dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rels[:k]))
    ideal = sum(r / math.log2(i + 2) for i, r in enumerate(sorted(rels, reverse=True)[:k]))
    return dcg / ideal if ideal else 0.0


def load(p): return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]


def evaluate(gt, chunks, retrieved):
    text = {c["chunk_id"]: norm(c["text"]) for c in chunks}
    ret = {r["id"]: r["retrieved_chunk_ids"] for r in retrieved}
    # 앵커를 품은 청크 = 그 문항의 정답 청크 (재청킹에 무관하게 매번 새로 계산)
    rows, no_anchor, no_host = [], [], []
    for g in gt:
        if g.get("answerable") is not True:
            continue
        span = norm(g.get("gt_anchor_span"))
        if not span:
            no_anchor.append(g["id"]); continue
        hosts = {cid for cid, t in text.items() if span in t}
        if not hosts:
            no_host.append(g["id"]); continue
        r = ret.get(g["id"], [])
        rank = next((i for i, c in enumerate(r, 1) if c in hosts), 0)
        # soft = 앵커 청크 ∪ GT가 함께 라벨한 청크 중 첫 적중 순위
        rel = {c: REL_GT for c in (g.get("gt_chunk_ids") or []) if c in text}
        rel.update({c: REL_HOST for c in hosts})
        soft = next((i for i, c in enumerate(r, 1) if c in rel), 0)
        rows.append({"id": g["id"], "bf": g["business_function"], "q": g["question"],
                     "rank": rank, "soft_rank": soft, "n_host": len(hosts),
                     "n_rel": len(rel), "rels": [rel.get(c, 0) for c in r], "top5": r[:5]})
    return rows, no_anchor, no_host


def report(rows, no_anchor, no_host, label):
    n = len(rows)
    print(f"\n=== {label} ===")
    print(f"평가 대상 {n}건 | 앵커 없음 {len(no_anchor)}건 | 앵커를 품은 청크가 코퍼스에 없음 {len(no_host)}건")
    if no_host: print(f"  코퍼스 미수록 앵커: {no_host}")
    hits = {k: sum(1 for r in rows if 0 < r["rank"] <= k) / n for k in KS}
    mrr = sum(1 / r["rank"] for r in rows if 0 < r["rank"] <= 10) / n
    print("| " + " | ".join(f"Hit@{k}" for k in KS) + " | MRR@10 |")
    print("|" + "---:|" * (len(KS) + 1))
    print("| " + " | ".join(f"{hits[k]:.3f}" for k in KS) + f" | {mrr:.3f} |")
    lo, hi = wilson(sum(1 for r in rows if r["rank"] == 1), n)
    print(f"Hit@1 95% CI(Wilson): [{lo:.3f}, {hi:.3f}]  (±{(hi-lo)/2*100:.1f}pp) — "
          f"이보다 작은 차이는 이 평가셋(n={n})으로 구분할 수 없다.")
    soft = {k: sum(1 for r in rows if 0 < r["soft_rank"] <= k) / n for k in (1, 3, 5)}
    nd = {k: sum(ndcg(r["rels"], k) for r in rows) / n for k in (3, 5, 10)}
    print(f"soft(앵커∪gt_chunk_ids) Hit@1 {soft[1]:.3f} · Hit@3 {soft[3]:.3f} · Hit@5 {soft[5]:.3f}")
    print(f"nDCG@3 {nd[3]:.3f} · nDCG@5 {nd[5]:.3f} · nDCG@10 {nd[10]:.3f}"
          f"  (등급: 앵커청크 {REL_HOST} / GT 라벨청크 {REL_GT})")
    print(f"평균 정답청크 수(앵커 보유 청크): {sum(r['n_host'] for r in rows)/n:.2f} · "
          f"평균 relevant 청크 수(등급 포함): {sum(r['n_rel'] for r in rows)/n:.2f}")
    print("\n| 업무 | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 |")
    print("|---|---:|---:|---:|---:|---:|")
    by = collections.defaultdict(list)
    for r in rows: by[r["bf"]].append(r)
    for bf, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        v = [sum(1 for r in rs if 0 < r["rank"] <= k) / len(rs) for k in (1, 3, 5, 10)]
        print(f"| {bf} | {len(rs)} | " + " | ".join(f"{x:.3f}" for x in v) + " |")
    return hits, mrr


def mcnemar(base, new, blabel, nlabel):
    """Hit@1 짝지은 비교 — 개선/악화 건수만으로 이항검정(정확검정, 근사 아님)."""
    b = {r["id"]: r["rank"] == 1 for r in base}
    win = sum(1 for r in new if r["rank"] == 1 and not b.get(r["id"], False))
    los = sum(1 for r in new if r["rank"] != 1 and b.get(r["id"], False))
    n = win + los
    # 양측 이항검정 p (H0: 개선·악화가 동등, p=0.5)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(min(win, los) + 1)) / 2 ** n) if n else 1.0
    print(f"\n=== McNemar Hit@1: {blabel} → {nlabel} ===")
    print(f"개선 {win}건 · 악화 {los}건 · 순 {win-los:+d}건 · 양측 p={p:.4f} "
          f"{'(유의)' if p < 0.05 else '(유의하지 않음 — 노이즈와 구분 불가)'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default="data/gt_natural450_v10_anchor.jsonl")
    ap.add_argument("--chunks", default="data/chunks.jsonl")
    ap.add_argument("--retrieved", default="data/retrieved_top30.jsonl")
    ap.add_argument("--label", default="anchor-gold")
    ap.add_argument("--dump-miss", default="")
    ap.add_argument("--compare", default="", help="비교 대상 retrieved 파일 — McNemar 유의성 검정")
    a = ap.parse_args()
    gt, chunks = load(a.gt), load(a.chunks)
    rows, na, nh = evaluate(gt, chunks, load(a.retrieved))
    report(rows, na, nh, a.label)
    if a.compare:
        base, _, _ = evaluate(gt, chunks, load(a.compare))
        mcnemar(base, rows, a.compare, a.retrieved)
    if a.dump_miss:
        miss = [r for r in rows if not (0 < r["rank"] <= 30)]
        json.dump(miss, io.open(a.dump_miss, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nHit@30 미적중 {len(miss)}건 -> {a.dump_miss}")


if __name__ == "__main__":
    main()
