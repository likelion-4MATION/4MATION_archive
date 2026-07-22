"""chatbot/app.py — 실전2 end 데모 Streamlit UI (D트랙 mock→실물 전환).

동결 계약 answer() -> {text, sources, confidence, route, checks, _meta}만 소비한다.
confidence 표기는 07-22 결정대로 "관련 문서 유사도"(정답 확신도 아님).

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

ROUTE_LABEL = {"rag": "문서 기반 답변", "link": "타기관 안내", "reject": "소관 밖"}

st.set_page_config(page_title="KDIC 안내 챗봇 PoC", page_icon="💬")
st.title("💬 KDIC 안내 챗봇 — PoC")
st.caption("예금보험공사 안내 문서에 근거해 답변합니다. (실전2 end 데모)")

with st.sidebar:
    st.subheader("세션 상태")
    st.metric("HCX 콜 (재시도 포함)", f"{chain._calls} / {chain.CALL_BUDGET}")
    st.caption("예산 소진 시 앱을 재시작하면 리셋됩니다.")
    st.divider()
    st.caption(
        "표시되는 유사도는 질문-문서 관련도이며 정답 확신도가 아닙니다. "
        "검증 플래그는 참고용이며 답변을 차단하지 않습니다."
    )


def render_answer(r: dict) -> None:
    """answer() 결과 1건 렌더 — 계약 4필드 + 부가(checks/_meta)만 사용."""
    if r["text"] is None:
        st.error(f"답변 생성 실패: {r['_meta'].get('error', '원인 미상')}")
        return
    st.markdown(r["text"])
    meta = r["_meta"]
    st.caption(
        f"{ROUTE_LABEL.get(r['route'], r['route'])}"
        f" · 관련 문서 유사도 {r['confidence']:.2f}"
        f" · {meta.get('latency_ms') or '?'}ms"
    )
    if r["sources"]:
        with st.expander("근거 문서"):
            for i, s in enumerate(r["sources"], 1):
                st.markdown(f"{i}. [{s['title']}]({s['url']})")
    if not r["checks"]["ok"]:
        with st.expander("⚑ 검증 플래그 (차단 아님)"):
            for f in r["checks"]["flags"]:
                st.markdown(f"- {f}")


if "history" not in st.session_state:
    st.session_state.history = []

for turn in st.session_state.history:
    with st.chat_message("user"):
        st.markdown(turn["q"])
    with st.chat_message("assistant"):
        render_answer(turn["r"])

q = st.chat_input("예: 예금보험금은 어떻게 신청하나요?")
if q:
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant"):
        with st.spinner("문서 검색·답변 생성 중… (최초 1회는 임베딩 모델 로딩으로 오래 걸립니다)"):
            r = chain.answer(q)
        render_answer(r)
    st.session_state.history.append({"q": q, "r": r})
    st.rerun()
