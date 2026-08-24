"""정본 검색 캐시 생성 — 커밋된 rag.py 설정 그대로 450문항 × k=30을 굳힌다."""
import json, io, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rag
D = pathlib.Path(__file__).resolve().parent / "data"
gt = [json.loads(l) for l in io.open(D/"gt_natural450_v10_anchor.jsonl", encoding="utf-8")]
idx = sys.argv[1] if len(sys.argv) > 1 else str(D/"index")      # A/B용 대체 인덱스
out = sys.argv[2] if len(sys.argv) > 2 else str(D/"retrieved_top30.jsonl")
s = rag.Searcher(index_dir=idx)
t0 = time.time()
with io.open(out, "w", encoding="utf-8") as f:
    for g in gt:
        f.write(json.dumps({"id": g["id"], "retrieved_chunk_ids":
            [h["chunk_id"] for h in s.search(g["question"], k=30, mode="hybrid_bf")]},
            ensure_ascii=False) + "\n")
print(f"{idx} -> {out} · BF_DOC_CAP={rag.BF_DOC_CAP} · {len(gt)}문항 · {time.time()-t0:.0f}s")
