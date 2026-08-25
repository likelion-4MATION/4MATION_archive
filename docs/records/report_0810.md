<!-- 상태:records -->
> **기록** — 2026-08-25 시점의 사실. 고치지 않는다(정정은 추기로)
> 문서 지도: `docs/README.md`(문서 지도) · `docs/프로젝트_전체흐름.md`(전체 그림·용어 해설)

---

# 작업 보고 — 2026-08-10 (Qform_ver3 T1~T4)

> **브랜치** `Qform_ver3`
> **범위** T1~T4 (전이 층 + 검증). T5~T8(렌더·문서)은 미착수
> **HCX 콜** 이 세션 전체 **0** — 전 구간 결정론 검증
> **선행** `CLAUDE.md` · `docs/records/Qform_ver3_task_assignment.md`

---

## §0. 한눈에

전이 층 세 가지(반복질문·슬롯 이월·정의형 예외)를 닫고, 그것을 담보하는 멀티턴 하니스를 세웠다.
명세서 §0-2에 따라 **450셋 회귀 측정은 불필요**했고, 대신 **T4 결정론 하니스 19시나리오**가 R3의 대체 담보다.

| T | 이름 | 상태 | 담보 |
|---|---|---|---|
| T1 | 반복질문 버그 해소 | ✅ | `next_question` 691케이스 ver2 대조 불일치 0 |
| T2 | 슬롯 이월 + 파라미터 외부화 | ✅ | 첨부 ON/OFF 병기 · 이월 사유 결정론 출력 |
| T3 | 정의형 질의 예외 | ✅ (단서 있음) | 450셋 되묻기 9건 무변경 |
| T4 | 멀티턴 검증 하니스 | ✅ | **19/19 통과** · 지문 `sha256 f0b78f2c8efe5543` |

**미해결 1건** — `verify_qform_e2e.py` AC2가 T1과 구조적으로 충돌한다. 사람의 결정이 필요하다(§5).

---

## §1. T1 — 반복질문 버그 해소

### 문제

응답이 어떤 슬롯도 채우지 못하면 **같은 슬롯을 다시 물었다.** 원인은 로직이 아니라 상태 스키마 —
"이 슬롯은 물었고 답을 얻지 못했다"를 기록할 자리가 없었다.

### 변경

| 파일 | 내용 |
|---|---|
| `chatbot/qform_flow.py` | `new_state()`에 `asked: []` · `start()`에서 리셋 · `reply()`에서 `_mark_asked()` · `_step()`이 `exclude` 전달 |
| `chatbot/qform_state.py` | `next_question(slots, exclude=None)` — `eligible`에서 `exclude` 슬롯 제외 |

`asked`는 슬롯 **값이 아니라 대화 이력**이라 `qform` 밖 최상위 키에 둔다. `_clean()`을 안 거치므로 `answer()`로 새지 않는다.

### 실측

```
── AC1-1 재질문 0 · AC1-2 MAX_ASK_TURNS 내 답변 도달 ──
  시나리오          되물은 슬롯 순서                   중복  ask턴  답변도달
  R1 무관한 답변     ['qualification']                 0     1     도달
  R2 3턴 무응답성    ['qualification']                 0     1     도달
  R3 asked 소진     ['qualification','subject']       0     2     도달
  정상 2턴(대조)     ['qualification','subject']       0     2     도달

── AC1-3 next_question(exclude=None) ≡ ver2 ──
  대조 케이스 691건 (14행 전수 × 부분채움 격자 + 허용값 조합) · 불일치 0건
  ※ ver2 원본을 `git show HEAD:`로 떠서 두 구현 출력을 직접 대조

── AC1-4 answer() 인자에 asked 미포함 ──
  전달 키 5개(SLOT_FIELDS만) · 슬롯 외 키 0건
```

### 명세서와 다르게 간 것

