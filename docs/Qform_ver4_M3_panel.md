# Qform_ver4 · M3 — 메모리 패널

> **브랜치** `Qform_ver4` · **실행** 2026-08-18 · **선행** M0·M1·M2·M2-b
> **명세** `docs/Qform_ver4_task_assignment.md` M3 절 · **설계 추기** `QFORM_ARCH_설계스펙.md` §24(rev.8)
> **실행자** CC

---

## §0. 잠금 정보

| 항목 | 값 |
|---|---|
| HEAD SHA | `d2a7c2053765a00e89b9c6722e6bbc12da3d49d6` |
| `chunks.jsonl` | `6af9517ba0da80db1296b9c7f202b534ae23cd17d8e7746614f7d89d869bd381` |
| **`chatbot/qform_memory_panel.py`** (신규) | `edc52741e2ce7563` · 324줄 |
| **`chatbot/verify_qform_panel.py`** (신규) | `e803bbde4ba23307` · 215줄 |
| `chatbot/qform_flow.py` | `dd4a7839f081ef6d` · 469줄 |
| `chatbot/qform_config.py` | `eb83e6d544c60ea7` · 181줄 |
| `chatbot/app.py` | `b034536a1d9bd3f9` · 626줄 |
| `chatbot/verify_qform_multiturn.py` | `c48b0e428abef8a0` · 386줄 |
| 측정 환경 | Python 3.11.9 · 네트워크·LLM 콜 0 |

### 0-1. 동결 무변동 (A3-11·A3-12·A3-13)

| 파일 | sha256(앞16) | AC |
|---|---|---|
| `chatbot/verify_qform_e2e.py` | `3a9472ca2e4a5f85` | **A3-11 diff 0줄** |
| `crawler/rag.py` | `84247b7c0aa6b6ad` | **A3-12 diff 0줄** |
| `chatbot/chain.py` | `a37b2a77eed5a5bf` | **A3-12 diff 0줄** |
| `chatbot/qform_panel.py` | `34d5f43597d90bac` | **A3-13 diff 0줄** |
| `crawler/eval.py` · `qform_combos_msdr.csv` · `chunks.jsonl` · `doc_attachments.json` | 무변동 | — |

M2 작업 전 스냅샷과 **8건 전건 동일**하다.

---

## §1. 구조 — 렌더를 얇게 유지한 방법

Streamlit 렌더는 눈으로만 확인되므로 **상태 전이·화면 모델을 UI 없이 호출 가능한 순수 함수로 갈랐다.**

| 층 | 파일 | 책임 |
|---|---|---|
| 화면 모델 | `qform_memory_panel.panel_model()` | 3구역 · 항목 · 상태 · `effect` · `actionable`. **순수 함수, 상태 미변경** |
| 조작 | `qform_memory_panel.apply()` | `edit`/`clear`/`pass`/`move`/`drop` 단일 진입점. **`answer()` 미호출** |
| 전이 | `qform_flow.edit()` · `pass_slot()` | 슬롯·`asked`·`ask_turn` |
| 렌더 | `app.py render_memory_panel()` | 모델을 그리고 클릭을 `(op, kwargs)` 로 돌려줄 뿐 |
| 검증 | `chatbot/verify_qform_panel.py` (신규) | A3-1~A3-9 를 UI 없이 실측 |

**`chatbot/qform_panel.py` 에 얹지 않았다** — 그 파일은 T6 트레이스 패널이고 동결이다(M0 판정 3).

---

## §2. 패널이 보여주는 것 — "고치면 무엇이 바뀌는가" (필수 표)

패널이 값을 보여주는데 실제로는 안 먹는 상태가 최악이다. 전 항목에 `effect` 를 달고,
바뀌는 게 없으면 `actionable=False` 로 내려 **회색 처리**한다.

| 구역 | 항목 | 고치면 바뀌는 것 | 정말 바뀌나 |
|---|---|---|---|
| 적용 중 | 역할(`party`) | 첨부 후단 필터 · 되묻기 판정 | ○ |
| 적용 중 | 세부 용건(`sub_task`) | 첨부 후단 필터 · 되묻기 판정 | ○ |
| 적용 중 | 자격(`qualification`) | 첨부 후단 필터 · 되묻기 판정 | ○ |
| 적용 중 | 주체(`subject`) | 첨부 후단 필터 · 되묻기 판정 | ○ |
| 적용 중 | 신청 수단(`method`) | 첨부 후단 필터 · 되묻기 판정 | ○ |
| 적용 중 | (만료된 슬롯) | **없음 — 이 턴에는 안 쓰인다** | **× 회색 잔류** |
| 기억만 함 | 업무(`bf`) | 이월 허용 여부만 (검색·생성 불개입) | ○ (이월에만) |
| 기억만 함 | **직전 참조 문서** | **없음 — 표시 전용** | **× 회색** |
| 대기 중인 용건 | 대기 의도 | 처리 순서 · 큐 제외 | ○ |

