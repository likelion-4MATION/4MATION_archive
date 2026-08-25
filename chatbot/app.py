"""chatbot/app.py — 실전2 end 데모 Streamlit UI (큐폼 E2E 배선).

동결 계약 answer() -> {text, sources, confidence, route, checks, _meta}만 소비한다.
confidence 표기는 07-22 결정대로 "관련 문서 유사도"(정답 확신도 아님).

큐폼 배선 (Qform_ver2):
    질의 → classify_query_bf(질의) **1회** → extract(결정론, 콜 0) → next_question?
         ├ 있으면 되묻기(최대 2턴). **되묻기 턴에는 answer()를 부르지 않는다** → HCX 콜 0
         └ 없으면 answer(query, qform=slots) → 첨부 후단 필터

상태 전이는 `qform_flow` 가 전담한다. 이 파일은 **렌더와 토글만** 맡는다 —
갈라둬야 UI 없이 전이 규칙을 실측할 수 있다(`verify_qform_e2e.py`).

업무 판정(bf)은 app 층에서 1회 계산해 extract 에 주입한다(E3). 이 주입점이 나중에
MoAI 라우터가 꽂힐 자리다. 부스트 ON 으로 검색 쿼리가 바뀌어도 슬롯 필터가 보는
업무는 그대로다.

쿼리 부스트(serialize)는 **기본 OFF**. 검색 동작을 바꾸므로 450셋 회귀 수치가 나오기
전에는 켜지 않는다(§1-4 no numbers, no merge). 사이드바 토글로 시연 중 비교만 가능.
되묻기 문구 모드도 **기본 ⓐ 템플릿(콜 0)**. ⓑ는 비교용이다.

ver3 T5 — 되묻기 선택지 버튼과 예시 질의 칩을 붙였다. 둘 다 **콜 0**이고, 값·문구를
이 파일이 만들지 않는다. 버튼 값은 `qform_flow.options()`(조합 테이블 생존 행),
칩 문구는 `docs/qform_시험질의셋.md` 원문이다. 렌더가 값을 창작하면 그 순간
"근거 있는 답변"이라는 주장이 무너진다.

실행: streamlit run chatbot/app.py
주의: chain.CALL_BUDGET(70콜, 재시도 포함)을 공유 — 소진 시 앱 재시작으로 리셋.
"""
import json
import pathlib
import sys
import uuid
from datetime import datetime, timezone

import streamlit as st
import streamlit.components.v1 as components

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "chatbot"))
sys.path.insert(0, str(ROOT / "crawler"))
sys.path.insert(0, str(ROOT / "admin"))

import chain
import orchestrator
import oos_store
import qform_flow
import qform_followup
import qform_memory_panel as qmp
import qform_panel
import qform_state
import qform_trace

ROUTE_LABEL = {"rag": "문서 기반 답변", "link": "타기관 안내", "reject": "소관 밖",
               "oos": "안내 범위 밖 처리"}
SLOT_LABEL = {"party": "역할", "sub_task": "세부주제", "qualification": "자격",
              "subject": "주체", "method": "접수수단"}
ASK_MODES = {"ⓐ 템플릿 (콜 0)": "template", "ⓑ LLM 생성 (턴당 1콜)": "llm"}

MAX_VISIBLE_OPTIONS = 6         # 선택지 버튼 노출 상한. 넘으면 접는다 (T5 B1-4)
LOW_CALL_WARN = 10              # 남은 HCX 콜이 이 이하면 사이드바에 경고 (T7 B6)

# ── 에러 문구 (T7 B6-3) ─────────────────────────────────────────────────────
# `_meta.error` 원문을 화면에 그대로 뿌리면 안 된다. `chain._hcx` 는 실패 시
# `http_{status}:{응답 본문 200자}` 를 담는데, 그 본문에 엔드포인트·토큰·요청 ID 가
# 섞여 나올 수 있다. **코드를 사람 문구로 갈아 끼우고, 숫자 상태 코드만 통과시킨다.**
import re  # noqa: E402  (에러 코드 파싱 전용)

_ERROR_TEXT = {
    "call_budget_exhausted":
        "이번 세션의 모델 호출 예산을 모두 사용했습니다. 앱을 다시 시작하면 초기화됩니다. "
        "되묻기·선택지·슬롯 수정은 예산과 무관하게 계속 쓰실 수 있습니다.",
}
_HTTP_RE = re.compile(r"^http_(\d{3})")


def humanize_error(code) -> str:
    """`_meta.error` → 사람이 읽을 문구. **원문·URL·키·스택트레이스를 노출하지 않는다.**"""
    code = str(code or "")
    if code in _ERROR_TEXT:
        return _ERROR_TEXT[code]
    m = _HTTP_RE.match(code)
    if m:                       # 상태 코드 세 자리만 통과 — 응답 본문은 버린다
        return f"모델 서버에서 응답을 받지 못했습니다 (통신 오류 {m.group(1)}). 잠시 후 다시 시도해 주세요."
    if code.startswith("exception:"):
        return "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
    return "일시적인 오류로 답변을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."

# ── 예시 질의 칩 (T5 B2) ────────────────────────────────────────────────────
# 문구는 `docs/qform_시험질의셋.md` 에서 **그대로** 가져온다. 임의 창작 금지 —
# 조합 테이블·시험 질의셋 밖 문구를 만들지 않는다(CLAUDE.md §2-4·§2-5).
#
#   착오송금 반환 신청  ← 시험 질의셋 B1 (되묻기 1턴 경로. 선택지 버튼이 바로 보이는 진입점)
#   예금자보호제도      ← 시험 질의셋 E1
#   예금보험금 안내     ← 시험 질의셋 E4
#   채무조정 안내       ← 시험 질의셋 E2
#   은닉재산 신고       ← 시험 질의셋 E3
#   고객 미수령금 신청  ← **`crawler/data/testset_natural_450.jsonl` 수록 문구** (08-11 결정)
#       이 업무만 시험 질의셋에 항목이 없다. 지어내는 대신 450셋에서 그대로 가져왔다
#       (해당 업무 77건 중 classify 판정이 일치하는 문구). 원천이 둘인 유일한 칩이다.
EXAMPLE_CHIPS = [
    ("착오송금 반환 신청", "착오송금 반환 신청 서류가 뭐예요?"),
    ("예금자보호제도", "예금보호한도가 얼마인가요?"),
    ("예금보험금 안내", "예금보험금은 어떻게 신청하나요?"),
    ("고객 미수령금 신청", "고객 미수령금은 어떻게 조회하고 신청하나요?"),
    ("채무조정 안내", "채무조정 신청하려면 어떻게 해요?"),
    ("은닉재산 신고", "은닉재산 신고하면 포상금 얼마나 받나요?"),
]

# 업무 도메인 아이콘 — EXAMPLE_CHIPS 라벨과 1:1. 장식용(이모지)일 뿐 판정에 안 쓴다.
DOMAIN_ICONS = {
    "착오송금 반환 신청": "💸",
    "예금자보호제도": "🛡️",
    "예금보험금 안내": "💰",
    "고객 미수령금 신청": "🔍",
    "채무조정 안내": "🤝",
    "은닉재산 신고": "🕵️",
}

# 슬롯 추출 스코프 라벨 → `qform_config.SPEC["QFORM_SCOPE"]` 허용값. 첫 항목이 기본값이다.
SCOPE_LABELS = {"착오송금 단일 (기본)": "msdr", "착오송금 + 예금보험금": "msdr+dpin"}
_SCOPE_DEFAULT_LABEL = next(iter(SCOPE_LABELS))

st.set_page_config(page_title="KDIC 안내 챗봇 PoC", page_icon="💬", layout="wide")

