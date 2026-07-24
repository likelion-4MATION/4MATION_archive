"""파서 v0 — 결정론적 BeautifulSoup 본문 추출. LLM 미사용 (동일 입력=동일 출력).

입력: run1/data/raw/*.html + data/meta/*.json (D0 산출)
출력: data/parsed/{doc_id}.json (doc_id · text · attachments · 메타 상속)

설계 근거(03 문서 + D1 DOM 정찰):
- KDIC 페이지는 텍스트의 90%+가 GNB 네비 노이즈 → 본문 컨테이너 `.contents`로 좁혀 잡는다.
  (#container는 브레드크럼/타이틀 포함, `.contents`가 실제 본문 — 32건 전부 1개씩 존재 확인)
- `.contents` 내부 크롬/기능부 제거: floatTop(글자크기·언어) · floatBottom(챗봇·상단이동)
  · btnBottomArea(조회/신청 바로가기 버튼) · script/style · form/input/button.
- 표는 값 유실 없이 행 텍스트("cell | cell")로 직렬화. 구조 미화(markdown)는 P2 몫이라 안 함.
- 브레드크럼은 `.location` 최상위 li 직계자식의 첫 링크만 (드롭다운 형제메뉴 무시).
- coverage=안내부 페이지(상속인 금융거래조회)는 조회 기능부(btnBottomArea) 제거로 안내부만 남김.

첨부(PDF/HWP 등) 처리 — 정적 크롤링 범위 내에서 가능한 만큼 태깅:
  실사 결과 두 가지 패턴이 섞여 있음.
  1) www.kdic.or.kr 자료실/보도자료류: <a href="...pdf/hwp">  → 절대 URL을 그대로 확보 가능
     (link_type="direct", url 채워짐).
  2) fins.kdic.or.kr 포털(구비서류안내 등): <button class="btnIco icoHwp/icoPdf"
     onclick="gfn_downloadFile(encId, encName)">  → href가 없다. [meta-doc 후속]
     실사 결과 encId/encName은 세션 종속이 아니라 페이지 렌더마다 고정된 토큰이고,
     그대로 POST {www.kdic.or.kr}/cm/file/downloadFile.do 또는
     {fins.kdic.or.kr}/api/cm/file/downloadFile.do (도메인별로 경로가 다름) 에
     JSON 바디로 되돌려 보내면 실파일을 받을 수 있음이 확인됨(fetch_attachments.py).
     그래서 이 토큰(enc_real/enc_temp)을 attachments에 그대로 보존한다 — parser.py는
     여전히 raw HTML만 읽고 네트워크 요청을 하지 않으므로 결정론성은 안 깨진다.
     실다운로드·로컬 저장은 fetch_attachments.py, parsed 첨부와 로컬 파일 연결은
     link_files.py가 각각 별도 단계로 담당한다(자세한 이유: 대신 하드코딩된 링크가
     아니라 doc_id+토큰으로 정확히 1:1 매칭하기 위함 — anchor_text 같은 표시 텍스트
     기반 매칭은 동일 문구가 반복되는 페이지에서 모호해질 수 있음).
  doc_kind는 첨부가 속한 표의 헤더 텍스트(예: '관련 서식')를 규칙 매칭해서 부여.
  표 밖에 있는 느슨한 첨부 링크는 doc_kind="기타"로 처리.
"""
from __future__ import annotations

import glob
import hashlib
import json
import pathlib
import re
import sys
from copy import deepcopy
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString

RAW_DIR = "data/raw"
META_DIR = "data/meta"
OUT_DIR = "data/parsed"
CONTENT_SELECTOR = ".contents"

# .contents 내부에서 제거할 크롬/기능부 (결정론적)
# 주의: attachments 추출은 이 제거보다 먼저 수행해야 함 (button 태그가 여기서 날아감)
NOISE_SELECTORS = [
    "script", "style", "noscript",
    ".floatTop", ".floatBottom", ".btnBottomArea",
    "form", "input", "button",
]

# 안내부 페이지 — 조회/신청 기능부 제거, coverage=안내부.
# 상속인 조회는 ASSIGNMENT_D1 T1 지정, 부채증명원은 07-13 xlsx '포함(안내부)' 판정 편입분.
COVERAGE_ANNAE = {
    "kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn",      # 상속인 금융거래조회
    "kdic-www-sp-sprtfund-SprtFndDebtDlngAplyGudn-selectScrn",   # 부채증명원/금융거래정보신청
}

