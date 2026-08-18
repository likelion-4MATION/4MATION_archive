"""Colab 리랭커 실험 입력 패키징 — 로컬에서 실행해 zip 하나로 만든다.

Colab에 리랭커만 태우고 검색은 로컬 프로덕션 경로(rag.search)로 미리 굳혀 올린다.
그래야 Colab에서 임베딩·FAISS·BM25·라우터를 재현할 필요가 없고, 리랭커 효과만
분리해서 볼 수 있다(검색이 바뀌면 리랭커 비교가 오염된다).

산출: rerank_colab/rerank_inputs.zip
  chunks.jsonl              청크 본문 (리랭커 입력 + 앵커 판정용)
  gt_natural430.jsonl       TEST
  gt_natural355.jsonl       VAL
  candidates_430.jsonl      top-50 후보 + 검색 점수·순위 (블렌딩용)
  candidates_355.jsonl
  meta.json                 파라미터·베이스라인 지표 (Colab 자체검증용)

사용:
  cd crawler && python ../rerank_colab/prepare_inputs.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import zipfile

OUT_DIR = pathlib.Path(__file__).resolve().parent
# sys.path[0]은 이 스크립트 폴더라 crawler 모듈이 안 잡힌다. crawler를 명시 추가.
sys.path.insert(0, str(OUT_DIR.parent / "crawler"))

import rag                          # noqa: E402
import eval_anchor_v3 as ev3        # noqa: E402

DEPTH = 50
SETS = {"430": "../final_testset/gt_natural430.jsonl",
        "355": "../final_testset/gt_natural355.jsonl"}


def main() -> int:
    chunks_path = pathlib.Path("data/chunks.jsonl")
    chunks = ev3._load_jsonl(chunks_path)
    searcher = rag.Searcher()
    params = dict(RRF_ALPHA=rag.RRF_ALPHA, RRF_K=rag.RRF_K, BF_BOOST=rag.BF_BOOST,
                  FACET_BOOST=rag.FACET_BOOST, BF_DOC_CAP=rag.BF_DOC_CAP,
                  QBF_MSP_MIN=rag.QBF_MSP_MIN, EMBED_MODEL=rag.MODEL_NAME, DEPTH=DEPTH)
    meta = {"params": params, "baseline": {},
            "corpus_sha256": hashlib.sha256(chunks_path.read_bytes()).hexdigest(),
            "n_chunks": len(chunks)}

    staged: dict[str, str] = {"chunks.jsonl": chunks_path.read_text(encoding="utf-8")}
    for name, gt_path in SETS.items():
        gt = ev3._load_jsonl(pathlib.Path(gt_path))
        cands = []
        for item in gt:
            hits = searcher.search(item["question"], k=DEPTH, mode="hybrid_bf")
            cands.append({"id": item["id"], "question": item["question"],
                          # rank는 0-based. score는 부스트까지 반영된 최종 융합 점수.
                          "candidates": [{"chunk_id": h["chunk_id"], "rank": r,
                                          "score": h["_score"]}
                                         for r, h in enumerate(hits)]})
        ret = [{"id": c["id"],
                "retrieved_chunk_ids": [x["chunk_id"] for x in c["candidates"]]}
               for c in cands]
        res = ev3.evaluate_retrieval(gt, ret, chunks, score="both")
        a, b = res["anchor_level"], res["chunk_on_anchor_subset"]
        meta["baseline"][name] = {
            "n_scored": a["n_scored"],
            "anchor": {k: round(a[k], 6) for k in
                       ("hit@1", "hit@3", "hit@5", "hit@10", "hit@30", "hit@50", "mrr")},
            "chunk_id": {k: round(b[k], 6) for k in
                         ("hit@1", "hit@3", "hit@5", "hit@10", "hit@30", "hit@50", "mrr")},
        }
        staged[f"gt_natural{name}.jsonl"] = pathlib.Path(gt_path).read_text(encoding="utf-8")
        staged[f"candidates_{name}.jsonl"] = "".join(
            json.dumps(c, ensure_ascii=False) + "\n" for c in cands)
        print(f"  [{name}] 후보 {len(cands)}문항 × top-{DEPTH} · "
              f"베이스라인 앵커 hit@5 {a['hit@5']:.4f}")

    staged["meta.json"] = json.dumps(meta, ensure_ascii=False, indent=2)
    zip_path = OUT_DIR / "rerank_inputs.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in staged.items():
            z.writestr(name, body)
    mb = zip_path.stat().st_size / 1e6
    print(f"\n[out] {zip_path} · {mb:.1f}MB")
    print("      Colab 노트북 2번 셀에서 이 파일을 업로드하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