# ── 레이아웃 CSS (ver6) ──────────────────────────────────────────────────────
# 좌·우 컬럼 안 맨 앞에 보이지 않는 마커(span)를 심어두고, `[data-testid="stColumn"]
# :has(.col-anchor-*)` 로 "그 마커를 담고 있는 컬럼"을 직접 골라낸다 — 형제 선택자로
# 옆 요소를 짚어가던 이전 방식보다 훨씬 안전하다(중첩 깊이가 바뀌어도 안 깨진다).
# 안쪽에 또 st.columns()가 있어도(도메인 그리드 등) 그 내부 컬럼엔 마커가 없어서
# 이 규칙이 걸리지 않는다.
st.markdown("""
<style>
/* Streamlit은 기본적으로 앱 전체를 뷰포트 높이에 고정하고(overflow:hidden) 그 안
   (stAppScrollToBottomContainer, chat_input이 있으면 생김)만 내부 스크롤시킨다 —
   좌·우를 sticky로 고정하려면 페이지 자체가 평범하게 스크롤돼야 하므로 풀어준다.
   중간 래퍼(stMainBlockContainer·stHorizontalBlock)에 overflow:hidden이 섞여 있으면
   sticky가 조용히 무효화되므로 같이 열어준다. */
[data-testid="stApp"][data-testid="stApp"],
[data-testid="stAppViewContainer"][data-testid="stAppViewContainer"],
[data-testid="stAppScrollToBottomContainer"][data-testid="stAppScrollToBottomContainer"],
[data-testid="stMainBlockContainer"][data-testid="stMainBlockContainer"],
[data-testid="stHorizontalBlock"][data-testid="stHorizontalBlock"] {
    position: static !important; height: auto !important; min-height: 0 !important;
    overflow: visible !important; overflow-y: visible !important;
}
body { min-height: 100vh; }

/* 색 하나로 통일 — 좌·우 배경, 사용자 말풍선 모두 이 회색 하나만 쓴다 */
:root {
    --panel-gray: #F1F3F4;
    --panel-title-size: 1.02rem;  /* "세션 상태" 같은 소제목 크기 */
    --metric-value-size: 2rem;    /* HCX 콜 "8 / 70" 숫자 크기 — 제목보다 눈에 띄게 크게 */
    --ui-red: #FF4B4B;            /* Streamlit 기본 테마 primaryColor — 대화 초기화 버튼과 같은 빨강 */
}

[data-testid="stColumn"]:has(.col-anchor-left),
[data-testid="stColumn"]:has(.col-anchor-right) {
    position: sticky; top: 4.5rem; align-self: flex-start;
    max-height: calc(100vh - 6rem); overflow-y: auto;
    background: var(--panel-gray); border-radius: 14px; padding: 0.9rem 1.05rem;
    scrollbar-width: none;
}
[data-testid="stColumn"]:has(.col-anchor-left)::-webkit-scrollbar,
[data-testid="stColumn"]:has(.col-anchor-right)::-webkit-scrollbar { display: none; }

/* 왼쪽·오른쪽 안 글자·버튼·간격을 촘촘하게 — 스크롤을 줄인다 */
[data-testid="stColumn"]:has(.col-anchor-left) h2, [data-testid="stColumn"]:has(.col-anchor-left) h3,
[data-testid="stColumn"]:has(.col-anchor-left) h4,
[data-testid="stColumn"]:has(.col-anchor-right) h2, [data-testid="stColumn"]:has(.col-anchor-right) h3,
[data-testid="stColumn"]:has(.col-anchor-right) h4 {
    font-size: var(--panel-title-size) !important; margin-top: .2rem !important; margin-bottom: .2rem !important;
}
[data-testid="stColumn"]:has(.col-anchor-left) p, [data-testid="stColumn"]:has(.col-anchor-left) .stMarkdown,
[data-testid="stColumn"]:has(.col-anchor-left) [data-testid="stCaptionContainer"],
[data-testid="stColumn"]:has(.col-anchor-right) p, [data-testid="stColumn"]:has(.col-anchor-right) .stMarkdown,
[data-testid="stColumn"]:has(.col-anchor-right) [data-testid="stCaptionContainer"] {
    font-size: .83rem !important; line-height: 1.35 !important;
}
[data-testid="stColumn"]:has(.col-anchor-left) button,
[data-testid="stColumn"]:has(.col-anchor-right) button {
    font-size: .82rem !important; padding: .3rem .55rem !important; min-height: 2rem !important;
}
[data-testid="stColumn"]:has(.col-anchor-left) [data-testid="stVerticalBlock"],
[data-testid="stColumn"]:has(.col-anchor-right) [data-testid="stVerticalBlock"] {
    gap: .35rem !important;
}
[data-testid="stColumn"]:has(.col-anchor-left) [data-testid="stMetricValue"] {
    font-size: var(--metric-value-size) !important;
}
[data-testid="stColumn"]:has(.col-anchor-left) hr, [data-testid="stColumn"]:has(.col-anchor-right) hr {
    margin: .5rem 0 !important;
}
/* 회색 배경 위 항목 카드는 흰색으로 — 배경과 구분 (근거조각·추천질문·도메인 카드 등).
   `st.container(key=...)`에 "card-"로 시작하는 key를 주면 Streamlit이 그 컨테이너에
   st-key-card-... 클래스를 그대로 붙여준다 — 이 훅으로 카드만 콕 집어 흰 배경을 준다. */
[class*="st-key-card-"] {
    background: #FFFFFF !important; border-radius: 10px !important;
    padding: .5rem .65rem !important; margin-bottom: .4rem !important;
}

/* 업무별 추천 검색어(6×1)는 버튼별 특별 크기 규칙 없이 위 일반 버튼 규칙(font-size
   .82rem · min-height 2rem)을 그대로 쓴다 — "지금 뜨는 검색어" 카드와 같은 크기가
   된다. 한 줄 폭이 넓어져서(6×1) 라벨이 2줄로 넘어갈 일도 거의 없다. */

/* 추천 질문 카드의 "Q." 만 현재 테마 빨강으로 — 버튼 라벨은 일반 텍스트라
   문자 단위 스타일링이 안 되니 ::first-letter 로 첫 글자("Q")만 짚는다.
   qcard- 접두사(위 _render_question_cards)로 이 카드들에만 걸리게 한다. */
/* 실제 글자는 button > ... > p 안에 있다 — button 자체엔 ::first-letter가 안 먹는다
   (라이브 DOM으로 확인: button::first-letter는 무효, button p::first-letter는 유효). */
[class*="st-key-qcard-"] button p::first-letter { color: var(--ui-red) !important; }

/* 하단 입력창 가운데 정렬 — 폭 자체는 아래 JS(components.html)가 중앙 컬럼 실측값으로
   맞춘다. margin:auto만 CSS로 미리 걸어 두면 JS가 늦게 붙어도 어색하게 왼쪽에
   붙어있지 않는다. */
[data-testid="stBottomBlockContainer"] { margin-left: auto !important; margin-right: auto !important; }
</style>
""", unsafe_allow_html=True)

st.title("💬 KDIC 안내 챗봇 — PoC")
st.caption("예금보험공사 안내 문서에 근거해 답변합니다. (실전2 end 데모 · 큐폼 배선)")
title_col, report_col = st.columns([5, 1])
with title_col:
  
with report_col:
    st.write("")
    if st.button("🚩 챗봇 오류 신고", key="top-report", width="stretch"):
        st.session_state.report_confirm = True

st.session_state.setdefault("history", [])
st.session_state.setdefault("flow", qform_flow.new_state())
st.session_state.setdefault("needs_regen", False)   # 슬롯 수정 후 재답변 대기 (T6)
st.session_state.setdefault("session_id", f"sess_{uuid.uuid4().hex[:16]}")
st.session_state.setdefault("report_confirm", False)
st.session_state.setdefault("report_notice", None)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_history(turn: dict) -> dict:
    item = {**turn, "message_id": turn.get("message_id") or f"msg_{uuid.uuid4().hex[:16]}",
            "timestamp": turn.get("timestamp") or _utc_now()}
    st.session_state.history.append(item)
    return item


def last_answer_id() -> str:
    for turn in reversed(st.session_state.history):
        if turn.get("role") == "answer":
            return str(turn.get("message_id") or "")
    return ""


def report_context() -> dict:
    flow = st.session_state.flow
    return {
        "session_id": st.session_state.session_id,
        "target_message_id": last_answer_id(),
        "payload": {
            "conversation": st.session_state.history,
            "model_version": chain.MODEL_NAME,
            "qform": flow.get("qform"),
            "slot_origin": flow.get("slot_origin"),
            "queue": flow.get("unit_queue"),
            "qform_queue": flow.get("queue"),
            "routing_history": flow.get("routing_history"),
            "call_count": chain._calls,
        },
    }


