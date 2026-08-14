# KDIC 검색 평가 리포트 v3

## 1. 개요

청크 단위 검색 평가 — gold `chunk_id`를 직접 비교해 기존 `parent_doc_id` 기준 평가가
안고 있던 '같은 문서면 적중' 거품을 배제하고 실제 청크 적중률을 측정한다.

## 2. 평가 대상 / 데이터 구성

- GT 라벨: `C:\Users\twink\4MATION\crawler\data\gt_relabeled_v7.jsonl`
- 전체 30건 · 평가 대상(answerable=true) 26건 · 제외(answerable=false) 4건 · 라벨 불일치 0건

| relation | 문항수 |
|---|---:|
| single | 26 (100.0%) |

## 3. 실험 파라미터

- Corpus: 215개 청크 (`chunks.jsonl`)
- Retriever: RRF(k=5, alpha=0.6) + BF_MODE=soft(cap=5)
- Embedding: dragonkue/BGE-m3-ko
- 검색 단위: chunk (기존 parent_doc_id 평가와 별도)
- 검색 소스: `rag.Searcher.search(question, k=10, mode='hybrid_bf_rerank')`
- Top-K: 10

## 4. 평가 지표 및 판정 기준

- Hit@1/3/5/10: Top-K 안에 gold가 relation 조건을 만족하며 존재하는지 (분모: 평가 대상 문항수).
- Macro Recall@3/5/10: 문항별 recall(Top-K에서 회수한 gold 비율)의 문항 평균. 주지표.
- (참고) Micro Recall@3/5/10: 전체 gold occurrence 기준 합산 recall. 문항당 gold 개수가 많을수록 가중치가 커짐 — 보조지표로만 사용.
- Gold Coverage: 전체 gold chunk occurrence 중 Top-10에서 회수되지 못한 비율(`missing_gold@10`).
- MRR: relation 조건을 만족하는 gold가 처음 나온 순위의 역수, Top-10까지만 본다(MRR@10).
- relation 판정: `single`/`or`는 ANY(하나만 맞아도 적중), `and`는 ALL(전부 맞아야 적중); null/누락은 single.
- answerable=false 문항은 Hit@K·Recall@K·MRR 분모에서 제외.

## 5. 전체 평가 결과

| Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |
|---:|---:|---:|---:|---:|
| 0.308 | 0.577 | 0.692 | 0.923 | 0.476 |

| MacroRecall@3 | MacroRecall@5 | MacroRecall@10 |
|---:|---:|---:|
| 0.577 | 0.692 | 0.923 |

- (참고) Micro Recall@10: 0.923 · gold 총계(occurrence): 26 · 미회수(@10): 2

## 6. Relation별 결과

| relation | 문항수 | Hit@1 | Hit@3 | Hit@5 | MacroRecall@10 | MRR |
|---|---:|---:|---:|---:|---:|---:|
| single | 26 | 0.308 | 0.577 | 0.692 | 0.923 | 0.476 |

## 7. 도메인별 결과

| 업무 | 문항수 | Hit@1 | Hit@3 | Hit@5 | MacroRecall@10 | MRR |
|---|---:|---:|---:|---:|---:|---:|
| 예금자보호제도 | 26 | 0.308 | 0.577 | 0.692 | 0.923 | 0.476 |

## 8. 오류 분석

- 미적중(top-3 밖) 11건 / 평가 대상 26건 (42.3%)

### 8-1. 미적중 원인 분포

정분류: gt 업무 청크가 top-3 안에 있으나 순위/청킹 문제로 놓침. 오분류: top-3 전부 다른 업무 청크로 채워짐. (업무 분류기가 적용됐는지까지는 이 표만으로 알 수 없음 — 세부 조사는 수작업 검토 필요.)

| 원인 | 건수 |
|---|---:|
| 정분류(업무 내 랭킹·청킹) | 11 (100.0%) |

### 8-2. 업무별 미적중

| 업무 | 문항수 | 미적중 | 미적중률 |
|---|---:|---:|---:|
| 예금자보호제도 | 26 | 11 | 42.3% |

### 8-3. 혼입 문서 랭킹 (미적중 top-3를 잠식한 다른 업무 청크)