ATTACH_RE = re.compile(r"\.(hwp|hwpx|pdf|xlsx?|docx?|pptx?|zip|txt|csv)(\?|$)", re.I)

# onclick="gfn_downloadFile('encId', 'encName')" 에서 두 토큰을 그대로 추출.
# fetch_attachments.py가 실다운로드에 그대로 재사용(도메인별 엔드포인트로 POST).
ONCLICK_RE = re.compile(
    r"gfn_downloadFile\(\s*'((?:[^'\\]|\\.)*)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\)"
)

# 표 헤더 텍스트 → doc_kind 규칙 매핑 (우선순위 순서대로 첫 매치 채택)
DOC_KIND_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"서식|양식"), "양식"),
    (re.compile(r"안내|자료|첨부"), "안내자료"),
]

# button/a class="btnIco icoXxx" → file_type 매핑에 쓰는 패턴
ICO_CLASS_RE = re.compile(r"^ico([A-Za-z]+)$")


def collapse(s: str) -> str:
    return re.sub(r"[ \t ]+", " ", s).strip()


def infer_doc_kind(header_text: str) -> str:
    if not header_text:
        return "기타"
    for pattern, kind in DOC_KIND_RULES:
        if pattern.search(header_text):
            return kind
    return "기타"


def get_table_headers(table) -> list[str]:
    """표 헤더 텍스트 목록 (컬럼 인덱스 → doc_kind 추론용)."""
    header_row = None
    thead = table.find("thead")
    if thead:
        header_row = thead.find("tr")
    if header_row is None:
        first_tr = table.find("tr")
        if first_tr and first_tr.find_all("th"):
            header_row = first_tr
    if header_row is None:
        return []
    return [collapse(th.get_text(" ")) for th in header_row.find_all(["th", "td"])]


def _row_line(tr) -> str:
    """표 한 행을 "cell | cell" 한 줄로 직렬화 (table_to_lines·_anchor_text 공용)."""
    cells = [collapse(c.get_text(" ")) for c in tr.find_all(["th", "td"])]
    cells = [c for c in cells if c]
    return " | ".join(cells)


def table_to_lines(table) -> str:
    """표를 값 유실 없이 행 텍스트로 직렬화 (미화 없음)."""
    lines = []
    cap = table.find("caption")
    if cap:
        t = collapse(cap.get_text(" "))
        if t:
            lines.append(t)
    for tr in table.find_all("tr"):
        line = _row_line(tr)
        if line:
            lines.append(line)
    return "\n".join(lines)


def extract_breadcrumb(soup) -> list[str]:
    """`.location` 최상위 li 직계자식의 첫 링크만 취해 홈>…>현재 경로 구성."""
    loc = soup.select_one(".location")
    if not loc:
        return []
    top = loc.find(["ol", "ul"])
    if not top:
        return []
    out: list[str] = []
    for li in top.find_all("li", recursive=False):
        a = li.find("a")
        t = collapse((a.get_text(" ") if a else li.get_text(" ")))
        if t and t not in out:
            out.append(t)
    return out


