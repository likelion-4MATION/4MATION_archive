#!/usr/bin/env python3
"""crawler/eval.py 등가성 회귀 테스트 — 통합 전 평가기와 판정이 같은지 못박는다.

**faiss·numpy·검색 인덱스가 없어도 돌아간다.** 판정 로직은 순수 함수라
(gt, retrieved, chunk_meta) 세 데이터만 있으면 검증 가능하다. 검색 자체를 태우지
않으므로 CI·클론 직후에도 실행된다.

방법
  실제 GT + 실제 `data/chunks.jsonl` 로 **결정론적 합성 retrieved** 를 만들고
  `archive/superseded/` 의 구 평가기와 `crawler/eval.py` 의 반환값·리포트를 비교한다.
  합성 retrieved 는 문항 인덱스로 gold 배치 위치를 정해(0=완전 miss … 7=완전 hit)
  hit@1~50·부분회수·미회수 경우를 모두 훑는다 — 전부 hit/전부 miss 인 축퇴 입력을 피한다.

  통합 시 §4(chunk 판정)는 구 `eval_anchor_v3.py` 를 **이름 변경 0건**으로 이식했다.
  이 테스트가 깨지면 그 이식이 훼손된 것이므로, 수치를 고치지 말고 원인을 찾을 것.

사용
    python3 crawler/tests/test_eval_equivalence.py     # 단독 실행
    pytest crawler/tests/test_eval_equivalence.py      # pytest 로도 수집됨
"""
from __future__ import annotations

import importlib.util as iu
import json
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CRAWLER = REPO / "crawler"
SUPERSEDED = REPO / "archive" / "superseded"

GT_MAIN = REPO / "final_testset" / "gt_natural430_anchored.jsonl"   # 정본 TEST
GT_ALT = CRAWLER / "gt_testset_retrieval_450.jsonl"
CHUNKS = CRAWLER / "data" / "chunks.jsonl"


# ── 로더 ───────────────────────────────────────────────────────────────────

def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _module(name: str, path: Path):
    spec = iu.spec_from_file_location(name, path)
    mod = iu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _install_rag_stub() -> None:
    """구 eval_doc_legacy.py 는 모듈 최상위에서 `import rag` 를 한다.

    통합 eval.py 는 rag 를 지연 임포트하므로 스텁이 필요 없다 — 스텁은
    archive 쪽 파일을 로드하기 위한 것뿐이다.
    """
    if "rag" in sys.modules:
        return
    stub = types.ModuleType("rag")
    stub.MODEL_NAME = "stub"
    stub.RRF_K, stub.RRF_ALPHA = 4, 0.65
    stub.BF_MODE, stub.BF_DOC_CAP, stub.BF_BOOST, stub.FACET_BOOST = "soft", 5, 0.06, 0.05

    class _S:                                    # noqa: D401
        def __init__(self, *a, **k):
            raise RuntimeError("검색 스택 없이 도는 테스트다 — Searcher 를 쓰면 안 된다.")

    stub.Searcher = _S
    stub.classify_query_bf = lambda q: None
    sys.modules["rag"] = stub


# ── 합성 retrieved ─────────────────────────────────────────────────────────

def synth_retrieved(gt: list[dict], all_ids: list[str], depth: int) -> list[dict]:
    """문항마다 gold 배치 위치를 바꿔 hit/miss/부분회수를 골고루 만든다(결정론)."""
    n = len(all_ids)
    out = []
    for i, item in enumerate(gt):
        gold = item.get("gt_chunk_ids") or (
            [item["gt_chunk_id"]] if item.get("gt_chunk_id") else [])
        if isinstance(gold, str):
            gold = [gold]
        gold = list(dict.fromkeys(gold))
        bg = [all_ids[(i * 7 + j * 13) % n] for j in range(depth)]
        bg = [c for c in bg if c not in gold]
        placement = i % 8
        ids = list(bg)
        if placement == 7:
            ids = gold + bg
        elif placement:
            for gi, g in enumerate(gold):
                if gi > placement:
                    break
                ids.insert(min(placement * 2 + gi, len(ids)), g)
        out.append({"id": item["id"], "retrieved_chunk_ids": ids[:depth]})
    return out


