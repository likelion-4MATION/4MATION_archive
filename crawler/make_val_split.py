"""gt_natural505.jsonl -> gt_natural355.jsonl (answerable==True 필터).

505 = VAL 원본(answerable True 355 + False 150). unanswerable은 gold 청크가
없어 hit@k 분모에 들어갈 수 없으므로, 정답 매칭 평가용 서브셋만 따로 둔다.
(데이터셋_평가셋_수정내역_20260818.md §2·§3)

사용: cd crawler && python make_val_split.py
"""
import json
from pathlib import Path

SRC = Path("data/gt_natural505.jsonl")
DST = Path("data/gt_natural355.jsonl")


def main() -> None:
    items = [json.loads(l) for l in SRC.open(encoding="utf-8") if l.strip()]
    kept = [it for it in items if it.get("answerable") is True]
    with DST.open("w", encoding="utf-8") as f:
        for it in kept:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"{SRC} {len(items)}건 -> {DST} {len(kept)}건 (answerable=True만)")


if __name__ == "__main__":
    main()
