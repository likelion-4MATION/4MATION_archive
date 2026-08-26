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
import html
import json
import pathlib
import sys
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import streamlit as st

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
import ui_theme

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

# 슬롯 추출 스코프 라벨 → `qform_config.SPEC["QFORM_SCOPE"]` 허용값. 첫 항목이 기본값이다.
SCOPE_LABELS = {"착오송금 단일 (기본)": "msdr", "착오송금 + 예금보험금": "msdr+dpin"}
_SCOPE_DEFAULT_LABEL = next(iter(SCOPE_LABELS))

st.set_page_config(page_title="예봄 · 예금보험공사 AI 안내",
                   page_icon=str(ui_theme.YEBOM_PATH), layout="wide")
ui_theme.inject()

# ── 진입 로딩 화면 — 세션 첫 런에만, **정확히 1회** ──────────────────────────
# 사라지는 시점을 CSS 애니메이션에 맡기면 안 된다. 스크립트 런이 끝날 때 streamlit
# 프론트가 요소 컨테이너를 remount 하면서 `yebom-out` 의 시계가 0으로 돌아가 화면이
# 한 번 더 뜬다 — 브라우저 실측: mount 0.65s → 페이드 시작 1.66s(opacity .70)
# → **2.06s opacity 1 복귀** → 3.45s 소멸. python 은 1회만 돌았다(런 로그 1건).
# 그래서 자리(placeholder)를 잡아 두고 **이 런이 끝나기 전에 python 이 지운다**.
# 지운 뒤에는 remount 될 요소 자체가 없으므로 재생될 애니메이션도 없다.
SPLASH_HOLD_SEC = 3.0           # 화면에 머무는 시간. 페이드아웃(2.4s+0.5s)이 이 안에서 끝난다
# 자리는 **매 런 잡는다.** 첫 런에만 요소를 만들면 다음 런부터 뒤따르는 요소의 인덱스가
# 통째로 한 칸 밀린다 → streamlit 프론트가 본문 컬럼을 같은 자리에 덮어쓰지 못하고
# 새로 붙여, 이전 런의 화면이 아래에 그대로 남는다(앱이 두 벌로 보이는 증상).
# 빈 placeholder 는 아무것도 그리지 않으므로 화면에는 영향이 없다.
_splash_slot = st.empty()
_splash = None
if not st.session_state.get("_splashed"):
    st.session_state["_splashed"] = True
    _splash = ui_theme.splash(_splash_slot)
    _splash_until = time.monotonic() + SPLASH_HOLD_SEC
ui_theme.header(
    "예봄",
    "예금보험공사 안내",
    tag="PoC 데모",
)

st.session_state.setdefault("history", [])
st.session_state.setdefault("flow", qform_flow.new_state())
st.session_state.setdefault("needs_regen", False)   # 슬롯 수정 후 재답변 대기 (T6)
st.session_state.setdefault("session_id", f"sess_{uuid.uuid4().hex[:16]}")
st.session_state.setdefault("report_confirm", False)
st.session_state.setdefault("report_notice", None)


def rerun_later() -> None:
    """렌더 **도중**에는 st.rerun() 을 부르지 않는다 — 플래그만 세우고 끝에서 돌린다.

    렌더 중간에 rerun 하면 그 아래 위젯(채팅 입력·메모리 패널·대기 용건)이 그 런에서
    **선언되지 않는다.** streamlit 프론트는 직전 런의 요소를 지우지 못한 채 새 런의
    요소를 얹으므로 같은 패널이 잠깐 두 벌 보이고 페이지 높이가 튄다 — 업무별 추천
    검색어 클릭 실측에서 버튼 수가 27 → **40** → 28 로 튀었다(중복 UI 의 정체).
    화면을 다 그린 뒤에 돌리면 그 창이 없다.
    """
    st.session_state["_rerun_after_render"] = True


def embedding_cold() -> bool:
    """임베딩 모델이 아직 이 프로세스에 안 올라왔는가 = "최초 임베딩" 안내를 띄울 때인가.

    화면 상태가 아니라 **캐시 상태**를 본다. `rag.get_model()` 이 모델을 모듈 전역
    `rag._model` 에 물려 두므로, 한 번 올라오면 Ctrl+R 로 세션이 새로 나도(프로세스는
    그대로다) 여기서 False 가 된다 — 안내는 진짜 최초 1회에만 뜬다.
    `sys.modules.get` 으로 조회만 한다. import 하면 그 자체가 수 초짜리 부작용이다.
    """
    rag = sys.modules.get("rag")
    return rag is None or getattr(rag, "_model", None) is None


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


# 오류 신고 확인 UI 는 우측 레일 `render_support_card()` 안 인라인 아코디언으로 옮겼다.
# 저장 로직(`oos_store.create_report`)·플래그 이름은 그대로다.

# 사이드바 3구역 — **사용자 → 기억 → 관리자** 순서로 자리를 먼저 잡는다.
# 관리자 위젯 값(ASK_MODE/BOOST/CONFIG/SHOW_TRACE)은 본문보다 **먼저** 읽혀야 하는데,
# 메모리 패널은 본문 렌더 **뒤에** 그려진다(flow 가 확정된 뒤라야 맞다).
# 컨테이너로 슬롯을 예약해 두면 호출 순서와 화면 순서를 따로 둘 수 있다.
with st.sidebar:
    _sb_user = st.container()
    _sb_mem = st.container()
    _sb_admin = st.container()

with _sb_user:
    if st.button("＋ 새로운 대화 시작하기", key="btn-newchat", type="primary",
                 width="stretch"):
        st.session_state.history = []
        st.session_state.flow = qform_flow.new_state()
        st.session_state.needs_regen = False
        st.session_state.session_id = f"sess_{uuid.uuid4().hex[:16]}"
        st.session_state["_pending_step"] = None
        rerun_later()
    st.divider()
    st.subheader("현재 대화")
    _asked = [t["text"] for t in st.session_state.history if t["role"] == "user"]
    if _asked:
        for _i, _t in enumerate(_asked, 1):
            st.caption(f"{_i}. {_t}")
    else:
        st.caption("아직 질문이 없습니다.")

