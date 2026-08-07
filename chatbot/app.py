"""chatbot/app.py — 실전2 end 데모 Streamlit UI (큐폼 E2E 배선).

동결 계약 answer() -> {text, sources, confidence, route, checks, _meta}만 소비한다.
confidence 표기는 07-22 결정대로 "관련 문서 유사도"(정답 확신도 아님).

큐폼 배선 (Qform_ver1):
    질의 → extract(결정론, 콜 0) → next_question?
         ├ 있으면 되묻기(최대 2턴). **되묻기 턴에는 answer()를 부르지 않는다** → HCX 콜 0
         └ 없으면 answer(query, qform=slots) → 첨부 후단 필터

쿼리 부스트(serialize)는 **기본 OFF**. 검색 동작을 바꾸므로 450셋 회귀 수치가 나오기
전에는 켜지 않는다(§1-4 no numbers, no merge). 사이드바 토글로 시연 중 비교만 가능.

실행: streamlit run chatbot/app.py
주의: chain.CALL_BUDGET(10콜, 재시도 포함)을 공유 — 소진 시 앱 재시작으로 리셋.
"""
import pathlib
import sys

import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "chatbot"))
sys.path.insert(0, str(ROOT / "crawler"))

import chain
import qform_state
from qform_extract import IN_SCOPE_BF, extract

ROUTE_LABEL = {"rag": "문서 기반 답변", "link": "타기관 안내", "reject": "소관 밖"}
MAX_ASK_TURNS = 2                       # D2: 되묻기 상한
SLOT_LABEL = {"party": "역할", "sub_task": "세부주제", "qualification": "자격",
              "subject": "주체", "method": "접수수단"}

st.set_page_config(page_title="KDIC 안내 챗봇 PoC", page_icon="💬")
st.title("💬 KDIC 안내 챗봇 — PoC")
st.caption("예금보험공사 안내 문서에 근거해 답변합니다. (실전2 end 데모 · 큐폼 배선)")

with st.sidebar:
    st.subheader("세션 상태")
    st.metric("HCX 콜 (재시도 포함)", f"{chain._calls} / {chain.CALL_BUDGET}")
    st.caption("되묻기 턴은 콜을 쓰지 않습니다. 예산 소진 시 앱 재시작으로 리셋됩니다.")
    st.divider()

    st.subheader("큐폼")
    st.checkbox(
        "쿼리 부스트 (실험)", value=False, key="boost",
        help="슬롯 값을 검색 쿼리에 덧붙입니다. 검색 동작이 바뀌므로 450셋 회귀 수치가 "
             "나오기 전까지는 기본 OFF입니다. 첨부 후단 필터는 토글과 무관하게 항상 동작합니다.",
    )
    st.caption("첨부 후단 필터는 항상 켜져 있습니다 (슬롯이 비면 자동으로 기존 동작).")
    if st.button("대화 초기화"):
        st.session_state.history = []
        st.session_state.pending = None
        st.rerun()

    st.divider()
    st.caption(
        "표시되는 유사도는 질문-문서 관련도이며 정답 확신도가 아닙니다. "
        "검증 플래그는 참고용이며 답변을 차단하지 않습니다."
    )


# ══════════════════════════════════════════════════════════════════════════
# 렌더 헬퍼
# ══════════════════════════════════════════════════════════════════════════
def _fmt_size(n) -> str:
    if not n:
        return ""
    return f" · {n / 1024:.0f}KB" if n < 1024 * 1024 else f" · {n / 1024 / 1024:.1f}MB"


def _clean(slots: dict) -> dict:
    """추출기 부가키(_hits/_bf/_scope) 제거 — answer()·survivors()에 넘길 순수 슬롯."""
    return {f: slots.get(f) for f in qform_state.SLOT_FIELDS}