def _anchor_text(el) -> str:
    """el(버튼)을 감싸는 문맥에서, 최종 본문 텍스트에 그대로 남는 형태로 앵커를 뽑는다.

    chunk.py가 첨부를 청크에 매칭할 때 쓰는 앵커. onclick_dynamic 버튼은
    serialize_text() 단계에서 통째로 decompose되므로 버튼 자신의 텍스트는
    본문에 남지 않는다 — 대신 버튼을 감싸는 li/행의 안내 문구("~신청서" 등)가
    본문에 남으므로 그쪽을 앵커로 써야 매칭이 가능하다. 단, 본문 직렬화 방식이
    li(비표) 문맥과 표 행 문맥에서 다르므로(serialize_text vs table_to_lines),
    앵커도 같은 방식으로 만들어야 부분 문자열 매칭이 성립한다:
      - <li> 조상이 있으면: serialize_text()처럼 줄 단위 collapse 후 "\\n" 결합.
        (li 안에 문서명 자체가 있는 케이스 — 구비서류안내류)
      - 없고 <tr> 조상이 있으면: table_to_lines()의 _row_line()과 동일하게
        같은 행의 다른 셀(문서명이 버튼과 분리된 셀에 있는 경우)까지 포함해
        "cell | cell" 한 줄로 결합. (버튼 셀 자체엔 텍스트가 없는 케이스 — 자료실류)
      - 그것도 없으면: 가장 가까운 <div> 조상(li(비표) 문맥과 표 행 문맥과 다르게
        직계자식 문구가 아닌, 형제 <span>/<p> 등에 문서명이 있는 카드형 레이아웃 —
        예: 부보금융회사 목록 엑셀/한글 다운로드) 텍스트를 li와 동일한 방식으로 뽑는다.
        단, 앵커가 본문 어디서든 부분일치되는 사고를 막기 위해 결과가 너무 길면
        (지나치게 상위 div까지 올라가 페이지 대부분을 삼킨 경우) 버리고 ""를 반환한다
        — 매칭 실패로 남는 게 엉뚱한 청크에 오매칭되는 것보다 낫다.
    """
    li = el.find_parent("li")
    if li is not None:
        ctx = deepcopy(li)
        for b in ctx.find_all(onclick=lambda v: v and "gfn_downloadFile" in v):
            b.decompose()
        raw = ctx.get_text("\n")
        lines = [collapse(l) for l in raw.split("\n")]
        lines = [l for l in lines if l]
        return "\n".join(lines)

    tr = el.find_parent("tr")
    if tr is not None:
        ctx = deepcopy(tr)
        for b in ctx.find_all(onclick=lambda v: v and "gfn_downloadFile" in v):
            b.decompose()
        return _row_line(ctx)

    div = el.find_parent("div")
    if div is not None:
        ctx = deepcopy(div)
        for b in ctx.find_all(onclick=lambda v: v and "gfn_downloadFile" in v):
            b.decompose()
        raw = ctx.get_text("\n")
        lines = [collapse(l) for l in raw.split("\n")]
        lines = [l for l in lines if l]
        text = "\n".join(lines)
        return text if 0 < len(text) <= 200 else ""

    return ""


def _direct_attachment(a, doc_kind: str, base_url: str) -> dict | None:
    href = a.get("href", "").strip()
    if not href or href.startswith("javascript:"):
        return None
    if "/cm/file/" not in href and not ATTACH_RE.search(href):
        return None
    m = ATTACH_RE.search(href)
    file_type = m.group(1).lower() if m else "other"
    abs_url = urljoin(base_url, href)
    name = collapse(a.get_text(" ")) or href.rsplit("/", 1)[-1]
    return {
        "name": name,
        "file_type": file_type,
        "doc_kind": doc_kind,
        # url = "문서를 찾을 수 있는 위치" — direct는 파일 자체의 절대 URL.
        "url": abs_url,
        "link_type": "direct",
        # direct는 <a> 태그 자체가 노이즈 제거 대상이 아니라 name이 본문에
        # 그대로 남는다 — anchor_text=name으로 매칭 방식을 dynamic과 통일.
        "anchor_text": name,
    }


def _dynamic_attachment(btn, doc_kind: str, base_url: str) -> dict | None:
    onclick = btn.get("onclick", "") or ""
    m = ONCLICK_RE.search(onclick)
    if m is None:
        return None
    enc_real, enc_temp = m.group(1), m.group(2)
    file_type = "other"
    for c in btn.get("class", []):
        mm = ICO_CLASS_RE.match(c)
        if mm:
            file_type = mm.group(1).lower()
            break
    return {
        "name": collapse(btn.get_text(" ")),
        "file_type": file_type,
        "doc_kind": doc_kind,
        # url = "문서를 찾을 수 있는 위치" 안내 페이지 URL (실파일 자체는 아님 —
        # 실다운로드는 enc_real/enc_temp로 fetch_attachments.py가 별도 수행).
        "url": base_url,
        "link_type": "onclick_dynamic",
        "anchor_text": _anchor_text(btn),
        # 다운로드 재현용 토큰 원본. 세션 종속이 아니라 페이지 렌더마다 고정값이라
        # (실사 확인) doc_id 안에서 이 쌍이 곧 파일 신원 그 자체 — link_files.py가
        # anchor_text 같은 표시 텍스트가 아니라 이 값으로 정확히 1:1 매칭한다.
        "enc_real": enc_real,
        "enc_temp": enc_temp,
    }