`직전 참조 문서` 는 소비처가 A(표시 전용)라 아무것도 안 바꾼다. **빼지 않고 회색으로 남긴 이유** —
"시스템이 무엇을 들고 있는지"를 보이는 것 자체가 패널의 목적이고, 안 바뀐다는 사실을 같이 적으면
화면이 거짓말하지 않는다.

### 2-1. 업무별 노출 축 (M2 판정 1 연장)

| 업무 | 노출 축 |
|---|---|
| 착오송금 반환 신청 | `party` · `sub_task` · `qualification` · `subject` · `method` (5) |
| **예금보험금 안내** | `sub_task` · `qualification` · `subject` · `method` (**4 — `party` 미노출**) |
| 업무 불명 | 5축 전부 (숨기는 쪽이 더 위험하다) |

---

## §3. 검증 결과

### 3-1. `verify_qform_panel.py` (신규) — 11/11 통과 ✅ · 지문 `12619f9c100feb6e`

| AC | 기준 | 실측 | 판정 |
|---|---|---|---|
| A3-1 | 3구역 · 라벨이 명세 문구와 일치 | `['적용 중', '기억만 함', '대기 중인 용건']` | ✅ |
| A3-1b | 전 항목에 `effect` 표기 | 7개 항목 · 누락 **0건** | ✅ |
| A3-2 | X 후 재발동 0 · `asked` 무변동 · `ask_turn` 무변동 · `answer()` 0회 | `ready` · `pending=None` · asked 동일 · 턴 2→2 · **answer() 0회** | ✅ |
| A3-3 | pass 사용 시 재질문 0 | `pass(qualification)` → 다음 질문 `None` · answer() 0회 | ✅ |
| A3-4 | TTL=3 이월 3턴 생존 · 만료 회색 잔류(삭제 0) | origin `[이월,이월,이월,미채움]` · 패널 `subject=법인(만료)` **잔류** | ✅ |
| A3-5 | 업무 전환 시 표기 · 오이월 0 | bf=예금보험금 안내 · 노출축 4개 · `party` 미노출 · **오이월 0건** | ✅ |
| A3-6 | 다중 의도 큐 적재 · `answer()` 1회 · 4필드 무변경 | 큐 1건(`이의제기`) · **answer() 1회** · 4필드 유지 | ✅ |
| A3-6b | 큐 ✏️순서변경 · ❌제외 | `[이의제기,신청철회]` → move → drop | ✅ |
| A3-7 | 교차 감지 · 문구에 `나눠서 안내드릴게요` | `kind=cross` · bfs 2개 · **문구 포함** | ✅ |
| A3-8 | `[이대로 답변받기]` 즉시 답변 · 재발동 없음 | ask→answer · answer() 1회 · `pending=None` | ✅ |
| A3-9 | 버튼 값 ⊆ 조합 테이블 | MSDR+DPIN 전 슬롯 · **테이블 밖 0건** | ✅ |

### 3-2. 기존 하니스 — 회귀 0

| 스크립트 | M2-b 실측 | **M3 실측** | 판정 |
|---|---|---|---|
| `verify_combos.py` | 14행·38 / DPIN 9행·11 | 동일 | 무변동 |
| `verify_terms.py` | 통과 ✅ | 통과 ✅ | 무변동 |
| `qform_extract.py` | 20/20 | 20/20 | 무변동 |
| **`qform_state.py`** | **9건 / 450 = 2.0%** | **9건 / 450 = 2.0%** | **무변동** |
| `qform_config.py` | 통과 ✅ | 통과 ✅ (TTL=3·패널 2종 반영) | 갱신 |
| **`verify_qform_multiturn.py`** | 24/24 · `e6d0fe7ff4540b89` | **24/24** · **`246d07124d333c9b`** | **개정분만 변경** |
| **`verify_qform_e2e.py`** | 통과 ✅ | 통과 ✅ · **diff 0줄** | **무변동** |
| `verify_qform_integration.py` | 통과 ✅ | 통과 ✅ | 무변동 |
| `verify_docs.py` | 통과 ✅ | 통과 ✅ | 무변동 |
| **`verify_qform_panel.py`** (신규) | — | **11/11 ✅** | 신규 |

