<!-- 상태:current -->
> **심사 절차 정본** — HCX·DeepSeek가 같은 검색 근거로 생성한 답변을 OpenCode의 한 모델로
> 블라인드 심사한다. P0는 2026-08-26 완료했고 DeepSeek 우세 신호를 확인했다. 운영 기본값은
> 변경하지 않았으며 P1 150문항은 미실행이다.

# HCX·DeepSeek 생성 후 OpenCode 단일 심사

## 구조

```text
같은 질문 + 같은 검색 컨텍스트
          ├─ 우리 코드 → HCX 답변
          └─ 우리 코드 → DeepSeek 답변
                         ↓
                  A/B 이름을 무작위로 가림
                         ↓
           고정된 OpenCode Judge가 문항별 심사
```

OpenCode의 공급자나 API를 HCX·DeepSeek로 바꾸지 않는다. 두 답변은 우리 코드가 각각 생성하고,
OpenCode는 모델 하나를 Judge로 고정해 비교만 한다. OpenCode 화면의 진행 에이전트 모델과 실제
Judge는 별개다. Judge 모델은 모든 호출에 `--model`로 명시하고 결과 메타데이터로 검증한다.

## P0 결과

- 생성: 40문항 × 2모델 × 3회 = 240답변, 오류 0건
- 최종 Judge: `upstage/solar-pro4`, reasoning medium, temperature 0
- 심사: 40문항 F1·F2 전수, 스키마 검증 80/80 통과
- 자기일치도: 0.80, F1·F2 총계 동일
- F1: DeepSeek 16승 / HCX 2승 / 동률 22
- 할루시네이션 판정: HCX 7/40, DeepSeek 0/40
- 지연 p50: HCX 3,254ms, DeepSeek 1,634ms

수치·정정·한계는
[`../records/HCX_DeepSeek_P0_결과_20260826.md`](../records/HCX_DeepSeek_P0_결과_20260826.md)에
보존한다. 이 결과는 P0 방향성이며 운영 기본값 전환 결정이 아니다.

## 1. 답변 생성

루트 `.env`에 HCX와 DeepSeek 설정이 모두 있어야 한다. `LLM_PROVIDER` 값은 비교 러너에 영향을
주지 않는다. 러너가 두 공급자를 명시적으로 각각 호출한다.

P0 재현:

```bash
.venv/bin/python chatbot/eval_answers.py \
  --n 40 --repeat 3 --seed 20260826 --overwrite
```

검색은 질문마다 한 번만 실행하며, 같은 `context_sha`의 컨텍스트를 두 모델에 전달한다.
산출물은 `chatbot/data/llm_compare/` 아래에 만들어지고 Git에는 포함되지 않는다.

- `run_manifest.json`: 데이터 해시·HEAD·시드·모델명·고정 파라미터
- `contexts.jsonl`: 문항별 검색 결과와 정확한 컨텍스트
- `answers.jsonl`: HCX·DeepSeek 반복 답변과 지연·오류

### P1 실행 전 중단 조건

현재 단순 `--n 150 --seed 20260826` 표본은 P0 40문항 중 37문항과 겹친다. 루브릭을 다듬는 데
사용한 P0 문항이 본채점에 다시 들어가지 않도록, P1 샘플러에 P0 제외 계약과 회귀 테스트를
추가하기 전에는 P1 생성을 실행하지 않는다.

P1은 다음 조건을 모두 만족해야 한다.

- P0 40문항과 교집합 0
- 업무 6종 각 20개 이상
- `chunk_relation=and` 25개 이상
- `cross_domain=true` 10개 이상
- `evidence_type=inferable` 10개 이상
- `answerable=false` 2개 전량
- P0와 다른 출력 디렉터리

## 2. 블라인드 입력 생성

여러 문항을 한 요청에 넣으면 유사한 A/B를 합치거나 문항 객체를 생략하는 사례가 있었다.
배치 크기는 이름과 달리 **항상 1문항**으로 고정한다.

