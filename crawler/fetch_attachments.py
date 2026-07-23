"""첨부문서 자체 파일스토리지 구축 — onclick_dynamic 첨부 실다운로드.

parser.py가 각 onclick_dynamic 첨부에 enc_real/enc_temp(다운로드 토큰 원본)를
이미 실어두므로, 여기서는 raw HTML을 다시 훑을 필요 없이 data/parsed/*.json을
그대로 읽어 다운로드만 수행한다. 토큰은 세션 종속이 아니라 페이지 렌더마다
고정값(실사 확인)이라 그대로 되돌려 보내면 파일을 받을 수 있다:

  www.kdic.or.kr  → POST /cm/file/downloadFile.do
  fins.kdic.or.kr → POST /api/cm/file/downloadFile.do
  body: {"encAtchFilePathNm": enc_real, "encOrgnlFileNm": enc_temp}  (JSON 그대로)

성공 시 Content-Disposition: attachment; filename="...(percent-encoded)" 로
실제 원본 파일명이 오고 바이너리 바디가 파일 그 자체.

출력:
  data/files/{doc_id}/{원본파일명}
  data/files/manifest.json — doc_id별 첨부 메타(enc_real/enc_temp 포함) + 로컬
  저장 경로 + sha256. link_files.py가 이 (doc_id, enc_real, enc_temp)로
  data/parsed/*.json의 attachments와 정확히 1:1 조인한다.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import random
import re
import sys
import time
from urllib.parse import unquote

import requests

import config

PARSED_DIR = pathlib.Path("data/parsed")
OUT_DIR = pathlib.Path("data/files")
MANIFEST_PATH = OUT_DIR / "manifest.json"

DOWNLOAD_ENDPOINT = {
    "www": ("www.kdic.or.kr", "/cm/file/downloadFile.do"),
    "fins": ("fins.kdic.or.kr", "/api/cm/file/downloadFile.do"),
}

_last_request_ts = 0.0


def _polite_wait() -> None:
    global _last_request_ts
    elapsed = time.time() - _last_request_ts
    wait = (config.REQUEST_INTERVAL_SEC
            + random.uniform(0.0, config.REQUEST_JITTER_SEC) - elapsed)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.time()


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return name or "file"


def parse_content_disposition_filename(header_value: str) -> str | None:
    m = re.search(r'filename\*?=([^;]+)', header_value or "")
    if not m:
        return None
    raw = m.group(1).strip().strip('"').strip("'")
    raw = re.sub(r"^UTF-8''", "", raw, flags=re.I)
    try:
        return unquote(raw)
    except Exception:
        return raw


def download_one(session: requests.Session, site: str, base_url: str,
                  enc_real: str, enc_temp: str) -> tuple[bytes | None, str | None, str | None]:
    """반환: (바이너리 or None, 원본파일명 or None, 에러메시지 or None)"""
    host, path = DOWNLOAD_ENDPOINT[site]
    url = f"https://{host}{path}"
    body = {"encAtchFilePathNm": enc_real, "encOrgnlFileNm": enc_temp}
    _polite_wait()
    try:
        r = session.post(
            url, json=body, timeout=config.TIMEOUT_SEC,
            headers={"Referer": base_url, "Content-Type": "application/json; charset=utf-8"},
        )
    except Exception as e:
        return None, None, f"요청 실패: {e}"

    disposition = r.headers.get("Content-Disposition", "")
    if r.status_code == 200 and "attachment" in disposition:
        filename = parse_content_disposition_filename(disposition) or "file.bin"
        return r.content, filename, None
    return None, None, f"HTTP {r.status_code}, Content-Type={r.headers.get('Content-Type')}, len={len(r.content)}"


def main() -> None:
    docs = []
    for p in sorted(PARSED_DIR.glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("has_attachments"):
            docs.append(rec)

    if not docs:
        sys.exit("첨부 있는 문서 없음")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sessions: dict[str, requests.Session] = {}
    manifest = []
    ok_count = fail_count = 0
    # 같은 문서가 페이지 내 여러 곳(예: 본인/대리인 탭)에 동일 토큰으로 중복
    # 노출되는 경우가 실사에서 확인됨 — doc_id당 토큰 캐시로 재요청 방지.
    token_cache: dict[tuple, dict] = {}  # (doc_id, enc_real, enc_temp) -> 결과 필드(status 등)

    for rec in docs:
        doc_id = rec["doc_id"]
        site = rec.get("site", "")
        base_url = rec.get("final_url") or rec.get("source_url") or ""
        atts = [a for a in rec.get("attachments", []) if a.get("link_type") == "onclick_dynamic"]
        if not atts:
            continue  # direct 첨부만 있는 문서 — 이미 절대 URL 확보돼 있어 다운로드 불필요
        if site not in DOWNLOAD_ENDPOINT:
            print(f"[skip] {doc_id}: 알 수 없는 site={site!r}")
            continue

        host = DOWNLOAD_ENDPOINT[site][0]
        if host not in sessions:
            s = requests.Session()
            s.headers.update({"User-Agent": config.USER_AGENT, "Accept-Language": "ko"})
            sessions[host] = s
        session = sessions[host]

        doc_dir = OUT_DIR / doc_id
        print(f"=== {doc_id} ({len(atts)}건) ===")
        for att in atts:
            entry = {
                "doc_id": doc_id,
                "site": site,
                "source_page_url": base_url,
                "name": att["name"],
                "doc_kind": att["doc_kind"],
                "file_type": att["file_type"],
                "anchor_text": att["anchor_text"],
                "enc_real": att["enc_real"],
                "enc_temp": att["enc_temp"],
            }

            cache_key = (doc_id, att["enc_real"], att["enc_temp"])
            cached = token_cache.get(cache_key)
            if cached is not None:
                entry.update(cached)
                if entry["status"] == "ok":
                    print(f"  [ok:재사용] {entry['orig_filename']} -> {entry['stored_path']}")
                manifest.append(entry)
                continue

            content, orig_name, err = download_one(
                session, site, base_url, att["enc_real"], att["enc_temp"])

            if content is None:
                result = {"status": "failed", "error": err}
                entry.update(result)
                print(f"  [fail] {att['name'][:40]!r} — {err}")
                fail_count += 1
            else:
                doc_dir.mkdir(parents=True, exist_ok=True)
                safe_name = sanitize_filename(orig_name)
                stored_path = doc_dir / safe_name
                n = 1
                while stored_path.exists():
                    stem, dot, ext = safe_name.rpartition(".")
                    stored_path = doc_dir / (f"{stem}_{n}.{ext}" if dot else f"{safe_name}_{n}")
                    n += 1
                stored_path.write_bytes(content)
                ext = orig_name.rsplit(".", 1)[-1].lower() if "." in orig_name else att["file_type"]
                result = {
                    "status": "ok",
                    "orig_filename": orig_name,
                    "file_type": ext,
                    "stored_path": str(stored_path.as_posix()),
                    "size_bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
                entry.update(result)
                print(f"  [ok] {orig_name} ({len(content):,} bytes) -> {stored_path}")
                ok_count += 1

            token_cache[cache_key] = result
            manifest.append(entry)

    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n완료: 성공 {ok_count}건 · 실패 {fail_count}건 → {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
