"""앵커 스팬 기준 평가 — chunk_id가 아니라 gold 앵커 텍스트 포함 여부로 판정한다.

재청킹으로 chunk_id가 바뀌어도 지표가 깨지지 않는다(phantom chunk 문제의 근본 해결).
"""
import argparse, json, io, sys, collections, pathlib
sys.stdout.reconfigure(encoding="utf-8")

KS = (1, 3, 5, 10, 30)
norm = lambda s: "".join((s or "").split())


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
        rows.append({"id": g["id"], "bf": g["business_function"], "q": g["question"],
                     "rank": rank, "n_host": len(hosts), "top5": r[:5]})
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
    print(f"평균 정답청크 수(앵커 보유 청크): {sum(r['n_host'] for r in rows)/n:.2f}")
    print("\n| 업무 | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 |")
    print("|---|---:|---:|---:|---:|---:|")
    by = collections.defaultdict(list)
    for r in rows: by[r["bf"]].append(r)
    for bf, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        v = [sum(1 for r in rs if 0 < r["rank"] <= k) / len(rs) for k in (1, 3, 5, 10)]
        print(f"| {bf} | {len(rs)} | " + " | ".join(f"{x:.3f}" for x in v) + " |")
    return hits, mrr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default="data/gt_natural450_v10_anchor.jsonl")
    ap.add_argument("--chunks", default="data/chunks.jsonl")
    ap.add_argument("--retrieved", default="data/retrieved_top30.jsonl")
    ap.add_argument("--label", default="anchor-gold")
    ap.add_argument("--dump-miss", default="")
    a = ap.parse_args()
    rows, na, nh = evaluate(load(a.gt), load(a.chunks), load(a.retrieved))
    report(rows, na, nh, a.label)
    if a.dump_miss:
        miss = [r for r in rows if not (0 < r["rank"] <= 30)]
        json.dump(miss, io.open(a.dump_miss, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nHit@30 미적중 {len(miss)}건 -> {a.dump_miss}")


if __name__ == "__main__":
    main()