if st.session_state.report_notice:
    level, message = st.session_state.report_notice
    (st.success if level == "ok" else st.error)(message)
    st.session_state.report_notice = None

if st.session_state.report_confirm:
    st.warning("오류 분석을 위해 현재 대화 내용과 답변 처리 기록이 저장됩니다.")
    confirm_col, cancel_col, _ = st.columns([1, 1, 4])
    if confirm_col.button("신고하기", key="report-confirm", type="primary", width="stretch"):
        try:
            ctx = report_context()
            saved = oos_store.create_report(ctx["payload"], session_id=ctx["session_id"],
                                            report_path="top_button",
                                            target_message_id=ctx["target_message_id"])
            st.session_state.report_notice = ("ok", f"오류 신고가 접수되었습니다 ({saved['report_id']}).")
        except Exception:
            st.session_state.report_notice = ("error", "오류 신고를 저장하지 못했습니다. 접수된 것으로 처리하지 않았습니다.")
        st.session_state.report_confirm = False
        st.rerun()
    if cancel_col.button("취소", key="report-cancel", width="stretch"):
        st.session_state.report_confirm = False
        st.rerun()

# 좌측(정보) / 중앙(대화) / 우측(추천 질문·근거 조각) — 예시 UI(서울 열린데이터광장
# 챗봇) 레이아웃을 참고해 사이드바 대신 고정 3컬럼으로 구성한다.
# 좌·우 폭은 서로 같게, 중앙은 그보다 조금 더 크게.
left, center, right = st.columns([1.1, 2.3, 1.1])

with left:
    st.markdown('<span class="col-anchor-left"></span>', unsafe_allow_html=True)
    if st.button("🔄 대화 초기화", key="btn-reset-top", type="primary", width="stretch"):
        st.session_state.history = []
        st.session_state.flow = qform_flow.new_state()
        st.session_state.needs_regen = False
        st.session_state.session_id = f"sess_{uuid.uuid4().hex[:16]}"
        st.session_state["_pending_step"] = None
        st.rerun()
    st.divider()

    st.subheader("세션 상태")
    _left_calls = chain.CALL_BUDGET - chain._calls
    st.metric("HCX 콜 (재시도 포함)", f"{chain._calls} / {chain.CALL_BUDGET}")
    # 예산 경고 (T7 B6-1) — 소진되고 나서 알면 시연 도중에 막힌다. 미리 보여 준다.
    if _left_calls <= 0:
        st.error("모델 호출 예산 소진 — 새 답변을 만들 수 없습니다. "
                 "되묻기·선택지·슬롯 수정은 계속 동작합니다 (콜 0).")
    elif _left_calls <= LOW_CALL_WARN:
        st.warning(f"남은 모델 호출 {_left_calls}회. "
                   "경로에 따라 OOS 분류 또는 답변 생성에 호출을 씁니다.")
    st.caption("되묻기 턴은 ⓐ 모드에서 콜을 쓰지 않습니다. 예산 소진 시 앱 재시작으로 리셋됩니다.")

    # 예시 UI처럼 좌측은 세션 상태 · 근거 문서만 상시 노출한다. 큐폼 설정(및 트레이스 토글)은
    # 접어 둔다 — 기능은 그대로고, 접혀 있어도 위젯 상태는 유지된다(Streamlit 특성).
    with st.expander("⚙️ 큐폼 설정"):
        st.radio(
            "되묻기 문구", list(ASK_MODES), index=0, key="ask_mode_label",
            help="ⓐ는 조합 테이블 값을 CSV 문구에 끼워 넣습니다(LLM 콜 0). "
                 "ⓑ는 같은 판정 결과를 LLM이 한 문장으로 다듬습니다. 값 고정 가드를 어기면 "
                 "ⓐ로 폴백하고 사유를 남깁니다 — 어느 쪽이 나은지는 비교해 보고 정합니다.",
        )
        st.checkbox(
            "쿼리 부스트 (실험)", value=False, key="boost",
            help="슬롯 값을 검색 쿼리에 덧붙입니다. 검색 동작이 바뀌므로 450셋 회귀 수치가 "
                 "나오기 전까지는 기본 OFF입니다. 첨부 후단 필터는 토글과 무관하게 항상 동작합니다.",
        )
        # ver4 M8-b — `QFORM_SCOPE` 는 M5 에서 SPEC 에 신설했는데 화면에 없었다.
        # **종합 관리자 콘솔이 읽을 자리**라 여기에 노출한다. 기본값은 `msdr`(착오송금 단일) 유지 —
        # 확장 전환은 `verify_qform_e2e.py`(동결) AC5 fixture 와 충돌해 보류돼 있다(HOLES H39).
        st.selectbox(
            "슬롯 추출 스코프", list(SCOPE_LABELS), index=0, key="qform_scope_label",
            help="msdr=착오송금 단일(기본·현행). msdr+dpin=예금보험금 포함. "
                 "확장은 실측만 끝났고 기본값 전환은 보류 상태입니다(HOLES H39).",
        )
        st.checkbox("트레이스 패널", value=False, key="show_trace",
                    help="질의 1건이 어느 층에서 어떻게 갈렸는지 보여줍니다. "
                         "좌측을 세션 상태·근거 문서 위주로 단순하게 유지하려고 기본은 꺼둡니다.")
        st.caption("첨부 후단 필터는 항상 켜져 있습니다 (슬롯이 비면 자동으로 기존 동작).")
        st.divider()
        st.caption(
            "표시되는 유사도는 질문-문서 관련도이며 정답 확신도가 아닙니다. "
            "검증 플래그는 참고용이며 답변을 차단하지 않습니다."
        )

ASK_MODE = ASK_MODES[st.session_state.get("ask_mode_label", "ⓐ 템플릿 (콜 0)")]
BOOST = bool(st.session_state.get("boost"))
# 좌측 큐폼 설정 → 정책 오버라이드. `qform_config.resolve()` 가 허용범위 밖 값을 기본값으로 되돌린다.
CONFIG = {"QFORM_SCOPE": SCOPE_LABELS[st.session_state.get("qform_scope_label",
                                                          _SCOPE_DEFAULT_LABEL)]}


# ══════════════════════════════════════════════════════════════════════════
# 렌더 헬퍼
# ══════════════════════════════════════════════════════════════════════════
def _fmt_size(n) -> str:
    if not n:
        return ""
    return f" · {n / 1024:.0f}KB" if n < 1024 * 1024 else f" · {n / 1024 / 1024:.1f}MB"


def render_slots(slots: dict, *, key_prefix: str = "", editable: bool = False) -> str | None:
    """채워진 슬롯 노출 — 기획서 §7 '조용히 반영 금지'. 사용자가 보고 **고칠 수 있어야** 한다.

    editable 이면 슬롯마다 해제 버튼을 붙이고, 눌린 슬롯 이름을 돌려준다(T6 B3).
    ver2 는 표시만 했다 — 보이지만 고칠 수 없으면 §7 을 절반만 지킨 것이다.
    과거 턴에는 안 붙인다. 지금 상태가 아닌 것을 고치는 시늉이 되기 때문이다.
    """
    filled = [(f, SLOT_LABEL.get(f, f), v) for f, v in slots.items()
              if f in qform_state.SLOT_FIELDS and v]
    if not filled:
        return None
    if not editable:
        st.caption("🎯 " + " · ".join(f"{lab} **{v}**" for _, lab, v in filled))
        return None

    unset = None
    st.caption("🎯 확정된 조건 — 잘못 잡혔으면 ✕ 로 풀고 다시 고르세요")
    for col, (f, lab, v) in zip(st.columns(len(filled)), filled):
        if col.button(f"{lab} {v}  ✕", key=f"unset-{key_prefix}-{f}", width="stretch",
                      help=f"'{lab}' 조건을 해제하고 되묻기를 다시 받습니다 (HCX 콜 0)"):
            unset = f
    return unset


