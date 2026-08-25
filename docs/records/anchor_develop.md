<!-- 상태:records -->
> **기록** — 2026-08-25 시점의 사실. 고치지 않는다(정정은 추기로)
> 문서 지도: `docs/README.md`(문서 지도) · `docs/프로젝트_전체흐름.md`(전체 그림·용어 해설)

---


````markdown
# 앵커텍스트 기반 RAG 검색 정확도 개선
2026-08-10 박유상
## 1. 목표

앵커텍스트(기관명, 제도명, 문서명, 행위, 대상 등)를 질의 분석 단계에서 추출하고, 이를 검색 및 재정렬 과정의 독립적인 검색 신호로 활용하여 RAG 검색 정확도를 높인다.

단순히 임베딩 모델이나 `top_k`만 조정하기보다는 다음과 같이 검색 파이프라인 자체를 개선하는 것을 목표로 한다.

```text
Query
  ↓
Anchor Extraction
  ↓
Anchor Type / Importance 분석
  ↓
Hybrid Retrieval
  ↓
Anchor-aware Scoring
  ↓
Conflict Penalty
  ↓
Reranking
  ↓
Top-K
````

---

## 2. Anchor Weight 조정

앵커와 일반 질의의 검색 신호에 서로 다른 가중치를 부여한다.

예:

```text
final_score =
    0.40 * anchor_exact_match
  + 0.25 * anchor_bm25
  + 0.20 * dense_similarity
  + 0.15 * metadata_match
```

### 조정 대상

* Anchor exact match weight
* Anchor lexical/BM25 weight
* Dense similarity weight
* Metadata match weight

기관명, 제도명, 서류명처럼 고유명사 성격이 강한 앵커는 Dense보다 lexical/exact match의 비중을 높이는 방향을 우선 실험한다.

---

## 3. Anchor Type별 검색 전략

모든 앵커를 동일한 검색 방식으로 처리할 필요는 없다.

| Anchor Type | 권장 검색 방식     |
| ----------- | ------------ |
| 기관명         | Exact / BM25 |
| 제도명         | BM25 + Dense |
| 서류명         | Exact / BM25 |
| 질문 의도       | Dense        |
| 행위          | Dense        |
| 숫자 / 기간     | Exact        |
| 법률 / 규정 용어  | BM25         |

예:

```text
기관 = 예금보험공사
→ Exact / BM25

업무 = 채무조정
→ BM25 + Dense

행위 = 신청
→ Dense

문서요소 = 소득증빙서류
→ Exact / BM25
```

이를 `Anchor Type별 Retrieval Policy`로 관리할 수 있다.

---

## 4. Anchor Query Expansion

앵커의 동의어와 표현 변형을 생성하여 검색 범위를 보완한다.

예:

```text
채무조정
├── 채무 조정
├── 신용회복
├── 상환조건 변경
├── 채무조정 신청
└── 채무조정제도
```

검색 시 다음을 각각 활용할 수 있다.

```text
원문 질의
앵커
앵커 확장어
```

각 검색 결과를 합쳐 최종 후보를 생성한다.

### 주요 파라미터

```text
expansion_count
expansion_weight
```

초기 실험에서는 확장어를 1~3개 수준으로 제한하고 precision 저하 여부를 확인한다.

확장어를 과도하게 생성하면 검색 범위는 넓어지지만 관련 없는 문서가 증가할 수 있으므로 Recall과 Precision을 함께 확인해야 한다.

---

## 5. Anchor-aware Hybrid Search

단순히

```text
BM25 score + Dense score
```

를 계산하기보다 각 검색 방식에서 후보를 가져온 뒤 Fusion하는 구조를 사용한다.

```text
                    ┌─ BM25
Query → Anchor ─────┼─ Dense
                    └─ Exact
                         ↓
                       Fusion
```

### RRF

BM25와 Dense score의 스케일이 서로 다르기 때문에 초기 실험에서는 RRF를 사용하는 것이 편리하다.

```text
RRF(d) = Σ 1 / (k + rank_i(d))
```

### 주요 파라미터

* RRF `k`
* BM25 `top_k`
* Dense `top_k`
* Anchor `top_k`
* 최종 candidate 수

---

## 6. Anchor Coverage Score

검색 결과 Chunk가 질문의 핵심 앵커를 얼마나 포함하는지 별도의 점수로 계산한다.

예:

```text
anchors:
[
  "예금보험공사",
  "채무조정",
  "소득증빙서류"
]
```

검색된 Chunk가 세 가지 앵커를 모두 포함한다면 높은 점수를 부여한다.

```text
anchor_coverage =
    matched_anchors / total_important_anchors
```

최종 점수에 추가:

```text
final_score =
    α * dense_score
  + β * bm25_score
  + γ * anchor_coverage
