"""청크 오버랩 실험용 인덱스 빌더 — data/parsed → 지정 overlap으로 청킹 → 지정 index_dir에 저장.

data/chunks.jsonl · data/index(공용 산출물)는 건드리지 않는다 (병렬 실험 시 경합 방지).
"""

from __future__ import annotations

import argparse
import glob
import json
import pathlib
import pickle

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

import chunk as chunk_mod
import rag


def build(overlap: int, chunks_out: pathlib.Path, index_dir: pathlib.Path) -> None:
    chunk_mod.OVERLAP = overlap
    parsed = sorted(glob.glob(f"{chunk_mod.PARSED_DIR}/*.json"))
    all_chunks = []
    for p in parsed:
        rec = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        all_chunks.extend(chunk_mod.make_chunks(rec))

    chunks_out.parent.mkdir(parents=True, exist_ok=True)
    with open(chunks_out, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    index_dir.mkdir(parents=True, exist_ok=True)
    if all_chunks:
        embs = rag.embed_texts([rag.chunk_embed_text(c) for c in all_chunks])
    else:
        embs = np.zeros((0, rag.EMB_DIM), "float32")
    dim = int(embs.shape[1]) if embs.shape[0] else rag.EMB_DIM
    index = faiss.IndexFlatIP(dim)
    if all_chunks:
        index.add(embs)
    faiss.write_index(index, str(index_dir / "faiss.index"))
    np.save(index_dir / "emb.npy", embs)

    corpus = [rag.tokenize(c["text"]) for c in all_chunks]
    bm25 = BM25Okapi(corpus) if corpus else None
    with open(index_dir / "bm25.pkl", "wb") as f:
        pickle.dump({"bm25": bm25, "corpus_len": len(all_chunks)}, f)

    with open(index_dir / "chunk_meta.jsonl", "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"overlap={overlap}: 청크 {len(all_chunks)}건 → {chunks_out}, 인덱스 → {index_dir}")


def main() -> None:
    ap = argparse.ArgumentParser(description="오버랩 실험용 인덱스 빌드")
    ap.add_argument("--overlap", type=int, required=True)
    ap.add_argument("--chunks-out", type=pathlib.Path, required=True)
    ap.add_argument("--index-dir", type=pathlib.Path, required=True)
    args = ap.parse_args()
    build(args.overlap, args.chunks_out, args.index_dir)


if __name__ == "__main__":
    main()