| 청크 ID | 출현 | 업무 |
|---|---:|---|
| `kdic-fins-cm-bbs-selectFaqNramtAply#28` | 1 | 예금보험금 안내 |
| `kdic-fins-cm-bbs-selectFaqNramtAply#12` | 1 | 예금보험금 안내 |
| `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#01` | 1 | 예금보험금 안내 |

### 8-4. 업무 간 혼입 흐름 (정답 업무 → top-1 업무)

| 정답 업무 | → top-1 업무 | 건수 |
|---|---|---:|
| 예금자보호제도 | 예금보험금 안내 | 1 |

### 8-5. 대표 실패 사례 (gold가 top-10에도 없음)

- **[예금자보호제도] train-PROT-006** — 신협 조합원이 아니어도 예금자보호를 받을 수 있나요?
  - gold: `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#09`
  - top-3: `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#02`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#02`
- **[예금자보호제도] train-PROT-011** — 부부 공동명의 통장은 보호한도 계산이 어떻게 되나요?
  - gold: `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#10`
  - top-3: `kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#00`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#28`

## 9. 개선 우선순위

1. '예금자보호제도' 업무 — 미적중 11/26건(42.3%)로 가장 취약함
2. `kdic-fins-cm-bbs-selectFaqNramtAply#28` 청크가 미적중 1건에서 top-3를 잠식 — 업무 분류/부스트 파라미터 재검토 대상 1순위

## 10. 참고

기존 document-level(같은 `parent_doc_id`면 적중) 판정과 비교한 거품(percentage points):

| 지표 | chunk-level | document-level | 문서 단위 거품 |
|---|---:|---:|---:|
| hit@1 | 0.308 | 0.577 | +26.9pp |
| hit@3 | 0.577 | 1.000 | +42.3pp |
| hit@5 | 0.692 | 1.000 | +30.8pp |
| recall@10 | 0.923 | 1.000 | +7.7pp |
| mrr | 0.476 | 0.756 | +28.1pp |

## 부록. 문항별 라벨과 검색 청크

