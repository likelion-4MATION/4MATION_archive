"""chatbot/ui_theme.py — UI 1차 디자인 데모용 스타일 주입 (렌더 전용).

색·폰트·radius 토큰은 `.streamlit/config.toml`(streamlit 1.59 네이티브 테마)이 담당한다.
여기 CSS 는 **테마 옵션으로 못 잡는 것만** 맡는다:

  1. 하단 고정 입력 바(st.chat_input) — 단일 박스, 전송 아이콘만 KDIC RED
  2. 질문/답변을 아이콘이 아니라 **타이포그래피**로 구분 (말풍선·아바타 없음)
  3. expander 를 카드가 아닌 disclosure(구분선) 형태로
  4. 사이드바·트레이스(관리자) 패널 위계 정리

색상 근거 — `.streamlit/config.toml` 주석과 동일하다.
  Navy #003679 · Red #E30022 (08-25 리디자인 지시서 지정값)
  실측 CI 값(#1E3370 / #D51224)과 다르다. 근거는 config.toml 머리주석 참조.
  회색계   #212529 / #495057 / #DEE2E6 / #F4F6F8
  레드는 CTA(검색 버튼) 전용. 녹색·보라·네온 미사용.

기능 코드는 건드리지 않는다 — `inject()` 는 `st.markdown` 한 번이 전부다.
selector 는 streamlit 1.59 DOM(`data-testid` / class) 기준이다. 상위 버전에서
selector 가 어긋나도 **기본 streamlit 스타일로 폴백**할 뿐 화면이 깨지지 않는다.
"""
import base64
import html
import pathlib

import streamlit as st