1. **파일 귀속 정정** — 명세 T1-①은 "`qform_state.py`의 `new_state()`"라 했으나 `new_state()`·`_clean()`은 실제로 `qform_flow.py`에 있다. `asked`는 `qform_flow`, `exclude`는 `qform_state`에 넣었다.
2. **`ask_turn` 증가 지점 유지** — 명세 T1-②를 문자 그대로 `reply()`에 증가를 추가하면 턴이 이중 계수되어 `MAX_ASK_TURNS=2`가 실질 1턴이 된다(ver2 대비 전이 회귀). 현행 `_step()` 한 곳으로 유지했고, 질문을 발행하고 증가하지 않는 경로는 없다.
3. **`asked`는 질의 단위 초기화** — `start()`에서 `[]`로 리셋. 턴 간 이월은 T2 `SLOT_CARRYOVER`의 소관이며 선취하지 않았다.

세 건 모두 착수 전 확인받고 진행했다.

---

## §2. T2 — 슬롯 이월 + 대화 정책 파라미터 외부화

### 문제

`start()`가 새 질의마다 상태를 통째로 덮어써 **턴 간 정보 이월이 0**이었다. 되묻기로 좁힌 슬롯이 다음 턴에 증발했다.

### 설계 근거 — 실측이 설계를 결정했다

착수 전에 후속 질의의 `classify_query_bf` 판정을 쟀다. 이 표가 세 가지 결정을 강제했다.

| 그룹 | 실측 | 함의 |
|---|---|---|
| 동일 업무 후속 6문항 | **전부 `classify=None`** | "bf가 직전과 같을 때만"을 문자 그대로 구현하면 이월이 **영영 발동 안 함** → bf 상속 필수 |
| 업무 전환 5문항 | 전부 구체 업무로 확정 (예금자보호제도·고객 미수령금 신청·채무조정 안내 등) | `bf_match` 방벽이 깨끗하게 작동 |
| 잡담 3문항 | 착오송금을 상속시켜도 **추출 슬롯 0개** | 여기가 오이월 차단 지점 |

### 변경

| 파일 | 내용 |
|---|---|
| `chatbot/qform_config.py` ★신규 | 파라미터 4종 + `SPEC`(콘솔용 메타) + `resolve()`/`validate()` |
| `chatbot/qform_flow.py` | `_carryover_gate()` · `start()` 이월 로직 · `turn_no`/`slot_turn`/`slot_origin` · `config` 배선 |
| `chatbot/qform_trace.py` | `L["slots"]`에 `origin`/`carried`/`carryover` 추가 |

| 파라미터 | 기본값 | 허용값 |
|---|---|---|
| `SLOT_CARRYOVER` | `True` | bool |
| `CARRYOVER_TTL` | `2` | 1~5 |
| `CARRYOVER_SCOPE` | `"bf_match"` | `bf_match` \| `global` \| `off` |
| `MAX_ASK_TURNS` | `2` | 1~3 (`qform_flow`에서 이관, 별칭 유지) |

허용범위 밖 값은 예외 대신 **기본값으로 되돌리고 `_invalid`에 기록**한다. 사이드바(사람 입력)에서 오는 값이라 잘못된 값 하나로 대화가 죽으면 안 된다.

### 실측

```
── AC2-1 슬롯 유지 · AC2-6 첨부 ON/OFF 병기 ──
  C1 동일업무 2턴   첨부 OFF 12 → ON 8   이월 ['qualification','subject']
  C2 확정→후속      첨부 OFF 12 → ON 8   이월 ['qualification','subject']
  부수 효과: OFF는 후속 턴에 qualification을 **다시 묻는다**. ON은 안 묻는다.

── AC2-2 업무 전환 오이월 0건 ──
  C3  →미수령금   이월 0 · "업무 전환 착오송금 반환 신청 → 고객 미수령금 신청"
  C3b →예금보호   이월 0 · "업무 전환 착오송금 반환 신청 → 예금자보호제도"
  C4  →소관밖     이월 0 · "신규 추출 0 — 업무 증거 없음"

── AC2-3 신규 > 이월 ──  subject 법인 → 미성년자 (출처 '신규')
── AC2-4 TTL ──         TTL=1 이월 1턴 / TTL=2 이월 2턴 / TTL=3 이월 3턴
── AC2-5 이월 OFF ──    6턴 슬롯·answer() 인자 전부 '매 턴 새 상태'와 동일
── 트레이스 ──          {party:신규, sub_task:신규, qualification:이월, subject:이월, method:미채움}
```

