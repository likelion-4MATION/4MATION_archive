"""전량 수집 실행 — python run_crawl.py --manifest crawl_manifest.csv

스모크: python run_crawl.py --manifest crawl_manifest.csv --limit 3
산출: data/raw/*.html · data/meta/*.json · data/crawl_report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from collections import Counter
from datetime import datetime, timezone

import config
import crawler


def load_manifest(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            url = (row.get("url") or "").strip()
            if url.startswith("http"):
                rows.append(row)
    if not rows:
        sys.exit(f"매니페스트에 url 컬럼이 없거나 비어 있음: {path}")
    # 중복 URL 제거 (variant 분기는 URL이 다르므로 유지됨)
    seen, uniq = set(), []
    for r in rows:
        if r["url"] not in seen:
            seen.add(r["url"])
            uniq.append(r)
    return uniq


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", default=".", help="산출 루트 (기본: 현재 폴더)")
    ap.add_argument("--limit", type=int, default=0, help="스모크용 앞 N건만")
    args = ap.parse_args()

    rows = load_manifest(args.manifest)
    if args.limit:
        rows = rows[: args.limit]
    out_root = pathlib.Path(args.out)

    print(f"=== KDIC 크롤 시작: {len(rows)}건 · {datetime.now().isoformat(timespec='seconds')} ===")
    results = []
    for i, row in enumerate(rows, 1):
        res = crawler.fetch_one(row, out_root)
        results.append(res)
        mark = {"ok": "✓", "robots_blocked": "⛔", "error_page": "✗"}.get(res["status"], "!")
        print(f"[{i:>3}/{len(rows)}] {mark} {res['status']:<14} {res['url']}")

    counts = Counter(r["status"] for r in results)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "manifest": args.manifest,
        "total": len(results),
        "counts": dict(counts),
        "robots_blocked": [r["url"] for r in results if r["status"] == "robots_blocked"],
        "error_pages": [r["url"] for r in results if r["status"] == "error_page"],
        "failures": [r for r in results if r["status"] not in ("ok",)],
        "results": results,
    }
    report_path = out_root / config.REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 요약 ===")
    for k, v in counts.most_common():
        print(f"  {k:<16}{v}")
    print(f"리포트: {report_path}")
    if counts.get("ok", 0) < len(results):
        print("※ 실패 건은 report의 failures 참고 — 2시간 룰: 막히면 구멍 목록에 기록하고 우회")


if __name__ == "__main__":
    main()