def render_attachments(atts: list, key_prefix: str) -> None:
    """근거 문서 첨부를 문서별로 그룹핑해 다운로드 버튼으로 렌더.

    로컬 실파일(abs_path)이 있으면 st.download_button(즉시 다운로드), 없으면 원문
    페이지 링크로 폴백. 히스토리 재렌더 충돌 방지를 위해 key에 prefix를 붙인다.
    """
    if not atts:
        return
    groups, order = {}, []
    for a in atts:
        title = a.get("doc_title") or a.get("doc_id")
        if title not in groups:
            groups[title] = []
            order.append(title)
        groups[title].append(a)
    with st.expander(f"📎 관련 서식·첨부파일 ({len(atts)}건)", expanded=True):
        for ti, title in enumerate(order):
            st.markdown(f"**{title}**")
            for ai, a in enumerate(groups[title]):
                kind = f"[{a['doc_kind']}] " if a.get("doc_kind") else ""
                fname = a.get("orig_filename") or "attachment"
                size = _fmt_size(a.get("file_size"))
                label = f"⬇ {kind}{a.get('label') or fname}  ·  {fname}{size}"
                key = f"att-{key_prefix}-{ti}-{ai}"
                if a.get("available") and a.get("abs_path"):
                    try:
                        data = pathlib.Path(a["abs_path"]).read_bytes()
                        st.download_button(
                            label, data=data, file_name=fname,
                            mime=a.get("mime") or "application/octet-stream", key=key,
                        )
                        continue
                    except OSError:
                        pass  # 읽기 실패 시 링크 폴백
                url = a.get("source_url") or ""
                st.markdown(f"- {kind}[{a.get('label') or fname}]({url}) — 원문 페이지에서 내려받기")


def render_evidence_card(r: dict) -> None:
    """근거 자료 카드 — 최종 답변의 근거 문서·검증 플래그. (첨부파일은 말풍선 쪽에 남는다.)

    말풍선(render_answer)에서 그리던 것과 **완전히 같은 모양**(접이식 라벨 포함)을
    그대로 우측 컬럼으로 옮긴 것뿐이다 — 데이터·판정 로직은 손대지 않았다.
    """
    if r.get("text") is None:
        st.caption("이 답변은 오류로 근거 자료가 없습니다.")
        return
    if r["sources"]:
        with st.expander("근거 문서"):
            for i, s in enumerate(r["sources"], 1):
                st.markdown(f"{i}. [{s['title']}]({s['url']})")
    if not r["checks"]["ok"]:
        with st.expander("⚑ 검증 플래그 (차단 아님)"):
            for f in r["checks"]["flags"]:
                st.markdown(f"- {f}")


def render_answer(r: dict, key_prefix: str = "live", slots: dict | None = None,
                  search_q: str | None = None, editable: bool = False,
                  followups: list[dict] | None = None) -> dict:
    """answer() 결과 1건 렌더 — 계약 4필드 + 부가(checks/_meta)만 사용.

    반환: {"unset": 해제 슬롯|None, "chip": 복구 칩 질의|None, "followup": 후속 질의|None}
    """
    out = {"unset": None, "chip": None, "followup": None}
    if r["text"] is None:
        # 대화를 죽이지 않는다 — 안내 문구 + 다음 행동(예시 칩)을 같이 낸다(T7 B6-2·3).
        st.warning(humanize_error(r["_meta"].get("error")))
        out["chip"] = render_chips(f"err-{key_prefix}")
        return out
    st.markdown(r["text"])
    if slots:
        out["unset"] = render_slots(slots, key_prefix=key_prefix, editable=editable)
    meta = r["_meta"]
    st.caption(
        f"{ROUTE_LABEL.get(r['route'], r['route'])}"
        f" · 관련 문서 유사도 {r['confidence']:.2f}"
        f" · {meta.get('latency_ms') or '?'}ms"
    )
    if search_q:
        st.caption(f"🔎 부스트 적용 검색어: `{search_q}`")
    # 근거 문서·검증 플래그는 우측 "근거 자료" 컬럼으로 옮겼다(render_evidence_card).
    # 첨부파일 다운로드는 대화 흐름과 붙어 있는 게 자연스러워 말풍선에 그대로 둔다.
    render_attachments(r.get("attachments") or [], key_prefix)
    action = (r.get("_meta") or {}).get("action")
    if action == "REFERRAL" and r.get("referral"):
        ref = r["referral"]
        st.caption(f"안내처 · {ref['org']}")
        if ref.get("url"):
            st.link_button("공식 안내 페이지", ref["url"])
        if ref.get("phone"):
            st.write(f"전화: {ref['phone']}")
        if ref.get("hours"):
            st.caption(f"운영시간: {ref['hours']}")
    if action == "PHONE_GUIDE":
        if st.button("유선 상담 안내", key=f"phone-{key_prefix}"):
            st.session_state[f"phone-open-{key_prefix}"] = True
        if st.session_state.get(f"phone-open-{key_prefix}"):
            guide = r.get("phone_guide")
            if guide:
                st.write(guide["message"])
                st.write(f"대표번호: {guide['phone']}")
                st.caption(f"운영시간: {guide['hours']}")
            else:
                st.caption("현재 게시·활성화된 유선 상담 정보가 없습니다.")
#    if not r["checks"]["ok"]:
#        with st.expander("⚑ 검증 플래그 (차단 아님)"):
#            for f in r["checks"]["flags"]:
#                st.markdown(f"- {f}")
#    우측 근거 

    # reject 복구 경로 (T6 B4) — 소관 밖이라고 끝내면 그 화면이 막다른 길이 된다.
    # **타기관 이름·URL 을 붙이지 않는다.** HOLES H7 이 열려 있어 근거가 없고,
    # 없는 기관을 안내하는 순간 R2(참고문서에 있는 내용만) 위반이다.
    # 할 수 있는 것은 "우리가 답할 수 있는 것"을 다시 보여 주는 것까지다.
    if r.get("route") == "reject":
        st.caption("다른 질문을 해보세요")
        out["chip"] = render_chips(f"rej-{key_prefix}")
    elif followups:
        out["followup"] = render_followups(followups, key_prefix)
    return out


def render_followups(items: list[dict], key_prefix: str) -> dict | None:
    """후속 질문 추천 (T7 B5). 클릭된 {"field","value"} 를 돌려준다. **HCX 콜 +0.**

    라벨은 `축 이름 · 조합 테이블 값` 이다. 축 이름은 화면이 이미 쓰던 `SLOT_LABEL`,
    값은 생존 행 그대로 — **문구를 만들지 않는다**(CLAUDE.md §2-4).
    착오송금 외 업무에서는 `items` 가 비어 이 함수가 아예 안 불린다. 정상이다(§2-5).

    클릭은 **새 질의가 아니라 슬롯 좁히기**로 흐른다(08-11 결정 · C안). 검색 쿼리를
    건드리지 않아야 회귀 트리거가 0으로 유지된다 — 자세한 사유는 `qform_followup` 참조.
    """
    if not items:
        return None
    picked = None
    st.caption("조건을 더 좁혀서 보기")
    for col, it in zip(st.columns(len(items)), items):
        lab = SLOT_LABEL.get(it["field"], it["field"])
        if col.button(f"{lab} · {it['value']}", width="stretch",
                      key=f"fu-{key_prefix}-{it['field']}-{it['value']}",
                      help=f"'{lab}'을(를) '{it['value']}'(으)로 두고 다시 답변받습니다"):
            picked = it
    return picked


def render_ask(turn: dict) -> None:
    """되묻기 턴 — 문구 + 남은 후보. ⓐ/ⓑ 구별과 폴백 사유를 캡션에 남긴다."""
    st.markdown(turn["prompt"])
    tag = "ⓐ 템플릿" if turn["mode"] == "template" else f"ⓑ LLM · 콜 {turn['calls']}"
    if turn.get("fallback"):
        tag += f" → ⓐ 폴백 ({turn['fallback']})"
    st.caption(f"남은 후보 {turn['remaining']}개 · 건너뛰어도 답변합니다 · {tag}")


_ESCAPE = "\x00escape"      # 렌더 층 내부 신호. 슬롯 값이 아니다(조합 테이블 밖으로 안 나간다)
_PASS = "\x00pass"


