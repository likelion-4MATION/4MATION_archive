"""융합 레이어 A/B 스윕 — 질의별 dense/BM25 점수를 1회 캐시하고 랭킹식만 갈아끼운다.

인덱스·청킹·GT 무수정. 캐시(data/qscore_cache.npz)는 최초 1회만 모델을 돌리고
이후 스윕은 numpy 연산이라 즉시 끝난다. 첫 변형은 현행 rag.py 로직 그대로이며,
retrieved_top30_kunam.jsonl과 top-30이 완전 일치하는지 검증한 뒤에만 결과를 신뢰한다.
"""
import io, json, sys, pathlib, argparse, collections
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rag
from eval_anchor_gold import evaluate, wilson, ndcg, load

D = pathlib.Path(__file__).resolve().parent / "data"
CACHE = D / "qscore_cache.npz"


def build_cache(gt, chunks):
    """질의 × 청크 dense 코사인 / BM25 원점수 행렬. 181청크라 통째로 들고 있어도 1MB 미만."""
    qs = [g["question"] for g in gt]
    emb = np.load(D / "index" / "emb.npy")                    # (N, d), 정규화 완료
    qe = rag.embed_texts(qs)                                  # (Q, d), 정규화 완료
    dense = qe @ emb.T                                        # 코사인
    import pickle  # 로컬 build_index.py가 만든 인덱스 — rag.py와 동일 경로, 외부 입력 아님
    with open(D / "index" / "bm25.pkl", "rb") as f:
        bm25 = pickle.load(f)["bm25"]
    toks = [rag.tokenize(q) for q in qs]
    # 동의어 확장은 rag.sparse()와 동일하게 걸어야 파리티가 성립한다.
    sparse = np.array([bm25.get_scores(rag.expand_query_tokens(t)) for t in toks], dtype="float32")
    np.savez(CACHE, dense=dense.astype("float32"), sparse=sparse,
             ids=np.array([g["id"] for g in gt]),
             toks=np.array([json.dumps(t, ensure_ascii=False) for t in toks]))
    return dense, sparse, toks


def get_cache(gt, chunks):
    if CACHE.exists():
        z = np.load(CACHE, allow_pickle=False)
        if len(z["ids"]) == len(gt):
            return z["dense"], z["sparse"], [json.loads(t) for t in z["toks"]]
    print("캐시 생성 중(모델 1회 로드)...", flush=True)
    return build_cache(gt, chunks)


def ranks_desc(scores):
    """현행 sparse()와 동일한 정렬 — argsort 내림차순(동점 시 인덱스 역순)."""
    return np.argsort(scores)[::-1]


class Fuser:
    def __init__(self, chunks):
        self.chunks = chunks
        self.titles = [set(rag.tokenize(f"{c.get('page_title') or ''} {c.get('page_type') or ''}"))
                       for c in chunks]
        # IDF: 제목 토큰이 몇 개 문서(청크)에 등장하는가 — 흔한 토큰의 겹침 가치를 깎는다.
        df = collections.Counter(t for ts in self.titles for t in ts)
        n = len(chunks)
        self.idf = {t: np.log(1 + n / c) for t, c in df.items()}

    def rank(self, qi, dense, sparse, toks, k=30, *, mode="rrf", alpha=None, rrf_k=None,
             dense_w=None, title_w=None, cap=None, bf_mult=True, title_idf=False,
             bf=None, facets=None):
        alpha = rag.RRF_ALPHA if alpha is None else alpha
        rrf_k = rag.RRF_K if rrf_k is None else rrf_k
        dense_w = rag.DENSE_W if dense_w is None else dense_w
        title_w = rag.TITLE_W if title_w is None else title_w
        # cap 기본값도 모듈 상수에서 읽는다 — 0으로 박아두면 파이프라인과 조용히 어긋난다.
        cap = (rag.BF_DOC_CAP if rag.BF_DOC_CAP < len(self.chunks) else 0) if cap is None else cap
        d, s = dense[qi], sparse[qi]
        N = len(self.chunks)
        sc = np.zeros(N, dtype="float64")

        if mode == "rrf":
            for r, i in enumerate(ranks_desc(d)):
                sc[i] += alpha / (rrf_k + r + 1)
            for r, i in enumerate(ranks_desc(s)):
                sc[i] += (1.0 - alpha) / (rrf_k + r + 1)
        elif mode == "norm":
            # 질의별 min-max 정규화 후 convex 결합 — 이산 순위를 거치지 않는다.
            nz = lambda v: (v - v.min()) / (v.max() - v.min()) if v.max() > v.min() else v * 0
            sc = alpha * nz(d) + (1.0 - alpha) * nz(s)
        else:
            raise ValueError(mode)

        # 업무/패싯 부스트 (현행: 같은 업무 청크 전체에 상수 가산)
        if bf is not None and rag.BF_BOOST > 0:
            allow = rag.BF_SHARED_DOCS.get(bf, set())
            for i, c in enumerate(self.chunks):
                if c.get("business_function") == bf or c["parent_doc_id"] in allow:
                    # 현행 rag.py는 dense 비례 곱셈. bf_mult=None이 옛 상수 가산 대조군.
                    sc[i] += rag.BF_BOOST * (1.0 if bf_mult is None else d[i] / max(d.max(), 1e-9))
                    if facets:
                        hit = sum(1 for t in facets if t in c.get("sub_category", ""))
                        if hit:
                            sc[i] += rag.FACET_BOOST * hit

        if mode == "rrf" and dense_w:
            sc += dense_w * d
        elif mode == "norm" and dense_w:
            pass  # norm 모드는 dense가 이미 연속항이라 중복 가산하지 않는다

        if title_w and toks:
            qt = set(toks)
            for i, ts in enumerate(self.titles):
                hit = qt & ts
                if hit:
                    if title_idf:
                        num = sum(self.idf.get(t, 0.0) for t in hit)
                        den = sum(self.idf.get(t, np.log(1 + len(self.chunks))) for t in qt)
                    else:
                        num, den = len(hit), len(qt)
                    sc[i] += title_w * num / den

        order = sorted(range(N), key=lambda i: -sc[i])
        if cap:
            seen, out = collections.Counter(), []
            for i in order:
                dd = self.chunks[i]["parent_doc_id"]
                if seen[dd] < cap:
                    out.append(i); seen[dd] += 1
            order = out
        return [self.chunks[i]["chunk_id"] for i in order[:k]]


