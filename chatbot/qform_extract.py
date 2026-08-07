# -*- coding: utf-8 -*-
"""큐폼 결정론 슬롯 추출기 — T2.

자연어 질의 → 착오송금 슬롯(party/sub_task/qualification/subject/method).
**LLM 호출 0.** 순수 키워드 매핑. 못 잡으면 해당 키를 None으로 둔다.

설계 원칙 (기획서 §7 / task_assignment T2):
- **추출 실패(None)는 정상이고, 오추출은 해롭다.** 오추출은 정답 조합을 사용자가
  보기도 전에 지운다(하드필터 실패의 반복). 그래서 애매하면 None으로 둔다 — 정밀도 우선.
- `sub_task` 우선. 값별 어휘가 좁고 뚜렷하다. 특히 4개 숨은 분기
  (신청철회·매입계약해제·수령계좌변경·대리인변경)는 어휘가 배타적이라 고정밀.
- 값 표기는 조합 테이블/유상 태깅과 **정확히 일치**해야 조인된다.
- `business_function`은 MOAI 라우터가 프리필한다. None이면 classify_query_bf() 폴백(결정론).
  이번 스프린트는 착오송금 전용 — 타 업무로 분류되면 슬롯을 채우지 않는다(스코프 게이트).

반환:
    {"party":…, "sub_task":…, "qualification":…, "subject":…, "method":…,
     "_hits": {슬롯: [트리거…]}, "_bf": 판정된 업무, "_scope": "in"|"out"}
"""
from __future__ import annotations

IN_SCOPE_BF = "착오송금 반환 신청"

# ── 조합 테이블 허용값 (출력 자기검증용. '공통'은 테이블 와일드카드라 추출 안 함) ──
ALLOWED = {
    "party": {"송금인", "수취인"},
    "sub_task": {"제도안내", "반환신청", "신청철회", "매입계약해제",
                 "수령계좌변경", "대리인변경", "이의제기", "이체수수료환급"},
    "qualification": {"본인", "대리인"},
    "subject": {"본인", "대리인", "미성년자", "군복무자",
                "국외거주 또는 유학생", "법인", "비법인단체"},
    "method": {"온라인", "방문", "우편", "이메일", "팩스"},
}


def _nsp(s: str) -> str:
    """공백 제거 정규화 (rag.classify_query_bf 와 동일 관행: '보호 한도'='보호한도')."""
    return (s or "").replace(" ", "")


def _hits_any(qn: str, keywords) -> list[str]:
    """공백 제거 질의에 등장하는 키워드 목록(공백 제거 비교)."""
    return [k for k in keywords if _nsp(k) in qn]


# ── sub_task 규칙 (순서 = 우선순위, 첫 매칭 승). specific → fuzzy ─────────────
# kind:
#   "any": 키워드 중 하나라도 등장하면 발동
#   "and": (A리스트, B리스트) — A 하나 & B 하나 모두 등장해야 발동
_SUBTASK_RULES = [
    # 4개 숨은 분기 (배타적 어휘, 고정밀). 대리인변경을 계좌변경보다 먼저.
    ("대리인변경", "and", (["대리인", "위임"], ["변경", "바꾸", "교체", "해지", "바뀌"])),
    ("수령계좌변경", "any", ["수령계좌"]),
    ("수령계좌변경", "and", (["계좌", "입금", "받을 계좌", "환급 계좌"], ["변경", "바꾸", "바뀌"])),
    ("신청철회", "any", ["철회", "신청 취소", "접수 취소", "취소하", "취소할", "취소하려", "취소하고"]),
    ("매입계약해제", "any", ["매입계약", "매입 계약", "계약 해제", "계약해제"]),
    # 수취인 2분기 (좁은 어휘)
    ("이의제기", "any", ["이의"]),
    ("이체수수료환급", "any", ["이체수수료", "이체 수수료"]),
    ("이체수수료환급", "and", (["수수료"], ["환급", "돌려", "환불"])),
    ("이체수수료환급", "any", ["환급"]),  # 착오송금 게이트 안에서 환급=수수료환급
    # 반환신청 = 구비서류 intent OR 신청방법(채널+행위) intent
    ("반환신청", "any", ["서류", "구비", "준비물", "챙기", "챙겨", "제출", "들고", "가지고",
                     "가져", "필요한 게", "필요한가", "뭐 필요", "뭐가 필요", "인증서"]),
    ("반환신청", "and", (["온라인", "인터넷", "홈페이지", "방문", "찾아가", "창구", "우편", "팩스", "이메일"],
                     ["신청", "접수", "제출", "방법", "어떻게", "하려면", "하면 되", "하면 돼"])),
    # 제도안내 = 정보 요구 (fallback)
    ("제도안내", "any", ["제도", "뭔가요", "뭐예요", "뭐에요", "무엇", "란 게", "어떤 경우", "어떤경우",
                     "대상", "자격", "얼마", "언제까지", "기한", "제외", "유의", "주의",
                     "되나요", "되나", "되는", "가능한", "가능해", "돌려받을 수", "받을 수 있",
                     "신청할 수 있", "절차", "단계", "과정", "먼저", "어떡", "어떻게 해"]),
]

