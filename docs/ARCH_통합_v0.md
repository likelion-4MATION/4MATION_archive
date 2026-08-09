# ARCH_통합 v0 — 층 전체 흐름 지도

> **v0** · 2026-08-09 · 브랜치 `Qform_ver2` · **팀 공유용**
> **읽는 법** §1만 읽으면 전체 흐름을 말할 수 있게 썼다. 나머지는 필요할 때 찾아보는 참조다.

---

## §0. 이 문서의 성격

**흐름 지도지 설계 결정 기록이 아니다.**

| | 이 문서 (`ARCH_통합_v0`) | `QFORM_ARCH_설계스펙` |
|---|---|---|
| 답하는 질문 | "질의 1건이 **지금 어떻게 흐르나**" | "왜 **그렇게 정했나**" |
| 성격 | AS-IS 스냅샷 | 설계 결정 기록(DR) |
| 충돌 시 | 진다 | **이긴다 (주인 문서)** |

설계를 바꾸려면 `QFORM_ARCH_설계스펙.md`를 먼저 고친다. 이 문서는 코드가 바뀌면 따라 바뀐다.

**§1 다이어그램은 화면과 같은 것이다.** 층 구성이 `chatbot/qform_trace.py`의 `LAYER_ORDER` 상수 하나에서 나오고, 우측 트레이스 패널의 카드도 같은 상수를 읽는다. 그림과 실행 화면이 어긋날 수 없는 구조다.

---

## §1. 질의 1건의 생애 ★

사용자가 "착오송금 반환 신청 서류가 뭐예요?"라고 쳤을 때 벌어지는 일 전부.

```
                    ┌─────────────────────────────────────────────┐
  사용자 질의  ────▶ │  app.py  (렌더 · 토글)                       │
                    │  qform_flow.py  (상태 전이)                   │
                    └────────────────────┬────────────────────────┘
                                         │
   ═══ ① 라우팅 층 ════════════════════════▼═══════════════════════════════
                                                                    콜
   [1] 소관 게이트    chain.classify()  ─ LLM 분류                    1
        정상 / 모호 → 계속        소관밖 → **즉시 거절, 아래 전부 생략**
                                         │
   [2] 업무 신호      rag.classify_query_bf()  ─ 키워드 점수          0
        6업무 × 가중 키워드 → 점수 → 최소 3점 · 마진 2 → 업무 또는 불명
        ★ 여기서 1회만 계산해 아래로 **주입**한다 (MoAI 라우터가 꽂힐 자리)
                                         │
   ═══ ② 큐폼 층 (전부 결정론 · LLM 콜 0) ═══▼═══════════════════════════════
                                                                    콜
   [3] 슬롯 추출      qform_extract.extract(q, business_function=bf)  0
        착오송금이 아니면 → 슬롯 전부 None (스코프 게이트)
        party · sub_task · qualification · subject · method
                                         │
   [4] 조합 생존      qform_state.survivors()                        0
        조합 테이블 14행을 슬롯으로 좁힌다
        14 → 12 → 7 → 6 → 1     (슬롯이 하나씩 걸릴 때마다)
                                         │
   [5] 되묻기         qform_state.next_question()  ─ 판정             0
                      qform_ask.build_question()   ─ 문구         ⓐ0 / ⓑ1
        생존 ≥ 2행이고 물을 슬롯이 있으면  →  되묻고 **여기서 멈춘다**
        ★ 되묻기 턴에는 answer()를 부르지 않는다 → 아래 층이 아예 안 돈다
        최대 2턴. 탈출구("잘 모르겠어요")를 누르면 즉시 아래로.
                                         │
   ═══ ③ 검색·생성 층 ══════════════════════▼═══════════════════════════════
                                                                    콜
   [6] 검색           rag.Searcher.search(mode="hybrid_bf")          0
        dense(FAISS) + BM25 → 가중 RRF → 업무 소프트부스트 → 문서당 1청크
                                         │
   [7] 생성           chain._hcx()  ─ 참고문서만 근거로 답변 생성        1
                                         │
   ═══ ④ 후단 층 ═══════════════════════════▼═══════════════════════════════
                                                                    콜
   [8] 첨부           attachments.collect(hits, qform=slots)         0
        검색이 고른 문서의 첨부를 조합 조인으로 **좁힌다**
        11서식/24파일  →  3서식/8파일
                                         │
   [9] 검증           answer_checks.run_all()                        0
        출처 표기 · 날조 URL · 구정보 — 플래그만 남기고 **차단하지 않는다**
                                         ▼
                              답변 + 근거 문서 + 첨부 파일
                              (우측 패널에 [1]~[9] 층별 근거)
```

