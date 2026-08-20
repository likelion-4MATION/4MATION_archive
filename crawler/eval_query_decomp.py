# -*- coding: utf-8 -*-
"""복합질의 분해 검색 실험 — and 문항의 '두 요구가 각각 다른 청크에 있음' 회수용. (기각)

문제: and 문항 실패 다수가 "필요 스팬 하나는 top-5 안인데 나머지가 6~10위"였다.
실패 질문을 실제로 읽어보면 대부분 한 문장에 요구가 둘이다.
  "온라인으로 신청하는 사이트가 어디예요? / 인증은 뭘로 하죠?"
  "해외 거주자는 어떻게 받아요? / 대리 신청 서류는요?"
질의 전체를 한 벡터로 임베딩하면 두 요구가 평균돼 한쪽(보통 앞부분)에 끌린다.
그래서 앞부분 근거는 잘 나오고 뒷부분 근거가 경계 밖으로 밀린다.

처방: 질의를 하위질의로 쪼개 각각 검색하고 RRF로 융합한다. 각 하위질의가 자기
근거를 상위로 올리므로 서로 다른 청크가 함께 top-5에 들어온다.

중요 - 라벨 누수 금지: 분해 여부를 chunk_relation(and/or)으로 정하지 않는다.
그건 정답을 보고 검색 전략을 바꾸는 것이라 평가가 무의미해진다. 오직 질문 문자열의
형태(물음표·접속어)만 보고 결정하며, 따라서 single 문항에도 동일하게 적용된다.

결과: 기각. 분해기가 물음표(?)와 접속어만 봐서, 실제로 쪼개지는 질의가 전체의
극소수뿐이라 hit@5에 유의미한 영향이 없었다. 의문사(뭘/어디로 등) 2개를 인식하는
절 단위 분해기로 확장하면 적용 범위가 넓어질 수 있다 — 다음에 시도할 사람을 위해 남김.

사용: cd crawler && python eval_query_decomp.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import rag
from eval_anchor_span_multi import RETRIEVAL_DEPTH, _item_metrics, _norm

TEST_GT = "data/gt_natural430_curated.jsonl"
VAL_GT = "data/gt_natural355.jsonl"
KS = (1, 3, 5, 10)

# 하위질의 가중(전체질의는 1.0). 0.0이면 분해를 끈 현행과 동일하다.
SUB_WEIGHTS = [0.0, 0.3, 0.5, 0.7, 1.0]
MIN_SUB_LEN = 6      # 이보다 짧은 조각은 독립 질의로 보지 않는다
RRF_K = 5

# 물음표, 그리고/또/및, 쉼표+의문 어미 등 '요구가 둘'인 표지
_SPLIT_RE = re.compile(r"(?<=[?？])\s*|\s*(?:그리고|또한|또|및)\s+")


def split_query(q: str) -> list[str]:
    """질문 문자열만 보고 하위질의로 쪼갠다(정답 라벨을 보지 않는다)."""
    parts = [p.strip() for p in _SPLIT_RE.split(q) if p and p.strip()]
    parts = [p for p in parts if len(p.replace(" ", "")) >= MIN_SUB_LEN]
    # 쪼갠 결과가 1개거나 원문과 사실상 같으면 분해하지 않은 것으로 본다.
    if len(parts) < 2:
        return []
    return parts


def prepare(gt: list[dict], searcher: "rag.Searcher") -> list[dict]:
    """전체질의 + 하위질의 각각의 dense/sparse 전체 풀 랭크를 미리 계산해 캐시한다."""
    n = len(searcher.chunks)
    out = []
    for item in gt:
        q = item["question"]
        subs = split_query(q)
        rec = {
            "item": item,
            "full": ({int(i): r for r, (i, _) in enumerate(searcher.dense(q, n))},
                     {int(i): r for r, (i, _) in enumerate(searcher.sparse(q, n))}),
            "subs": [],
            "bf": rag.classify_query_bf(q),
            "facets": rag.query_facets(q),
        }
        for sq in subs:
            rec["subs"].append(
                ({int(i): r for r, (i, _) in enumerate(searcher.dense(sq, n))},
                 {int(i): r for r, (i, _) in enumerate(searcher.sparse(sq, n))}))
        out.append(rec)
    return out


def _rrf_add(sc: dict[int, float], d_rank, s_rank, weight: float) -> None:
    for i in set(d_rank) | set(s_rank):
        v = 0.0
        if i in d_rank:
            v += rag.RRF_ALPHA / (RRF_K + d_rank[i] + 1)
        if i in s_rank:
            v += (1 - rag.RRF_ALPHA) / (RRF_K + s_rank[i] + 1)
        sc[i] = sc.get(i, 0.0) + weight * v


def retrieve(chunks, rec, w_sub: float) -> list[str]:
    sc: dict[int, float] = {}
    _rrf_add(sc, rec["full"][0], rec["full"][1], 1.0)
    if w_sub > 0:
        for d_rank, s_rank in rec["subs"]:
            _rrf_add(sc, d_rank, s_rank, w_sub)

    bf, facets = rec["bf"], rec["facets"]
    if bf is not None and rag.BF_BOOST > 0:
        allow = rag.BF_SHARED_DOCS.get(bf, set())
        for i in sc:
            c = chunks[i]
            if c.get("business_function") == bf or c["parent_doc_id"] in allow:
                sc[i] += rag.BF_BOOST
                if rag.FACET_BOOST and facets:
                    hit = sum(1 for t in facets if t in c.get("sub_category", ""))
                    if hit:
                        sc[i] += rag.FACET_BOOST * hit

    ranked = sorted(sc.items(), key=lambda x: -x[1])
    if rag.BF_DOC_CAP:
        seen: dict[str, int] = {}
        capped = []
        for idx, score in ranked:
            d = chunks[idx]["parent_doc_id"]
            if seen.get(d, 0) < rag.BF_DOC_CAP:
                capped.append((idx, score))
                seen[d] = seen.get(d, 0) + 1
        ranked = capped
    return [chunks[i]["chunk_id"] for i, _ in ranked[:RETRIEVAL_DEPTH]]


def evaluate(prepared, chunks, chunk_text, w_sub) -> dict:
    agg = {f"hit@{k}": 0 for k in KS}
    agg["mrr"] = 0.0
    by_rel: dict[str, list[int]] = {}
    n = 0
    for rec in prepared:
        ids = retrieve(chunks, rec, w_sub)
        v = _item_metrics(rec["item"], ids, chunk_text, id_fallback=True)
        n += 1
        for k in KS:
            agg[f"hit@{k}"] += v[f"hit@{k}"]
        agg["mrr"] += v["mrr"]
        rel = rec["item"].get("chunk_relation") or "single"
        by_rel.setdefault(rel, []).append(1 if v["hit@5"] else 0)
    res = {k: val / n for k, val in agg.items()}
    res["n"] = n
    res["rel"] = {r: (sum(x) / len(x), len(x)) for r, x in by_rel.items()}
    return res


def run(gt_path, label, searcher, chunks, chunk_text) -> dict:
    gt = [json.loads(l) for l in open(gt_path, encoding="utf-8") if l.strip()]
    gt = [x for x in gt if x.get("answerable") is True]
    prepared = prepare(gt, searcher)
    n_split = sum(1 for r in prepared if r["subs"])
    print(f"\n{'='*76}\n[{label}] {gt_path} · 평가 대상 {len(gt)}건 "
          f"· 분해된 질의 {n_split}건({n_split/len(gt)*100:.1f}%)\n{'='*76}")
    print(f"{'w_sub':>7}" + "".join(f"{'hit@'+str(k):>9}" for k in KS) + f"{'mrr':>9}   relation별 hit@5")
    out = {}
    for w in SUB_WEIGHTS:
        r = evaluate(prepared, chunks, chunk_text, w)
        out[w] = r
        rel = "  ".join(f"{k}={v[0]:.3f}({v[1]})" for k, v in sorted(r["rel"].items()))
        cells = "".join(f"{r[f'hit@{k}']:>9.3f}" for k in KS) + f"{r['mrr']:>9.3f}"
        star = "  *현행(분해 없음)" if w == 0.0 else ""
        print(f"{w:>7.2f}{cells}   {rel}{star}")
    return out


def main() -> None:
    searcher = rag.Searcher()
    chunks = searcher.chunks
    chunk_text = {c["chunk_id"]: _norm(c.get("text", "")) for c in chunks}
    print(f"현행 파라미터: alpha={rag.RRF_ALPHA} bf={rag.BF_BOOST} "
          f"facet={rag.FACET_BOOST} cap={rag.BF_DOC_CAP} · 채점: id_fallback 켬")

    test = run(TEST_GT, "TEST", searcher, chunks, chunk_text)
    val = run(VAL_GT, "VAL", searcher, chunks, chunk_text)

    print(f"\n{'='*76}\n두 셋 전이성 판정 (분해 없음 w_sub=0 대비 hit@5 증감)\n{'='*76}")
    t0, v0 = test[0.0]["hit@5"], val[0.0]["hit@5"]
    print(f"{'w_sub':>7}{'TEST':>10}{'VAL':>10}   판정")
    for w in SUB_WEIGHTS:
        dt, dv = test[w]["hit@5"] - t0, val[w]["hit@5"] - v0
        verdict = "기준" if w == 0.0 else ("채택 가능(둘 다 개선)" if dt > 0 and dv > 0 else "한쪽만/악화")
        print(f"{w:>7.2f}{dt:>+10.4f}{dv:>+10.4f}   {verdict}")


if __name__ == "__main__":
    main()