with _sb_admin:
    st.divider()
    # 예산 경고는 접힌 영역 밖에 둔다 (T7 B6-1) — 소진되고 나서 알면 시연 도중에 막힌다.
    _left_calls = chain.CALL_BUDGET - chain._calls
    if _left_calls <= 0:
        st.error("모델 호출 예산 소진 — 새 답변을 만들 수 없습니다. "
                 "되묻기·선택지·슬롯 수정은 계속 동작합니다 (콜 0).")
    elif _left_calls <= LOW_CALL_WARN:
        st.warning(f"남은 모델 호출 {_left_calls}회. "
                   "경로에 따라 OOS 분류 또는 답변 생성에 호출을 씁니다.")

    with st.expander("관리자 · 고급 설정"):
        st.metric("HCX 콜 (재시도 포함)", f"{chain._calls} / {chain.CALL_BUDGET}")
        st.caption("되묻기 턴은 ⓐ 모드에서 콜을 쓰지 않습니다. 예산 소진 시 앱 재시작으로 리셋됩니다.")
        st.divider()
        st.radio(
            "되묻기 문구", list(ASK_MODES), index=0, key="ask_mode_label",
            help="ⓐ는 조합 테이블 값을 CSV 문구에 끼워 넣습니다(LLM 콜 0). "
                 "ⓑ는 같은 판정 결과를 LLM이 한 문장으로 다듬습니다. 값 고정 가드를 어기면 "
                 "ⓐ로 폴백하고 사유를 남깁니다 — 어느 쪽이 나은지는 비교해 보고 정합니다.",
        )
        st.toggle(
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
                    help="질의 1건이 어느 층에서 어떻게 갈렸는지 우측 레일 하단에 보여줍니다. "
                         "관리자 콘솔로 이관 예정이라 기본은 꺼둡니다.")
        st.caption("첨부 후단 필터는 항상 켜져 있습니다 (슬롯이 비면 자동으로 기존 동작).")
        st.divider()
        st.caption(
            "표시되는 유사도는 질문-문서 관련도이며 정답 확신도가 아닙니다. "
            "검증 플래그는 참고용이며 답변을 차단하지 않습니다."
        )

