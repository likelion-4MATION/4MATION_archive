# -*- coding: utf-8 -*-
"""대시보드 지표 + 실측 A/B 근거.

**측정하지 않은 조합에는 숫자를 만들지 않는다.** 실측이 있는 지점만 값을 내고,
나머지는 `None` 으로 돌려 프런트가 "?" 와 "미측정" 배지를 띄우게 한다.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

import settings

REPO = settings.REPO
CRAWLER = REPO / "crawler"

# ── 실측 정확도 (지표: 앵커 hit@5) ─────────────────────────────────────
# 출처: crawler/data/tune_v2_summary.md · eval_overlap_report.md · eval_tablefix_report.md
ACC_PRESET = {"accuracy": 0.9054, "balanced": 0.8946, "diverse": 0.8892}
ACC_K = {3: 0.8108, 5: 0.9081}                     # exp_tablefix K3/K5 (181청크)
ACC_CHUNK = {                                       # "size|overlap|table_keep"
    "800|100|1": {"chunks": 181, "all": 0.8977, "single": 0.9081, "and": 0.8182,
                  "src": "exp_tablefix on gap≤12 (현행)"},
    "800|100|0": {"chunks": 215, "all": 0.8209, "single": 0.8946, "and": 0.3091,
                  "src": "exp_tablefix off (구 설정)"},
    "800|200|0": {"chunks": 218, "all": 0.8163, "single": 0.8892, "and": 0.3091,
                  "src": "exp_overlap OVERLAP=200"},
    "800|300|0": {"chunks": 222, "all": 0.8116, "single": 0.8811, "and": 0.3273,
                  "src": "exp_overlap OVERLAP=300"},
}
BASELINE = {"acc": 0.9081, "calls": 1.72, "latency": 4.0, "cost": 9.7}

# 경로별 실측 (exp/route_e2e_report.md)
LAT_FAST, LAT_RAG = 1.32, 4.96
FAST_SHARE = 0.28                                   # 조기차단 경로 비중
FIRE_RATE = {"msdr": 0.020, "msdr+dpin": 0.042}     # 큐폼 되묻기 발동률 (450셋 실측)


def _measured_at_k(m: dict, k: int) -> dict | None:
    """재빌드 실측에서 `hit@k` 를 꺼낸다 — '정답 근거가 상위 k개 안에 들 확률'.

    관리자가 고르는 `k` 는 답변에 넣을 문서 수라, 이 값이 그대로 그 의미가 된다.
    러너는 hit@1·3·5·10 만 내므로 k=2·4 는 실측이 없다(만들지 않는다).
    """
    v = (m or {}).get(f"hit@{int(k)}")
    if v is None:
        return None
    return {"value": v, "grade": "measured", "metric": f"hit@{int(k)}",
            "src": f"재빌드 실측 {str(m.get('at', ''))[:10]} · {m.get('chunks', '?')}청크 "
                   f"— 정답 근거가 상위 {int(k)}개 안에 들 확률"}


def accuracy_for(cfg: dict, changed: list[str], measured: dict | None = None) -> dict:
    """정확도 예측. 축이 둘 이상 바뀌면 계산하지 않는다(효과가 곱해지지 않는다).

    **실측이 있으면 상수표보다 먼저 쓴다.** 예전에는 아무것도 안 바꿨을 때 `BASELINE["acc"]`
    (0.9081, 181청크 시절 상수)를 그대로 돌려줘서 '변경 후' 칸이 코퍼스를 바꿔도 늘 0.9081 로
    굳어 있었다.
    """
    m = measured if measured is not None else settings.measured()
    chunk_ax = any(k in changed for k in ("CHUNK_SIZE", "OVERLAP", "TABLE_KEEP"))
    k_ax = "k" in changed
    preset_ax = "preset" in changed
    axes = sum([chunk_ax, k_ax, preset_ax])

    if axes == 0:
        got = _measured_at_k(m, cfg.get("k", 5))
        if got:
            return {**got, "src": got["src"] + " · 변경 없음"}
        return {"value": BASELINE["acc"], "grade": "measured",
                "metric": "anchor hit@5", "src": "현재 적용 중 (재빌드 실측 기록 없음)"}
    if axes > 1:
        return {"value": None, "grade": "mixed", "metric": None,
                "src": "정확도에 영향을 주는 항목을 두 가지 이상 동시에 변경"}
    if chunk_ax:
        key = f"{int(cfg['CHUNK_SIZE'])}|{int(cfg['OVERLAP'])}|{1 if cfg['TABLE_KEEP'] else 0}"
        hit = ACC_CHUNK.get(key)
        return ({"value": hit["single"], "grade": "measured", "metric": "anchor hit@5",
                 "src": hit["src"], "detail": hit} if hit else
                {"value": None, "grade": "unmeasured", "metric": None,
                 "src": "이 조합은 평가한 적이 없습니다 — [한 번에 실행]으로 재보세요"})
    if k_ax:
        got = _measured_at_k(m, cfg["k"])
        if got:
            return got
        v = ACC_K.get(int(cfg["k"]))
        return ({"value": v, "grade": "measured", "metric": f"hit@{int(cfg['k'])}",
                 "src": f"exp_tablefix K{int(cfg['k'])} (181청크)"}
                if v is not None else
                {"value": None, "grade": "unmeasured", "metric": None,
                 "src": f"k={int(cfg['k'])}는 실측이 없습니다 (러너는 hit@1·3·5·10만 냅니다)"})
    v = ACC_PRESET.get(cfg.get("preset"))
    return ({"value": v, "grade": "measured", "metric": "anchor hit@5",
             "src": "tune_params_v2 그리드 (TEST 430)"}
            if v is not None else {"value": None, "grade": "unmeasured",
                                   "metric": None, "src": ""})


def current_point() -> dict:
    """⑦탭 '현재' 열의 기준점 — **지금 실제로 빌드된 조합**에서 만든다.

    예전에는 `ACC_CHUNK["800|100|1"]` 을 상수로 박아 썼는데, 재빌드로 코퍼스가 바뀌면
    화면이 계속 옛 조합을 '현재'라고 우겼다. 우선순위는

      ① 재빌드 실측(`settings.record_measured`) — 지금 인덱스를 직접 잰 값
      ② A/B 표에 그 조합이 있으면 그 값
      ③ 없으면 전부 `None` → 화면에 '미측정'

    지표가 섞이지 않게 `metric` 을 함께 돌려준다. 실측 경로의 `all` 은 러너가 낸
    앵커 hit@5(전체)이고, 단일/복합 분해는 러너가 내지 않으므로 `None` 이다.
    """
    cfg = settings.current()          # pending 이 아니라 override — 실제로 빌드된 조합
    key = f"{int(cfg['CHUNK_SIZE'])}|{int(cfg['OVERLAP'])}|{1 if cfg['TABLE_KEEP'] else 0}"
    m = settings.measured()
    c = corpus()
    if m.get("anchor_hit@5") is not None or m.get("hit@5") is not None:
        return {"key": key, "chunks": m.get("chunks") or c.get("chunks"),
                "all": m.get("anchor_hit@5"), "single": None, "and": None,
                "chunk_hit5": m.get("hit@5"), "grade": "measured",
                "src": (f"재빌드 실측 {str(m.get('at', ''))[:10]} · "
                        f"{m.get('n_evaluated', '?')}문항 · {m.get('chunks', '?')}청크")}
    hit = ACC_CHUNK.get(key)
    if hit:
        return {"key": key, "chunks": hit["chunks"], "all": hit["all"],
                "single": hit["single"], "and": hit["and"], "chunk_hit5": None,
                "grade": "measured", "src": hit["src"]}
    return {"key": key, "chunks": c.get("chunks"), "all": None, "single": None,
            "and": None, "chunk_hit5": None, "grade": "unmeasured",
            "src": "현재 조합은 A/B 표에도 없고 재빌드 실측 기록도 없습니다"}


def _ops(cfg: dict) -> dict:
    """콜 수·응답시간·비용 — 설정 하나로 계산. 기준선과 예상값에 같은 함수를 쓴다."""
    fast = FAST_SHARE if cfg.get("earlyBlock") else 0.0
    calls = fast * 1 + (1 - fast) * 2
    if cfg.get("askMode") == "llm":
        calls += FIRE_RATE.get(cfg.get("QFORM_SCOPE"), 0.02) * int(cfg.get("MAX_ASK_TURNS", 2))
    latency = fast * LAT_FAST + (1 - fast) * LAT_RAG
    cost = BASELINE["cost"] * (calls / BASELINE["calls"]) * \
        (float(cfg.get("maxTokens", 512)) / 512 * 0.45 + 0.55)
    return {"calls": round(calls, 2), "latency": round(latency, 2), "cost": round(cost, 1)}


def baseline_of(saved: dict) -> dict:
    """**지금 저장된 설정**의 지표. 저장하면 '현재' 열이 즉시 따라 움직인다.

    재빌드 실측치(`settings.record_measured`)가 있으면 정확도는 그 값을 쓴다 — 추정표보다 우선.
    지표는 저장된 `k` 에 맞춰 `hit@k` 를 쓴다. '변경 후' 칸과 같은 잣대가 되도록.
    """
    import registry
    ops = _ops(saved)
    acc = _measured_at_k(settings.measured(), saved.get("k", 5))
    if acc is None:
        changed = [k for k in registry.BY_KEY
                   if str(saved.get(k)) != str(registry.DEFAULTS.get(k))]
        acc = accuracy_for(saved, changed, measured={})
    return {"acc": acc.get("value"), "acc_grade": acc.get("grade"),
            "acc_src": acc.get("src"), "acc_metric": acc.get("metric"), **ops}


def projection(cfg: dict, changed: list[str], saved: dict | None = None) -> dict:
    """변경 후 예상 지표. 기준선은 **저장된 설정**에서 계산한다."""
    ops = _ops(cfg)
    return {
        "accuracy": accuracy_for(cfg, changed),
        "calls": {"value": ops["calls"], "grade": "computed",
                  "src": "경로 비중 × 경로별 콜 수 (reject 1 / rag 2)"},
        "latency": {"value": ops["latency"], "grade": "computed",
                    "src": f"경로별 실측 (reject {LAT_FAST}s / rag {LAT_RAG}s)"},
        "cost": {"value": ops["cost"], "grade": "estimated",
                 "src": "콜 수 × 답변 길이 계수 (추정)"},
        "baseline": baseline_of(saved if saved is not None else cfg),
    }


# ── 코퍼스·데이터 신선도 ────────────────────────────────────────────────
def corpus() -> dict:
    f = CRAWLER / "data" / "chunks.jsonl"
    if not f.exists():
        return {"available": False}
    lens, docs = [], set()
    try:
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                lens.append(len(r.get("text") or ""))
                docs.add(r.get("parent_doc_id"))
    except (OSError, json.JSONDecodeError):
        return {"available": False}
    if not lens:
        return {"available": False}
    lens.sort()
    return {
        "available": True, "chunks": len(lens), "docs": len(docs),
        "avg": round(sum(lens) / len(lens)), "median": lens[len(lens) // 2],
        "max": max(lens), "min": min(lens),
        "over_limit": sum(1 for x in lens if x > int(settings.effective()["CHUNK_SIZE"])),
        "mtime": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
                 .astimezone().isoformat(timespec="seconds"),
    }


def attachments() -> dict:
    f = CRAWLER / "data" / "doc_attachments.json"
    if not f.exists():
        return {"available": False, "docs": []}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False, "docs": []}
    rows, total, uniq = [], 0, set()
    for doc, items in d.items():
        names = {i.get("anchor_text") for i in items}
        # 표 파싱 잔여물 — 줄바꿈·파이프가 섞인 표시명은 정제 대상으로 표시한다
        dirty = sum(1 for n in names if n and ("\n" in n or "|" in n or len(n) > 40))
        rows.append({"doc_id": doc, "count": len(items), "unique": len(names),
                     "types": sorted({i.get("file_type") for i in items if i.get("file_type")}),
                     "dirty_labels": dirty})
        total += len(items)
        uniq |= names
    return {"available": True, "docs": sorted(rows, key=lambda r: -r["count"]),
            "total": total, "unique": len(uniq),
            "dirty": sum(r["dirty_labels"] for r in rows)}


def freshness() -> dict:
    meta_dir = CRAWLER / "data" / "meta"
    last = None
    if meta_dir.exists():
        ts = [p.stat().st_mtime for p in meta_dir.glob("*.json")]
        if ts:
            last = datetime.fromtimestamp(max(ts), timezone.utc).astimezone() \
                .isoformat(timespec="seconds")
    c = corpus()
    return {
        "last_crawl": last,
        "corpus": f"{c.get('chunks','?')}청크 / {c.get('docs','?')}문서" if c.get("available") else "미확인",
        "insured_list_quarter": "2026년 2분기",     # 원문 명시: 업데이트 주기 분기
        "insured_list_indexed": False,               # xlsx 본문 미색인 — 알림 대상
        "rate_month": "2026-07",
    }


def health() -> dict:
    idx = CRAWLER / "data" / "index"
    return {
        "index_ok": (idx / "faiss.index").exists() and (idx / "bm25.pkl").exists(),
        "index_mtime": (datetime.fromtimestamp((idx / "faiss.index").stat().st_mtime,
                                               timezone.utc).astimezone().isoformat(timespec="seconds")
                        if (idx / "faiss.index").exists() else None),
        "router_ok": (REPO / "router_moai_embedding_model").exists(),
        "repo": str(REPO),
    }


def business_mix() -> list[dict]:
    """업무별 질의 분포 — 평가셋 기준 (실서비스 로그가 붙으면 그쪽으로 교체)."""
    f = CRAWLER / "data" / "testset_natural_450.jsonl"
    if not f.exists():
        return []
    from collections import Counter
    c = Counter()
    try:
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    c[json.loads(line).get("business_function")] += 1
    except (OSError, json.JSONDecodeError):
        return []
    tot = sum(c.values()) or 1
    return [{"name": k, "n": v, "pct": round(v / tot * 100, 1)} for k, v in c.most_common()]