AC2-6 수치가 명세서 예시(22→2)와 다른 건 예시가 포맷 견본이라 그렇다. 실측 기준선(착오송금 3문서 24파일)에서 **12→8건**이다.

### 명세서가 비워둔 자리를 채운 결정 3건

1. **`bf` 상속** — 판정 불명이면 직전 업무를 물려 `extract`에 넣는다. 업무가 **다른 값으로 확정**되면 상속도 이월도 차단.
2. **`<스코프 통과>` = 신규 추출 슬롯 ≥ 1** — 명세서가 플레이스홀더로 남긴 자리. 잡담도 판정 불명이라 1번 게이트를 통과하는데, 여기서 막지 않으면 직전 슬롯이 통째로 따라붙는다. **명세서 의사코드에 없는 추가 조건.**
3. **TTL 의미 = `현재턴 − 설정턴 ≤ TTL`** — `TTL=2`면 설정 후 2개 후속 턴까지 유효. 이월된 슬롯은 **원래 설정 턴 스탬프를 유지**해서 계속 늙는다(안 그러면 영구 생존).

`CARRYOVER_SCOPE="global"`은 업무 방벽과 증거 게이트를 **둘 다** 걷어낸다 — 데모에서 방벽의 효과를 보이려면 방벽 없는 쪽이 실제로 오이월을 내야 하기 때문. 기본값 승격 안 함.

---

## §3. T3 — 정의형 질의 예외

### ⚠ 명세서의 전제가 재현되지 않았다

명세서는 "정의형 질의에 되묻기 게이트가 발동한다"를 문제로 들었으나, **그런 사례가 0건**이다.

```
450셋 전수 (450건)
  되묻기 발동          9건   ← 전부 서류·접수·절차 질의
  정의형 어휘 보유     24건
  교집합               0건   ← T3 대상이 존재하지 않음

이월(T2) 후 다중턴 — 정의형 후속 9종
  이월 때문에 새로 생긴 되묻기: 0건
```

구조적 이유다. 되묻기 게이트는 `sub_task == "반환신청"`일 때만 열리는데, 정의형 질의는 `sub_task`가 `제도안내` 또는 `None`으로 떨어져 게이트가 애초에 안 열린다. 명세서가 든 예시 "가지급금이 뭔가요"조차 `sub_task=None`이라 이미 되묻기를 안 타고, `verify_qform_e2e.py` AC4가 그것을 이미 검증하며 통과 중이었다.

### ⚠ 그리고 명세서가 제시한 패턴은 데모 주력 질의를 죽인다

명세서의 좁은 패턴(`~가 뭔가요/뭐예요/무엇인가요/란/이란/의 정의`)을 그대로 적용하면:

```
"착오송금 반환 신청 서류가 뭐예요?"
  현행: 되묻기 qualification  →  좁은 패턴 적용: 정의형 판정 →  되묻기 소멸 ⛔
  └ B그룹 첫 질의 · verify_qform_e2e AC1 시나리오 · 첨부 좁힘 시연 주력
```

"뭐예요" 하나에 걸린다. `CLAUDE.md` §3이 경고한 함정 그대로다.

### 변경 — 절차·서류 어휘 배제 조항을 추가했다

`is_definitional(query)` = 정의형 마커 **AND NOT** 절차·서류 어휘 **AND NOT** 얼마·언제까지