def extract_attachments(container, base_url: str) -> list[dict]:
    """첨부 목록 보존 + 정적 크롤링 범위 내에서 가능한 메타 태깅.

    반환 스키마 (item당):
      name, file_type, doc_kind, url(항상 채움 — "문서를 찾을 수 있는 URL".
      direct는 파일 자체의 절대 URL, onclick_dynamic은 파일 URL을 만들 수 없어
      대신 안내 페이지 자체 URL — 챗봇이 문서 파일을 직접 반환할 필요 없이
      링크만 안내하면 되므로 이 값으로 충분), link_type("direct"|"onclick_dynamic",
      url이 실제 파일인지 안내 페이지인지 구분용),
      anchor_text(chunk.py가 청크 매칭에 쓰는 필드 — direct는 name과 동일,
      dynamic은 버튼을 감싸는 li/td 문구. 표시용 name과 매칭용 anchor_text를
      분리한 이유는 [meta-doc] 참고), onclick_dynamic 항목엔 추가로
      enc_real/enc_temp(다운로드 토큰 원본 — link_files.py의 파일 신원 키)

    [meta-doc 후속] dynamic dedup 키를 (enc_real, enc_temp) 토큰 쌍으로 쓴다 —
    name/anchor_text 같은 표시 텍스트 기반 키는 동일 문서가 페이지 내 여러 곳
    (예: 본인/대리인 탭)에 노출될 때 실제로는 서로 다른 파일인데도 문구가
    똑같아서 dedup 키가 충돌하는 사례가 실사에서 나왔다(예: SprtFndDebtDlngAplyGudn
    페이지의 "금융거래정보 발급신청서" — 본인용/대리인용이 텍스트는 동일, 토큰은
    다른 별개 파일). 토큰은 페이지 렌더마다 고정값이라(세션 종속 아님, 실사 확인)
    진짜 파일 신원으로 안전하게 쓸 수 있다. 반대로 같은 문서의 hwp/pdf 버튼처럼
    name/anchor_text가 같아도 토큰이 다르면 별개 항목으로 정확히 유지된다.
    """
    out: list[dict] = []
    seen: set[tuple] = set()

    def add(item: dict | None, dedup_key: tuple) -> None:
        if item is None or dedup_key in seen:
            return
        seen.add(dedup_key)
        out.append(item)

    for table in container.find_all("table"):
        headers = get_table_headers(table)
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            for idx, cell in enumerate(cells):
                header_text = headers[idx] if idx < len(headers) else ""
                doc_kind = infer_doc_kind(header_text)

                for a in cell.find_all("a", href=True):
                    item = _direct_attachment(a, doc_kind, base_url)
                    if item:
                        add(item, ("direct", item["url"]))

                for btn in cell.find_all(onclick=lambda v: v and "gfn_downloadFile" in v):
                    item = _dynamic_attachment(btn, doc_kind, base_url)
                    if item:
                        add(item, ("dynamic", item["name"], item["anchor_text"],
                                   item["file_type"], item["enc_real"], item["enc_temp"]))

    # 표 밖 느슨한 첨부 링크 (자료실/보도자료 목록형 페이지 등)
    for a in container.find_all("a", href=True):
        if a.find_parent("table"):
            continue
        item = _direct_attachment(a, "기타", base_url)
        if item:
            add(item, ("direct", item["url"]))

    for btn in container.find_all(onclick=lambda v: v and "gfn_downloadFile" in v):
        if btn.find_parent("table"):
            continue
        item = _dynamic_attachment(btn, "기타", base_url)
        if item:
            add(item, ("dynamic", item["name"], item["anchor_text"],
                       item["file_type"], item["enc_real"], item["enc_temp"]))

    return out


def serialize_text(container) -> str:
    """노이즈 제거된 컨테이너를 라인 구조 텍스트로 직렬화 (표는 행 텍스트로 치환)."""
    for table in container.find_all("table"):
        table.replace_with(NavigableString("\n" + table_to_lines(table) + "\n"))
    raw = container.get_text("\n")
    lines = [collapse(l) for l in raw.split("\n")]
    lines = [l for l in lines if l]
    return "\n".join(lines)