def deep_diff(a, b, path: str = "") -> list[str]:
    if type(a) is not type(b) and not (isinstance(a, (int, float))
                                       and isinstance(b, (int, float))):
        return [f"{path}: type {type(a).__name__} != {type(b).__name__}"]
    if isinstance(a, dict):
        out = []
        for k in set(a) | set(b):
            if k not in a:
                out.append(f"{path}.{k}: 신규에만 있음")
            elif k not in b:
                out.append(f"{path}.{k}: 구본에만 있음")
            else:
                out += deep_diff(a[k], b[k], f"{path}.{k}")
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: len {len(a)} != {len(b)}"]
        return [d for i, (x, y) in enumerate(zip(a, b))
                for d in deep_diff(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


# ── 검증 본문 ──────────────────────────────────────────────────────────────

def run() -> list[str]:
    """실패 메시지 목록을 반환한다(빈 리스트 = 통과)."""
    missing = [p for p in (GT_MAIN, CHUNKS, SUPERSEDED) if not p.exists()]
    if missing:
        return [f"필요한 파일이 없다: {', '.join(str(m) for m in missing)}"]

    _install_rag_stub()
    fails: list[str] = []
    chunks = _load(CHUNKS)
    all_ids = [c["chunk_id"] for c in chunks]

    new = _module("unified_eval", CRAWLER / "eval.py")
    old_v3 = _module("old_v3", SUPERSEDED / "eval_anchor_v3.py")
    old_sp = _module("old_sp", SUPERSEDED / "eval_anchor_span_multi.py")
    old_gd = _module("old_gd", SUPERSEDED / "eval_anchor_gold.py")
    old_doc = _module("old_doc", SUPERSEDED / "eval_doc_legacy.py")

    def check(tag: str, diffs: list[str]) -> None:
        if diffs:
            fails.append(f"{tag} — 차이 {len(diffs)}건: {diffs[:5]}")
            print(f"  ✗ {tag}")
        else:
            print(f"  ✓ {tag}")

    # 1. chunk 판정(정본) — GT 2종 × score 3종 + 청크메타 없는 경로
    gt_paths = [GT_MAIN] + ([GT_ALT] if GT_ALT.exists() else [])
    for gt_path in gt_paths:
        gt = _load(gt_path)
        ret = synth_retrieved(gt, all_ids, new.DEPTH_CHUNK)
        for score in new.SCORE_MODES:
            check(f"chunk / {gt_path.name} / score={score}",
                  deep_diff(new.evaluate_retrieval(gt, ret, chunks, score=score),
                            old_v3.evaluate_retrieval(gt, ret, chunks, score=score), "chunk"))

    gt = _load(GT_MAIN)
    ret = synth_retrieved(gt, all_ids, new.DEPTH_CHUNK)
    check("chunk / 청크메타 없음(doc_metrics=None)",
          deep_diff(new.evaluate_retrieval(gt, ret, None, score="chunk_id"),
                    old_v3.evaluate_retrieval(gt, ret, None, score="chunk_id"), "chunk"))

    # 2. span 판정 × id_fallback 2종
    ret10 = synth_retrieved(gt, all_ids, new.DEPTH_SPAN)
    for idf in (False, True):
        check(f"span / id_fallback={idf}",
              deep_diff(new.evaluate_span_retrieval(gt, ret10, chunks, idf),
                        old_sp.evaluate_span_retrieval(gt, ret10, chunks, idf), "span"))

    # 3. gold(앵커-host) 판정 + 통계 함수
    ret30 = synth_retrieved(gt, all_ids, 30)
    check("gold / 앵커-host 판정",
          deep_diff(list(new.evaluate_anchor_gold(gt, chunks, ret30)),
                    list(old_gd.evaluate(gt, chunks, ret30)), "gold"))
    stat_ok = all(new.wilson(k, n) == old_gd.wilson(k, n)
                  for k, n in ((0, 0), (1, 1), (37, 448), (448, 448), (200, 430)))
    stat_ok &= all(new.ndcg(r, k) == old_gd.ndcg(r, k)
                   for r in ([2, 0, 1, 0, 2], [0] * 10, [1, 1, 1], [2])
                   for k in (3, 5, 10))
    check("gold / wilson · ndcg 수치", [] if stat_ok else ["통계 함수 값 불일치"])

    # 4. 구세대 문서단위 지표 함수(§3 에 보존한 3개)
    hits = [{"parent_doc_id": f"d{i}"} for i in range(10)]
    doc_ok = all(new.first_hit_rank(hits, s) == old_doc.first_hit_rank(hits, s)
                 for s in ({"d0"}, {"d4"}, {"d9"}, {"zz"}, set()))
    per_q = [{"rank": r, "bf": f"bf{r % 3}"} for r in range(12)]
    doc_ok &= new.group_metrics(per_q, "bf") == old_doc.group_metrics(per_q, "bf")
    check("doc / first_hit_rank · group_metrics", [] if doc_ok else ["문서단위 지표 불일치"])

    # 5. 리포트 마크다운 — 바이트 동일
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        rn = new.evaluate_retrieval(gt, ret, chunks, score="both")
        ro = old_v3.evaluate_retrieval(gt, ret, chunks, score="both")
        new.write_report(rn, td / "a.md", GT_MAIN, "합성", chunks)
        old_v3.write_report(ro, td / "b.md", GT_MAIN, "합성", chunks)
        check("chunk 리포트 마크다운 바이트 동일",
              [] if (td / "a.md").read_bytes() == (td / "b.md").read_bytes()
              else ["리포트 내용이 다르다"])

        sn = new.evaluate_span_retrieval(gt, ret10, chunks, False)
        so = old_sp.evaluate_span_retrieval(gt, ret10, chunks, False)
        new.write_span_report(sn, td / "c.md", GT_MAIN, "합성", chunks)
        old_sp.write_report(so, td / "d.md", GT_MAIN, "합성", chunks)
        check("span 리포트 마크다운 바이트 동일",
              [] if (td / "c.md").read_bytes() == (td / "d.md").read_bytes()
              else ["리포트 내용이 다르다"])

    # 6. 하위호환 심볼 — 기존 호출부가 쓰는 이름이 전부 살아 있는지
    need = ["evaluate_retrieval", "evaluate_span_retrieval", "evaluate_anchor_gold",
            "_load_jsonl", "_norm_text", "norm_ws", "_get_gt_chunk_ids", "_get_gt_anchors",
            "_hit_at_k", "_anchor_hit_at_k", "_anchor_reciprocal_rank", "_recall_at_k",
            "_get_relation", "_get_relation_label", "_split_gold_by_anchor",
            "write_report", "write_span_report", "write_chunk_report",
            "wilson", "ndcg", "mcnemar", "first_hit_rank", "group_metrics",
            "load_jsonl", "KS", "KS_SPAN", "KS_GOLD", "RETRIEVAL_DEPTH", "DEPTH_SPAN"]
    absent = [n for n in need if not hasattr(new, n)]
    check("하위호환 심볼 전수", [f"누락: {absent}"] if absent else [])

    # 7. admin/runner.run_eval() 이 읽는 키
    r = new.evaluate_retrieval(gt, ret, new._load_jsonl(CHUNKS), score="both")
    m, an = r["chunk_level"], r.get("anchor_level") or {}
    need_keys = ("n_evaluated", "hit@1", "hit@3", "hit@5", "hit@10", "mrr", "macro_recall@50")
    miss_keys = [k for k in need_keys if k not in m] + ([] if "hit@5" in an else ["anchor.hit@5"])
    check("admin/runner.run_eval() 이 읽는 키", [f"누락: {miss_keys}"] if miss_keys else [])

    return fails


def test_eval_equivalence() -> None:
    """pytest 진입점."""
    fails = run()
    assert not fails, "\n".join(fails)


if __name__ == "__main__":
    print("=== crawler/eval.py 등가성 검증 (검색 스택 불필요) ===\n")
    result = run()
    print()
    if result:
        for line in result:
            print(f"실패: {line}")
        raise SystemExit(1)
    print("=" * 60)
    print("통과 — 통합 전후 판정이 완전히 일치한다.")
    print("=" * 60)
