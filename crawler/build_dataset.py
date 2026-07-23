"""데이터셋 빌드 래퍼 — 첨부 포함 chunks.jsonl / doc_attachments.json 산출.

[doc-agg] 첨부 실다운로드(fetch_attachments)는 네트워크·비결정론 단계이고 파일이
거의 안 바뀌므로, recollect(pipeline.py)의 잦은 재실행 루프에 넣지 않고 소스가
바뀔 때만 도는 이 배치 래퍼로 분리한다.

단계: (선택)크롤 → parse → fetch_attachments → link_files → chunk
  - run_crawl.py         : (--crawl 시) data/raw + data/meta 라이브 수집
  - parser.py            : data/raw+meta → data/parsed/*.json (첨부 enc 토큰 포함)
  - fetch_attachments.py : onclick 첨부 실다운로드 → data/files/ + manifest.json (네트워크)
  - link_files.py        : manifest ⋈ parsed → parsed에 local_path stamp (manifest 없으면 스킵)
  - chunk.py             : parsed → data/chunks.jsonl + data/doc_attachments.json

사용:
  python build_dataset.py            # data/raw 캐시로 데이터셋 재빌드(첨부 다운로드 포함)
  python build_dataset.py --crawl    # 라이브 크롤부터 전체
  python build_dataset.py --no-fetch # 첨부 다운로드 건너뜀(오프라인 실험용, local_path 미채움)

첫 빌드 권장 순서:
  python build_dataset.py --crawl
  python pipeline.py --manifest crawl_manifest.csv --use-cache --rebuild
"""
from __future__ import annotations

import argparse
import subprocess
import sys


def run(cmd: list[str]) -> None:
    print(f"\n$ python {' '.join(cmd)}")
    if subprocess.run([sys.executable] + cmd).returncode != 0:
        sys.exit(f"[build_dataset] 실패: {' '.join(cmd)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="crawl_manifest.csv")
    ap.add_argument("--crawl", action="store_true", help="run_crawl부터 라이브 수집")
    ap.add_argument("--no-fetch", action="store_true", help="첨부 실다운로드 건너뜀")
    args = ap.parse_args()

    if args.crawl:
        run(["run_crawl.py", "--manifest", args.manifest])
    run(["parser.py"])
    if not args.no_fetch:
        run(["fetch_attachments.py"])
    run(["link_files.py"])
    run(["chunk.py"])
    print("\n=== build_dataset 완료: data/chunks.jsonl · data/doc_attachments.json ===")


if __name__ == "__main__":
    main()
