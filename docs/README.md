<!-- 상태:index -->
> **문서 지도** — 어디에 무엇이 있나. 처음이면 [`프로젝트_전체흐름.md`](프로젝트_전체흐름.md)
> 부터 읽으면 된다(용어 해설 포함).

---

# docs — 문서 지도

## 먼저 읽을 것 셋

| 문서 | 무엇 |
|---|---|
| [**프로젝트_전체흐름.md**](프로젝트_전체흐름.md) | 전체 그림 · **용어·지표 해설** · 배운 것 5가지. 사전 지식 없이 읽을 수 있게 썼다 |
| [**INDEX_시간축.md**](INDEX_시간축.md) | "언제 무슨 일" — `logs/`·회의록을 등뼈로 4개 국면 |
| [**INDEX_사건축.md**](INDEX_사건축.md) | "무슨 문제를 어떻게" — 문제→원인→해결→근거 12건 |

## 4계층 — 문서 맨 위 배지를 먼저 볼 것

| 계층 | 뜻 | 개수 |
|---|---|---:|
| [`current/`](current/) | **정본** — 지금 이대로 돌아간다 | 8 |
| [`records/`](records/) | **기록** — 그때의 사실, 고치지 않는다 | 70 |
| [`plans/`](plans/) | **계획** — 실행 여부를 배지에 적었다. 현행과 다를 수 있다 | 7 |
| [`superseded/`](superseded/) | **폐기·경위** — 왜 그 길로 안 갔는지 | 3 |

---

## current/ — 정본 8건

| 문서 | 무엇 |
|---|---|
| [`RUNBOOK.md`](current/RUNBOOK.md) | **실행 명령 정본.** 5개 축 + 평가·검증 |
| [`OOS_구현_운영가이드.md`](current/OOS_구현_운영가이드.md) | 소관밖 처리 운영 절차·안전 규칙 |
| [`QFORM_ARCH_설계스펙.md`](current/QFORM_ARCH_설계스펙.md) | 되묻기(Qform) **설계 원천(DR)** |
| [`관리자콘솔_사양서.md`](current/관리자콘솔_사양서.md) | 콘솔 화면·파라미터 사양 |
| [`KDIC_소관경계_정리.md`](current/KDIC_소관경계_정리.md) | 무엇이 예보 소관인가 |
| [`router_checkpoint.md`](current/router_checkpoint.md) | 라우터 체크포인트 배포·무결성 |
| [`faq_routing_bf.md`](current/faq_routing_bf.md) | FAQ 청크 BF 태깅 규약 |
| [`qform_시험질의셋.md`](current/qform_시험질의셋.md) | 시연 질의 원문 — 코드가 인용하는 고정 자산 |

## plans/ — 계획 7건

배지에 **실행 상태**를 적었다. 본문이 현행과 다를 수 있다.

| 문서 | 실행 상태 |
|---|---|
| [`OOS_처리로직_계획서.md`](plans/OOS_처리로직_계획서.md) | **부분 구현.** §3 L0 게이트를 LLM 으로 전제 — 현행은 라우터 기권 |
| [`작업계획서_초기라우팅_B안채택.md`](plans/작업계획서_초기라우팅_B안채택.md) | 학습·평가 완료, **전환 미착수**. §10-1 미결 |
| [`1150_테스트셋_생성계획서.md`](plans/1150_테스트셋_생성계획서.md) | 생성 완료. §10 의 "G6 130건"은 실물과 다름(210건) |
| [`복합질의_라우팅_3안비교.md`](plans/복합질의_라우팅_3안비교.md) | **구현됨** — `orchestrator.py`·`query_units.py` |
| [`통합계획서_release_v1.md`](plans/통합계획서_release_v1.md) | 미승인 초안. M1·M4·M5 구현, 나머지 미착수 |
| [`답변품질_LLM심사_HCX_vs_DeepSeek.md`](plans/답변품질_LLM심사_HCX_vs_DeepSeek.md) | **HCX 파일럿 + bounded parent A/B 완료(08-26)** · DeepSeek 대기. 결과 §14 · §15 · 판정축 §16 · 앵커≠답변품질 §17 · 본채점 150 자동지표 §18 · 헤드룸·리랭커 §19 · k=5·BF절제 §20 |
| [`실전1-2_피드백_해결계획.md`](plans/실전1-2_피드백_해결계획.md) | **미착수.** 실전1 15건 + 실전2 13건 + 종합 예상질문 18건 — 신규 작업 7건 · 팀 확인 1건. 우선순위는 §20 |

## superseded/ — 폐기·경위 3건

지우지 않는 이유는 `archive/README.md` 와 같다 — **판단 변경의 근거가 여기 남아 있다.**