**한 문장 요약**: 소관인지 가른 뒤(1) 어느 업무인지 채점하고(2), 그 업무가 착오송금이면 질문을 슬롯으로 채점해(3) 조합 테이블을 좁히고(4), 안 좁혀지면 되묻고(5), 좁혀졌으면 검색·생성해서(6·7) 첨부를 조합으로 정밀화한 뒤(8) 검증 플래그를 붙여(9) 내보낸다.

### 읽을 때 놓치기 쉬운 세 가지

| | |
|---|---|
| **되묻기는 파이프라인을 자른다** | [5]에서 되물으면 [6]~[9]가 **실행되지 않는다**. 그래서 ⓐ 모드 2턴 대화의 HCX 콜은 분류 1 + 생성 1 = **2콜**뿐이다. 되묻기가 콜을 태우지 않는다 |
| **큐폼은 답을 정하지 않는다** | [4]의 조합 생존은 **첨부를 좁히는 데만** 쓴다. 어느 문서를 반환할지는 [6] 검색이 정한다. 슬롯이 비면 첨부가 넓게 나올 뿐 답이 틀리지 않는다 |
| **[2]는 판정이지 필터가 아니다** | 업무 신호는 소프트부스트(가산점)다. 틀려도 정답 문서를 배제하지 않는다. 불명(`None`)이면 부스트를 안 걸고 전체 검색한다 |

---

## §2. 층 4종

§1의 9단계를 성격으로 묶으면 네 층이다. **층마다 실패했을 때 벌어지는 일이 다르다.**

| 층 | 단계 | 성격 | LLM | 틀렸을 때 |
|---|---|---|---|---|
| **① 라우팅** | [1] 소관 게이트 · [2] 업무 신호 | 판정 | 1콜 + 0 | 과차단(정상 질문 거절) 또는 엉뚱한 업무에 가산점 |
| **② 큐폼** | [3] 슬롯 · [4] 조합 · [5] 되묻기 | **결정론** | **0** | 슬롯 미추출 → 첨부가 넓어짐(안전). 오추출 → 정답 조합이 지워짐(해로움) |
| **③ 검색·생성** | [6] 검색 · [7] 생성 | 확률 | 0 + 1콜 | 근거 문서 오선정 · 문서 밖 내용 생성 |
| **④ 후단** | [8] 첨부 · [9] 검증 | 결정론 | **0** | 첨부 과다/누락 · 플래그 오탐 |

> **②가 결정론인 것이 설계의 핵심이다.** 애매하면 `None`으로 둔다 — 오추출은 미추출보다 해롭다. 미추출은 첨부가 넓어질 뿐이지만, 오추출은 사용자가 보기도 전에 정답 조합을 지운다.

---

## §3. AS-IS 실배선표

§1의 각 단계가 **실제로 어느 파일 어느 함수**인지. (2026-08-09 기준)

