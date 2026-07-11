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

import chunk as chunk_mod
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
            return {"doc_id": doc_id, "status": res["status"]}
        html = raw_p.read_text(encoding="utf-8", errors="replace")
        meta = json.loads(meta_p.read_text(encoding="utf-8"))

    # ── content_hash 스킵 판정 (D0 재현성 지표와 동일: 가시 텍스트) ──
    content_hash = hashlib.sha256(crawler.visible_text(html).encode()).hexdigest()
    if not store.needs_update(doc_id, content_hash):
        return {"doc_id": doc_id, "status": "skipped"}

    # ── parse → chunk → upsert ───────────────────────────────
    parsed = parser_mod.parse_one(doc_id, html, meta)
    parsed_dir = out_root / "data/parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    (parsed_dir / f"{doc_id}.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    chunks = chunk_mod.make_chunks(parsed)
    store.upsert(doc_id, chunks, content_hash)
    return {"doc_id": doc_id, "status": "upserted", "n_chunks": len(chunks)}


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


if __name__ == "__main__":
    main()
