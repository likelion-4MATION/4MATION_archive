"""가드 로직 픽스처 테스트 — 네트워크 불필요. python tests/test_guards.py"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import crawler  # noqa: E402

# .location 구조는 실물 KDIC DOM 준용 — 직계 li의 첫 링크가 경로, ulSelectBox 안 ul은
# 드롭다운 형제 메뉴(통합검색 등 노이즈). H8: 형제 메뉴가 breadcrumb에 섞이면 안 됨.
NORMAL = """<html><head><title>예금자보호제도 | KDIC</title></head><body>
<div class="location"><ol>
<li><a class="btn_home" href="/sp/main.do">홈</a></li>
<li><div class="ulSelectBox"><a href="/sp/main.do">예금자보호</a>
<ul><li class="curr"><a href="/sp/main.do">예금자보호</a></li>
<li><a href="/cm/srch/s.do">통합검색</a></li>
<li><a href="/cm/imtncal/c.do">예금보호금액 모의계산기</a></li></ul>
</div></li>
<li><div class="ulSelectBox"><a href="/sp/dpstrprot/ProtSystProtLmts/selectScrn.do"><strong>보호한도</strong></a>
<ul><li><a href="/sp/dpstrprot/p.do">보호대상</a></li>
<li class="curr"><a href="/sp/dpstrprot/ProtSystProtLmts/selectScrn.do">보호한도</a></li></ul>
</div></li>
</ol></div>
<p>2025년 9월부터 예금보호 한도가 1억원으로 상향되었습니다.</p>
<div style="display:none">이용자수가 많아 서비스 접속 대기</div>
""" + "<p>정상 본문 문단입니다</p>" * 120 + "</body></html>"

ERROR = ("<html><head><title>오류 | KDIC</title></head>"
         "<body>요청하신 페이지를 찾을 수 없습니다</body></html>")

WAITING = ("<html><head><title>안내</title></head>"
           "<body>이용자수가 많아 서비스 접속 대기 중입니다</body></html>")


def run() -> None:
    checks = []

    t = crawler.visible_text(NORMAL)
    checks.append(("정상 페이지: 오류 아님",
                   not crawler.looks_like_error_page("https://x/sp/a.do",
                                                     NORMAL, "예금자보호제도 | KDIC")))
    checks.append(("정상 페이지: 숨김 대기열 문구 있어도 본문 길면 통과",
                   not crawler.looks_like_waiting_room(t)))
    checks.append(("오류 타이틀 감지",
                   crawler.looks_like_error_page("https://x/a.do", ERROR, "오류 | KDIC")))
    checks.append(("error404 URL 감지",
                   crawler.looks_like_error_page("https://x/error404.do", NORMAL,
                                                 "예금자보호제도 | KDIC")))
    checks.append(("대기열: 짧은 본문 + 마커",
                   crawler.looks_like_waiting_room(crawler.visible_text(WAITING))))

    from bs4 import BeautifulSoup
    bc = crawler.extract_breadcrumb(BeautifulSoup(NORMAL, "lxml"))
    checks.append(("브레드크럼: 직계 첫 링크만, 드롭다운 형제 제외 (H8)",
                   bc == ["홈", "예금자보호", "보호한도"]))

    checks.append(("doc_id: www .do 제거",
                   crawler.doc_id_from_url("https://www.kdic.or.kr/sp/pr/limit.do")
                   == "kdic-www-sp-pr-limit"))
    checks.append(("doc_id: 쿼리 variant 구분",
                   crawler.doc_id_from_url("https://fins.kdic.or.kr/a.do?tab=faq")
                   != crawler.doc_id_from_url("https://fins.kdic.or.kr/a.do?tab=guide")))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
    if failed:
        sys.exit(f"\n{len(failed)}건 실패")
    print(f"\n전체 {len(checks)}건 통과")


if __name__ == "__main__":
    run()
