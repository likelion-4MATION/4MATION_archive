"""attachments.py — 근거 문서 첨부 조회 (청크 태깅 우선 + 문서 단위 폴백).

설계 원천: workflow/정리_4_첨부파이프라인_이식_doc-agg.md
  - 검색은 청크 단위, 생성은 부모 문서 단위 → 첨부도 하이브리드로 조회.
  - 청크 단위: 검색된 청크에 실제 태깅된 첨부(enc_real 조인)를 정밀 반환.
  - 문서 단위: 그 근거 문서에 태깅 청크가 하나도 없으면 doc_attachments.json의
    문서 전체 첨부로 폴백(서식 누락 방지 안전망).

특성: LLM·네트워크 무관한 순수 로컬 조회. chain.answer()에 top-level 'attachments'
      부가 필드로 실린다(계약 4필드 불변 — 부가 필드만 추가). app.py는 이 결과의
      abs_path/mime/orig_filename으로 st.download_button을 렌더한다.

첨부 실파일: crawler/data/files/{doc_id}/... (build_dataset.py --crawl 의 fetch 산출물).
            doc_attachments.json 각 항목의 local_path가 crawler/ 기준 상대경로.
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CRAWLER_DIR = ROOT / "crawler"
DOC_ATTACH_PATH = CRAWLER_DIR / "data" / "doc_attachments.json"

# 큐폼 후단 필터(B안)용: 첨부 조합 좌표 원천(유상 태깅) + 스코프
TAGGING_PATH = CRAWLER_DIR / "yesom_분기분석" / "attachment_tagging_template.csv"
QFORM_SCOPE_BF = "착오송금 반환 신청"   # 하위호환 별칭 (ver1~3 단일 스코프)

# ver4 M2 — 업무별 조합 테이블. **파일 분리 + combo_id prefix 로 네임스페이스를 가른다.**
# 착오송금 CSV 는 동결이라 한 파일에 합치지 않는다(§9-7).
QFORM_TABLES = {
    "착오송금 반환 신청": CRAWLER_DIR / "data" / "qform_combos_msdr.csv",
    "예금보험금 안내": CRAWLER_DIR / "data" / "qform_combos_dpin.csv",
}

# 다운로드 시 브라우저에 넘길 MIME (미지정·기타는 octet-stream = 강제 다운로드).
MIME = {
    "pdf": "application/pdf",
    "hwp": "application/x-hwp",
    "hwpx": "application/haansofthwpx",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "zip": "application/zip",
    "other": "application/octet-stream",
}

_cache = None


def _load() -> dict:
    """doc_attachments.json 1회 로드(캐시). 없으면 빈 dict — 앱은 안 깨진다."""
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(DOC_ATTACH_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            _cache = {}
    return _cache


def _key(a: dict):
    """청크 태깅 첨부 <-> doc_attachments 항목 조인 키. enc_real이 파일 단위 고유값."""
    return a.get("enc_real") or a.get("anchor_text") or a.get("name")


# ── 큐폼 후단 필터(B안, §3-1) ──────────────────────────────────────────────
# collect() 결과를 조합 조인으로 좁힌다. 슬롯이 비거나 sub_task=None이면 무손실
# 통과(graceful degradation) — 기존 동작으로 자연 복귀. 검색·생성엔 관여 안 함
# (계약 4필드 불변, hit@k 불변). 첨부 목록만 정밀화한다.
_tag_cache = None
_combo_cache: dict | None = None


def _load_combo_tables() -> dict:
    """bf -> 조합행 리스트. 파일이 없으면 그 업무만 조용히 빠진다(앱은 안 깨진다)."""
    global _combo_cache
    if _combo_cache is None:
        import csv
        tables = {}
        for bf, path in QFORM_TABLES.items():
            try:
                with path.open(encoding="utf-8-sig") as fh:
                    tables[bf] = list(csv.DictReader(fh))
            except (FileNotFoundError, OSError):
                continue
        _combo_cache = tables
    return _combo_cache


def _load_tagging() -> dict:
    """(doc_id, canonical_filename) -> 태깅행. 조인키 = orig_filename 확장자 제거 == canonical_filename."""
    global _tag_cache
    if _tag_cache is None:
        import csv
        idx = {}
        try:
            with TAGGING_PATH.open(encoding="utf-8-sig") as fh:  # BOM 방지
                for r in csv.DictReader(fh):
                    idx[(r["source_doc_id"], r["canonical_filename"])] = r
        except (FileNotFoundError, OSError, KeyError):
            idx = {}
        _tag_cache = idx
    return _tag_cache


def _joins_combo(combo: dict, coords: dict) -> bool:
    """조합행 <-> 첨부 좌표 조인 (T1 AC4와 동일 술어). 공란/'공통'=와일드카드, 다중값 overlap."""
    from qform_state import _toks
    if combo["business_function"].strip() != coords["business_function"].strip():
        return False
    cp, ap = combo["party"].strip(), coords["party"].strip()
    if cp and ap and cp != ap:
        return False
    if combo["sub_task"].strip() != coords["sub_task"].strip():
        return False
    qc, qa = _toks(combo["qualification"]), _toks(coords["qualification"])
    if qc and qa and not (qc & qa):
        return False
    sc, sa = _toks(combo["subject"]), _toks(coords["subject"])
    if sc and sa and "공통" not in sc and "공통" not in sa and not (sc & sa):
        return False
    mc, ma = _toks(combo["method"]), _toks(coords["method"])
    if mc and ma and not (mc & ma):
        return False
    return True


def _qform_narrow(out: list, qform: dict) -> list:
    """collect() 결과를 큐폼 슬롯으로 후단 필터. 스코프 밖/미태깅 첨부는 보존.

    **한 업무의 조합 테이블은 그 업무의 첨부만 좁힌다.** 그리고 사용자의 `sub_task` 가
    그 테이블에 실재하는 값일 때만 발동한다 — 예: `sub_task='반환신청'` 이면 DPIN 테이블은
    아예 관여하지 않고 예금보험금 첨부는 **ver3 와 동일하게 보존**된다. 이 조건이 없으면
    "생존 조합 0개 → 전부 제외"가 되어 타업무 첨부가 조용히 사라진다(오추출 > 미추출, 규칙6).
    """
    if not qform or not qform.get("sub_task"):
        return out                       # sub_task 없으면 좁히지 않음(D2, graceful)
    try:
        from qform_state import survivors, _toks
    except Exception:
        return out                       # 상태 모듈 부재 시 무손실 통과

    want = _toks(qform.get("sub_task"))
    surv_by_bf = {}
    for bf, rows in _load_combo_tables().items():
        have = set()
        for r in rows:
            have |= _toks(r["sub_task"])
        if want & have:                  # 이 테이블이 다루는 용건일 때만 발동
            surv_by_bf[bf] = survivors(qform, rows)

    if not surv_by_bf:
        return out                       # 어느 테이블도 모르는 sub_task → 무손실 통과

    idx = _load_tagging()
    kept = []
    for att in out:
        fname = att.get("orig_filename")
        stem = pathlib.Path(fname).stem if fname else None
        coords = idx.get((att.get("doc_id"), stem))
        bf = coords["business_function"].strip() if coords else None
        if coords is None or bf not in surv_by_bf:
            kept.append(att)             # 미태깅·스코프 밖 → 보존
        elif any(_joins_combo(c, coords) for c in surv_by_bf[bf]):
            kept.append(att)             # 생존 조합에 조인 → 유지
        # else: 좌표는 있으나 어느 생존 조합과도 안 맞음 → 제외
    return kept


def _abs(local_path):
    """crawler/ 기준 상대 local_path -> 절대경로(실존 시). 없으면 None(원문 링크 폴백용)."""
    if not local_path:
        return None
    p = CRAWLER_DIR / local_path
    return str(p) if p.exists() else None


def _fmt(a: dict, doc_id: str, doc_title: str, page_url: str) -> dict:
    lp = a.get("local_path")
    ap = _abs(lp)
    fname = a.get("orig_filename") or (pathlib.Path(lp).name if lp else None)
    ftype = (a.get("file_type") or "").lower()
    return {
        "doc_id": doc_id,
        "doc_title": doc_title,
        "label": a.get("anchor_text") or a.get("name") or fname or "첨부파일",
        "file_type": ftype,
        "doc_kind": a.get("doc_kind"),
        "orig_filename": fname,
        "local_path": lp,
        "abs_path": ap,                 # app.py가 이 경로에서 bytes를 읽어 다운로드 버튼 생성
        "file_size": a.get("file_size"),
        "mime": MIME.get(ftype, MIME["other"]),
        "source_url": a.get("url") or page_url,
        "available": ap is not None,    # False면 로컬 파일 없음 -> 원문 링크로 폴백
    }


def collect(hits, doc_attachments=None, qform=None) -> list:
    """검색 hits -> 반환할 첨부 목록. 근거 문서 등장 순서 보존.

    문서별 규칙: 그 문서 소속 검색 청크 중 하나라도 첨부 태깅이 있으면 -> 태깅된
    파일만(정밀). 태깅이 전무하거나 매칭 실패면 -> 문서 전체 첨부(폴백).
    파일은 (doc_id, orig_filename)로 dedup(재다운로드 _1 중복 방지).

    qform(큐폼 슬롯 dict)이 주어지면 결과를 조합 조인으로 **후단 필터**한다(B안, §3-1).
    기본값 None이면 기존 동작과 완전 동일 — 슬롯이 비면 자연 복귀(graceful degradation).
    """
    da = doc_attachments if doc_attachments is not None else _load()

    order = []
    title_by = {}
    url_by = {}
    tagged_by = {}      # doc_id -> 검색 청크에 태깅된 첨부 키 집합

    for h in hits:
        pid = h.get("parent_doc_id")
        if not pid:
            continue
        if pid not in tagged_by:
            tagged_by[pid] = set()
            order.append(pid)
            title_by[pid] = h.get("page_title", "")
            url_by[pid] = h.get("source_url", "")
        if h.get("has_attachments"):
            for a in h.get("attachments") or []:
                k = _key(a)
                if k:
                    tagged_by[pid].add(k)

    out = []
    seen = set()
    for pid in order:
        entries = da.get(pid) or []
        if not entries:
            continue
        tagged = tagged_by.get(pid) or set()
        picked = [a for a in entries if _key(a) in tagged] if tagged else []
        if not picked:                  # 태깅 없음 or 매칭 실패 -> 문서 단위 폴백
            picked = entries
        for a in picked:
            fname = a.get("orig_filename") or a.get("local_path") or a.get("name")
            dk = (pid, fname)
            if dk in seen:
                continue
            seen.add(dk)
            out.append(_fmt(a, pid, title_by[pid], url_by[pid]))
    if qform:                            # B안 후단 필터 (없으면 기존 동작 그대로)
        out = _qform_narrow(out, qform)
    return out