def render_options(opts: list[str], key_prefix: str) -> str | None:
    """되묻기 선택지 버튼 (T5 B1). 클릭된 값을 돌려준다.

    **라벨 = 조합 테이블 값 그대로.** 다듬거나 부연을 붙이지 않는다(C6·CLAUDE.md §2-4).
    버튼 경로는 값이 enum 에서 직접 오므로 슬롯 오추출이 구조적으로 0 이고,
    HCX 비결정성을 안 타서 시연이 결정론이 된다.

    key 에 턴 인덱스 prefix 를 붙여 히스토리 재렌더 충돌을 막는다(기존 관행).
    """
    if not opts:
        return None
    picked = None

    def _row(values: list[str], tag: str) -> None:
        nonlocal picked
        for col, v in zip(st.columns(len(values)), values):
            if col.button(v, key=f"opt-{key_prefix}-{tag}-{v}", width="stretch"):
                picked = v

    head, tail = opts[:MAX_VISIBLE_OPTIONS], opts[MAX_VISIBLE_OPTIONS:]
    for i in range(0, len(head), 3):
        _row(head[i:i + 3], f"h{i}")
    if tail:
        with st.expander(f"다른 선택지 보기 ({len(tail)}개)"):
            for i in range(0, len(tail), 3):
                _row(tail[i:i + 3], f"t{i}")
    # K9 — 빠른 답변은 키 조합이 아니라 **버튼**. 탈출구 로직은 ver2부터 구현·검증돼 있어
    # (verify_qform_e2e.py AC3) 여기서 하는 일은 **입구를 하나 더 여는 렌더링 변경**이다.
    # K5 — ⏭ pass 는 "이 슬롯은 답하지 않겠다". X(오염 차단)와 역할이 다르다.
    c1, c2 = st.columns(2)
    if c1.button("이대로 답변받기", key=f"opt-{key_prefix}-escape", width="stretch"):
        picked = _ESCAPE
    if c2.button("⏭ 이건 넘어갈게요", key=f"opt-{key_prefix}-pass", width="stretch"):
        picked = _PASS
    return picked


_TERMS_CACHE: dict | None = None


def term_caption(value: str) -> str | None:
    """선택지 값이 용어 사전의 `term` 이면 **`one_line` 전문**을 캡션으로 돌려준다.

    M1 판정 3 — **버튼 라벨 = `term` · 캡션 = `one_line` 전문.** `one_line` 은 코퍼스
    축자 문장이라 **자르지 않는다**(줄이는 순간 창작이다). 화면에서 줄이는 것은
    말줄임이 아니라 캡션으로 내리는 것으로 해결한다.
    현재 조합 테이블의 슬롯 값(본인·대리인·법인…)과 용어 사전의 term(예금보험금·
    가지급금…)은 교집합이 없어 이 경로는 **아직 발동하지 않는다** — D 되묻기를 구현하지
    않기로 했기 때문이다(08-18 M1 판정 1). 배선만 두고 재측정 대상으로 남긴다.
    """
    global _TERMS_CACHE
    if _TERMS_CACHE is None:
        import csv
        try:
            with (ROOT / "crawler" / "data" / "qform_terms_v0.csv").open(encoding="utf-8-sig") as fh:
                _TERMS_CACHE = {r["term"]: r["one_line"] for r in csv.DictReader(fh)}
        except Exception:
            _TERMS_CACHE = {}
    return _TERMS_CACHE.get(value)


def render_memory_panel(flow: dict, key_prefix: str = "mem") -> tuple | None:
    """메모리 패널 3구역 (ver4 M3). **렌더만 한다** — 모델·조작은 `qform_memory_panel`.

    반환: 클릭된 조작 `(op, kwargs)` 또는 None. 호출자가 `qmp.apply()` 로 넘긴다.
    `answer()` 는 어느 경로로도 호출되지 않는다(A3-2).
    """
    model = qmp.panel_model(flow)
    action = None
    st.subheader("기억")
    st.caption(f"이월 유효 {model['ttl']}턴 · 만료 항목은 회색으로 남습니다")
    for zone in model["zones"]:
        st.markdown(f"**{zone['name']}**")
        if not zone["items"]:
            st.caption("(없음)")
            continue
        for i, it in enumerate(zone["items"]):
            val = it.get("value")
            shown = ", ".join(val) if isinstance(val, list) else (val or "—")
            line = f"{it['label']} · {shown}"
            if it["status"] != qmp.ST_ACTIVE:
                st.caption(f"~~{line}~~  ({it['status']})")     # 회색 잔류 — 삭제하지 않는다
            else:
                st.write(line)
            st.caption(f"고치면 → {it['effect']}" + ("" if it["actionable"] else "  (표시 전용)"))
            cap = term_caption(shown)
            if cap:
                st.caption(cap)                                  # M1 판정 3 · one_line 전문
            if not it["actionable"]:
                continue
            cols = st.columns(len(it["ops"]) or 1)
            for col, op in zip(cols, it["ops"]):
                label = {"edit": "✏️", "clear": "❌", "pass": "⏭",
                         "move": "✏️ 순서", "drop": "❌"}[op]
                if col.button(label, key=f"{key_prefix}-{zone['name']}-{i}-{op}"):
                    if op in ("move", "drop"):
                        action = (op, {"index": it["index"], "delta": -1})
                    else:
                        action = (op, {"field": it["field"]})
    return action


def render_chips(key_prefix: str, items: list[tuple[str, str]] | None = None,
                 per_row: int = 3) -> str | None:
    """질의 칩 (T5 B2). 클릭된 질의 문구를 돌려준다.

    `items` 미지정 시 `EXAMPLE_CHIPS`(업무 6종, `docs/qform_시험질의셋.md` 원문) 사용.
    다른 출처(예: 코퍼스 FAQ 원문) 문구를 넣을 때도 **같은 원칙** — 화면이 문구를
    창작하지 않는다 — 을 지켜야 한다.
    """
    items = EXAMPLE_CHIPS if items is None else items
    picked = None
    for i in range(0, len(items), per_row):
        chunk = list(enumerate(items[i:i + per_row], start=i))
        for col, (idx, (label, query)) in zip(st.columns(len(chunk)), chunk):
            with col:
                # 버튼 자체가 이미 테두리 있는 박스라 st.container(border=True)로 한 번 더
                # 감싸면 네모가 2겹이 된다 — 감싸지 않고 버튼 하나만 둔다.
                # DOMAIN_ICONS에 있는 라벨(업무 6종)이면 이모지를 붙인다(우측 "업무별
                # 추천 검색어"와 같은 스타일). 없는 라벨(에러 복구용 등)은 그냥 텍스트.
                icon = DOMAIN_ICONS.get(label)
                shown = f"{icon}  {label}" if icon else label
                if st.button(shown, key=f"chip-{key_prefix}-{idx}", width="stretch",
                             help=query):
                    picked = query
    return picked


# ── 지금 뜨는 검색어 — 코퍼스 FAQ 페이지 원문에서만 뽑는다(EXAMPLE_CHIPS와 같은 원칙:
# 창작 금지). 코퍼스에 FAQ 페이지가 있는 업무만 자연히 포함된다(현재: 예금자보호제도,
# 은닉재산 신고 2종 — 나머지 업무는 FAQ 페이지 자체가 없어 후보에 안 뜬다).
_FAQ_Q_RE = re.compile(r"질문\s*\n(.+?)\n\s*답변", re.S)
_TRENDING_CACHE: list[str] | None = None


def _load_trending_questions(limit: int = 6) -> list[str]:
    global _TRENDING_CACHE
    if _TRENDING_CACHE is None:
        qs: list[str] = []
        try:
            with (ROOT / "crawler" / "data" / "chunks.jsonl").open(encoding="utf-8") as fh:
                for line in fh:
                    d = json.loads(line)
                    if "FAQ" not in (d.get("page_title") or ""):
                        continue
                    m = _FAQ_Q_RE.search(d.get("text") or "")
                    if m:
                        q = m.group(1).strip()
                        if q and q not in qs:
                            qs.append(q)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            qs = []
        _TRENDING_CACHE = qs
    return _TRENDING_CACHE[:limit]


