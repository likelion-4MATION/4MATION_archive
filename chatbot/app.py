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
import pathlib
import sys

import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "chatbot"))
sys.path.insert(0, str(ROOT / "crawler"))

import chain
import qform_flow
import qform_followup
import qform_panel
import qform_state
import qform_trace

ROUTE_LABEL = {"rag": "문서 기반 답변", "link": "타기관 안내", "reject": "소관 밖"}
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

st.set_page_config(page_title="KDIC 안내 챗봇 PoC", page_icon="💬", layout="wide")
st.title("💬 KDIC 안내 챗봇 — PoC")
st.caption("예금보험공사 안내 문서에 근거해 답변합니다. (실전2 end 데모 · 큐폼 배선)")

st.session_state.setdefault("history", [])
st.session_state.setdefault("flow", qform_flow.new_state())
st.session_state.setdefault("needs_regen", False)   # 슬롯 수정 후 재답변 대기 (T6)

with st.sidebar:
    st.subheader("세션 상태")
    _left_calls = chain.CALL_BUDGET - chain._calls
    st.metric("HCX 콜 (재시도 포함)", f"{chain._calls} / {chain.CALL_BUDGET}")
    # 예산 경고 (T7 B6-1) — 소진되고 나서 알면 시연 도중에 막힌다. 미리 보여 준다.
    if _left_calls <= 0:
        st.error("모델 호출 예산 소진 — 새 답변을 만들 수 없습니다. "
                 "되묻기·선택지·슬롯 수정은 계속 동작합니다 (콜 0).")
    elif _left_calls <= LOW_CALL_WARN:
        st.warning(f"남은 모델 호출 {_left_calls}회. 답변 1건당 2콜(분류+생성)을 씁니다.")
    st.caption("되묻기 턴은 ⓐ 모드에서 콜을 쓰지 않습니다. 예산 소진 시 앱 재시작으로 리셋됩니다.")
    st.divider()

    st.subheader("큐폼")
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
    st.checkbox("트레이스 패널", value=True, key="show_trace",
                help="질의 1건이 어느 층에서 어떻게 갈렸는지 보여줍니다.")
    st.caption("첨부 후단 필터는 항상 켜져 있습니다 (슬롯이 비면 자동으로 기존 동작).")

    if st.button("대화 초기화"):
        st.session_state.history = []
        st.session_state.flow = qform_flow.new_state()
        st.session_state.needs_regen = False
        st.rerun()

    st.divider()
    st.caption(
        "표시되는 유사도는 질문-문서 관련도이며 정답 확신도가 아닙니다. "
        "검증 플래그는 참고용이며 답변을 차단하지 않습니다."
    )

ASK_MODE = ASK_MODES[st.session_state.get("ask_mode_label", "ⓐ 템플릿 (콜 0)")]
BOOST = bool(st.session_state.get("boost"))


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
    if r["sources"]:
        with st.expander("근거 문서"):
            for i, s in enumerate(r["sources"], 1):
                st.markdown(f"{i}. [{s['title']}]({s['url']})")
    render_attachments(r.get("attachments") or [], key_prefix)
    if not r["checks"]["ok"]:
        with st.expander("⚑ 검증 플래그 (차단 아님)"):
            for f in r["checks"]["flags"]:
                st.markdown(f"- {f}")

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
    return picked


def render_chips(key_prefix: str, per_row: int = 3) -> str | None:
    """예시 질의 칩 (T5 B2). 클릭된 질의 문구를 돌려준다.

    문구는 `docs/qform_시험질의셋.md` 원문이다 — `EXAMPLE_CHIPS` 주석에 출처를 남겼다.
    """
    picked = None
    for i in range(0, len(EXAMPLE_CHIPS), per_row):
        chunk = EXAMPLE_CHIPS[i:i + per_row]
        for col, (label, query) in zip(st.columns(len(chunk)), chunk):
            if col.button(label, key=f"chip-{key_prefix}-{label}", width="stretch",
                          help=query):
                picked = query
    return picked


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
        st.session_state.history.append(
            {"role": "ask", "prompt": ev["prompt"], "remaining": ev["remaining"],
             "mode": a["mode"], "calls": a["calls"], "fallback": a["fallback_reason"],
             "trace": trace}
        )
    else:
        # 후속 추천은 여기서 **한 번** 계산해 히스토리에 굳힌다. 매 렌더마다 다시 뽑으면
        # 나중 턴의 슬롯이 과거 답변의 추천을 바꿔 버린다. 결정론이고 콜 0 이다.
        st.session_state.history.append(
            {"role": "answer", "r": ev["result"], "slots": ev["slots"],
             "search_q": ev["boosted"], "trace": trace,
             "followups": qform_followup.suggest(ev["slots"])}
        )