**10종 전부 exit 0.**

### 3-3. 멀티턴 지문 변경 — 바뀐 이유가 개정 3건 + E5 외에 없음

지문 = `sid|AC|기대|실측|통과` **24행의 sha256**. 24행 중 바뀐 행은 아래 4개뿐이고 나머지 **20행은 바이트 동일**이다.

| 행 | 개정 전 | 개정 후 |
|---|---|---|
| **C6** | `TTL=2 후 만료` / `신규 → 이월 → 이월 → 미채움` | `TTL=3 후 만료` / `신규 → 이월 → 이월 → 이월 → 미채움` |
| **E1** | `해제→되묻기 재발동` / `subject 법인→None · ask(subject)` | `해제→침묵 (재질문 0)` / `… ready · pending=None · answer() 0회` |
| **E2** | `asked 정리 · 상한서 재질문` | `asked·턴 보존 · 되살아남은 다음 질의로 이관` |
| **E5** | `해제 후 선택지 복구` / `6개 · 법인 포함=True` | `해제 후 선택지 복구 (생존값 기준)` / `options=0개(침묵) · 생존 6개` |

무변동 20행: R1·R2·R3 · C1·C2·C3·C4·C5·C7 · D1~D8 · E3·E4 · 콜회계.

---

## §4. 다중 의도 감지 — 오발동 실측

| 판정 | 조건 | 450셋 | 비율 |
|---|---|---:|---:|
| `parallel` | 절 2개 이상 **그리고** 절별 `sub_task` 2종 이상 | **1건** | 0.2% |
| `cross` | `rag.BF_QUERY_KEYWORDS` 동시 득점 2업무 이상 (문턱 `QBF_MIN_SCORE=3`) | **2건** | 0.4% |
| `single` | 그 외 | 447건 | 99.3% |

감지된 parallel 1건 — `이체수수료 환급 신청, 인터넷으로 하는 방법이 있나요?` (`이체수수료환급` + `반환신청`).

**미발동 사례를 숨기지 않는다** — 논의정리 §11-1이 복합형 예시로 든
`착오송금 신청했는데 그 은행이 파산하면 내 돈은?` 은 **`single` 로 판정된다.**
`파산` 만으로는 예금자보호제도가 문턱(3점)에 못 미친다. 문턱을 낮추면 잡히지만
오발동이 같이 늘어 **낮추지 않았다**(오발동 > 미발동, 규칙6). → `crawler/HOLES.md` H34.

---

## §5. 보고 (CLAUDE.md §7 형식)

## M3 완료

### 실측

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| A3-1 | 3구역 렌더 · 라벨 일치 | 일치 | ✅ |
| A3-2 | X 후 재발동 0 · asked·턴 무변동 · answer() 0회 | 전건 충족 | ✅ |
| A3-3 | pass 후 재질문 0 | 0 | ✅ |
| A3-4 | TTL=3 이월 3턴 · 만료 회색 잔류 | 충족 · 삭제 0 | ✅ |
| A3-5 | 업무 전환 표기 · 오이월 0 | 충족 · 0건 | ✅ |
| A3-6 | 큐 적재 · answer() 1회 · 4필드 무변경 | 충족 | ✅ |
| A3-7 | 교차 되묻기 · `나눠서 안내드릴게요` | 충족 | ✅ |
| A3-8 | 즉시 답변 · 재발동 없음 | 충족 | ✅ |
| A3-9 | 버튼 값 ⊆ 조합 테이블 | 밖 0건 | ✅ |
| A3-10 | `verify_qform_multiturn.py` 전체 통과 | **24/24** | ✅ |
| A3-11 | `verify_qform_e2e.py` diff 0줄 · 통과 | 해시 동일 · 통과 | ✅ |
| A3-12 | `rag.py` · `chain.py` diff 0줄 | 해시 동일 | ✅ |
| A3-13 | `qform_panel.py` diff 0줄 | 해시 동일 | ✅ |
| 회귀 | 450셋 발동률 | **9건 / 2.0% 무변동** | ✅ |
| git | 실행 0회 | **0회** | ✅ |

### 명세와 다르게 간 것

