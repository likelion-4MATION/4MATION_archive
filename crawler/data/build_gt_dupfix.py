"""GT 보강 — anchor_span이 gold 외 다른 청크에도 verbatim으로 등장하면 그 청크를 gt_chunk_ids에 추가.

배경: eval_report_450.md 진단 결과, KDIC 사이트에 동일 콘텐츠를 담은 페이지가
여러 URL로 중복 게재된 사례가 다수 발견됨(예: 은닉재산 신고 FAQ가 사이트 페이지와
통합게시판 양쪽에 그대로 미러링). 단일 gold만 인정하면 리트리버가 내용상 동등한
"다른 쪽" 청크를 골랐을 때도 미적중으로 잘못 집계된다.

판정: gt_anchor_span(공백 제거)이 gold가 아닌 다른 청크 본문(공백 제거)에
부분 문자열로 그대로 들어있으면 그 청크를 근거로 추가한다(LLM 미개입, 결정론).
"""
from __future__ import annotations

import json
import re

SRC = "gt_natural450_v9_dupfix2.jsonl"
DST = "gt_natural450_v9_dupfix2.jsonl"
CHUNKS = "chunks.jsonl"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def main() -> None:
    chunks = [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]
    chunk_norm = {c["chunk_id"]: norm(c["text"]) for c in chunks}

    rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]
    n_changed = 0
    for r in rows:
        if not r.get("answerable"):
            continue
        span = r.get("gt_anchor_span") or ""
        if len(span) < 15:
            continue
        span_n = norm(span)
        gold = list(dict.fromkeys(r.get("gt_chunk_ids") or ([r["gt_chunk_id"]] if r.get("gt_chunk_id") else [])))
        gold_set = set(gold)
        dup = [cid for cid, txt in chunk_norm.items() if cid not in gold_set and span_n in txt]
        if dup:
            r["gt_chunk_ids"] = gold + dup
            n_changed += 1

    with open(DST, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{n_changed}/{len(rows)}건 gt_chunk_ids 보강 → {DST}")


if __name__ == "__main__":
    main()
