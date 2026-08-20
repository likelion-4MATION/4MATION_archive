"""gt_natural450.jsonl -> gt_natural430.jsonl : 앵커(gt_anchors/gt_anchor_span) 결측 문항 제외.

--mode has-anchor(기본): gt_anchors 또는 gt_anchor_span이 완전히 빈 문항을 뺀다
  (answerable=false 2건 + 정답 텍스트 자체가 없는 answerable=true 18건 = 20건 제외).
  정답 텍스트가 없으면 span 채점 자체가 성립하지 않으므로, 애초에 span 기준
  평가에는 못 쓰는 문항이다.
--mode full-anchor: and/or 문항은 gold 청크 개수만큼 앵커가 다 있어야 통과.
  fill_anchors.py로 사람이 근거를 보강한 뒤에나 의미가 생기는 조건이라, 지금
  단계(보강 전)에서는 has-anchor만 실질적으로 쓸 수 있다.
(데이터셋_평가셋_수정내역_20260818.md §3·부록)

사용: cd crawler && python filter_anchored.py --gt data/gt_natural450.jsonl
"""
import argparse
import json
from pathlib import Path


def _anchors(item: dict) -> list[str]:
    anchors = item.get("gt_anchors")
    if anchors:
        return [a for a in anchors if a]
    span = item.get("gt_anchor_span")
    return [span] if span else []


def _gold_ids(item: dict) -> list[str]:
    ids = item.get("gt_chunk_ids")
    if ids:
        return list(dict.fromkeys(ids))
    cid = item.get("gt_chunk_id")
    return [cid] if cid else []


def has_anchor(item: dict) -> bool:
    return bool(_anchors(item))


def full_anchor(item: dict) -> bool:
    return len(_anchors(item)) >= len(set(_gold_ids(item)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True, type=Path)
    ap.add_argument("--mode", choices=["has-anchor", "full-anchor"], default="has-anchor")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    items = [json.loads(l) for l in args.gt.open(encoding="utf-8") if l.strip()]
    check = has_anchor if args.mode == "has-anchor" else full_anchor
    kept = [it for it in items if check(it)]

    out = args.out or args.gt.with_name(args.gt.name.replace("450", "430"))
    with out.open("w", encoding="utf-8") as f:
        for it in kept:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"{args.gt} {len(items)}건 --mode {args.mode} -> {out} {len(kept)}건 "
          f"(제외 {len(items) - len(kept)}건)")


if __name__ == "__main__":
    main()
