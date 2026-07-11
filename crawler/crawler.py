"""KDIC 화이트리스트 크롤러 v0 — 코어 로직.

원칙 (P0 로드맵):
- 매니페스트에 있는 URL만 수집한다 (발견형 크롤링 없음 = 화이트리스트 방식)
- 호스트별 세션 선행: 진입점 방문으로 쿠키 확보 후 순회
- robots.txt disallow → 수집 절대 금지, skipped_robots에 기록만
- 오류 페이지 가드: error404 / "오류 | KDIC" 타이틀 감지 → 실패 처리, raw 저장 안 함
- raw HTML은 원본 바이트 그대로 보존, 메타 JSON 별도 저장
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import random
import re
import time
import urllib.robotparser
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

import config

# ── 내부 상태 ────────────────────────────────────────────────
_sessions: dict[str, requests.Session] = {}
_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
_last_request_ts = 0.0


def _polite_wait(multiplier: float = 1.0) -> None:
    global _last_request_ts
    elapsed = time.time() - _last_request_ts
    wait = (config.REQUEST_INTERVAL_SEC * multiplier
            + random.uniform(0.0, config.REQUEST_JITTER_SEC) - elapsed)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.time()


# ── 세션 선행 ────────────────────────────────────────────────
def ensure_session(host: str) -> requests.Session:
    """호스트별 세션 반환. 최초 호출 시 진입점 방문으로 쿠키 확보."""
    if host in _sessions:
        return _sessions[host]
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT, "Accept-Language": "ko"})
    entry = config.ENTRY_POINTS.get(host)
    if entry:
        _polite_wait()
        try:
            r = s.get(entry, timeout=config.TIMEOUT_SEC)
            print(f"[session] {host} 진입 {r.status_code} · cookies={len(s.cookies)}")
        except Exception as e:  # 진입 실패해도 순회는 시도 (결과는 가드가 판정)
            print(f"[session] {host} 진입 실패: {e}")
    _sessions[host] = s
    return s


# ── robots ───────────────────────────────────────────────────
def robots_status(url: str) -> str:
    """'allowed' | 'disallowed' | 'unreachable' — disallowed면 수집 금지."""
    p = urlparse(url)
    # 절대규칙 1 — 정책 차단 우선 적용 (robots.txt Disallow 반영; urllib 실패·UA 스코프 무관)
    for pat in config.POLICY_DISALLOW.get(p.netloc, []):
        if re.search(pat, p.path):
            return "disallowed"
    base = f"{p.scheme}://{p.netloc}"
    rp = _robots_cache.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(base + "/robots.txt")
        try:
            rp.read()
            rp._reachable = True  # type: ignore[attr-defined]
        except Exception:
            print(f"[robots] {base}/robots.txt 읽기 실패 — 보수적으로 진행(기록)")
            rp = urllib.robotparser.RobotFileParser()
            rp.parse("")  # 빈 규칙 = 전체 허용, 단 상태는 unreachable로 기록
            rp._reachable = False  # type: ignore[attr-defined]
        _robots_cache[base] = rp
    if not getattr(rp, "_reachable", True):
        return "unreachable"
    return "allowed" if rp.can_fetch(config.USER_AGENT, url) else "disallowed"


# ── 가드 ─────────────────────────────────────────────────────
def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def looks_like_error_page(final_url: str, html: str, title: str) -> bool:
    if any(m in final_url for m in config.ERROR_URL_MARKERS):
        return True
    if any(m in title for m in config.ERROR_TITLE_MARKERS):
        return True
    return any(m in html for m in config.ERROR_BODY_MARKERS)


def looks_like_waiting_room(text: str) -> bool:
    """대기열 문구가 있고 '본문이 비정상적으로 짧을 때만' 대기열로 판정."""
    if len(text) > config.WAITING_ROOM_MAX_TEXT_LEN:
        return False
    return any(m in text for m in config.WAITING_ROOM_MARKERS)


# ── 메타 추출 ────────────────────────────────────────────────
def extract_title(soup: BeautifulSoup) -> str:
    return soup.title.get_text(strip=True) if soup.title else ""


def extract_breadcrumb(soup: BeautifulSoup) -> list[str]:
    """KDIC 계열 브레드크럼 best-effort 추출 (location/breadcrumb 계열 셀렉터)."""
    for sel in ("[class*=location]", "[id*=location]",
                "[class*=breadcrumb]", "ol.breadcrumb", "nav[aria-label*=현재]"):
        node = soup.select_one(sel)
        if node:
            parts = [t.get_text(strip=True) for t in node.find_all(["a", "li", "span", "strong"])]
            parts = [p for p in parts if p and len(p) < 40]
            # 중복 제거(순서 유지)
            seen, out = set(), []
            for p in parts:
                if p not in seen:
                    seen.add(p)
                    out.append(p)
            if out:
                return out
    return []


def doc_id_from_url(url: str) -> str:
    p = urlparse(url)
    site = "www" if p.netloc.startswith("www.") else p.netloc.split(".")[0]
    slug = p.path.strip("/").replace("/", "-")
    slug = re.sub(r"\.do$", "", slug) or "root"
    if p.query:  # variant 분기 페이지(FAQ판/안내판 등) 쿼리 구분 보존
        slug += "-" + hashlib.sha256(p.query.encode()).hexdigest()[:8]
    return f"kdic-{site}-{slug}"


# ── 수집 본체 ────────────────────────────────────────────────
def fetch_one(row: dict, out_root: pathlib.Path) -> dict:
    """매니페스트 1행 수집. 결과 dict(status 포함) 반환.

    status: ok | robots_blocked | external_host | error_page |
            waiting_room | http_error | exception
    """
    url = row["url"].strip()
    host = urlparse(url).netloc
    result = {"url": url, "doc_id": doc_id_from_url(url)}

    if not host.endswith(config.ALLOWED_HOST_SUFFIX):
        result["status"] = "external_host"  # 외부 링크는 link_registry 몫, 수집 안 함
        return result

    rs = robots_status(url)
    result["robots_status"] = rs
    if rs == "disallowed":
        result["status"] = "robots_blocked"  # 절대 수집 금지 — 기록만
        return result

    s = ensure_session(host)
    last_err = None
    for attempt in range(config.MAX_RETRY + 1):
        _polite_wait(multiplier=2.0 if attempt else 1.0)
        try:
            r = s.get(url, timeout=config.TIMEOUT_SEC)
            if r.status_code >= 500:
                last_err = f"HTTP {r.status_code}"
                continue
            raw: bytes = r.content  # 원본 바이트 보존
            r.encoding = r.apparent_encoding or "utf-8"
            html = r.text
            soup = BeautifulSoup(html, "lxml")
            title = extract_title(soup)
            text = visible_text(html)

            if looks_like_waiting_room(text):
                last_err = "waiting_room"
                print(f"[wait] 대기열 감지 → 간격 2배 재시도: {url}")
                continue
            if r.status_code == 404 or looks_like_error_page(str(r.url), html, title):
                result.update(status="error_page", http_status=r.status_code, title=title)
                return result  # 오수집 차단 — raw 저장 안 함

            # 저장
            raw_dir = out_root / config.RAW_DIR
            meta_dir = out_root / config.META_DIR
            raw_dir.mkdir(parents=True, exist_ok=True)
            meta_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / f"{result['doc_id']}.html").write_bytes(raw)

            meta = {
                "doc_id": result["doc_id"],
                "source_url": url,
                "final_url": str(r.url),
                "business_function": row.get("business_function", ""),
                "sub_category": row.get("sub_category", ""),
                "page_type": row.get("page_type", ""),
                "coverage": row.get("coverage", ""),      # 전체 / 안내부
                "variant": row.get("variant", ""),        # FAQ판/안내판 분기
                "robots_status": rs,
                "http_status": r.status_code,
                "encoding": r.encoding,
                "title": title,
                "breadcrumb": extract_breadcrumb(soup),
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                # 재실행 재현성 판정용 — CSRF/세션값 변동 흡수를 위해 보이는 텍스트 기준
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "text_len": len(text),
            }
            (meta_dir / f"{result['doc_id']}.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            result.update(status="ok", title=title, http_status=r.status_code,
                          text_len=len(text))
            return result
        except requests.RequestException as e:
            last_err = str(e)
    result.update(status="waiting_room" if last_err == "waiting_room" else "http_error",
                  error=str(last_err))
    return result