# ══════════════════════════════════════════════════════════════════════════
# 본문 — 좌측 대화 / 우측 트레이스 (st.chat_input은 컬럼 안에 못 들어가므로 최상위)
# ══════════════════════════════════════════════════════════════════════════
flow = st.session_state.flow
pending = flow["pending_slot"]
SHOW_TRACE = bool(st.session_state.get("show_trace"))

left, right = st.columns([3, 2]) if SHOW_TRACE else (st.container(), None)

last_answer = max((i for i, t in enumerate(st.session_state.history)
                   if t["role"] == "answer"), default=None)

with left:
    unset_field = None
    chip_q = None
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
        # 첫 화면 — 빈 입력창만 두면 무엇을 물어볼 수 있는지 알 수 없다(T5 B2)
        st.caption("이런 걸 물어볼 수 있어요")
        chip_q = render_chips("home")

if right is not None:
    with right:
        qform_panel.render([t["trace"] for t in st.session_state.history if t.get("trace")])

# 대화가 시작되면 칩은 사이드바로 옮긴다 — 본문을 차지하지 않으면서 항상 닿는다.
if st.session_state.history:
    with st.sidebar:
        st.divider()
        st.subheader("예시 질의")
        chip_q = render_chips("side", per_row=1) or chip_q

q = st.chat_input("예: 착오송금 반환 신청 서류가 뭐예요?")

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
    ev = qform_flow.edit(flow, field, value, source=source, ask_mode=ASK_MODE)
    st.session_state.history.append({"role": "user", "text": note})
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
        ev = qform_flow.skip(flow, boost=BOOST)
        st.session_state.needs_regen = False
        record(ev, build_trace(ev, chain._calls - c0))
    st.rerun()

if chosen and pending:
    # 버튼 경로 — `value=` 로 값을 직접 주입한다. 자연어 추출을 경유하지 않는다.
    st.session_state.history.append({"role": "user", "text": chosen})
    with st.spinner("처리 중…"):
        c0 = chain._calls
        ev = qform_flow.reply(flow, chosen, value=chosen, ask_mode=ASK_MODE, boost=BOOST)
        st.session_state.needs_regen = False
        record(ev, build_trace(ev, chain._calls - c0))
    st.rerun()

# 예시 칩은 되묻기 중이어도 **새 질의**다 — 사용자가 다른 걸 물으려고 누른 것이다.
# (후속 추천은 새 질의가 아니라 슬롯 좁히기라 위 `_edit` 경로로 빠진다.)
q_new, q_reply = (chip_q, None) if chip_q else ((None, q) if pending else (q, None))

if q_new or q_reply:
    text = q_new or q_reply
    st.session_state.history.append({"role": "user", "text": text})
    # 되묻기 턴이면 즉시 끝나고, 답변 턴이면 검색·생성이 돈다. 어느 쪽인지는 전이가 정한다.
    with st.spinner("처리 중… (최초 1회는 임베딩 모델 로딩으로 오래 걸립니다)"):
        c0 = chain._calls
        step = qform_flow.reply if q_reply else qform_flow.start
        st.session_state.needs_regen = False
        ev = step(flow, text, ask_mode=ASK_MODE, boost=BOOST)
        # 콜 회계는 app 층에서 잰다 — chain 에 카운터를 심지 않는다(E2)
        record(ev, build_trace(ev, chain._calls - c0))
    st.rerun()