| 파일 | 내용 |
|---|---|
| `chatbot/qform_extract.py` | `is_definitional()` 신규 (`_DEF_MARKERS` / `_PROC_KW` / `_NOT_DEF`) |
| `chatbot/qform_flow.py` | `_step()` 정의형 우회 · `BYPASS_DEFINITIONAL` · `state["ask_bypass"]` |
| `chatbot/qform_trace.py` | `_no_ask_reason()`에 `bypass` 인자 · `L["ask"]["bypass"]` |

절차·서류 어휘 배제는 **명세서에 없는 조건**이다. 개념을 묻는 것과 방법을 묻는 것은 어미가 같아도 다른 질의다.

### 실측

```
── AC3-1 정의형 8문항(D1~D8) 되묻기 발동 ──  0건 · 전부 answer · definitional_bypass
── AC3-4 반례 5문항(얼마·언제까지) 오판 ──    0건
── AC3-2 기존 되묻기 판정 무변경 ──
     450셋 발동: T3 전 9건 → 후 9건 · 우회로 사라진 것 0건
     14행 분포: 0턴 7 / 1턴 1 / 2턴 6 · 평균 0.93턴 (ver2 기대치 일치)
── AC3-3 소관 밖 정의형 6문항 ──  슬롯 전부 {} · 검색쿼리 전부 무변형
── 기능 확인 (자연 발동 0이라 인위 구성) ──
     되묻기 조건 갖춘 상태 + 정의형 질의 → next_question=qualification 인데 전이는 answer
     슬롯 {party:송금인, sub_task:반환신청} 유지 (지우지 않음)
── 450셋 정의형 판정 분포 ──  23/450건 (5.1%) · 전부 타 업무 · 되묻기 발동분과 교집합 0
```

`route=reject` 자체는 `chain.answer()` 내부 분류기 소관이라 콜 0으로 잴 수 없다. T3이 건너뛰는 건 **되묻기뿐**이고 스코프 게이트는 `extract()`에 그대로 있으므로, AC3-3은 "슬롯 0 · 쿼리 무변형"으로 측정했다.

### 결론 — 솔직하게

구현은 넣었지만 **오늘 고치는 버그는 없고, 앞으로를 막는 방어 장치**다.
되묻기 게이트가 넓어지거나(6업무 확장 등) 이월이 `sub_task`를 더 자주 물려주게 되면 그때 문다.
**AC3-1이 "발동 0"인 것도 T3 덕분이 아니라 원래 0이었기 때문**이며, 이 사실을 T8 결과공유에 그대로 싣는다. 없는 성과를 주장하지 않는다.

---

## §4. T4 — 멀티턴 검증 하니스

`chatbot/verify_qform_multiturn.py` 신규. `verify_qform_e2e.py`는 **한 줄도 건드리지 않았다**(HEAD 대비 diff 0줄 확인).

```
━━━ 멀티턴 전이 검증 (HCX 콜 0) ━━━
  시나리오  대상 AC    기대                  실측                                    판정
  R1       AC1-1     재질문 0              재질문 0                                 ✅
  R2       AC1-2     답변 도달 · 턴≤2       answer · 턴 1 · 재질문 0                  ✅
  R3       AC1-1·2   asked 2종 소진→답변    asked=['qualification','subject'] · answer ✅
  C1       AC2-1     이월 ≥1               이월 ['qualification','subject']          ✅
  C2       AC2-1·6   이월 ≥1 · 첨부 ON<OFF  이월 2개 · 첨부 12→8                      ✅
  C3       AC2-2     오이월 0              오이월 0 · 업무 전환 착오송금 → 고객 미수령금 신청  ✅
  C4       AC2-2     오이월 0 (2턴)         소관밖 0 · 복귀 0                          ✅
  C5       AC2-3     법인→미성년자(신규)      법인→미성년자(신규)                          ✅
  C6       AC2-4     TTL=2 후 만료         신규 → 이월 → 이월 → 미채움                   ✅
  C7       AC2-5     ver2 등가 (슬롯·인자)   슬롯 동일 · answer 인자 동일                  ✅
  D1~D5    AC3-1     되묻기 0 · 우회         answer · definitional_bypass (5건)        ✅
  D6~D8    AC3-4     정의형 아님            정의형=False · bypass=None (3건)            ✅
  콜회계    AC4-1     chain 미로딩 · 콜 0     chain 로딩=False · 되묻기 LLM 콜 0           ✅

  19/19 통과 · 결과 지문 sha256 f0b78f2c8efe5543
```