def parse_html(html: str, selector: str = CONTENT_SELECTOR) -> BeautifulSoup:
    """lxml 우선 파싱, selector 미탐지 시 html.parser로 재시도.

    일부 fins.kdic.or.kr 응답은 본인인증 위젯 스니펫이 <html>/<body>째로
    중복 포함돼 온다(malformed). HTML5 스펙(WHATWG §13.2.6.4.7 "in body")은
    이런 중복 body를 만나면 기존 body에 병합해 계속 파싱하도록 정의하는데,
    Windows용 lxml 휠은 libxml2 2.11에 고정돼 있어(PyPI 최신판도 동일) 이
    복구를 못 하고 두 번째(진짜) body를 통째로 버린다 — libxml2 2.14+
    (macOS/manylinux 휠 기본값)부터 HTML5 준수 토크나이저로 정상 복구됨.
    html.parser(표준 라이브러리)는 OS/휠 버전과 무관하게 이 복구를 해낸다.
    """
    soup = BeautifulSoup(html, "lxml")
    if soup.select_one(selector) is None:
        alt = BeautifulSoup(html, "html.parser")
        if alt.select_one(selector) is not None:
            return alt
    return soup


def parse_one(doc_id: str, html: str, meta: dict) -> dict:
    soup = parse_html(html)
    breadcrumb = extract_breadcrumb(soup)
    container = soup.select_one(CONTENT_SELECTOR)
    base_url = meta.get("final_url") or meta.get("source_url") or ""

    if container is None:
        # 컨테이너 미탐지 — 본문 유실 위험. 빈 텍스트로 표시하고 호출측에서 경고.
        return {"doc_id": doc_id, "text": "", "attachments": [],
                "has_attachments": False, "attachment_count": 0,
                "breadcrumb": breadcrumb, "_no_container": True}

    # 첨부는 노이즈 제거 전에 수집 (기능부 안에 서식 다운로드가 있을 수 있음,
    # button 태그는 NOISE_SELECTORS에서 통째로 decompose되므로 반드시 먼저 실행)
    attachments = extract_attachments(container, base_url)

    for sel in NOISE_SELECTORS:
        for n in container.select(sel):
            n.decompose()

    text = serialize_text(container)
    site = "www" if "-www-" in doc_id else ("fins" if "-fins-" in doc_id else "")
    coverage = "안내부" if doc_id in COVERAGE_ANNAE else "전체"
    page_title = breadcrumb[-1] if breadcrumb else collapse(meta.get("title", ""))
    sub_category = " > ".join(breadcrumb[1:]) if len(breadcrumb) > 1 else ""

    return {
        "doc_id": doc_id,
        "source_url": meta.get("source_url", ""),
        "final_url": meta.get("final_url", ""),
        "site": site,
        "business_function": meta.get("business_function", ""),
        "sub_category": sub_category,
        "page_type": meta.get("page_type", ""),
        "coverage": coverage,
        "variant": meta.get("variant", ""),
        "page_title": page_title,
        "breadcrumb": breadcrumb,
        "title_raw": collapse(meta.get("title", "")),
        "text": text,
        "text_len": len(text),
        "attachments": attachments,
        "has_attachments": len(attachments) > 0,
        "attachment_count": len(attachments),
        "robots_status": meta.get("robots_status", ""),
        "collected_at": meta.get("collected_at", ""),
        "raw_sha256": meta.get("raw_sha256", ""),
        "parsed_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def main() -> None:
    src_root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(".")
    raw_glob = sorted((src_root / RAW_DIR).glob("*.html"))
    if not raw_glob:
        sys.exit(f"raw HTML 없음: {src_root / RAW_DIR}")

    out_dir = pathlib.Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    ok, warn = 0, []
    for p in raw_glob:
        doc_id = p.stem
        meta_path = pathlib.Path(META_DIR) / f"{doc_id}.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        html = p.read_text(encoding="utf-8", errors="replace")
        rec = parse_one(doc_id, html, meta)
        (out_dir / f"{doc_id}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        if rec.get("_no_container"):
            warn.append(f"{doc_id}: 본문 컨테이너 미탐지")
        elif rec["text_len"] < 120:
            warn.append(f"{doc_id}: 본문 {rec['text_len']}자 (얇음 — 이미지/영상 위주 의심)")
        ok += 1

    print(f"파싱 {ok}건 → {out_dir}/")
    if warn:
        print("경고:")
        for w in warn:
            print("  -", w)


if __name__ == "__main__":
    main()
