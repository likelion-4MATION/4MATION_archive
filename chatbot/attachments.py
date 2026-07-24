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


def collect(hits, doc_attachments=None) -> list:
    """검색 hits -> 반환할 첨부 목록. 근거 문서 등장 순서 보존.

    문서별 규칙: 그 문서 소속 검색 청크 중 하나라도 첨부 태깅이 있으면 -> 태깅된
    파일만(정밀). 태깅이 전무하거나 매칭 실패면 -> 문서 전체 첨부(폴백).
    파일은 (doc_id, orig_filename)로 dedup(재다운로드 _1 중복 방지).
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
    return out
