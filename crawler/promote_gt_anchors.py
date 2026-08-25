"""gt_anchor_span(문자열 1개) → gt_anchors(리스트) 스키마 승격.

배경: `gt_anchor_span`은 문자열 1개인데 `chunk_relation='and'`의 gold는 2~4개다.
450셋 실측상 gold 청크 555개 중 434개(78.2%)만 앵커가 덮어, 앵커만으로는 'and'의
ALL 조건을 세울 수 없다(69문항). 그래서 판정이 ALL이 아니라 ANY로 느슨해져 있었다.

이 스크립트가 하는 일 — 결정론적 변환만:
  1. `gt_anchors` 리스트 필드 신설. 기존 `gt_anchor_span`은 지우지 않고 병존한다
     (docs/앵커텍스트_정답라벨링_파이프라인.md ② "gt_docs 병존 → 점진 전환" 원칙).
  2. 각 gold 청크가 앵커로 덮이는지 실측해 커버리지를 리포트한다.

이 스크립트가 하지 않는 일:
  **앵커를 만들어내지 않는다.** 앵커 없는 gold 청크의 근거 문장은 원문에 라벨이 없어
  결정론적으로 도출할 수 없다. 추론으로 채우면 창작이므로 비워 두고 건수로 드러낸다.
  그 칸을 메우는 것은 라벨 작업(파이프라인 문서 ① 앵커 선정)의 몫이며, 그 전까지
  eval.py chunk 판정은 앵커 없는 gold를 chunk_id로 판정한다(하이브리드).

사용:
  python promote_gt_anchors.py --gt gt_testset_retrieval_450.jsonl
  python promote_gt_anchors.py --gt ... --out data/gt_450_v2.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import unicodedata

DEFAULT_GT = "gt_testset_retrieval_450.jsonl"
DEFAULT_CHUNKS = "data/chunks.jsonl"


def norm_text(text: str) -> str:
    """eval._norm_text와 동일 규칙 — 공백만 흡수, 문자는 보존."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def gold_ids(item: dict) -> list[str]:
    ids = item.get("gt_chunk_ids") or ([item["gt_chunk_id"]] if item.get("gt_chunk_id") else [])
    if isinstance(ids, str):
        ids = [ids]
    return list(dict.fromkeys(ids))


def existing_anchors(item: dict) -> list[str]:
    """이미 gt_anchors가 있으면 그것을, 없으면 gt_anchor_span 1개를 씨앗으로 쓴다(멱등)."""
    anchors = item.get("gt_anchors")
    if isinstance(anchors, str):
        anchors = [anchors]
    if anchors:
        return list(dict.fromkeys(a for a in anchors if a and a.strip()))
    span = item.get("gt_anchor_span")
    return [span] if span and span.strip() else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default=DEFAULT_GT)
    ap.add_argument("--chunks", default=DEFAULT_CHUNKS)
    ap.add_argument("--out", default=None, help="기본: <gt>_anchors.jsonl (원본 무수정)")
    args = ap.parse_args()

    rows = [json.loads(l) for l in
            pathlib.Path(args.gt).read_text(encoding="utf-8").splitlines() if l.strip()]
    chunks = {c["chunk_id"]: norm_text(c.get("text", "")) for c in
              (json.loads(l) for l in
               pathlib.Path(args.chunks).read_text(encoding="utf-8").splitlines() if l.strip())}

    out_path = args.out or args.gt.replace(".jsonl", "_anchors.jsonl")
    total_gold = covered_gold = 0
    per_rel = collections.Counter()
    unanchored_by_rel = collections.Counter()
    n_full = n_partial = n_none = 0
    missing_chunk = set()

    for item in rows:
        anchors = existing_anchors(item)
        item["gt_anchors"] = anchors
        if item.get("answerable") is not True:
            continue
        gold = gold_ids(item)
        rel = item.get("chunk_relation") or "single"
        na = [norm_text(a) for a in anchors]
        covered = [c for c in gold
                   if c in chunks and any(a in chunks[c] for a in na)]
        missing_chunk |= {c for c in gold if c not in chunks}
        total_gold += len(gold)
        covered_gold += len(covered)
        per_rel[rel] += 1
        gap = len(gold) - len(covered)
        unanchored_by_rel[rel] += gap
        if not anchors:
            n_none += 1
        elif gap:
            n_partial += 1
        else:
            n_full += 1

    pathlib.Path(out_path).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    print(f"[in ] {args.gt} · {len(rows)}행")
    print(f"[out] {out_path} · gt_anchors 필드 추가(gt_anchor_span 병존)")
    print()
    print("=== gold 청크 앵커 커버리지 (answerable=true 기준) ===")
    print(f"  gold 청크 {total_gold}개 중 앵커가 덮는 것 {covered_gold}개 "
          f"({covered_gold / total_gold:.1%}) · 앵커 없음 {total_gold - covered_gold}개")
    print(f"  relation별 앵커 없는 gold 수: {dict(unanchored_by_rel)}")
    print()
    print("=== 문항 분류 ===")
    print(f"  전부 앵커로 덮임 : {n_full}건  (앵커만으로 판정 가능)")
    print(f"  일부만 덮임      : {n_partial}건 (나머지 gold는 chunk_id 폴백)")
    print(f"  앵커 없음        : {n_none}건  (전부 chunk_id 폴백)")
    if missing_chunk:
        print(f"\n  ! 코퍼스에 없는 gold 청크 {len(missing_chunk)}개 — "
              f"청킹과 GT 버전이 어긋났을 수 있음: {sorted(missing_chunk)[:3]}")
    print("\n라벨 작업 필요분: 앵커 없는 gold 청크 "
          f"{total_gold - covered_gold}개 (파이프라인 문서 ① 앵커 선정).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
