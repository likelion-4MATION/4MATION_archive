"""재실행 재현성 검증 — 통과조건 1번: "재실행해도 동일 결과".

사용:
  1차 수집 → python run_crawl.py --manifest crawl_manifest.csv --out run1
  2차 수집 → python run_crawl.py --manifest crawl_manifest.csv --out run2
  비교     → python verify_rerun.py run1 run2

판정 기준은 text_sha256 (보이는 텍스트 해시).
raw 바이트는 CSRF 토큰·세션값 때문에 매 실행 달라질 수 있어 기준에서 제외.
"""

from __future__ import annotations

import json
import pathlib
import sys


def load_meta(root: str) -> dict[str, dict]:
    metas = {}
    for p in pathlib.Path(root, "data/meta").glob("*.json"):
        m = json.loads(p.read_text(encoding="utf-8"))
        metas[m["doc_id"]] = m
    return metas


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python verify_rerun.py <run1_dir> <run2_dir>")
    a, b = load_meta(sys.argv[1]), load_meta(sys.argv[2])

    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    both = sorted(set(a) & set(b))
    diff = [d for d in both if a[d]["text_sha256"] != b[d]["text_sha256"]]

    print(f"run1 {len(a)}건 · run2 {len(b)}건 · 공통 {len(both)}건")
    if only_a:
        print(f"run1에만 존재: {only_a}")
    if only_b:
        print(f"run2에만 존재: {only_b}")
    if diff:
        print(f"텍스트 해시 불일치 {len(diff)}건:")
        for d in diff:
            print(f"  {d}: {a[d]['text_len']} → {b[d]['text_len']} chars")
    ok = not (only_a or only_b or diff)
    print("\n판정:", "통과 — 동일 결과 재현" if ok else "미통과 — 위 차이 확인 필요")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
