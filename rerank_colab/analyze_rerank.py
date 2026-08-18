"""Colab 리랭커 점수(rerank_scores.json)를 로컬에서 재평가·분해한다.

리랭킹은 후보 집합을 바꾸지 않고 순서만 바꾸므로, 점수만 있으면 GPU 없이
깊이·블렌딩·cap 스윕과 relation별 분해를 전부 다시 돌릴 수 있다.

핵심 질문: 430(TEST)에서 hit@5가 제자리인 것이 '리랭커가 무능해서'인가,
아니면 'single은 오르고 and는 떨어져 집계가 상쇄돼서'인가.

판정은 eval_anchor_v3 규약을 그대로 쓴다(같은 모듈을 import).

사용:
  cd crawler && python ../rerank_colab/analyze_rerank.py
  cd crawler && python ../rerank_colab/analyze_rerank.py --scores ../rerank_scores.json
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "crawler"))

import eval_anchor_v3 as ev3        # noqa: E402

KS = (1, 3, 5, 10, 30, 50)


def zscore(xs: list[float]) -> list[float]:
    if len(xs) < 2:
        return [0.0] * len(xs)
    m, s = statistics.mean(xs), statistics.pstdev(xs)
    return [0.0] * len(xs) if s == 0 else [(x - m) / s for x in xs]


def reorder(cand: dict, rr: dict, depth: int, w: float, post_cap: int,
            doc_of: dict) -> list[str]:
    """노트북 7번 셀과 동일한 재정렬 규칙."""
    head = cand["candidates"][:depth]
    tail = [x["chunk_id"] for x in cand["candidates"][depth:]]
    zr = zscore([rr[x["chunk_id"]] for x in head])
    zs = zscore([x["score"] for x in head])
    fused = sorted(zip((x["chunk_id"] for x in head),
                       (w * a + (1 - w) * b for a, b in zip(zr, zs))),
                   key=lambda t: -t[1])
    order = [c for c, _ in fused]
    if post_cap:
        seen: dict[str, int] = {}
        keep = []
        for c in order:
            d = doc_of[c]
            if seen.get(d, 0) < post_cap:
                keep.append(c)
                seen[d] = seen.get(d, 0) + 1
        kept = set(keep)
        order = keep + [c for c in order if c not in kept]
    return order + tail


def score(items, orders, chunk_text) -> tuple[dict, int]:
    m = {f"hit@{k}": 0 for k in KS}
    m["mrr"] = 0.0
    n = 0
    for it in items:
        if it.get("answerable") is not True:
            continue
        gold = ev3._get_gt_chunk_ids(it)
        anchors = ev3._get_gt_anchors(it)
        unanchored, _stale = ev3._split_gold_by_anchor(gold, anchors, chunk_text)
        if not anchors and not unanchored:
            continue
        n += 1
        rel = ev3._get_relation(it)
        ids = orders[it["id"]]
        for k in KS:
            if ev3._anchor_hit_at_k(anchors, unanchored, ids, chunk_text, rel, k):
                m[f"hit@{k}"] += 1
        m["mrr"] += ev3._anchor_reciprocal_rank(anchors, unanchored, ids, chunk_text, rel)
    return {k: v / n for k, v in m.items()}, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default=str(ROOT / "rerank_scores.json"))
    ap.add_argument("--inputs", default=str(ROOT / "rerank_colab" / "rerank_inputs.zip"))
    args = ap.parse_args()

    import zipfile
    with zipfile.ZipFile(args.inputs) as z:
        rd = lambda n: [json.loads(l) for l in z.read(n).decode("utf-8").splitlines() if l.strip()]
        chunks = rd("chunks.jsonl")
        meta = json.loads(z.read("meta.json").decode("utf-8"))
        SETS = {n: (rd(f"gt_natural{n}.jsonl"),
                    {c["id"]: c for c in rd(f"candidates_{n}.jsonl")}) for n in ("430", "355")}
    chunk_text = {c["chunk_id"]: ev3._norm_text(c.get("text", "")) for c in chunks}
    doc_of = {c["chunk_id"]: c["parent_doc_id"] for c in chunks}
    RR = json.load(open(args.scores, encoding="utf-8"))

    # 베이스라인 재현 — 여기가 어긋나면 이후 분해가 무의미하다.
    print("=== 베이스라인 재현 ===")
    for name, (items, cands) in SETS.items():
        base = {i: [x["chunk_id"] for x in c["candidates"]] for i, c in cands.items()}
        m, n = score(items, base, chunk_text)
        exp = meta["baseline"][name]["anchor"]["hit@5"]
        print(f"  {name}: n={n} hit@5 {m['hit@5']:.4f} (기대 {exp:.4f}) "
              f"{'OK' if abs(m['hit@5'] - exp) < 1e-6 else '!! 불일치'}")

    CFG = [("430", 50, 0.3, 0), ("430", 50, 0.7, 0), ("430", 50, 1.0, 0),
           ("430", 30, 0.3, 0), ("355", 30, 0.7, 0), ("355", 50, 1.0, 0)]
    print("\n=== relation별 분해 (base → rerank, hit@5) ===")
    for name, depth, w, cap in CFG:
        items, cands = SETS[name]
        base = {i: [x["chunk_id"] for x in c["candidates"]] for i, c in cands.items()}
        new = {i: reorder(c, RR[name][i], depth, w, cap, doc_of) for i, c in cands.items()}
        agg = collections.defaultdict(lambda: [0.0, 0.0, 0])
        for it in items:
            if it.get("answerable") is not True:
                continue
            lab = ev3._get_relation_label(it)
            b, _ = score([it], base, chunk_text)
            r, _ = score([it], new, chunk_text)
            agg[lab][0] += b["hit@5"]
            agg[lab][1] += r["hit@5"]
            agg[lab][2] += 1
        tot_b = sum(v[0] for v in agg.values())
        tot_r = sum(v[1] for v in agg.values())
        tot_n = sum(v[2] for v in agg.values())
        print(f"\n  [{name}] depth={depth} w={w} cap={cap}  "
              f"전체 {tot_b/tot_n:.4f} → {tot_r/tot_n:.4f} ({(tot_r-tot_b)/tot_n:+.4f})")
        for lab, (b, r, n) in sorted(agg.items(), key=lambda t: -t[1][2]):
            # 기여도 = 이 relation이 전체 Δ에 얹은 몫(문항수 가중)
            print(f"    {lab:<10} {n:>3}건  {b/n:.4f} → {r/n:.4f}  ({(r-b)/n:+.4f})"
                  f"  전체기여 {(r-b)/tot_n:+.4f}")

    print("\n=== 'and' 제외 시 스윕 (single/or/near_dup/duplicate/contained만) ===")
    for name in ("430", "355"):
        items, cands = SETS[name]
        sub = [it for it in items if ev3._get_relation_label(it) != "and"]
        base = {i: [x["chunk_id"] for x in c["candidates"]] for i, c in cands.items()}
        b, n = score(sub, base, chunk_text)
        print(f"\n  [{name}] and 제외 {n}문항 · base hit@5 {b['hit@5']:.4f} "
              f"(천장 hit@50 {b['hit@50']:.4f})")
        print(f"    {'depth':>6}{'w':>5}{'cap':>5}{'hit@1':>9}{'hit@3':>9}{'hit@5':>9}{'mrr':>9}{'Δhit@5':>10}")
        for depth in (30, 50):
            for w in (0.3, 0.5, 0.7, 1.0):
                new = {i: reorder(c, RR[name][i], depth, w, 0, doc_of) for i, c in cands.items()}
                m, _ = score(sub, new, chunk_text)
                print(f"    {depth:>6}{w:>5}{0:>5}{m['hit@1']:>9.4f}{m['hit@3']:>9.4f}"
                      f"{m['hit@5']:>9.4f}{m['mrr']:>9.4f}{m['hit@5']-b['hit@5']:>+10.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