# ── party 방향 어휘 (sub_task 로 결정 안 될 때 폴백) ──────────────────────────
_PARTY_RULES = [
    ("수취인", ["받은", "들어온", "잘못 들어", "수취인", "받아버린", "돌려달", "반환 요구", "반환요구"]),
    ("송금인", ["보낸", "송금한", "이체한", "내가 보", "잘못 보", "잘못 송금", "잘못 이체",
              "송금인", "보낸 사람", "송금한 사람"]),
]
# sub_task → party (정의상 확정). 제도안내는 양쪽이라 None.
_SUBTASK_PARTY = {
    "이의제기": "수취인", "이체수수료환급": "수취인",
    "반환신청": "송금인", "신청철회": "송금인", "매입계약해제": "송금인",
    "수령계좌변경": "송금인", "대리인변경": "송금인",
}

# ── subject(주체) 전용 엔티티. 비법인단체를 법인보다 먼저(동호회 오분류 방지) ────
_SUBJECT_RULES = [
    ("미성년자", ["미성년", "자녀", "친권"]),
    ("군복무자", ["군인", "군복무", "군대", "복무 중", "군 복무", "군대 간"]),
    ("비법인단체", ["비법인", "동호회", "단체", "모임", "계모임"]),
    ("법인", ["법인", "회사", "사업자"]),
    ("국외거주 또는 유학생", ["해외", "국외", "외국", "유학", "재외"]),
]

# ── qualification 어휘 ──────────────────────────────────────────────────────
_AGENT_KW = ["대리", "대신", "위임", "맡겨", "보호자", "부모", "친권자"]
_SELF_KW = ["본인", "제가", "내가", "나 혼자", "직접 신청", "직접 접수"]

# ── method(채널). 다중 허용(';'). 표기순 = 온라인/방문/우편/이메일/팩스 ──────────
_METHOD_ORDER = ["온라인", "방문", "우편", "이메일", "팩스"]
_METHOD_RULES = {
    "온라인": ["온라인", "인터넷", "홈페이지", "웹사이트", "비대면", "모바일"],
    "방문": ["방문", "찾아가", "창구", "직접 가", "들고 가", "가져가", "내방", "방문해"],
    "우편": ["우편", "등기"],
    "이메일": ["이메일", "메일"],
    "팩스": ["팩스"],
}