# ── 분류별 추천 검색어 — 업무 도메인마다 여러 질문. `testset_natural_450.jsonl` 원문만
# 쓴다(팀 관례상 임의 창작 금지) — 이미 이 파일이 EXAMPLE_CHIPS 중 "고객 미수령금 신청"
# 칩 문구의 원천으로 쓰던 파일과 같다.
_DOMAIN_Q_CACHE: dict[str, list[str]] | None = None


def _load_domain_questions(limit: int = 5) -> dict[str, list[str]]:
    """업무별 자연어 질문(구어체 포함) — "현재 질문과 비슷한 질문"(문맥 추천) 전용.

    직전 질의와 같은 결로 자연스럽게 이어지게 구어체 파라프레이즈를 그대로 쓴다.
    """
    global _DOMAIN_Q_CACHE
    if _DOMAIN_Q_CACHE is None:
        by_bf: dict[str, list[str]] = {}
        try:
            with (ROOT / "crawler" / "data" / "testset_natural_450.jsonl").open(encoding="utf-8") as fh:
                for line in fh:
                    d = json.loads(line)
                    bf, q = d.get("business_function"), d.get("question")
                    if not bf or not q:
                        continue
                    lst = by_bf.setdefault(bf, [])
                    if q not in lst and len(lst) < limit:
                        lst.append(q)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            by_bf = {}
        _DOMAIN_Q_CACHE = by_bf
    return _DOMAIN_Q_CACHE


# ── 업무별 추천 검색어 — "대표 질문"(origin_question) 전용 풀. testset_natural_450.jsonl의
# 각 구어체 문항은 더 formal한 origin_question에서 파생됐다(예: "돌아가신 부모님 계좌가
# 어디 있는지 확인하는 서비스 있나요?" ← origin_question "상속인 금융거래 조회서비스란?").
# origin_question만 모으면 개인 사연이 섞인 구어체 없이 공적·대표적인 질문만 남고,
# "현재 질문과 비슷한 질문"(위 함수, question 원문 사용)과 자연히 겹치지 않는다.
_REP_DOMAIN_Q_CACHE: dict[str, list[str]] | None = None


def _load_representative_domain_questions(limit: int = 6) -> dict[str, list[str]]:
    global _REP_DOMAIN_Q_CACHE
    if _REP_DOMAIN_Q_CACHE is None:
        by_bf: dict[str, list[str]] = {}
        try:
            with (ROOT / "crawler" / "data" / "testset_natural_450.jsonl").open(encoding="utf-8") as fh:
                for line in fh:
                    d = json.loads(line)
                    bf, oq = d.get("business_function"), d.get("origin_question")
                    if not bf or not oq:
                        continue
                    lst = by_bf.setdefault(bf, [])
                    if oq not in lst and len(lst) < limit:
                        lst.append(oq)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            by_bf = {}
        _REP_DOMAIN_Q_CACHE = by_bf
    return _REP_DOMAIN_Q_CACHE


def _render_question_cards(questions: list[str], key_prefix: str) -> str | None:
    """"Q. 문장" 카드 목록. 클릭된 질문 원문을 돌려준다.

    key 에 공통으로 "qcard-" 를 붙인다 — CSS가 이 접두사 하나로 "Q." 글자만
    빨갛게 물들인다(도메인 그리드 버튼처럼 이모지로 시작하는 버튼은 안 걸리게).
    """
    picked = None
    for i, q in enumerate(questions):
        if st.button(f"Q. {q}", key=f"qcard-{key_prefix}-{i}", width="stretch"):
            picked = q
    return picked


def _current_domain_context() -> str | None:
    """가장 최근 질의의 업무 도메인 — 결정론 재분류(HCX 콜 0)로 얻는다.

    `qform_trace.bf_debug` 는 검색측 업무 판정에도 쓰는 로컬 키워드 분류기라
    `_load_domain_questions()` 의 키(테스트셋 business_function)와 라벨이 1:1이다.
    판정이 애매(점수·마진 미달)하면 None — 호출부가 트렌드 목록으로 자연히 폴백한다.
    """
    base_q = (st.session_state.get("flow") or {}).get("base_q")
    if not base_q:
        return None
    try:
        return qform_trace.bf_debug(base_q).get("bf")
    except Exception:
        return None


def render_domain_questions(key_prefix: str) -> str | None:
    """업무 도메인 목록(6×1) → 클릭 시 그 업무의 추천 질문 목록(예시 UI와 같은 2단 동작).

    도메인 클릭은 **바로 질의로 안 나간다** — 그 업무의 질문 목록을 먼저 보여주고,
    질문 카드를 클릭해야 실제 질의가 나간다. 뒤로가기로 도메인 목록에 돌아간다.
    """
    sel_key = f"{key_prefix}-sel"
    selected = st.session_state.get(sel_key)
    domain_qs = _load_representative_domain_questions()

    if selected and domain_qs.get(selected):
        if st.button("← 목록으로", key=f"{key_prefix}-back"):
            st.session_state[sel_key] = None
            st.rerun()
        st.markdown(f"**{DOMAIN_ICONS.get(selected, '📁')} {selected}**")
        return _render_question_cards(domain_qs[selected], f"{key_prefix}-q")

    picked_domain = None
    for lab, _ in EXAMPLE_CHIPS:
        if st.button(f"{DOMAIN_ICONS.get(lab, '📁')}  {lab}",
                     key=f"{key_prefix}-dom-{lab}", width="stretch"):
            picked_domain = lab
    if picked_domain:
        st.session_state[sel_key] = picked_domain
        st.rerun()
    return None


def render_recommended_questions(key_prefix: str) -> str | None:
    """우측 '추천 질문' — 현재 질문과 비슷한 질문(업무 문맥) + 업무별 추천 검색어.

    직전 질의의 업무 도메인을 판정할 수 있으면 그 업무의 질문을 보여주고("현재
    질문과 비슷한 질문"), 아직 대화가 없거나 판정이 애매하면 FAQ 트렌드 목록으로
    폴백한다("지금 뜨는 검색어") — 둘 다 콜 0(로컬 판정·코퍼스 원문)이다.
    """
    picked = None
    ctx_bf = _current_domain_context()
    domain_qs = _load_domain_questions()
    ctx_questions = domain_qs.get(ctx_bf) if ctx_bf else None
    if ctx_questions:
        st.markdown("#### 🎯 현재 질문과 비슷한 질문")
        picked = _render_question_cards(ctx_questions, f"{key_prefix}-ctx") or picked
    else:
        trending = _load_trending_questions()
        if trending:
            st.markdown("#### 🔥 지금 뜨는 검색어")
            picked = _render_question_cards(trending, f"{key_prefix}-trend") or picked
    st.divider()
    st.markdown("#### 📂 업무별 추천 검색어")
    picked = render_domain_questions(f"{key_prefix}-cat") or picked
    return picked


def _fetch_evidence_chunks(query: str, k: int) -> list[dict]:
    """근거 조각 재조달 — 검색은 결정론이라 다시 돌려도 같은 결과다(HCX 콜 0).

    `answer()` 는 검색 hits(청크 단위)를 반환값에 담지 않으므로(계약 4필드 불변),
    `qform_trace._default_search` 와 같은 방식으로 필요할 때만 재호출해서 얻는다.
    """
    try:
        return chain.get_searcher().search(query, k=k, mode="hybrid_bf")
    except Exception:
        return []


def render_evidence_chunks(r: dict, query: str | None) -> None:
    """근거 조각 — 최종 답변 생성에 실제로 쓰인 검색 결과(청크) 목록.

    예시 UI의 '데이터셋' 대응. 카드는 요약(제목·유사도·본문 앞부분)만 보여주고,
    "펼치기"를 눌러야 청크 전문·업무구분·원문 링크가 나온다(예시 UI의 데이터
    구성요소·속성 펼치기와 같은 자리).
    """
    if r.get("text") is None or not query:
        st.caption("근거 조각 없음")
        return
    k = (r.get("_meta") or {}).get("k") or 3
    hits = _fetch_evidence_chunks(query, k)
    if not hits:
        st.caption("근거 조각 없음")
        return
    for i, h in enumerate(hits, 1):
        title = h.get("page_title") or h.get("parent_doc_id") or "문서"
        score = h.get("_score")
        badge = f" · 유사도 {score:.2f}" if isinstance(score, (int, float)) else ""
        full = (h.get("text") or "").strip()
        with st.container(key=f"card-evidence-{i}"):
            st.markdown(f"**{i}. {title}**{badge}")
            snippet = full.replace("\n", " ")
            if len(snippet) > 100:
                snippet = snippet[:100] + "…"
            st.caption(snippet)
            with st.expander("펼치기 — 청크 전문·출처"):
                st.markdown(full or "_본문 없음_")
                st.caption(f"업무구분: {h.get('business_function') or '—'}"
                           f"  ·  문서ID: {h.get('parent_doc_id') or '—'}")
                if h.get("source_url"):
                    st.markdown(f"[원문 페이지 열기]({h['source_url']})")