ASK_MODE = ASK_MODES[st.session_state.get("ask_mode_label", "ⓐ 템플릿 (콜 0)")]
BOOST = bool(st.session_state.get("boost"))
# 관리자 고급 설정 → 정책 오버라이드. `qform_config.resolve()` 가 허용범위 밖 값을 기본값으로 되돌린다.
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
        # 과거 턴 — 조작할 수 없으므로 버튼이 아니라 글자 태그로만 남긴다
        ui_theme.chips([(lab, v) for _, lab, v in filled])
        return None

    unset = None
    # 박스로 감싸지 않는다 — 라벨 한 줄 + 칩 줄. 기능·반환값은 그대로다.
    ui_theme.mini("확정된 조건 · ✕ 로 풀고 다시 고를 수 있어요")
    with st.container(key=f"kdic-slots-{key_prefix}", horizontal=True,
                      horizontal_alignment="left"):
        for f, lab, v in filled:
            if st.button(f"{lab} · {v}  ✕", key=f"unset-{key_prefix}-{f}", width="content",
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
    with st.expander(f"관련 서식·첨부파일 ({len(atts)}건)"):
        for ti, title in enumerate(order):
            st.markdown(f"**{title}**")
            for ai, a in enumerate(groups[title]):
                kind = f"[{a['doc_kind']}] " if a.get("doc_kind") else ""
                fname = a.get("orig_filename") or "attachment"
                size = _fmt_size(a.get("file_size"))
                label = f"{kind}{a.get('label') or fname}  ·  {fname}{size}"
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
        with st.expander(f"참고 문헌·출처 ({len(r['sources'])}건)"):
            for i, s in enumerate(r["sources"], 1):
                st.markdown(f"{i}. [{s['title']}]({s['url']})")
    if not r["checks"]["ok"]:
        with st.expander("검증 플래그 (차단 아님)"):
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
    meta = r["_meta"]
    # 머리글 한 줄 — 라벨 + 경로/유사도/지연. 같은 정보를 본문 아래 캡션에서 위로만 옮겼다.
    ui_theme.answer_head(
        f"{ROUTE_LABEL.get(r['route'], r['route'])}"
        f" · 관련 문서 유사도 {r['confidence']:.2f}"
        f" · {meta.get('latency_ms') or '?'}ms"
    )
    st.markdown(r["text"])
    if search_q:
        st.caption(f"부스트 적용 검색어: `{search_q}`")
    # 본문과 부속(조건·서식)을 얇은 선 하나로 가른다 — 부속이 없으면 선도 없다.
    atts = r.get("attachments") or []
    has_slots = any(v for f, v in (slots or {}).items()
                    if f in qform_state.SLOT_FIELDS and v)
    if atts or has_slots:
        ui_theme.answer_sep()
    if slots:
        out["unset"] = render_slots(slots, key_prefix=key_prefix, editable=editable)
    # 근거 문서·검증 플래그는 우측 "근거 자료" 컬럼으로 옮겼다(render_evidence_card).
    # 첨부파일 다운로드는 대화 흐름과 붙어 있는 게 자연스러워 말풍선에 그대로 둔다.
    render_attachments(atts, key_prefix)
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
    ui_theme.mini("조건을 더 좁혀서 보기")
    # 카드가 아니라 선택형 태그다 — 글자 길이만큼만 차지하고 넘치면 다음 줄로 접힌다
    with st.container(key=f"kdic-fu-{key_prefix}", horizontal=True,
                      horizontal_alignment="left"):
        for it in items:
            lab = SLOT_LABEL.get(it["field"], it["field"])
            if st.button(f"{lab} · {it['value']}", width="content",
                         key=f"fu-{key_prefix}-{it['field']}-{it['value']}",
                         help=f"'{lab}'을(를) '{it['value']}'(으)로 두고 다시 답변받습니다"):
                picked = it
    return picked


def render_ask(turn: dict) -> None:
    """되묻기 턴 — 문구 + 남은 후보. ⓐ/ⓑ 구별과 폴백 사유를 캡션에 남긴다."""
    st.markdown(turn["prompt"])
    # 남은 후보 수·ⓐⓑ 모드는 **진행 표시가 아니라 트레이스**다. 사용자 화면에 늘 띄우면
    # 설문 진행 바처럼 읽힌다 — 관리자 트레이스가 켜져 있을 때만 남긴다.
    if not st.session_state.get("show_trace"):
        return
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

    # 3열 고정 그리드를 쓰면 두 글자짜리 값도 컬럼 폭만큼 커진다. 가로 컨테이너로
    # 흘려 **글자 길이만큼만** 차지하게 한다(넘치면 다음 줄로 자연히 접힌다).
    # 컨테이너 key 는 `ui_theme` 가 추천 질문 카드와 같은 시각 언어를 걸 때만 쓴다.
    # 클릭 → 즉시 다음 질문. 확인·다음 버튼은 없다(이 함수 반환값이 곧 응답이다).
    def _flow(values: list[str], tag: str) -> None:
        nonlocal picked
        with st.container(key=f"kdic-opts-{key_prefix}-{tag}", horizontal=True,
                          horizontal_alignment="left"):
            for v in values:
                if st.button(v, key=f"opt-{key_prefix}-{tag}-{v}", width="content"):
                    picked = v

    head, tail = opts[:MAX_VISIBLE_OPTIONS], opts[MAX_VISIBLE_OPTIONS:]
    _flow(head, "h")
    if tail:
        with st.expander(f"다른 선택지 보기 ({len(tail)}개)"):
            _flow(tail, "t")
    # K9 — 빠른 답변은 키 조합이 아니라 **버튼**. 탈출구 로직은 ver2부터 구현·검증돼 있어
    # (verify_qform_e2e.py AC3) 여기서 하는 일은 **입구를 하나 더 여는 렌더링 변경**이다.
    # K5 — ⏭ pass 는 "이 슬롯은 답하지 않겠다". X(오염 차단)와 역할이 다르다.
    with st.container(key=f"kdic-esc-{key_prefix}", horizontal=True,
                      horizontal_alignment="left"):
        if st.button("이대로 답변받기", key=f"opt-{key_prefix}-escape", width="content"):
            picked = _ESCAPE
        if st.button("이건 넘어갈게요", key=f"opt-{key_prefix}-pass", width="content"):
            picked = _PASS
    return picked


# 맥락 칩 더블클릭 판정 창(초). streamlit 위젯에는 dblclick 이벤트가 없고 markdown 의
# <script> 는 실행되지 않는다 — 클릭 두 번의 **간격**으로 본다. 실제 더블클릭은 물론
# "두 번 눌러 취소"로도 걸리므로, 오작동해도 취소가 안 될 뿐 잘못 취소되지는 않는다.
_CHIP_DBLCLICK_SEC = 2.0


def render_branch_chip(flow: dict) -> bool:
    """되묻기 맥락 칩. 두 번 빠르게 누르면 True(= Q-Form 취소)를 돌려준다.

    단계 번호도 진행 바도 그리지 않는다 — **지금 어느 업무 흐름인지**만 남긴다.
    라벨은 `flow["bf"]`(라우팅이 고른 업무명) 그대로다. 문구를 만들지 않는다.
    """
    label = flow.get("bf")
    if not label:
        return False
    with st.container(key="kdic-branch"):
        clicked = st.button(label, key=f"branch-{flow['ask_turn']}",
                            help="두 번 누르면 이 질문 흐름을 취소하고 일반 대화로 돌아갑니다")
    if not clicked:
        return False
    now, last = time.monotonic(), st.session_state.get("_chip_click", 0.0)
    st.session_state["_chip_click"] = now
    return now - last <= _CHIP_DBLCLICK_SEC


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
    st.markdown("### 대화 기억")
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
                label = {"edit": "수정", "clear": "해제", "pass": "건너뛰기",
                         "move": "위로", "drop": "삭제"}[op]
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
                if st.button(label, key=f"chip-{key_prefix}-{idx}", width="stretch",
                             help=query):
                    picked = query
    return picked


# 추천 질문 어조 게이트 — 화면에 세우는 질문은 **표준 존댓말 의문문**만 통과시킨다.
# 코퍼스에는 구어체 파라프레이즈("…있어?", "…궁금함")와 명사구 표제("예금자보호제도")가
# 섞여 있다. 문구를 고쳐 쓰면 창작이 되므로(CLAUDE.md §2-4) **고르기만 한다** —
# `요?` · `니까?` 로 끝나는 것만 남긴다(그냥 `까?` 는 "…있을까?" 같은 해체가 섞인다).
# 업무별로 33~75건이 통과해 노출 상한(5~6)을 넉넉히 채운다. 반말이 들어오는 경로가
# 남지 않으므로 출력단 `^Q\.` 정규식 후처리는 두지 않는다 — 접두사는 아예 안 붙인다.
_POLITE_Q_RE = re.compile(r"(요|니까)\?$")
# 화면 문구가 코퍼스에 섞여 들어온 것("송금하시겠습니까?")은 사용자 질문이 아니라
# 시스템이 사용자에게 묻는 확인문이다. 종결형으로 갈라낸다.
_CONFIRM_Q_RE = re.compile(r"시겠(습니까|어요|나요)\?$")


def _polite(q: str) -> bool:
    q = q.strip()
    return bool(_POLITE_Q_RE.search(q)) and not _CONFIRM_Q_RE.search(q)


# ── 코퍼스 원문 질문 풀 — 화면에 뜨는 추천 질문은 전부 여기서 나온다. 문구를 만들지
# 않는다는 원칙(EXAMPLE_CHIPS와 동일)을 지키되, 출처 우선순위를 명시한다:
#   1) FAQ 페이지의 `질문/답변` 블록 원문   2) 본문의 질문형 헤딩("…이란?")
#   3) `testset_natural_450.jsonl` 의 origin_question
# FAQ 판정은 `page_title` 이 아니라 `page_type` 으로 한다 — 착오송금 FAQ 페이지처럼
# page_title 에 "FAQ" 가 없는 문서가 있어서 title 기준이면 통째로 빠졌다.
_FAQ_Q_RE = re.compile(r"질문\s*\n(.+?)\n\s*답변", re.S)
# "FAQ TOP10" 시드 페이지는 같은 질문에 "1. " 번호만 붙은 사본이다 — 번호를 떼면
# 원본과 문자열이 같아져 중복 제거로 자연히 하나만 남는다.
_NUM_PREFIX_RE = re.compile(r"^(\d+)\.\s*")
# 헤딩은 "고객 미수령금이란?" 처럼 존댓말 종결이 아니어서 `_polite()` 로는 못 거른다.
_HEADING_Q_RE = re.compile(r"(란|나요|가요|습니까)\?$")
# 카드 한 줄에 안 들어가는 장문 FAQ("보험사고가 발생한 부보금융회사에 예금 등 채권과…")는
# 제외한다. 문구를 고쳐 줄이지 않는다 — 그냥 안 쓴다.
_MAX_Q_LEN = 50
# 사이트의 "고객센터 > FAQ > TOP 10" 페이지는 실제 조회수 순위다 — 추천 질문 정렬의
# 1순위 근거로 쓴다(순위가 없는 질문은 뒤로). 코퍼스에 TOP 10 이 있는 업무는 착오송금뿐이라
# 나머지 업무는 아래 관련도·길이 기준으로만 정렬된다.
_TOP10_RANK: dict[str, int] = {}
_CORPUS_Q_CACHE: tuple[dict[str, list[str]], dict[str, list[str]]] | None = None
_ORIGIN_Q_CACHE: dict[str, list[str]] | None = None
_TRENDING_CACHE: list[str] | None = None


def _push(lst: list[str], q: str) -> None:
    if q and len(q) <= _MAX_Q_LEN and q not in lst:
        lst.append(q)


def _load_corpus_questions() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """`chunks.jsonl` 원문에서 (업무별 FAQ 질문, 업무별 질문형 헤딩)."""
    global _CORPUS_Q_CACHE
    if _CORPUS_Q_CACHE is None:
        faq: dict[str, list[str]] = {}
        head: dict[str, list[str]] = {}
        try:
            with (ROOT / "crawler" / "data" / "chunks.jsonl").open(encoding="utf-8") as fh:
                for line in fh:
                    d = json.loads(line)
                    bf = d.get("business_function")
                    if not bf or bf == "공통":     # 업무 미할당 청크는 어느 칩에도 안 붙는다
                        continue
                    text = d.get("text") or ""
                    if "FAQ" in (d.get("page_type") or ""):
                        top10 = d.get("page_title") == "TOP 10"
                        for m in _FAQ_Q_RE.finditer(text):
                            raw = m.group(1).strip()
                            q = _NUM_PREFIX_RE.sub("", raw)
                            if not _polite(q):
                                continue
                            if top10 and (n := _NUM_PREFIX_RE.match(raw)):
                                _TOP10_RANK.setdefault(q, int(n.group(1)))
                            _push(faq.setdefault(bf, []), q)
                    else:
                        for ln in text.split("\n"):
                            ln = ln.strip()
                            if (len(ln) >= 6 and _HEADING_Q_RE.search(ln)
                                    and not _CONFIRM_Q_RE.search(ln)):
                                _push(head.setdefault(bf, []), ln)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            faq, head = {}, {}
        _CORPUS_Q_CACHE = (faq, head)
    return _CORPUS_Q_CACHE


def _load_origin_questions() -> dict[str, list[str]]:
    """`testset_natural_450.jsonl` 의 origin_question — FAQ·헤딩이 모자랄 때만 쓰는 3순위."""
    global _ORIGIN_Q_CACHE
    if _ORIGIN_Q_CACHE is None:
        by_bf: dict[str, list[str]] = {}
        try:
            with (ROOT / "crawler" / "data" / "testset_natural_450.jsonl").open(encoding="utf-8") as fh:
                for line in fh:
                    d = json.loads(line)
                    bf, oq = d.get("business_function"), d.get("origin_question")
                    if bf and oq and _polite(oq):
                        _push(by_bf.setdefault(bf, []), oq)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            by_bf = {}
        _ORIGIN_Q_CACHE = by_bf
    return _ORIGIN_Q_CACHE


def _by_priority(bf: str, qs: list[str]) -> list[str]:
    """사이트 FAQ TOP 10 순위 → 업무명 토큰 포함 수 → 짧은 순.

    셋 다 코퍼스에 있는 정보만 쓴다 — 문구를 고치거나 만들지 않고 순서만 정한다.
    길이를 마지막 기준으로 두는 건 같은 관련도면 조건이 덜 붙은 일반적인 질문이
    그 업무를 더 잘 대표하기 때문이다.
    """
    toks = [t for t in bf.split() if len(t) > 1]
    return sorted(qs, key=lambda q: (_TOP10_RANK.get(q, 99),
                                     -sum(t in q for t in toks), len(q)))


# ── 지금 뜨는 검색어 — 업무별 대표 질문 풀의 1순위를 업무마다 하나씩 돌아가며 뽑는다.
# 업무 순서는 EXAMPLE_CHIPS 순서라 한 업무 질문만 몰리지 않는다.


def _load_trending_questions(limit: int = 6) -> list[str]:
    global _TRENDING_CACHE
    if _TRENDING_CACHE is None:
        rep = _load_representative_domain_questions()
        qs: list[str] = []
        for rank in range(max((len(v) for v in rep.values()), default=0)):
            for lab, _ in EXAMPLE_CHIPS:
                pool = rep.get(lab) or []
                if rank < len(pool):
                    _push(qs, pool[rank])
        _TRENDING_CACHE = qs
    return _TRENDING_CACHE[:limit]


# ── 분류별 추천 검색어 — 업무 도메인마다 여러 질문. `testset_natural_450.jsonl` 원문만
# 쓴다(팀 관례상 임의 창작 금지) — 이미 이 파일이 EXAMPLE_CHIPS 중 "고객 미수령금 신청"
# 칩 문구의 원천으로 쓰던 파일과 같다.
_DOMAIN_Q_CACHE: dict[str, list[str]] | None = None


def _load_domain_questions(limit: int = 5) -> dict[str, list[str]]:
    """업무별 자연어 질문 — "현재 질문과 비슷한 질문"(문맥 추천) 전용.

    직전 질의와 같은 결로 이어지도록 파라프레이즈를 그대로 쓰되, `_polite()` 를
    통과한 존댓말 의문문만 남긴다.
    """
    global _DOMAIN_Q_CACHE
    if _DOMAIN_Q_CACHE is None:
        by_bf: dict[str, list[str]] = {}
        try:
            with (ROOT / "crawler" / "data" / "testset_natural_450.jsonl").open(encoding="utf-8") as fh:
                for line in fh:
                    d = json.loads(line)
                    bf, q = d.get("business_function"), d.get("question")
                    if not bf or not q or not _polite(q):
                        continue
                    lst = by_bf.setdefault(bf, [])
                    if q not in lst and len(lst) < limit:
                        lst.append(q)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            by_bf = {}
        _DOMAIN_Q_CACHE = by_bf
    return _DOMAIN_Q_CACHE


# ── 업무별 추천 검색어 — 크롤링 원문에 실제로 있는 질문만 쓴다. 출처 우선순위는
# FAQ 원문 질문 → 질문형 헤딩 → origin_question 이고, 한 업무의 풀이 상한을 못 채울
# 때만 다음 순위로 내려간다(다른 업무 질문을 끌어오지 않는다).
_REP_DOMAIN_Q_CACHE: dict[str, list[str]] | None = None


def _load_representative_domain_questions(limit: int = 6) -> dict[str, list[str]]:
    global _REP_DOMAIN_Q_CACHE
    if _REP_DOMAIN_Q_CACHE is None:
        faq, head = _load_corpus_questions()
        origin = _load_origin_questions()
        by_bf: dict[str, list[str]] = {}
        for bf in {*faq, *head, *origin}:
            lst: list[str] = []
            for tier in (faq.get(bf), head.get(bf), origin.get(bf)):
                for q in _by_priority(bf, tier or []):
                    if len(lst) >= limit:
                        break
                    _push(lst, q)
            by_bf[bf] = lst
        _REP_DOMAIN_Q_CACHE = by_bf
    return _REP_DOMAIN_Q_CACHE


def _render_question_cards(questions: list[str], key_prefix: str) -> str | None:
    """추천 질문 카드 목록. 클릭된 질문 원문을 돌려준다.

    라벨은 코퍼스 원문 그대로다 — "Q." 같은 접두사를 붙이지 않는다.
    key 의 "qcard-" 접두사는 `ui_theme` 가 카드 스타일을 걸 때만 쓴다.
    """
    picked = None
    for i, q in enumerate(questions):
        if st.button(q, key=f"qcard-{key_prefix}-{i}", width="stretch"):
            picked = q
    return picked


def _current_domain_context() -> str | None:
    """최근 답변의 실제 라우팅 업무. 구형 히스토리만 로컬 판정으로 폴백한다."""
    for turn in reversed(st.session_state.get("history") or []):
        if turn.get("role") != "answer":
            continue
        result = turn.get("r") or {}
        routing = turn.get("routing") or (result.get("_meta") or {}).get("routing")
        if routing:
            return routing.get("bf") if routing.get("triggered") else None
        break

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
        # 뒤로가기 화살표와 업무명은 **버튼 라벨 하나**다 — 두 요소를 나란히 놓고
        # 맞추는 게 아니라 애초에 같은 텍스트라 글꼴·line-height·baseline 이 구조적으로
        # 일치한다. 별도 행이 없어 질문 목록에 그만큼 수직 공간이 남는다.
        # 사이 간격은 EN SPACE(U+2002 = 0.5em ≈ 7px) — 보정용 margin 을 쓰지 않는다.
        with st.container(key="kdic-back"):
            if st.button(f"← {selected}", key=f"{key_prefix}-back", width="content"):
                st.session_state[sel_key] = None
                rerun_later()
        return _render_question_cards(domain_qs[selected], f"{key_prefix}-q")

    picked_domain = None
    with st.container(key="kdic-tags"):        # 디자인: 태그 칩 스타일 (동작 동일)
        for lab, _ in EXAMPLE_CHIPS:
            if st.button(lab, key=f"{key_prefix}-dom-{lab}", width="stretch"):
                picked_domain = lab
    if picked_domain:
        st.session_state[sel_key] = picked_domain
        rerun_later()
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
        ui_theme.section("현재 질문과 비슷한 질문")
        picked = _render_question_cards(ctx_questions, f"{key_prefix}-ctx") or picked
    else:
        trending = _load_trending_questions()
        if trending:
            ui_theme.section("지금 뜨는 검색어")
            picked = _render_question_cards(trending, f"{key_prefix}-trend") or picked
    ui_theme.section("업무별 추천 검색어")
    picked = render_domain_questions(f"{key_prefix}-cat") or picked
    return picked


def render_evidence_chunks(r: dict) -> None:
    """근거 조각 — 최종 답변 생성에 실제로 쓰인 검색 기록.

    예시 UI의 '데이터셋' 대응. 카드는 요약(제목·유사도·본문 앞부분)만 보여주고,
    "펼치기"를 눌러야 저장된 발췌·문서 ID·원문 링크가 나온다. 화면을 그리기 위해
    검색을 다시 실행하지 않으므로 답변 당시의 BF 오버라이드와 결과가 어긋나지 않는다.
    """
    if r.get("text") is None:
        st.caption("근거 조각 없음")
        return
    hits = (r.get("_meta") or {}).get("retrieval") or []
    if not hits:
        st.caption("근거 조각 없음")
        return
    for i, h in enumerate(hits, 1):
        title = h.get("title") or h.get("doc_id") or "문서"
        score = h.get("score")
        badge = f" · 유사도 {score:.2f}" if isinstance(score, (int, float)) else ""
        full = (h.get("text_excerpt") or "").strip()
        with st.container(key=f"card-evidence-{i}"):
            st.markdown(f"**{i}. {title}**{badge}")
            snippet = full.replace("\n", " ")
            if len(snippet) > 100:
                snippet = snippet[:100] + "…"
            st.caption(snippet)
            with st.expander("펼치기 — 저장된 발췌·출처"):
                st.markdown(full or "_본문 없음_")
                st.caption(f"청크ID: {h.get('chunk_id') or '—'}"
                           f"  ·  문서ID: {h.get('doc_id') or '—'}")
                if h.get("url"):
                    st.markdown(f"[원문 페이지 열기]({h['url']})")


# 랜딩 추천 카드 3종 — 08-25 리디자인 지시서 §8 지정(예금보험금 · 미수령금 · 착오송금).
# 문구는 EXAMPLE_CHIPS 에서 그대로 끌어온다. 여기서 새 문구를 만들지 않는다.
CARD_KEYS = ["예금보험금 안내", "고객 미수령금 신청", "착오송금 반환 신청"]
MAIN_CARDS = [c for k in CARD_KEYS for c in EXAMPLE_CHIPS if c[0] == k]


def render_cards() -> str | None:
    """랜딩 추천 질문 카드. 클릭된 질의 문구를 돌려준다 — `render_chips` 와 같은 계약."""
    picked = None
    for i, (col, (label, query)) in enumerate(
            zip(st.columns(len(MAIN_CARDS), gap="small"), MAIN_CARDS)):
        with col.container(key=f"kdic-card-{i}"):
            ui_theme.card(label, query)
            if st.button("바로 물어보기  →", key=f"card-{i}", width="stretch"):
                picked = query
    return picked


def render_support_card() -> None:
    """상담원 연결 · 오류 신고 — 우측 레일 최상단 지원 블록.

    상담원 연결은 PoC 미지원 기능이다 — 화면을 전환하지 않고 toast 로만 알린다.
    오류 신고는 ver6 로직 그대로(`oos_store.create_report`)이고, 확인 UI 만
    상단 블록에서 **버튼 바로 아래 인라인 아코디언**으로 옮겼다(다시 누르면 접힌다).
    """
    with st.container(key="kdic-agent"):
        st.markdown('<p class="kdic-agent-t">상담원 연결</p>'
                    '<p class="kdic-agent-d">상담원 연결이 필요하시면 클릭해 주세요</p>',
                    unsafe_allow_html=True)
        if st.button("상담원 연결하기", key="agent-connect", width="stretch"):
            st.toast("PoC 데모에서는 상담원 연결이 동작하지 않습니다.", icon="ℹ️")
        if st.session_state.report_notice:
            level, message = st.session_state.report_notice
            (st.success if level == "ok" else st.error)(message)
            st.session_state.report_notice = None
        if st.button("예봄 오류 신고", key="top-report", width="stretch"):
            st.session_state.report_confirm = not st.session_state.report_confirm
            rerun_later()
        if st.session_state.report_confirm:
            with st.container(key="kdic-report"):
                st.caption("오류 분석을 위해 현재 대화 내용과 답변 처리 기록이 저장됩니다.")
                ok_col, cancel_col = st.columns(2)
                if ok_col.button("신고하기", key="report-confirm", type="primary",
                                 width="stretch"):
                    try:
                        ctx = report_context()
                        saved = oos_store.create_report(
                            ctx["payload"], session_id=ctx["session_id"],
                            report_path="top_button",
                            target_message_id=ctx["target_message_id"])
                        st.session_state.report_notice = (
                            "ok", f"오류 신고가 접수되었습니다 ({saved['report_id']}).")
                    except Exception:
                        st.session_state.report_notice = (
                            "error", "오류 신고를 저장하지 못했습니다. 접수된 것으로 처리하지 않았습니다.")
                    st.session_state.report_confirm = False
                    rerun_later()
                if cancel_col.button("취소", key="report-cancel", width="stretch"):
                    st.session_state.report_confirm = False
                    rerun_later()


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


@contextmanager
def loading_spinner(message: str, note: str = ""):
    """답변 생성 경로 공용 로딩 표시 — 기본 스피너 대신 KDIC 로고 스피너를 쓴다.

    자리는 `_pending_step` 경로와 같은 `_loading_box`(중앙 컬럼, 회색 패널 바로 아래).
    가짜 진행 단계를 만들지 않고 `ui_theme.loading()` 을 그대로 재사용한다.
    예외가 나도 finally 에서 지운다 — 스피너가 남으면 화면이 멈춘 것처럼 보인다.
    """
    with _loading_box:
        ph = st.empty()
    with ph.container():
        ui_theme.loading(message, note)
    try:
        yield
    finally:
        ph.empty()


def _error_result(e: BaseException) -> dict:
    """계약 4필드 + _meta 만 채운 오류 결과. 문구는 `humanize_error` 가 만든다.

    예외 원문·스택트레이스는 담지 않는다(§ humanize_error 와 같은 정책).
    `render_answer` 는 `text is None` 을 이미 오류 경로로 그린다 — 렌더는 그대로 재사용.
    """
    return {"text": None, "sources": [], "confidence": 0.0, "route": "error",
            "checks": {"ok": False, "flags": ["생성 실패"], "results": {}},
            "attachments": [],
            "_meta": {"error": f"exception:{type(e).__name__}"}}


def run_step(fn) -> bool:
    """답변 생성 1스텝 실행 — **예외를 스크립트 밖으로 내보내지 않는다.**

    예외가 새면 streamlit 이 그 아래를 아예 안 그린다. 우측 레일(추천 질문·상담원
    연결)·입력창은 이전 런의 DOM 이 stale 로 남아 흐릿하고 클릭이 안 되는 상태가
    된다 — "로딩은 끝났는데 화면 전체가 비활성"으로 보이는 증상의 정체다.
    오류는 대화 턴으로 적재하고 렌더는 끝까지 돌린다.
    """
    c0 = chain._calls
    try:
        ev = fn()
        if ev:
            # 콜 회계는 app 층에서 잰다 — chain 에 카운터를 심지 않는다(E2)
            record(ev, build_trace(ev, chain._calls - c0))
        return True
    except Exception as e:  # noqa: BLE001  화면을 죽이는 것보다 오류 턴이 낫다
        # 화면 문구는 humanize_error 그대로(원문 미노출). 진짜 원인은 콘솔에만 남긴다 —
        # 삼키기만 하면 무엇이 터졌는지 아무 데도 안 남아 디버깅이 막힌다.
        traceback.print_exc()
        append_history({"role": "answer", "r": _error_result(e), "slots": {},
                        "search_q": None, "trace": None, "followups": []})
        return False


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
        append_history(
            {
                "role": "answer",
                "r": ev["result"],
                "slots": ev["slots"],
                "search_q": ev["boosted"],
                "query": ev.get("search_q"),
                "trace": trace,
                "followups": qform_followup.suggest(ev["slots"]),
                "unit": ev.get("unit"),
                "routing": ev.get("routing"),
            }
        )


# ══════════════════════════════════════════════════════════════════════════
# 본문 — 사이드바 | 중앙(안내·대화·결과) | 우측 레일(지원 · 추천 · 근거 · 트레이스)
# (st.chat_input 은 컬럼 안에 못 들어가므로 최상위에서 부른다)
# ══════════════════════════════════════════════════════════════════════════
flow = st.session_state.flow
pending = flow["pending_slot"]
SHOW_TRACE = bool(st.session_state.get("show_trace"))

last_answer = max((i for i, t in enumerate(st.session_state.history)
                   if t["role"] == "answer"), default=None)

# 3단 고정. 트레이스 토글로 폭이 바뀌면 시연 중 화면이 널뛴다 — 레일은 항상 있고,
# 토글은 그 안의 트레이스 블록만 켜고 끈다.
col_main, col_right = st.columns([7.5, 2.5], gap="large")

unset_field = None
chip_q = None
followup_q = None
skip = False
chosen = None
cancel_qform = False

with col_main:
    _main_box = st.container(key="kdic-main")     # 배경색 앵커. 렌더 순서는 그대로다
    _loading_box = st.container()                 # 로딩 상태 — 회색 패널 **아래**
with _main_box:
    # 첫 화면은 요소 여러 개다 — 대화가 시작되면 그만큼이 이전 런의 잔상으로 남는다
    # (질문 아래에 옛 카드가 그대로 붙어 보이던 증상). 슬롯 하나로 묶어 두면
    # 다음 런이 그 슬롯을 비우는 것만으로 통째로 사라진다.
    _intro = st.empty()
    if not st.session_state.history:
        # 첫 화면 — 빈 입력창만 두면 무엇을 물어볼 수 있는지 알 수 없다(T5 B2)
        with _intro.container():
            ui_theme.welcome("안녕하세요, <b>예봄</b>입니다. 무엇을 도와드릴까요?")
            ui_theme.section("자주 찾는 업무")
            chip_q = render_cards() or chip_q

    for ti, turn in enumerate(st.session_state.history):
        # 말풍선·아바타 없음. 질문은 문서 제목, 답변은 본문으로 흐른다.
        if turn["role"] == "user":
            if ti:
                st.markdown('<hr class="kdic-rule">', unsafe_allow_html=True)
            st.markdown(f'<p class="kdic-q">{html.escape(turn["text"])}</p>',
                        unsafe_allow_html=True)
        elif turn["role"] == "ask":
            render_ask(turn)
        else:
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
    # 자리가 자연스럽다.
    pending_step = st.session_state.get("_pending_step")
    if pending_step:
        # 로딩 상태는 중앙 컬럼 안, 회색 패널 바로 아래에 뜬다 — 전체화면 오버레이도,
        # 별도 로딩 화면도 만들지 않는다. 문구는 코드에서 실제로 갈리는 두 경로만
        # 반영한다(되묻기 응답 vs 새 용건). 파이프라인 내부 단계 훅이 없으므로 가짜
        # 진행 단계를 지어내지 않는다.
        with _loading_box:
            _loading = st.empty()
            with _loading.container():
                if pending_step["is_reply"]:
                    ui_theme.loading("예봄이 선택하신 조건을 반영하고 있어요.")
                else:
                    # 안내 문구는 **실제로 최초 임베딩일 때만** 붙인다(embedding_cold).
                    ui_theme.loading(
                        "예봄이 답변을 준비하고 있어요.",
                        "관련 정보를 검색하고 있습니다."
                        + (" 최초 1회는 임베딩 모델 로딩으로 오래 걸립니다."
                           if embedding_cold() else ""),
                    )
        try:
            st.session_state.needs_regen = False
            if pending_step["is_reply"]:
                run_step(lambda: qform_flow.reply(
                    flow, pending_step["text"], ask_mode=ASK_MODE,
                    boost=BOOST, config=CONFIG,
                ))
            else:
                run_step(lambda: orchestrator.start_turn(
                    flow, pending_step["text"], ask_mode=ASK_MODE,
                    boost=BOOST, config=CONFIG,
                    report_context={**report_context(),
                                    "target_message_id": pending_step.get("previous_target", "")},
                ))
        finally:
            # 성공·실패와 무관하게 로딩 표시와 **대기 플래그를 같이** 내린다.
            # 플래그가 남으면 다음 런이 같은 호출을 또 시도해 로딩에서 못 빠져나온다.
            _loading.empty()
            st.session_state["_pending_step"] = None
        st.rerun()

    # 슬롯을 고친 뒤 되물을 것이 없으면 여기서 재생성을 **명시로** 받는다.
    # 자동 재생성을 안 하는 이유: 칩을 만질 때마다 HCX 2콜이 나가면 예산이 샌다(AC6-5).
    # 위젯 key 와 상태 플래그 이름을 반드시 갈라 둔다 — 같은 이름이면 버튼이 매 런
    # 자기 반환값을 session_state 에 써서 플래그를 덮어쓴다.
    if st.session_state.get("needs_regen") and not pending:
        ui_theme.notice("조건이 바뀌었습니다. 이 조건으로 답변을 다시 받으시겠어요?")
    regen = (st.button("이 조건으로 다시 답변받기", key="btn-regen", type="primary")
             if st.session_state.get("needs_regen") and not pending else False)

    if pending:
        # 맥락 칩 — 진행 바 대신. 취소(더블클릭)도 이 칩 하나가 겸한다.
        cancel_qform = render_branch_chip(flow)
        # 선택지 버튼 — 값이 조합 테이블에서 직접 온다(T5 B1). 자유 입력·탈출구는 그대로.
        _opts = qform_flow.options(flow)
        chosen = render_options(_opts, key_prefix=str(flow["ask_turn"]))
        # 탈출구 상시 노출 — 기획서 §4. 미선택(null)은 결함이 아니라 정상 입력이다.
        # 선택지가 있으면 `render_options` 안의 [이대로 답변받기]가 같은 일을 하므로
        # 여기서 한 번 더 그리지 않는다. 선택지가 없을 때만 유일한 탈출구로 남는다.
        skip = (False if _opts else
                st.button("잘 모르겠어요 — 이대로 답변받기", key=f"skip-{flow['ask_turn']}"))

    _queue_box = st.container()                   # 다음 용건 안내 자리 (아래에서 채운다)

with col_right:
    with st.container(key="kdic-rail"):
        render_support_card()
        tab_reco, tab_evidence = st.tabs(["추천 질문", "근거 자료"])
        with tab_reco:
            chip_q = render_recommended_questions("reco") or chip_q
        with tab_evidence:
            if last_answer is not None:
                _last = st.session_state.history[last_answer]
                render_evidence_card(_last["r"])
                render_evidence_chunks(_last["r"])
            else:
                st.caption("답변을 받으면 이 자리에 근거 문서·근거 조각이 표시됩니다.")
        if SHOW_TRACE:
            # 관리자 정보는 추천 콘텐츠 **아래**. 라벨·스크롤박스는 qform_panel 이 갖고 있다.
            st.markdown("")
            qform_panel.render([t["trace"] for t in st.session_state.history
                                if t.get("trace")])

# ver4 M3 — 메모리 패널. 사이드바 중간 구역(_sb_mem)에 그린다.
_panel_action = None
if st.session_state.history:
    with _sb_mem:
        st.divider()
        _panel_action = render_memory_panel(flow)

# 입력 바 — 화면 최하단 고정. 반환 계약은 이전과 같다(질의 문자열 또는 None).
# 컬럼 안에서 부르면 고정이 풀린다.
q = st.chat_input("궁금한 내용을 입력해주세요.")

# 진입 로딩 화면 정리 — 화면을 다 그린 **뒤, 이 런 안에서** 지운다(위 SPLASH_HOLD_SEC 주석).
# rerun 으로 지우면 지워지기 전에 런이 끝나 remount 가 먼저 오고, 그때 애니메이션이
# 되감긴다. 여기서 지우면 런이 끝날 때 남아 있는 요소가 없다.
if _splash is not None:
    time.sleep(max(0.0, _splash_until - time.monotonic()))
    _splash.empty()

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
    with loading_spinner("예봄이 답변을 준비하고 있어요.", "관련 정보를 검색하고 있습니다."):
        if run_step(lambda: qform_flow.answer_now(flow, boost=BOOST)):
            st.session_state.needs_regen = False
    st.rerun()

if cancel_qform and pending:
    # 맥락 칩 더블클릭 — 답변을 만들지 않고 되묻기만 중단한다(HCX 콜 0).
    qform_flow.cancel(flow, config=CONFIG)
    st.rerun()

if skip and pending:
    with loading_spinner("예봄이 답변을 준비하고 있어요.", "관련 정보를 검색하고 있습니다."):
        if run_step(lambda: qform_flow.skip(flow, boost=BOOST, config=CONFIG)):
            st.session_state.needs_regen = False
    st.rerun()

if chosen == _ESCAPE and pending:
    # K9 [이대로 답변받기] — ver2 탈출구(`skip`)를 버튼으로 한 번 더 연 것이다.
    append_history({"role": "user", "text": "이대로 답변받기"})
    with loading_spinner("예봄이 답변을 준비하고 있어요.", "관련 정보를 검색하고 있습니다."):
        if run_step(lambda: qform_flow.skip(flow, boost=BOOST, config=CONFIG)):
            st.session_state.needs_regen = False
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
    with loading_spinner("예봄이 답변을 준비하고 있어요.", "관련 정보를 검색하고 있습니다."):
        if run_step(lambda: qform_flow.reply(flow, chosen, value=chosen,
                                             ask_mode=ASK_MODE, boost=BOOST, config=CONFIG)):
            st.session_state.needs_regen = False
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
    with _queue_box:
        ui_theme.notice(f"대기 중인 용건이 {len(flow['unit_queue'])}개 있습니다.")
        next_queued = st.button("다음 용건 처리", key="next-unit", type="primary")

if next_queued:
    with loading_spinner("예봄이 다음 용건을 처리하고 있어요."):
        run_step(lambda: orchestrator.next_unit(
            flow, ask_mode=ASK_MODE, boost=BOOST, config=CONFIG,
            report_context=report_context()))
    st.rerun()

if q_new or q_reply:
    # 사용자 메시지를 먼저 렌더하고, 다음 rerun에서 중앙 대화창 안에 spinner를 표시한다.
    text = q_new or q_reply
    previous_target = last_answer_id()
    append_history({"role": "user", "text": text})
    st.session_state["_pending_step"] = {
        "text": text,
        "is_reply": bool(q_reply),
        "previous_target": previous_target,
    }
    st.rerun()

# 렌더 도중 요청된 rerun 은 여기서 한 번만 돌린다 — `rerun_later()` 주석 참조.
if st.session_state.pop("_rerun_after_render", False):
    st.rerun()