| # | 층 | 파일 | 함수 / 상수 |
|---|---|---|---|
| — | 진입 | `chatbot/app.py` | `record()` · `build_trace()` · `ASK_MODES` |
| — | 상태 전이 | `chatbot/qform_flow.py` | `new_state()` · `start()` · `reply()` · `skip()` · `MAX_ASK_TURNS=2` |
| **1** | 소관 게이트 | `chatbot/chain.py` | `classify()` · `_route()` · `CLS_PROMPT` · `REJECT_TEXT` |
| **2** | 업무 신호 | `crawler/rag.py` | `classify_query_bf()` · `BF_QUERY_KEYWORDS` · `QBF_MIN_SCORE=3` · `QBF_MARGIN=2` |
| | ↳ 근거 재계산 | `chatbot/qform_trace.py` | `bf_debug()` — rag 상수를 읽어 점수 내역 재구성 |
| **3** | 슬롯 추출 | `chatbot/qform_extract.py` | `extract(query, business_function=_UNSET)` · `IN_SCOPE_BF` · `ALLOWED` · `_SUBTASK_RULES` |
| **4** | 조합 생존 | `chatbot/qform_state.py` | `survivors()` · `serialize()` · `SLOT_FIELDS` · `_COMBOS` |
| | ↳ 데이터 | `crawler/data/qform_combos_msdr.csv` | 14행 (C01~C14) — **동결** |
| **5** | 되묻기 판정 | `chatbot/qform_state.py` | `next_question()` · `_ASK_GATES` |
| | ↳ 문구 생성 | `chatbot/qform_ask.py` | `build_question(mode)` · `guard()` · `MAX_EXAMPLES=3` · `MAX_LEN=140` |
| | ↳ 데이터 | `crawler/data/qform_prompts.csv` | 20행 — 문장·표시 문구·근거 청크 |
| **6** | 검색 | `crawler/rag.py` | `Searcher.search(mode="hybrid_bf")` · `BF_MODE="soft"` · `BF_BOOST=0.005` · `RRF_ALPHA=0.6` · `RRF_K=5` · `BF_DOC_CAP=1` · `FACET_BOOST=0.03` |
| **7** | 생성 | `chatbot/chain.py` | `_hcx()` · `answer()` · `SYS_PROMPT_V2` · `GEN_PARAMS` · `CALL_BUDGET=70` |
| **8** | 첨부 | `chatbot/attachments.py` | `collect(hits, qform=)` · `_qform_narrow()` · `_joins_combo()` · `QFORM_SCOPE_BF` |
| **9** | 검증 | `chatbot/answer_checks.py` | `run_all()` · `_is_rejection()` |
| — | 트레이스 | `chatbot/qform_trace.py` | `collect()` · `LAYER_ORDER` · `LAYER_LABEL` · `DETERMINISTIC` |
| — | 패널 | `chatbot/qform_panel.py` | `panel_model()` · `render()` · `highlight()` · `PANEL_HEIGHT=620` |

**검증 스크립트** (전부 `전체 통과 ✅` 또는 어긋난 AC 표를 출력한다)

```bash
python3 chatbot/qform_trace.py            # T1 재계산 정합 + T5 트레이스
python3 chatbot/qform_ask.py              # T2 문구 외부화 + T3 가드 (ⓐ는 콜 0)
python3 chatbot/qform_ask.py --live       # T3 실제 HCX 되묻기 (2콜)
python3 chatbot/qform_state.py            # 회귀 — 0턴7/1턴1/2턴6 · 0.93 · 2.0%
python3 chatbot/verify_qform_e2e.py       # T4 E2E 전이 (HCX 콜 0)
python3 chatbot/qform_panel.py            # T6 패널 모델
python3 chatbot/verify_qform_integration.py   # B통합 — 11서식/24파일 → 1~4서식
python3 chatbot/verify_docs.py            # T7 문서 정합 (§1↔패널 · §3↔코드 · 추기만)
streamlit run chatbot/app.py              # E2E + 우측 패널
```

---

## §4. 설계-구현 갭

**문서엔 있고 코드엔 없는 것.** 데모에서 "이거 되나요?" 질문이 나올 자리다.

