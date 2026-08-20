"""OVERLAP 재청킹 A/B — GT 무수정 원칙으로 측정.

**이 실험의 함정과 방어**

재청킹하면 `chunk_id`가 바뀌어 `gt_chunk_ids` 조인이 깨진다. 여기서 GT를 새 청킹에
맞춰 고치면 지표는 오르지만 그건 **검색이 좋아진 게 아니라 채점을 고친 것**이다.
그래서 이 스크립트는 GT 파일을 절대 수정하지 않고, 다음 두 축으로만 읽는다.

  ① `single` 문항 (430에서 370건) — gold 1개·앵커 1개라 재청킹해도 판정 구조가
     그대로다. 앵커는 텍스트 매칭이라 chunk_id와 무관하다.
     **여기 변화가 곧 순수 검색 성능 변화다.** 이게 이 실험의 주지표.

  ② `and` 문항 (55건) — 재청킹으로 gold 둘이 한 청크에 합쳐지면 판정이 저절로
     쉬워진다. 이 상승분은 검색 개선이 아니라 **판정 완화**이므로 따로 세어
     '병합으로 인한 상승'과 '순위 개선으로 인한 상승'을 갈라 보고한다.

미앵커 gold(85개)는 chunk_id로만 조인되므로 재청킹 후 사라진다. 이를 **원문 프로브
재투영**으로 잇는다 — 옛 gold 청크에서 뽑은 고유 줄(코퍼스에서 그 청크에만 있던 줄)을
새 청크에서 찾는다. GT 편집이 아니라 같은 근거를 새 좌표로 옮기는 기계적 사상이며,
투영 실패율을 함께 보고해 신뢰 구간을 드러낸다.

앵커 잔존(파이프라인 문서 ⑥)도 같이 검증한다 — 재청킹 후 앵커가 여전히 **어느 한
청크에 온전히** 남는지. 잘리면 GT가 실제로 손상된 것이므로 그 자체가 비용이다.

사용:
  cd crawler && python eval_overlap.py
  cd crawler && python eval_overlap.py --overlaps 100 200 300 400
"""

from __future__ import annotations

import argparse
import collections
import importlib
import json
import pathlib
import statistics
import tempfile

import numpy as np

import rag
import eval_anchor_v3 as ev3
from tune_params import _topk_lists

GT_PATH = "../final_testset/gt_natural430.jsonl"
KS = (1, 3, 5, 10)
PROBE_MIN = 12          # 재투영 프로브로 쓸 줄의 최소 길이


def rechunk(overlap: int) -> list[dict]:
    """OVERLAP만 바꿔 재청킹. 원본 data/chunks.jsonl은 건드리지 않는다."""
    import chunk as chunkmod
    importlib.reload(chunkmod)
    out = pathlib.Path(tempfile.mkdtemp()) / "chunks.jsonl"
    chunkmod.OVERLAP = overlap
    chunkmod.OUT_PATH = str(out)
    chunkmod.DOC_ATT_PATH = str(out.parent / "doc_attachments.json")
    chunkmod.main()
    return ev3._load_jsonl(out)


def unique_probe(text: str, norm_all: dict[str, str], own: str) -> str | None:
    """그 청크에만 있던 가장 짧은 줄 — 재투영 프로브."""
    best = None
    for line in {l.strip() for l in text.split("\n") if len(l.strip()) >= PROBE_MIN}:
        nl = ev3._norm_text(line)
        owners = [k for k, t in norm_all.items() if nl in t]
        if len(owners) == 1 and owners[0] == own:
            if best is None or len(nl) < len(ev3._norm_text(best)):
                best = line
    return best


