# 라우터 후보·지표 확장 핸드오프 (2026-08-04)

> 대상 파일: `crawler/train_router_electra (1).ipynb`
> 목적: 컴플라이언스 라우터(질의를 업무별 in-scope로 분류 + out-of-scope 탐지) 후보 모델 4종과
> 평가 지표 3종(LBR/AOC/ECE)을 추가(효율 지표 APGR은 추가했다가 삭제 — 아래 참고). 코드는 이미
> 노트북에 반영됨 — 이 문서는 그 내용의 근거·전제·한계와 다음 세션(사람 또는 다른 AI)이 이어받을
> 작업을 정리한 것.

## 배경

`train_router_electra (1).ipynb` 셀 0(마크다운)이 원래 `routing_model_review.md §7-3/8-3`을
"기존 지표 정의 출처"로 참조하고 있었으나, 해당 파일은 이 레포(현재 브랜치, git 전체 히스토리,
`crawler/4MATION` 중첩 레포 포함)에 존재하지 않는다. 확인 결과 노트북이 **실제로 계산하는** 지표만
"기존 지표"로 간주하고 진행하기로 함(사용자 확인 완료). 즉 아래 표의 "기존" 4종이 이 작업의
유일하게 검증된 베이스라인이며, `routing_model_review.md`의 다른 내용(있었다면)은 반영되지 않았다.

## 지표 8종 정리

### 기존 4종 — 노트북 셀 11(`evaluate_router`)이 이미 계산하던 것

| 지표 | 정의 | 계산 방식 | 좋은 방향 |
|---|---|---|---|
| **Accuracy** | in-scope 6-class 분류 정확도 | `accuracy_score(y_true, y_pred)`, is_oos=False & 라벨이 학습 LABELS에 있는 문항만 | ↑ |
| **Macro F1** | 6개 업무(class) 간 불균형을 보정한 F1 평균 | `f1_score(..., average='macro')` | ↑ |
| **MSP** (Maximum Softmax Probability) | 모델이 가장 높은 확률을 준 클래스의 softmax 값 — "확신도" | `softmax(logits).max(axis=-1)` | 지표라기보다 아래 AUROC/LBR/AOC/ECE의 원재료 |
| **AUROC (OOS 탐지)** | `score=1-MSP`로 in-scope vs OOS를 얼마나 잘 분리하는지. `G5b`(near-OOD, 어휘·주제가 애매하게 겹치는 경우)가 가장 어려운/중요한 케이스 | `roc_auc_score(is_oos, 1-msp)`, 전체 및 그룹(G5a far-OOD/G5b near-OOD)별 | ↑ |

### 신규 3종 — 이번에 추가(안전성 2 + 교정 1)

| 분류 | 지표 | 정의 | 계산 방식(노트북 구현) | 좋은 방향 |
|---|---|---|---|---|
| ① 안전성 | **LBR** (Legitimate-Block Rate) | 정상(in-scope) 질의인데 라우터가 잘못 차단(OOS 판정)한 비율. "과잉 차단"으로 인한 고객 피해를 측정 | `MSP < BLOCK_TAU`인 in-scope 문항의 비율 | ↓ |
| ① 안전성 | **AOC** (Abstain-On-Clean) | 정상 질의인데 차단까지는 아니지만 확신이 낮아 기권(사람 리뷰로 회부)하는 비율 | `BLOCK_TAU <= MSP < REVIEW_TAU`인 in-scope 문항의 비율 | ↓ (단, 0에 가까우면 오히려 "과신"일 수 있어 LBR과 함께 봐야 함) |
| ② 신뢰도 교정 | **ECE** (Expected Calibration Error) | 모델이 "90% 확신"이라고 말한 예측들이 실제로 90% 맞는지 — 확신도와 실제 정확도의 괴리 | 10-bin 표준 ECE: `Σ (bin 크기/전체) × \|bin 정확도 − bin 평균 confidence\|` | ↓ |