| 문서 | 대체 |
|---|---|
| [`qform_기획서_v1.md`](superseded/qform_기획서_v1.md) | `current/QFORM_ARCH_설계스펙.md` rev.3 (D1 이 게이트 전제를 폐기) |
| [`앵커텍스트_정답라벨링_초기아이디어.md`](superseded/앵커텍스트_정답라벨링_초기아이디어.md) | `records/앵커텍스트_정답라벨링_파이프라인.md` → `crawler/eval.py` |
| [`라우팅x키워드분류기_조합_초기아이디어.md`](superseded/라우팅x키워드분류기_조합_초기아이디어.md) | `plans/작업계획서_초기라우팅_B안채택.md`(B안) → `crawler/rag.py` |

## records/ — 기록

고치지 않는다. 정정은 추기로 한다(`router_finetune_record.md` 가 그 예).

### 측정·결론 (숫자의 출처)

| 문서 | 무엇 |
|---|---|
| [`방법론_정확도개선_결론_20260818.md`](records/방법론_정확도개선_결론_20260818.md) | hit@5 `.765 → .891` 계보 5단계 |
| [`router_판정경계_측정_20260825.md`](records/router_판정경계_측정_20260825.md) | 라우터 OOS 차단율 · 시드 분산 σ=0.015 |
| [`router_finetune_record.md`](records/router_finetune_record.md) | MoAI vs kf-deberta 선정 경위 |
| [`GT_방법론_정리_20260812.md`](records/GT_방법론_정리_20260812.md) | 정답셋 방법론 |
| [`데이터셋_평가셋_수정내역_20260818.md`](records/데이터셋_평가셋_수정내역_20260818.md) | 평가셋 변경 이력 |

### 스프린트·보고

`SprintDemoV2_결과공유` · `SprintDemoV3_결과공유` · `QformSprintDemo_결과공유` ·
`Qform_ver4_최종보고` · `report_0810` · `phase3_milestone`

### Qform ver4 마일스톤 (8건 + 정리 4건)

`Qform_ver4_M0_recon` ~ `M7_scope_switch` · `M9_스팬이행_대조표` ·
`Qform_ver4_구현정리` · `Qform_ver4_문제점_분석` · `Qform_ver4_논의정리_0817_v4` ·
`Qform_v2_v3_변경요약`

### 설계·분석

`ARCH_통합_v0`(갭 G1~G13) · `anchor_develop` · `ANCHOR_구현_논의결과` ·
`앵커텍스트_정답라벨링_파이프라인` · `복잡도유형_도메인분석_v0` · `qform_조합테이블_착오송금_v0` ·
`Qform_ver3_task_assignment` · `QformSprintDemo_task_assignment`

### [`records/meeting/`](records/meeting/) — 회의록 16건

`2026-07-13` ~ `2026-08-12`. **08-12 이후는 없다** — 이후는 `logs/` 와 커밋 로그를 본다.

### [`records/handoff/`](records/handoff/) — 인계 3건

`eval_유상.md`(평가 트랙 인계) · `eval_TEMPLATE.md` · `README.md`

### [`records/진행도_2607/`](records/진행도_2607/) — 7월 원본·정리 19건

옛 `workflow/`·`workflow2/` 를 합친 것이다.

- **정리본 4건** — `정리_1_평가셋_라이프사이클` · `정리_2_검색_파이프라인_개선여정`(문제→원인→해결→선택 이유) ·
  `정리_3_이슈_트러블슈팅_원장` · `정리_4_첨부파이프라인_이식_doc-agg`
- **원본** — `진행도_*`(시간 도장 8건) · `CONTEXT.md` · `changelog_testset_eval.md` ·
  `context_0715_hw_자연어평가셋.md` · `통합_이슈_문제해결결과_20260715.md` ·
  `pair_triage_20260715.md` · `testset_paraphrase_pairs_20.md` · `embedding_space_pca.png`

---

## 이 디렉토리 밖의 문서

| 위치 | 무엇 |
|---|---|
| `../README.md` | 프로젝트 소개·구성·기술 스택 |
| `../SETUP.md` | 새 컴퓨터 설치 |
| `../DECISIONS.md` | 판단 로그 (D0~D13) — 코드가 왜 그 모양인가 |
| `../CONTRIBUTING.md` | 브랜치·커밋·PR 규칙 |
| `../logs/` | 데일리 스탠드업 23건 (07-13 ~ 08-20) |
| `../crawler/DECISIONS.md` · `../crawler/HOLES.md` | 파이프라인 판단 로그 · 미해결 홀 |
| `../crawler/README.md` · `../admin/README.md` | 각 축의 실행 안내 |
| `../archive/README.md` | 은퇴한 코드 19개와 은퇴 사유 |
