# rerank_colab — bge-reranker-v2-m3 리랭킹 실험

Colab(GPU)에서 리랭커만 태우는 실험 환경. 검색은 로컬 프로덕션 경로에서 미리 굳혀
올리므로 Colab에서 임베딩·FAISS·BM25·라우터를 재현할 필요가 없다.

## 왜 지금 다시 하는가

이전 리랭커 실험(`crawler/eval_rerank.py`, `Dongjin-kr/ko-reranker`)은 개선이 거의
없었는데, 원인은 리랭커가 아니라 **판정 입도**였다. 그 실험은
`data/testset_natural_300_v3.jsonl`의 문서 단위(`parent_doc_id ∈ gt_docs`) 판정을 썼고,
그 기준에서는 애초에 여지가 없었다:

| 판정 입도 | hit@5 | hit@50 (천장) | 헤드룸 |
|---|---:|---:|---:|
| 문서(parent_doc_id) | .9767 | .9977 | **+.021** |
| 청크(chunk_id) | .8023 | .9209 | +.119 |
| **앵커텍스트** | **.8186** | **.9302** | **+.112** |

*(TEST 430셋 · `RRF_ALPHA=0.65 · RRF_K=1 · BF_BOOST=0.12 · FACET_BOOST=0.15 · BF_DOC_CAP=5`)*

문서 단위로는 2.1%p 여지밖에 없었다. 청크·앵커 단위로는 11~16%p가 있고, 리랭커가
잘하는 일(문서 안에서 맞는 청크 고르기)이 정확히 그 구간이다.

| 셋 | 건질 수 있음 (top-50엔 있고 top-5엔 없음) | pool에도 없음 (리랭커 무관) |
|---|---:|---:|
| TEST 430 | 48 / 430 (11.2%) | 30 (7.0%) |
| VAL 355 | 58 / 355 (16.3%) | 4 (1.1%) |

pool은 이미 충분히 좋다. **병목은 순서다.** 특히 앵커 hit@3이 .709인데 천장이 .930이라
22%p 갭 — 리랭커는 작은 k에서 가장 강하고, LLM 컨텍스트에 들어가는 건 top-3~5다.

부수적으로, 앵커 판정은 리랭커에게 복수 정답을 허용한다 — 430셋에서 top-50 안에
앵커를 만족하는 청크가 2개 이상인 문항이 88건(20.5%)이다. `chunk_id` 판정에서는
그중 정확히 하나만 정답으로 인정됐다.

**단, 정직하게**: 앵커 헤드룸(.112)은 chunk_id 헤드룸(.119)보다 오히려 약간 작다.
앵커 판정이 이미 k=5에서 더 높기 때문이다. 즉 "앵커로 바꿔서 리랭커 이득이 커졌다"가
아니라 **"문서 단위로 재던 것이 여지를 가리고 있었다"** 가 정확한 진단이다.

## 사용법

```bash
# 1) 로컬에서 입력 패키징 (검색 결과를 굳혀 zip 하나로)
cd crawler && python ../rerank_colab/prepare_inputs.py
#    → rerank_colab/rerank_inputs.zip (0.5MB)

# 2) Colab에서 bge_reranker_v2_m3.ipynb 열기
#    런타임 > 런타임 유형 변경 > GPU(T4 이상)
#    2번 셀에서 rerank_inputs.zip 업로드
```

zip 구성:

| 파일 | 내용 |
|---|---|
| `chunks.jsonl` | 청크 본문 — 리랭커 입력 + 앵커 판정용 |
| `gt_natural430.jsonl` | TEST (앵커 보유 430문항) |
| `gt_natural355.jsonl` | VAL (answerable 355문항) |
| `candidates_{430,355}.jsonl` | top-50 후보 + 검색 점수·순위 (블렌딩용) |
| `meta.json` | 검색 파라미터 + 베이스라인 지표 + `corpus_sha256` |

## torch를 업그레이드하지 말 것

노트북은 **아무것도 설치하지 않는다.** Colab은 torch와 torchvision을 버전 짝을 맞춰
깔아두는데, torch만 올리면 짝이 어긋나 transformers의 lazy import가 깨진다:

```
RuntimeError: operator torchvision::nms does not exist
→ ModuleNotFoundError: Could not import module 'XLMRobertaForSequenceClassification'
```

`bge-reranker-v2-m3`는 Colab 기본 torch/transformers로 그냥 돈다. 이미 깨진 세션이면
**런타임 > 세션 다시 시작**으로 기본 torch로 되돌린 뒤 처음부터 다시 실행한다.
1번 셀이 torch/torchvision 짝과 transformers 버전을 확인만 한다.

## 노트북 구성

| 셀 | 내용 |
|---|---|
| 0 | GPU 확인 |
| 1 | 환경 확인 (설치 없음, torch/torchvision 짝 점검) |
| 2 | 입력 업로드·해제 |
| 3 | **판정 로직** — `crawler/eval_anchor_v3.py`와 동일 규약 |
| 4 | **베이스라인 재현 + assert** — 통과해야 이후 수치를 믿을 수 있다 |
| 5 | 리랭커 로드 + 스모크 |
| 6 | top-50 전량 채점 → `rerank_scores.json` 캐시 |
| 7 | 스윕: depth × blend `w` × post-cap |
| 8 | 결과 다운로드 |

