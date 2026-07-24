"""harness.py — 검색 실험 하네스 (밤1 T1·T3, HCX 0콜).

프로덕션 아님 — 관측·기록용. crawler/rag.py의 계약 동결된 Searcher를 소비만 한다.

지표 셈법은 crawler/eval.py와 동일하게 맞춘다(실행·수정 없이 셈법만 복제):
  - k=KMAX(10)로 검색 → gt_docs에 속한 첫 청크의 1-based 랭크 = rank (없으면 null)
  - hit@1 = rank==1 · hit@3 = 1<=rank<=3 · MRR = mean(1/rank, 미적중 0)
  - macro = business_function 그룹별 지표의 단순평균
  ※ 계약 기본값 k=5는 무변경 — KMAX=10은 eval.py 셈법 복제이지 파라미터 신설이 아님.
    기록 topk는 상위 5개(계약 기본 k=5 기준), rank는 10위까지 판정될 수 있음.

사용:
  python3 exp/harness.py run    # T1: {merged, natural} × {hybrid, dense} 600행 → harness_results.jsonl + 집계
  python3 exp/harness.py probe  # T3: trapset_v0 20 + 대표 6 → trap_probe_results.jsonl + 대조표
"""
import collections
import json
import os
import pathlib
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")        # 네트워크는 CLOVA 1곳만 — HF 차단
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "crawler"))           # rag.py 무수정 원칙 — 경로는 실행 스크립트 쪽에서

KMAX = 10          # eval.py KMAX 동일
TOPK_RECORD = 5    # 기록용 top-k (계약 기본 k=5)
TESTSETS = {
    "merged": ROOT / "crawler" / "data" / "testset_merged.jsonl",
    "natural": ROOT / "crawler" / "data" / "testset_natural.jsonl",
}
RESULTS = pathlib.Path(__file__).resolve().parent / "harness_results.jsonl"
TRAPSET = pathlib.Path(__file__).resolve().parent / "trapset_v0.jsonl"
PROBE_OUT = pathlib.Path(__file__).resolve().parent / "trap_probe_results.jsonl"

# 베이스라인 v1 락(hw 재현치) — 재현 판정 기대값 (h1, h3, mrr)
V1_EXPECTED = {
    ("merged", "hybrid"): (0.673, 0.853, 0.768),
    ("merged", "dense"): (0.567, 0.727, 0.661),
    ("natural", "hybrid"): (0.513, 0.753, 0.647),
    ("natural", "dense"): (0.420, 0.680, 0.562),
}
V1_H3_MACRO = {("merged", "hybrid"): 0.835, ("natural", "hybrid"): 0.759}

_searcher = None


def get_searcher():
    """Searcher 1회 생성 후 재사용(임베딩 모델 로드 비용)."""
    global _searcher
    if _searcher is None:
        from rag import Searcher
        _searcher = Searcher(index_dir=str(ROOT / "crawler" / "data" / "index"))
    return _searcher