### ③ 라우팅 효율 지표 — 삭제됨(2026-08-04)

**APGR**(Average Performance Gap Recovered, 구 CPT)을 [RouteLLM](https://arxiv.org/abs/2406.18665) 정의로
구현했었으나, 사용자 판단으로 **통째로 삭제**했다. 이유: 계산에 문항별 GPT-4 정답 여부(`gpt4_correct`)가
반드시 필요한데 그 라벨을 만들 계획이 없어서, 있어봐야 매번 "skip" 메시지만 찍는 죽은 코드였다. 게다가
그 죽은 코드 안에 버그가 2건(§실행 검수 3·4번) 있었던 것도 확인됐다 — 고쳐서 남겨두는 대신 기능 자체를
들어냈다(`_trapz`/`average_performance_gap_recovered` 함수, `evaluate_router`의 `gpt4_correct` 매개변수와
(d) 효율 섹션 전부 삭제). 필요해지면(실제로 `gpt4_correct` 데이터가 생기면) 이 문서의 §실행 검수 3·4번에
적힌 수정 내역을 참고해 되살리면 된다.

## 실행 검수 (2026-08-04) — 로컬에서 실제로 돌려서 찾은 버그 6건

ELECTRA 5종(koelectra-base/small, kcelectra-base, kr-electra, dialog-koelectra)은 사용자가 실제 Colab에서
학습을 성공시킨 걸 확인했으므로 이번 검수 대상에서 제외했다. 그 외 나머지 코드(공용 파이프라인 + intentguard
+ deycoding-router 경로)는 로컬 환경(Python 3.12, transformers 5.13.1, torch 2.12.1, numpy 2.5.1,
scikit-learn 1.9.0, huggingface_hub 1.23.0, tokenizers 0.22.2)에 각 셀 코드를 그대로 추출해 합성 데이터로
실행하며 검수했다 — 코드를 눈으로 읽는 것만으로는 못 잡았을 실행 버그 6건을 실제로 재현하고 고쳤다.

| # | 버그 | 증상 | 재현 방법 | 수정 |
|---|---|---|---|---|
| 1 | `test_rows` 스코프 | `intentguard`/`deycoding-router` 선택 시 셀 5 가드가 (구)셀 6 진입 전에 멈춰서, 가드가 안내한 셀 12/13으로 바로 가면 `test_rows`가 없어 `NameError` | 셀 4·5·6을 합성 파일로 실제 실행, 세 loader 모두에서 `test_rows` 존재 여부 확인 | `test_rows` 로딩(+`load_jsonl` 헬퍼)을 가드보다 앞, 셀 5로 이동. 셀 6엔 `train_rows`/`val_rows`(hf_trainable 전용)만 남김 |
| 2 | pip 설치 순서 충돌 위험 | `transformers>=4.51.0`과 `intentguard`를 따로 설치하면, 리졸버가 두 번째 설치에서 조용히 transformers를 다운그레이드할 수 있음(intentguard가 구버전 transformers를 요구할 경우) | 코드 리뷰(HF PyPI 메타데이터 미확인이라 재현 대신 리스크로 판단) | 한 `pip install` 호출로 병합 — 리졸버가 두 제약을 동시에 풀거나 설치 시점에 바로 에러 |
| 3 | `np.trapz` 제거(NumPy 2.0) | `average_performance_gap_recovered` 호출 시 `AttributeError: module 'numpy' has no attribute 'trapz'` | 로컬 numpy 2.5.1로 `evaluate_router` 실행 → 즉시 크래시 재현 | (당시) 버전 무관한 사다리꼴 적분(`_trapz`) 직접 구현으로 교체 → **이후 APGR 기능 자체가 삭제되면서 이 함수도 같이 사라짐(아래 참고)** |
| 4 | APGR 오라클 기준선 수학 오류(2단계에 걸쳐 발견) | 이상적인 라우터를 합성 데이터로 만들어 넣어도 APGR≈0.51(1.0이어야 함), 1차 수정 후에도 무작위 4200개 지점 중 104개에서 "오라클 < 실제 라우터"라는 모순 발견 | 합성 데이터 단위 테스트 + 4200개 지점 전수 검사 | (당시) 오라클 곡선을 benefit 내림차순 3단계 정렬로 재수정, 위반 0건 확인 → **이후 APGR 기능 자체가 삭제되면서 이 로직도 같이 사라짐** |
| 5 | `DeycodingGuessNet` state_dict 접두어 불일치 | 아키텍처 추정이 실제로 100% 맞는 체크포인트를 넣어도 항상 "0% 일치"로 오판정 — `net.load_state_dict()`가 `self.encoder` 서브모듈 때문에 모든 키에 없는 `encoder.` 접두어를 기대함 | `BertModel`로 진짜 체크포인트를 만들어(`good.pt`) `net.load_state_dict()`에 넣어봄 → 39/41 텐서가 실제로는 같은데도 0/41 일치로 보고됨 | `net.load_state_dict(...)` 대신 `net.encoder.load_state_dict(...)`로 교체 — 재검증 결과 좋은 체크포인트 100% 일치, 나쁜 체크포인트 0% 일치로 정확히 구분됨(분류헤드는 원래 체크포인트에 없는 게 정상이라 집계 분모에서도 제외) |

**2026-08-04 추가 결정**: 위 3·4번 버그를 고친 직후, 사용자가 "APGR은 `gpt4_correct` 라벨이 영영 없을 거라
실행해도 항상 skip만 찍는 기능인데, 고쳐서 남겨두느니 통째로 버리자"고 판단했다. 버그를 고치는 것과 기능
자체의 존재 가치는 별개 문제라는 지적이 맞아서, `_trapz`/`average_performance_gap_recovered` 함수와
`evaluate_router`의 `gpt4_correct` 매개변수·(d) 효율 섹션을 전부 삭제했다(§지표 8종 정리의 "③ 라우팅 효율
지표 — 삭제됨" 참고). 3·4번 표 행은 "그 시점엔 이런 버그가 있었다"는 기록으로만 남긴다.

5번 버그(`DeycodingGuessNet` 접두어)는 여전히 살아있는 기능의 버그라 특히 중요하다 — 고치기 전에는
`evaluate_deycoding_router`가 "아키텍처 추정을 실제로 시도하고 결과를 숫자로 보여준다"는 원래 목적과 반대로,
**아키텍처를 얼마나 잘 맞혔든 상관없이 항상 실패로 보고하는 죽은 코드**였다.

## 모델 후보 9종 전수 검사 + loader 매핑 (2026-08-04)

**설계가 바뀌었다.** 처음엔 "표준 방식(`AutoModelForSequenceClassification`)이 안 맞는 후보는 뺀다"는 식으로 갔는데, 사용자가 "특이 케이스라고 넘어가지 말고 처음부터 그 케이스 전용 경로로 매핑하라"고 요청해서 구조를 바꿨다. 이제 `MODEL_CANDIDATES`(셀 5)는 9개 전부를 `{repo, loader, ...}` 형태로 갖고 있고, `loader` 값이 "이 후보를 어느 셀에서 어떻게 실행해야 하는가"를 명시한다 — 안 맞으면 나중에 빼는 게 아니라 처음부터 맞는 경로로 보낸다.

| loader | 대상 후보 | 실행 위치 | 의미 |
|---|---|---|---|
| `hf_trainable` | 7개(기존 5종 + `kf-deberta` + `moai-embedding`) | 셀 6~9 (Trainer 파인튜닝) | `AutoModelForSequenceClassification`으로 6-class 파인튜닝. 표준 경로 |
| `onnx_asis` | `intentguard` | 셀 12 (`evaluate_intentguard`) | ONNX 전용 배포라 파인튜닝 불가 — 공식 pip 패키지로 as-is 평가 |
| `custom_statedict` | `deycoding-router` | 셀 13 (`evaluate_deycoding_router`) | HF 표준 파일이 없는 raw state_dict — 모델카드 스펙으로 아키텍처를 추정해 로딩을 **실제로 시도**하고 텐서 일치율을 그대로 보고 |

**2026-08-04 후속 수정**: 처음엔 이 가드를 셀 9(모델 로딩)에만 뒀는데, 실제 Colab 실행에서 `intentguard`를 선택하니 셀 9에 도달하기도 전에 셀 8(토크나이저, `tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)`)이 먼저 `perfecXion/intentguard-legal`로 무조건 다운로드를 시도해서 `OSError: Can't load tokenizer for 'perfecXion/intentguard-legal'`가 났다(그 저장소는 토크나이저 파일이 `tokenizer/` 서브폴더 안에 있어 루트에서 못 찾음). 근본 원인은 "가드가 있어야 할 가장 이른 지점에 없었다"는 것 — 대응으로 가드를 **셀 5(설정, `MODEL_NAME`이 확정되는 가장 이른 지점)로 옮기고 셀 9의 중복 가드는 제거**했다. 이제 `SELECTED_MODEL_KEY`를 바꾸고 셀 5만 실행해도 즉시 알 수 있고, 이후 어떤 셀도(토크나이저든 모델이든) 잘못된 후보로 시도되지 않는다.

전수 검사 근거(HF API로 각 저장소 파일 목록·config 직접 확인):

| 후보 | 저장소 | loader | 근거 |
|---|---|---|---|
| koelectra-base | monologg/koelectra-base-v3-discriminator | `hf_trainable` | `pytorch_model.bin` 있음. `ElectraForPreTraining` 백본 — 분류헤드는 원래 없고 새로 학습됨(정상 동작 방식) |
| koelectra-small | monologg/koelectra-small-v3-discriminator | `hf_trainable` | 위와 동일 패턴 |
| kcelectra-base | beomi/KcELECTRA-base-v2022 | `hf_trainable` | 위와 동일 패턴(사용자가 기존에 실제로 학습 성공시킨 후보) |
| kr-electra | snunlp/KR-ELECTRA-discriminator | `hf_trainable` | 위와 동일 패턴 |
| dialog-koelectra | skplanet/dialog-koelectra-small-discriminator | `hf_trainable` | 위와 동일 패턴 |
| kf-deberta | kakaobank/kf-deberta-base | `hf_trainable` | `pytorch_model.bin` 있음. `DebertaV2ForMaskedLM` 백본 — 위 5종과 동일한 "백본 재사용, 분류헤드 새로 학습" 패턴 |
| moai-embedding | BCCard/MoAI-Embedding-0.6B | `hf_trainable` | `model.safetensors` 있으나 아키텍처가 `Qwen3Model`(디코더 전용 0.6B). `transformers==4.44.2`는 Qwen3를 아예 모른다(4.51.0부터 지원) → 셀 1에서 버전 상향. Qwen 토크나이저 기본 pad_token 없음 → 셀 8/9에서 pad_token·config.pad_token_id 보강. 그래도 `hf_trainable` 경로 그대로 통과(별도 loader 불필요) — 나머지 후보보다 훨씬 크고(0.6B) 느려 Colab 무료 GPU에서 8 epoch 완주 안 될 수 있음(미실행, 리스크만 표시) |
| intentguard | perfecXion/intentguard-legal | `onnx_asis` | `pytorch_model.bin`/`model.safetensors` 자체가 없음(config.json/model.onnx/model_fp32.onnx.data/tokenizer/*만 존재). 공식 README도 파인튜닝이 아닌 as-is 사용(3-class allow/deny/abstain)을 명시 |
| deycoding-router | deycoding/deycoding-compliance-classifier-router | `custom_statedict` | `config.json`/`pytorch_model.bin`/`model.safetensors` 전부 없음 — 커스텀 `.pt` state_dict(가중치만) + 자체 BPE 토크나이저 json뿐, 원본 인코더 클래스 정의는 어디에도 공개 안 됨. 모델카드 스펙(12층/hidden 768/head 12/vocab 32K, BERT-base 형태)으로 최선 추정 아키텍처를 만들어 `load_state_dict(strict=False)`를 시도하고 missing/unexpected 텐서 수를 그대로 출력 — 절반 미만 일치 시 "무작위 가중치 평가는 의미 없음"이라고 명시하고 중단(§전제 6 참고) |

## 반영 위치 (노트북)

- **셀 0** (마크다운): 4~6번 항목 — loader 매핑 개요, 전수 검사 결과 요약, 이 문서로 링크.
- **셀 1** (pip install): `transformers==4.44.2` 고정 해제 → `transformers>=4.51.0`(moai-embedding/Qwen3 지원) + `intentguard` 패키지 설치(셀 12 전용). `huggingface_hub`/`tokenizers`/`torch`는 이미 transformers 의존성으로 설치돼 있어(셀 13용) 별도 추가 없음.
- **셀 5** (`MODEL_CANDIDATES`): dict-of-dicts로 재구성, 9개 전부에 `loader` 필드 부여. `MODEL_NAME = _candidate["repo"]`로 변경. **loader 가드도 여기로 이동**(`hf_trainable`이 아니면 이 셀에서 바로 중단 + 올바른 셀 안내) — 셀 9에 있던 걸 옮긴 것, 아래 §전제 참고.
- **셀 8** (토크나이저): `tokenizer.pad_token`이 없으면 `eos_token`으로 채우는 방어 코드(moai-embedding 전용, 다른 후보는 영향 없음).
- **셀 9** (모델 로딩): loader 가드는 셀 5로 이동했으므로 여기선 제거(중복 없음). `ignore_mismatched_sizes=True` + `OSError` 안내 메시지 + `model.config.pad_token_id = tokenizer.pad_token_id`는 그대로.
- **셀 11** (`evaluate_router` 및 헬퍼): `expected_calibration_error`/`legitimate_block_rate`/`abstain_on_clean` 3개 함수 추가, `evaluate_router()` 내부에 (c) 안전성 섹션으로 출력 연결. (효율 지표 `average_performance_gap_recovered`/`_trapz`는 한 번 추가했다가 §실행 검수에서 다룬 이유로 2026-08-04에 다시 삭제했다.)
- **셀 12 (`evaluate_intentguard`)**: `perfecXion/intentguard-legal`을 공식 `intentguard` pip 패키지로 as-is 실행 — 파인튜닝 없이 네이티브 allow/deny/abstain 출력을 그대로 LBR/AOC 계산에 사용. `vertical`은 `MODEL_CANDIDATES["intentguard"]["vertical"]`에서 가져옴.
- **셀 13 (신규, `evaluate_deycoding_router`)**: 모델카드 스펙 기반 `DeycodingGuessNet`(BERT-base + 6-class 헤드)을 구성해 `hf_hub_download`로 받은 state_dict 로딩을 시도, 텐서 일치율 보고 후 절반 이상 맞으면 as-is 스모크 테스트(forward shape 확인)까지 수행.
- **셀 15** (마크다운, 구 셀 13/14): "다음에 할 일"을 loader 매핑 구조에 맞춰 갱신.

## 전제와 한계 (반드시 읽을 것)

1. **LBR/AOC는 근사치다.** 현재 테스트셋(`testset_router_oos_1150.jsonl`, 아직 레포에 파일 자체가 없음 — 노트북에서도 "선택" 취급)의 `is_oos`는 "주제 범위 밖(6개 업무 어디에도 안 속함)"을 뜻하지, "컴플라이언스 위반/금지 발화"를 뜻하지 않는다. 진짜 LBR/AOC(과잉 차단으로 인한 안전성 리스크)를 측정하려면 **위반 여부가 라벨된 red-team/컴플라이언스 테스트셋**이 별도로 필요하다. 지금 구현은 그 데이터가 생기기 전까지 "주제 범위 이탈"을 대리 지표로 쓴다. `evaluate_intentguard`도 legal 버티컬이라 법률 외 업무엔 참고용 수치일 뿐이다.
2. **`BLOCK_TAU=0.5`, `REVIEW_TAU=0.8`은 자리표시자다.** 실제 서비스 목표(예: "LBR ≤ 1%") 기준으로 검증셋에서 역산해 재보정해야 한다.
3. **transformers 버전 상향(`>=4.51.0`)은 이 세션에서 실행 검증되지 않았다.** `build_training_args()`의 기존 try/except(eval_strategy/evaluation_strategy)가 버전차를 방어하도록 설계돼 있어 안전할 것으로 판단했으나, 실제 Colab 실행으로 확인 필요.
4. **`kf-deberta`/`moai-embedding`은 파일 존재·아키텍처만 확인했고 실제 Colab 실행은 안 해봤다.** 특히 moai-embedding은 0.6B라 실행 시간/메모리 리스크가 있다.
5. **`deycoding-router`의 `custom_statedict` 로딩은 "추정이 맞을 것"이라는 보장이 전혀 없다.** 모델카드에 적힌 스펙(12층/hidden 768/head 12/32K vocab)만으로 BERT-base 형태를 구성했을 뿐, 원본이 실제로 HF `BertModel`과 같은 레이어 명명 규칙(`encoder.layer.N.attention.self.query.weight` 등)을 쓴다는 근거는 없다 — 오히려 커스텀 학습 스크립트일 가능성이 높아 텐서 이름이 안 맞을 확률이 상당하다. 셀 13은 이걸 숨기지 않고 `missing_keys`/`unexpected_keys` 개수를 그대로 출력해서, 맞았는지 틀렸는지 실행 결과로 바로 판단할 수 있게만 해준다 — 로딩 성공을 미리 보장하지 않는다. `torch.load(..., weights_only=True)`로 로드하므로(보안 훅 권고 반영) 만약 파일이 순수 state_dict가 아니라면(예: 학습 스크립트 전체를 pickle) 여기서 에러가 나는 것도 정상이다.

## 다음 세션 TODO (우선순위순)

1. 셀 9까지 7개 `hf_trainable` 후보 실행해 실제 로딩·학습 성공 여부 확인(특히 moai-embedding, transformers 버전 상향 영향), 셀 12로 `intentguard` as-is 결과 확인, **셀 13으로 `deycoding-router` 아키텍처 추정 일치율 확인**(가장 불확실한 부분이라 우선순위 높음). 로직 자체는 로컬에서 합성 데이터로 검증 완료(§실행 검수)했지만, 실제 HF 저장소 다운로드·GPU 학습까지 거치는 진짜 Colab 실행은 아직 안 해봤다.
2. 셀 13의 텐서 일치율이 낮게 나오면(추정 실패) 배포자(Abhishek Dey)에게 인코더 아키텍처 정의 코드를 직접 요청하거나, 라이선스(CC-BY-NC-4.0, 비상업 전용) 문제도 있으니 애초에 포기하는 것도 선택지.
3. 컴플라이언스 위반 라벨이 있는 별도 테스트셋 확보 → LBR/AOC를 근사치가 아닌 실측치로 전환.
4. `BLOCK_TAU`/`REVIEW_TAU`를 검증셋 기준으로 재보정.
5. (선택) `routing_model_review.md`가 실제로 어딘가에 존재한다면 찾아서 이 문서와 대조 — 기존에 다른 지표 정의가 있었다면 여기 표를 갱신.
