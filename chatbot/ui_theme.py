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
/* 전송 버튼 = KDIC RED 원형. 입력이 비면 streamlit 이 :disabled 를 걸어 주므로
   "입력 전 subtle / 입력 후 활성" 은 상태 하나로 갈린다 — JS 없이 :disabled 만 쓴다.
   hover·active 는 색 한 단계·2% 축소까지만. Enter 는 streamlit 기본 동작 그대로다. */
[data-testid="stChatInputSubmitButton"] {
  width: 2.15rem !important; height: 2.15rem !important; min-height: 2.15rem !important;
  flex: none !important; padding: 0 !important;
  border: 0 !important; border-radius: 50% !important;
  background: #E30022 !important; color: #FFFFFF !important;
  transition: background .12s ease, transform .12s ease;
}
[data-testid="stChatInputSubmitButton"] svg { width: 1.05rem; height: 1.05rem; }
[data-testid="stChatInputSubmitButton"]:hover:not(:disabled) { background: #C4001C !important; }
[data-testid="stChatInputSubmitButton"]:active:not(:disabled) { transform: scale(.96); }
[data-testid="stChatInputSubmitButton"]:disabled {
  background: #F1F3F5 !important; color: #ADB5BD !important;
}
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

/* ── 답변 블록 ──────────────────────────────────────────────────────────── */
/* 머리글 한 줄(예봄 답변 + 부가정보) → 본문 → 얇은 선 → 부속(조건·서식).
   박스는 쓰지 않는다. 구분은 여백과 1px 선까지만. */
.kdic-ans-head {
  display: flex; align-items: baseline; flex-wrap: wrap; gap: .55rem;
  margin: .1rem 0 .55rem;
}
.kdic-ans-label {
  font-size: .72rem; font-weight: 700; letter-spacing: .06em; color: #003679;
  border-left: 2px solid #E30022; padding-left: .45rem;   /* RED 는 이 2px 만 */
}
.kdic-ans-meta { font-size: .72rem; color: #868E96; letter-spacing: .01em; }
.kdic-ans-sep { border: 0; border-top: 1px solid #E9ECEF; margin: 1.15rem 0 .85rem; }
/* 부속 블록 라벨 — 섹션 제목보다 한 단계 작게 */
.kdic-mini {
  font-size: .71rem; font-weight: 700; letter-spacing: .06em; color: #868E96;
  margin: 0 0 .4rem !important; line-height: 1.4;
}

/* 상태 안내 — 색 면적 대신 왼쪽 2px 선으로 본문과 가른다 */
.kdic-notice {
  border-left: 2px solid #003679; background: #F7F9FC;
  padding: .55rem .8rem; border-radius: 0 5px 5px 0;
  font-size: .85rem; color: #343A40; line-height: 1.55;
  margin: .35rem 0 .6rem !important;
}

/* 읽기 전용 조건 칩(과거 턴) — 버튼이 아니라 글자 태그다 */
.kdic-chips { display: flex; flex-wrap: wrap; gap: .3rem; margin: .1rem 0 .7rem; }
.kdic-chip {
  font-size: .74rem; color: #6C757D; line-height: 1.4;
  border: 1px solid #E9ECEF; border-radius: 999px; padding: .16em .65em;
}
.kdic-chip b { color: #343A40; font-weight: 600; }

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

/* ── 확정된 조건 ────────────────────────────────────────────────────────── */
/* 패널이 아니라 칩 줄이다 — 껍데기를 없애고 칩만 남긴다. 해제(✕)는 칩 자체가 겸한다.
   버튼 배치·반환값은 그대로고 모양만 바뀐다. */
[class*="st-key-kdic-slots-"] { gap: .3rem !important; margin: .1rem 0 .75rem !important; }
[class*="st-key-kdic-slots-"] [data-testid="stElementContainer"] { margin-bottom: 0; }
[class*="st-key-kdic-slots-"] .stButton button {
  width: auto !important; min-height: 0 !important;
  padding: .22em .7em !important; border-radius: 999px !important;
  background: #FFFFFF !important; border: 1px solid #DEE2E6 !important;
  font-size: .75rem !important; font-weight: 500 !important; color: #495057 !important;
}
[class*="st-key-kdic-slots-"] .stButton button:hover {
  background: #FFFFFF !important; border-color: #E30022 !important; color: #E30022 !important;
}

/* ── 후속 추천 태그 (`접수수단 · 온라인` 류) ─────────────────────────────── */
/* 카드가 아니라 선택형 태그다 — 글자 길이만큼만 차지하고 넘치면 다음 줄로 접힌다 */
[class*="st-key-kdic-fu-"] { gap: .35rem !important; margin: .1rem 0 .65rem !important; }
[class*="st-key-kdic-fu-"] [data-testid="stElementContainer"] { margin-bottom: 0; }
[class*="st-key-kdic-fu-"] .stButton button {
  width: auto !important; min-height: 0 !important;
  padding: .3em .8em !important; border-radius: 999px !important;
  background: #FFFFFF !important; border: 1px solid #DEE2E6 !important;
  font-size: .78rem !important; font-weight: 500 !important; color: #343A40 !important;
}
[class*="st-key-kdic-fu-"] .stButton button:hover {
  border-color: #003679 !important; background: #F4F6F8 !important; color: #003679 !important;
}

/* ── 업무별 추천 검색어: 뒤로가기 ───────────────────────────────────────── */
/* `← 착오송금 반환 신청` 은 **버튼 라벨 하나**다(app.py). 화살표와 업무명이 같은
   텍스트 노드라 글꼴·line-height·baseline 이 구조적으로 일치한다 — 두 요소를 나란히
   놓고 margin 으로 맞추는 구조가 아니다. 여기서는 버튼 껍데기만 벗겨 제목처럼 만든다.
   클릭 영역은 줄 전체(24px 이상)라 보이는 글자 위치를 밀지 않는다. */
.st-key-kdic-back [data-testid="stElementContainer"] { margin-bottom: 0; }
.st-key-kdic-back .stButton button {
  width: auto !important; min-height: 24px !important;
  padding: 0 .2rem !important; margin: 0 0 .5rem -.2rem !important;
  background: transparent !important; border: 0 !important; border-radius: 3px !important;
  justify-content: flex-start !important;
}
/* streamlit 이 라벨을 <p> 로 감싼다 — 제목 typography 는 이 <p> 에 건다 */
.st-key-kdic-back .stButton button p {
  margin: 0 !important; text-align: left;
  font-size: .86rem !important; font-weight: 700 !important; line-height: 24px !important;
  color: #212529 !important;
}
.st-key-kdic-back .stButton button:hover { background: #E9EDF2 !important; }
.st-key-kdic-back .stButton button:hover p { color: #003679 !important; }

/* ── 되묻기 맥락 칩 ─────────────────────────────────────────────────────── */
/* 진행 바도 단계 번호도 아니다 — 지금 어느 업무 흐름에 있는지만 글자 크기에 비례한
   최소 여백으로 남긴다. 칩 자체가 취소 조작 영역이다(두 번 누르면 취소). */
.st-key-kdic-branch { margin: .1rem 0 .55rem !important; }
.st-key-kdic-branch [data-testid="stElementContainer"] { margin-bottom: 0; }
.st-key-kdic-branch .stButton button {
  width: auto !important; min-height: 0 !important;
  padding: .18em .7em !important; border-radius: 999px !important;
  background: transparent !important; border: 1px solid #DEE2E6 !important;
  font-size: .74rem !important; font-weight: 600 !important; color: #6C757D !important;
  letter-spacing: .01em;
}
.st-key-kdic-branch .stButton button:hover {
  background: transparent !important; border-color: #ADB5BD !important; color: #495057 !important;
}

/* ── 되묻기 선택지 ──────────────────────────────────────────────────────── */
/* 추천 질문 카드와 같은 시각 언어(연회색 1px · radius 3px · 네이비 hover).
   누르면 바로 다음 질문으로 간다 — 확인 버튼이 없으므로 강조도 필요 없다. */
[class*="st-key-kdic-opts-"] .stButton button {
  border: 1px solid #DEE2E6 !important; border-radius: 999px !important;
  background: #FFFFFF !important; color: #212529 !important;
  padding: .38rem .9rem !important; min-height: 2.1rem !important;
}
[class*="st-key-kdic-opts-"] .stButton button:hover {
  border-color: #003679 !important; background: #F4F6F8 !important; color: #003679 !important;
}
/* 탈출구 2종은 선택지가 아니다 — 테두리를 빼 한 단계 뒤로 물린다 */
[class*="st-key-kdic-esc-"] .stButton button {
  border: 0 !important; background: transparent !important;
  color: #6C757D !important; font-size: .8rem !important; min-height: 1.9rem !important;
  padding: .2rem .4rem !important;
}
[class*="st-key-kdic-esc-"] .stButton button:hover {
  background: transparent !important; color: #003679 !important;
}

/* ── 오류 신고 인라인 아코디언 (지원 카드 안) ───────────────────────────── */
.st-key-kdic-report {
  background: #F4F6F8 !important; border: 1px solid #DEE2E6 !important;
  border-radius: 6px !important;
  padding: .65rem .75rem .35rem !important; margin-top: .45rem !important;
}
/* ── 예봄 브랜드: 헤더 아바타 ──────────────────────────────────────────── */
/* 서비스명 옆 캐릭터 하나. 로딩 화면에서 본 얼굴을 본 화면에서 다시 만나게 한다. */
.kdic-brand { display: flex; align-items: center; gap: .7rem; }
.kdic-avatar { flex: none; width: 42px; height: 42px; object-fit: contain; }

/* 첫 화면 인사 — 빈 대화창이 "무엇을 물어도 되는 곳"임을 화자 이름으로 알린다 */
.kdic-welcome {
  font-size: 1.05rem; font-weight: 600; color: #212529;
  margin: .1rem 0 1.1rem !important; line-height: 1.55;
}
.kdic-welcome b { color: #003679; font-weight: 700; }

/* ── 예봄 진입 로딩 화면 ────────────────────────────────────────────────── */
/* 세션 첫 런에만 DOM 에 들어가고, **같은 런 안에서 app.py 가 지운다**(placeholder
   `.empty()`). 사라지는 시점을 이 애니메이션에 맡기면, 런이 끝날 때 streamlit 이
   요소 컨테이너를 remount 하면서 시계가 0으로 돌아가 화면이 한 번 더 뜬다.
   그래서 페이드아웃은 SPLASH_HOLD_SEC(3.0s) **안에서 끝나도록** 잡아 두고,
   실제 제거는 python 이 한다. 숨기는 JS 는 없다.
   z-index 는 streamlit 사이드바(999991)보다 위여야 화면 전체를 덮는다. */
/* 스플래시 본체는 fixed 라 흐름에서 빠지지만, streamlit 이 감싸는 요소 컨테이너의
   높이·margin(약 14px)은 그대로 남아 **첫 런에서만** 본 화면이 14px 길어진다
   (세로 스크롤이 생기고 그만큼 컬럼 폭이 줄어든다). 껍데기를 접어 흔적을 없앤다 —
   display:none 은 fixed 자식까지 같이 지우므로 흐름에서만 빼낸다. */
[data-testid="stElementContainer"]:has(.yebom-splash) {
  position: absolute !important;
  height: 0 !important; min-height: 0 !important; margin: 0 !important;
}
.yebom-splash {
  position: fixed; inset: 0; z-index: 2147483000;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: #FFFFFF;
  animation: yebom-out .5s ease 2.4s forwards;   /* 2.9s 소멸 < 3.0s 제거 */
}
/* 캐릭터 + 서비스명 + 보조문구 + 점 = 한 덩어리. 부모의 flex 중앙정렬 하나로
   수평·수직 정중앙에 놓인다 — 덩어리 밖에 여백을 만드는 요소를 두지 않는다. */
.yebom-caption {
  display: flex; flex-direction: column; align-items: center;
}
@keyframes yebom-out { to { opacity: 0; visibility: hidden; } }
.yebom-splash img { width: 168px; height: auto; animation: yebom-in .6s ease both; }
.yebom-splash .yebom-name {
  font-size: 1.85rem; font-weight: 700; letter-spacing: -.02em; color: #003679;
  margin: .5rem 0 0 !important; animation: yebom-in .6s ease .08s both;
}
.yebom-splash .yebom-sub {
  font-size: .85rem; color: #6C757D; margin: .4rem 0 0 !important;
  animation: yebom-in .6s ease .16s both;
}
/* 로딩 점 3개 — Navy→Red 그라데이션을 여기 한 곳에만 쓴다(면적으로 쓰지 않는다) */
.yebom-dots { display: flex; gap: .42rem; margin-top: 1.6rem; }
.yebom-dots i {
  width: 6px; height: 6px; border-radius: 50%;
  background: linear-gradient(135deg, #003679, #E30022);
  opacity: .25; animation: yebom-dot 1.25s ease-in-out infinite;
}
.yebom-dots i:nth-child(2) { animation-delay: .16s; }
.yebom-dots i:nth-child(3) { animation-delay: .32s; }
@keyframes yebom-in { from { opacity: 0; transform: scale(.97); } }
@keyframes yebom-dot { 50% { opacity: .85; } }
/* 페이드아웃은 화면을 걷어내는 동작이라 남긴다 — 등장 연출과 점만 멈춘다 */
@media (prefers-reduced-motion: reduce) {
  .yebom-splash img, .yebom-name, .yebom-sub { animation: none; }
  .yebom-dots i { animation: none; opacity: .45; }
}
</style>

"""


# 예봄 캐릭터 원본 — `assets/yebom.png` (288px RGBA). 스플래시(168px)와 헤더
# 아바타(42px)가 같은 파일을 쓴다. 헤더 아바타는 매 rerun 마다 data URI 로 다시
# 실리므로 원본 자체를 표시 크기의 2배 선에서 유지한다 — 더 키우면 rerun 마다
# 그만큼 더 나간다. 캐릭터가 바뀌면 이 PNG 만 같은 규격으로 갈아끼우면 된다.
YEBOM_PATH = pathlib.Path(__file__).with_name("assets") / "yebom.png"
try:
    _YEBOM_SRC = "data:image/png;base64," + base64.b64encode(YEBOM_PATH.read_bytes()).decode()
except OSError:                     # 자산이 없어도 앱은 죽지 않는다 — 캐릭터만 빠진다
    _YEBOM_SRC = ""


def inject() -> None:
    """페이지당 1회 호출. 스타일 외 부작용 없음."""
    st.markdown(_CSS, unsafe_allow_html=True)


def header(title: str, subtitle: str, tag: str = "") -> None:
    """서비스 헤더 — 예봄 캐릭터 + 서비스명 + 설명 1줄. `st.title`(이모지 h1) 대체."""
    tag_html = f'<span class="kdic-tag">{tag}</span>' if tag else ""
    avatar = (f'<img class="kdic-avatar" src="{_YEBOM_SRC}" alt="예봄">'
              if _YEBOM_SRC else "")
    st.markdown(
        f'<div class="kdic-header"><div class="kdic-brand">{avatar}<div>'
        f'<p class="kdic-title">{title}{tag_html}</p>'
        f'<p class="kdic-sub">{subtitle}</p>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )


def welcome(text: str) -> None:
    """첫 화면 인사 한 줄 — 화자(예봄)를 대화가 시작되기 전에 밝힌다."""
    st.markdown(f'<p class="kdic-welcome">{text}</p>', unsafe_allow_html=True)


def splash(slot=None, name: str = "예봄", subtitle: str = "예금보험공사 AI 안내"):
    """세션 첫 런에만 그리는 진입 로딩 화면. **자리(placeholder)를 돌려준다.**

    앱 초기화를 막지 않는다 — 요소를 하나 뱉을 뿐이다. 페이드아웃은 CSS 가 하지만
    **제거는 호출자가 같은 런 안에서** `.empty()` 로 한다: 요소가 남은 채 런이 끝나면
    streamlit 프론트의 remount 로 애니메이션이 되감겨 화면이 두 번 뜬다(app.py 주석).
    자산이 없으면 이름만 뜬다 — 앱은 죽지 않는다.
    """
    img = f'<img src="{_YEBOM_SRC}" alt="">' if _YEBOM_SRC else ""
    # 호출자가 잡아 둔 자리를 쓴다 — 여기서 새로 만들면 첫 런에만 요소가 생겨
    # 뒤따르는 요소 인덱스가 런마다 달라진다(app.py 스플래시 주석).
    slot = st.empty() if slot is None else slot
    slot.markdown(
        f'<div class="yebom-splash">{img}'
        f'<div class="yebom-caption">'
        f'<p class="yebom-name">{html.escape(name)}</p>'
        f'<p class="yebom-sub">{html.escape(subtitle)}</p>'
        f'<div class="yebom-dots"><i></i><i></i><i></i></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    return slot


def section(label: str) -> None:
    """본문 섹션 라벨 — h2/h3 를 쓰면 위계가 헤더와 겹친다."""
    st.markdown(f'<p class="kdic-section">{label}</p>', unsafe_allow_html=True)


def answer_head(meta: str = "", label: str = "예봄 답변") -> None:
    """답변 블록 머리 — 작은 라벨 + (있으면) 출처·신뢰도 한 줄.

    본문 위 한 줄이 전부다. 박스를 두르지 않는다 — 답변 본문이 중심 콘텐츠다.
    `meta` 는 호출자가 이미 만들어 둔 문자열 그대로 쓴다(문구를 만들지 않는다).
    """
    meta_html = f'<span class="kdic-ans-meta">{html.escape(meta)}</span>' if meta else ""
    st.markdown(
        f'<div class="kdic-ans-head">'
        f'<span class="kdic-ans-label">{html.escape(label)}</span>{meta_html}</div>',
        unsafe_allow_html=True,
    )


def answer_sep() -> None:
    """답변 본문과 부속(조건·서식) 사이 얇은 구분선."""
    st.markdown('<hr class="kdic-ans-sep">', unsafe_allow_html=True)


def mini(label: str) -> None:
    """부속 블록 라벨 (예: '확정된 조건')."""
    st.markdown(f'<p class="kdic-mini">{html.escape(label)}</p>', unsafe_allow_html=True)


def notice(text: str) -> None:
    """상태 안내 — st.info 의 파란 판 대신 왼쪽 2px 선. 본문과는 확실히 갈린다."""
    st.markdown(f'<p class="kdic-notice">{html.escape(text)}</p>', unsafe_allow_html=True)


def chips(pairs) -> None:
    """읽기 전용 조건 태그 줄 (과거 턴). 조작할 수 없으므로 버튼이 아니다."""
    if not pairs:
        return
    body = "".join(
        f'<span class="kdic-chip">{html.escape(lab)} <b>{html.escape(str(val))}</b></span>'
        for lab, val in pairs
    )
    st.markdown(f'<div class="kdic-chips">{body}</div>', unsafe_allow_html=True)


# 스피너 이미지 — KDIC 링 로고 실물(`assets/kdic-spinner.png`, 96px RGBA, 흰 배경 제거).
# 손으로 그린 SVG 로는 양 끝 테이퍼와 두 곡선 사이 흰 간격이 재현되지 않았다(원 2개로는
# 안 되는 형태다). 원본 픽셀을 그대로 쓴다. 96px 원본이라 32px 표시에서 3배 DPI 까지
# 선명하다. data URI 로 넣는 이유는 streamlit 이 임의 정적 파일을 서빙하지 않기 때문.
# 로고가 바뀌면 이 PNG 만 갈아끼우면 된다.
_LOGO_PATH = pathlib.Path(__file__).with_name("assets") / "kdic-spinner.png"
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