_CSS = """
<style>
/* 좌우 여백 한 값으로 묶는다 — 본문 블록과 하단 입력 바가 같은 좌변을 쓴다 */
:root { --kdic-gutter: clamp(1.25rem, 2.5vw, 4rem); }

/* ── 레이아웃 ───────────────────────────────────────────────────────────── */
/* 본문 블록 — 고정 max-width 를 두면 넓은 화면에서 우측이 통째로 남는다. 폭 제한을
   풀고 좌우 여백만 화면 폭에 비례해(clamp) 대칭으로 준다 → 어느 해상도에서도
   좌우 여백이 같고, 특정 해상도용 고정 픽셀 레이아웃이 되지 않는다.
   하단 여백은 고정 입력 바(약 5.3rem) + 여유 — 마지막 콘텐츠가 입력창에 가리지 않게. */
.stMainBlockContainer {
  padding-top: 2.2rem;
  padding-bottom: 1rem;        /* 하단 여백은 중앙 컬럼에만 준다(아래 규칙) */
  max-width: none;
  padding-left: var(--kdic-gutter) !important;
  padding-right: var(--kdic-gutter) !important;
}
.stAppHeader { background: transparent; }

/* ── 서비스 헤더 ────────────────────────────────────────────────────────── */
.kdic-header { border-bottom: 2px solid #003679; padding-bottom: .85rem; margin-bottom: 1.4rem; }
.kdic-header .kdic-title {
  font-size: 1.6rem; font-weight: 700; letter-spacing: -.02em;
  color: #003679; line-height: 1.3; margin: 0;
}
.kdic-header .kdic-sub {
  font-size: .88rem; color: #495057; margin: .35rem 0 0; line-height: 1.5;
}
.kdic-header .kdic-tag {
  display: inline-block; margin-left: .5rem; vertical-align: .18em;
  font-size: .68rem; font-weight: 600; letter-spacing: .04em;
  color: #495057; background: #F4F6F8; border: 1px solid #DEE2E6;
  border-radius: 2px; padding: .1rem .38rem;
}

/* 본문 섹션 라벨 */
.kdic-section {
  font-size: .78rem; font-weight: 700; letter-spacing: .06em; color: #495057;
  margin: .4rem 0 .55rem; padding-bottom: .3rem; border-bottom: 1px solid #DEE2E6;
}

/* ── 하단 고정 입력 바 (st.chat_input) ─────────────────────────────────── */
/* 입력칸과 전송 버튼이 한 박스 안에 든다. 붉은색은 전송 아이콘에만 — 면적으로 쓰지 않는다 */
[data-testid="stChatInput"] {
  border: 1px solid #DEE2E6 !important; border-radius: 24px !important;
  background: #FFFFFF !important; box-shadow: none !important;
}
[data-testid="stChatInput"]:focus-within {
  border-color: #003679 !important; box-shadow: none !important; outline: none !important;
}
/* streamlit 이 내부 래퍼·textarea 에도 각각 포커스 링을 얹는다 — 전부 눌러야 잔상이 사라진다 */
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] textarea:focus,
[data-testid="stChatInput"] textarea:focus-visible {
  box-shadow: none !important; outline: none !important; border: 0 !important;
  background: transparent !important;   /* 내부 래퍼의 secondaryBackground 가 회색으로 비친다 */
}
[data-testid="stChatInput"] textarea { font-size: .95rem !important; }
[data-testid="stChatInputSubmitButton"] {
  color: #E30022 !important; background: transparent !important; border: 0 !important;
}
[data-testid="stChatInputSubmitButton"]:hover {
  color: #FFFFFF !important; background: #E30022 !important;
}
[data-testid="stChatInputSubmitButton"]:disabled { color: #ADB5BD !important; }
/* 하단 입력 바 — 본문 블록과 같은 폭·같은 좌측 정렬(padding-left 는 streamlit 기본값
   --kdic-gutter — 본문 블록과 같은 값). 오른쪽만 우측 레일 몫(컬럼 2.5/10)만큼 더
   비워, 입력창이 레일 아래로 넘어가지 않게 한다. */
[data-testid="stBottomBlockContainer"] {
  max-width: none;
  padding-bottom: 2.75rem;                       /* 입력창과 viewport 하단 사이 간격 */
  padding-left: var(--kdic-gutter) !important;
  /* 우변을 중앙 컬럼 우변에 맞춘다. 본문 폭 M, 여백 g, 컬럼 간격 4rem 일 때
     중앙 컬럼 폭 ≈ .764 × (M − 2g − 4rem) 로 실측된다 → 남길 우측 패딩은
     M − g − 그 값 = .236M + .53g + 3.06rem. 셋 다 상대값이라 해상도를 안 탄다. */
  padding-right: calc(23.6% + var(--kdic-gutter) * .53 + 3.06rem) !important;
}

/* ── 결과 영역: 질문은 문서 제목, 답변은 안내문 본문 ────────────────────── */
.kdic-q {
  border-left: 3px solid #003679;
  padding: .05rem 0 .05rem .8rem;
  margin: .2rem 0 1rem !important;
  font-size: 1.05rem; font-weight: 600; color: #212529; line-height: 1.55;
}
.kdic-rule { border: 0; border-top: 1px solid #DEE2E6; margin: 2.2rem 0 1.6rem; }

[data-testid="stMarkdownContainer"] p { line-height: 1.78; }
[data-testid="stMarkdownContainer"] li { line-height: 1.72; }

/* ── expander = 카드가 아니라 disclosure ────────────────────────────────── */
.stExpander, [data-testid="stExpander"] { border: 0 !important; box-shadow: none !important; }
.stExpander details, [data-testid="stExpander"] details {
  border: 0 !important;
  border-top: 1px solid #DEE2E6 !important;
  border-radius: 0 !important;
  background: transparent !important;
}
.stExpander summary, [data-testid="stExpander"] summary,
.stExpander summary:hover, .stExpander summary:focus {
  background: transparent !important; box-shadow: none !important;
  padding: .5rem 0 !important;
  font-size: .85rem !important; font-weight: 600; color: #343A40 !important;
}
.stExpander summary:hover { color: #003679 !important; }
[data-testid="stExpanderDetails"] { padding: .1rem 0 .7rem !important; }

/* ── 버튼·칩: 작고 단정하게 (CTA 아님 — 무채색 + 네이비 hover) ──────────── */
.stButton button:not([data-testid="stBaseButton-primary"]),
[data-testid="stBaseButton-secondary"] {
  font-size: .855rem !important; font-weight: 500 !important;
  padding: .38rem .7rem !important; min-height: 2.15rem !important;
  border-color: #DEE2E6 !important; color: #343A40 !important;
  box-shadow: none !important;
}
.stButton button:not([data-testid="stBaseButton-primary"]):hover,
[data-testid="stBaseButton-secondary"]:hover {
  border-color: #003679 !important; color: #003679 !important; background: #F4F6F8 !important;
}
[data-testid="stBaseButton-primary"] {
  box-shadow: none !important; font-weight: 600 !important;
  background: #003679 !important; border-color: #003679 !important; color: #FFFFFF !important;
}
[data-testid="stBaseButton-primary"]:hover {
  background: #00285A !important; border-color: #00285A !important; color: #FFFFFF !important;
}
.stDownloadButton button { font-size: .83rem !important; }

/* ── 캡션 ───────────────────────────────────────────────────────────────── */
[data-testid="stCaptionContainer"] p { font-size: .78rem !important; color: #6C757D !important; }

/* ── 사이드바: 중앙보다 튀지 않게 ───────────────────────────────────────── */
.stSidebar [data-testid="stSidebarUserContent"] { padding-top: 1.6rem; }
.stSidebar h2, .stSidebar h3 {
  font-size: .74rem !important; font-weight: 700 !important; letter-spacing: .07em;
  color: #6C757D !important; margin: 0 0 .5rem !important; padding: 0 !important;
}
.stSidebar hr { margin: 1.05rem 0 !important; border-color: #DEE2E6 !important; }
.stSidebar [data-testid="stWidgetLabel"] p { font-size: .82rem !important; font-weight: 500; }
.stSidebar .stButton button { width: 100%; }
.stSidebar [data-testid="stMetricLabel"] p { font-size: .78rem !important; }
.stSidebar [data-testid="stElementContainer"] { margin-bottom: .1rem; }

/* ── 트레이스(관리자) 패널: 사용자 시야에서 물러나게 ────────────────────── */
/* 스크롤 컨테이너는 앱 통틀어 이것 하나뿐이라 직접 잡는다 */
[data-testid="stVerticalBlockBorderWrapper"] {
  border-color: #DEE2E6 !important; border-radius: 3px !important;
  background: #FAFBFC; padding: 0 .85rem !important;
}
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] p {
  font-size: .84rem; line-height: 1.6;
}
[data-testid="stVerticalBlockBorderWrapper"] h1,
[data-testid="stVerticalBlockBorderWrapper"] h2,
[data-testid="stVerticalBlockBorderWrapper"] h3 {
  font-size: .95rem !important; font-weight: 600 !important; padding: .2rem 0 !important;
}
.kdic-trace {
  font-size: .78rem; font-weight: 700; letter-spacing: .07em; color: #6C757D;
  border-bottom: 1px solid #DEE2E6; padding-bottom: .45rem; margin: .3rem 0 .7rem;
}

/* ── 메인 대화 영역 배경 ────────────────────────────────────────────────── */
/* 은은한 청회색 판 위에 흰 카드·흰 입력창이 뜨는 구성 */
.st-key-kdic-main {
  background: #EBF0F5 !important; border-radius: 4px;
  padding: 1.25rem 1.4rem 1.6rem !important; min-height: 22rem;
}

/* ── 로딩 상태 (답변이 그려질 자리) ─────────────────────────────────────── */
/* 전체화면 오버레이 없음. 답변 본문과 같은 컨테이너 안에서 같은 여백을 쓴다. */
.kdic-load { display: flex; align-items: center; gap: .85rem; padding: .1rem 0 .5rem; }
.kdic-load-msg {
  font-size: .95rem; font-weight: 600; color: #212529;
  margin: 0 !important; line-height: 1.55;
}
.kdic-load-note {
  font-size: .8rem; color: #6C757D; margin: .15rem 0 0 !important; line-height: 1.5;
}
.kdic-spin {
  flex: none; display: block; width: 32px; height: 32px;
  animation: kdic-spin 1.15s linear infinite; transform-origin: 50% 50%;
}
@keyframes kdic-spin { to { transform: rotate(360deg); } }
/* 회전을 아예 멈추면 진행 중인지 알 수 없다 — 느리게만 돌린다 */
@media (prefers-reduced-motion: reduce) { .kdic-spin { animation-duration: 3.2s; } }

/* ── 상담원 연결 카드 (우측 레일 최상단) ─────────────────────────────────── */
.st-key-kdic-agent {
  background: #FFFFFF !important; border: 1px solid #DEE2E6 !important;
  border-radius: 3px !important;
  padding: .95rem 1.1rem 1.05rem !important; margin-bottom: 1.3rem;
}

/* ── 추천 질문 (우측 레일) — 무게감을 낮춘 연회색 테두리 ─────────────────── */
[class*="st-key-rail-q-"] .stButton button,
[class*="st-key-qcard-"] .stButton button {
  border: 1px solid #DEE2E6 !important; border-radius: 3px !important;
  background: #FFFFFF !important; color: #212529 !important;
  padding: .5rem .8rem !important;
}
[class*="st-key-rail-q-"] .stButton button:hover,
[class*="st-key-qcard-"] .stButton button:hover {
  border-color: #003679 !important; background: #F4F6F8 !important; color: #003679 !important;
}
.kdic-agent-t {
  font-size: .85rem; font-weight: 700; color: #003679; margin: 0 0 .3rem !important;
}
.kdic-agent-d {
  font-size: .78rem; color: #6C757D; line-height: 1.5; margin: 0 0 .7rem !important;
}

/* ── 추천 질문 카드 (본문 중앙 3개) ─────────────────────────────────────── */
/* 컨테이너 key → `st-key-kdic-card-N` 클래스. 카드 껍데기는 CSS, 내용은 버튼 하나 */
[class*="st-key-kdic-card-"] {
  border: 0 !important; border-radius: 0 !important; position: relative;
  background: #FFFFFF; padding: .95rem 1rem 1rem !important;
  transition: border-color .12s ease, background .12s ease;
  height: 180px !important; min-height: 180px !important; flex: none !important;
  display: flex !important; flex-direction: column !important;
  justify-content: space-between !important; overflow: hidden;
}
/* KDIC 시그니처 프레임 — 위 Red ㄷ자 · 아래 Navy ㄷ자 · 좌우 중앙은 끊는다 */
[class*="st-key-kdic-card-"]::before,
[class*="st-key-kdic-card-"]::after {
  content: ""; position: absolute; left: 0; right: 0;
  pointer-events: none; border-style: solid; border-width: 1.5px;
}
[class*="st-key-kdic-card-"]::before {
  top: 0; height: 30%; border-color: #E30022; border-bottom: 0;
}
[class*="st-key-kdic-card-"]::after {
  bottom: 0; height: 30%; border-color: #003679; border-top: 0;
}
[class*="st-key-kdic-card-"]:hover { background: #FAFBFC; }
[class*="st-key-kdic-card-"] [data-testid="stElementContainer"] { margin-bottom: 0; }
.kdic-card-cat {
  font-size: .72rem; font-weight: 700; letter-spacing: .05em; color: #003679;
  margin: 0 0 .45rem !important;
}
.kdic-card-q {
  font-size: .93rem; font-weight: 600; color: #212529; line-height: 1.5;
  margin: 0 !important;
}
/* 카드 안 버튼 = 텍스트 링크처럼. 카드 자체가 이미 테두리를 갖고 있다 */
[class*="st-key-kdic-card-"] .stButton button {
  background: transparent !important; border: 0 !important;
  padding: 0 !important; min-height: auto !important;
  color: #003679 !important; font-weight: 600 !important; font-size: .82rem !important;
  justify-content: flex-start !important;
}
[class*="st-key-kdic-card-"] .stButton button:hover { color: #E30022 !important; }
[class*="st-key-kdic-card-"] .stButton button p { text-align: left; width: 100%; }

/* ── 우측 레일 ──────────────────────────────────────────────────────────── */
.st-key-kdic-rail { padding-top: .15rem; }
.st-key-kdic-rail .stButton button {
  text-align: left; justify-content: flex-start !important;
  font-size: .82rem !important; padding: .34rem .6rem !important;
  min-height: 2rem !important; width: 100%;
}
/* 추천 검색어는 태그처럼 — 버튼을 좌우 여백만 준 칩으로 */
.st-key-kdic-tags .stButton button {
  border-radius: 999px !important; font-size: .78rem !important;
  padding: 0 .9rem !important; width: 100%;
  height: 2.1rem !important; min-height: 2.1rem !important;
  border: 1.5px solid #000000 !important; color: #212529 !important;
}
.st-key-kdic-tags .stButton button:hover {
  border-color: #000000 !important; background: #F4F6F8 !important; color: #003679 !important;
}
.st-key-kdic-tags .stButton button p {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  width: 100%; text-align: center;
}
.st-key-kdic-tags [data-testid="stElementContainer"] { margin-bottom: .35rem; }
.st-key-kdic-rail [data-testid="stElementContainer"] { margin-bottom: .2rem; }
[class*="st-key-qcard-"] .stButton button p { text-align: left; width: 100%; }
[class*="st-key-qcard-"] .stButton button { justify-content: flex-start !important; }
.kdic-trace .kdic-trace-note { font-weight: 500; letter-spacing: 0; color: #ADB5BD; }

/* ── 우측 레일 viewport 고정 ────────────────────────────────────────────── */
/* 레일이 든 컬럼 자체를 sticky 로 뽑는다. 컬럼은 기본이 stretch 라 그대로 두면
   부모 높이를 다 먹어 sticky 가 움직일 여지가 없다 — align-self 를 풀어 준다.
   레일 높이를 viewport 로 가두면 페이지 전체 높이가 중앙 콘텐츠 기준이 되어,
   레일이 길 때 첫 진입 화면이 아래로 밀려 있던 것도 같이 사라진다.
   컬럼 폭 안에 머무르므로 중앙 콘텐츠·chat_input 과 겹치지 않는다. */
[data-testid="stColumn"]:has(.st-key-kdic-rail) {
  position: sticky !important; top: 4rem;
  align-self: flex-start !important;
  /* 레일이 쓸 수 있는 실제 높이 = viewport − (레일 시작선까지 9.3rem) − (고정 입력
     바 7rem) − (바 위 최소 여유 1.2rem). 이보다 길면 페이지가 늘어나 첫 진입 화면이
     아래로 밀리고 레일 끝이 입력 바에 닿는다 — 이 두 조건이 상한을 정한다. */
  max-height: calc(100vh - 17.9rem);
  padding-bottom: 2rem;              /* 스크롤 끝에서 마지막 버튼이 붙어 잘리지 않게 */
  overflow-y: auto; overflow-x: hidden;
  scrollbar-width: none; -ms-overflow-style: none;   /* 내부 스크롤바 숨김 */
  /* 스크롤 경계에서 항목이 툭 잘려 보이지 않게 하단 32px 만 서서히 흐려지게 한다.
     오버레이가 아니라 마스크라 레이어를 얹지 않는다 — 클릭·스크롤 영역·콘텐츠 높이가
     그대로고 배경색을 하드코딩하지 않는다. 맨 아래까지 내리면 이 구간이 레일 하단
     패딩(2rem)과 겹쳐 마지막 항목은 온전히 보인다. */
  -webkit-mask-image: linear-gradient(to bottom, #000 calc(100% - 32px), transparent);
  mask-image: linear-gradient(to bottom, #000 calc(100% - 32px), transparent);
}
[data-testid="stColumn"]:has(.st-key-kdic-rail)::-webkit-scrollbar {
  width: 0; height: 0; display: none;
}
/* flex 아이템 기본 min-width:auto 때문에 긴 문구 하나가 컬럼을 밀어내 가로로 넘칠 수
   있다. 0 으로 눌러 두면 컬럼이 항상 제 몫 안에 머문다(레일이 화면 밖으로 안 나간다). */
[data-testid="stColumn"] { min-width: 0 !important; }
/* 하단 여백은 중앙 컬럼에만. 블록 전체에 주면 레일 아래에도 붙어 페이지가 늘어나고,
   그만큼 레일이 짧아져 더 많이 잘린다. 마지막 콘텐츠가 입력창에 가리지 않는 효과는 같다. */
[data-testid="stColumn"]:has(.st-key-kdic-main) { padding-bottom: 8rem !important; }

/* ── 확정된 조건 패널 ───────────────────────────────────────────────────── */
/* 기능·버튼 배치는 그대로. 테두리·라운드·여백으로만 독립 블록처럼 떼어 낸다 */
[class*="st-key-kdic-slots-"] {
  background: #FFFFFF !important; border: 1px solid #DEE2E6 !important;
  border-radius: 6px !important;
  padding: .8rem .95rem .45rem !important; margin: .35rem 0 1rem !important;
}

/* ── 오류 신고 인라인 아코디언 (지원 카드 안) ───────────────────────────── */
.st-key-kdic-report {
  background: #F4F6F8 !important; border: 1px solid #DEE2E6 !important;
  border-radius: 6px !important;
  padding: .65rem .75rem .35rem !important; margin-top: .45rem !important;
}
</style>
"""