| id | answerable | relation | gold chunk IDs | Top-10 retrieved chunk IDs | chunk Hit@1/3/5/10 | doc Hit@1/3/5/10 |
|---|---|---|---|---|---|---|
| train-PROT-001 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#09` | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#05`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#08`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#12`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#05`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#08`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#09` | 0/0/0/1 | 1/1/1/1 |
| train-PROT-002 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#09` | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#08`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#10`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#11`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#05`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#09`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#09`<br>`kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn#02` | 0/0/0/1 | 1/1/1/1 |
| train-PROT-003 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#10` | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#09`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#10`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn#00`<br>`kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn#00`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#28`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#00` | 0/1/1/1 | 1/1/1/1 |
| train-PROT-004 | true | single | `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01` | `kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#08`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#02`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#05`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#09`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#02`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04` | 0/0/0/1 | 0/1/1/1 |
| train-PROT-005 | true | single | `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01` | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#08`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#02`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#05`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#28`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#09`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01` | 0/0/0/1 | 0/1/1/1 |
| train-PROT-006 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#09` | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#02`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#02`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#09`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#12` | 0/0/0/0 | 1/1/1/1 |
| train-PROT-007 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02` | `kdic-www-sp-dpstrprot-selectProtSystProtSumr#02`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#07`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn#11`<br>`kdic-www-sp-kmrs-kmrsItrdProc-selectScrn#00`<br>`kdic-fins-cm-bbs-selectFaqCncmPrptDclr#00`<br>`kdic-www-sp-dpstrprot-ProtSyst-selectScrn#00`<br>`kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn#02`<br>`kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn#00` | 0/1/1/1 | 0/1/1/1 |
| train-PROT-008 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#00` | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#01`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#08`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#15`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#11`<br>`kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#07`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn#00` | 1/1/1/1 | 1/1/1/1 |
| train-PROT-009 | true | single | `kdic-fins-cm-bbs-selectFaqNramtAply#03` | `kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#16`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#28`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#25`<br>`kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#11`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#00`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#19` | 1/1/1/1 | 1/1/1/1 |
| train-PROT-010 | false | single | - | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#08`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#09`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#12`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#28`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#11`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#00` | excluded | excluded |
| train-PROT-011 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#10` | `kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#00`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#28`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#16`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#11`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#37`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#08`<br>`kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#01` | 0/0/0/0 | 0/1/1/1 |
| train-PROT-012 | false | single | - | `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#08`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#03`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#05`<br>`kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn#00` | excluded | excluded |
| train-PROT-013 | true | single | `kdic-fins-cm-bbs-selectFaqNramtAply#02` | `kdic-fins-cm-bbs-selectFaqNramtAply#02`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#08`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#04`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#08`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#05`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02` | 1/1/1/1 | 1/1/1/1 |
| train-PROT-014 | false | single | - | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#10`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#02`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#04`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#12`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#02` | excluded | excluded |
| train-PROT-015 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#05` | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#05`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#11`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#00`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#08`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#01` | 1/1/1/1 | 1/1/1/1 |
| train-PROT-016 | true | single | `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#00` | `kdic-fins-cm-bbs-selectFaqNramtAply#12`<br>`kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#07`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#28`<br>`kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#00`<br>`kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn#00`<br>`kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn#00`<br>`kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#15` | 0/0/1/1 | 0/1/1/1 |
| train-PROT-017 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#06` | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#06`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#07`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#15`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#11`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#14`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#09`<br>`kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#01`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#03` | 1/1/1/1 | 1/1/1/1 |
| train-PROT-018 | true | single | `kdic-www-sp-dpstrprot-ProtSyst-selectScrn#00` | `kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSyst-selectScrn#00`<br>`kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#01`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#33`<br>`kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#00`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#25`<br>`kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn#01`<br>`kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#02`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#14`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#13` | 0/1/1/1 | 0/1/1/1 |
| train-PROT-019 | true | single | `kdic-www-sp-dpstrprot-ProtSyst-selectScrn#00` | `kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00`<br>`kdic-fins-ir-aplygudn-MtrsRelLawoRgul-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSyst-selectScrn#00`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#09`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#07`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn#00`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#05`<br>`kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#02` | 0/1/1/1 | 0/1/1/1 |
| train-PROT-020 | true | single | `kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn#01` | `kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn#01`<br>`kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn#03`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#15`<br>`kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn#05`<br>`kdic-fins-cm-bbs-selectFaqCncmPrptDclr#06`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#03`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02`<br>`kdic-fins-cm-bbs-selectFaqLbltInfoInq#05` | 0/1/1/1 | 1/1/1/1 |
| train-PROT-021 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#04` | `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#02`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#10`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#04`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#05`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#08`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#09`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#03`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#01` | 0/1/1/1 | 0/1/1/1 |
| train-PROT-022 | true | single | `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#07` | `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#07`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#04`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#04`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#09`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#10`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#03`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#02`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#00` | 1/1/1/1 | 1/1/1/1 |
| train-PROT-023 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#04` | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#04`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#07`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#04`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#00`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#02`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#02`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#08` | 1/1/1/1 | 1/1/1/1 |
| train-PROT-024 | true | single | `kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn#00` | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#08`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#04`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#03`<br>`kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn#00`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#00`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#05` | 0/0/0/1 | 0/1/1/1 |
| train-PROT-025 | true | single | `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#02` | `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#04`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#02`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#08`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#05`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#03` | 0/0/1/1 | 1/1/1/1 |
| train-PROT-026 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03` | `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#02`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#09`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#08`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#02`<br>`kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01` | 0/0/0/1 | 0/1/1/1 |
| train-PROT-027 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#16` | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#16`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#10`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#08`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#09`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#11`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#28`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#08`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01` | 1/1/1/1 | 1/1/1/1 |
| train-PROT-028 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02` | `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#02`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02`<br>`kdic-fins-cm-bbs-selectFaqTop10#03`<br>`kdic-fins-cm-bbs-selectFaqMsdrGvbkAply#09`<br>`kdic-www-sp-dpstrprot-selectProtSystProtSumr#00`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#08`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#02`<br>`kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn#00`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#07` | 0/1/1/1 | 0/1/1/1 |
| train-PROT-029 | false | single | - | `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#09`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#08`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#05`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-ProtSyst-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00`<br>`kdic-fins-ir-aplygudn-MtrsRelLawoRgul-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#11` | excluded | excluded |
| train-PROT-030 | true | single | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#11` | `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#10`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#16`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#11`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#28`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#01`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#08`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#03`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#04` | 0/0/1/1 | 1/1/1/1 |