| # | 기준 | 실측 |
|---|---|---|
| AC4-1 | HCX 콜 0 (스텁 주입) | `chain`이 `sys.modules`에 **아예 없음** · 되묻기 LLM 콜 0 |
| AC4-2 | 통과 표 / 실패 시 어긋난 AC 표 | 19행 표 + `fails` 분기 구현 |
| AC4-3 | `verify_qform_e2e.py` diff 0줄 | HEAD 대비 **0줄** |
| AC4-4 | 재실행 동일 출력 | 2회 실행 diff **0줄** · 지문 출력으로 상시 확인 가능 |

첨부는 스텁이 아니라 **실제 `attachments.collect()`** 를 돌린다(순수 로컬 조인). 이월 ON/OFF 첨부 건수를 진짜로 비교할 수 있다.

---

## §5. ⛔ 결정 대기 — `verify_qform_e2e.py` AC2

**현상**: `verify_qform_e2e.py`가 AC2 하나에서 실패한다(exit 1). 나머지 AC1·AC3~AC7은 전부 OK이고, AC6 첨부 건수(8/8/10/8/2/2/24/24)·AC7 되묻기 턴 분포까지 기준선과 완전 동일하다.

```
── AC2. 2턴 후 미채움이어도 진행 ──
  ver2  전이: ask → ask → answer · ask_turn=2
  ver3  전이: ask → answer      · ask_turn=1   → DIFF
```

**원인은 버그가 아니라 AC2가 버그를 기대값으로 박아둔 것이다.** 대본이 `["…서류가 뭐예요?", "글쎄요", "잘 모르겠어요"]`인데, ver2에서 2번째 `ask`는 **1번째와 같은 `qualification`을 다시 묻는 것**이었다. 그게 정확히 AC1-1이 없애라고 한 재질문이다.

T1 이후 이 대본으로 2턴에 도달하는 것은 **구조적으로 불가능**하다 — 두 번째로 물을 수 있는 `subject`는 `qualification == "대리인"`일 때만 게이트가 열리는데, 응답이 슬롯을 못 채우면 그 조건이 안 선다. AC2는 기대값이 달라진 게 아니라 **충족 불가능해졌다.**

AC2가 지키려던 성질("미채움이어도 답변 도달 · 무한 되묻기 없음")은 살아 있고 오히려 강해졌으며(2턴 → 1턴), **T4의 R2가 이어받아 통과 중**이다.

| 안 | 내용 | 대가 |
|---|---|---|
| **A** (현재 진행 중) | e2e를 그대로 두고 AC2 실패를 문서화 | §0-2·AC4-3 완전 준수. 대신 **스프린트 내내 하니스가 빨간 채로 exit 1** — T5~T7에서 진짜 회귀가 나도 이미 빨개서 안 보임 |
| **B** (권고) | e2e AC2 기대값 3줄 수정 (`["ask","answer"]` · `ask_turn==1`) + 사유 주석 | **무변경 목록 위반 → 승인 필요.** T4의 AC4-3도 함께 완화 필요 |
| C | 2턴을 살리도록 T1 구현 변경 | AC1-1 정면 위반. **불가** |

현재 A로 진행 중이다. B를 권고하는 이유는 "항상 빨간 하니스"가 `CLAUDE.md` §4-8(각 T 종료 시 하니스 재실행)이 막으려던 실패를 그대로 만들기 때문이다. **T5 착수 전에 정하는 것이 좋다.**

---

## §6. 무변경 파일 확인

