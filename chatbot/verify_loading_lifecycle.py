"""로딩 상태 lifecycle 회귀 검증 — `python -m verify_loading_lifecycle` (chatbot/ 에서).

지키는 것 하나: **답변 생성 중 예외가 스크립트 밖으로 새면 안 된다.**
새면 streamlit 이 그 아래(우측 레일·입력창)를 안 그리고, 이전 런의 DOM 이 stale 로
남아 화면 전체가 흐릿·클릭 불가가 된다. `run_step` 이 그 경계다.
"""
import warnings

warnings.filterwarnings("ignore")
import streamlit as st

import app


def main() -> None:
    r = app._error_result(RuntimeError("boom"))
    assert r["text"] is None and r["route"] == "error"
    assert {"text", "sources", "confidence", "route"} <= r.keys(), "계약 4필드"
    assert r["_meta"]["error"] == "exception:RuntimeError"
    assert "boom" not in str(r), "예외 원문이 화면 계약에 새면 안 된다"
    assert "오류" in app.humanize_error(r["_meta"]["error"])

    st.session_state.history = []
    ok = app.run_step(lambda: (_ for _ in ()).throw(ValueError("x")))
    assert ok is False, "예외는 False 로만 알린다 — 밖으로 던지지 않는다"
    assert len(st.session_state.history) == 1, "오류도 대화 턴으로 남는다"
    assert st.session_state.history[0]["r"]["text"] is None

    assert app.run_step(lambda: None) is True, "이벤트 없음은 실패가 아니다"
    assert len(st.session_state.history) == 1
    print("OK: run_step catches, records error turn")


if __name__ == "__main__":
    main()