def render_slots(slots: dict) -> None:
    """채워진 슬롯 노출 — 기획서 §7 '조용히 반영 금지'. 사용자가 보고 고칠 수 있어야 한다."""
    filled = [(SLOT_LABEL.get(f, f), v) for f, v in _clean(slots).items() if v]
    if not filled:
        return
    st.caption("🎯 " + " · ".join(f"{lab} **{v}**" for lab, v in filled))


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
                  search_q: str | None = None) -> None:
    """answer() 결과 1건 렌더 — 계약 4필드 + 부가(checks/_meta)만 사용."""
    if r["text"] is None:
        st.error(f"답변 생성 실패: {r['_meta'].get('error', '원인 미상')}")
        return
    st.markdown(r["text"])
    if slots:
        render_slots(slots)
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


# ══════════════════════════════════════════════════════════════════════════
# 큐폼 상태 전이
# ══════════════════════════════════════════════════════════════════════════
def _finalize(base_q: str, slots: dict) -> None:
    """되묻기 종료 → 검색·생성. 부스트 ON이면 슬롯을 쿼리에 직렬화해 덧붙인다."""
    slots = _clean(slots)
    search_q, shown = base_q, None
    if st.session_state.get("boost"):
        extra = qform_state.serialize(slots)
        if extra:
            search_q = f"{base_q} {extra}"
            shown = search_q
    with st.spinner("문서 검색·답변 생성 중… (최초 1회는 임베딩 모델 로딩으로 오래 걸립니다)"):
        r = chain.answer(search_q, qform=slots)
    st.session_state.history.append(
        {"role": "answer", "r": r, "slots": slots, "search_q": shown}
    )
    st.session_state.pending = None


def _ask(base_q: str, slots: dict, nq: dict, turns: int) -> None:
    st.session_state.pending = {
        "q": base_q, "slots": _clean(slots), "turns": turns,
        "prompt": nq["prompt"], "remaining": nq["remaining"],
    }
    st.session_state.history.append(
        {"role": "ask", "prompt": nq["prompt"], "remaining": nq["remaining"]}
    )


def _step(base_q: str, slots: dict, turns: int) -> None:
    """되묻기 판정 후 분기. turns 상한 도달 시 강제 종료."""
    nq = qform_state.next_question(_clean(slots)) if turns < MAX_ASK_TURNS else None
    if nq:
        _ask(base_q, slots, nq, turns + 1)
    else:
        _finalize(base_q, slots)


# ══════════════════════════════════════════════════════════════════════════
# 본문
# ══════════════════════════════════════════════════════════════════════════
st.session_state.setdefault("history", [])
st.session_state.setdefault("pending", None)

for ti, turn in enumerate(st.session_state.history):
    if turn["role"] == "user":
        with st.chat_message("user"):
            st.markdown(turn["text"])
    elif turn["role"] == "ask":
        with st.chat_message("assistant"):
            st.markdown(turn["prompt"])
            st.caption(f"남은 후보 {turn['remaining']}개 · 건너뛰어도 답변합니다")
    else:
        with st.chat_message("assistant"):
            render_answer(turn["r"], key_prefix=f"h{ti}",
                          slots=turn.get("slots"), search_q=turn.get("search_q"))

pending = st.session_state.pending
skip = False
if pending:
    # 탈출구 상시 노출 — 기획서 §4. 미선택(null)은 결함이 아니라 정상 입력이다.
    skip = st.button("잘 모르겠어요 — 이대로 답변받기", key=f"skip-{pending['turns']}")

q = st.chat_input("예: 착오송금 반환 신청 서류가 뭐예요?")

if skip and pending:
    _finalize(pending["q"], pending["slots"])
    st.rerun()

if q:
    st.session_state.history.append({"role": "user", "text": q})
    if pending:
        # 되묻기 응답 — 후속 답변만으로는 스코프 게이트에 막히므로 원질의와 합쳐
        # business_function 을 명시로 넘긴다.
        merged = extract(f"{pending['q']} {q}", business_function=IN_SCOPE_BF)
        slots = {**pending["slots"]}
        for f in qform_state.SLOT_FIELDS:          # 기존 값 보존, 빈 칸만 채움
            if not slots.get(f) and merged.get(f):
                slots[f] = merged[f]
        _step(pending["q"], slots, pending["turns"])
    else:
        _step(q, extract(q), 0)
    st.rerun()