def run(name, fuser, gt, chunks, dense, sparse, toks, **kw):
    ret = []
    for qi, g in enumerate(gt):
        bf = rag.classify_query_bf(g["question"])
        fac = rag.query_facets(g["question"]) if rag.FACET_BOOST > 0 else set()
        ret.append({"id": g["id"], "retrieved_chunk_ids":
                    fuser.rank(qi, dense, sparse, toks[qi], bf=bf, facets=fac, **kw)})
    rows, _, _ = evaluate(gt, chunks, ret)
    n = len(rows)
    h = {k: sum(1 for r in rows if 0 < r["rank"] <= k) / n for k in (1, 3, 5, 10, 30)}
    soft1 = sum(1 for r in rows if r["soft_rank"] == 1) / n
    nd5 = sum(ndcg(r["rels"], 5) for r in rows) / n
    mrr = sum(1 / r["rank"] for r in rows if 0 < r["rank"] <= 10) / n
    return {"name": name, "rows": rows, "ret": ret, "Hit@1": h[1], "Hit@3": h[3],
            "Hit@5": h[5], "Hit@10": h[10], "Hit@30": h[30], "MRR@10": mrr,
            "soft@1": soft1, "nDCG@5": nd5}


def mcnemar_p(base_rows, new_rows):
    import math
    b = {r["id"]: r["rank"] == 1 for r in base_rows}
    win = sum(1 for r in new_rows if r["rank"] == 1 and not b.get(r["id"], False))
    los = sum(1 for r in new_rows if r["rank"] != 1 and b.get(r["id"], False))
    n = win + los
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(min(win, los) + 1)) / 2 ** n) if n else 1.0
    return win, los, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="이름에 이 문자열이 든 변형만 실행")
    a = ap.parse_args()
    gt = [g for g in load(D / "gt_natural450_v10_anchor.jsonl") if g.get("answerable") is True]
    chunks = load(D / "chunks.jsonl")
    dense, sparse, toks = get_cache(gt, chunks)
    fuser = Fuser(chunks)

    variants = [
        ("baseline(현행)", {}),
        # #4 RRF 폐기 — 질의별 정규화 점수 융합
        *[(f"norm α={x}", dict(mode="norm", alpha=x)) for x in (0.5, 0.6, 0.7, 0.8, 0.9)],
        # #4 DENSE_W 민감도 곡선
        *[(f"DENSE_W={x}", dict(dense_w=x)) for x in (0.0, 0.25, 0.4, 0.5, 0.6, 0.75, 1.0, 1.5)],
        # #5 문서당 청크 캡
        *[(f"cap={c}", dict(cap=c)) for c in (2, 3, 4)],
        # #6 업무부스트 곱셈화
        ("bf_const(옛 상수 가산)", dict(bf_mult=None)),
        # #7 제목 겹침 IDF 가중
        ("title_idf", dict(title_idf=True)),
        *[(f"title_idf w={x}", dict(title_idf=True, title_w=x)) for x in (0.08, 0.15, 0.25)],
    ]
    res = []
    for name, kw in variants:
        if a.only and a.only not in name:
            continue
        res.append(run(name, fuser, gt, chunks, dense, sparse, toks, **kw))

    base = next((r for r in res if r["name"].startswith("baseline")), None)
    if base:
        actual = {r["id"]: r["retrieved_chunk_ids"]
                  for r in load(D / "retrieved_top30_kunam.jsonl")}
        same = sum(1 for r in base["ret"] if actual.get(r["id"]) == r["retrieved_chunk_ids"])
        top1 = sum(1 for r in base["ret"]
                   if actual.get(r["id"], [None])[0] == r["retrieved_chunk_ids"][0])
        print(f"[파리티] 시뮬레이터 vs 실제 파이프라인: top-30 완전일치 {same}/{len(base['ret'])} · "
              f"top-1 일치 {top1}/{len(base['ret'])}")

    print("\n| 변형 | Hit@1 | 95% CI | Hit@3 | Hit@5 | MRR@10 | soft@1 | nDCG@5 | vs base (개선/악화, p) |")
    print("|---|---:|---|---:|---:|---:|---:|---:|---|")
    n = len(base["rows"]) if base else 448
    for r in res:
        lo, hi = wilson(round(r["Hit@1"] * n), n)
        cmp = ""
        if base and r is not base:
            w, l, p = mcnemar_p(base["rows"], r["rows"])
            cmp = f"{w}/{l}, p={p:.3f}" + ("" if p < 0.05 else " ns")
        print(f"| {r['name']} | {r['Hit@1']:.3f} | [{lo:.3f},{hi:.3f}] | {r['Hit@3']:.3f} | "
              f"{r['Hit@5']:.3f} | {r['MRR@10']:.3f} | {r['soft@1']:.3f} | {r['nDCG@5']:.3f} | {cmp} |")


if __name__ == "__main__":
    main()
