"""표 원자성 수정 A/B — `chunk.TABLE_GAP_MAX` on/off, GT 무수정.

문제: 표 셀 안 `<br>` 다항목이 파이프 없는 줄로 직렬화돼 표 블록을 끊는다.
보호대상 표(2,330자)가 10청크, 착오송금 구비서류가 20청크로 흩어져 조각마다
어느 행인지 알 수 없게 된다(HOLES H13 · DECISIONS 07-13 관찰 1).

수정: 파이프 줄 사이 비-파이프 줄을 셀 연속으로 흡수. 표는 크기와 무관하게
단독 청크(chunk.py 규약 "표 절대 중간분할 금지").

**측정 원칙 — GT를 고쳐 지표를 올리지 않는다.**
  주지표는 `single`(430에서 370건). gold 1개·앵커 1개라 재청킹해도 판정 구조가
  불변이고 앵커는 텍스트 매칭이라 chunk_id와 무관하다. 여기 변화가 순수 검색 변화다.
  `and`의 상승은 gold가 한 청크로 합쳐지며 생기는 **판정 완화**가 섞이므로 병합
  건수를 따로 세어 갈라 보고한다. 미앵커 gold는 원문 고유 줄 프로브로 재투영한다
  (GT 편집 아님) — exp_overlap.py와 같은 규약.

컨텍스트 비용도 함께 잰다 — 표를 합치면 청크가 커져 LLM 입력이 늘 수 있다.

사용:
  cd crawler && python exp_tablefix.py
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
from exp_overlap import rechunk, unique_probe, score_corpus
from tune_params import _topk_lists

GT_PATH = "../final_testset/gt_natural430.jsonl"
CHARS_PER_TOKEN = 1.7
SYS_LEN, FIXED = 304, 40


def variant(gap_max, overlap: int = 100):
    """TABLE_GAP_MAX만 바꿔 재청킹. gap_max=0 이 옛 동작(흡수 안 함) 대조군."""
    import importlib
    import tempfile
    import chunk as chunkmod
    importlib.reload(chunkmod)
    chunkmod.OVERLAP = overlap
    chunkmod.TABLE_GAP_MAX = gap_max
    out = pathlib.Path(tempfile.mkdtemp()) / "chunks.jsonl"
    chunkmod.OUT_PATH = str(out)
    chunkmod.DOC_ATT_PATH = str(out.parent / "doc_attachments.json")
    chunkmod.main()
    return ev3._load_jsonl(out)


def context_cost(chunks, items, bf_of, Ks=(3, 5)):
    """변형 코퍼스에서 top-K 컨텍스트 크기(자·토큰)와 HCX-003 한도 초과율."""
    n_c = len(chunks)
    doc_of = np.array([c["parent_doc_id"] for c in chunks])
    clen = np.array([len(c["text"]) + len(c.get("page_title", "")) + 10 for c in chunks])
    qs = [r["question"] for r in items]
    ce = rag.embed_texts([rag.chunk_embed_text(c) for c in chunks])
    qe = rag.embed_texts(qs)
    order = np.argsort(-(qe @ ce.T), axis=1, kind="stable")
    rank_d = np.empty((len(qs), n_c), "int32")
    rank_d[np.arange(len(qs))[:, None], order] = np.arange(n_c)
    from rank_bm25 import BM25Okapi
    bm = BM25Okapi([rag.tokenize(c["text"]) for c in chunks])
    rank_s = np.empty((len(qs), n_c), "int32")
    for i, q in enumerate(qs):
        rank_s[i, np.argsort(bm.get_scores(rag.tokenize(q)))[::-1]] = np.arange(n_c)
    bf = np.zeros((len(qs), n_c), "float32")
    fc = np.zeros((len(qs), n_c), "float32")
    for i, q in enumerate(qs):
        b = rag.classify_query_bf(q)
        if b is None:
            continue
        allow = rag.BF_SHARED_DOCS.get(b, set())
        hit = np.array([(bf_of[j] == b) or (chunks[j]["parent_doc_id"] in allow)
                        for j in range(n_c)], dtype=bool)
        bf[i] = hit
        f = rag.query_facets(q)
        if f:
            fc[i] = np.array([sum(1 for t in f if t in chunks[j].get("sub_category", ""))
                              for j in range(n_c)], "float32") * hit
    sc = (rag.RRF_ALPHA / (rag.RRF_K + rank_d + 1)
          + (1 - rag.RRF_ALPHA) / (rag.RRF_K + rank_s + 1)
          + rag.BF_BOOST * bf + rag.FACET_BOOST * fc)
    out = {}
    for K in Ks:
        tops = _topk_lists(sc, doc_of, rag.BF_DOC_CAP, K, tie=rank_d)
        v = sorted(int(clen[t].sum()) + SYS_LEN + FIXED + len(q)
                   for t, q in zip(tops, qs))
        out[K] = dict(med=statistics.median(v), avg=statistics.mean(v),
                      p95=v[int(len(v) * .95)], mx=max(v),
                      tok=statistics.mean(v) / CHARS_PER_TOKEN,
                      over=sum(1 for x in v if x / CHARS_PER_TOKEN > 7600) / len(v))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", default=["430", "355"])
    ap.add_argument("--report", default="data/eval_tablefix_report.md")
    args = ap.parse_args()

    base = {c["chunk_id"]: c for c in ev3._load_jsonl(pathlib.Path("data/chunks.jsonl"))}
    base_norm = {k: ev3._norm_text(v["text"]) for k, v in base.items()}
    items = [r for r in ev3._load_jsonl(pathlib.Path(GT_PATH))
             if r.get("answerable") is True and ev3._get_gt_chunk_ids(r)]

    probes = {}
    for it in items:
        anchors = ev3._get_gt_anchors(it)
        for c in ev3._get_gt_chunk_ids(it):
            if c in base_norm and not any(a in base_norm[c] for a in anchors) and c not in probes:
                probes[c] = unique_probe(base[c]["text"], base_norm, c)
    print(f"[재투영] 미앵커 gold {len(probes)}개 · 프로브 확보 {sum(1 for v in probes.values() if v)}개")

    rows = []
    for label, gap in (("off (현행)", 0), ("on gap<=12", 12), ("on 무제한", None)):
        chunks = variant(gap)
        nt = {c["chunk_id"]: ev3._norm_text(c.get("text", "")) for c in chunks}
        idx = {c["chunk_id"]: i for i, c in enumerate(chunks)}
        bfmap = rag.load_bf_map()
        import faq_bf_map as fbm
        bf_of = []
        for c in chunks:
            if bfmap and fbm.is_board(c):
                q = fbm.extract_question(c["text"])
                bf_of.append(bfmap.get(fbm.qhash(fbm.normalize_q(q))) if q else None)
            else:
                bf_of.append(c.get("business_function"))

        anchors_all = {a for it in items for a in ev3._get_gt_anchors(it)}
        kept = sum(1 for a in anchors_all if any(a in t for t in nt.values()))

        conds, merged, proj_fail = [], 0, 0
        for it in items:
            gold = ev3._get_gt_chunk_ids(it)
            anchors = ev3._get_gt_anchors(it)
            sets = [s for s in ({idx[c] for c in nt if a in nt[c]} for a in anchors) if s]
            cov_old = {c for c in gold if c in base_norm
                       and any(a in base_norm[c] for a in anchors)}
            for c in gold:
                if c in cov_old:
                    continue
                p = probes.get(c)
                s = {idx[k] for k in nt if p and ev3._norm_text(p) in nt[k]} if p else set()
                if s:
                    sets.append(s)
                else:
                    proj_fail += 1
            is_and = ev3._get_relation(it) == "and"
            if is_and and len(sets) > 1 and set.intersection(*map(set, sets)):
                merged += 1
            conds.append((is_and, sets, ev3._get_relation_label(it)))

        res = score_corpus(chunks, items, conds, bf_of)
        L = sorted(len(c["text"]) for c in chunks)
        # K=5 컨텍스트 비용
        n_c = len(chunks)
        doc_of = np.array([c["parent_doc_id"] for c in chunks])
        clen = np.array([len(c["text"]) + len(c.get("page_title", "")) + 10 for c in chunks])
        rows.append((label, chunks, res, kept, len(anchors_all), merged, proj_fail, L, clen, doc_of))
        r5 = res[5]
        print(f"  {label:<10} 청크 {n_c:>4} · 최대 {L[-1]:>5}자 · 앵커잔존 {kept}/{len(anchors_all)}"
              f" · 병합 {merged} · 투영실패 {proj_fail} | "
              f"K5 전체 {r5['_all'][0]:.4f} single {r5.get('single',(0,0))[0]:.4f} "
              f"and {r5.get('and',(0,0))[0]:.4f}")

    out = ["# 표 원자성 수정 A/B (`chunk.TABLE_GAP_MAX`)\n",
           "- 주지표 **`single`** — 판정 구조 불변이라 순수 검색 변화",
           "- `and` 상승분은 gold 병합(판정 완화)이 섞이므로 병합 건수 병기",
           "- GT 무수정 · 미앵커 gold는 원문 프로브 재투영\n",
           "| 설정 | 청크 | 최대자 | 800자초과 | 앵커잔존 | and병합 | K5 전체 | K5 single | K5 and | K3 single | K10 single |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for label, chunks, res, kept, tot, merged, pf, L, clen, doc_of in rows:
        g = lambda K, l: res[K].get(l, (float("nan"), 0))[0]
        out.append(f"| {label} | {len(chunks)} | {L[-1]:,} | {sum(1 for x in L if x>800)} | "
                   f"{kept}/{tot} | {merged} | {res[5]['_all'][0]:.4f} | {g(5,'single'):.4f} | "
                   f"{g(5,'and'):.4f} | {g(3,'single'):.4f} | {g(10,'single'):.4f} |")
    pathlib.Path(args.report).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n[out] {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
