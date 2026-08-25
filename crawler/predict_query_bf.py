"""질의측 BF를 라우터로 사전 예측 → data/query_bf_router.jsonl

현행 `rag.classify_query_bf`(키워드+마진)를 라우터로 교체하는 A/B의 입력을 만든다.
문서측 `faq_bf_map.py`와 같은 패턴 — 라우터 추론은 오프라인 1회, 실험은 캐시 조인.

분리 이유:
- 실험을 config마다 재추론하면 느리고, torch(라우터)와 faiss(검색)를 한 프로세스에
  올릴 이유가 없다.
- 같은 질문 집합에 대해 항상 같은 예측을 쓰므로 config 간 비교가 정확해진다.

조인 키는 문서측과 동일한 정규화 hash(qhash) — 질문 텍스트가 같으면 매핑이 따라온다.

사용:
  python predict_query_bf.py --gt data/gt_schema_v6.jsonl
  python predict_query_bf.py --gt ... --out data/query_bf_router.jsonl
"""

from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timezone

from faq_bf_map import Router, normalize_q, qhash

DEFAULT_GT = "data/gt_schema_v6.jsonl"
DEFAULT_OUT = "data/query_bf_router.jsonl"
DEFAULT_ROUTER = "../router_moai_embedding_model"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default=DEFAULT_GT)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--router", default=DEFAULT_ROUTER)
    ap.add_argument("--field", default="question")
    args = ap.parse_args()

    rows = [json.loads(l) for l in
            pathlib.Path(args.gt).read_text(encoding="utf-8").splitlines() if l.strip()]
    # 같은 질문이 여러 문항에 나올 수 있으므로 고유 질문만 추론한다.
    uniq: dict[str, str] = {}
    for r in rows:
        q = normalize_q(r[args.field])
        uniq.setdefault(qhash(q), q)
    print(f"[in] {args.gt} · {len(rows)}행 · 고유 질문 {len(uniq)}")

    router = Router(args.router)
    keys = list(uniq)
    preds = router.predict([uniq[k] for k in keys])

    now = datetime.now(timezone.utc).isoformat()
    with open(args.out, "w", encoding="utf-8") as f:
        for k, (bf, msp) in zip(keys, preds):
            # 임계는 여기서 적용하지 않는다 — 실험에서 θ를 스윕해야 하므로 원 확률을 보존.
            f.write(json.dumps({"qhash": k, "question": uniq[k], "bf": bf,
                                "msp": round(msp, 4), "model": args.router,
                                "source": "router", "labeled_at": now},
                               ensure_ascii=False) + "\n")
    print(f"[out] {args.out} · {len(keys)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
