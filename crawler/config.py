"""KDIC 화이트리스트 크롤러 v0 설정 — 4MATION 선발대 스프린트.

07-10 정찰 반영:
- www.kdic.or.kr 루트(/)는 502 → 진입점은 /sp/main.do
- 세션 선행 필수: 진입점 방문으로 쿠키 확보 후 내부 순회
  (누락 시 전 페이지가 오류 스냅샷으로 수집될 위험)
"""

# 명시적 User-Agent — 연락처(팀 대표 메일). 공식 팀 주소 확정 시 교체.
USER_AGENT = (
    "4MATION-KDIC-RAG-PoC/0.1 "
    "(+https://github.com/likelion-4MATION/4MATION; LikeLion x Clavi bootcamp; "
    "contact: hyunuk200202@gmail.com)"
)

# 요청 간격 1~2초 (기본 1.5s + 0~0.7s 지터)
REQUEST_INTERVAL_SEC = 1.5
REQUEST_JITTER_SEC = 0.7
TIMEOUT_SEC = 15
MAX_RETRY = 2

# 호스트별 세션 진입점 (루트 진입 → 세션 확보)
ENTRY_POINTS = {
    "www.kdic.or.kr": "https://www.kdic.or.kr/sp/main.do",
    "fins.kdic.or.kr": "https://fins.kdic.or.kr/",
}

# 매니페스트 외 도메인 안전장치 — kdic 계열만 수집
ALLOWED_HOST_SUFFIX = ".kdic.or.kr"

# ── 절대규칙 1: 정책 차단 오버레이 (robots.txt Disallow 반영) ──────
# 실측 robots.txt (2026-07-11, HTTP 200):
#   fins.kdic.or.kr → Disallow: /cm/bbs/  (채무정보조회 FAQ 등 — 고객사 허용 확인 전 금지)
#   www.kdic.or.kr  → Disallow: /*List.do$ , /*Dtl.do$ , /../../srch/
# 두 robots 그룹 모두 'User-agent: Googlebot' 전용이라 우리 UA엔 자동 미적용이고,
# urllib.robotparser는 KDIC robots.txt 읽기에 실패(기본 UA 차단)한다. 그래서
# 절대규칙 1 준수를 위해 경로 패턴으로 명시 차단한다 — 수집 안 하고 report에 기록만.
#
# 07-15 재해석: fins /cm/bbs/ FAQ 5건 고객사 허용 확보 → 차단 해제(HOLES H18).
POLICY_DISALLOW = {
    "fins.kdic.or.kr": [],
    "www.kdic.or.kr": [r"List\.do$", r"Dtl\.do$", r"/srch/"],
}

# ── 오류 페이지 가드 ──────────────────────────────────────────
# 타이틀/URL에서 감지되면 실패 처리, raw 저장 안 함 (정상 페이지 오수집 차단)
ERROR_TITLE_MARKERS = ("오류 | KDIC", "오류|KDIC")
ERROR_URL_MARKERS = ("error404", "error/404")
ERROR_BODY_MARKERS = ("요청하신 페이지를 찾을 수 없습니다",)

# ── 트래픽 제어(대기열) 가드 ─────────────────────────────────
# 마커 문구는 정상 페이지에도 숨김 모달로 존재 → 본문이 비정상적으로 짧을 때만 판정
WAITING_ROOM_MARKERS = ("서비스 접속 대기", "이용자수가 많아", "접속이 차단")
WAITING_ROOM_MAX_TEXT_LEN = 800  # 보이는 텍스트가 이보다 짧고 마커 존재 → 대기열

# 산출 경로
RAW_DIR = "data/raw"
META_DIR = "data/meta"
REPORT_PATH = "data/crawl_report.json"