```

단순 semantic similarity만으로는 유사하지만 다른 기관의 문서를 높은 순위에 올릴 수 있기 때문에, Anchor Coverage를 별도 feature로 사용하는 것이 중요하다.

---

## 7. Anchor Importance

앵커마다 중요도가 다르다는 점을 반영한다.

예:

```json
{
  "institution": {
    "text": "예금보험공사",
    "importance": 1.0
  },
  "service": {
    "text": "채무조정",
    "importance": 0.9
  },
  "document": {
    "text": "소득증빙서류",
    "importance": 1.0
  },
  "action": {
    "text": "신청",
    "importance": 0.5
  }
}
```

가중 Anchor Coverage:

```text
weighted_anchor_coverage =
    Σ(matched_anchor × importance)
    /
    Σ(importance)
```

예를 들어 `신청`보다 `소득증빙서류`가 누락된 경우 더 큰 penalty를 주도록 설계할 수 있다.

---

## 8. Negative Anchor / Conflict Penalty

공공기관 RAG에서는 특히 중요한 방법이다.

예를 들어 질문이

```text
예금보험공사의 채무조정
```

인데 검색 결과가

```text
신용회복위원회의 채무조정
```

이라면 두 기관의 업무가 유사하기 때문에 Dense similarity만 사용할 경우 높은 점수를 받을 수 있다.

따라서 질문의 기관 앵커가

```text
예금보험공사
```

일 때 Chunk에

```text
신용회복위원회
```

가 등장하면 penalty를 적용한다.

```text
final_score =
    retrieval_score
    + anchor_match_bonus
    - conflict_penalty
```

특히 다음과 같이 유사한 entity가 많은 데이터셋에서 효과가 클 가능성이 높다.

* 기관명
* 제도명
* 상품명
* 서비스명
* 법령명

---

## 9. Chunk Metadata에 Anchor 정보 저장

검색 단계에서 매번 문서 전체를 분석하지 않고, Indexing 단계에서 Anchor Metadata를 미리 저장한다.

예:

```json
{
  "chunk_id": "1234",
  "text": "...",
  "institution": ["예금보험공사"],
  "service": ["채무조정"],
  "document": ["소득증빙자료"],
  "keywords": ["신청", "서류"],
  "parent_document": "채무조정 안내"
}
```

검색 구조:

```text
Query
 ↓
Anchor Extraction
 ↓
Metadata Filtering
 ↓
BM25 + Dense Retrieval
 ↓
Reranking
```

### Hard Filter와 Soft Boost 구분

모든 Metadata를 Hard Filter로 사용하면 Recall이 떨어질 수 있으므로 entity별로 다르게 적용한다.

예:

```text
기관명 → Hard Filter 또는 강한 Boost
제도명 → Soft Boost
행위 → Soft Boost
키워드 → Soft Boost
```

데이터 특성에 따라 Hard Filter와 Soft Boost를 비교 실험한다.

---

## 10. Reranker에 Anchor Feature 추가

일반적인 Reranker:

```text
Query
Chunk
 ↓
Cross Encoder
 ↓
Relevance Score
```

를 다음과 같이 확장한다.

```text
Query
Chunk
Anchor 정보
 ↓
Reranker
 ↓
Relevance Score
```

활용할 수 있는 Feature:

```text
dense_similarity
bm25_score
anchor_coverage
anchor_exact_match
metadata_match
institution_match
negative_anchor
```

초기에는 별도의 ML 모델을 학습시키기보다 가중합 방식으로 실험한다.

이후 충분한 학습 데이터가 확보되면 Learning-to-Rank로 확장할 수 있다.

예:

* LambdaMART
* XGBoost Ranker
* LightGBM Ranker

---

# 11. 추천 실험 순서

한 번에 여러 요소를 변경하지 않고 단계별 Ablation Test를 수행한다.

```text
Baseline
   │
   ├─ BM25
   ├─ Dense
   └─ Hybrid
        │
        ▼
① Anchor Coverage
        │
        ▼
② Anchor Type별 가중치
        │
        ▼
③ Metadata / Exact Match
        │
        ▼
④ Negative Anchor Penalty
        │
        ▼
⑤ RRF / Weighted Fusion 튜닝
        │
        ▼
⑥ Reranker
        │
        ▼
