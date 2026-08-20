# -*- coding: utf-8 -*-
"""우측 트레이스 패널 — T6.

`qform_trace.collect()` 가 만든 층별 트레이스를 **화면 모델**로 바꾸고(`panel_model`,
순수 함수) streamlit 이 그것만 소비해 그린다(`render`). 갈라둔 이유는 T4·T5 와 같다 —
"무엇을 그릴지"를 UI 없이 실측할 수 있어야 하고, 그래야 층 구성이 문서·수집기와
어긋나지 않는다.

층 순서·라벨·결정론 구간은 **`qform_trace` 가 소유**한다(`LAYER_ORDER`·`LAYER_LABEL`·
`DETERMINISTIC`). 여기서 다시 정의하지 않는다 — 두 곳에 적으면 드리프트가 난다.

기본 펼침 규칙: **분기가 일어난 층만** 펼친다. 9층을 다 펼치면 되묻기 2턴에서
패널이 대화를 밀어낸다. "무슨 일이 있었나"를 한눈에 주는 게 목적이지 전부 보이는 게
목적이 아니다.
"""
from __future__ import annotations

import pathlib
import sys

_BASE = pathlib.Path(__file__).resolve().parent.parent
for _p in (_BASE / "chatbot", _BASE / "crawler"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from qform_trace import DETERMINISTIC, LAYER_LABEL, LAYER_ORDER  # noqa: E402

SLOT_LABEL = {"party": "역할", "sub_task": "세부주제", "qualification": "자격",
              "subject": "주체", "method": "접수수단"}
PANEL_HEIGHT = 620          # 우측 패널 고정 높이 — 대화 영역을 밀어내지 않게 스크롤을 가둔다
MAX_SCORE_ROWS = 3          # 업무 신호 점수표에 보여줄 상위 업무 수


def highlight(text: str, keywords) -> str:
    """질의 원문에서 트리거 키워드를 **볼드**로 감싼다.

    겹치면 긴 키워드가 이긴다("착오송금" vs "송금"). 유도 표기(`⟵sub_task:…`)는
    원문에 없는 값이라 건너뛴다.
    """
    kws = {k for k in (keywords or []) if k and not str(k).startswith("⟵")}
    spans: list[tuple[int, int]] = []
    for kw in sorted(kws, key=len, reverse=True):
        start = 0
        while True:
            i = text.find(kw, start)
            if i < 0:
                break
            if not any(s < i + len(kw) and i < e for s, e in spans):
                spans.append((i, i + len(kw)))
            start = i + 1
    if not spans:
        return text
    out, last = [], 0
    for s, e in sorted(spans):
        out.append(text[last:s])
        out.append(f"**{text[s:e]}**")
        last = e
    out.append(text[last:])
    return "".join(out)


def _card(key, headline, *, open_=False, rows=None, extra=None, calls=None, status="수집"):
    badge = "콜 0" if key in DETERMINISTIC else (f"콜 {calls}" if calls is not None else "콜 ?")
    return {"key": key, "label": LAYER_LABEL[key], "headline": headline, "open": open_,
            "badge": badge, "status": status, "rows": rows or [], "extra": extra or {}}


def panel_model(trace: dict) -> dict:
    """트레이스 1건 → 패널 화면 모델. **streamlit 을 모른다.**

    반환: {"title", "subtitle", "calls", "cards": [카드…]}
        카드: {"key","label","headline","open","badge","status","rows","extra"}
    """
    if not trace:
        return {"title": "트레이스 없음", "subtitle": "", "calls": {}, "cards": []}
    if trace.get("error") or not trace.get("layers"):
        return {"title": "트레이스 조립 실패", "subtitle": trace.get("error", ""),
                "calls": {}, "cards": []}

    L = trace["layers"]
    q = trace.get("query") or ""
    cards = []

    for key in LAYER_ORDER:
        lay = L[key]
        st_ = lay.get("status", "수집")
        if st_.startswith("생략"):
            cards.append(_card(key, st_, calls=lay.get("calls"), status=st_))
            continue

        if key == "gate":
            cards.append(_card(
                key, f"{lay['label'] or '—'} — {lay['reason'] or ''}",
                open_=lay["label"] not in (None, "정상"), calls=lay["calls"],
                rows=[("라우트", lay["route"]), ("분류 콜", lay["calls"]),
                      ("지연", f"{lay['latency_ms']}ms" if lay["latency_ms"] else "—"),
                      ("JSON 파싱 실패", lay["parse_fail"])]))

        elif key == "bf":
            top = sorted(lay["scores"].items(), key=lambda x: -x[1])[:MAX_SCORE_ROWS]
            cards.append(_card(
                key, f"{lay['bf'] or '불명'}  [{lay['verdict']}]",
                open_=lay["verdict"] != "확정", calls=0,
                rows=[("판정 사유", lay["reason"])],
                extra={"scores": [(bf, sc, lay["hits"].get(bf, [])) for bf, sc in top],
                       "margin": lay["margin"],
                       "query_hl": highlight(q, [k for hs in lay["hits"].values()
                                                 for k, _, _ in hs])}))

        elif key == "slots":
            trig = [t for ts in (lay["triggers"] or {}).values() for t in ts]
            cards.append(_card(
                key, f"{lay['filled']}/5 채움 · 스코프 {lay['scope']}",
                open_=lay["filled"] > 0, calls=0,
                rows=[(SLOT_LABEL.get(f, f), v or "—") for f, v in lay["slots"].items()],
                extra={"query_hl": highlight(q, trig),
                       "triggers": lay["triggers"] or {}, "bf_used": lay["bf_used"]}))

        elif key == "combos":
            trail = lay["trail"]
            cards.append(_card(
                key, " → ".join(str(n) for _, n in trail),
                open_=lay["remaining"] < lay["total"], calls=0,
                rows=[("생존 조합", ", ".join(lay["combo_ids"]) or "—")],
                extra={"trail": trail, "total": lay["total"], "remaining": lay["remaining"]}))

        elif key == "ask":
            if lay["fired"]:
                head = f"{SLOT_LABEL.get(lay['slot'], lay['slot'])} 물음 · {lay['turn']}턴"
                rows = [("사유", lay["reason"]),
                        ("문구 모드", "ⓐ 템플릿" if lay["mode"] == "template" else "ⓑ LLM"),
                        ("되묻기 콜", lay["calls"]),
                        ("제시한 값", ", ".join(lay["values"] or []) or "—")]
                if lay["fallback_reason"]:
                    rows.append(("⚠ 폴백 사유", lay["fallback_reason"]))
            else:
                head, rows = "되묻지 않음", [("사유", lay["reason"])]
            cards.append(_card(key, head, open_=bool(lay["fired"] or lay["fallback_reason"]),
                               calls=lay["calls"],
                               rows=rows, extra={"prompt": lay["prompt"],
                                                 "fallback": lay["fallback_reason"],
                                                 "mode": lay["mode"]}))

        elif key == "search":
            head = f"top-{lay['k']} · {len(lay['docs'])}건"
            if lay["bf_drift"]:
                head += "  ⚠ 업무 갈림"
            rows = [("부스트", "ON" if lay["boost_applied"] else "OFF"),
                    ("검색 쿼리", lay["search_q"])]
            if lay["bf_drift"]:
                rows.append(("검색측 업무", f"{lay['search_bf']} (app 판정과 다름)"))
            cards.append(_card(key, head, open_=bool(lay["bf_drift"] or lay["boost_applied"]),
                               calls=0, rows=rows, extra={"docs": lay["docs"]}))

        elif key == "generate":
            cards.append(_card(
                key, f"{lay['latency_ms'] or '?'}ms · {lay['chars'] or 0}자",
                open_=bool(lay["error"]), calls=lay["calls"],
                rows=[("생성 콜", lay["calls"]), ("HTTP", lay["hcx_status"]),
                      ("오류", lay["error"] or "—")]))

        elif key == "attachments":
            bf_, bl = lay["before_forms"], lay["before_files"]
            af, al = lay["after_forms"], lay["after_files"]
            cards.append(_card(
                key, f"{bf_}서식/{bl}파일 → {af}서식/{al}파일",
                open_=(al != bl), calls=0,
                rows=[("최종 서식", ", ".join(sorted({a['label'] or a['file']
                                                   for a in lay['final']})) or "—")],
                extra={"before": (bf_, bl), "after": (af, al), "final": lay["final"]}))

        elif key == "checks":
            n = len(lay["flags"])
            cards.append(_card(key, "통과" if lay["ok"] else f"플래그 {n}건",
                               open_=not lay["ok"], calls=0,
                               rows=[("플래그", f)for f in lay["flags"]] or
                                    [("비고", lay["skipped"] or "없음")]))

    c = trace.get("calls") or {}
    if trace.get("pending"):
        title = f"되묻기 {L['ask'].get('turn') or ''}턴 · {L['ask'].get('slot') or ''}"
        subtitle = f"생존 {L['combos']['remaining']}행 · 답변 전 (분류·검색·생성 미실행)"
    elif trace.get("rejected"):
        title = "소관 밖 — 거절"
        subtitle = f"{L['gate']['reason'] or ''} · HCX {c.get('total')}콜 · 검색·생성 생략"
    else:
        title = f"답변 · {L['bf']['bf'] or '업무 불명'}"
        subtitle = f"생존 {L['combos']['remaining']}행 · HCX {c.get('total')}콜"
    return {"title": title, "subtitle": subtitle, "calls": c, "cards": cards}


# ══════════════════════════════════════════════════════════════════════════
# streamlit 렌더 — 모델만 소비한다
# ══════════════════════════════════════════════════════════════════════════
def render(traces: list[dict]) -> None:
    """우측 패널 본체. `traces` = 대화에 쌓인 트레이스들(오래된 것부터).

    턴별로 접어두고 **최신 턴만 펼친다** — 되묻기 2턴이면 카드가 세 배로 늘어난다.
    """
    import streamlit as st

    st.subheader("🔬 트레이스")
    if not traces:
        st.caption("질의를 입력하면 층별 분기 근거가 여기에 표시됩니다.")
        return

    body = st.container(height=PANEL_HEIGHT) if _supports_height() else st.container()
    with body:
        for i, tr in enumerate(traces):
            m = panel_model(tr)
            last = i == len(traces) - 1
            with st.expander(f"{i + 1}. {m['title']}", expanded=last):
                st.caption(m["subtitle"])
                _render_calls(st, m["calls"])
                for card in m["cards"]:
                    _render_card(st, card)


def _supports_height() -> bool:
    """`st.container(height=)` 는 최신 streamlit 에만 있다. 없으면 그냥 컨테이너."""
    import inspect

    import streamlit as st
    try:
        return "height" in inspect.signature(st.container).parameters
    except (TypeError, ValueError):
        return False


def _render_calls(st, calls: dict) -> None:
    if not calls:
        return
    parts = [f"게이트 {calls.get('gate')}", f"되묻기 {calls.get('ask')}",
             f"생성 {calls.get('generate')}"]
    st.caption(f"**HCX {calls.get('total')}콜** = " + " + ".join(parts)
               + f"  ·  결정론 {len(calls.get('deterministic', []))}층 콜 0")


def _render_card(st, card: dict) -> None:
    title = f"{card['label']} · {card['headline']}   `{card['badge']}`"
    if card["status"].startswith("생략"):
        st.markdown(f"◦ {card['label']} — _{card['status']}_  `{card['badge']}`")
        return
    with st.expander(title, expanded=card["open"]):
        ex = card["extra"]
        if card["key"] in ("bf", "slots") and ex.get("query_hl"):
            st.markdown(f"> {ex['query_hl']}")
        if card["key"] == "combos":
            st.markdown("### " + "  →  ".join(f"`{n}`" for _, n in ex["trail"]))
            st.caption(" · ".join(lab for lab, _ in ex["trail"]))
        if card["key"] == "attachments":
            bcol, acol = st.columns(2)
            bcol.metric("필터 전", f"{ex['before'][0]}서식", f"{ex['before'][1]}파일",
                        delta_color="off")
            acol.metric("필터 후", f"{ex['after'][0]}서식",
                        f"{ex['after'][1] - ex['before'][1]}파일")
        for label, value in card["rows"]:
            st.markdown(f"- {label}: {value}")
        if card["key"] == "bf":
            for bf, sc, hits in ex["scores"]:
                trig = ", ".join(f"{k}×{n}(w{w})" if n > 1 else f"{k}(w{w})"
                                 for k, w, n in hits) or "—"
                st.markdown(f"- `{sc:>2}점` **{bf}** ← {trig}")
        if card["key"] == "ask" and ex.get("prompt"):
            st.info(ex["prompt"])
        if card["key"] == "search" and ex.get("docs"):
            st.dataframe(
                [{"문서": d["title"], "점수": d["score"], "업무": d["business_function"]}
                 for d in ex["docs"]], hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════
# 검증 하니스 (python3 chatbot/qform_panel.py) — T6 AC 실측 출력
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import json

    import attachments as _att
    import qform_flow
    import qform_state
    import qform_trace
    from qform_extract import extract

    rag = qform_trace.rag
    fails: list[tuple[str, str, str]] = []

    MS_DOCS = {"kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn",
               "kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn",
               "kdic-fins-ir-aplygudn-MtrsVstRcptGudn-selectScrn"}
    HITS = [json.loads(l) for l in
            (_BASE / "crawler" / "data" / "chunks.jsonl").open(encoding="utf-8")
            if json.loads(l)["parent_doc_id"] in MS_DOCS]

    def stub_answer(q, qform):
        return {"text": "착오송금 반환 신청 서류는 다음과 같습니다 [출처1]", "sources": [],
                "confidence": 0.62, "route": "rag", "checks": {"ok": True, "flags": []},
                "attachments": _att.collect(HITS, qform=qform),
                "_meta": {"cls_label": "정상", "cls_reason": "착오송금 반환지원 문의",
                          "cls_calls": 1, "cls_parse_fail": 0, "cls_latency_ms": 310,
                          "hcx_status": 200, "latency_ms": 1180, "error": None, "k": 3}}

    def conversation(ask_mode="template", llm_call=None, boost=False):
        """되묻기 2턴 대화를 돌려 트레이스 3건을 만든다 (ask · ask · answer)."""
        s, traces = qform_flow.new_state(), []
        script = ["착오송금 반환 신청하려는데 필요한 서류 알려주세요", "대리인이 신청해요", "법인이요"]
        ev = qform_flow.start(s, script[0], ask_mode=ask_mode, boost=boost,
                              classify_fn=rag.classify_query_bf, answer_fn=stub_answer,
                              llm_call=llm_call)
        calls = 0 if ev["kind"] == "ask" else 2
        traces.append(qform_trace.collect(
            s["base_q"], qform_trace.bf_debug(s["base_q"]), s["slots_raw"],
            ev.get("survivors"), ev.get("ask"), ev.get("result"), boost,
            search_q=ev.get("search_q"), hits=HITS, hcx_calls=calls, ask_turn=s["ask_turn"]))
        for rep in script[1:]:
            if ev["kind"] != "ask":
                break
            ev = qform_flow.reply(s, rep, ask_mode=ask_mode, boost=boost,
                                  answer_fn=stub_answer, llm_call=llm_call)
            calls = 0 if ev["kind"] == "ask" else 2
            traces.append(qform_trace.collect(
                s["base_q"], qform_trace.bf_debug(s["base_q"]), s["slots_raw"],
                ev.get("survivors"), ev.get("ask"), ev.get("result"), boost,
                search_q=ev.get("search_q"), hits=HITS, hcx_calls=calls,
                ask_turn=s["ask_turn"]))
        return traces

    print("우측 트레이스 패널 — 화면 모델 검증 (streamlit 불필요 · LLM 콜 0)\n")
    TR = conversation()

    # ── AC1. 층 구성이 수집기와 1:1 ────────────────────────────────────────
    print("── AC1. 패널 카드 = 수집기 층 구성 (T7 §1 다이어그램 기준) ──")
    m_last = panel_model(TR[-1])
    keys = [c["key"] for c in m_last["cards"]]
    ac1 = keys == list(LAYER_ORDER)
    print(f"  카드 {len(keys)}장 · 순서 {'LAYER_ORDER 와 일치' if ac1 else '불일치 ⛔'}")
    print(f"  {' → '.join(LAYER_LABEL[k] for k in keys)}")
    print(f"  → {'OK' if ac1 else 'DIFF ⛔'}")
    if not ac1:
        fails.append(("AC1", "LAYER_ORDER 일치", str(keys)))

    # ── AC2. 되묻기 턴에도 그 시점까지의 트레이스 ──────────────────────────
    print("\n── AC2. 되묻기 턴 트레이스 (답변 전) ──")
    kinds = ["되묻기" if t["pending"] else "답변" for t in TR]
    m0 = panel_model(TR[0])
    skipped0 = {c["key"] for c in m0["cards"] if c["status"].startswith("생략")}
    ask0 = next(c for c in m0["cards"] if c["key"] == "ask")
    comb0 = next(c for c in m0["cards"] if c["key"] == "combos")
    # 되묻기 턴에는 answer() 를 부르지 않는다 → **분류(소관 게이트)도 안 돈다.**
    # 그 뒤 층(검색·생성·첨부·검증)까지 5층이 생략이고, 앞 4층만 실제로 채워진다.
    WANT_SKIP = {"gate", "search", "generate", "attachments", "checks"}
    ac2 = (TR[0]["pending"] and ask0["open"] and comb0["headline"] == "14 → 12 → 7"
           and skipped0 == WANT_SKIP)
    print(f"  트레이스 {len(TR)}건: {' · '.join(kinds)}")
    print(f"  1턴 패널 제목: \"{m0['title']}\" · 부제 \"{m0['subtitle']}\"")
    print(f"  생존 추이 카드: {comb0['headline']} · 되묻기 카드 펼침={ask0['open']}")
    print(f"  채워진 층: {', '.join(LAYER_LABEL[k] for k in LAYER_ORDER if k not in skipped0)}")
    print(f"  생략된 층: {', '.join(LAYER_LABEL[k] for k in LAYER_ORDER if k in skipped0)}")
    print(f"  → {'OK' if ac2 else 'DIFF ⛔'}")
    if not ac2:
        fails.append(("AC2", "되묻기 턴 5층 생략", f"{sorted(skipped0)}"))

    # ── AC3. 패널 모델이 대화 렌더와 독립 ──────────────────────────────────
    print("\n── AC3. 숨김 토글 — 패널 모델이 대화와 독립 ──")
    import ast
    psrc = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    top_imports = {n.names[0].name for n in ast.walk(psrc)
                   if isinstance(n, ast.Import) and n.col_offset == 0}
    model_pure = "streamlit" not in top_imports
    asrc = pathlib.Path(_BASE / "chatbot" / "app.py").read_text(encoding="utf-8")
    guarded = "show_trace" in asrc and "qform_panel.render" in asrc
    ac3 = model_pure and guarded
    print(f"  panel_model 은 streamlit 미의존(모듈 최상단 import 없음): {model_pure}")
    print(f"  app.py 가 show_trace 토글로 render 를 감싸는가: {guarded}")
    print(f"  → {'OK' if ac3 else 'DIFF ⛔'}  (숨기면 render 자체가 안 불린다)")
    if not ac3:
        fails.append(("AC3", "토글 분기·모델 순수", f"{model_pure}/{guarded}"))

    # ── AC4. 패널이 대화를 밀어내지 않음 — 기본 펼침 억제 ──────────────────
    print("\n── AC4. 2턴 대화에서 패널 길이 억제 ──")
    print(f"  {'턴':4} {'카드':>4} {'기본 펼침':>7} {'생략':>4}  펼친 층")
    open_counts = []
    for i, t in enumerate(TR, 1):
        m = panel_model(t)
        op = [c["label"] for c in m["cards"] if c["open"]]
        sk = [c for c in m["cards"] if c["status"].startswith("생략")]
        open_counts.append(len(op))
        print(f"  {i:<4} {len(m['cards']):>4} {len(op):>7} {len(sk):>4}  {', '.join(op)}")
    ac4 = all(n <= 5 for n in open_counts) and PANEL_HEIGHT > 0
    print(f"  기본 펼침 최대 {max(open_counts)}층 / 9층 · 최신 턴만 expander 펼침 · "
          f"패널 고정 높이 {PANEL_HEIGHT}px 스크롤 격리")
    print(f"  → {'OK' if ac4 else 'DIFF ⛔'}")
    if not ac4:
        fails.append(("AC4", "기본 펼침 ≤5층", f"최대 {max(open_counts)}층"))

    # ── AC5. ⓐ/ⓑ 모드 차이가 패널에서 식별 가능 ────────────────────────────
    print("\n── AC5. ⓐ/ⓑ 모드 식별 (문구 + 콜수) ──")
    LLM_TEXT = "법인, 비법인단체, 미성년자 중 어느 쪽을 대리해 신청하시나요?"
    TR_B = conversation("llm", llm_call=lambda m: (LLM_TEXT, {"error": None, "calls": 1}))
    TR_F = conversation("llm", llm_call=lambda m: ("아무 말이나 합니다", {"error": None, "calls": 1}))
    rows = []
    for tag, tt in (("ⓐ 템플릿", TR), ("ⓑ LLM", TR_B), ("ⓑ→폴백", TR_F)):
        c = next(x for x in panel_model(tt[1])["cards"] if x["key"] == "ask")
        d = dict(c["rows"])
        rows.append((tag, d.get("문구 모드"), d.get("되묻기 콜"), d.get("⚠ 폴백 사유", "—"),
                     c["extra"]["prompt"]))
    print(f"  {'요청':8} {'패널 표기':10} {'콜':>3} {'폴백':22} 문구")
    for tag, mode, calls, fb, prompt in rows:
        print(f"  {tag:8} {mode:10} {calls:>3} {str(fb)[:22]:22} {prompt[:34]}…")
    ac5 = (rows[0][1] == "ⓐ 템플릿" and rows[0][2] == 0
           and rows[1][1] == "ⓑ LLM" and rows[1][2] == 1 and rows[1][4] == LLM_TEXT
           and rows[2][3] != "—" and rows[2][4] == rows[0][4])
    print(f"  폴백 시 문구가 ⓐ 와 동일한가: {rows[2][4] == rows[0][4]} (위반 문구 미노출)")
    print(f"  → {'OK' if ac5 else 'DIFF ⛔'}")
    if not ac5:
        fails.append(("AC5", "ⓐ/ⓑ 문구·콜수 구별", str(rows)))

    # ── 시각 요소 ──────────────────────────────────────────────────────────
    print("\n── 시각 요소 ──")
    mS = next(c for c in m_last["cards"] if c["key"] == "slots")
    mC = next(c for c in m_last["cards"] if c["key"] == "combos")
    mA = next(c for c in m_last["cards"] if c["key"] == "attachments")
    print(f"  트리거 하이라이트  {mS['extra']['query_hl']}")
    print(f"  생존 행 추이      {mC['headline']}   ({', '.join(l for l, _ in mC['extra']['trail'])})")
    print(f"  첨부 대비         {mA['headline']}")
    hl_ok = "**" in mS["extra"]["query_hl"]
    print(f"  하이라이트 적용: {hl_ok}")
    if not hl_ok:
        fails.append(("시각", "트리거 하이라이트", "미적용"))

    # ── reject 경로 패널 ───────────────────────────────────────────────────
    print("\n── reject 경로 패널 ──")
    QR = "미국 은행에 넣은 예금도 보호되나요?"
    rej = qform_trace.collect(
        QR, qform_trace.bf_debug(QR), extract(QR, business_function=rag.classify_query_bf(QR)),
        None, None,
        {"text": "죄송합니다…", "sources": [], "confidence": 0.0, "route": "reject",
         "checks": {"ok": True, "flags": [], "skipped": "고정 거절 문구"}, "attachments": [],
         "_meta": {"cls_label": "소관밖", "cls_reason": "외국 소재 금융기관 예금",
                   "cls_calls": 1, "cls_parse_fail": 0, "cls_latency_ms": 290,
                   "latency_ms": 290, "k": 3}},
        False, hits=[], hcx_calls=1)
    mr = panel_model(rej)
    print(f"  제목 \"{mr['title']}\" · 부제 \"{mr['subtitle']}\"")
    for c in mr["cards"]:
        mark = "생략" if c["status"].startswith("생략") else ("펼침" if c["open"] else "접힘")
        print(f"    {c['label']:12} [{mark}] {c['headline'][:44]}")

    print()
    if fails:
        print("어긋난 AC ⛔")
        print(f"  {'AC':6} {'기대':24} 실측")
        for ac, want, got in fails:
            print(f"  {ac:6} {want:24} {got}")
        sys.exit(1)
    print("전체 통과 ✅  (패널 모델 검증 — streamlit 렌더는 실환경 확인 필요)")
    sys.exit(0)