| 파일 | 상태 |
|---|---|
| `crawler/rag.py` | 미접촉 |
| `crawler/eval.py` | 미접촉 |
| `chatbot/chain.py` | 미접촉 (`on_progress` 등 kwarg 추가 없음) |
| `crawler/data/chunks.jsonl` · `data/raw/` · `data/parsed/` | 미접촉 |
| `crawler/data/qform_combos_msdr.csv` | 미접촉 (14행 동결) |
| `crawler/data/qform_prompts.csv` | 미접촉 |
| `chatbot/verify_qform_e2e.py` | 미접촉 — **HEAD 대비 diff 0줄 확인** |

트레이스 조립은 전부 app/트레이스 층에서만 한다(§2-7). 파이프라인에 로깅·리턴값 추가·전역 심기 없음.

---

## §7. 하니스 상태 (10종)

| 하니스 | 결과 |
|---|---|
| `qform_config.py` | ✅ |
| `qform_state.py` | ✅ (14행 0턴7/1턴1/2턴6 · 평균 0.93턴 유지) |
| `qform_extract.py` | ✅ |
| `qform_ask.py` | ✅ (ⓐ 콜 0 · ⓑ 턴당 1콜 · 가드 8종 폴백) |
| `qform_trace.py` | ✅ (450셋 재계산 정합 · 트레이스 ON/OFF 동일) |
| `qform_panel.py` | ✅ |
| `verify_qform_integration.py` | ✅ |
| `verify_docs.py` | ✅ |
| **`verify_qform_multiturn.py`** ★신규 | ✅ **19/19** |
| `verify_qform_e2e.py` | ⛔ **AC2 하나** — §5 결정 대기 |

---

## §8. 커밋 이력 (T 단위)

```
T1  git add chatbot/qform_state.py chatbot/qform_flow.py
    fix(qform): 되묻기 반복질문 해소 — asked 이력 추가·슬롯 재질문 차단

T2  git add chatbot/qform_config.py chatbot/qform_flow.py chatbot/qform_trace.py
    feat(qform): 슬롯 이월 도입 — 업무전환 방벽·TTL·콘솔 파라미터 외부화

T3  git add chatbot/qform_extract.py chatbot/qform_flow.py chatbot/qform_trace.py
    fix(qform): 정의형 질의 되묻기 우회 — 스코프 게이트 유지
    ※ 명세서 커밋 목록에 qform_trace.py 누락 — 작업 항목 ③이 요구해 추가

T4  git add chatbot/verify_qform_multiturn.py
    test(qform): 멀티턴 전이 검증 하니스 — 이월·반복질문·정의형 19시나리오
```

---

## §9. 다음 — T5~T8

| T | 이름 | 선행 조건 |
|---|---|---|
| T5 | 되묻기 선택지 버튼 + 예시 질의 칩 | **§5 결정 권장** · 칩 문구는 `docs/current/qform_시험질의셋.md`에서만 |
| T6 | 슬롯 칩 수정 + reject 복구 경로 | `edit()` 신규 · 타기관 안내 금지(H7 열림) |
| T7 | 후속 질문 추천 + 예산·에러 처리 | 착오송금에서만 뜨는 것이 정상(C8 동결) |
| T8 | 설계 문서 갱신 · 결과 공유 | 설계스펙 DR · 갭 표 · `SprintDemoV3_결과공유.md` |

T5 이후 각 T 종료 시 **`verify_qform_multiturn.py` 재실행**으로 전이 회귀를 확인한다 —
렌더 작업이 전이를 깨도 화면으로는 안 보인다.

### T8에 반드시 실을 것

- **T3은 오늘 고친 버그가 없다** (§3 결론). 방어 장치로 기록하고 성과로 포장하지 않는다
- 명세서와 다르게 간 결정 5건 (T1 3건 · T2 2건 + T3 1건)
- §0-3 의도적 미구현 목록 — 감점이 아니라 설계 판단의 증거