def build_trace(ev: dict, hcx_calls: int) -> dict | None:
    """트레이스 조립 — **app 층에서만** 한다(E2). 파이프라인에는 계측이 없다.

    끄면 이 함수가 아예 안 불린다. 켜도 `answer()` 는 이미 끝난 뒤라 답변·첨부·콜수에
    개입할 지점이 없다. 필요한 값은 반환값 읽기 또는 결정론 재호출로 얻는다.
    """
    if not st.session_state.get("show_trace"):
        return None
    flow = st.session_state.flow
    try:
        return qform_trace.collect(
            flow["base_q"], qform_trace.bf_debug(flow["base_q"]), flow["slots_raw"],
            ev.get("survivors"), ev.get("ask"), ev.get("result"), BOOST,
            search_q=ev.get("search_q"), hcx_calls=hcx_calls, ask_turn=flow["ask_turn"],
        )
    except Exception as e:  # noqa: BLE001  트레이스가 대화를 죽이면 안 된다
        return {"error": f"{type(e).__name__}: {e}", "layers": {}}


def record(ev: dict, trace: dict | None = None) -> None:
    """전이 이벤트를 히스토리에 적재 — 렌더가 읽을 형태로만 옮긴다."""
    if ev["kind"] == "ask":
        a = ev["ask"]
        append_history(
            {"role": "ask", "prompt": ev["prompt"], "remaining": ev["remaining"],
             "mode": a["mode"], "calls": a["calls"], "fallback": a["fallback_reason"],
             "trace": trace, "unit": ev.get("unit"), "routing": ev.get("routing")}
        )
    else:
        # 후속 추천은 여기서 **한 번** 계산해 히스토리에 굳힌다. 매 렌더마다 다시 뽑으면
        # 나중 턴의 슬롯이 과거 답변의 추천을 바꿔 버린다. 결정론이고 콜 0 이다.
        #append_history(
        #    {"role": "answer", "r": ev["result"], "slots": ev["slots"],
        #     "search_q": ev["boosted"], "trace": trace,
        #     "followups": qform_followup.suggest(ev["slots"]),
        #     "unit": ev.get("unit"), "routing": ev.get("routing")}
        #)
        append_history(
            {
                "role": "answer",
                "r": ev["result"],
                "slots": ev["slots"],
                "search_q": ev["boosted"],
                "query": ev["search_q"],
                "trace": trace,
                "followups": qform_followup.suggest(ev["slots"]),
                "unit": ev.get("unit"),
                "routing": ev.get("routing"),
            }
          )


# ══════════════════════════════════════════════════════════════════════════
# 본문 레이아웃 — 좌측(정보: 세션상태·큐폼·근거문서·기억·트레이스) /
# 중앙(대화) / 우측(추천 질문 · 근거 조각)
# (st.chat_input은 컬럼 안에 못 들어가므로 최상위)
# ══════════════════════════════════════════════════════════════════════════
flow = st.session_state.flow
pending = flow["pending_slot"]
SHOW_TRACE = bool(st.session_state.get("show_trace"))

last_answer = max((i for i, t in enumerate(st.session_state.history)
                   if t["role"] == "answer"), default=None)

chip_q = None

with center:
    st.markdown('<span class="center-col-anchor"></span>', unsafe_allow_html=True)
    st.subheader("💬 대화")
    unset_field = None
    followup_q = None
    for ti, turn in enumerate(st.session_state.history):
        if turn["role"] == "user":
            with st.chat_message("user"):
                st.markdown(turn["text"])
        elif turn["role"] == "ask":
            with st.chat_message("assistant"):
                render_ask(turn)
        else:
            with st.chat_message("assistant"):
                # 슬롯 해제는 **마지막 답변에만** 붙인다 — 과거 턴의 슬롯을 고치는 시늉을
                # 하면 화면과 실제 상태(flow)가 갈린다.
                act = render_answer(turn["r"], key_prefix=f"h{ti}",
                                    slots=turn.get("slots"), search_q=turn.get("search_q"),
                                    editable=(ti == last_answer and not pending),
                                    followups=(turn.get("followups")
                                               if ti == last_answer and not pending else None))
                unset_field = act["unset"] or unset_field
                chip_q = act["chip"] or chip_q
                followup_q = act["followup"] or followup_q

    # 대기 중인 질의 처리 — 사용자 메시지는 위 루프에서 이미 그려졌다. 여기서 로딩
    # 표시를 하고 실제 검색·생성을 돈다 — 메시지 목록 바로 아래(입력창 바로 위)라
    # 자리가 자연스럽다("어시스턴트가 입력 중" 느낌).
    pending_step = st.session_state.get("_pending_step")
    if pending_step:
        with st.chat_message("assistant"):
            with st.spinner("처리 중… (최초 1회는 임베딩 모델 로딩으로 오래 걸립니다)"):
                c0 = chain._calls
                step_fn = qform_flow.reply if pending_step["is_reply"] else qform_flow.start
                st.session_state.needs_regen = False
                ev = step_fn(flow, pending_step["text"], ask_mode=ASK_MODE, boost=BOOST, config=CONFIG)
                # 콜 회계는 app 층에서 잰다 — chain 에 카운터를 심지 않는다(E2)
                record(ev, build_trace(ev, chain._calls - c0))
        st.session_state["_pending_step"] = None
        st.rerun()

    # 슬롯을 고친 뒤 되물을 것이 없으면 여기서 재생성을 **명시로** 받는다.
    # 자동 재생성을 안 하는 이유: 칩을 만질 때마다 HCX 2콜이 나가면 예산이 샌다(AC6-5).
    # 위젯 key 와 상태 플래그 이름을 반드시 갈라 둔다 — 같은 이름이면 버튼이 매 런
    # 자기 반환값을 session_state 에 써서 플래그를 덮어쓴다.
    if st.session_state.get("needs_regen") and not pending:
        st.info("조건이 바뀌었습니다. 이 조건으로 답변을 다시 받으시겠어요?")
    regen = (st.button("이 조건으로 다시 답변받기", key="btn-regen", type="primary")
             if st.session_state.get("needs_regen") and not pending else False)

    skip = False
    chosen = None
    if pending:
        # 선택지 버튼 — 값이 조합 테이블에서 직접 온다(T5 B1). 자유 입력·탈출구는 그대로.
        chosen = render_options(qform_flow.options(flow), key_prefix=str(flow["ask_turn"]))
        # 탈출구 상시 노출 — 기획서 §4. 미선택(null)은 결함이 아니라 정상 입력이다.
        skip = st.button("잘 모르겠어요 — 이대로 답변받기", key=f"skip-{flow['ask_turn']}")
    elif not st.session_state.history:
        # 첫 화면 — 업무 6종 대표 질문 카드(예시 UI의 초기 예시 카드 자리).
        st.markdown("이런 걸 물어볼 수 있어요")
        chip_q = render_chips("home", per_row=3) or chip_q

with right:
    st.markdown('<span class="col-anchor-right"></span>', unsafe_allow_html=True)
    tab_reco, tab_evidence = st.tabs(["💡 추천 질문", "🧩 근거 조각"])
    with tab_reco:
        chip_q = render_recommended_questions("reco") or chip_q
    with tab_evidence:
        if last_answer is not None:
            _last = st.session_state.history[last_answer]
            render_evidence_chunks(_last["r"], _last.get("query"))
        else:
            st.caption("답변을 받으면 이 자리에 근거 조각이 표시됩니다.")

