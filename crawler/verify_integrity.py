"""인덱스·코퍼스 정합성 검증 — faiss/emb/meta/bm25/chunks 개수 일치 등.

파이프라인 산출물이 서로 어긋나면 검색이 조용히 틀린다(예: emb는 213인데
faiss는 181이면 인덱스 범위 밖 참조). 재수집/재청킹/재인덱싱 후 이 스크립트로
한 번에 검증한다. 실패 시 exit code 1 → CI/커밋 훅에 걸 수 있음.

사용: python verify_integrity.py   (crawler/ 에서 실행)
"""
from __future__ import annotations

import json
import pathlib
import pickle
import sys

import numpy as np

DATA = pathlib.Path("data")
IDX = DATA / "index"
EMB_DIM = 768


def _lines(p: pathlib.Path) -> int:
    return sum(1 for _ in open(p, encoding="utf-8"))


def main() -> int:
    fails: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        mark = "OK ✓" if cond else "FAIL ✗"
        print(f"  [{mark}] {name}{('  · ' + detail) if detail else ''}")
        if not cond:
            fails.append(name)

    # ── 청크 단위: 5개 카운트가 모두 같아야 ──────────────────
    chunks_n = _lines(DATA / "chunks.jsonl")
    meta_n = _lines(IDX / "chunk_meta.jsonl")
    emb = np.load(IDX / "emb.npy")
    emb_n, emb_dim = emb.shape
    bm_len = pickle.load(open(IDX / "bm25.pkl", "rb")).get("corpus_len")
    import faiss
    faiss_n = faiss.read_index(str(IDX / "faiss.index")).ntotal

    print("── 청크 단위 정합성 (모두 동일해야) ──")
    counts = {"chunks.jsonl": chunks_n, "chunk_meta.jsonl": meta_n,
              "emb.npy": emb_n, "faiss.index": faiss_n, "bm25.corpus_len": bm_len}
    for k, v in counts.items():
        print(f"    {k:18}: {v}")
    check("청크 카운트 5종 일치", len(set(counts.values())) == 1)
    check("임베딩 차원 == 768", emb_dim == EMB_DIM, f"dim={emb_dim}")

    # ── 문서 단위: raw/parsed/meta/docs.json/고유 parent ──────
    ch = [json.loads(l) for l in open(DATA / "chunks.jsonl", encoding="utf-8")]
    uniq_parent = len(set(c["parent_doc_id"] for c in ch))
    raw_n = len(list((DATA / "raw").glob("*.html")))
    parsed_n = len(list((DATA / "parsed").glob("*.json")))
    metaf_n = len(list((DATA / "meta").glob("*.json")))
    docs = json.loads((IDX / "docs.json").read_text(encoding="utf-8"))

    print("── 문서 단위 정합성 ──")
    for k, v in [("raw/*.html", raw_n), ("parsed/*.json", parsed_n),
                 ("meta/*.json", metaf_n), ("docs.json", len(docs)),
                 ("chunks 고유 parent", uniq_parent)]:
        print(f"    {k:18}: {v}")
    check("raw == parsed == meta", raw_n == parsed_n == metaf_n)
    check("docs.json == 고유 parent", len(docs) == uniq_parent)

    # ── 교차 참조 무결성 ─────────────────────────────────────
    print("── 교차 참조 ──")
    docset = set(docs)
    orphan = [c["chunk_id"] for c in ch if c["parent_doc_id"] not in docset]
    check("고아 청크 없음(parent가 docs.json에)", not orphan,
          f"{len(orphan)}건" + (f" 예: {orphan[:3]}" if orphan else ""))

    ts_path = DATA / "testset_merged.jsonl"
    if ts_path.exists():
        pset = set(c["parent_doc_id"] for c in ch)
        tj = [json.loads(l) for l in open(ts_path, encoding="utf-8")]
        badgt = sorted({g for x in tj for g in x["gt_docs"] if g not in pset})
        empty = sum(1 for x in tj for _ in [x] if not x["gt_docs"])
        check("평가셋 gt 전부 코퍼스에 존재", not badgt,
              f"미존재 {len(badgt)}건 {badgt[:3]}" if badgt else f"{len(tj)}문항")
        check("gt_docs 빈 문항 없음", empty == 0, f"빈 문항 {empty}건")

    # ── 결과 ─────────────────────────────────────────────────
    print()
    if fails:
        print(f"❌ 정합성 실패 {len(fails)}건: {', '.join(fails)}")
        return 1
    print("✅ 모든 정합성 검사 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
