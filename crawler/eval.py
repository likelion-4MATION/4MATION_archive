"""통합 검색 평가 — 청크·스팬·앵커 3종 판정을 한 파일에서 담당한다.

이 파일은 다음 5개 평가 스크립트를 하나로 합친 결과다(2026-08-24 통합).
archive/superseded/ 에 원본이 그대로 남아 있다.

| 흡수한 원본                        | 대응 서브커맨드 | 상태 |
|-----------------------------------|----------------|------|
| `eval_anchor_v3.py`               | `chunk`        | **정본** — 로직 무변경 이식 |
| `eval_anchor_span_multi.py`       | `span`         | 다중 span AND 판정 |
| `eval_anchor_gold.py`             | `gold`         | 앵커-host 판정 + Wilson/nDCG/McNemar |
| `eval.py` (구세대, parent_doc_id)  | —              | 평가셋 소실·폐기. 지표 함수만 §3 에 보존 |
| `eval_TF.py` · `eval_pair.py`      | —              | 평가셋 소실. archive 로 이동 |

⚠ 이름 주의 — 이 `eval.py` 는 **구세대 `eval.py`(parent_doc_id 판정, 폐기)가 아니다.**
기존 문서에서 "eval.py = 폐기된 구세대 평가"로 읽히는 서술은 archive/superseded/
eval_doc_legacy.py 를 가리킨다. 판정 기준은 `docs/records/handoff/eval_유상.md` §5 #3 을 따른다.

세 판정의 의미가 서로 달라 "중복 제거"로 하나만 남기지 않았다. 실제로 중복이던
것(로더·정규화·표 헬퍼·GT 파서·검색 실행)만 §2 로 합쳐 단일 지점을 만들었다.

  - `chunk` : **앵커텍스트 판정(정본).** KS=1~50, relation ANY/ALL. **admin 콘솔이 쓰는 경로.**
              `gt_chunk_ids` 는 판정에 쓰지 않는다 — 특정 청킹에 대한 좌표라 재청킹하면
              값이 변하고, 그러면 수치가 검색 성능이 아니라 판정 방식 때문에 움직인다.
              앵커가 없는 문항은 분모에서 뺀다(미적중이 아니라 판정 불가).
              구 하이브리드 동작(앵커 미커버 gold 를 id 로 요구)은 `--id-fallback` 으로만.
  - `span`  : `gt_anchor_spans`(청크별 정렬 리스트) 전부 발견해야 AND hit. KS=1~10.
  - `gold`  : 앵커를 포함한 **모든** 청크를 host 로 계산(gold id 무관). 등급 nDCG·
              Wilson CI·McNemar 유의성 검정 제공.

사용:
    cd crawler
    python eval.py chunk --gt ../final_testset/gt_natural430_anchored.jsonl   # 앵커 판정(기본)
    python eval.py chunk --gt ... --score chunk_id|anchor|both --mode hybrid_bf
    python eval.py chunk --gt ... --id-fallback     # 구 하이브리드 판정(라벨 잔량 감사용)
    python eval.py span  --gt ... --mode hybrid_bf [--id-fallback] [--limit N]
    python eval.py gold  --gt ... --retrieved data/retrieved_top30.jsonl [--compare other.jsonl]
    python eval.py              # 인자 없으면 chunk (구 eval_anchor_v3.py 기본 동작)

임포트 계약(하위호환) — 기존 호출부가 쓰던 이름을 전부 유지한다.
    import eval as ev3
    ev3.evaluate_retrieval(...) · ev3._load_jsonl(...) · ev3._norm_text(...)
    ev3._get_gt_chunk_ids(...) · ev3._get_gt_anchors(...) · ev3._hit_at_k(...)
    ev3._anchor_hit_at_k(...) · ev3._anchor_reciprocal_rank(...) · ev3._recall_at_k(...)
    ev3._get_relation(...) · ev3._get_relation_label(...) · ev3._split_gold_by_anchor(...)
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Iterable


# ══════════════════════════════════════════════════════════════════════════
# §1. 상수 — 판정 방식마다 K 범위와 검색 깊이가 다르다. 섞으면 수치가 조용히 틀린다.
# ══════════════════════════════════════════════════════════════════════════

# chunk 판정(정본). KS 를 접두어 없이 두는 이유: 구 eval_anchor_v3.py 본문을 이름
# 변경 0건으로 이식하기 위해서다. 외부 호환용 별칭은 §7 에 있다.
KS = (1, 3, 5, 10, 30, 50)
RECALL_KS = (3, 5, 10, 30, 50)
RETRIEVAL_DEPTH = 50   # 검색 깊이(recall@30/50 측정 위해 50까지)
MRR_DEPTH = 10        # MRR은 @10 유지
SCORE_MODES = ("chunk_id", "anchor", "both")

KS_CHUNK = KS
RECALL_KS_CHUNK = RECALL_KS
DEPTH_CHUNK = RETRIEVAL_DEPTH

# span 판정 — 구 eval_anchor_span_multi.py 는 깊이 10 에서만 채점했다. 값을 바꾸면
# 커밋된 span 리포트와 비교가 끊기므로 원본 그대로 둔다.
KS_SPAN = (1, 3, 5, 10)
RECALL_KS_SPAN = (3, 5, 10)
DEPTH_SPAN = 10

# gold(앵커-host) 판정 — 구 eval_anchor_gold.py.
KS_GOLD = (1, 3, 5, 10, 30)
# 등급 relevance: 앵커 보유 청크=2(정답 근거), GT가 함께 라벨한 gt_chunk_ids=1(답변 가능).
# strict Hit만 보면 GT 스스로 relevant로 표시한 청크를 1위로 뽑아도 실패로 세게 된다.
REL_HOST, REL_GT = 2, 1

# 구세대 문서단위 평가(§3) 잔존 상수.
KMAX_DOC = 10


# ══════════════════════════════════════════════════════════════════════════
# §2. 공용 유틸 — 통합의 실질. 아래 함수들은 원래 3개 파일에 같은 코드로
#     복제돼 있었다(로더·표 헬퍼·GT 파서는 바이트 동일, 검색 실행·data 탐색은
#     인자 하나 차이). 여기 한 벌만 두고 차이는 인자로 표현한다.
# ══════════════════════════════════════════════════════════════════════════


def _default_data_dir(marker: str = "gt_schema_v6.jsonl") -> Path:
    """스크립트 위치에서 위로 올라가며 marker 를 품은 data 폴더를 찾는다.

    구 eval_anchor_v3 는 marker='gt_schema_v6.jsonl', 구 eval_anchor_span_multi 는
    'chunks.jsonl' 을 찾았다 — 함수는 같고 marker 만 달랐다.
    """
    for parent in Path(__file__).resolve().parents:
        data_dir = parent / "data"
        if (data_dir / marker).is_file():
            return data_dir
    raise FileNotFoundError(f"{marker}을 포함한 data 폴더를 찾을 수 없습니다.")


def _load_jsonl(path: Path) -> list[dict]:
    """JSONL 정본 로더. 구 파일들의 _load_jsonl / load / load_testset 을 대체한다."""
    with Path(path).open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _norm_text(text: str) -> str:
    """앵커·청크 텍스트 공통 정규화 — 공백/개행 차이만 흡수하고 문자는 보존.

    chunk 판정(정본)이 쓰는 규칙. NFKC 를 거치므로 전각/반각·호환문자도 흡수한다.
    """
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def norm_ws(text: str | None) -> str:
    """공백만 제거하는 정규화(NFKC 없음) — 구 span/gold 판정의 규칙.

    `_norm_text` 로 통일하지 않는다. NFKC 를 추가하면 두 평가기의 판정 결과가
    바뀌어 커밋된 리포트와 비교가 끊긴다. 규칙이 다른 것은 버그가 아니라
    측정 축의 차이이므로 둘 다 남긴다.
    """
    return "".join((text or "").split())


def _format_ids(chunk_ids: list[str]) -> str:
    return "<br>".join(f"`{chunk_id}`" for chunk_id in chunk_ids) or "-"


def _pct_table(counter: dict, total: int, headers: tuple[str, str]) -> list[str]:
    lines = [f"| {headers[0]} | {headers[1]} |", "|---|---:|"]
    for key, count in sorted(counter.items(), key=lambda kv: -kv[1]):
        pct = count / total * 100 if total else 0.0
        lines.append(f"| {key} | {count} ({pct:.1f}%) |")
    return lines


def _print_group(title: str, rows: list[tuple[str, str]]) -> None:
    """제목 아래 key: value를 한 줄씩 나열하고, 라벨 너비를 맞춘 표 느낌으로 출력한다."""
    print(f"[{title}]")
    label_width = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"  {label.ljust(label_width)} : {value}")
    print()  # 다음 그룹과 빈 줄 하나(연속 줄바꿈 두 번) 간격.


def _search_results(gt_data: Iterable[dict], mode: str, data_dir: Path,
                    depth: int = RETRIEVAL_DEPTH, gold_bf: bool = True) -> list[dict]:
    """검색 실행. gold_bf=True 이고 mode='hybrid_bf' 면 gold business_function 을 주입해
    순수 검색기만 평가한다.

    라우터는 별도 테스트셋에서 평가 중 → 여기선 classify_query_bf(질의 분류)를 태우지 않고
    레코드의 gold business_function을 주입한다. 배포 soft 경로(hybrid_soft+cap)를 그대로 복제.

    구 두 파일의 차이를 인자로 흡수했다:
      chunk(정본) : depth=50, gold_bf=True   — 구 eval_anchor_v3._search_results
      span        : depth=10, gold_bf=False  — 구 eval_anchor_span_multi._search_results
    """
    import rag

    searcher = rag.Searcher(index_dir=str(data_dir / "index"))

    def gold_injected(question: str, gold_bf_value: str) -> list[str]:
        # rag.search(mode='hybrid_bf') under BF_MODE='soft' 의 복제 — 단 bf=gold
        pool = searcher.hybrid_soft(question, len(searcher.chunks),
                                    bf=gold_bf_value, boost=rag.BF_BOOST)
        capped = searcher._cap_by_doc(pool, rag.BF_DOC_CAP)[:depth]
        return [searcher.chunks[idx]["chunk_id"] for idx, _ in capped]

    results = []
    for item in gt_data:
        if gold_bf and mode == "hybrid_bf":
            rids = gold_injected(item["question"], item["business_function"])
        else:
            rids = [hit["chunk_id"] for hit in
                    searcher.search(item["question"], k=depth, mode=mode)]
        results.append({"id": item["id"], "retrieved_chunk_ids": rids})
    return results


def _retriever_desc() -> tuple[str, str]:
    """리포트 머리말용 (retriever, embedding) 설명. rag 미로드 환경도 견딘다."""
    try:
        import rag
        return (f"RRF(k={rag.RRF_K}, alpha={rag.RRF_ALPHA}) + "
                f"BF_MODE={rag.BF_MODE}(cap={rag.BF_DOC_CAP}, boost={rag.BF_BOOST}, "
                f"facet={rag.FACET_BOOST})", rag.MODEL_NAME)
    except Exception:
        return ("정보 없음(외부 검색 결과 사용)", "정보 없음(외부 검색 결과 사용)")


# ── 통계 (구 eval_anchor_gold.py) — 다른 어느 평가기에도 없던 유일 자산 ────────

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """이항비율 Wilson 95% CI — n=448에서 정규근사보다 안전하고 한 줄이다."""
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def ndcg(rels: list[int], k: int) -> float:
    """rels = 검색 순위대로의 등급 리스트. 이상 정렬 대비 정규화."""
    dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rels[:k]))
    ideal = sum(r / math.log2(i + 2) for i, r in enumerate(sorted(rels, reverse=True)[:k]))
    return dcg / ideal if ideal else 0.0


def mcnemar(base: list[dict], new: list[dict], blabel: str, nlabel: str) -> None:
    """Hit@1 짝지은 비교 — 개선/악화 건수만으로 이항검정(정확검정, 근사 아님)."""
    b = {r["id"]: r["rank"] == 1 for r in base}
    win = sum(1 for r in new if r["rank"] == 1 and not b.get(r["id"], False))
    los = sum(1 for r in new if r["rank"] != 1 and b.get(r["id"], False))
    n = win + los
    # 양측 이항검정 p (H0: 개선·악화가 동등, p=0.5)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(min(win, los) + 1)) / 2 ** n) if n else 1.0
    print(f"\n=== McNemar Hit@1: {blabel} → {nlabel} ===")
    print(f"개선 {win}건 · 악화 {los}건 · 순 {win-los:+d}건 · 양측 p={p:.4f} "
          f"{'(유의)' if p < 0.05 else '(유의하지 않음 — 노이즈와 구분 불가)'}")


# ══════════════════════════════════════════════════════════════════════════
# §3. 문서단위(parent_doc_id) 지표 — 구세대 평가기의 잔존 계약.
#
# 구 eval.py / eval_TF.py / eval_pair.py 는 기본 평가셋이 디스크에서 사라져
# 실행 불가 상태이며 archive/superseded/ 로 옮겼다(docs/records/handoff/eval_유상.md §3
# 이 이미 "폐기(참조용)"로 판정). 다만 아래 3개 함수는 다른 코드가 임포트할 수
# 있는 순수 지표 함수라 여기 남긴다 — 되살릴 때 판정 로직을 다시 쓰지 않도록.
#
# ⚠ '같은 문서면 적중' 거품이 있는 구세대 판정이다. 신규 측정에는 쓰지 말고
#    chunk/span/gold 판정을 쓸 것.
# ══════════════════════════════════════════════════════════════════════════

def first_hit_rank(hits: list[dict], gt: set[str]) -> int:
    """gt_docs에 속한 첫 청크의 1-based 랭크. 없으면 0."""
    for r, c in enumerate(hits, 1):
        if c["parent_doc_id"] in gt:
            return r
    return 0

def _row(items: list[dict]) -> dict:
    """문항 리스트 → hit@1·hit@3·MRR (해당 그룹의 micro 지표)."""
    n = len(items)
    return {
        "n": n,
        "hit@1": sum(p["rank"] == 1 for p in items) / n,
        "hit@3": sum(1 <= p["rank"] <= 3 for p in items) / n,
        "mrr": sum((1.0 / p["rank"] if p["rank"] else 0.0) for p in items) / n,
    }

def group_metrics(per_q: list[dict], key: str) -> tuple[dict, dict]:
    """key별 지표 표 + 그룹 단순평균(macro). 반환: (그룹별 rows, macro dict)."""
    groups: dict[str, list] = collections.defaultdict(list)
    for p in per_q:
        groups[p[key]].append(p)
    rows = {g: _row(items) for g, items in groups.items()}
    g = len(rows)
    macro = {m: sum(r[m] for r in rows.values()) / g for m in ("hit@1", "hit@3", "mrr")}
    macro["groups"] = g
    return rows, macro

# ══════════════════════════════════════════════════════════════════════════
# §4. chunk / 앵커텍스트 판정 — **정본**. 구 eval_anchor_v3.py 를 이름 변경
#     0건으로 이식했다. 로직·집계 키·반환 dict 전부 무변경이므로 admin 콘솔의
#     run_eval() 과 커밋된 eval_v3_*.md 수치가 그대로 재현된다.
#     (§2 로 옮긴 것: _default_data_dir · _load_jsonl · _norm_text ·
#      _format_ids · _pct_table · _print_group · _search_results)
# ══════════════════════════════════════════════════════════════════════════

def _get_gt_chunk_ids(item: dict) -> list[str]:
    """새 ``gt_chunk_ids`` 우선, 비어 있으면 구형 단일 gold를 사용한다."""
    chunk_ids = item.get("gt_chunk_ids")
    if chunk_ids:
        if isinstance(chunk_ids, str):
            chunk_ids = [chunk_ids]
        return list(dict.fromkeys(chunk_ids))
    chunk_id = item.get("gt_chunk_id")
    return [chunk_id] if chunk_id else []

# chunk_relation 별칭 → 채점 의미. v9 라벨(gt_natural882)이 gold 간 관계를 더 잘게
# 쪼개 기록하면서 near_dup/duplicate/contained가 등장했다. 셋 다 "gold 중 어느 하나로도
# 답이 된다"는 ANY이며, 실측으로 확인했다 — duplicate는 gold 본문 유사도 1.000(완전
# 동일), near_dup은 0.934~0.996, contained는 앵커가 gold 전부에 들어 있다.
# 알 수 없는 값은 계속 예외로 막는다. 조용히 ANY로 흘리면 스키마 드리프트가 묻힌다.
RELATION_ANY = {"single", "or", "duplicate", "near_dup", "contained"}

RELATION_ALL = {"and"}

def _get_relation_label(item: dict) -> str:
    """원본 chunk_relation 문자열(리포트 분해용). null/누락은 single."""
    return item.get("chunk_relation") or "single"

def _get_relation(item: dict) -> str:
    """채점에 쓰는 정규화 relation — ANY 계열은 'or', ALL은 'and'로 접는다.

    null/누락 relation은 확정 스키마의 단일 근거 레코드로 처리한다.
    """
    label = _get_relation_label(item)
    if label in RELATION_ALL:
        return "and"
    if label in RELATION_ANY:
        # 'single'은 gold 1개 전제라 'or'와 판정이 같지만, 기존 수치·감사 로그와의
        # 연속성을 위해 표기를 보존한다(_hit_at_k에서 둘 다 ANY로 처리).
        return "single" if label == "single" else "or"
    raise ValueError(f"{item.get('id')}: unsupported chunk_relation={label!r}")

def _hit_at_k(gold_ids: list[str], retrieved_ids: list[str], relation: str, k: int) -> bool:
    """single/or는 ANY, and는 ALL 조건으로 청크 hit을 판정한다."""
    if not gold_ids:
        return False
    top_k = set(retrieved_ids[:k])
    if relation in {"single", "or"}:
        return bool(set(gold_ids) & top_k)
    return set(gold_ids).issubset(top_k)

def _recalled_gold_at_k(gold_ids: list[str], retrieved_ids: list[str], k: int) -> int:
    """Top-k에 회수된 서로 다른 gold chunk 수를 반환한다."""
    return len(set(gold_ids) & set(retrieved_ids[:k]))

def _recall_at_k(gold_ids: list[str], retrieved_ids: list[str], k: int) -> float:
    """한 문항의 gold chunk coverage를 반환한다."""
    if not gold_ids:
        return 0.0
    return _recalled_gold_at_k(gold_ids, retrieved_ids, k) / len(set(gold_ids))

def _recall_at_10(gold_ids: list[str], retrieved_ids: list[str]) -> float:
    """Top-10에 회수된 gold chunk 비율(관계와 무관한 gold coverage)이다."""
    return _recall_at_k(gold_ids, retrieved_ids, 10)

def _reciprocal_rank(gold_ids: list[str], retrieved_ids: list[str], relation: str) -> float:
    """ANY는 첫 gold, AND는 마지막 필수 gold가 나온 순위의 역수다."""
    if not gold_ids:
        return 0.0
    gold_set = set(gold_ids)
    seen: set[str] = set()
    for rank, chunk_id in enumerate(retrieved_ids, 1):
        if chunk_id not in gold_set:
            continue
        if relation in {"single", "or"}:
            return 1.0 / rank
        seen.add(chunk_id)
        if seen == gold_set:
            return 1.0 / rank
    return 0.0

def _get_gt_anchors(item: dict) -> list[str]:
    """정규화된 앵커 리스트. gt_anchors(신) 우선, gt_anchor_span(구) 폴백."""
    anchors = item.get("gt_anchors")
    if isinstance(anchors, str):
        anchors = [anchors]
    if not anchors:
        span = item.get("gt_anchor_span")
        anchors = [span] if span else []
    return list(dict.fromkeys(_norm_text(a) for a in anchors if a and a.strip()))

def _split_gold_by_anchor(gold_ids: list[str], anchors: list[str],
                          chunk_text: dict[str, str]) -> tuple[list[str], list[str]]:
    """(chunk_id 폴백 대상, 코퍼스에 없는 gold) 로 나눈다.

    `gt_chunk_ids`는 **특정 청킹에 대한 좌표**다. 재청킹하면 일부 id가 사라지는데,
    사라진 id를 필수 조건으로 남기면 `and` 문항이 영구 불가능해진다 — 엄격한 게
    아니라 판정이 망가진 것이다(앵커를 아무리 채워도 그 id 안에서는 찾을 수 없다).
    그래서 **코퍼스에 없는 gold는 조건에서 빼고 별도로 센다.** 세는 이유는 판정이
    앵커에만 의존하는 비율을 감추지 않기 위해서다.

    코퍼스에 있으면서 앵커가 안 덮는 gold는 여전히 chunk_id 폴백으로 요구한다.
    """
    fallback, stale = [], []
    for cid in gold_ids:
        if cid not in chunk_text:
            stale.append(cid)
        elif not any(a in chunk_text[cid] for a in anchors):
            fallback.append(cid)
    return fallback, stale

def _anchor_found_at_k(anchor: str, retrieved_ids: list[str],
                       chunk_text: dict[str, str], k: int) -> bool:
    return any(anchor in chunk_text.get(cid, "") for cid in retrieved_ids[:k])

def _anchor_hit_at_k(anchors: list[str], unanchored: list[str], retrieved_ids: list[str],
                     chunk_text: dict[str, str], relation: str, k: int) -> bool:
    if not anchors and not unanchored:
        return False
    top_k = set(retrieved_ids[:k])
    if relation == "and":
        return (all(_anchor_found_at_k(a, retrieved_ids, chunk_text, k) for a in anchors)
                and set(unanchored).issubset(top_k))
    return (any(_anchor_found_at_k(a, retrieved_ids, chunk_text, k) for a in anchors)
            or bool(set(unanchored) & top_k))

def _anchor_reciprocal_rank(anchors: list[str], unanchored: list[str],
                            retrieved_ids: list[str], chunk_text: dict[str, str],
                            relation: str) -> float:
    """조건이 충족되는 최초 순위의 역수. and는 마지막 필수 근거가 나온 순위."""
    for rank in range(1, min(len(retrieved_ids), MRR_DEPTH) + 1):
        if _anchor_hit_at_k(anchors, unanchored, retrieved_ids, chunk_text, relation, rank):
            return 1.0 / rank
    return 0.0

def _empty_anchor_metrics() -> dict:
    # Recall은 두지 않는다 — 앵커는 '회수 비율'의 분모가 되는 단위가 아니다.
    # 0.000을 찍으면 chunk_level의 recall과 나란히 놓였을 때 오독되므로 아예 뺀다.
    return {"n_scored": 0, "n_missing_span": 0, "n_full_anchor": 0, "n_id_fallback": 0,
            "n_stale_gold": 0, "n_stale_only": 0,
            **{f"hit@{k}": 0.0 for k in KS}, "mrr": 0.0}

def _anchor_metric_values(anchors: list[str], unanchored: list[str], retrieved_ids: list[str],
                          chunk_text: dict[str, str], relation: str) -> dict:
    return {**{f"hit@{k}": _anchor_hit_at_k(anchors, unanchored, retrieved_ids,
                                            chunk_text, relation, k) for k in KS},
            "mrr": _anchor_reciprocal_rank(anchors, unanchored, retrieved_ids,
                                           chunk_text, relation)}

def _add_anchor_metrics(metrics: dict, values: dict) -> None:
    metrics["n_scored"] += 1
    for key in (*(f"hit@{k}" for k in KS), "mrr"):
        metrics[key] += values[key]

def _finalize_anchor_metrics(metrics: dict) -> dict:
    if metrics["n_scored"]:
        for key in (*(f"hit@{k}" for k in KS), "mrr"):
            metrics[key] /= metrics["n_scored"]
    return metrics

def _empty_metrics() -> dict:
    return {
        "n_total": 0,
        "n_evaluated": 0,
        "n_excluded_unanswerable": 0,
        "n_inconsistent": 0,
        **{f"hit@{k}": 0.0 for k in KS},
        **{f"recalled_gold@{k}": 0 for k in RECALL_KS},
        "total_gold": 0,
        **{f"recall@{k}": 0.0 for k in RECALL_KS},
        **{f"macro_recall@{k}": 0.0 for k in RECALL_KS},
        "missing_gold@10": 0,
        "mrr": 0.0,
    }

def _metric_values(gold_ids: list[str], retrieved_ids: list[str], relation: str) -> dict:
    return {
        **{f"hit@{k}": _hit_at_k(gold_ids, retrieved_ids, relation, k) for k in KS},
        **{f"recalled_gold@{k}": _recalled_gold_at_k(gold_ids, retrieved_ids, k)
           for k in RECALL_KS},
        **{f"recall@{k}": _recall_at_k(gold_ids, retrieved_ids, k)
           for k in RECALL_KS},
        # rank cutoff matches RETRIEVAL_DEPTH so MRR stays MRR@10, not MRR@len(retrieved_ids).
        "mrr": _reciprocal_rank(gold_ids, retrieved_ids[:MRR_DEPTH], relation),
    }

# hit 누산은 KS 전체를 돈다. hit@30/hit@50이 빠져 있어 chunk/doc 레벨에서 항상
# 0.0000으로 찍혔고, "top-50에도 없음"으로 오독될 수 있었다(리랭커 헤드룸 산정 시 실제로 걸림).
_HIT_KEYS = tuple(f"hit@{k}" for k in KS) + ("mrr",)

def _add_metrics(metrics: dict, values: dict, gold_ids: list[str]) -> None:
    """문항 하나의 결과를 집계 메트릭에 더한다."""
    metrics["n_evaluated"] += 1
    unique_gold_count = len(set(gold_ids))
    metrics["total_gold"] += unique_gold_count
    for key in _HIT_KEYS:
        metrics[key] += values[key]
    for k in RECALL_KS:
        metrics[f"recalled_gold@{k}"] += values[f"recalled_gold@{k}"]
        metrics[f"macro_recall@{k}"] += values[f"recall@{k}"]

def _finalize_metrics(metrics: dict) -> dict:
    """Hit/MRR/MacroRecall은 문항 기준, (micro)Recall은 gold chunk occurrence 기준으로 정규화한다."""
    if metrics["n_evaluated"]:
        denominator = metrics["n_evaluated"]
        for key in _HIT_KEYS:
            metrics[key] /= denominator
        for k in RECALL_KS:
            metrics[f"macro_recall@{k}"] /= denominator
    if metrics["total_gold"]:
        denominator = metrics["total_gold"]
        for k in RECALL_KS:
            metrics[f"recall@{k}"] = metrics[f"recalled_gold@{k}"] / denominator
    metrics["missing_gold@10"] = metrics["total_gold"] - metrics["recalled_gold@10"]
    return metrics

def _parent_ids(
    chunk_ids: list[str],
    chunk_to_doc: dict[str, str],
    missing_prefix: str = "__missing__",
) -> list[str]:
    """알 수 없는 gold는 절대 검색에 매칭되지 않는 별도 식별자로 보존한다."""
    return list(dict.fromkeys(chunk_to_doc.get(chunk_id, f"{missing_prefix}:{chunk_id}")
                              for chunk_id in chunk_ids))

def evaluate_retrieval(
    gt_data: Iterable[dict],
    retrieved_data: Iterable[dict],
    chunk_metadata: Iterable[dict] | None = None,
    score: str = "both",
    id_fallback: bool = True,
) -> dict:
    """GT와 검색 결과를 결정론적으로 평가한다.

    answerable=false는 모든 Hit@K, Recall@K, MRR의 분모에서 제외된다.
    Recall은 문항 평균이 아니라 전체 gold chunk 기준으로 계산한다.
    ``chunk_metadata``를 주면 기존 방식과 같은 문서 단위 참고 지표도 함께 계산한다.

    ``score``: 적중 판정 기준.
      - ``chunk_id``: gold chunk_id 완전일치(기존 동작).
      - ``anchor``  : top-k 청크 텍스트가 ``gt_anchor_span``을 포함하는지(골드텍스트).
      - ``both``    : 둘 다 산출(기본). 전환 효과를 나란히 보기 위한 모드.
    앵커 판정은 청크 본문이 필요하므로 ``chunk_metadata`` 없이는 건너뛴다.

    ``id_fallback``: 앵커가 덮지 못한 gold 를 ``chunk_id`` 로 요구할지.
      - ``True``  (함수 기본값) 기존 동작. 구 ``eval_anchor_v3.py`` 와 바이트 동등하다 —
        `tests/test_eval_equivalence.py` 가 이 경로를 기준값으로 삼으므로 바꾸지 않는다.
      - ``False`` **앵커텍스트만으로 판정한다.** `gt_chunk_ids` 는 특정 청킹에 대한
        좌표라 재청킹하면 값이 변한다 — 평가 기준으로 쓰면 코퍼스를 바꿀 때마다
        수치가 판정 방식 때문에 움직인다. 앵커가 하나도 없는 문항은 판정 근거가
        없으므로 ``n_missing_span`` 으로 세고 분모에서 뺀다.
    **평가셋 정책은 `id_fallback=False`(앵커텍스트 전용)다.** CLI(`--score` 기본
    ``anchor``)와 `admin/runner.run_eval()` 이 그 경로로 부른다. 함수 기본값이 아직
    ``True`` 인 것은 등가성 회귀 테스트의 기준값을 보존하기 위한 것뿐이다.
    """
    if score not in SCORE_MODES:
        raise ValueError(f"score must be one of {SCORE_MODES}, got {score!r}")
    retrieved_by_id: dict[str, list[str]] = {}
    for item in retrieved_data:
        item_id = item["id"]
        if item_id in retrieved_by_id:
            raise ValueError(f"duplicate retrieved result id: {item_id}")
        retrieved_by_id[item_id] = item.get("retrieved_chunk_ids", [])

    chunk_meta_list = list(chunk_metadata) if chunk_metadata is not None else None
    chunk_to_doc = {item["chunk_id"]: item["parent_doc_id"]
                    for item in (chunk_meta_list or [])}
    chunk_metrics = _empty_metrics()
    doc_metrics = _empty_metrics() if chunk_meta_list is not None else None
    relation_metrics: dict[str, dict] = {}
    domain_metrics: dict[str, dict] = {}
    audit_rows = []

    # 앵커 판정용 정규화 본문 — 청크당 1회만 정규화하고 문항마다 재사용.
    anchor_on = score in ("anchor", "both") and chunk_meta_list is not None
    chunk_text = ({c["chunk_id"]: _norm_text(c.get("text", "")) for c in chunk_meta_list}
                  if anchor_on else {})
    anchor_metrics = _empty_anchor_metrics() if anchor_on else None
    anchor_relation_metrics: dict[str, dict] = {}
    # 앵커 채점 대상(=span 보유) 문항만 모은 chunk_id 기준 수치. 두 판정의 Δ를 같은
    # 모집단 위에서 내기 위한 baseline — 전체 n_evaluated와 비교하면 라벨 결측분이
    # 판정 차이로 섞여 들어간다. hit@k·mrr 키가 같아 앵커 누산기를 그대로 재사용한다.
    chunk_on_anchor = _empty_anchor_metrics() if anchor_on else None
    chunk_on_anchor_relation: dict[str, dict] = {}

    for gt_item in gt_data:
        item_id = gt_item["id"]
        gold_ids = _get_gt_chunk_ids(gt_item)
        relation = _get_relation(gt_item)          # 채점용(ANY/ALL로 정규화)
        rel_label = _get_relation_label(gt_item)   # 리포트 분해용(원본 표기 보존)
        retrieved_ids = retrieved_by_id.get(item_id, [])
        answerable = gt_item.get("answerable") is True
        chunk_metrics["n_total"] += 1
        if doc_metrics is not None:
            doc_metrics["n_total"] += 1

        if not answerable:
            chunk_metrics["n_excluded_unanswerable"] += 1
            if doc_metrics is not None:
                doc_metrics["n_excluded_unanswerable"] += 1
            if gold_ids:
                chunk_metrics["n_inconsistent"] += 1
                if doc_metrics is not None:
                    doc_metrics["n_inconsistent"] += 1
            audit_rows.append({"id": item_id, "answerable": False, "chunk_relation": rel_label,
                               "gold_chunk_ids": gold_ids, "retrieved_chunk_ids": retrieved_ids,
                               "excluded": True})
            continue

        chunk_metrics["n_evaluated"] += 1
        if not gold_ids:
            chunk_metrics["n_inconsistent"] += 1
            if doc_metrics is not None:
                doc_metrics["n_inconsistent"] += 1
        values = _metric_values(gold_ids, retrieved_ids, relation)
        # n_evaluated is incremented above to preserve the explicit
        # answerable=true denominator, including an invalid no-gold label.
        chunk_metrics["total_gold"] += len(set(gold_ids))
        for key in _HIT_KEYS:
            chunk_metrics[key] += values[key]
        for k in RECALL_KS:
            chunk_metrics[f"recalled_gold@{k}"] += values[f"recalled_gold@{k}"]
            chunk_metrics[f"macro_recall@{k}"] += values[f"recall@{k}"]

        relation_metrics.setdefault(rel_label, _empty_metrics())
        relation_metrics[rel_label]["n_total"] += 1
        _add_metrics(relation_metrics[rel_label], values, gold_ids)

        domain = gt_item.get("business_function") or "(unknown)"
        domain_metrics.setdefault(domain, _empty_metrics())
        domain_metrics[domain]["n_total"] += 1
        _add_metrics(domain_metrics[domain], values, gold_ids)

        row = {"id": item_id, "answerable": True, "chunk_relation": rel_label,
               "business_function": domain, "question": gt_item.get("question", ""),
               "gold_chunk_ids": gold_ids, "retrieved_chunk_ids": retrieved_ids,
               "excluded": False, "chunk": values}

        if anchor_on:
            anchors = _get_gt_anchors(gt_item)
            unanchored, stale = _split_gold_by_anchor(gold_ids, anchors, chunk_text)
            if not id_fallback:
                # 앵커텍스트 전용 판정 — chunk_id 는 조건에서 완전히 뺀다.
                # 앵커가 없는 문항은 아래 `not anchors and not unanchored` 에 걸려
                # n_missing_span 으로 빠진다(미적중이 아니라 판정 불가).
                unanchored = []
            anchor_metrics["n_stale_gold"] += len(stale)
            if stale and not anchors:
                anchor_metrics["n_stale_only"] += 1
            if not anchors and not unanchored:
                # 앵커도 gold도 없으면 판정 근거가 없다 — 미적중으로 세면 라벨 결측이
                # 검색 실패로 둔갑하므로 분모에서 빼고 건수로만 드러낸다.
                anchor_metrics["n_missing_span"] += 1
                row["anchor"] = None
            else:
                anchor_values = _anchor_metric_values(anchors, unanchored, retrieved_ids,
                                                      chunk_text, relation)
                _add_anchor_metrics(anchor_metrics, anchor_values)
                # 순수 앵커 판정분과 chunk_id 폴백이 섞인 분량을 나눠 센다 —
                # 이 비율이 라벨 작업 잔량이자 수치의 id 의존도다.
                if unanchored:
                    anchor_metrics["n_id_fallback"] += 1
                else:
                    anchor_metrics["n_full_anchor"] += 1
                anchor_relation_metrics.setdefault(rel_label, _empty_anchor_metrics())
                _add_anchor_metrics(anchor_relation_metrics[rel_label], anchor_values)
                # 같은 문항의 chunk_id 판정도 별도 누산 → Δ가 동일 모집단 기준이 된다.
                _add_anchor_metrics(chunk_on_anchor, values)
                chunk_on_anchor_relation.setdefault(rel_label, _empty_anchor_metrics())
                _add_anchor_metrics(chunk_on_anchor_relation[rel_label], values)
                row["anchor"] = anchor_values
        if doc_metrics is not None:
            gold_doc_ids = _parent_ids(gold_ids, chunk_to_doc, "__missing_gold__")
            retrieved_doc_ids = _parent_ids(retrieved_ids, chunk_to_doc, "__missing_retrieved__")
            doc_values = _metric_values(gold_doc_ids, retrieved_doc_ids, relation)
            _add_metrics(doc_metrics, doc_values, gold_doc_ids)
            row["gold_parent_doc_ids"] = gold_doc_ids
            row["doc"] = doc_values
        audit_rows.append(row)

    _finalize_metrics(chunk_metrics)
    if doc_metrics is not None:
        _finalize_metrics(doc_metrics)
    for metrics in relation_metrics.values():
        _finalize_metrics(metrics)
    for metrics in domain_metrics.values():
        _finalize_metrics(metrics)
    if anchor_metrics is not None:
        _finalize_anchor_metrics(anchor_metrics)
        _finalize_anchor_metrics(chunk_on_anchor)
        for metrics in anchor_relation_metrics.values():
            _finalize_anchor_metrics(metrics)
        for metrics in chunk_on_anchor_relation.values():
            _finalize_anchor_metrics(metrics)

    gold_coverage = {
        "gold_chunk_total": chunk_metrics["total_gold"],
        "recalled_gold@3": chunk_metrics["recalled_gold@3"],
        "recalled_gold@5": chunk_metrics["recalled_gold@5"],
        "recalled_gold@10": chunk_metrics["recalled_gold@10"],
        "missing_gold@10": chunk_metrics["missing_gold@10"],
        "gold_coverage@10": chunk_metrics["recall@10"],
    }

    return {
        "chunk_level": chunk_metrics,
        "document_level": doc_metrics,
        "anchor_level": anchor_metrics,
        "anchor_relation_metrics": anchor_relation_metrics,
        "chunk_on_anchor_subset": chunk_on_anchor,
        "chunk_on_anchor_subset_relation": chunk_on_anchor_relation,
        "relation_metrics": relation_metrics,
        "domain_metrics": domain_metrics,
        "gold_coverage": gold_coverage,
        "audit_rows": audit_rows,
        "score_mode": score,
        # 레거시 경로(id_fallback=True)에는 이 키를 넣지 않는다 — 등가성 회귀 테스트가
        # 구 평가기의 반환 dict 와 키 집합까지 대조하기 때문이다(tests/ §1).
        **({} if id_fallback else {"id_fallback": False}),
    }

def _error_analysis(rows: list[dict], chunk_to_bf: dict[str, str] | None) -> dict:
    """미적중(top-3 밖) 문항의 원인·혼입 패턴을 집계한다.

    chunk_to_bf가 없으면(청크 메타 미제공) 목록만 반환하고 도메인 분류는 생략한다.
    """
    misses = [row for row in rows if not row["excluded"] and not row["chunk"]["hit@3"]]
    by_domain: dict[str, int] = {}
    for row in misses:
        by_domain[row["business_function"]] = by_domain.get(row["business_function"], 0) + 1

    if chunk_to_bf is None:
        return {"misses": misses, "by_domain": by_domain, "cause": {}, "intruders": {},
                "cross_flow": {}, "worst": [row for row in misses if not row["chunk"]["hit@10"]][:8]}

    cause: dict[str, int] = {}
    intruders: dict[str, int] = {}
    cross_flow: dict[tuple[str, str], int] = {}
    for row in misses:
        top3 = row["retrieved_chunk_ids"][:3]
        top3_bf = [chunk_to_bf.get(cid, "(unknown)") for cid in top3]
        gt_bf = row["business_function"]
        reason = "정분류(업무 내 랭킹·청킹)" if gt_bf in top3_bf else "오분류(다른 업무로 혼입)"
        cause[reason] = cause.get(reason, 0) + 1
        for cid, bf in zip(top3, top3_bf):
            if bf != gt_bf:
                intruders[cid] = intruders.get(cid, 0) + 1
        if top3_bf and top3_bf[0] != gt_bf:
            key = (gt_bf, top3_bf[0])
            cross_flow[key] = cross_flow.get(key, 0) + 1

    worst = [row for row in misses if not row["chunk"]["hit@10"]][:8]
    return {"misses": misses, "by_domain": by_domain, "cause": cause,
            "intruders": intruders, "cross_flow": cross_flow, "worst": worst}

def write_report(result: dict, output_path: Path, gt_path: Path, retrieval_source: str,
                  chunk_metadata: list[dict] | None = None) -> None:
    """새 v3 결과 전용 Markdown 보고서를 저장한다."""
    chunk = result["chunk_level"]
    doc = result["document_level"]
    relation_metrics = result["relation_metrics"]
    domain_metrics = result["domain_metrics"]
    gold_coverage = result["gold_coverage"]
    rows = result["audit_rows"]
    chunk_to_bf = ({c["chunk_id"]: c.get("business_function", "(unknown)") for c in chunk_metadata}
                   if chunk_metadata else None)

    try:
        import rag
        retriever_desc = (f"RRF(k={rag.RRF_K}, alpha={rag.RRF_ALPHA}) + "
                          f"BF_MODE={rag.BF_MODE}(cap={rag.BF_DOC_CAP})")
        embedding_desc = rag.MODEL_NAME
    except Exception:
        retriever_desc = "정보 없음(외부 검색 결과 사용)"
        embedding_desc = "정보 없음(외부 검색 결과 사용)"

    lines = ["# KDIC 검색 평가 리포트 v3", "",
              "## 1. 개요", "",
              "청크 단위 검색 평가 — gold `chunk_id`를 직접 비교해 기존 `parent_doc_id` 기준 평가가",
              "안고 있던 '같은 문서면 적중' 거품을 배제하고 실제 청크 적중률을 측정한다.", "",
              "## 2. 평가 대상 / 데이터 구성", "",
              f"- GT 라벨: `{gt_path}`",
              f"- 전체 {chunk['n_total']}건 · 평가 대상(answerable=true) {chunk['n_evaluated']}건 · "
              f"제외(answerable=false) {chunk['n_excluded_unanswerable']}건 · 라벨 불일치 {chunk['n_inconsistent']}건",
              ""]
    lines += _pct_table({rel: m["n_total"] for rel, m in relation_metrics.items()},
                        chunk["n_evaluated"], ("relation", "문항수"))
    lines += ["",
              "## 3. 실험 파라미터", "",
              f"- Corpus: {len(chunk_metadata)}개 청크 (`chunks.jsonl`)" if chunk_metadata is not None
              else "- Corpus: 정보 없음(청크 메타 미제공)",
              f"- Retriever: {retriever_desc}",
              f"- Embedding: {embedding_desc}",
              f"- 검색 단위: chunk (기존 parent_doc_id 평가와 별도)",
              f"- 검색 소스: {retrieval_source}",
              f"- Top-K: {RETRIEVAL_DEPTH}", "",
              "## 4. 평가 지표 및 판정 기준", "",
              "- Hit@1/3/5/10: Top-K 안에 gold가 relation 조건을 만족하며 존재하는지 (분모: 평가 대상 문항수).",
              "- Macro Recall@3/5/10: 문항별 recall(Top-K에서 회수한 gold 비율)의 문항 평균. 주지표.",
              "- (참고) Micro Recall@3/5/10: 전체 gold occurrence 기준 합산 recall. 문항당 gold 개수가 많을수록 가중치가 커짐 — 보조지표로만 사용.",
              "- Gold Coverage: 전체 gold chunk occurrence 중 Top-10에서 회수되지 못한 비율(`missing_gold@10`).",
              "- MRR: relation 조건을 만족하는 gold가 처음 나온 순위의 역수, Top-10까지만 본다(MRR@10).",
              "- relation 판정: `single`/`or`는 ANY(하나만 맞아도 적중), `and`는 ALL(전부 맞아야 적중); null/누락은 single.",
              "- answerable=false 문항은 Hit@K·Recall@K·MRR 분모에서 제외.", "",
              "## 5. 전체 평가 결과", "",
              "| Hit@1 | Hit@3 | Hit@5 | Hit@10 | Hit@30 | Hit@50 | MRR@10 |",
              "|---:|---:|---:|---:|---:|---:|---:|",
              f"| {chunk['hit@1']:.3f} | {chunk['hit@3']:.3f} | {chunk['hit@5']:.3f} | "
              f"{chunk['hit@10']:.3f} | {chunk['hit@30']:.3f} | {chunk['hit@50']:.3f} | {chunk['mrr']:.3f} |",
              "",
              "| MacroRecall@3 | MacroRecall@5 | MacroRecall@10 | MacroRecall@30 | MacroRecall@50 |",
              "|---:|---:|---:|---:|---:|",
              f"| {chunk['macro_recall@3']:.3f} | {chunk['macro_recall@5']:.3f} | "
              f"{chunk['macro_recall@10']:.3f} | {chunk['macro_recall@30']:.3f} | {chunk['macro_recall@50']:.3f} |",
              "",
              "> recall@50 = 리랭커 천장. @10→@30→@50 증가폭이 크면 top-k 확대(리랭커 후보) 이득.",
              "",
              f"- (참고) Micro Recall@10: {chunk['recall@10']:.3f} · gold 총계(occurrence): "
              f"{gold_coverage['gold_chunk_total']} · 미회수(@10): {gold_coverage['missing_gold@10']}", "",
              "## 6. Relation별 결과", "",
              "| relation | 문항수 | Hit@5 | Hit@10 | MacroRecall@10 | MacroRecall@30 | MacroRecall@50 | MRR@10 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for rel in ("single", "or", "and"):
        m = relation_metrics.get(rel)
        if m:
            lines.append(f"| {rel} | {m['n_total']} | {m['hit@5']:.3f} | {m['hit@10']:.3f} | "
                        f"{m['macro_recall@10']:.3f} | {m['macro_recall@30']:.3f} | "
                        f"{m['macro_recall@50']:.3f} | {m['mrr']:.3f} |")

    lines += ["", "## 7. 도메인별 결과", "",
              "| 업무 | 문항수 | Hit@5 | Hit@10 | MacroRecall@10 | MacroRecall@30 | MacroRecall@50 | MRR@10 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for domain, m in sorted(domain_metrics.items(), key=lambda kv: -kv[1]["n_total"]):
        lines.append(f"| {domain} | {m['n_total']} | {m['hit@5']:.3f} | {m['hit@10']:.3f} | "
                    f"{m['macro_recall@10']:.3f} | {m['macro_recall@30']:.3f} | "
                    f"{m['macro_recall@50']:.3f} | {m['mrr']:.3f} |")

    err = _error_analysis(rows, chunk_to_bf)
    n_miss = len(err["misses"])
    lines += ["", "## 8. 오류 분석", "",
              f"- 미적중(top-3 밖) {n_miss}건 / 평가 대상 {chunk['n_evaluated']}건 "
              f"({n_miss / chunk['n_evaluated'] * 100 if chunk['n_evaluated'] else 0:.1f}%)", ""]
    if err["cause"]:
        lines += ["### 8-1. 미적중 원인 분포", "",
                  "정분류: gt 업무 청크가 top-3 안에 있으나 순위/청킹 문제로 놓침. "
                  "오분류: top-3 전부 다른 업무 청크로 채워짐. "
                  "(업무 분류기가 적용됐는지까지는 이 표만으로 알 수 없음 — 세부 조사는 수작업 검토 필요.)", ""]
        lines += _pct_table(err["cause"], n_miss, ("원인", "건수"))
    else:
        lines += ["_청크 메타(`--chunks`)가 없어 원인 분류를 생략함._"]

    lines += ["", "### 8-2. 업무별 미적중", "",
              "| 업무 | 문항수 | 미적중 | 미적중률 |", "|---|---:|---:|---:|"]
    for domain, count in sorted(err["by_domain"].items(), key=lambda kv: -kv[1]):
        total = domain_metrics[domain]["n_total"]
        lines.append(f"| {domain} | {total} | {count} | {count / total * 100 if total else 0:.1f}% |")

    if err["intruders"]:
        lines += ["", "### 8-3. 혼입 문서 랭킹 (미적중 top-3를 잠식한 다른 업무 청크)", "",
                  "| 청크 ID | 출현 | 업무 |", "|---|---:|---|"]
        for cid, count in sorted(err["intruders"].items(), key=lambda kv: -kv[1])[:15]:
            lines.append(f"| `{cid}` | {count} | {chunk_to_bf.get(cid, '(unknown)')} |")

    if err["cross_flow"]:
        lines += ["", "### 8-4. 업무 간 혼입 흐름 (정답 업무 → top-1 업무)", "",
                  "| 정답 업무 | → top-1 업무 | 건수 |", "|---|---|---:|"]
        for (gt_bf, top1_bf), count in sorted(err["cross_flow"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {gt_bf} | {top1_bf} | {count} |")

    if err["worst"]:
        lines += ["", "### 8-5. 대표 실패 사례 (gold가 top-10에도 없음)", ""]
        for row in err["worst"]:
            lines += [f"- **[{row['business_function']}] {row['id']}** — {row['question']}",
                     f"  - gold: {_format_ids(row['gold_chunk_ids'])}",
                     f"  - top-3: {_format_ids(row['retrieved_chunk_ids'][:3])}"]

    lines += ["", "## 9. 개선 우선순위", ""]
    priorities = []
    for domain, count in sorted(err["by_domain"].items(), key=lambda kv: -kv[1])[:3]:
        total = domain_metrics[domain]["n_total"]
        priorities.append(f"'{domain}' 업무 — 미적중 {count}/{total}건"
                          f"({count / total * 100 if total else 0:.1f}%)로 가장 취약함")
    and_m = relation_metrics.get("and")
    if and_m and and_m["hit@3"] < chunk["hit@3"]:
        priorities.append(f"`and` relation(다중 근거 필요) Hit@3={and_m['hit@3']:.3f}로 "
                          f"전체 평균({chunk['hit@3']:.3f})보다 낮음 — 다중 청크 회수 전략 점검 필요")
    if err["intruders"]:
        top_intruder = max(err["intruders"].items(), key=lambda kv: kv[1])
        priorities.append(f"`{top_intruder[0]}` 청크가 미적중 {top_intruder[1]}건에서 top-3를 잠식 "
                          f"— 업무 분류/부스트 파라미터 재검토 대상 1순위")
    lines += [f"{i}. {p}" for i, p in enumerate(priorities, 1)] or ["_미적중 사례 없음._"]

    if doc is not None:
        lines += ["", "## 10. 참고", "",
                  "기존 document-level(같은 `parent_doc_id`면 적중) 판정과 비교한 거품(percentage points):", "",
                  "| 지표 | chunk-level | document-level | 문서 단위 거품 |",
                  "|---|---:|---:|---:|"]
        for key in ("hit@1", "hit@3", "hit@5", "recall@10", "mrr"):
            bubble = (doc[key] - chunk[key]) * 100
            lines.append(f"| {key} | {chunk[key]:.3f} | {doc[key]:.3f} | {bubble:+.1f}pp |")

    lines += _anchor_report_lines(result)

    lines += ["", "## 부록. 문항별 라벨과 검색 청크", "",
              "| id | answerable | relation | gold chunk IDs | Top-10 retrieved chunk IDs | chunk Hit@1/3/5/10 | doc Hit@1/3/5/10 |",
              "|---|---|---|---|---|---|---|"]
    for row in rows:
        if row["excluded"]:
            chunk_hits = doc_hits = "excluded"
        else:
            chunk_hits = "/".join(str(int(row["chunk"][f"hit@{k}"])) for k in KS)
            doc_hits = ("/".join(str(int(row["doc"][f"hit@{k}"])) for k in KS)
                        if "doc" in row else "-")
        lines.append("| {id} | {answerable} | {relation} | {gold} | {retrieved} | {chunk_hits} | {doc_hits} |".format(
            id=row["id"], answerable=str(row["answerable"]).lower(), relation=row["chunk_relation"],
            gold=_format_ids(row["gold_chunk_ids"]),
            retrieved=_format_ids(row["retrieved_chunk_ids"][:RETRIEVAL_DEPTH]),
            chunk_hits=chunk_hits, doc_hits=doc_hits))

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def _anchor_report_lines(result: dict) -> list[str]:
    """앵커텍스트 판정 결과 — chunk_id 판정과 나란히 놓아 전환 효과를 드러낸다."""
    anchor = result.get("anchor_level")
    if not anchor:
        return []
    # Δ는 '앵커 채점 대상 문항'이라는 동일 모집단 위에서 낸다. 전체 n_evaluated 기준
    # chunk_id 수치와 비교하면 라벨 결측분이 판정 차이로 섞인다.
    base_all = result["chunk_on_anchor_subset"]
    chunk = result["chunk_level"]
    n_scored = anchor["n_scored"] or 1
    lines = ["", "## 앵커텍스트(골드텍스트) 판정", "",
             "적중 = top-k 청크가 `gt_anchors`를 포함하는지로 판정(공백 정규화 후 부분문자열).",
             "정답 내용이 여러 청크에 정당히 존재해도 적중으로 잡히며, 재청킹으로 `chunk_id`가",
             "밀려도 판정이 유지된다. 출처: `docs/records/앵커텍스트_정답라벨링_파이프라인.md` ⑤.", "",
             "- `single`/`or`: 앵커 하나라도 발견되면 적중",
             "- `and`: 앵커 **전부** 발견 + 앵커 없는 gold 청크 **전부** top-k에 존재"]
    if result.get("id_fallback") is False:
        lines += [
            "- **판정은 앵커텍스트만 본다 (`--id-fallback` 꺼짐).** `gt_chunk_ids` 는 특정 청킹에",
            "  대한 좌표라 재청킹하면 값이 변한다 — 평가 기준으로 쓰면 수치가 검색 성능이 아니라",
            "  판정 방식 때문에 움직인다. 그래서 `and` 조건에서도 앵커 없는 gold 는 요구하지 않는다.",
            "- 앵커가 하나도 없는 문항은 판정 근거가 없어 **분모에서 뺀다**(미적중이 아니다).", "",
            f"- 채점 {anchor['n_scored']}문항 (전부 순수 앵커 판정) "
            f"· 앵커 미보유 {anchor['n_missing_span']}문항(분모 제외)",
            f"- **앵커 커버율: {anchor['n_scored'] / (anchor['n_scored'] + anchor['n_missing_span'] or 1):.1%}** "
            f"— 이 비율이 낮으면 수치의 모집단이 작다는 뜻이다. 잔여 라벨 작업량의 지표.",
            f"- 아래 표의 두 열과 Δ는 모두 **앵커 채점 대상 {anchor['n_scored']}문항** 기준이다."
            f" chunk_id 열은 **참고용**이며 판정에 쓰이지 않는다"
            f" (전체 {chunk['n_evaluated']}문항 기준 chunk_id hit@5 = {chunk['hit@5']:.3f}).", ""]
    else:
        lines += [
            "- 앵커가 덮지 않는 gold 청크는 `chunk_id`로 판정한다(하이브리드). 앵커를 지어내지",
            "  않으면서 relation 의미를 지키는 방식이며, 라벨이 채워질수록 id 의존분이 줄어든다.", "",
            f"- 채점 {anchor['n_scored']}문항 "
            f"(앵커만으로 판정 {anchor['n_full_anchor']} · chunk_id 폴백 섞임 {anchor['n_id_fallback']}) "
            f"· 근거 없음 {anchor['n_missing_span']}문항(분모 제외)",
            f"- **id 의존도: {anchor['n_id_fallback'] / n_scored:.1%}** — 이 비율이 0에 가까울수록 "
            f"수치가 순수 앵커 판정이다. 잔여 라벨 작업량의 지표이기도 하다.",
            f"- 아래 표의 두 열과 Δ는 모두 **앵커 채점 대상 {anchor['n_scored']}문항** 기준이다"
            f" (참고: 전체 {chunk['n_evaluated']}문항 기준 chunk_id hit@5 = {chunk['hit@5']:.3f}).", ""]
    lines += ["| 지표 | chunk_id 기준 | 앵커텍스트 기준 | Δ |", "|---|---:|---:|---:|"]
    for key in ("hit@1", "hit@3", "hit@5", "hit@10", "mrr"):
        lines.append(f"| {key} | {base_all[key]:.3f} | {anchor[key]:.3f} | "
                     f"{anchor[key] - base_all[key]:+.3f} |")
    rel = result.get("anchor_relation_metrics") or {}
    base_rel = result.get("chunk_on_anchor_subset_relation") or {}
    if rel:
        lines += ["", "### relation별 hit@5", "",
                  "| relation | 문항 | chunk_id | 앵커텍스트 | Δ |", "|---|---:|---:|---:|---:|"]
        for name, m in sorted(rel.items()):
            base = base_rel.get(name, {}).get("hit@5", 0.0)
            lines.append(f"| {name} | {m['n_scored']} | {base:.3f} | {m['hit@5']:.3f} | "
                         f"{m['hit@5'] - base:+.3f} |")
        lines += ["",
                  "`and`는 ALL 조건(앵커 전부 + 앵커 없는 gold 전부)으로 판정한다. 앵커 라벨이",
                  "부족한 만큼 chunk_id 판정에 수렴하므로, 위 'id 의존도'와 함께 읽을 것 —",
                  "라벨을 채우면 이 수치가 재청킹에도 견디는 값으로 바뀐다.",
                  "잔여 라벨 작업량은 `promote_gt_anchors.py`가 gold 청크 단위로 보고한다."]
    return lines

def _print_summary(result: dict, report_path: Path) -> None:
    """콘솔 요약을 항목마다 줄을 나누고, 그룹 사이는 빈 줄로 구분해 가독성 있게 출력한다."""
    m = result["chunk_level"]
    anchor = result.get("anchor_level")
    print("=== KDIC v3 평가 결과 ===")
    print()
    _print_group("데이터", [
        ("n_total", str(m["n_total"])),
        ("n_evaluated", str(m["n_evaluated"])),
        ("n_excluded", str(m["n_excluded_unanswerable"])),
        ("n_inconsistent", str(m["n_inconsistent"])),
        ("score_mode", result.get("score_mode", "chunk_id")),
        ("판정", "앵커텍스트 전용 (chunk_id 미사용)" if result.get("id_fallback") is False
                else "앵커 + chunk_id 폴백 (하이브리드)"),
    ])
    if anchor:
        base = result["chunk_on_anchor_subset"]   # 동일 모집단(앵커 채점 대상) baseline
        _print_group(f"Hit@K — chunk_id vs 앵커텍스트 (앵커 채점 {anchor['n_scored']}문항 기준)", [
            (f"Hit@{k}", f"{base[f'hit@{k}']:.3f}  ->  {anchor[f'hit@{k}']:.3f}"
                         f"  ({anchor[f'hit@{k}'] - base[f'hit@{k}']:+.3f})")
            for k in (1, 3, 5, 10)
        ] + [("MRR@10", f"{base['mrr']:.3f}  ->  {anchor['mrr']:.3f}"
                        f"  ({anchor['mrr'] - base['mrr']:+.3f})"),
             ("앵커 채점/결측", f"{anchor['n_scored']} / {anchor['n_missing_span']}")]
            + ([("앵커 커버율",
                 f"{anchor['n_scored'] / ((anchor['n_scored'] + anchor['n_missing_span']) or 1):.1%}"
                 f"  (앵커 미보유 {anchor['n_missing_span']}문항은 분모 제외)")]
               if result.get("id_fallback") is False else
               [("순수앵커/id폴백", f"{anchor['n_full_anchor']} / {anchor['n_id_fallback']}"
                 f"  (id 의존도 {anchor['n_id_fallback'] / (anchor['n_scored'] or 1):.1%})")]))
    if result.get("score_mode") != "anchor":
        # anchor 모드에서는 위 비교 그룹이 이미 chunk_id 열을 담고 있어 중복이다.
        _print_group("Hit@K (chunk_id 기준)", [
            ("Hit@1", f"{m['hit@1']:.3f}"),
            ("Hit@3", f"{m['hit@3']:.3f}"),
            ("Hit@5", f"{m['hit@5']:.3f}"),
            ("Hit@10", f"{m['hit@10']:.3f}"),
        ])
    _print_group("MacroRecall", [
        ("@3", f"{m['macro_recall@3']:.3f}"),
        ("@5", f"{m['macro_recall@5']:.3f}"),
        ("@10", f"{m['macro_recall@10']:.3f}  (micro@10={m['recall@10']:.3f})"),
        ("@30", f"{m['macro_recall@30']:.3f}"),
        ("@50", f"{m['macro_recall@50']:.3f}  <- 리랭커 천장"),
    ])
    _print_group("MRR", [("MRR@10", f"{m['mrr']:.3f}")])
    print(f"report -> {report_path}")


# ══════════════════════════════════════════════════════════════════════════
# §5. 다중 span 판정 — 구 eval_anchor_span_multi.py.
#     `gt_anchor_spans`(청크별 정렬 리스트) 를 소비한다. and 는 모든 span 이
#     top-k 안에서 발견돼야 hit. §4 와 집계 키가 달라(id_hit@k · total_spans ·
#     n_no_span) 누산기를 공유하지 못한다 → _span_* 접두어로 분리했다.
#     KS_SPAN=(1,3,5,10) · DEPTH_SPAN=10 — 원본 값 유지(리포트 비교 연속성).
# ══════════════════════════════════════════════════════════════════════════

def _get_gt_spans(item: dict) -> list[str]:
    """gt_anchor_spans(리스트/문자열) 우선, 없으면 구형 gt_anchor_span으로 폴백한다."""
    spans = item.get("gt_anchor_spans")
    if spans is None:
        spans = item.get("gt_anchor_span")
    if spans is None:
        return []
    if isinstance(spans, str):
        return [spans] if spans else []
    return [s for s in spans if s]

def _relation_mode(item: dict) -> str:
    """'and'만 다중 근거 결합(ALL)으로, 나머지는 전부 ANY로 취급한다."""
    return "and" if item.get("chunk_relation") == "and" else "any"

def _rank_of_span_hit(span_norm: str, retrieved_ids: list[str],
                       chunk_text: dict[str, str], depth: int) -> int:
    """span이 처음 발견된 순위(1-base)를 반환한다. 못 찾으면 0."""
    if not span_norm:
        return 0
    for rank, chunk_id in enumerate(retrieved_ids[:depth], 1):
        text = chunk_text.get(chunk_id)
        if text and span_norm in text:
            return rank
    return 0

def _id_hit_at_k(gold_ids: list[str], retrieved_ids: list[str], mode: str, k: int) -> bool:
    """비교용 참고 지표: chunk_id 직접비교(기존 eval_anchor_v3.py) 방식."""
    if not gold_ids:
        return False
    top_k = set(retrieved_ids[:k])
    if mode == "and":
        return set(gold_ids).issubset(top_k)
    return bool(set(gold_ids) & top_k)

def _rank_of_id_hit(chunk_id: str, retrieved_ids: list[str], depth: int) -> int:
    """chunk_id가 처음 나온 순위(1-base). 못 찾으면 0."""
    for rank, cid in enumerate(retrieved_ids[:depth], 1):
        if cid == chunk_id:
            return rank
    return 0

def _item_metrics(item: dict, retrieved_ids: list[str], chunk_text: dict[str, str],
                  id_fallback: bool = False) -> dict:
    spans_norm = [norm_ws(s) for s in _get_gt_spans(item)]
    spans_norm = [s for s in spans_norm if s]
    gold_ids = _get_gt_chunk_ids(item)
    mode = _relation_mode(item)

    ranks = [_rank_of_span_hit(s, retrieved_ids, chunk_text, DEPTH_SPAN) for s in spans_norm]

    if id_fallback and not spans_norm and gold_ids:
        # evidence_type=inferable(계산·추론형)은 정답 문장이 원문에 없어 스팬이 구조적으로
        # 비어 있다. 스팬 0개를 그대로 두면 무조건 미적중이 되는데 이는 검색 실패가 아니라
        # 측정 결함이므로, 이때만 gold chunk_id 등장 여부로 대체 판정한다(팀 하이브리드 규약).
        ranks = [_rank_of_id_hit(cid, retrieved_ids, DEPTH_SPAN) for cid in gold_ids]

    found_ranks = [r for r in ranks if r > 0]

    hits = {}
    for k in KS_SPAN:
        found_at_k = [r for r in ranks if 0 < r <= k]
        if mode == "and":
            hits[f"hit@{k}"] = bool(ranks) and len(found_at_k) == len(ranks)
        else:
            hits[f"hit@{k}"] = bool(found_at_k)

    if mode == "and":
        # 모든 span이 등장해야 만족되므로, 그 시점은 "가장 늦게 처음 나온 span의 순위"다.
        mrr = 1.0 / max(ranks) if ranks and all(r > 0 for r in ranks) else 0.0
    else:
        mrr = 1.0 / min(found_ranks) if found_ranks else 0.0

    recall = {f"recall@{k}": (len([r for r in ranks if 0 < r <= k]) / len(ranks) if ranks else 0.0)
              for k in RECALL_KS_SPAN}

    id_hits = {f"id_hit@{k}": _id_hit_at_k(gold_ids, retrieved_ids, mode, k) for k in KS_SPAN}

    return {**hits, "mrr": mrr, **recall, "ranks": ranks, **id_hits,
            "gold_ids": gold_ids, "relation_mode": mode,
            "n_spans": len(spans_norm), "n_spans_found": len(found_ranks)}

def _span_empty_metrics() -> dict:
    return {
        "n_total": 0, "n_evaluated": 0, "n_excluded_unanswerable": 0,
        "n_inconsistent": 0, "n_no_span": 0, "n_missing_chunk_text": 0,
        **{f"hit@{k}": 0.0 for k in KS_SPAN},
        **{f"id_hit@{k}": 0.0 for k in KS_SPAN},
        **{f"recalled@{k}": 0 for k in RECALL_KS_SPAN},
        "total_spans": 0,
        **{f"recall@{k}": 0.0 for k in RECALL_KS_SPAN},
        **{f"macro_recall@{k}": 0.0 for k in RECALL_KS_SPAN},
        "mrr": 0.0,
    }

def _span_add_metrics(metrics: dict, values: dict) -> None:
    metrics["n_evaluated"] += 1
    metrics["total_spans"] += values["n_spans"]
    for k in KS_SPAN:
        metrics[f"hit@{k}"] += values[f"hit@{k}"]
        metrics[f"id_hit@{k}"] += values[f"id_hit@{k}"]
    metrics["mrr"] += values["mrr"]
    for k in RECALL_KS_SPAN:
        recovered = round(values[f"recall@{k}"] * values["n_spans"])
        metrics[f"recalled@{k}"] += recovered
        metrics[f"macro_recall@{k}"] += values[f"recall@{k}"]
    if values["n_spans"] == 0:
        metrics["n_no_span"] += 1

def _span_finalize_metrics(metrics: dict) -> dict:
    if metrics["n_evaluated"]:
        denom = metrics["n_evaluated"]
        for k in KS_SPAN:
            metrics[f"hit@{k}"] /= denom
            metrics[f"id_hit@{k}"] /= denom
        metrics["mrr"] /= denom
        for k in RECALL_KS_SPAN:
            metrics[f"macro_recall@{k}"] /= denom
    if metrics["total_spans"]:
        for k in RECALL_KS_SPAN:
            metrics[f"recall@{k}"] = metrics[f"recalled@{k}"] / metrics["total_spans"]
    return metrics

def evaluate_span_retrieval(gt_data: Iterable[dict], retrieved_data: Iterable[dict],
                             chunk_metadata: Iterable[dict], id_fallback: bool = False) -> dict:
    """GT의 gt_anchor_spans(청크별 span 리스트)와 검색된 청크 본문을 비교해 채점한다.

    answerable=false는 분모에서 제외한다. chunk_metadata는 chunk 본문 조회(채점용)와
    business_function 조회(오류 분석용)에 함께 쓴다.
    """
    retrieved_by_id: dict[str, list[str]] = {}
    for item in retrieved_data:
        item_id = item["id"]
        if item_id in retrieved_by_id:
            raise ValueError(f"duplicate retrieved result id: {item_id}")
        retrieved_by_id[item_id] = item.get("retrieved_chunk_ids", [])

    chunk_metadata = list(chunk_metadata)
    chunk_text: dict[str, str] = {c["chunk_id"]: norm_ws(c.get("text", "")) for c in chunk_metadata}

    metrics = _span_empty_metrics()
    relation_metrics: dict[str, dict] = {}
    domain_metrics: dict[str, dict] = {}
    audit_rows = []

    for gt_item in gt_data:
        item_id = gt_item["id"]
        retrieved_ids = retrieved_by_id.get(item_id, [])
        answerable = gt_item.get("answerable") is True
        metrics["n_total"] += 1

        if not answerable:
            metrics["n_excluded_unanswerable"] += 1
            if _get_gt_spans(gt_item):
                metrics["n_inconsistent"] += 1
            audit_rows.append({"id": item_id, "answerable": False, "excluded": True})
            continue

        missing_text_ids = [cid for cid in retrieved_ids[:DEPTH_SPAN] if cid not in chunk_text]
        metrics["n_missing_chunk_text"] += len(missing_text_ids)

        values = _item_metrics(gt_item, retrieved_ids, chunk_text, id_fallback)
        if not values["gold_ids"]:
            metrics["n_inconsistent"] += 1
        _span_add_metrics(metrics, values)

        relation = gt_item.get("chunk_relation") or "single"
        relation_metrics.setdefault(relation, _span_empty_metrics())
        relation_metrics[relation]["n_total"] += 1
        _span_add_metrics(relation_metrics[relation], values)

        domain = gt_item.get("business_function") or "(unknown)"
        domain_metrics.setdefault(domain, _span_empty_metrics())
        domain_metrics[domain]["n_total"] += 1
        _span_add_metrics(domain_metrics[domain], values)

        audit_rows.append({
            "id": item_id, "answerable": True, "excluded": False,
            "chunk_relation": relation, "relation_mode": values["relation_mode"],
            "business_function": domain, "question": gt_item.get("question", ""),
            "evidence_type": gt_item.get("evidence_type"),
            "gold_chunk_ids": values["gold_ids"], "retrieved_chunk_ids": retrieved_ids,
            "span_ranks": values["ranks"], "no_span": values["n_spans"] == 0,
            "n_spans": values["n_spans"], "n_spans_found": values["n_spans_found"],
            "missing_text_ids": missing_text_ids,
            "hit": {f"hit@{k}": values[f"hit@{k}"] for k in KS_SPAN},
            "id_hit": {f"id_hit@{k}": values[f"id_hit@{k}"] for k in KS_SPAN},
            "recall": {f"recall@{k}": values[f"recall@{k}"] for k in RECALL_KS_SPAN},
            "mrr": values["mrr"],
        })

    _span_finalize_metrics(metrics)
    for m in relation_metrics.values():
        _span_finalize_metrics(m)
    for m in domain_metrics.values():
        _span_finalize_metrics(m)

    return {"overall": metrics, "relation_metrics": relation_metrics,
            "domain_metrics": domain_metrics, "audit_rows": audit_rows}

def _span_error_analysis(rows: list[dict], chunk_to_bf: dict[str, str]) -> dict:
    """미적중(top-3 밖) 문항의 원인·혼입 패턴을 집계한다.

    span 자체가 없는 문항(no_span)은 검색 품질과 무관하게 항상 miss이므로
    여기서 제외하고 별도 섹션(no_span_rows)으로 다룬다.
    """
    misses = [row for row in rows if not row["excluded"] and not row["no_span"]
              and not row["hit"]["hit@3"]]
    no_span_rows = [row for row in rows if not row["excluded"] and row["no_span"]]
    by_domain: dict[str, int] = {}
    for row in misses:
        by_domain[row["business_function"]] = by_domain.get(row["business_function"], 0) + 1

    cause: dict[str, int] = {}
    intruders: dict[str, int] = {}
    cross_flow: dict[tuple[str, str], int] = {}
    for row in misses:
        top3 = row["retrieved_chunk_ids"][:3]
        top3_bf = [chunk_to_bf.get(cid, "(unknown)") for cid in top3]
        gt_bf = row["business_function"]
        reason = "정분류(업무 내 랭킹·청킹)" if gt_bf in top3_bf else "오분류(다른 업무로 혼입)"
        cause[reason] = cause.get(reason, 0) + 1
        for cid, bf in zip(top3, top3_bf):
            if bf != gt_bf:
                intruders[cid] = intruders.get(cid, 0) + 1
        if top3_bf and top3_bf[0] != gt_bf:
            key = (gt_bf, top3_bf[0])
            cross_flow[key] = cross_flow.get(key, 0) + 1

    worst = [row for row in misses if not row["hit"]["hit@10"]][:8]
    return {"misses": misses, "no_span_rows": no_span_rows, "by_domain": by_domain,
            "cause": cause, "intruders": intruders, "cross_flow": cross_flow, "worst": worst}

def write_span_report(result: dict, output_path: Path, gt_path: Path, retrieval_source: str,
                  chunk_metadata: list[dict]) -> None:
    """eval_anchor_v3_report.md와 같은 구성(개요/데이터/파라미터/지표/결과/오류분석/부록)의 span판 리포트."""
    m = result["overall"]
    relation_metrics = result["relation_metrics"]
    domain_metrics = result["domain_metrics"]
    rows = result["audit_rows"]
    chunk_to_bf = {c["chunk_id"]: c.get("business_function", "(unknown)") for c in chunk_metadata}

    try:
        import rag
        retriever_desc = (f"RRF(k={rag.RRF_K}, alpha={rag.RRF_ALPHA}) + "
                          f"BF_MODE={rag.BF_MODE}(cap={rag.BF_DOC_CAP}, boost={rag.BF_BOOST}, "
                          f"facet={rag.FACET_BOOST})")
        embedding_desc = rag.MODEL_NAME
    except Exception:
        retriever_desc = "정보 없음(외부 검색 결과 사용)"
        embedding_desc = "정보 없음(외부 검색 결과 사용)"

    lines = ["# KDIC 검색 평가 리포트 — span 기준(다중 span, and/or 지원)", "",
              "## 1. 개요", "",
              "정답 텍스트(`gt_anchor_spans`)가 검색된 청크 본문에 포함되는지로 hit을 판정한다.",
              "gold `chunk_id`를 직접 비교하는 기존 `eval_anchor_v3.py`와 달리, 청크 재분할로",
              "chunk_id가 바뀌어도 내용이 같으면 hit으로 잡힌다. `and`는 필요한 span 전부,",
              "`or`/`single`은 하나만 발견되면 hit이다. `id_hit@k`는 기존 chunk_id 직접비교",
              "결과를 참고용으로 함께 계산한 것이다.", "",
              "## 2. 평가 대상 / 데이터 구성", "",
              f"- GT 라벨: `{gt_path}`",
              f"- 전체 {m['n_total']}건 · 평가 대상(answerable=true) {m['n_evaluated']}건 · "
              f"제외(answerable=false) {m['n_excluded_unanswerable']}건 · "
              f"라벨 불일치 {m['n_inconsistent']}건",
              f"- 평가 대상 중 span 없음(라벨에 인용 가능한 정답 텍스트가 없음): "
              f"{m['n_no_span']}건 — 8절 참고(검색 품질과 무관하게 항상 miss로 집계됨)",
              f"- retrieved 상위 {DEPTH_SPAN} 내 chunk_id → 본문 조회 실패 연인원: "
              f"{m['n_missing_chunk_text']}건 (0이 아니면 chunks.jsonl 스냅샷과 검색 인덱스 "
              "버전이 다를 수 있으니 먼저 확인할 것)", ""]
    lines += _pct_table({rel: rm["n_total"] for rel, rm in relation_metrics.items()},
                        m["n_evaluated"], ("relation", "문항수"))
    lines += ["",
              "## 3. 실험 파라미터", "",
              f"- Corpus: {len(chunk_metadata)}개 청크 (`chunks.jsonl`)",
              f"- Retriever: {retriever_desc}",
              f"- Embedding: {embedding_desc}",
              f"- 검색 단위: chunk 검색 결과 + 정답 텍스트(span) 본문 포함 여부로 채점",
              f"- 검색 소스: {retrieval_source}",
              f"- Top-K: {DEPTH_SPAN}", "",
              "## 4. 평가 지표 및 판정 기준", "",
              "- Hit@1/3/5/10: Top-K 안에서 relation 조건을 만족하며 gold span이 발견되는지",
              "  (분모: 평가 대상 문항수). `and`는 필요한 span 전부, 그 외는 하나만 발견되면 hit.",
              "- Macro Recall@3/5/10: 문항별 recall(Top-K에서 회수한 span 비율)의 문항 평균. 주지표.",
              "- (참고) Micro Recall@3/5/10: 전체 span occurrence 기준 합산 recall. 문항당 span",
              "  개수가 많을수록(주로 `and`) 가중치가 커짐 — 보조지표로만 사용.",
              "- MRR: `and`는 마지막으로 발견된 필수 span의 순위, 그 외는 처음 발견된 span의",
              "  순위의 역수, Top-10까지만 본다(MRR@10).",
              "- id_hit@k: gold `chunk_id`를 직접 비교하는 기존 방식(참고용, 10절 비교표).",
              "- answerable=false 문항은 전 지표의 분모에서 제외.",
              "- span 없음 문항은 분모에 포함되지만(n_evaluated) 항상 hit=False로 집계된다", ""]
    lines += ["## 5. 전체 평가 결과", "",
              "| Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |",
              "|---:|---:|---:|---:|---:|",
              f"| {m['hit@1']:.3f} | {m['hit@3']:.3f} | {m['hit@5']:.3f} | {m['hit@10']:.3f} | "
              f"{m['mrr']:.3f} |",
              "",
              "| MacroRecall@3 | MacroRecall@5 | MacroRecall@10 |",
              "|---:|---:|---:|",
              f"| {m['macro_recall@3']:.3f} | {m['macro_recall@5']:.3f} | "
              f"{m['macro_recall@10']:.3f} |",
              "",
              f"- (참고) Micro Recall@10: {m['recall@10']:.3f} · span 총계(occurrence): "
              f"{m['total_spans']} · 회수(@10): {m['recalled@10']}", ""]

    lines += ["## 6. Relation별 결과", "",
              "| relation | 문항수 | Hit@1 | Hit@3 | Hit@5 | MacroRecall@10 | MRR |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for rel, rm in sorted(relation_metrics.items(), key=lambda kv: -kv[1]["n_total"]):
        lines.append(f"| {rel} | {rm['n_total']} | {rm['hit@1']:.3f} | {rm['hit@3']:.3f} | "
                    f"{rm['hit@5']:.3f} | {rm['macro_recall@10']:.3f} | {rm['mrr']:.3f} |")

    lines += ["", "## 7. 도메인별 결과", "",
              "| 업무 | 문항수 | Hit@1 | Hit@3 | Hit@5 | MacroRecall@10 | MRR |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for domain, dm in sorted(domain_metrics.items(), key=lambda kv: -kv[1]["n_total"]):
        lines.append(f"| {domain} | {dm['n_total']} | {dm['hit@1']:.3f} | {dm['hit@3']:.3f} | "
                    f"{dm['hit@5']:.3f} | {dm['macro_recall@10']:.3f} | {dm['mrr']:.3f} |")

    err = _span_error_analysis(rows, chunk_to_bf)
    no_span_rows = err["no_span_rows"]
    lines += ["", "## 8. span 없음 라벨", "",
              f"{len(no_span_rows)}건 — 원문에 그대로 인용 가능한 정답 텍스트가 없어(주로 "
              "`evidence_type=inferable`, 계산·추론형 답변) gt_anchor_span 자체가 비어 있다.",
              "검색이 아무리 정확해도 이 문항들은 항상 miss로 집계되므로, 전체 Hit/MRR을",
              f"{len(no_span_rows)}/{m['n_evaluated']}건만큼 구조적으로 낮춘다. span을 소급",
              "라벨링하거나 별도 분모로 빼고 보는 것을 검토할 것.", ""]
    if no_span_rows:
        lines += ["| id | relation | evidence_type | gold chunk IDs | question |",
                  "|---|---|---|---|---|"]
        for row in no_span_rows:
            lines.append(f"| {row['id']} | {row['chunk_relation']} | {row['evidence_type']} | "
                        f"{_format_ids(row['gold_chunk_ids'])} | {row['question']} |")

    n_miss = len(err["misses"])
    n_scoreable = m["n_evaluated"] - len(no_span_rows)
    lines += ["", "## 9. 오류 분석", "",
              f"- 미적중(top-3 밖) {n_miss}건 / 채점 가능 문항 {n_scoreable}건 "
              f"({n_miss / n_scoreable * 100 if n_scoreable else 0:.1f}%, span 없음 제외)", ""]
    if err["cause"]:
        lines += ["### 9-1. 미적중 원인 분포", "",
                  "정분류: gt 업무 청크가 top-3 안에 있으나 순위/청킹 문제로 span을 못 찾음. "
                  "오분류: top-3 전부 다른 업무 청크로 채워짐.", ""]
        lines += _pct_table(err["cause"], n_miss, ("원인", "건수"))

    lines += ["", "### 9-2. 업무별 미적중", "",
              "| 업무 | 문항수 | 미적중 | 미적중률 |", "|---|---:|---:|---:|"]
    for domain, count in sorted(err["by_domain"].items(), key=lambda kv: -kv[1]):
        total = domain_metrics[domain]["n_total"]
        lines.append(f"| {domain} | {total} | {count} | {count / total * 100 if total else 0:.1f}% |")

    if err["intruders"]:
        lines += ["", "### 9-3. 혼입 문서 랭킹 (미적중 top-3를 잠식한 다른 업무 청크)", "",
                  "| 청크 ID | 출현 | 업무 |", "|---|---:|---|"]
        for cid, count in sorted(err["intruders"].items(), key=lambda kv: -kv[1])[:15]:
            lines.append(f"| `{cid}` | {count} | {chunk_to_bf.get(cid, '(unknown)')} |")

    if err["cross_flow"]:
        lines += ["", "### 9-4. 업무 간 혼입 흐름 (정답 업무 → top-1 업무)", "",
                  "| 정답 업무 | → top-1 업무 | 건수 |", "|---|---|---:|"]
        for (gt_bf, top1_bf), count in sorted(err["cross_flow"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {gt_bf} | {top1_bf} | {count} |")

    if err["worst"]:
        lines += ["", "### 9-5. 대표 실패 사례 (gold span이 top-10에도 없음)", ""]
        for row in err["worst"]:
            lines += [f"- **[{row['business_function']}] {row['id']}** ({row['chunk_relation']}) "
                     f"— {row['question']}",
                     f"  - gold chunk IDs: {_format_ids(row['gold_chunk_ids'])}",
                     f"  - span 발견({row['n_spans_found']}/{row['n_spans']}), 순위: "
                     f"{row['span_ranks']}",
                     f"  - top-3: {_format_ids(row['retrieved_chunk_ids'][:3])}"]

    lines += ["", "## 10. 개선 우선순위", ""]
    priorities = []
    for domain, count in sorted(err["by_domain"].items(), key=lambda kv: -kv[1])[:3]:
        total = domain_metrics[domain]["n_total"]
        priorities.append(f"'{domain}' 업무 — 미적중 {count}/{total}건"
                          f"({count / total * 100 if total else 0:.1f}%)로 가장 취약함")
    and_m = relation_metrics.get("and")
    if and_m and and_m["hit@3"] < m["hit@3"]:
        priorities.append(f"`and` relation(다중 span 필요) Hit@3={and_m['hit@3']:.3f}로 "
                          f"전체 평균({m['hit@3']:.3f})보다 낮음 — MacroRecall@10="
                          f"{and_m['macro_recall@10']:.3f}로 부분 회수는 되고 있어 다중 청크"
                          " 동시 회수 전략(top-k 확대/쿼리 분해) 점검 필요")
    if err["intruders"]:
        top_intruder = max(err["intruders"].items(), key=lambda kv: kv[1])
        priorities.append(f"`{top_intruder[0]}` 청크가 미적중 {top_intruder[1]}건에서 top-3를 잠식 "
                          f"— 업무 분류/부스트 파라미터 재검토 대상 1순위")
    if no_span_rows:
        priorities.append(f"span 없는 라벨 {len(no_span_rows)}건은 검색과 무관하게 항상 miss — "
                          "8절 목록부터 소급 라벨링하면 즉시 Hit/MRR이 개선됨")
    lines += [f"{i}. {p}" for i, p in enumerate(priorities, 1)] or ["_미적중 사례 없음._"]

    lines += ["", "## 11. span 기준 vs chunk_id 기준 비교 (참고)", "",
              "chunk_id 직접비교(기존 방식) 대비 span 기준 채점의 거품/회수(percentage points):",
              "",
              "| 지표 | span 기준 | chunk_id 기준 | 차이(span - id, pp) |",
              "|---|---:|---:|---:|"]
    for key in ("hit@1", "hit@3", "hit@5", "hit@10"):
        id_key = f"id_{key}"
        bubble = (m[key] - m[id_key]) * 100
        lines.append(f"| {key} | {m[key]:.3f} | {m[id_key]:.3f} | {bubble:+.1f}pp |")

    lines += ["", "## 부록. 문항별 라벨과 검색 청크", "",
              "| id | answerable | relation(mode) | 업무 | gold chunk IDs | span 발견(회수/필요) | "
              "각 span 순위 | Top-10 retrieved chunk IDs | span Hit@1/3/5/10 | id Hit@1/3/5/10 |",
              "|---|---|---|---|---|---:|---|---|---|---|"]
    for row in rows:
        if row["excluded"]:
            lines.append(f"| {row['id']} | false | - | - | - | - | - | - | excluded | excluded |")
            continue
        span_hits = "/".join(str(int(row["hit"][f"hit@{k}"])) for k in KS_SPAN)
        id_hits = "/".join(str(int(row["id_hit"][f"id_hit@{k}"])) for k in KS_SPAN)
        rank_str = ",".join(str(r) if r else "-" for r in row["span_ranks"]) or "-"
        lines.append(
            "| {id} | true | {relation}({mode}) | {bf} | {gold} | {nf}/{n} | {ranks} | "
            "{retrieved} | {span_hits} | {id_hits} |".format(
                id=row["id"], relation=row["chunk_relation"], mode=row["relation_mode"],
                bf=row["business_function"], gold=_format_ids(row["gold_chunk_ids"]),
                nf=row["n_spans_found"], n=row["n_spans"], ranks=rank_str,
                retrieved=_format_ids(row["retrieved_chunk_ids"][:DEPTH_SPAN]),
                span_hits=span_hits, id_hits=id_hits))

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def _span_print_summary(result: dict, report_path: Path) -> None:
    m = result["overall"]
    print("=== KDIC span 기준(다중 span) 평가 결과 ===")
    print()
    _print_group("데이터", [
        ("n_total", str(m["n_total"])),
        ("n_evaluated", str(m["n_evaluated"])),
        ("n_excluded", str(m["n_excluded_unanswerable"])),
        ("n_inconsistent", str(m["n_inconsistent"])),
        ("n_no_span", str(m["n_no_span"])),
        ("n_missing_chunk_text", str(m["n_missing_chunk_text"])),
    ])
    _print_group("Hit@K (span 기준 / id 기준)", [
        (f"Hit@{k}", f"{m[f'hit@{k}']:.3f} / {m[f'id_hit@{k}']:.3f}") for k in KS_SPAN
    ])
    _print_group("MacroRecall", [
        ("@3", f"{m['macro_recall@3']:.3f}"),
        ("@5", f"{m['macro_recall@5']:.3f}"),
        ("@10", f"{m['macro_recall@10']:.3f}  (micro@10={m['recall@10']:.3f})"),
    ])
    _print_group("MRR", [("MRR@10", f"{m['mrr']:.3f}")])
    print(f"report -> {report_path}")

# ══════════════════════════════════════════════════════════════════════════
# §6. 앵커-host 판정 — 구 eval_anchor_gold.py.
#     §4·§5 와 결정적으로 다른 점: gold chunk_id 를 전혀 보지 않고, 앵커 텍스트를
#     **포함한 모든 청크**를 그 문항의 정답 host 집합으로 매번 새로 계산한다.
#     재청킹에 완전히 무관해지는 대신, 앵커가 코퍼스에 아예 없으면(no_host)
#     채점 자체가 불가능해 별도로 센다.
#     Wilson CI · 등급 nDCG · McNemar 는 §2 에 있다(다른 서브커맨드도 쓸 수 있게).
# ══════════════════════════════════════════════════════════════════════════


def evaluate_anchor_gold(gt: list[dict], chunks: list[dict],
                         retrieved: list[dict]) -> tuple[list[dict], list, list]:
    """(rows, no_anchor, no_host) 반환. rank=strict(앵커 host), soft_rank=앵커∪gt_chunk_ids."""
    text = {c["chunk_id"]: norm_ws(c["text"]) for c in chunks}
    ret = {r["id"]: r["retrieved_chunk_ids"] for r in retrieved}
    # 앵커를 품은 청크 = 그 문항의 정답 청크 (재청킹에 무관하게 매번 새로 계산)
    rows, no_anchor, no_host = [], [], []
    for g in gt:
        if g.get("answerable") is not True:
            continue
        span = norm_ws(g.get("gt_anchor_span"))
        if not span:
            no_anchor.append(g["id"])
            continue
        hosts = {cid for cid, t in text.items() if span in t}
        if not hosts:
            no_host.append(g["id"])
            continue
        r = ret.get(g["id"], [])
        rank = next((i for i, c in enumerate(r, 1) if c in hosts), 0)
        # soft = 앵커 청크 ∪ GT가 함께 라벨한 청크 중 첫 적중 순위
        rel = {c: REL_GT for c in (g.get("gt_chunk_ids") or []) if c in text}
        rel.update({c: REL_HOST for c in hosts})
        soft = next((i for i, c in enumerate(r, 1) if c in rel), 0)
        rows.append({"id": g["id"], "bf": g["business_function"], "q": g["question"],
                     "rank": rank, "soft_rank": soft, "n_host": len(hosts),
                     "n_rel": len(rel), "rels": [rel.get(c, 0) for c in r], "top5": r[:5]})
    return rows, no_anchor, no_host


def report_anchor_gold(rows: list[dict], no_anchor: list, no_host: list,
                       label: str) -> tuple[dict, float]:
    n = len(rows)
    print(f"\n=== {label} ===")
    print(f"평가 대상 {n}건 | 앵커 없음 {len(no_anchor)}건 | "
          f"앵커를 품은 청크가 코퍼스에 없음 {len(no_host)}건")
    if no_host:
        print(f"  코퍼스 미수록 앵커: {no_host}")
    if not n:
        print("  채점 가능한 문항이 없어 지표를 산출하지 않는다.")
        return {}, 0.0
    hits = {k: sum(1 for r in rows if 0 < r["rank"] <= k) / n for k in KS_GOLD}
    mrr = sum(1 / r["rank"] for r in rows if 0 < r["rank"] <= 10) / n
    print("| " + " | ".join(f"Hit@{k}" for k in KS_GOLD) + " | MRR@10 |")
    print("|" + "---:|" * (len(KS_GOLD) + 1))
    print("| " + " | ".join(f"{hits[k]:.3f}" for k in KS_GOLD) + f" | {mrr:.3f} |")
    lo, hi = wilson(sum(1 for r in rows if r["rank"] == 1), n)
    print(f"Hit@1 95% CI(Wilson): [{lo:.3f}, {hi:.3f}]  (±{(hi-lo)/2*100:.1f}pp) — "
          f"이보다 작은 차이는 이 평가셋(n={n})으로 구분할 수 없다.")
    soft = {k: sum(1 for r in rows if 0 < r["soft_rank"] <= k) / n for k in (1, 3, 5)}
    nd = {k: sum(ndcg(r["rels"], k) for r in rows) / n for k in (3, 5, 10)}
    print(f"soft(앵커∪gt_chunk_ids) Hit@1 {soft[1]:.3f} · Hit@3 {soft[3]:.3f} · "
          f"Hit@5 {soft[5]:.3f}")
    print(f"nDCG@3 {nd[3]:.3f} · nDCG@5 {nd[5]:.3f} · nDCG@10 {nd[10]:.3f}"
          f"  (등급: 앵커청크 {REL_HOST} / GT 라벨청크 {REL_GT})")
    print(f"평균 정답청크 수(앵커 보유 청크): {sum(r['n_host'] for r in rows)/n:.2f} · "
          f"평균 relevant 청크 수(등급 포함): {sum(r['n_rel'] for r in rows)/n:.2f}")
    print("\n| 업무 | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 |")
    print("|---|---:|---:|---:|---:|---:|")
    by = collections.defaultdict(list)
    for r in rows:
        by[r["bf"]].append(r)
    for bf, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        v = [sum(1 for r in rs if 0 < r["rank"] <= k) / len(rs) for k in (1, 3, 5, 10)]
        print(f"| {bf} | {len(rs)} | " + " | ".join(f"{x:.3f}" for x in v) + " |")
    return hits, mrr


# ══════════════════════════════════════════════════════════════════════════
# §7. 공개 별칭 — 통합 전 이름으로도 임포트되게 유지한다.
#     기존 호출부(admin/runner.py · tune_params*.py · audit_anchors.py 등)는
#     `import eval as ev3` 한 줄만 바꾸면 나머지가 그대로 동작한다.
# ══════════════════════════════════════════════════════════════════════════

load_jsonl = _load_jsonl                 # 권장 공개명
default_data_dir = _default_data_dir
norm_text = _norm_text
format_ids = _format_ids
pct_table = _pct_table
print_group = _print_group
search_results = _search_results
get_gt_chunk_ids = _get_gt_chunk_ids
get_gt_anchors = _get_gt_anchors
write_chunk_report = write_report         # write_report = chunk 판정 리포트(정본)
evaluate_chunk_retrieval = evaluate_retrieval


# ══════════════════════════════════════════════════════════════════════════
# §8. CLI — 서브커맨드 chunk / span / gold.
#     인자 없이 실행하거나 첫 인자가 옵션이면 chunk 로 붙인다
#     (구 `python eval_anchor_v3.py --gt ...` 명령이 그대로 통한다).
# ══════════════════════════════════════════════════════════════════════════

SUBCOMMANDS = ("chunk", "span", "gold")


def _cmd_chunk(args: argparse.Namespace) -> None:
    """구 eval_anchor_v3.main() — 판정 로직 무변경. 기본 판정 기준만 앵커텍스트 전용이다."""
    data_dir = _default_data_dir()
    gt_data = _load_jsonl(args.gt)
    if args.retrieved:
        retrieved_data = _load_jsonl(args.retrieved)
        retrieval_source = f"외부 결과 `{args.retrieved}` (검색 미실행)"
    else:
        retrieved_data = _search_results(gt_data, args.mode, data_dir,
                                        depth=DEPTH_CHUNK, gold_bf=True)
        retrieval_source = f"`rag.Searcher.search(question, k=10, mode={args.mode!r})`"
    chunk_metadata = _load_jsonl(args.chunks)
    result = evaluate_retrieval(gt_data, retrieved_data, chunk_metadata,
                                score=args.score, id_fallback=args.id_fallback)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_report(result, args.report, args.gt, retrieval_source, chunk_metadata)
    _print_summary(result, args.report)


def _cmd_span(args: argparse.Namespace) -> None:
    """구 eval_anchor_span_multi.main() — 동작 무변경(검색 깊이 10 · gold BF 주입 없음)."""
    data_dir = _default_data_dir("chunks.jsonl")
    gt_data = _load_jsonl(args.gt)
    if args.limit:
        gt_data = gt_data[: args.limit]
    if args.retrieved:
        retrieved_data = _load_jsonl(args.retrieved)
        retrieval_source = f"외부 결과 `{args.retrieved}` (검색 미실행)"
    else:
        retrieved_data = _search_results(gt_data, args.mode, data_dir,
                                        depth=DEPTH_SPAN, gold_bf=False)
        retrieval_source = f"`rag.Searcher.search(question, k=10, mode={args.mode!r})`"
    chunk_metadata = _load_jsonl(args.chunks)
    result = evaluate_span_retrieval(gt_data, retrieved_data, chunk_metadata, args.id_fallback)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_span_report(result, args.report, args.gt, retrieval_source, chunk_metadata)
    _span_print_summary(result, args.report)


def _cmd_gold(args: argparse.Namespace) -> None:
    """구 eval_anchor_gold.main() — 동작 무변경."""
    gt, chunks = _load_jsonl(args.gt), _load_jsonl(args.chunks)
    rows, na, nh = evaluate_anchor_gold(gt, chunks, _load_jsonl(args.retrieved))
    report_anchor_gold(rows, na, nh, args.label)
    if args.compare:
        base, _, _ = evaluate_anchor_gold(gt, chunks, _load_jsonl(args.compare))
        mcnemar(base, rows, str(args.compare), str(args.retrieved))
    if args.dump_miss:
        miss = [r for r in rows if not (0 < r["rank"] <= 30)]
        Path(args.dump_miss).write_text(
            json.dumps(miss, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nHit@30 미적중 {len(miss)}건 -> {args.dump_miss}")


def _build_parser() -> argparse.ArgumentParser:
    data_dir = _default_data_dir()
    ap = argparse.ArgumentParser(
        prog="eval.py",
        description="KDIC 통합 검색 평가 — chunk(정본) / span(다중스팬) / gold(앵커-host)")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("chunk", help="청크·앵커 판정(정본, 구 eval_anchor_v3.py)")
    p.add_argument("--gt", default=data_dir / "gt_schema_v6.jsonl", type=Path)
    p.add_argument("--chunks", default=data_dir / "chunks.jsonl", type=Path)
    p.add_argument("--retrieved", type=Path,
                   help="id, retrieved_chunk_ids JSONL. 생략하면 현재 rag.Searcher로 검색한다.")
    p.add_argument("--mode", default="hybrid_bf", help="--retrieved 생략 시 rag 검색 mode")
    p.add_argument("--report", default=data_dir / "eval_chunk_report.md", type=Path)
    p.add_argument("--score", default="anchor", choices=SCORE_MODES,
                   help="적중 판정 기준. anchor=앵커텍스트 판정(기본, 평가셋 정책) · "
                        "chunk_id=gold ID 완전일치만 산출 · both=둘 다 병기. "
                        "anchor/both는 산출 지표가 같고 콘솔 표시만 다르다 — "
                        "chunk_id 지표는 오류 분석·감사표에 필요해 항상 계산된다.")
    p.add_argument("--id-fallback", action="store_true", dest="id_fallback",
                   help="앵커가 덮지 못한 gold 를 chunk_id 로 요구한다(구 동작). "
                        "기본 꺼짐 — gt_chunk_ids 는 특정 청킹에 대한 좌표라 재청킹하면 "
                        "값이 변하므로 평가 기준으로 쓰지 않는다. 라벨 잔량 감사용으로만 켠다.")
    p.set_defaults(func=_cmd_chunk)

    p = sub.add_parser("span", help="다중 span 판정(구 eval_anchor_span_multi.py)")
    p.add_argument("--gt", default=data_dir / "gt_natural450_multi.jsonl", type=Path)
    p.add_argument("--chunks", default=data_dir / "chunks.jsonl", type=Path)
    p.add_argument("--retrieved", type=Path,
                   help="id, retrieved_chunk_ids JSONL. 생략하면 현재 rag.Searcher로 검색한다.")
    p.add_argument("--mode", default="hybrid_bf", help="--retrieved 생략 시 rag 검색 mode")
    p.add_argument("--report", default=data_dir / "eval_span_report.md", type=Path)
    p.add_argument("--limit", type=int, default=0,
                   help="처음 N건만 평가(스모크 테스트용, 대표성 있는 지표가 아님). 0이면 전체.")
    p.add_argument("--id-fallback", action="store_true", dest="id_fallback",
                   help="스팬이 아예 없는 문항(evidence_type=inferable 등)만 gold chunk_id "
                        "등장 여부로 대체 판정한다. 기본 꺼짐(기존 리포트와 동일).")
    p.set_defaults(func=_cmd_span)

    p = sub.add_parser("gold", help="앵커-host 판정 + Wilson CI·nDCG·McNemar(구 eval_anchor_gold.py)")
    p.add_argument("--gt", default=data_dir / "gt_natural450_v10_anchor.jsonl", type=Path)
    p.add_argument("--chunks", default=data_dir / "chunks.jsonl", type=Path)
    p.add_argument("--retrieved", default=data_dir / "retrieved_top30.jsonl", type=Path)
    p.add_argument("--label", default="anchor-gold")
    p.add_argument("--dump-miss", default="", dest="dump_miss")
    p.add_argument("--compare", default="",
                   help="비교 대상 retrieved 파일 — McNemar 유의성 검정")
    p.set_defaults(func=_cmd_gold)
    return ap


def main(argv: list[str] | None = None) -> None:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    # 서브커맨드 생략 시 chunk — 구 `python eval_anchor_v3.py --gt ...` 호환
    if not argv or argv[0] not in SUBCOMMANDS and not argv[0] in ("-h", "--help"):
        argv = ["chunk"] + argv
    args = _build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        _build_parser().print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