| # | 명세 | 실제 | 이유 |
|---:|---|---|---|
| 1 | 하니스 개정 범위 = **E1·E2·C6** | **E5 도 개정** | X 가 침묵하면서 `pending_slot` 이 없어져 `options()` 가 빈 리스트가 정상이 됐다. 개정하지 않으면 E5 가 **실패**한다. 성질("해제한 값을 다시 고를 수 있다")은 `qform_ask.survivor_values()`(렌더가 읽는 원천)로 보존. **규칙 11 범위 밖이라 사후 승인 대상** |
| 2 | 산출물 목록에 검증 하니스 없음 | **`chatbot/verify_qform_panel.py` 신규** | A3-1~A3-9 는 렌더 층에 있어 기존 하니스로 못 잰다. 규칙 11이 `verify_qform_multiturn.py` 개정을 E1·E2·C6 으로 묶었으므로 **새 파일이 유일한 경로** |
| 3 | 다중 의도 "**발화 순서대로** 1번째 처리, 2번째 큐" | **`extract()` 가 고른 것을 처리하고 나머지를 큐에 넣는다** | `extract()` 는 규칙 순서로 단일 선택한다. 발화 순서로 바꾸려면 `qform_extract` 를 고쳐야 하고 그건 450셋 회귀 트리거다. 큐 적재는 명세대로 |
| 4 | (명세에 없음) | `state["expired"]` 신설 | "만료 항목 회색 잔류"를 하려면 만료된 **마지막 값**을 어딘가 들고 있어야 한다. `slot_turn` 은 만료 시 지워진다 |
| 5 | M1 판정 3 "버튼 라벨=term · 캡션=one_line" | **배선만 하고 발동 0건** | 조합 테이블 슬롯 값(본인·대리인·법인…)과 용어 사전 term(예금보험금·가지급금…)의 **교집합이 0**이다. D 되묻기를 구현하지 않기로 했으므로(M1 판정 1) 물릴 자리가 없다. `app.term_caption()` 에 배선만 남기고 재측정 대상으로 기록 |

### [판정 필요]

| # | 항목 | 선택지 | 근거 |
|---:|---|---|---|
| 1 | **E5 개정 사후 승인** | (A) 승인 (B) 되돌리고 E5 실패 허용 (C) 다른 판정식 | 개정 안 하면 24/24 가 **23/24** 로 떨어진다. 성질은 보존했고 판정 원천을 `options()` → `survivor_values()` 로 옮겼을 뿐 |
| 2 | **`verify_qform_panel.py` 를 §5 상시 목록에 넣을지** | (A) 넣는다(8종→10종) (B) M3 전용으로 둔다 | 현재 CLAUDE.md §5 목록은 7종. 실제 상시 검증 자산은 **10종**이 됐다 |
| 3 | **교차 감지 문턱** | (A) `QBF_MIN_SCORE=3` 승계(현행) (B) 낮춰 회수율 ↑ | 논의정리 예시 문장이 (A)에서 **미발동**. 낮추면 잡히지만 450셋 오발동이 는다. 현재 cross 2건(0.4%) |

### 커밋 대상

```
git add chatbot/qform_memory_panel.py
git add chatbot/verify_qform_panel.py
git add chatbot/qform_flow.py
git add chatbot/qform_config.py
git add chatbot/app.py
git add chatbot/verify_qform_multiturn.py
git add DECISIONS.md
git add crawler/HOLES.md
git add docs/QFORM_ARCH_설계스펙.md
git add docs/Qform_ver4_M3_panel.md

git commit -m "feat(qform): M3 메모리 패널 3구역 + X/pass 역할 분리 + TTL=3 + 다중의도 큐

- qform_memory_panel.py 신규: panel_model/apply 순수 함수, 렌더는 app.py 가 얇게
- X = 오염 차단(침묵, asked/ask_turn 무변동), pass = 재질문 차단(asked 기록)
- CARRYOVER_TTL 2->3, 만료 항목 회색 잔류(state.expired)
- 다중의도 분할 후 순차 큐, 교차는 rag.BF_QUERY_KEYWORDS 동시득점으로 판정
- SPEC 에 MAX_QUEUE / PANEL_EXPIRED 신설
- verify_qform_panel.py 신규 11/11, multiturn 24/24 (C6/E1/E2/E5 개정)
- verify_qform_e2e.py / rag.py / chain.py / qform_panel.py diff 0줄
- 450셋 발동률 9건 2.0% 무변동"
```

**M4 로 넘어가지 않는다.** 보고 후 대기 (CLAUDE.md §0-2).