def score_corpus(chunks: list[dict], items: list[dict], conds: list, bf_of: list) -> dict:
    """새 코퍼스로 검색해 K별 relation 지표. 융합 파라미터는 현행 그대로."""
    n_c = len(chunks)
    doc_of = np.array([c["parent_doc_id"] for c in chunks])
    qs = [r["question"] for r in items]
    ce = rag.embed_texts([rag.chunk_embed_text(c) for c in chunks])
    qe = rag.embed_texts(qs)
    sim = qe @ ce.T
    order = np.argsort(-sim, axis=1, kind="stable")
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

    res = {}
    for K in KS:
        tops = _topk_lists(sc, doc_of, rag.BF_DOC_CAP, K, tie=rank_d)
        per = collections.defaultdict(lambda: [0, 0])
        for (is_and, sets, lab), ranked in zip(conds, tops):
            per[lab][1] += 1
            if not sets:
                continue
            pos = set(ranked)
            ok = (all(pos & s for s in sets) if is_and else any(pos & s for s in sets))
            per[lab][0] += bool(ok)
        res[K] = {l: (a / b, b) for l, (a, b) in per.items()}
        res[K]["_all"] = (sum(a for a, _ in per.values()) / sum(b for _, b in per.values()),
                          sum(b for _, b in per.values()))
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlaps", nargs="+", type=int, default=[100, 200, 300])
    ap.add_argument("--report", default="data/eval_overlap_report.md")
    args = ap.parse_args()

    base = {c["chunk_id"]: c for c in ev3._load_jsonl(pathlib.Path("data/chunks.jsonl"))}
    base_norm = {k: ev3._norm_text(v["text"]) for k, v in base.items()}
    items = [r for r in ev3._load_jsonl(pathlib.Path(GT_PATH))
             if r.get("answerable") is True and ev3._get_gt_chunk_ids(r)]

    # 미앵커 gold → 재투영 프로브 (원본 코퍼스에서 1회만 계산)
    probes: dict[str, str | None] = {}
    for it in items:
        anchors = ev3._get_gt_anchors(it)
        for c in ev3._get_gt_chunk_ids(it):
            if c in base_norm and not any(a in base_norm[c] for a in anchors) and c not in probes:
                probes[c] = unique_probe(base[c]["text"], base_norm, c)
    n_probe_ok = sum(1 for v in probes.values() if v)
    print(f"[재투영] 미앵커 gold 청크 {len(probes)}개 · 프로브 확보 {n_probe_ok}개")

    L = ["# OVERLAP 재청킹 A/B (GT 무수정)\n",
         "- 주지표는 **`single` 문항의 hit@K** — 재청킹해도 판정 구조가 불변이라 순수 검색 변화다.",
         "- `and`의 상승은 gold 병합에 의한 **판정 완화**가 섞이므로 병합 건수를 함께 본다.",
         "- 미앵커 gold는 원문 고유 줄 프로브로 재투영(GT 편집 아님). 투영 실패율 병기.\n"]
    rows = []
    for ov in args.overlaps:
        chunks = rechunk(ov)
        nt = {c["chunk_id"]: ev3._norm_text(c.get("text", "")) for c in chunks}
        idx = {c["chunk_id"]: i for i, c in enumerate(chunks)}
        # bf_map 조인 — FAQ 청크는 split_faq라 OVERLAP 영향 없음
        bfmap = rag.load_bf_map()
        import faq_bf_map as fbm
        bf_of = []
        for c in chunks:
            if bfmap and fbm.is_board(c):
                q = fbm.extract_question(c["text"])
                bf_of.append(bfmap.get(fbm.qhash(fbm.normalize_q(q))) if q else None)
            else:
                bf_of.append(c.get("business_function"))

        # ⑥ 앵커 잔존
        anchors_all = {a for it in items for a in ev3._get_gt_anchors(it)}
        kept = sum(1 for a in anchors_all if any(a in t for t in nt.values()))
        # 조건 집합 구성 + 병합/투영 집계
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
            rel = ev3._get_relation_label(it)
            is_and = ev3._get_relation(it) == "and"
            if is_and and len(sets) > 1 and set.intersection(*map(set, sets)):
                merged += 1          # 필요 근거가 한 청크에 모두 들어감 = 판정 완화
            conds.append((is_and, sets, rel))

        res = score_corpus(chunks, items, conds, bf_of)
        rows.append((ov, len(chunks), kept, len(anchors_all), merged, proj_fail, res))
        r5 = res[5]
        print(f"  OVERLAP={ov:<4} 청크 {len(chunks):>4} · 앵커잔존 {kept}/{len(anchors_all)}"
              f" · 병합 {merged} · 투영실패 {proj_fail} | "
              f"K5 전체 {r5['_all'][0]:.4f} single {r5.get('single',(0,0))[0]:.4f} "
              f"and {r5.get('and',(0,0))[0]:.4f}")

    L += ["| OVERLAP | 청크수 | 앵커 잔존 | and 병합 | 투영실패 | K5 전체 | K5 single | K5 and | K3 single | K10 single |",
          "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for ov, n, kept, tot, merged, pf, res in rows:
        g = lambda K, l: res[K].get(l, (float('nan'), 0))[0]
        L.append(f"| {ov} | {n} | {kept}/{tot} | {merged} | {pf} | {res[5]['_all'][0]:.4f} | "
                 f"{g(5,'single'):.4f} | {g(5,'and'):.4f} | {g(3,'single'):.4f} | {g(10,'single'):.4f} |")
    pathlib.Path(args.report).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n[out] {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
