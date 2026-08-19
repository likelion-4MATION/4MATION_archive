"""GT 보강 2단계 — 패러프레이즈(비-verbatim) 중복 청크 탐지.

1단계(build_gt_dupfix.py)는 anchor_span이 문자 그대로 다른 청크에도 등장하는
경우만 잡았다. 실제로는 KDIC 사이트가 같은 사실(금액/기간/제외사유 등)을
표현만 바꿔 여러 페이지·FAQ에 중복 게재하는 경우가 더 많다 — 이건 verbatim
매칭으로 못 잡는다.

판정 근거(결정론, LLM 미개입):
- "사실 앵커" = anchor_span 안의 숫자열(금액/기간/퍼센트 등). 후보 청크가 그
  숫자열을 전부 포함하면 같은 사실을 진술한다는 강한 증거로 본다.
- 숫자 앵커가 있는 문항: 후보가 숫자를 전부 포함 + (본문 유사도 or 임베딩
  유사도) 최소 기준 통과 → 자동 채택.
- 숫자 앵커가 없는 문항(정성적 사실): 임베딩/본문 유사도 둘 다 훨씬 높은
  기준을 요구 → 자동 채택. 애매하면 채택하지 않고 리뷰 목록에만 남긴다.

출력:
- data/gt_natural450_v9_dupfix2.jsonl — 자동 채택분만 반영한 최종 GT
- data/dupfix_v2_ambiguous.md — 애매해서 자동 채택 안 한 후보(사람 리뷰용)
"""
from __future__ import annotations

import difflib
import json
import re

import numpy as np

SRC_GT = "gt_natural450_v9_dupfix2.jsonl"
DST_GT = "gt_natural450_v9_dupfix2.jsonl"
AMBIG_REPORT = "dupfix_v2_ambiguous.md"
CHUNKS = "chunks.jsonl"
EMB_PATH = "index/emb.npy"
META_PATH = "index/chunk_meta.jsonl"

# 자동 채택 임계값(그리드/직관 없이 보수적으로 고정 — 오탐보다 미채택을 우선).
NUM_ANCHOR_EMB_MIN = 0.75   # 숫자 사실 일치 + 이 정도 임베딩 유사도면 채택
NUM_ANCHOR_TEXT_MIN = 0.30  # 또는 숫자 사실 일치 + 이 정도 본문 유사도면 채택
NO_NUM_EMB_MIN = 0.90       # 숫자 앵커 없을 때는 훨씬 높은 임베딩 유사도 요구
NO_NUM_TEXT_MIN = 0.55      # 또는 훨씬 높은 본문 유사도
AMBIG_EMB_MIN = 0.70        # 이 밑은 애매 후보로도 취급 안 함(노이즈)


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def numbers_in(s: str) -> set[str]:
    return set(re.findall(r"\d[\d,\.]*\d|\d", s or ""))


def text_sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def main() -> None:
    chunks = [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]
    meta = [json.loads(l) for l in open(META_PATH, encoding="utf-8")]
    emb = np.load(EMB_PATH)
    assert [c["chunk_id"] for c in chunks] == [m["chunk_id"] for m in meta], "emb.npy 순서 불일치"
    ids = [c["chunk_id"] for c in chunks]
    idx_of = {cid: i for i, cid in enumerate(ids)}
    text_of = {cid: c["text"] for cid, c in zip(ids, chunks)}
    norm_of = {cid: norm(t) for cid, t in text_of.items()}

    rows = [json.loads(l) for l in open(SRC_GT, encoding="utf-8")]
    n_auto, n_ambig = 0, 0
    ambig_lines = ["# Phase 2 dupfix — 애매해서 자동 채택 안 한 후보\n"]

    for r in rows:
        if not r.get("answerable"):
            continue
        span = r.get("gt_anchor_span") or ""
        if len(span) < 10:
            continue
        gold = list(dict.fromkeys(
            r.get("gt_chunk_ids") or ([r["gt_chunk_id"]] if r.get("gt_chunk_id") else [])))
        gold_set = set(gold)
        if not gold_set:
            continue
        span_nums = numbers_in(span)
        gold_embs = np.stack([emb[idx_of[g]] for g in gold if g in idx_of])
        if gold_embs.size == 0:
            continue

        accepted, ambiguous = [], []
        for cid in ids:
            if cid in gold_set:
                continue
            e_sim = float(np.max(gold_embs @ emb[idx_of[cid]]))  # 정규화 임베딩 → 코사인
            if e_sim < AMBIG_EMB_MIN:
                continue
            t_sim = max(text_sim(norm_of[g], norm_of[cid]) for g in gold if g in norm_of)

            if span_nums:
                has_all_nums = span_nums.issubset(numbers_in(text_of[cid]))
                is_dup = has_all_nums and (e_sim >= NUM_ANCHOR_EMB_MIN or t_sim >= NUM_ANCHOR_TEXT_MIN)
            else:
                has_all_nums = None
                is_dup = e_sim >= NO_NUM_EMB_MIN or t_sim >= NO_NUM_TEXT_MIN

            if is_dup:
                accepted.append((cid, e_sim, t_sim))
            else:
                ambiguous.append((cid, e_sim, t_sim, has_all_nums))

        if accepted:
            r["gt_chunk_ids"] = gold + [cid for cid, _, _ in accepted]
            n_auto += 1
        if ambiguous:
            n_ambig += 1
            ambig_lines.append(f"\n## {r['id']} ({r.get('business_function')}) — {r['question']}")
            ambig_lines.append(f"gold: {gold}")
            ambig_lines.append(f"anchor: {span[:150]}")
            for cid, e_sim, t_sim, has_nums in sorted(ambiguous, key=lambda x: -x[1])[:5]:
                ambig_lines.append(f"- `{cid}` emb={e_sim:.3f} text={t_sim:.3f} 숫자일치={has_nums}")

    with open(DST_GT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(AMBIG_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(ambig_lines) + "\n")

    print(f"자동 채택: {n_auto}건 → {DST_GT}")
    print(f"애매(리뷰 필요): {n_ambig}건 → {AMBIG_REPORT}")


if __name__ == "__main__":
    main()
