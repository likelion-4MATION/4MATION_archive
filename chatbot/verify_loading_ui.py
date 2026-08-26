# -*- coding: utf-8 -*-
"""로딩 UI 불변식 검증 — 진입 스플래시 1회 · 렌더 중 rerun 금지 · 임베딩 안내 조건.

`app.py` 는 import 즉시 페이지를 그리므로 소스에서 필요한 조각만 떼어 확인한다.
셋 다 "화면을 눈으로 보고" 가 아니라 **코드가 지키는 조건**으로 잡는 항목이다.
"""
from __future__ import annotations

import pathlib
import re
import sys
import types

SRC = (pathlib.Path(__file__).resolve().parent / "app.py").read_text(encoding="utf-8")


def check_embedding_cold() -> None:
    """안내 문구는 **캐시 상태**로 판정한다 — 화면 상태나 세션 플래그가 아니다."""
    block = SRC[SRC.index("def embedding_cold"):SRC.index("def _utc_now")]
    g: dict = {"sys": sys}
    exec(block, g)
    cold = g["embedding_cold"]

    saved = sys.modules.pop("rag", None)
    try:
        assert cold() is True, "rag 미임포트 = 최초 임베딩 → 안내 노출"

        stub = types.ModuleType("rag")
        stub._model = None
        sys.modules["rag"] = stub
        assert cold() is True, "모델 미로드 → 안내 노출"

        stub._model = object()
        assert cold() is False, "모델 로드 완료 → 재진입·Ctrl+R 이어도 안내 없음"
    finally:
        sys.modules.pop("rag", None)
        if saved is not None:
            sys.modules["rag"] = saved
    print("[OK] embedding_cold : 캐시 상태 기준으로 3가지 경우 모두 일치")


def check_no_rerun_during_render() -> None:
    """렌더 함수 안에서 st.rerun() 을 부르면 그 아래 위젯이 그 런에서 선언되지 않는다.

    직전 런의 요소가 남은 채 새 런의 요소가 얹혀 같은 패널이 두 벌 보인다
    (실측 버튼 27→40→28). 렌더 구간의 rerun 은 전부 `rerun_later()` 여야 한다.
    """
    render_zone = SRC[SRC.index("def rerun_later"):SRC.index("flow = st.session_state.flow\npending")]
    bad = [i for i, ln in enumerate(render_zone.splitlines(), 1)
           if ln.strip() == "st.rerun()"]     # 호출문만 본다(주석·독스트링 언급은 통과)
    assert not bad, f"렌더 도중 st.rerun() 호출. rerun_later() 로 바꾸세요: 줄 {bad}"

    assert 'st.session_state.pop("_rerun_after_render", False)' in SRC, \
        "미룬 rerun 을 스크립트 끝에서 처리하는 구문이 없다"
    print(f"[OK] render st.rerun() 0건 · rerun_later() {render_zone.count('rerun_later()') - 1}곳 · 끝에서 1회 처리")


def check_splash_once() -> None:
    """스플래시는 세션 첫 런에만 그리고, **그 런 안에서 python 이 지운다**.

    CSS 애니메이션에 제거를 맡기면 런 종료 시 remount 로 시계가 되감겨 두 번 뜬다
    (실측 mount 0.65s → 페이드 1.66s → opacity 1 복귀 2.06s). 지워 두면 remount 될
    요소가 없다. 페이드아웃은 제거 시점(SPLASH_HOLD_SEC)보다 **먼저** 끝나야 한다.
    """
    assert SRC.count("ui_theme.splash(") == 1, "스플래시 호출 지점은 1곳이어야 한다"
    assert "_splash.empty()" in SRC, "python 이 스플래시를 제거하지 않는다"
    # 자리는 **조건 밖**에서 잡아야 한다. 첫 런에만 요소를 만들면 다음 런부터
    # 뒤 요소의 인덱스가 밀려 본문 컬럼이 통째로 한 벌 더 남는다.
    slot_line = SRC.index("_splash_slot = st.empty()")
    assert slot_line < SRC.index('if not st.session_state.get("_splashed")'),         "_splash_slot 은 _splashed 분기보다 먼저, 매 런 만들어져야 한다"
    hold = float(re.search(r"SPLASH_HOLD_SEC = ([\d.]+)", SRC).group(1))
    assert 3.0 <= hold <= 5.0, f"유지 시간 {hold}s 가 3~5s 밖이다"

    css = (pathlib.Path(__file__).resolve().parent / "ui_theme.py").read_text(encoding="utf-8")
    dur, delay = re.search(r"animation: yebom-out ([\d.]+)s ease ([\d.]+)s", css).groups()
    assert float(dur) + float(delay) <= hold, \
        f"페이드아웃 종료 {float(dur)+float(delay)}s 가 제거 시점 {hold}s 보다 늦다"
    print(f"[OK] splash 1회 · 유지 {hold}s · 페이드 종료 {float(dur)+float(delay)}s < 제거 {hold}s")


if __name__ == "__main__":
    check_embedding_cold()
    check_no_rerun_during_render()
    check_splash_once()