def extract(query: str, business_function: str | None = None) -> dict:
    """자연어 → 슬롯 dict. LLM 호출 0. 못 잡으면 해당 키 None."""
    hits: dict[str, list[str]] = {}
    out = {"party": None, "sub_task": None, "qualification": None,
           "subject": None, "method": None, "_hits": hits}

    # 0) 업무 스코프 게이트 — 착오송금이 아니면 슬롯 채우지 않음
    bf = business_function
    if bf is None:
        try:
            from crawler.rag import classify_query_bf  # 결정론 폴백 (지연 임포트)
            bf = classify_query_bf(query)
        except Exception:
            bf = None
    out["_bf"] = bf
    if bf is not None and bf != IN_SCOPE_BF:
        out["_scope"] = "out"
        return out
    out["_scope"] = "in"

    qn = _nsp(query)

    # 1) sub_task (우선). 순서대로 첫 매칭.
    for label, kind, spec in _SUBTASK_RULES:
        if kind == "any":
            m = _hits_any(qn, spec)
            fired = bool(m)
        else:  # "and"
            a, b = spec
            ma, mb = _hits_any(qn, a), _hits_any(qn, b)
            m = ma + mb
            fired = bool(ma) and bool(mb)
        if fired:
            out["sub_task"] = label
            hits["sub_task"] = m
            break

    # 2) subject (엔티티). 첫 매칭.
    for label, kws in _SUBJECT_RULES:
        m = _hits_any(qn, kws)
        if m:
            out["subject"] = label
            hits["subject"] = m
            break

    # 3) qualification. 명시 어휘 우선, 없으면 subject/entity 로 유도.
    agent = _hits_any(qn, _AGENT_KW)
    self_ = _hits_any(qn, _SELF_KW)
    ent_subject = out["subject"] in {"미성년자", "군복무자", "법인", "비법인단체", "국외거주 또는 유학생"}
    if agent or ent_subject:
        out["qualification"] = "대리인"
        hits["qualification"] = agent or [f"⟵subject:{out['subject']}"]
    elif self_:
        out["qualification"] = "본인"
        hits["qualification"] = self_

    # subject 가 엔티티가 아니면 qualification 으로 채움(본인/대리인)
    if out["subject"] is None and out["qualification"] in {"본인", "대리인"}:
        out["subject"] = out["qualification"]
        hits.setdefault("subject", [f"⟵qualification:{out['qualification']}"])

    # 4) party. sub_task 정의상 확정 → 없으면 방향 어휘.
    if out["sub_task"] in _SUBTASK_PARTY:
        out["party"] = _SUBTASK_PARTY[out["sub_task"]]
        hits["party"] = [f"⟵sub_task:{out['sub_task']}"]
    else:
        for label, kws in _PARTY_RULES:
            m = _hits_any(qn, kws)
            if m:
                out["party"] = label
                hits["party"] = m
                break

    # 5) method. 다중 허용.
    chans = [c for c in _METHOD_ORDER if _hits_any(qn, _METHOD_RULES[c])]
    if chans:
        out["method"] = ";".join(chans)
        hits["method"] = [k for c in chans for k in _hits_any(qn, _METHOD_RULES[c])]

    return out


def validate_values(slots: dict) -> list[tuple[str, str]]:
    """추출 슬롯의 모든 값이 조합 테이블 허용값 안인지 검사. 위반 [(슬롯,값)] 반환."""
    bad = []
    for slot, allowed in ALLOWED.items():
        v = slots.get(slot)
        if v is None:
            continue
        for tok in str(v).split(";"):
            if tok and tok not in allowed:
                bad.append((slot, tok))
    return bad


