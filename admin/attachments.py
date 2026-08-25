# -*- coding: utf-8 -*-
"""첨부문서·링크 관리 — 관리자가 표시명을 고치고 파일·링크를 직접 넣는다.

원본 `crawler/data/doc_attachments.json` 은 **크롤링 산출물이라 건드리지 않는다.**
관리자 편집분은 `data/attachments.json` 에 오버레이로 쌓고, 조회 시 합쳐서 돌려준다.
재크롤링을 해도 관리자가 고친 표시명이 살아남는 구조다(`link_registry` 와 같은 패턴).

  overlay = {
    "labels":   {"<doc_id>::<key>": "고친 표시명"},
    "hidden":   ["<doc_id>::<key>", ...],           숨김 처리(삭제 대신)
    "replace":  {"<doc_id>::<key>": {filename, note, at}},   구 파일 → 새 파일 교체
    "extra":    [ {id, doc_id, label, kind, url|filename, note, ...} ],
    "links":    [ {id, title, url, phone, org, keywords, business, note} ],
  }

원본 첨부 **파일 자체**는 `crawler/data/files/{doc_id}/{원본파일명}` 에 이미 받아져 있고
`crawler/data/files/manifest.json` 이 `(doc_id, enc_real, enc_temp)` 로 조인 키를 준다
(`fetch_attachments.py` 산출물). 콘솔은 그 파일을 **읽어서 내려주기만** 한다 — 지우거나
덮어쓰지 않는다. 교체는 새 파일을 `data/uploads/` 에 올리고 오버레이에 연결하는 방식이다.

`links` 는 OOS 계획서의 **안내 사전(referral registry)** 이다. 타기관 안내(`link` route)가
쓰는 연락처를 관리자가 직접 관리한다 — 코드에 하드코딩하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone

import settings

BASE = pathlib.Path(__file__).resolve().parent
STORE = BASE / "data" / "attachments.json"
UPLOAD_DIR = BASE / "data" / "uploads"
CRAWLER = settings.REPO / "crawler"
SRC = CRAWLER / "data" / "doc_attachments.json"
FILES_DIR = CRAWLER / "data" / "files"
MANIFEST = FILES_DIR / "manifest.json"

_LOCK = threading.Lock()
_EMPTY = {"labels": {}, "hidden": [], "replace": {}, "extra": [], "links": []}

ALLOWED_EXT = {".pdf", ".hwp", ".hwpx", ".docx", ".doc", ".xlsx", ".xls",
               ".csv", ".txt", ".png", ".jpg", ".jpeg", ".zip"}
MAX_BYTES = 30 * 1024 * 1024

_URL_OK = re.compile(r"^https?://[\w.-]+(?::\d+)?(?:/[^\s]*)?$", re.I)
_PHONE_OK = re.compile(r"^[\d\-()\s~,]+$")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _load() -> dict:
    if not STORE.exists():
        return json.loads(json.dumps(_EMPTY))
    try:
        d = json.loads(STORE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(_EMPTY))
    for k, v in _EMPTY.items():
        d.setdefault(k, json.loads(json.dumps(v)))
    return d


def _save(d: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STORE)


# ── 표시명 정제 ─────────────────────────────────────────────────────────
_DIRTY = re.compile(r"[\n|]|STEP\s*\d|※")


def is_dirty(label: str) -> bool:
    """표 파싱 잔여물인가. 사용자 화면에 그대로 나가면 깨져 보이는 값."""
    if not label:
        return True
    return bool(_DIRTY.search(label)) or len(label) > 40


def suggest(label: str) -> str:
    """정제 제안 — 첫 줄만, 파이프 뒤 꼬리 제거, 공백 정리. 판단은 사람이 한다."""
    s = (label or "").split("\n")[0]
    s = s.split("|")[-1] if "|" in s else s
    s = re.sub(r"※.*$", "", s)
    s = re.sub(r"\s+", " ", s).strip(" ·-—")
    return s[:40].strip()


def _key(doc_id: str, item: dict) -> str:
    raw = f"{item.get('anchor_text')}|{item.get('name')}|{item.get('file_type')}"
    return f"{doc_id}::{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:8]}"


# ── 원본 파일 (fetch_attachments.py 산출물) ─────────────────────────────
def _manifest() -> dict:
    """`key` → 다운로드된 원본 파일 메타. 없으면 빈 dict(기능만 꺼진다)."""
    if not MANIFEST.exists():
        return {}
    try:
        rows = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out = {}
    for r in rows:
        if r.get("status") != "ok" or not r.get("stored_path"):
            continue
        out.setdefault(_key(r.get("doc_id", ""), r), r)      # 중복은 먼저 것 유지
    return out


def source_path(key: str) -> pathlib.Path | None:
    """크롤링으로 받아 둔 원본 파일 경로. 저장소 밖은 절대 내주지 않는다."""
    r = _manifest().get(key)
    if not r:
        return None
    p = (CRAWLER / r["stored_path"]).resolve()
    root = FILES_DIR.resolve()
    if not p.exists() or not (root == p or root in p.parents):
        return None
    return p


# ── 조회 ────────────────────────────────────────────────────────────────
def list_all() -> dict:
    """원본 + 관리자 오버레이를 합친 목록."""
    ov = _load()
    src = {}
    if SRC.exists():
        try:
            src = json.loads(SRC.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            src = {}
    man = _manifest()

    docs, n_dirty, n_edited = [], 0, 0
    for doc_id, items in src.items():
        rows = []
        seen = set()
        for it in items:
            k = _key(doc_id, it)
            if k in seen:
                continue
            seen.add(k)
            orig = it.get("anchor_text") or it.get("name") or ""
            edited = ov["labels"].get(k)
            dirty = is_dirty(orig)
            n_dirty += 1 if (dirty and not edited) else 0
            n_edited += 1 if edited else 0
            mf = man.get(k)
            rep = ov["replace"].get(k)
            rows.append({
                "key": k, "doc_id": doc_id, "source": "crawl",
                "label": edited or orig, "original": orig,
                "edited": bool(edited), "dirty": dirty and not edited,
                "suggestion": suggest(orig) if dirty else None,
                "file_type": (pathlib.Path(rep["filename"]).suffix.lstrip(".").lower()
                              if rep else it.get("file_type")),
                "page_url": it.get("url"),                 # 원문 페이지(파일 주소가 아니다)
                "hidden": k in ov["hidden"],
                # 원본 파일 — 크롤러가 이미 받아 둔 것
                "has_file": bool(mf),
                "orig_filename": (mf or {}).get("orig_filename"),
                "size_bytes": (mf or {}).get("size_bytes"),
                "sha256": ((mf or {}).get("sha256") or "")[:12],
                "download": f"/api/attachments/source/{k}" if mf else None,
                # 교체분
                "replaced": bool(rep),
                "replace_filename": (rep or {}).get("filename"),
                "replace_note": (rep or {}).get("note"),
                "replace_at": (rep or {}).get("at"),
                "replace_download": (f"/api/attachments/file/{rep['filename']}"
                                     if rep else None),
            })
        for e in ov["extra"]:
            if e.get("doc_id") == doc_id:
                rows.append({**e, "source": "admin", "dirty": False, "edited": True,
                             "download": e.get("url"), "has_file": bool(e.get("filename"))})
        docs.append({"doc_id": doc_id, "items": rows, "count": len(rows)})

    orphan = [{**e, "source": "admin", "dirty": False, "edited": True,
               "download": e.get("url"), "has_file": bool(e.get("filename"))}
              for e in ov["extra"] if e.get("doc_id") not in src]
    if orphan:
        docs.append({"doc_id": "(관리자 추가)", "items": orphan, "count": len(orphan)})

    return {"docs": sorted(docs, key=lambda d: -d["count"]),
            "links": ov["links"],
            "stats": {"docs": len(docs),
                      "items": sum(d["count"] for d in docs),
                      "dirty": n_dirty, "edited": n_edited,
                      "extra": len(ov["extra"]), "links": len(ov["links"]),
                      "hidden": len(ov["hidden"]), "replaced": len(ov["replace"]),
                      "files": len(man)}}


# ── 편집 ────────────────────────────────────────────────────────────────
def set_label(key: str, label: str) -> dict:
    label = (label or "").strip()
    if not label:
        return {"ok": False, "errors": ["표시명을 입력하세요."]}
    if len(label) > 40:
        return {"ok": False, "errors": ["표시명은 40자 이내입니다."]}
    if is_dirty(label):
        return {"ok": False, "errors": ["줄바꿈·표 기호(|)·※ 는 표시명에 넣을 수 없습니다."]}
    with _LOCK:
        d = _load()
        d["labels"][key] = label
        _save(d)
    return {"ok": True}


def reset_label(key: str) -> dict:
    with _LOCK:
        d = _load()
        d["labels"].pop(key, None)
        _save(d)
    return {"ok": True}


def set_hidden(key: str, hidden: bool) -> dict:
    with _LOCK:
        d = _load()
        s = set(d["hidden"])
        s.add(key) if hidden else s.discard(key)
        d["hidden"] = sorted(s)
        _save(d)
    return {"ok": True}


def set_replace(key: str, filename: str, note: str = "") -> dict:
    """구 문서를 새 파일로 **교체**한다.

    원본은 지우지 않는다 — `crawler/data/files/` 는 크롤링 산출물이고 재크롤링으로 다시
    받아지는 자산이다. 오버레이에 '이 자리에는 이 파일을 쓴다'만 기록하고, 되돌리기는
    그 기록을 지우면 끝난다.
    """
    if not filename or not upload_path(filename):
        return {"ok": False, "errors": ["새 파일을 먼저 업로드하세요."]}
    with _LOCK:
        d = _load()
        old = d["replace"].get(key)
        d["replace"][key] = {"filename": filename,
                             "note": (note or "").strip()[:100], "at": _now()}
        _save(d)
    if old and old.get("filename") != filename:              # 직전 교체본 정리
        (UPLOAD_DIR / old["filename"]).unlink(missing_ok=True)
    return {"ok": True, "replace": d["replace"][key]}


def clear_replace(key: str) -> dict:
    """교체를 취소하고 크롤링 원본으로 되돌린다."""
    with _LOCK:
        d = _load()
        gone = d["replace"].pop(key, None)
        _save(d)
    if gone and gone.get("filename"):
        (UPLOAD_DIR / gone["filename"]).unlink(missing_ok=True)
    return {"ok": True, "restored": bool(gone)}


def resolved(doc_id: str) -> list[dict]:
    """**챗봇이 부를 함수** — 이 문서에서 사용자에게 실제로 안내할 첨부 목록.

    숨김은 빠지고, 교체된 항목은 새 파일을 가리키고, 관리자 추가분이 뒤에 붙는다.
    `chunk.match_attachments()` 가 만든 청크 단위 첨부 대신 문서 단위 안전망으로 쓴다.
    """
    data = list_all()
    doc = next((d for d in data["docs"] if d["doc_id"] == doc_id), None)
    out = []
    for it in (doc or {}).get("items", []):
        if it.get("hidden"):
            continue
        out.append({"label": it["label"], "file_type": it.get("file_type"),
                    "url": it.get("replace_download") or it.get("download")
                           or it.get("page_url"),
                    "replaced": bool(it.get("replaced")),
                    "source": it.get("source")})
    return out


def bulk_clean() -> dict:
    """정제 필요 항목에 제안값을 일괄 적용. 되돌리기는 항목별 초기화로."""
    data = list_all()
    applied = []
    with _LOCK:
        d = _load()
        for doc in data["docs"]:
            for it in doc["items"]:
                if it.get("dirty") and it.get("suggestion"):
                    d["labels"][it["key"]] = it["suggestion"]
                    applied.append({"key": it["key"], "label": it["suggestion"]})
        _save(d)
    return {"ok": True, "applied": applied, "count": len(applied)}


# ── 관리자 추가 첨부 (파일 업로드 · 외부 링크) ───────────────────────────
def add_extra(doc_id: str, label: str, kind: str, url: str = "",
              filename: str = "", note: str = "") -> dict:
    err = []
    if not (label or "").strip():
        err.append("표시명을 입력하세요.")
    if kind not in ("file", "url"):
        err.append("종류는 파일 또는 링크여야 합니다.")
    if kind == "url" and not _URL_OK.match((url or "").strip()):
        err.append("링크는 http:// 또는 https:// 로 시작하는 주소여야 합니다.")
    if kind == "file" and not filename:
        err.append("파일을 먼저 업로드하세요.")
    if err:
        return {"ok": False, "errors": err}
    row = {"id": uuid.uuid4().hex[:10], "doc_id": doc_id or "(관리자 추가)",
           "label": label.strip()[:40], "kind": kind,
           "url": url.strip() if kind == "url" else f"/api/attachments/file/{filename}",
           "filename": filename if kind == "file" else "",
           "file_type": (pathlib.Path(filename).suffix.lstrip(".").lower()
                         if filename else "link"),
           "note": (note or "").strip()[:100], "updated_at": _now()}
    with _LOCK:
        d = _load()
        d["extra"].append(row)
        _save(d)
    return {"ok": True, "item": row}


def delete_extra(item_id: str) -> bool:
    with _LOCK:
        d = _load()
        before = len(d["extra"])
        keep = [e for e in d["extra"] if e["id"] != item_id]
        gone = [e for e in d["extra"] if e["id"] == item_id]
        d["extra"] = keep
        _save(d)
    for e in gone:                                  # 업로드 파일도 같이 정리
        if e.get("filename"):
            (UPLOAD_DIR / e["filename"]).unlink(missing_ok=True)
    return before != len(keep)


def save_upload(filename: str, data: bytes) -> dict:
    ext = pathlib.Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return {"ok": False, "errors": [f"허용되지 않는 형식입니다: {ext or '(확장자 없음)'}. "
                                        f"가능: {', '.join(sorted(ALLOWED_EXT))}"]}
    if len(data) > MAX_BYTES:
        return {"ok": False, "errors": [f"파일이 너무 큽니다 ({len(data)/1024/1024:.1f}MB). "
                                        f"최대 {MAX_BYTES//1024//1024}MB."]}
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w가-힣.\-]", "_", pathlib.Path(filename).name)[:80]
    stored = f"{uuid.uuid4().hex[:8]}_{safe}"
    (UPLOAD_DIR / stored).write_bytes(data)
    return {"ok": True, "filename": stored, "size": len(data)}


def upload_path(name: str) -> pathlib.Path | None:
    p = (UPLOAD_DIR / name).resolve()
    return p if p.exists() and UPLOAD_DIR.resolve() in p.parents else None


# ── 안내 사전 (타기관 링크) ─────────────────────────────────────────────
def upsert_link(row: dict) -> dict:
    err = []
    title = (row.get("title") or "").strip()
    url = (row.get("url") or "").strip()
    phone = (row.get("phone") or "").strip()
    if not title:
        err.append("기관·제도 이름을 입력하세요.")
    if not url and not phone:
        err.append("주소나 전화번호 중 하나는 반드시 필요합니다.")
    if url and not _URL_OK.match(url):
        err.append("주소는 http:// 또는 https:// 로 시작해야 합니다.")
    if phone and not _PHONE_OK.match(phone):
        err.append("전화번호에 숫자·하이픈 외 문자가 있습니다.")
    if not row.get("keywords"):
        err.append("발동 키워드를 최소 1개 입력하세요.")
    if err:
        return {"ok": False, "errors": err}
    with _LOCK:
        d = _load()
        row = {**row, "title": title, "url": url, "phone": phone,
               "keywords": [k.strip() for k in row.get("keywords", []) if k.strip()],
               "business": row.get("business") or [],
               "note": (row.get("note") or "").strip()[:120],
               "updated_at": _now()}
        rid = row.get("id")
        if rid and any(x["id"] == rid for x in d["links"]):
            d["links"] = [row if x["id"] == rid else x for x in d["links"]]
        else:
            row["id"] = rid or uuid.uuid4().hex[:10]
            d["links"].append(row)
        _save(d)
    return {"ok": True, "link": row}


def delete_link(link_id: str) -> bool:
    with _LOCK:
        d = _load()
        before = len(d["links"])
        d["links"] = [x for x in d["links"] if x["id"] != link_id]
        _save(d)
    return before != len(d["links"])


def match_links(query: str, business: str | None = None) -> list[dict]:
    """`link` route 가 쓰는 조회 — 발동 키워드가 걸린 안내처만."""
    qn = (query or "").replace(" ", "")
    out = []
    for r in _load()["links"]:
        if business and r.get("business") and business not in r["business"]:
            continue
        if any(k.replace(" ", "") in qn for k in r.get("keywords", [])):
            out.append(r)
    return out


# ── 초기 안내 사전 시드 — 전부 크롤링 원문에 실재하는 값 ────────────────
SEED_LINKS = [
    {"id": "sl-ccrs", "title": "신용회복위원회 (워크아웃)", "org": "신용회복위원회",
     "url": "https://www.ccrs.or.kr", "phone": "1600-5500",
     "keywords": ["워크아웃", "신용회복", "채무조정 신청"],
     "business": ["채무조정 안내"],
     "note": "원문: '개별 금융회사에 신청하는 것이 아닙니다'"},
    {"id": "sl-sleep", "title": "휴면계좌 통합조회", "org": "전국은행연합회",
     "url": "https://www.sleepmoney.or.kr", "phone": "",
     "keywords": ["휴면계좌", "휴면예금", "잠자는 돈"],
     "business": ["예금보험금 안내", "고객 미수령금 신청"],
     "note": "정상 영업 중인 은행·보험·우체국 휴면계좌"},
    {"id": "sl-voice", "title": "보이스피싱 피해구제", "org": "송금 은행 / 경찰",
     "url": "", "phone": "112",
     "keywords": ["보이스피싱", "전기통신금융사기", "사기 이체"],
     "business": ["착오송금 반환 신청"],
     "note": "원문: 은행에 피해사실 신고 → 수취인계좌 지급정지"},
    {"id": "sl-court", "title": "개인회생·파산 (법원)", "org": "서울회생법원",
     "url": "https://slb.scourt.go.kr", "phone": "",
     "keywords": ["개인회생", "파산", "면책"],
     "business": ["채무조정 안내"],
     "note": "예보 페이지는 안내만 — 신청은 법원"},
    {"id": "sl-kdic", "title": "예금보험공사 고객상담센터", "org": "예금보험공사",
     "url": "", "phone": "1588-0037",
     "keywords": ["상담", "문의", "전화"],
     "business": [],
     "note": "파산재단 채무자 02-758-1000 · ㈜케이알앤씨 1899-0057"},
]


def ensure_seed() -> None:
    """링크가 하나도 없을 때만 시드를 넣는다 — 관리자가 지운 항목을 되살리지 않는다."""
    d = _load()
    if not d["links"] and not STORE.exists():
        d["links"] = [dict(x) for x in SEED_LINKS]
        _save(d)