def load_jsonl(path) -> list[dict]:
    return [json.loads(l) for l in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def first_hit_rank(hits: list[dict], gt: set) -> int:
    """eval.py 동일 — gt_docs에 속한 첫 청크의 1-based 랭크, 없으면 0."""
    for r, c in enumerate(hits, 1):
        if c["parent_doc_id"] in gt:
            return r
    return 0


def _micro(items: list[dict]) -> dict:
    n = len(items)
    return {
        "n": n,
        "hit@1": sum(p["rank"] == 1 for p in items) / n,
        "hit@3": sum(p["rank"] is not None and p["rank"] <= 3 for p in items) / n,
        "mrr": sum((1.0 / p["rank"]) if p["rank"] else 0.0 for p in items) / n,
    }


def _macro_h3(items: list[dict]) -> float:
    groups = collections.defaultdict(list)
    for p in items:
        groups[p["bf"]].append(p)
    return sum(_micro(v)["hit@3"] for v in groups.values()) / len(groups)


def run() -> None:
    s = get_searcher()
    all_rows = []
    print(f"[run] corpus {len(s.chunks)}청크 · KMAX={KMAX} · 기록 top{TOPK_RECORD}")
    for ts_name, path in TESTSETS.items():
        testset = load_jsonl(path)
        for mode in ("hybrid", "dense"):
            for it in testset:
                gt = set(it["gt_docs"])
                hits = s.search(it["question"], k=KMAX, mode=mode)
                rank = first_hit_rank(hits, gt) or None
                all_rows.append({
                    "testset": ts_name, "query": it["question"], "mode": mode,
                    "topk": [{f: h[f] for f in ("parent_doc_id", "page_title", "business_function", "_score")}
                             for h in hits[:TOPK_RECORD]],
                    "gt_docs": it["gt_docs"],
                    "rank": rank,
                    "hit1": rank == 1,
                    "hit3": rank is not None and rank <= 3,
                    # 집계·후속 분석용 부가 필드
                    "bf": it["business_function"],
                    "representative": bool(it.get("representative")),
                })
            print(f"  [{ts_name}/{mode}] {len(testset)}문항 완료")

    with open(RESULTS, "w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[run] {len(all_rows)}행 → {RESULTS.name}\n")

    # ── 집계 + v1 재현 판정 ──────────────────────────────────
    print(f"{'set/mode':16} {'hit@1':>7} {'hit@3':>7} {'MRR':>7}   v1 기대(h1/h3/mrr) 판정")
    ok_all = True
    for (ts_name, mode), (e1, e3, em) in V1_EXPECTED.items():
        items = [r for r in all_rows if r["testset"] == ts_name and r["mode"] == mode]
        m = _micro(items)
        match = (round(m["hit@1"], 3), round(m["hit@3"], 3), round(m["mrr"], 3)) == (e1, e3, em)
        ok_all &= match
        print(f"{ts_name + '/' + mode:16} {m['hit@1']:>7.3f} {m['hit@3']:>7.3f} {m['mrr']:>7.3f}"
              f"   {e1:.3f}/{e3:.3f}/{em:.3f} {'✓ 일치' if match else '✗ 불일치'}")
    for (ts_name, mode), e in V1_H3_MACRO.items():
        items = [r for r in all_rows if r["testset"] == ts_name and r["mode"] == mode]
        mac = _macro_h3(items)
        match = round(mac, 3) == e
        ok_all &= match
        print(f"{ts_name + '/h3_macro':16} {mac:>23.3f}   {e:.3f} {'✓ 일치' if match else '✗ 불일치'}")

    for ts_name in TESTSETS:
        rep = [r for r in all_rows if r["testset"] == ts_name and r["mode"] == "hybrid" and r["representative"]]
        print(f"대표 6문항 top-3 적중({ts_name}/hybrid): {sum(r['hit3'] for r in rep)}/{len(rep)}")

    print(f"\n[업무별 hit@3 (merged/hybrid)]")
    items = [r for r in all_rows if r["testset"] == "merged" and r["mode"] == "hybrid"]
    groups = collections.defaultdict(list)
    for r in items:
        groups[r["bf"]].append(r)
    for bf, g in sorted(groups.items(), key=lambda x: -len(x[1])):
        m = _micro(g)
        print(f"  {bf:16} n={m['n']:3d}  hit@3={m['hit@3']:.3f}  MRR={m['mrr']:.3f}")

    print(f"\n[T1 재현 판정] {'성공 — v1 락 수치 전 항목 일치' if ok_all else '실패 — 불일치 항목 있음(리포트에 원인 후보 기록)'}")


def probe() -> None:
    """트랩 20 + 정상 대표 6 → 라우팅 신호 실측 (hybrid top-3 bf 구성 · dense 코사인 top1)."""
    s = get_searcher()
    traps = load_jsonl(TRAPSET)
    normals = [it for it in load_jsonl(TESTSETS["merged"]) if it.get("representative")]
    queries = ([{"query": t["query"], "group": "trap", "trap_type": t["trap_type"],
                 "expected_route": t["expected_route"]} for t in traps]
               + [{"query": it["question"], "group": "normal", "trap_type": None,
                   "expected_route": "rag"} for it in normals])

    rows = []
    for q in queries:
        top3 = s.search(q["query"], k=3, mode="hybrid")
        d1 = s.search(q["query"], k=1, mode="dense")[0]
        bfs = [h["business_function"] for h in top3]
        bf_top, bf_cnt = collections.Counter(bfs).most_common(1)[0]
        rows.append({
            **q,
            "top3": [{f: h[f] for f in ("parent_doc_id", "page_title", "business_function", "_score")}
                     for h in top3],
            "bf_list": bfs,
            "bf_majority": bf_top, "bf_majority_n": bf_cnt,
            "bf_unanimous": bf_cnt == 3,
            "dense_top1_score": round(d1["_score"], 4),
            "dense_top1_bf": d1["business_function"],
            "hybrid_top1_score": top3[0]["_score"],
        })
    with open(PROBE_OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[probe] {len(rows)}행 → {PROBE_OUT.name}\n")

    def stat(vals):
        v = sorted(vals)
        n = len(v)
        return f"min {v[0]:.3f} · 중앙값 {v[n // 2]:.3f} · max {v[-1]:.3f}"

    print(f"{'그룹/유형':24} {'n':>3} {'bf만장일치':>9} {'dense top1 코사인':>30}")
    for g in ("normal", "trap"):
        sub = [r for r in rows if r["group"] == g]
        print(f"{g:24} {len(sub):>3} {sum(r['bf_unanimous'] for r in sub):>7}/{len(sub)}"
              f"   {stat([r['dense_top1_score'] for r in sub])}")
        if g == "trap":
            for tt in ("해외 보호한도", "타기관 소관", "업무 혼동", "구정보 확인형"):
                tsub = [r for r in sub if r["trap_type"] == tt]
                if tsub:
                    print(f"  └ {tt:18} {len(tsub):>3} {sum(r['bf_unanimous'] for r in tsub):>7}/{len(tsub)}"
                          f"   {stat([r['dense_top1_score'] for r in tsub])}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        run()
    elif cmd == "probe":
        probe()
    else:
        sys.exit("사용법: python3 exp/harness.py [run|probe]")
