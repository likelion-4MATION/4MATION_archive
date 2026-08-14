"""앵커 라벨이 없는 문항을 걸러 앵커 판정 전용 GT를 만든다.

배경: 앵커텍스트 판정(eval_anchor_v3 --score anchor)은 `gt_anchors`/`gt_anchor_span`이
있어야 채점된다. 결측 문항을 섞어 두면 평가기가 분모에서 빼주긴 하지만, 셋의 실제
크기와 리포트의 분모가 달라 인용할 때 혼동이 생긴다. 앵커 채점 전용 셋을 따로 두면
"이 파일의 행수 = 분모"가 성립한다.

두 가지 엄격도:
  --mode has-anchor   앵커가 1개라도 있으면 유지(기본). gold 일부만 덮여도 통과 —
                      덮이지 않은 gold는 평가기가 chunk_id로 판정한다(하이브리드).
  --mode full-anchor  gold 청크 '전부'가 앵커로 덮인 문항만 유지. 이 셋의 수치는
                      chunk_id 폴백이 0%인 순수 앵커 판정이다.

full-anchor 판정에는 청크 본문이 필요하므로 --chunks를 읽는다.
레코드는 원본을 그대로 옮긴다 — 필드 추가·수정 없음.

사용:
  python filter_anchored.py --gt ../final_testset/gt_natural450.jsonl
  python filter_anchored.py --gt ... --mode full-anchor
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib

import eval_anchor_v3 as ev3

DEFAULT_CHUNKS = "data/chunks.jsonl"


def load(path: str) -> list[dict]:
    return [json.loads(l) for l in
            pathlib.Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True)
    ap.add_argument("--chunks", default=DEFAULT_CHUNKS)
    ap.add_argument("--mode", default="has-anchor", choices=("has-anchor", "full-anchor"))
    ap.add_argument("--out", default=None, help="기본: <gt 폴더>/gt_natural<N>.jsonl")
    args = ap.parse_args()

    rows = load(args.gt)
    chunk_text = {c["chunk_id"]: ev3._norm_text(c.get("text", ""))
                  for c in load(args.chunks)}

    kept, dropped = [], collections.Counter()
    for r in rows:
        anchors = ev3._get_gt_anchors(r)
        if not anchors:
            dropped["앵커 없음"] += 1
            continue
        gold = ev3._get_gt_chunk_ids(r)
        unanchored = ev3._split_gold_by_anchor(gold, anchors, chunk_text)
        if args.mode == "full-anchor" and unanchored:
            dropped["gold 일부만 덮임"] += 1
            continue
        kept.append(r)

    out = args.out or str(pathlib.Path(args.gt).parent / f"gt_natural{len(kept)}.jsonl")
    pathlib.Path(out).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
    sha = hashlib.sha256(pathlib.Path(out).read_bytes()).hexdigest()

    print(f"[in ] {args.gt} · {len(rows)}행 · mode={args.mode}")
    print(f"       제외 {dict(dropped)} (총 {sum(dropped.values())}건)")
    print(f"[out] {out} · {len(kept)}행 · sha256 {sha[:16]}…")

    ans = collections.Counter(str(r.get("answerable")) for r in kept)
    rel = collections.Counter(ev3._get_relation_label(r) for r in kept)
    # 유지된 문항 중 gold가 일부만 덮인 비율 = 평가 시 chunk_id 폴백 의존도.
    part = sum(1 for r in kept
               if ev3._split_gold_by_anchor(ev3._get_gt_chunk_ids(r),
                                            ev3._get_gt_anchors(r), chunk_text))
    print(f"       answerable {dict(ans)} · relation {dict(rel)}")
    print(f"       gold 일부만 덮인 문항 {part}/{len(kept)} "
          f"(= 평가 시 id 의존도 {part / (len(kept) or 1):.1%})")

    assert all(ev3._get_gt_anchors(r) for r in kept), "앵커 없는 행이 남았다"
    ids = [r["id"] for r in kept]
    assert len(set(ids)) == len(ids), "id 중복"
    print(f"[검증] 전건 앵커 보유 · id 유일 {len(ids)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
