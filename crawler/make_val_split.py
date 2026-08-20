"""VAL 셋 분리 — gt_natural882에서 TEST(450)와 겹치지 않는 문항만 떼어낸다.

평가셋 역할 규약(2026-08-14 확정):
  TEST = final_testset/gt_natural450.jsonl  (450건)
  VAL  = 882 − (450과 질문이 겹치는 377건) = 505건
         그중 answerable=true 만 = 355건

882는 VAL과 TEST의 합집합이므로 두 셋의 독립 검증에 쓸 수 없다. 이 스크립트는
882를 원천으로 두고 VAL을 결정론적으로 재생성한다 — 손으로 만든 파일을 남기지 않는다.

겹침 판정은 `question` 텍스트 기준이다. id는 두 셋에서 체계가 달라(450=nat450-*,
882=kdic-*/v9neg-*/nat450-*) 조인 키로 쓸 수 없다.

레코드는 882 원본을 그대로 옮긴다 — 필드 추가·수정 없음(앵커 승격은
promote_gt_anchors.py의 몫).

사용:
  python make_val_split.py                    # 505 + 355 둘 다 생성
  python make_val_split.py --answerable-only  # 355만
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib

SRC = "../final_testset/gt_natural882.jsonl"
TEST = "../final_testset/gt_natural450.jsonl"
OUT_DIR = "../final_testset"


def load(path: str) -> list[dict]:
    return [json.loads(l) for l in
            pathlib.Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def dump(rows: list[dict], path: str) -> None:
    pathlib.Path(path).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    sha = hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    print(f"[out] {path} · {len(rows)}행 · sha256 {sha[:16]}…")


def describe(rows: list[dict], name: str) -> None:
    ans = collections.Counter(str(r.get("answerable")) for r in rows)
    rel = collections.Counter(str(r.get("chunk_relation")) for r in rows)
    pre = collections.Counter(r["id"].split("-")[0] for r in rows)
    anchors = sum(1 for r in rows if r.get("gt_anchors") or r.get("gt_anchor_span"))
    print(f"  {name}: {len(rows)}행 · answerable {dict(ans)} · 앵커 보유 {anchors}")
    print(f"       relation {dict(rel)}")
    print(f"       id prefix {dict(pre)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--test", default=TEST)
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--answerable-only", action="store_true",
                    help="355건만 생성(505 중간 산출물은 저장하지 않음)")
    args = ap.parse_args()

    src = load(args.src)
    test = load(args.test)
    test_q = {r["question"] for r in test}

    val = [r for r in src if r["question"] not in test_q]
    answerable = [r for r in val if r.get("answerable") is True]

    print(f"[in ] {args.src} {len(src)}행 · TEST {args.test} {len(test)}행")
    print(f"      겹침 {len(src) - len(val)}건 제외 → VAL {len(val)}건 "
          f"· 그중 answerable {len(answerable)}건")
    print()
    describe(val, "VAL(전체)")
    describe(answerable, "VAL(answerable)")
    print()

    out = pathlib.Path(args.out_dir)
    if not args.answerable_only:
        dump(val, str(out / f"gt_natural{len(val)}_val.jsonl"))
    dump(answerable, str(out / f"gt_natural{len(answerable)}.jsonl"))

    # 분리 규약이 실제로 지켜졌는지 자체 검증 — 조용히 어긋나면 평가 채널이 오염된다.
    ans_q = {r["question"] for r in answerable}
    assert not (ans_q & test_q), "VAL과 TEST 질문이 겹친다 — 분리 실패"
    assert all(r.get("answerable") is True for r in answerable)
    ids = [r["id"] for r in answerable]
    assert len(set(ids)) == len(ids), "id 중복"
    print(f"\n[검증] TEST와 질문 교집합 0 · answerable 전건 true · id 유일 {len(ids)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