| # | 항목 | 문서 근거 | 코드 상태 | 막고 있는 것 |
|---|---|---|---|---|
| G1 | **MoAI 라우터** | `router_finetune_record.md` | **주입점만.** `app.py`에서 `classify_query_bf()` 부르는 자리가 교체 지점 | 확정 조건 4건(시드3·D코드 매핑·tau 재보정·200 test) + **GPU 상시 서빙** |
| G2 | **Energy 스코어 · tau** | 같은 문서 §5·§7 | 없음 | 채택 스코어가 MSP→Energy로 바뀌어 임계 **재보정 필요**(기존 MSP tau 무효) |
| G3 | **λ (키워드×라우터 조합)** | `라우팅x키워드분류기_조합_초기아이디어.md` §3.1 | 없음. **현행 = λ=0**(키워드 단독) | G1 선행. `eval_TF.py` λ 스윕 A/B 미실행 |
| G4 | **link route** | `DECISIONS.md` · `handoff_chain_draft.md` §4 | `_route()`는 rag/reject만 반환. `link_registry.json`은 있으나 **미연결** | HOLES **H7** — 외부 담당기관 URL 미확보(창작 금지) |
| G5 | **handoff 분기** | `qform_기획서_v1.md` §12 (rag/reject/**handoff**) | 없음 | 민원 어휘 프리필터 미구현. 상담 연결 대상·경로 미정 |
| G6 | **B-2 자격·한도 판정** | `QFORM_ARCH` §7-3 | **구현 안 함(의도적)** | 규칙 1 정면 충돌. 채무조정은 원리적으로 불가(개별심사) |
| G7 | **C 상태 의존 분기** | `QFORM_ARCH` §2-2 | 없음 | 조합 테이블로 표현 불가 — 분기 트리 템플릿 별도 설계 필요 |
| G8 | **D 용어 판별 사전** | `QFORM_ARCH` §2-2 | 없음 | 착오송금 관통 이후 |
| G9 | **E 링크 레지스트리** | `QFORM_ARCH` §2-2 | 데이터만 있고 미연결 | G4와 같은 H7 |
| G10 | **메타데이터 부스트** | `QFORM_ARCH` §9 ③ | 없음 | **오라클 실험 선행 필수** |
| G11 | **6업무 확장** | 기획서 전반 | 착오송금 1업무만 | 나머지 5업무 조합 테이블 미작성 |
| G12 | **관리자 콘솔** | 스프린트 계획 v3 | CSV 외부화까지만 | A(E2E)가 돌아야 "콘솔에서 뭘 만질지"가 확정된다 |
| G13 | **검색측 업무 재분류** | 이번 스프린트 실측 | `rag.search`가 **부스트된 쿼리로 업무를 다시 분류**한다 | `rag.py` 무수정 제약. 부스트 ON에서 app 판정과 **13건** 갈림 → 패널에 `⚠ 업무 갈림`으로 표기 |

> **G13은 이번에 새로 드러난 것이다.** 부스트를 켜면 검색 쿼리가 바뀌고, `rag.search` 내부가 그 바뀐 쿼리로 업무를 다시 분류한다. 슬롯 필터가 보는 업무와 검색 부스트가 보는 업무가 갈릴 수 있다. 부스트가 기본 OFF라 지금은 안 터지지만, ON을 기본으로 올리기 전에 반드시 정리해야 한다.

---

## §5. 계약 (깨면 안 되는 것)

| # | 계약 | 어디서 강제되나 |
|---|---|---|
| C1 | `chain.answer()` 반환 **4필드 무변경** — `text` `sources` `confidence` `route`. 부가는 `checks`/`attachments`/`_meta`에만 | `verify_qform_integration.py` AC4 |
| C2 | `crawler/rag.py` · `crawler/eval.py` · `chatbot/chain.py` **diff 0줄** — 손대면 450셋 회귀가 따라온다 | `qform_trace.py` AC2 (sha256 표기 + `git diff` 사람 확인) |
| C3 | `attachments.collect(qform=None)` = **기존 동작 완전 동일** (graceful degradation) | `verify_qform_integration.py` AC1 |
| C4 | 후단 필터는 **부분집합만** — 첨부를 추가하지 않고 좁히기만 | 같은 스크립트 AC2 |
| C5 | 되묻기 **판정은 결정론** — LLM은 표현 층에만 개입 | `qform_ask.py` T3-AC6 (14행 전수 판정 불일치 0) |
| C6 | LLM이 **선택지를 창작하지 않는다** — 값은 조합 테이블에서만 | `qform_ask.py` T2-AC4 · `guard()` |
| C7 | 트레이스를 꺼도 **답변·첨부·콜수 동일** | `qform_trace.py` T5-AC3 |
| C8 | 조합 테이블 14행 **동결** | 행 추가·수정은 별도 결정 사항 |

---

## §6. 하드코딩 경계

| 대상 | 처리 | 이번에 바뀐 것 |
|---|---|---|
| 첨부 양식파일 · 외부 링크 | **하드코딩**(레지스트리) — 청크에 텍스트가 없어 검색 불가 | — |
| 구비서류 항목 선택 | **조합 테이블**(`qform_combos_msdr.csv` 14행) | — |
| **되묻기 문구** | **CSV**(`qform_prompts.csv` 20행) | ⬅ v1은 코드 상수 2개였다 |
| 설명·본문 | **검색** | — |
| 어느 문서를 반환하나 | **검색** (박지 않음) | — |
| 자격·한도 판정 | **구현 안 함** | — |

**부연 표현은 코퍼스 실재분만 쓴다.** v1 되묻기 문구의 부연 4개가 전부 코퍼스 0청크(창작)였고, 원문 표현으로 교체했다 — 자세한 판정은 `DECISIONS.md` 08-09 항목.

---

## §7. 콜 회계

| 경로 | 분류 | 되묻기 | 생성 | 합 |
|---|---|---|---|---|
| 일반 질의 (0턴) | 1 | 0 | 1 | **2** |
| 되묻기 2턴 · **ⓐ 템플릿(기본)** | 1 | **0** | 1 | **2** |
| 되묻기 2턴 · ⓑ LLM | 1 | 2 | 1 | **4** |
| 소관 밖 (reject) | 1 | — | **0** | **1** |
| 트레이스 ON | +0 | +0 | +0 | **+0** |

- 되묻기 턴에는 `answer()`를 부르지 않으므로 **되묻기가 늘어도 생성 콜은 1이다.**
- 트레이스는 반환값 읽기 + 결정론 재호출뿐이라 **콜을 늘리지 않는다.** 9층 중 6층이 콜 0.
- 예산은 `chain.CALL_BUDGET=70` 하나를 공유한다. ⓑ 모드도 별도 예산을 두지 않는다.

---

## §8. 알려진 한계

본문을 여기 옮기지 않는다 — 원본이 주인이다.

| | 항목 | 원본 |
|---|---|---|
| 보호한도 구정보 | 5천만원/1억원 표기 혼재 (사이트측 문제로 종결, **현행 1억원 고정**) | `crawler/HOLES.md` H6 · H6b · H9 · H26 |
| 타기관 URL 미확보 | link route·라우팅 레지스트리를 막고 있음 | 같은 파일 H7 |
| 평가셋 self-referential | 낙관 편향 | H12 |
| gt_docs 근사 · 착오송금 중복 타겟 | 열림(사람 판단 대기) | H16 · H17 |
| FAQ 인접 질의 흡수 | 검색 오염 | H22 |
| 문서 결정 로그 | 전체 | `/DECISIONS.md` · `docs/QFORM_ARCH_설계스펙.md` |
