"""BF_DOC_CAP × 반환 K 스윕 — relation(single/and) 분리 + LLM 컨텍스트 비용 병기.

왜 이 두 축인가:
  `and` 문항은 필요 청크가 **전부** top-K에 들어와야 적중한다. 그런데
  `_cap_by_doc(BF_DOC_CAP=5)`는 문서당 5청크만 남기고 **나머지를 랭킹에서 삭제**한다.
  같은 문서에서 여러 청크가 필요한 `and`의 요구와 문서당 상한이 정면 충돌해,
  430의 `and` 55건 중 28건은 필요 gold가 순위가 낮은 게 아니라 **존재하지 않게** 된다.
  cap을 끄면 55건 전부의 필요 청크가 top-50 안에 들어온다(꼴등 중앙 6~18위).

  반면 cap은 몬스터 문서 독점을 막는 장치라 끄면 `single`이 나빠질 수 있다.
  그래서 두 축을 함께 돌리고 **relation별로 나눠** 본다.

컨텍스트 비용을 함께 재는 이유:
  K를 늘리면 적중은 오르지만 LLM 입력이 커진다. HCX-003은 최대 입력 7,600토큰이라
  한도 초과가 곧 실패다. 적중률만 보고 K를 키우면 배포에서 깨진다.
  프롬프트 조립은 `chatbot/chain.py:197` 형식을 그대로 따른다.

사용:
  cd crawler && python tune_cap_k.py
  cd crawler && python tune_cap_k.py --sets 430 --report data/cap_k_430.md
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics

import numpy as np

import rag
import eval as ev3
from tune_params import _topk_lists

CAPS = (0, 3, 5, 8, 10, 15)        # 0 = 무제한
KS = (3, 5, 8, 10, 15, 20, 30)
CHARS_PER_TOKEN = 1.7              # CLOVA 토큰계산기 문서 예제(한국어 17자→10토큰) 기준
HCX003_MAX_INPUT = 7600
SYS_LEN = 304                      # chatbot/chain.py SYS_PROMPT_V2
FIXED_OVERHEAD = 40                # "[참고문서]\n…\n\n[질문]\n" + 질의


def build(name: str):
    searcher = rag.Searcher()
    chunks = searcher.chunks
    n_c = len(chunks)
    doc_of = np.array([c["parent_doc_id"] for c in chunks])
    nt = {c["chunk_id"]: ev3._norm_text(c.get("text", "")) for c in chunks}
    cid = {c["chunk_id"]: i for i, c in enumerate(chunks)}
    # [출처N] 제목\n본문 — chain.py:197 형식
    clen = np.array([len(c["text"]) + len(c.get("page_title", "")) + 10 for c in chunks])

    gt = [r for r in ev3._load_jsonl(pathlib.Path(f"../final_testset/gt_natural{name}.jsonl"))
          if r.get("answerable") is True and ev3._get_gt_chunk_ids(r)]
    qs = [r["question"] for r in gt]
    qe = rag.embed_texts(qs)
    _, I = searcher.index.search(qe, n_c)
    rank_d = np.empty((len(qs), n_c), "int32")
    rank_d[np.arange(len(qs))[:, None], I] = np.arange(n_c)
    rank_s = np.empty((len(qs), n_c), "int32")
    for i, q in enumerate(qs):
        rank_s[i, np.argsort(searcher.bm25.get_scores(rag.tokenize(q)))[::-1]] = np.arange(n_c)

    bf = np.zeros((len(qs), n_c), "float32")
    fc = np.zeros((len(qs), n_c), "float32")
    for i, q in enumerate(qs):
        b = rag.classify_query_bf(q)
        if b is None:
            continue
        allow = rag.BF_SHARED_DOCS.get(b, set())
        hit = np.array([(searcher._bf[j] == b) or (chunks[j]["parent_doc_id"] in allow)
                        for j in range(n_c)], dtype=bool)
        bf[i] = hit
        f = rag.query_facets(q)
        if f:
            fc[i] = np.array([sum(1 for t in f if t in chunks[j].get("sub_category", ""))
                              for j in range(n_c)], "float32") * hit

    score = (rag.RRF_ALPHA / (rag.RRF_K + rank_d + 1)
             + (1 - rag.RRF_ALPHA) / (rag.RRF_K + rank_s + 1)
             + rag.BF_BOOST * bf + rag.FACET_BOOST * fc)

    # 문항별 판정 조건 — eval.py chunk 판정의 앵커 하이브리드 규약
    need = []
    for it in gt:
        gold = ev3._get_gt_chunk_ids(it)
        anchors = ev3._get_gt_anchors(it)
        sets = [s for s in ({cid[c] for c in nt if a in nt[c]} for a in anchors) if s]
        cov = set().union(*sets) if sets else set()
        sets += [{cid[c]} for c in gold if c in cid and cid[c] not in cov]
        need.append((ev3._get_relation(it) == "and", sets, ev3._get_relation_label(it),
                     len(it["question"])))
    return dict(score=score, doc_of=doc_of, rank_d=rank_d, need=need, clen=clen, n=len(gt))


def evaluate(B, cap: int, K: int):
    tops = _topk_lists(B["score"], B["doc_of"], cap, K, tie=B["rank_d"])
    per = collections.defaultdict(lambda: [0, 0])
    ctx = []
    for (is_and, sets, lab, qlen), ranked in zip(B["need"], tops):
        per[lab][1] += 1
        ctx.append(int(B["clen"][ranked].sum()) + SYS_LEN + FIXED_OVERHEAD + qlen)
        if not sets:
            continue
        pos = {c: r for r, c in enumerate(ranked, 1)}
        firsts = [min((pos[c] for c in s if c in pos), default=None) for s in sets]
        ok = (not any(f is None for f in firsts)) if is_and else any(f is not None for f in firsts)
        per[lab][0] += bool(ok)
    hits = {l: a / b for l, (a, b) in per.items()}
    tot = sum(a for a, _ in per.values()) / sum(b for _, b in per.values())
    ctx.sort()
    return hits, tot, ctx, {l: b for l, (_, b) in per.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", default=["430", "355"])
    ap.add_argument("--report", default="data/cap_k_report.md")
    args = ap.parse_args()

    L = ["# BF_DOC_CAP × 반환 K 스윕 (relation 분리 + 컨텍스트 비용)\n",
         f"- 융합: alpha={rag.RRF_ALPHA} · rrf_k={rag.RRF_K} · bf={rag.BF_BOOST} · facet={rag.FACET_BOOST}",
         f"- 판정: 앵커 하이브리드(eval.py chunk 판정 규약) · `and`=ALL, 그 외=ANY",
         f"- 토큰 환산 {CHARS_PER_TOKEN}자/토큰 · HCX-003 최대입력 {HCX003_MAX_INPUT:,}토큰",
         f"- 컨텍스트 = SYS({SYS_LEN}자) + [출처N] 제목/본문 + 질의 (chain.py:197 형식)",
         "- **현행 배포는 cap=5**이며 `chain.py`가 `search(k=k)`로 K를 받는다\n"]

    for name in args.sets:
        B = build(name)
        cnt = evaluate(B, 5, 5)[3]
        L += [f"\n## {name}셋 (n={B['n']} · " +
              " · ".join(f"{l} {c}" for l, c in sorted(cnt.items(), key=lambda t: -t[1])) + ")\n",
              "| cap | K | 전체 | single | and | or | ctx 중앙(자) | ctx p95 | 평균토큰 | 7.6K초과 |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        print(f"\n=== {name}셋 (n={B['n']}) ===")
        print(f"  {'cap':>4}{'K':>4}{'전체':>8}{'single':>8}{'and':>8}{'ctx중앙':>9}{'평균tok':>8}{'초과':>7}")
        for cap in CAPS:
            for K in KS:
                hits, tot, ctx, _ = evaluate(B, cap, K)
                med = statistics.median(ctx)
                p95 = ctx[int(len(ctx) * .95)]
                avgtok = statistics.mean(ctx) / CHARS_PER_TOKEN
                over = sum(1 for x in ctx if x / CHARS_PER_TOKEN > HCX003_MAX_INPUT) / len(ctx)
                s = hits.get("single", float("nan"))
                a = hits.get("and", float("nan"))
                o = hits.get("or", float("nan"))
                L.append(f"| {cap or '∞'} | {K} | {tot:.3f} | {s:.3f} | {a:.3f} | {o:.3f} | "
                         f"{med:,.0f} | {p95:,.0f} | {avgtok:,.0f} | {over:.0%} |")
                print(f"  {(cap or '∞'):>4}{K:>4}{tot:>8.3f}{s:>8.3f}{a:>8.3f}"
                      f"{med:>9,.0f}{avgtok:>8,.0f}{over:>7.0%}")
    pathlib.Path(args.report).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n[out] {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