# ══════════════════════════════════════════════════════════════════════════
# 검증 하니스 (python3 chatbot/qform_extract.py) — AC 실측 출력
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import json
    import pathlib

    BASE = pathlib.Path(__file__).resolve().parent.parent  # repo root
    TESTSET = BASE / "crawler" / "data" / "testset_natural_450.jsonl"

    rows = [json.loads(l) for l in TESTSET.open(encoding="utf-8")]
    ms = [r for r in rows if r["business_function"] == IN_SCOPE_BF]
    other = [r for r in rows if r["business_function"] != IN_SCOPE_BF]

    SLOTS = ["party", "sub_task", "qualification", "subject", "method"]

    def cover(subset):
        c = {s: 0 for s in SLOTS}
        for r in subset:
            sl = extract(r["question"], r["business_function"])
            for s in SLOTS:
                if sl[s] is not None:
                    c[s] += 1
        return c

    print("── AC: 결정론 슬롯 추출률 (450셋, business_function 프리필) ──")
    cm, co = cover(ms), cover(other)
    print(f"  {'slot':14} {'착오송금84':>12} {'기타366(게이트)':>16} {'전체450':>10}")
    for s in SLOTS:
        print(f"  {s:14} {cm[s]:>5}/{len(ms)} {cm[s]/len(ms)*100:>4.0f}% "
              f"{co[s]:>7}/{len(other)} {co[s]/len(other)*100:>3.0f}% "
              f"{(cm[s]+co[s])/len(rows)*100:>7.0f}%")
    print("  (기타366은 스코프 게이트로 전부 None 이 정상 — 오추출 억제 지표)")

    # ── 수기 20문항 sub_task 정확도 ─────────────────────────────────────────
    CASES = [
        ("착오송금 반환 지원 제도가 뭔가요?", "제도안내"),
        ("잘못 보낸 돈, 돌려받을 수 있는 대상이 어떻게 되나요?", "제도안내"),
        ("착오송금 언제까지 신청할 수 있어요?", "제도안내"),
        ("착오송금 반환 신청할 때 구비서류가 뭐예요?", "반환신청"),
        ("잘못 송금한 돈 온라인으로 접수하는 방법 알려줘", "반환신청"),
        ("법인이 잘못 이체했을 때 반환 신청 서류는?", "반환신청"),
        ("미성년자 착오송금 반환 신청 서류 알려줘", "반환신청"),
        ("대리인이 방문해서 착오송금 반환 신청할 때 서류는?", "반환신청"),
        ("잘못 들어온 돈 돌려달라는데 이의제기하려면?", "이의제기"),
        ("착오송금 반환 요구에 이의 신청하는 서류는?", "이의제기"),
        ("이체수수료 환급 신청은 어떻게 해요?", "이체수수료환급"),
        ("착오송금 반환하면서 낸 수수료도 돌려받을 수 있어요?", "이체수수료환급"),
        ("착오송금 반환 신청을 철회하고 싶어요", "신청철회"),
        ("접수한 착오송금 신청을 취소하려면 어떻게 하죠?", "신청철회"),
        ("부당이득반환채권 매입계약을 해제하고 싶은데 서류가 뭐죠?", "매입계약해제"),
        ("매입계약 해제 신청은 어떻게 하나요?", "매입계약해제"),
        ("반환금 받을 수령계좌를 변경하려면?", "수령계좌변경"),
        ("착오송금 반환금 입금 계좌를 바꾸고 싶어요", "수령계좌변경"),
        ("착오송금 반환 신청 대리인을 변경하려면 뭐가 필요해요?", "대리인변경"),
        ("위임했던 대리인을 다른 사람으로 바꾸고 싶어요", "대리인변경"),
    ]
    print("\n── AC: 수기 20문항 sub_task 정확도 (오추출/미추출 구분) ──")
    ok = mis = wrong = 0
    for q, gold in CASES:
        pred = extract(q, IN_SCOPE_BF)["sub_task"]
        if pred == gold:
            verdict, ok = "정답", ok + 1
        elif pred is None:
            verdict, mis = "미추출", mis + 1
        else:
            verdict, wrong = f"오추출→{pred}", wrong + 1
        mark = "✅" if pred == gold else ("·" if pred is None else "✗")
        print(f"  {mark} [{gold:8}] {q[:34]:34} → {str(pred):8} {verdict}")
    print(f"  정답 {ok}/20 ({ok/20*100:.0f}%) · 오추출 {wrong} · 미추출 {mis}")

    # ── 허용값 검사 (450 + 20) ─────────────────────────────────────────────
    print("\n── AC: 추출 값 조합 테이블 허용값 준수 ──")
    viol = 0
    for r in rows:
        for bad in validate_values(extract(r["question"], r["business_function"])):
            viol += 1
            print(f"  ✗ 450 위반 {bad} @ {r['question'][:30]}")
    for q, _ in CASES:
        for bad in validate_values(extract(q, IN_SCOPE_BF)):
            viol += 1
            print(f"  ✗ 20 위반 {bad} @ {q[:30]}")
    print(f"  허용값 위반: {viol}건 (기대 0)  {'OK' if viol == 0 else 'DIFF'}")

    print("\n(LLM 호출 0 — 순수 키워드 매핑. 외부 네트워크·모델 호출 없음)")