4번 셀은 로컬에서 미리 검증했다 — 430/355 × 앵커/chunk_id 4개 조합 전부
`meta.json` 기대값과 소수점 4자리까지 일치.

## 스윕 레버

- **depth** (10/20/30/50) — 상위 몇 개만 리랭크할지. depth 밖 후보는 원래 순서로 뒤에 붙는다.
- **blend `w`** (0/0.3/0.5/0.7/1.0) — `w × 리랭커z + (1-w) × 검색z`. 두 신호를 각각
  z-정규화해 스케일을 맞춘다(검색 점수는 RRF라 스케일이 다르다). `w=0`이면 원본 순서.
- **post_cap** (0/1/2/3) — 리랭킹 **뒤** 문서당 청크 수 제한. 이전 실험은 `CAP=1`이었는데
  과했을 수 있어 함께 스윕한다.

## 판정 시 주의

1. **한쪽 셋만 좋은 설정은 버린다.** 파라미터 튜닝에서 이미 겪었다 — TEST 단독 최적은
   VAL을 깎았고, VAL 단독 최적은 TEST를 베이스라인 아래로 떨어뜨렸다
   (`DECISIONS.md` 2026-08-14 ④). 노트북 7번 셀이 두 셋 min 기준 표를 함께 출력한다.
2. **`hit@50`은 리랭킹으로 변하지 않는다** — 집합은 그대로고 순서만 바뀐다. 천장을
   넘기려면 검색 단계를 손봐야 한다.
3. **두 셋의 절대 수치를 나란히 놓고 회귀를 판단하지 말 것.** VAL은 `and` 문항 0건,
   TEST는 `and` 55건이라 구성이 다르다. 각각의 시계열로만 본다.
4. 최적점이 스윕 **경계**(depth=50 · w=1.0 · cap=0 등)에 붙으면 범위를 넓혀 재실행.
   경계 접촉은 최적이 아니라 그리드가 좁다는 신호다.

## 로컬 재검증

`rerank_scores.json`을 이 폴더에 내려두면 GPU 없이 재평가·재스윕할 수 있다
(점수만 있으면 순서 재조합은 CPU로 즉시 끝난다). 채택 확정 시에는 리랭킹을
`rag.py` 검색 경로에 넣지 말고 별도 단계로 두는 편이 좋다 — `search()` 시그니처와
`eval_anchor_v3` 계약을 유지해야 지금까지의 수치 계보가 이어진다.

## 주의: 이 폴더는 git 미추적 상태로 두면 사라진다

`rerank_inputs.zip`은 재생성 가능하지만(`prepare_inputs.py`), 노트북·README는 아니다.
실제로 한 번 유실된 적이 있으므로 커밋해 둘 것. zip은 `.gitignore` 대상으로 빼도 된다.


---

## v2 (2026-08-18) — 표 원자성 수정 코퍼스에서 재측정

노트북: `bge_reranker_v2_m3_run2.ipynb` (v1은 `bge_reranker_v2_m3.ipynb`, 215청크 기준으로 보존)

| | v1 | v2 |
|---|---|---|
| 코퍼스 | 215청크 (최대 800자) | 181청크 (최대 2,613자) |
| 파라미터 | alpha .65 · rrf_k 1 · bf .12 · facet .15 | alpha .65 · rrf_k 4 · bf .06 · facet .05 |
| GT | 원본 | 앵커 보강판 |
| 베이스라인 hit@5 (실경로) | .8186 / .8254 | **.8907 / .8535** |

### 결과 요약 — 미채택 유지, top-1 조건부

- **hit@5**: TEST 최대 **+.0047**(16/48 config) · VAL 최대 **+.0563**(40/48). 두 셋 모두 양수인
  최선은 `(ml 1024, depth 30, w 0.2)` — TEST +.0047(2문항). 비용 정당화 미달
- **hit@1**: 두 셋 모두 오르는 config **40/48**. 최선 `(1024, 30, 0.7)`에서 TEST **+.0605** ·
  VAL **+.1127**. 단 같은 설정의 hit@5는 TEST −.0442 — **hit@1과 hit@5가 상충한다**
- **`max_length` 1024 무의미**: 평균 +.0021. 청크 최대 2,613자인데도 800자 초과가 3개뿐이라
  절단 대상이 적었다. **512로 충분**(시간 절반)
- **`and` 55건 무반응**: 어떤 config에서도 .7818 그대로. 표 원자성 수정이 이미 그 구간을 가져갔다
- **`post_cap` 무영향**: 0과 5가 전 구간 동일(K≤5에서 `BF_DOC_CAP`이 무효인 것과 같은 이유, H29)

상세는 `DECISIONS.md` 2026-08-18 ④. 원자료는 `rerank_scores_v2.json`(512/1024 × 2셋 × 785문항)과
`sweep_v2.json`(96 config). `analyze_rerank.py`로 GPU 없이 재분석·재스윕할 수 있다.