def inject() -> None:
    """페이지당 1회 호출. 스타일 외 부작용 없음."""
    st.markdown(_CSS, unsafe_allow_html=True)


def header(title: str, subtitle: str, tag: str = "") -> None:
    """서비스 헤더 — 서비스명 + 설명 1줄. `st.title`(이모지 h1) 대체."""
    tag_html = f'<span class="kdic-tag">{tag}</span>' if tag else ""
    st.markdown(
        f'<div class="kdic-header">'
        f'<p class="kdic-title">{title}{tag_html}</p>'
        f'<p class="kdic-sub">{subtitle}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


def section(label: str) -> None:
    """본문 섹션 라벨 — h2/h3 를 쓰면 위계가 헤더와 겹친다."""
    st.markdown(f'<p class="kdic-section">{label}</p>', unsafe_allow_html=True)


# 스피너 이미지 — KDIC 링 로고 실물(`assets/kdic-logo.png`, 96px RGBA, 흰 배경 제거).
# 손으로 그린 SVG 로는 양 끝 테이퍼와 두 곡선 사이 흰 간격이 재현되지 않았다(원 2개로는
# 안 되는 형태다). 원본 픽셀을 그대로 쓴다. 96px 원본이라 32px 표시에서 3배 DPI 까지
# 선명하다. data URI 로 넣는 이유는 streamlit 이 임의 정적 파일을 서빙하지 않기 때문.
# 로고가 바뀌면 이 PNG 만 갈아끼우면 된다.
_LOGO_PATH = pathlib.Path(__file__).with_name("assets") / "kdic-logo.png"
try:
    _SPIN_SRC = "data:image/png;base64," + base64.b64encode(_LOGO_PATH.read_bytes()).decode()
except OSError:                     # 자산이 없어도 앱은 죽지 않는다 — 스피너만 빠진다
    _SPIN_SRC = ""
_SPIN_IMG = (f'<img class="kdic-spin" src="{_SPIN_SRC}" width="32" height="32" alt="">'
             if _SPIN_SRC else "")


def loading(message: str, note: str = "") -> None:
    """답변이 그려질 자리에 그대로 뜨는 로딩 상태 — 오버레이·별도 로딩 화면 없음."""
    note_html = f'<p class="kdic-load-note">{html.escape(note)}</p>' if note else ""
    st.markdown(
        f'<div class="kdic-load">{_SPIN_IMG}'
        f'<div><p class="kdic-load-msg">{html.escape(message)}</p>{note_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def card(category: str, question: str) -> None:
    """추천 질문 카드의 텍스트 2줄. 클릭 버튼은 호출자가 같은 컨테이너에 붙인다."""
    st.markdown(f'<p class="kdic-card-cat">{category}</p>'
                f'<p class="kdic-card-q">{question}</p>', unsafe_allow_html=True)
