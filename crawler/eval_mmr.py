# -*- coding: utf-8 -*-
"""MMR vs cap A/B (실험 B) — hybrid_bf의 다양성 단계를 cap ↔ MMR로 교체 비교.

설계 원칙: '다양성 단계'를 diversify(method=...) 하나로 추상화 →
  cap / mmr / none 을 파라미터로 교체. 이 구조 그대로 나중에 rag.py에 이식하면
  rag는 DIVERSITY 상수 하나만 바꿔 cap↔mmr 전환 가능(무수정 실험은 여기서).

파이프라인(공통): 업무 하드필터로 uncapped 후보 풀(FETCH_K) → 다양성 단계 → top-k.
  · cap : parent_doc_id당 CAP개 (현행 hybrid_bf가 이것, CAP=1)
  · mmr : λ·cos(q,d) − (1−λ)·max cos(d, 이미뽑은것)  (self 임베딩 재사용, 인덱스 무변경)
  · none: 그대로 top-k

정답 판정: top-k 청크의 parent_doc_id가 gt_docs에 포함되면 적중(eval_TF와 동일 문서단위).
비교 기준선: hybrid_bf(ref) = rag의 실제 배포 모드(pool=max(k*5,50)+cap1).

사용: cd crawler && python eval_mmr.py   (ko-sroberta만 필요, 리랭커 불필요)
"""
from __future__ import annotations
import collections
import json

import numpy as np
import rag

TESTSET = "data/testset_natural_300_v3.jsonl"
EMB_PATH = "data/index/emb.npy"     # chunk_meta.jsonl 순서와 정렬된 정규화 임베딩
FETCH_K = 20     # 다양성 단계 입력 후보 풀(uncapped)
KMAX = 10
CAP = 1
LAMBDAS = [0.3, 0.5, 0.7]


def first_doc_rank(chunks, gt):
    for r, c in enumerate(chunks, 1):
        if c["parent_doc_id"] in gt:
            return r
    return 0


# ── 다양성 단계 (cap ↔ mmr 교체 지점) ─────────────────────────────
def _cap(cand_idx, chunks, k, cap):
    seen = collections.Counter(); out = []
    for i in cand_idx:
        d = chunks[i]["parent_doc_id"]
        if seen[d] < cap:
            out.append(i); seen[d] += 1
        if len(out) >= k:
            break
    return out


def _mmr(cand_idx, k, qvec, E, lam):
    if not cand_idx:
        return []
    Ec = E[cand_idx]                 # (m, d), 정규화됨
    rel = Ec @ qvec                  # (m,) = cos(q, d)
    sim = Ec @ Ec.T                  # (m, m) = cos(d_i, d_j)
    m = len(cand_idx)
    selected = [int(np.argmax(rel))]
    remaining = set(range(m)) - set(selected)
    while remaining and len(selected) < k:
        best, best_s = None, -1e18
        for j in remaining:
            red = max(sim[j][s] for s in selected)     # 이미 뽑은 것과의 최대 유사
            s = lam * rel[j] - (1 - lam) * red
            if s > best_s:
                best_s, best = s, j
        selected.append(best); remaining.discard(best)
    return [cand_idx[i] for i in selected]


def diversify(cand_idx, method, k, *, chunks, qvec=None, E=None, cap=CAP, lam=0.5):
    if method == "none":
        return cand_idx[:k]
    if method == "cap":
        return _cap(cand_idx, chunks, k, cap)
    if method == "mmr":
        return _mmr(cand_idx, k, qvec, E, lam)
    raise ValueError(method)


def evaluate(searcher, E, testset, method, lam=0.5):
    h1 = h3 = 0; mrr = 0.0
    per_bf = collections.defaultdict(lambda: [0, 0])
    rep_hit = rep_n = 0
    per_q = []
    for it in testset:
        gt = set(it["gt_docs"])
        if method == "ref":     # rag 실제 hybrid_bf (pool 50 + cap1)
            hits = searcher.search(it["question"], k=KMAX, mode="hybrid_bf")
        else:
            bf = rag.classify_query_bf(it["question"])
            pool = searcher.hybrid(it["question"], FETCH_K, bf=bf)   # uncapped
            cand = [i for i, _ in pool]
            qvec = rag.embed_texts([it["question"]])[0] if method == "mmr" else None
            sel = diversify(cand, method, KMAX, chunks=searcher.chunks,
                            qvec=qvec, E=E, lam=lam)
            hits = [searcher.chunks[i] for i in sel]
        r = first_doc_rank(hits, gt)
        hit1, hit3 = (r == 1), (1 <= r <= 3)
        h1 += hit1; h3 += hit3; mrr += (1.0 / r if r else 0.0)
        b = per_bf[it["business_function"]]; b[0] += hit3; b[1] += 1
        if it["representative"]:
            rep_n += 1; rep_hit += hit3
        per_q.append({"q": it["question"], "hit3": hit3})
    n = len(testset)
    label = method if method != "mmr" else f"mmr@{lam}"
    return {"label": label, "hit@1": h1 / n, "hit@3": h3 / n, "mrr": mrr / n,
            "rep": f"{rep_hit}/{rep_n}", "per_bf": per_bf, "per_q": per_q}


def main():
    testset = [json.loads(l) for l in open(TESTSET, encoding="utf-8")]
    searcher = rag.Searcher()
    E = np.load(EMB_PATH)
    assert E.shape[0] == len(searcher.chunks), "emb.npy와 chunk_meta 정렬 불일치"

    runs = [evaluate(searcher, E, testset, "ref"),
            evaluate(searcher, E, testset, "cap")]
    for lam in LAMBDAS:
        runs.append(evaluate(searcher, E, testset, "mmr", lam))

    print(f"평가셋 {len(testset)}건 · FETCH_K={FETCH_K} · cap={CAP}\n")
    print(f"{'method':12} {'hit@1':>7} {'hit@3':>7} {'MRR':>7} {'대표6':>6}")
    for r in runs:
        print(f"{r['label']:12} {r['hit@1']:>7.3f} {r['hit@3']:>7.3f} {r['mrr']:>7.3f} {r['rep']:>6}")

    base = runs[0]                       # hybrid_bf(ref)
    best = max(runs[2:], key=lambda r: r["hit@3"])
    print(f"\n[업무별 hit@3 — ref → {best['label']}]")
    for bf in sorted(base["per_bf"], key=lambda b: -base["per_bf"][b][1]):
        bh, bn = base["per_bf"][bf]; rh, rn = best["per_bf"][bf]
        print(f"  {bf:16} {bh/bn:.3f} -> {rh/rn:.3f}  ({rh/rn - bh/bn:+.3f})")

    bmap = {p["q"]: p["hit3"] for p in base["per_q"]}
    gained = [p["q"] for p in best["per_q"] if p["hit3"] and not bmap.get(p["q"])]
    lost = [p["q"] for p in best["per_q"] if not p["hit3"] and bmap.get(p["q"])]
    print(f"\n[{best['label']} vs ref] hit@3 {base['hit@3']:.3f} -> {best['hit@3']:.3f} "
          f"({best['hit@3']-base['hit@3']:+.3f}) · 회복 {len(gained)} · 퇴행 {len(lost)}")
    if lost:
        for q in lost: print(f"   퇴행: {q}")


if __name__ == "__main__":
    main()
