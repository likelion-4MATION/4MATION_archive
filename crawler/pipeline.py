"""수집→검색 원자 파이프라인 — recollect(url) 트리거 프로토타입 (03 문서 §4).

recollect(url) = fetch(polite) → parse → chunk → upsert(store, by doc_id)
content_hash(가시 텍스트 sha256) 불변이면 parse/chunk/embed 스킵.
전체 재수집 = for url in manifest: recollect(url).

사용:
  python pipeline.py --manifest crawl_manifest.csv            # 라이브 재수집(폴라이트)
  python pipeline.py --manifest crawl_manifest.csv --use-cache# data/raw 캐시 사용(무네트워크)
  python pipeline.py --manifest crawl_manifest.csv --rebuild  # 인덱스 초기화 후 전량
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
from collections import Counter
from datetime import datetime, timezone

import chunk as chunk_mod
import config
import crawler
import parser as parser_mod
import rag
from run_crawl import load_manifest


def recollect(row: dict, store: rag.Store, out_root: pathlib.Path,
              use_cache: bool = False) -> dict:
    """URL 1건 재수집 원자 단위. content_hash 불변이면 downstream 스킵."""
    url = row["url"].strip()
    doc_id = crawler.doc_id_from_url(url)
    raw_p = out_root / "data/raw" / f"{doc_id}.html"
    meta_p = out_root / "data/meta" / f"{doc_id}.json"

    # ── fetch ────────────────────────────────────────────────
    fetch_res = {"url": url, "doc_id": doc_id}   # 라이브 시 fetch 상세로 대체(report용)
    if use_cache:
        if not raw_p.exists():
            store.remove(doc_id)
            return {"doc_id": doc_id, "status": "cache_miss"}
        html = raw_p.read_text(encoding="utf-8", errors="replace")
        meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {"source_url": url}
    else:
        res = crawler.fetch_one(row, out_root)
        if res["status"] != "ok":
            store.remove(doc_id)   # robots_blocked/error → 인덱스에서 제외
            return res
        fetch_res = res
        html = raw_p.read_text(encoding="utf-8", errors="replace")
        meta = json.loads(meta_p.read_text(encoding="utf-8"))

    # ── content_hash 스킵 판정 (D0 재현성 지표와 동일: 가시 텍스트) ──
    content_hash = hashlib.sha256(crawler.visible_text(html).encode()).hexdigest()
    if not store.needs_update(doc_id, content_hash):
        return {**fetch_res, "status": "skipped"}

    # ── parse → chunk → upsert ───────────────────────────────
    parsed = parser_mod.parse_one(doc_id, html, meta)
    parsed_dir = out_root / "data/parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    (parsed_dir / f"{doc_id}.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    chunks = chunk_mod.make_chunks(parsed)
    store.upsert(doc_id, chunks, content_hash)
    return {**fetch_res, "status": "upserted", "n_chunks": len(chunks)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="crawl_manifest.csv")
    ap.add_argument("--out", default=".")
    ap.add_argument("--use-cache", action="store_true", help="data/raw 캐시 사용(무네트워크)")
    ap.add_argument("--rebuild", action="store_true", help="인덱스 초기화 후 전량 재적재")
    args = ap.parse_args()

    out_root = pathlib.Path(args.out)
    if args.rebuild:
        shutil.rmtree(out_root / rag.INDEX_DIR, ignore_errors=True)

    rows = load_manifest(args.manifest)
    store = rag.Store(str(out_root / rag.INDEX_DIR))

    print(f"=== recollect 파이프라인: {len(rows)}건 · cache={args.use_cache} ===")
    results = []
    for i, row in enumerate(rows, 1):
        r = recollect(row, store, out_root, use_cache=args.use_cache)
        results.append(r)
        tag = {"upserted": "✓", "skipped": "=", "robots_blocked": "⛔"}.get(r["status"], "·")
        extra = f" ({r.get('n_chunks')}청크)" if r["status"] == "upserted" else ""
        print(f"[{i:>2}/{len(rows)}] {tag} {r['status']:<14}{extra} {r['doc_id']}")

    counts = Counter(r["status"] for r in results)
    changed = counts.get("upserted", 0)
    if changed or not (store.dir / "faiss.index").exists():
        store.build_and_save()
        built = "인덱스 재빌드"
    else:
        built = "변경 없음 — 인덱스 유지"

    print(f"\n=== 요약 === {dict(counts)}")
    print(f"저장 청크: {len(store.chunks)} · {built} → {store.dir}/")

    # 라이브 실행이면 crawl_report.json 갱신 — run_crawl.py와 동일 스키마.
    # skipped/upserted는 fetch 관점에선 ok (recollect가 전 URL을 실제 재수집하므로).
    if not args.use_cache:
        as_fetch = {"skipped": "ok", "upserted": "ok"}
        rep = []
        for r in results:
            rr = {k: v for k, v in r.items() if k != "n_chunks"}
            rr["status"] = as_fetch.get(r["status"], r["status"])
            rep.append(rr)
        fetch_counts = Counter(r["status"] for r in rep)
        report = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "manifest": args.manifest,
            "total": len(rep),
            "counts": dict(fetch_counts),
            "robots_blocked": [r["url"] for r in rep if r["status"] == "robots_blocked"],
            "error_pages": [r["url"] for r in rep if r["status"] == "error_page"],
            "failures": [r for r in rep if r["status"] != "ok"],
            "results": rep,
        }
        report_path = out_root / config.REPORT_PATH
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        print(f"crawl_report 갱신 → {report_path}")


if __name__ == "__main__":
    main()