```bash
.venv/bin/python chatbot/build_judge_batches.py \
  --batch-size 1 --repeat-idx 0 --seed 20260826 \
  --out-dir chatbot/data/llm_compare/judge_v3 --overwrite
```

- `batch_01.md`~`batch_40.md`: 모델명을 제거한 문항별 심사 입력
- `key.json`: A/B와 실제 모델의 대응표

`key.json`은 전체 심사와 스키마 검증이 끝날 때까지 열거나 Judge에 제공하지 않는다. P1에서는
A/B를 정확히 75:75로 균형 배정해야 하며, 이 기능을 구현·검증하기 전에는 P1 배치를 만들지 않는다.

## 3. Judge 고정

P0에서 검증한 고정값은 다음과 같다.

| 항목 | 값 |
|---|---|
| 모델 | `upstage/solar-pro4` |
| reasoning effort | `medium` |
| temperature | `0` |
| OpenCode | `1.18.18` |
| 에이전트 | `llm-judge` |

TUI에서 선택한 진행 모델을 바꿔도, 아래 호출에 지정한 Judge 모델은 바뀌지 않는다.

```bash
opencode run --title judge-01 --agent llm-judge \
  --model upstage/solar-pro4 \
  --variant medium \
  --file chatbot/data/llm_compare/judge_v3/batch_01.md \
  '첨부된 한 문항을 규칙대로 채점하고 길이 1인 JSON 배열만 출력해줘.'
```

각 문항은 새 세션에서 실행한다. 동적 무료 프리뷰 모델은 본채점 Judge로 쓰지 않는다.
P0에서 `opencode/x-preview-f-free`가 실행 중 레지스트리에서 사라졌고, 해당 결과는
`judge_v3/audit_oxalpha/`에 감사용으로만 보존했다.

## 4. 결과 검증

> §4 검증과 §5 해독을 자동으로 하는 스크립트는 저장소에 없다. 현재는 아래 항목을 사람이(또는 일회성
> 스크립트로) 확인하는 수동 절차다.

응답을 저장하기 전에 문항별로 다음을 검사한다.

- JSON 배열 길이 1
- 기대한 `item_id`가 정확히 한 번 존재
- A/B 채점 객체와 모든 점수 키 존재, 점수 0~3
- `corpus_defect_suspected`, `corpus_defect_note`, `verdict`, `verdict_reason` 존재
- `verdict`가 `A`, `B`, `tie` 중 하나
- 모델명이 Judge 입력이나 결과 판단 근거에 노출되지 않음

각 결과의 `.meta.json`에는 다음을 기록한다.

- 정확한 Judge 모델 ID와 reasoning effort
- OpenCode 버전과 실행 시각
- 루브릭 SHA-256과 입력 SHA-256
- 시드, `repeat_idx`, 시도 번호
- 스키마 검증 결과

모델·reasoning·루브릭 중 하나라도 바뀌면 이전 결과와 섞지 않고 해당 심사 패스를 처음부터
다시 실행한다. 최종 보고서는 F1을 정본 성적으로 쓰고 F2는 자기일치도 측정에만 사용한다.

## 5. 해독과 보고

모든 문항이 검증을 통과한 뒤에만 `key.json`을 사용해 A/B를 실제 모델로 해독한다. 집계는 다음을
포함한다.

- 승·패·동률과 축별 평균
- 할루시네이션·과거절·거절 정답률
- 업무·AND·교차업무·추론형 층별 결과
- 지연 p50·p95와 답변 길이
- A/B 위치별 승패 — 위치와 모델 매핑을 뒤집어 세지 않도록 회귀 테스트
- 코퍼스 결함 문항 별도 목록
- F1·F2 자기일치도
- P1에서는 Wilson 95% 신뢰구간·McNemar 검정·생성 3회 비결정성·`answer_checks` 탐지율

검색과 라우팅은 이 실험에서 고정한다. 결과는 생성 모델의 상대 비교이며 전체 RAG 파이프라인의
절대 품질로 인용하지 않는다.