⑦ Learning-to-Rank
```

각 단계에서 이전 단계 대비 성능 변화를 측정한다.

---

# 12. 주요 실험 파라미터

| 파라미터                   | 실험 범위         |
| ---------------------- | ------------- |
| BM25 top-k             | 10 / 20 / 50  |
| Dense top-k            | 10 / 20 / 50  |
| Fusion k               | 20 / 50 / 100 |
| Anchor weight          | 0.1 ~ 0.5     |
| Dense weight           | 0.2 ~ 0.7     |
| Exact-match bonus      | 0.1 ~ 0.5     |
| Anchor coverage weight | 0.1 ~ 0.5     |
| Conflict penalty       | 0.1 ~ 0.5     |
| Reranker 후보 수          | 10 / 20 / 50  |
| 최종 반환 k                | 3 / 5 / 10    |
| Expansion count        | 1 / 2 / 3     |

위 값은 초기 탐색 범위이며, 실제 최적값은 평가셋을 통해 결정한다.

---

# 13. 평가 지표

단순 정확도 하나만 보는 것보다 Retrieval 단계의 오류를 분리한다.

## 기본 Retrieval Metric

* Recall@K
* Precision@K
* MRR@K
* nDCG@K

## Anchor 관련 Metric

```text
Anchor Hit Rate
Anchor Coverage
Institution Match Rate
Service Match Rate
Document Match Rate
Conflict Rate
```

예:

```text
Institution Match Rate
=
기관 앵커가 존재하는 질의 중
정답 Chunk의 기관이 일치하는 비율
```

---

# 14. Error Category

검색 실패를 유형별로 분류하면 어떤 부분을 개선해야 하는지 확인하기 쉽다.

| 오류 유형               | 원인 후보                       |
| ------------------- | --------------------------- |
| 기관 mismatch         | Lexical / Metadata 부족       |
| 제도 mismatch         | Entity 구분 부족                |
| 문서 mismatch         | Anchor Coverage 부족          |
| 의미는 유사하지만 오답        | Dense 과가중                   |
| 정확한 Entity인데 순위가 낮음 | BM25 / Exact Match 부족       |
| 관련 문서가 아예 없음        | Query Expansion / Recall 문제 |
| 유사 기관 문서가 상위 점유     | Conflict Penalty 부족         |

특히 공공기관 데이터에서는 `기관 mismatch`와 `제도 mismatch`를 별도로 관리하는 것이 중요하다.

---

# 15. 추천 최종 구조

현재 RAG 구조를 확장한다면 다음 형태를 우선 고려한다.

```text
                         ┌── BM25 Retrieval ─────┐
                         │                       │
Query                    ├── Dense Retrieval ────┤
 ↓                       │                       │
Anchor Extraction ───────┼── Exact Retrieval ────┤
 ↓                       │                       │
Anchor Type / Importance │                       ↓
 ↓                       └──────────────→ Candidate Fusion
                                                    ↓
                                             Anchor Coverage
                                                    ↓
                                             Conflict Penalty
                                                    ↓
                                               Reranker
                                                    ↓
                                                 Top-K
```

핵심은 **Anchor를 단순히 검색어에 추가하는 것이 아니라 Retrieval → Scoring → Reranking 전 과정에서 별도의 Feature로 사용하는 것**이다.

---

# 16. 우선순위

구현 우선순위는 다음과 같이 잡을 수 있다.

### 1순위 — Anchor Coverage

가장 먼저 적용한다.

```text
anchor_coverage
```

를 Retrieval Score에 추가하고 성능 변화를 확인한다.

### 2순위 — Exact / BM25 Boost

기관명, 제도명, 서류명 등 고유명사 Anchor에 높은 lexical weight를 적용한다.

### 3순위 — Anchor Type별 가중치

기관명, 제도명, 서류명, 행위 등에 서로 다른 검색 정책을 적용한다.

### 4순위 — Negative Anchor

잘못된 기관이나 제도에 대한 Conflict Penalty를 추가한다.

### 5순위 — RRF / Weighted Fusion

BM25, Dense, Exact 검색 결과를 Fusion한다.

### 6순위 — Anchor-aware Reranker

Reranker에 Anchor 관련 Feature를 추가한다.

### 7순위 — Learning-to-Rank

충분한 학습 데이터가 확보된 이후 Learning-to-Rank 모델로 확장한다.

---

# 17. 최종 Score 구조

초기 실험에서는 다음과 같은 구조를 Baseline으로 설정할 수 있다.

```text
final_score =
    α * dense_score
  + β * lexical_score
  + γ * anchor_coverage
  + δ * exact_match
  + ε * metadata_match
  - ζ * conflict_penalty
```

각 항을 하나씩 제거하는 Ablation Test를 수행한다.

예:

```text
Baseline
Baseline + Anchor Coverage
Baseline + Anchor Coverage + Exact Match
Baseline + Anchor Coverage + Exact Match + Conflict Penalty
Baseline + Reranker
```

이를 통해 어떤 Feature가 실제 성능 향상에 기여했는지 확인할 수 있다.

---

# 18. 핵심 결론

앵커텍스트 기반 정확도 개선의 핵심은 **앵커를 추출하는 것에서 끝내지 않고 검색 시스템의 독립적인 검색 신호로 취급하는 것**이다.

특히 공공기관 RAG에서는 의미적으로 유사하지만 기관이나 제도가 다른 문서를 걸러내는 것이 중요하므로 다음 세 가지를 우선 적용하는 것이 효과적이다.

```text
1. Anchor Coverage
2. Entity Exact / Lexical Match
3. Negative Anchor / Conflict Penalty
```

이후

```text
Hybrid Retrieval
→ RRF
→ Anchor-aware Reranker
→ Learning-to-Rank
```

순으로 확장한다.

최종적으로는 다음 구조를 목표로 한다.

```text
Query
 ↓
Anchor Extraction
 ↓
Anchor Type / Importance
 ↓
┌──────────────────────────────┐
│ BM25 + Dense + Exact Search  │
└──────────────────────────────┘
 ↓
Candidate Fusion
 ↓
Anchor Coverage
 ↓
Entity Match / Metadata Match
 ↓
Conflict Penalty
 ↓
Reranker
 ↓
Top-K
```

