"""문서측 임베딩 입력 변형 A/B — 앵커 판정 · VAL/TEST 양쪽.

기존 `eval_embedinput.py`는 문서 단위(gt_docs) 판정 + testset_natural_400 기준이었다.
이 스크립트는 현행 규약(앵커 판정 · 튜닝된 융합 파라미터 · VAL 355 / TEST 430)으로
같은 질문을 다시 던진다.

배경: `and` 문항의 병목은 앵커 라벨이 아니라 **구비서류 표 청크가 검색되지 않는 것**이다
(430 `and` 55건 중 미앵커 gold가 전부 top-50에 드는 문항 29건뿐). 그 청크들은 본문에
'착오송금'도 '구비서류'도 없고 임베딩 입력에 붙는 컨텍스트는 page_title 하나뿐이다.

**반대 위험**: breadcrumb/sub_category는 형제문서끼리 접두가 거의 같아, 공유 토큰이
벡터를 지배해 형제 구분이 되레 나빠질 수 있다. 이 프로젝트는 형제 판별을 세 번 시도해
세 번 기각한 이력이 있다(docs/records/ANCHOR_구현_논의결과.md §3-4). 그래서 검색 지표만 보지 않고
**형제 쌍 코사인**과 **표 청크 회수율**을 같이 잰다 — 지표가 올라도 형제가 뭉개지면 기각.

변형:
  cur       page_title + 본문                       (현행)
  sub       sub_category + page_title + 본문
  bc        breadcrumb  + page_title + 본문
  leaf      sub_category의 **마지막 노드만** + page_title + 본문
            (공유 접두를 버리고 변별 노드만 — 형제 붕괴를 피하려는 절충안)
  short     자기 식별 정보가 없는 짧은 청크에만 leaf 적용 (SHORT_LEN 미만)

사용:
  cd crawler && python exp_docinput.py
  cd crawler && python exp_docinput.py --sets 430 355 --variants cur leaf short
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

SHORT_LEN = 200        # 'short' 변형이 문맥을 붙일 청크 길이 임계
DEPTH = 50
KS = (1, 3, 5, 10, 30, 50)
VARIANTS = ("cur", "sub", "bc", "leaf", "short")


def bc_str(c: dict) -> str:
    b = c.get("breadcrumb", "")
    return " > ".join(b) if isinstance(b, list) else (b or "")


def doc_input(c: dict, mode: str) -> str:
    title = c.get("page_title", "")
    base = f"{title}\n{c['text']}" if title else c["text"]
    sub = c.get("sub_category", "")
    leaf = sub.split(" > ")[-1] if sub else ""
    if mode == "cur":
        return base
    if mode == "sub" and sub:
        return f"{sub}\n{base}"
    if mode == "bc" and bc_str(c):
        return f"{bc_str(c)}\n{base}"
    if mode == "leaf" and leaf:
        return f"{leaf}\n{base}"
    if mode == "short" and leaf and len(c["text"]) < SHORT_LEN:
        return f"{leaf}\n{base}"
    return base


def rank_matrix_from_scores(scores: np.ndarray) -> np.ndarray:
    """행별 내림차순 순위(0-based). faiss와 동일하게 점수 내림차순, 동점은 인덱스 오름차순."""
    order = np.argsort(-scores, axis=1, kind="stable")
    ranks = np.empty_like(order)
    rows = np.arange(scores.shape[0])[:, None]
    ranks[rows, order] = np.arange(scores.shape[1])[None, :]
    return ranks.astype("int32")


def sibling_cosine(embs: np.ndarray, chunks: list[dict]) -> tuple[float, float]:
    """(형제 쌍 평균 코사인, 비형제 쌍 평균). 형제 = sub_category의 부모 경로가 같고 잎이 다른 문서."""
    parent = {}
    for i, c in enumerate(chunks):
        sub = c.get("sub_category", "")
        parts = sub.split(" > ")
        parent[i] = (" > ".join(parts[:-1]), parts[-1] if parts else "", c["parent_doc_id"])
    sib, non = [], []
    n = len(chunks)
    for i in range(n):
        for j in range(i + 1, n):
            pi, li, di = parent[i]
            pj, lj, dj = parent[j]
            if di == dj:
                continue                       # 같은 문서 청크는 형제가 아니다
            cos = float(embs[i] @ embs[j])
            (sib if (pi and pi == pj and li != lj) else non).append(cos)
    return (statistics.mean(sib) if sib else float("nan"),
            statistics.mean(non) if non else float("nan"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", default=["430", "355"])
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS))
    ap.add_argument("--report", default="data/eval_docinput_report.md")
    args = ap.parse_args()

    searcher = rag.Searcher()
    chunks = searcher.chunks
    n_c = len(chunks)
    cid_index = {c["chunk_id"]: i for i, c in enumerate(chunks)}
    doc_of = np.array([c["parent_doc_id"] for c in chunks])
    nt = {c["chunk_id"]: ev3._norm_text(c.get("text", "")) for c in chunks}

    # ── 질의측은 건드리지 않는다(비대칭) — 변형은 문서측 입력에만 ──
    data = {}
    for name in args.sets:
        gt = ev3._load_jsonl(pathlib.Path(f"../final_testset/gt_natural{name}.jsonl"))
        items = [r for r in gt if r.get("answerable") is True and ev3._get_gt_chunk_ids(r)]
        qs = [r["question"] for r in items]
        qe = rag.embed_texts(qs)
        sparse = np.stack([searcher.bm25.get_scores(rag.tokenize(q)) for q in qs])
        rank_s = np.empty((len(qs), n_c), dtype="int32")
        for i in range(len(qs)):
            rank_s[i, np.argsort(sparse[i])[::-1]] = np.arange(n_c)
        qbf = [rag.classify_query_bf(q) for q in qs]
        bf_mask = np.zeros((len(qs), n_c), dtype="float32")
        fc_mask = np.zeros((len(qs), n_c), dtype="float32")
        for qi, (bf, q) in enumerate(zip(qbf, qs)):
            if bf is None:
                continue
            allow = rag.BF_SHARED_DOCS.get(bf, set())
            hit = np.array([(searcher._bf[i] == bf) or (chunks[i]["parent_doc_id"] in allow)
                            for i in range(n_c)], dtype=bool)
            bf_mask[qi] = hit
            f = rag.query_facets(q)
            if f:
                fc_mask[qi] = np.array(
                    [sum(1 for t in f if t in chunks[i].get("sub_category", ""))
                     for i in range(n_c)], dtype="float32") * hit
        # 문항별 판정 조건(앵커 하이브리드)
        need = []
        for it in items:
            gold = ev3._get_gt_chunk_ids(it)
            anchors = ev3._get_gt_anchors(it)
            sets = [s for s in ({cid_index[c] for c in nt if a in nt[c]} for a in anchors) if s]
            cov = set().union(*sets) if sets else set()
            sets += [{cid_index[c]} for c in gold if c in cid_index and cid_index[c] not in cov]
            need.append((ev3._get_relation(it) == "and", sets,
                         ev3._get_relation_label(it)))
        data[name] = dict(items=items, qe=qe, rank_s=rank_s, bf=bf_mask, fc=fc_mask, need=need)
        print(f"[gt] {name}: {len(items)}문항")

    def score(need, tops):
        m = {f"hit@{k}": 0 for k in KS}
        m["mrr"] = 0.0
        per = collections.defaultdict(lambda: [0, 0])
        for (is_and, sets, lab), ranked in zip(need, tops):
            if not sets:
                continue
            pos = {c: r for r, c in enumerate(ranked, 1)}
            firsts = [min((pos[c] for c in s if c in pos), default=None) for s in sets]
            need_rank = (None if any(f is None for f in firsts) else max(firsts)) if is_and \
                else (min([f for f in firsts if f is not None], default=None))
            per[lab][1] += 1
            if need_rank is None:
                continue
            for k in KS:
                if need_rank <= k:
                    m[f"hit@{k}"] += 1
            if need_rank <= 5:
                per[lab][0] += 1
            if need_rank <= 10:
                m["mrr"] += 1.0 / need_rank
        n = len(need)
        return {k: v / n for k, v in m.items()}, {l: (a / b, b) for l, (a, b) in per.items()}

    L = ["# 문서측 임베딩 입력 변형 A/B (앵커 판정)\n",
         f"- 융합 파라미터: alpha={rag.RRF_ALPHA} · rrf_k={rag.RRF_K} · bf={rag.BF_BOOST} "
         f"· facet={rag.FACET_BOOST} · cap={rag.BF_DOC_CAP} · depth={DEPTH}",
         "- 질의측 입력은 불변(비대칭). 문서측 dense 입력만 교체하고 BM25는 본문 기반이라 불변.\n"]
    results = {}
    for v in args.variants:
        ce = rag.embed_texts([doc_input(c, v) for c in chunks])
        sib, non = sibling_cosine(ce, chunks)
        line = {"variant": v, "sib_cos": sib, "non_cos": non}
        for name, D in data.items():
            rank_d = rank_matrix_from_scores(D["qe"] @ ce.T)
            s = (rag.RRF_ALPHA / (rag.RRF_K + rank_d + 1)
                 + (1 - rag.RRF_ALPHA) / (rag.RRF_K + D["rank_s"] + 1)
                 + rag.BF_BOOST * D["bf"] + rag.FACET_BOOST * D["fc"])
            tops = _topk_lists(s, doc_of, rag.BF_DOC_CAP, DEPTH, tie=rank_d)
            m, per = score(D["need"], tops)
            line[name] = m
            line[f"{name}_rel"] = per
        results[v] = line
        print(f"  {v:<6} 형제코사인 {sib:.4f} (비형제 {non:.4f}) · " +
              " · ".join(f"{n} hit@5 {line[n]['hit@5']:.4f}" for n in args.sets))

    L.append("## 전체 지표\n")
    L.append("| 변형 | 형제 코사인 | 비형제 | " +
             " | ".join(f"{n} hit@1 | {n} hit@5 | {n} hit@50 | {n} MRR" for n in args.sets) + " |")
    L.append("|---|---:|---:|" + "---:|" * (4 * len(args.sets)))
    for v in args.variants:
        r = results[v]
        cells = "".join(f" {r[n]['hit@1']:.4f} | {r[n]['hit@5']:.4f} | "
                        f"{r[n]['hit@50']:.4f} | {r[n]['mrr']:.4f} |" for n in args.sets)
        L.append(f"| `{v}` | {r['sib_cos']:.4f} | {r['non_cos']:.4f} |{cells}")

    for name in args.sets:
        labs = sorted({l for v in args.variants for l in results[v][f"{name}_rel"]})
        L.append(f"\n## {name} — relation별 hit@5\n")
        L.append("| 변형 | " + " | ".join(f"{l} (n={results[args.variants[0]][f'{name}_rel'][l][1]})"
                                          for l in labs) + " |")
        L.append("|---|" + "---:|" * len(labs))
        for v in args.variants:
            L.append(f"| `{v}` | " +
                     " | ".join(f"{results[v][f'{name}_rel'][l][0]:.4f}" for l in labs) + " |")

    pathlib.Path(args.report).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n[out] {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