with left:
    st.divider()
    st.subheader("📎 근거 문서")
    if last_answer is not None:
        render_evidence_card(st.session_state.history[last_answer]["r"])
    else:
        st.caption("답변을 받으면 이 자리에 근거 문서·검증 플래그가 표시됩니다.")

    # ver4 M3 — 메모리 패널. 좌측 상시 노출은 세션 상태·근거 문서뿐이라 접어 둔다.
    _panel_action = None
    if st.session_state.history:
        st.divider()
        with st.expander("🧠 기억"):
            _panel_action = render_memory_panel(flow)

    if SHOW_TRACE:
        st.divider()
        qform_panel.render([t["trace"] for t in st.session_state.history if t.get("trace")])

q = st.chat_input("예: 착오송금 반환 신청 서류가 뭐예요?")

# 하단 입력창 폭을 중앙 대화 컬럼 기준으로 맞추되, 살짝 더 여유 있게 좌·우로 조금씩
# 더 넓힌다(WIDEN_PX) — 좌·우 패널 카드 패딩 안쪽 여유 공간만큼만 넓혀서 옆 칸을
# 침범하지 않는 선에서 손해 안 보게. st.chat_input은 컬럼 밖(하단 고정 영역)에 그려져서
# CSS만으론 "중앙 컬럼과 같은 폭"을 알 수 없어 실제 렌더된 폭을 재서 적용한다.
# 가운데 정렬은 CSS margin:auto에 맡긴다(하단 바 자체가 뷰포트 전체 폭이라 auto만으로
# 정확히 가운데 온다 — 이전에 JS로 getBoundingClientRect().left 를 그대로 margin-left에
# 넣었더니 뷰포트 기준 좌표와 박스 기준 마진이 안 맞아 어긋났었다).
components.html("""
<script>
const WIDEN_PX = 140;  // 중앙 컬럼 실측 폭보다 이만큼(좌우 합산) 더 넓힌다
function syncInputWidth() {
  try {
    const doc = window.parent.document;
    const anchor = doc.querySelector('.center-col-anchor');
    const col = anchor && anchor.closest('[data-testid="stColumn"]');
    const bottom = doc.querySelector('[data-testid="stBottomBlockContainer"]');
    if (!col || !bottom) return;
    const rect = col.getBoundingClientRect();
    bottom.style.maxWidth = 'none';
    bottom.style.width = (rect.width + WIDEN_PX) + 'px';
    bottom.style.marginLeft = 'auto';
    bottom.style.marginRight = 'auto';
  } catch (e) {}
}
syncInputWidth();
try {
  const doc = window.parent.document;
  new ResizeObserver(syncInputWidth).observe(doc.body);
  window.parent.addEventListener('resize', syncInputWidth);
} catch (e) {}
setInterval(syncInputWidth, 400);
</script>
""", height=0)

# 슬롯 해제(T6)와 후속 추천(T7 C안)은 **같은 경로**다 — 둘 다 슬롯을 고치고
# 되묻기만 재판정한다. `answer()` 는 부르지 않으므로 HCX 콜 0 이다(AC6-5·AC7-1).
_edit = None
if unset_field:
    _edit = (unset_field, None, "슬롯 칩 수정", f"'{SLOT_LABEL.get(unset_field, unset_field)}' 조건 해제")
elif followup_q:
    _lab = SLOT_LABEL.get(followup_q["field"], followup_q["field"])
    _edit = (followup_q["field"], followup_q["value"], "후속 추천",
             f"{_lab} · {followup_q['value']}(으)로 좁히기")

if _edit:
    field, value, source, note = _edit
    ev = qform_flow.edit(flow, field, value, source=source, ask_mode=ASK_MODE,
                         config=CONFIG)
    append_history({"role": "user", "text": note})
    if ev["kind"] == "ask":
        st.session_state.needs_regen = False        # 되물으니 재생성 버튼은 필요 없다
        record(ev, build_trace(ev, 0))
    else:
        st.session_state.needs_regen = True   # 물을 것이 없다 → 사용자가 재생성을 정한다
    st.rerun()

if regen:
    with st.spinner("문서 검색·답변 생성 중…"):
        c0 = chain._calls
        ev = qform_flow.answer_now(flow, boost=BOOST)
        st.session_state.needs_regen = False
        record(ev, build_trace(ev, chain._calls - c0))
    st.rerun()

if skip and pending:
    with st.spinner("문서 검색·답변 생성 중…"):
        c0 = chain._calls
        ev = qform_flow.skip(flow, boost=BOOST, config=CONFIG)
        st.session_state.needs_regen = False
        record(ev, build_trace(ev, chain._calls - c0))
    st.rerun()

if chosen == _ESCAPE and pending:
    # K9 [이대로 답변받기] — ver2 탈출구(`skip`)를 버튼으로 한 번 더 연 것이다.
    append_history({"role": "user", "text": "이대로 답변받기"})
    with st.spinner("처리 중…"):
        c0 = chain._calls
        ev = qform_flow.skip(flow, boost=BOOST, config=CONFIG)
        st.session_state.needs_regen = False
        record(ev, build_trace(ev, chain._calls - c0))
    st.rerun()

if chosen == _PASS and pending:
    # K5 ⏭ pass — 이 슬롯은 답하지 않겠다. `asked` 에 기록해 재질문을 막는다.
    # **`answer()` 를 부르지 않는다.** X(오염 차단)와 달리 여기서 대화가 멈춘다.
    _slot = flow.get("pending_slot")
    append_history({"role": "user", "text": "이건 넘어갈게요"})
    qmp.apply(flow, "pass", field=_slot)
    st.rerun()

if chosen and pending:
    # 버튼 경로 — `value=` 로 값을 직접 주입한다. 자연어 추출을 경유하지 않는다.
    append_history({"role": "user", "text": chosen})
    with st.spinner("처리 중…"):
        c0 = chain._calls
        ev = qform_flow.reply(flow, chosen, value=chosen, ask_mode=ASK_MODE,
                              boost=BOOST, config=CONFIG)
        st.session_state.needs_regen = False
        record(ev, build_trace(ev, chain._calls - c0))
    st.rerun()

if _panel_action:
    # 패널 조작은 전부 `qmp.apply()` 한 곳으로 들어간다. **answer() 를 부르지 않는다**(A3-2).
    _op, _kw = _panel_action
    qmp.apply(flow, _op, **_kw)
    st.rerun()

# 예시 칩은 되묻기 중이어도 **새 질의**다 — 사용자가 다른 걸 물으려고 누른 것이다.
# (후속 추천은 새 질의가 아니라 슬롯 좁히기라 위 `_edit` 경로로 빠진다.)
q_new, q_reply = (chip_q, None) if chip_q else ((None, q) if pending else (q, None))

next_queued = False
if flow.get("unit_queue") and not pending:
    with left:
        st.info(f"대기 중인 용건이 {len(flow['unit_queue'])}개 있습니다.")
        next_queued = st.button("다음 용건 처리", key="next-unit", type="primary")

if next_queued:
    with st.spinner("다음 용건 처리 중…"):
        c0 = chain._calls
        ev = orchestrator.next_unit(flow, ask_mode=ASK_MODE, boost=BOOST, config=CONFIG,
                                    report_context=report_context())
        if ev:
            record(ev, build_trace(ev, chain._calls - c0))
    st.rerun()

#if q_new or q_reply:
    # 2단계 렌더: 여기서는 사용자 메시지만 히스토리에 넣고 바로 rerun한다 — 그래야
    # 답변을 기다리는 동안에도 "내가 방금 뭘 물어봤는지"가 대화창에 바로 보인다.
    # 실제 검색·생성은 `with center:` 안, 메시지 목록 바로 아래(입력창 바로 위)에서
    # `_pending_step`을 보고 처리한다 — 그래야 로딩 표시가 그 자리에 뜬다.
#    text = q_new or q_reply
#    st.session_state.history.append({"role": "user", "text": text})
#    st.session_state["_pending_step"] = {"text": text, "is_reply": bool(q_reply)}
#    st.rerun()
    
if q_new or q_reply:
    text = q_new or q_reply
    previous_target = last_answer_id()
    append_history({"role": "user", "text": text})
    st.session_state["_pending_step"] = {
        "text": text,
        "is_reply": bool(q_reply),
        "previous_target": previous_target,
    }
    st.rerun()    
