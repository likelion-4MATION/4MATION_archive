"""가드 로직 픽스처 테스트 — 네트워크 불필요. python tests/test_guards.py"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import crawler  # noqa: E402

NORMAL = """<html><head><title>예금자보호제도 | KDIC</title></head><body>
<div class="location"><a>홈</a><a>예금자보호</a><span>보호한도</span></div>
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
    checks.append(("브레드크럼 추출", bc == ["홈", "예금자보호", "보호한도"]))

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
