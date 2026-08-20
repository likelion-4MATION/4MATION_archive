# KDIC 검색 평가 리포트 v3

## 1. 개요

청크 단위 검색 평가 — gold `chunk_id`를 직접 비교해 기존 `parent_doc_id` 기준 평가가
안고 있던 '같은 문서면 적중' 거품을 배제하고 실제 청크 적중률을 측정한다.

## 2. 평가 대상 / 데이터 구성

- GT 라벨: `data\gt_natural450_v9_dupfix2.jsonl`
- 전체 450건 · 평가 대상(answerable=true) 448건 · 제외(answerable=false) 2건 · 라벨 불일치 0건

| relation | 문항수 |
|---|---:|
| single | 374 (83.5%) |
| and | 69 (15.4%) |
| or | 5 (1.1%) |

## 3. 실험 파라미터

- Corpus: 185개 청크 (`chunks.jsonl`)
- Retriever: RRF(k=5, alpha=0.6) + BF_MODE=soft(cap=4)
- Embedding: dragonkue/BGE-m3-ko
- 검색 단위: chunk (기존 parent_doc_id 평가와 별도)
- 검색 소스: `rag.Searcher.search(question, k=30, mode='hybrid_bf')`
- Top-K: 30

## 4. 평가 지표 및 판정 기준

- Hit@1/3/5/10/30: Top-K 안에 gold가 relation 조건을 만족하며 존재하는지 (분모: 평가 대상 문항수).
- Macro Recall@3/5/10: 문항별 recall(Top-K에서 회수한 gold 비율)의 문항 평균. 주지표.
- (참고) Micro Recall@3/5/10: 전체 gold occurrence 기준 합산 recall. 문항당 gold 개수가 많을수록 가중치가 커짐 — 보조지표로만 사용.
- Gold Coverage: 전체 gold chunk occurrence 중 Top-10에서 회수되지 못한 비율(`missing_gold@10`).
- MRR: relation 조건을 만족하는 gold가 처음 나온 순위의 역수, Top-10까지만 본다(MRR@10).
- relation 판정: `single`/`or`는 ANY(하나만 맞아도 적중), `and`는 ALL(전부 맞아야 적중); null/누락은 single.
- answerable=false 문항은 Hit@K·Recall@K·MRR 분모에서 제외.

## 5. 전체 평가 결과

| Hit@1 | Hit@3 | Hit@5 | Hit@10 | Hit@30 | MRR |
|---:|---:|---:|---:|---:|---:|
| 0.438 | 0.703 | 0.826 | 0.913 | 0.955 | 0.596 |

| MacroRecall@3 | MacroRecall@5 | MacroRecall@10 |
|---:|---:|---:|
| 0.647 | 0.797 | 0.916 |

- (참고) Micro Recall@10: 0.878 · gold 총계(occurrence): 827 · 미회수(@10): 101

## 6. Relation별 결과

| relation | 문항수 | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Hit@30 | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|
| single | 374 | 0.511 | 0.783 | 0.893 | 0.968 | 0.987 | 0.668 |
| or | 5 | 0.200 | 0.600 | 0.800 | 1.000 | 1.000 | 0.483 |
| and | 69 | 0.058 | 0.275 | 0.464 | 0.609 | 0.783 | 0.218 |

## 7. 도메인별 결과

| 업무 | 문항수 | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Hit@30 | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|
| 예금자보호제도 | 84 | 0.548 | 0.798 | 0.881 | 0.940 | 0.988 | 0.692 |
| 착오송금 반환 신청 | 84 | 0.298 | 0.512 | 0.643 | 0.798 | 0.869 | 0.444 |
| 채무조정 안내 | 78 | 0.449 | 0.744 | 0.833 | 0.885 | 0.936 | 0.605 |
| 고객 미수령금 신청 | 75 | 0.400 | 0.733 | 0.853 | 0.933 | 0.973 | 0.588 |
| 예금보험금 안내 | 65 | 0.462 | 0.708 | 0.862 | 0.985 | 0.985 | 0.624 |
| 은닉재산 신고 | 62 | 0.484 | 0.742 | 0.919 | 0.968 | 1.000 | 0.644 |

## 8. 오류 분석

- 미적중(top-3 밖) 133건 / 평가 대상 448건 (29.7%)

### 8-1. 미적중 원인 분포

정분류: gt 업무 청크가 top-3 안에 있으나 순위/청킹 문제로 놓침. 오분류: top-3 전부 다른 업무 청크로 채워짐. (업무 분류기가 적용됐는지까지는 이 표만으로 알 수 없음 — 세부 조사는 수작업 검토 필요.)

| 원인 | 건수 |
|---|---:|
| 정분류(업무 내 랭킹·청킹) | 122 (91.7%) |
| 오분류(다른 업무로 혼입) | 11 (8.3%) |

### 8-2. 업무별 미적중

| 업무 | 문항수 | 미적중 | 미적중률 |
|---|---:|---:|---:|
| 착오송금 반환 신청 | 84 | 41 | 48.8% |
| 채무조정 안내 | 78 | 20 | 25.6% |
| 고객 미수령금 신청 | 75 | 20 | 26.7% |
| 예금보험금 안내 | 65 | 19 | 29.2% |
| 예금자보호제도 | 84 | 17 | 20.2% |
| 은닉재산 신고 | 62 | 16 | 25.8% |

### 8-3. 혼입 문서 랭킹 (미적중 top-3를 잠식한 다른 업무 청크)

| 청크 ID | 출현 | 업무 |
|---|---:|---|
| `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#01` | 10 | 예금보험금 안내 |
| `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#02` | 7 | 예금보험금 안내 |
| `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#03` | 7 | 예금보험금 안내 |
| `kdic-fins-cm-bbs-selectFaqNramtAply#26` | 5 | 예금보험금 안내 |
| `kdic-fins-cm-bbs-selectFaqNramtAply#20` | 4 | 예금보험금 안내 |
| `kdic-www-sp-sprtfund-SprtFndDebtDlngAplyGudn-selectScrn#00` | 4 | 채무조정 안내 |
| `kdic-fins-cm-bbs-selectFaqNramtAply#23` | 3 | 예금보험금 안내 |
| `kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01` | 2 | 예금자보호제도 |
| `kdic-fins-cm-bbs-selectFaqNramtAply#25` | 2 | 예금보험금 안내 |
| `kdic-fins-cm-bbs-selectFaqNramtAply#03` | 2 | 예금자보호제도 |
| `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00` | 1 | 예금자보호제도 |
| `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply#02` | 1 | 착오송금 반환 신청 |
| `kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn#00` | 1 | 착오송금 반환 신청 |
| `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn#02` | 1 | 착오송금 반환 신청 |
| `kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn#01` | 1 | 고객 미수령금 신청 |

### 8-4. 업무 간 혼입 흐름 (정답 업무 → top-1 업무)

| 정답 업무 | → top-1 업무 | 건수 |
|---|---|---:|
| 고객 미수령금 신청 | 예금보험금 안내 | 11 |
| 착오송금 반환 신청 | 예금보험금 안내 | 3 |
| 예금보험금 안내 | 예금자보호제도 | 2 |
| 고객 미수령금 신청 | 착오송금 반환 신청 | 2 |
| 예금보험금 안내 | 고객 미수령금 신청 | 1 |
| 예금자보호제도 | 예금보험금 안내 | 1 |
| 채무조정 안내 | 착오송금 반환 신청 | 1 |
| 고객 미수령금 신청 | 채무조정 안내 | 1 |

### 8-5. 대표 실패 사례 (gold가 top-10에도 없음)

- **[채무조정 안내] nat450-0052** — 파산해도 면책이 안 되는 경우는 어떤 때예요?
  - gold: `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn#02`<br>`kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn#03`
  - top-3: `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn#00`<br>`kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn#01`<br>`kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn#02`
- **[예금자보호제도] nat450-0065** — 어떤 금융회사에 맡긴 돈이어야 보호를 받을 수 있는 거죠?
  - gold: `kdic-www-sp-dpstrprot-selectProtSystProtSumr#00`
  - top-3: `kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#02`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#05`
- **[고객 미수령금 신청] nat450-0072** — 못 받은 돈, 온라인으로 신청하는 사이트가 어디예요? 인증은 뭘로 하죠?
  - gold: `kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn#01`<br>`kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#02`<br>`kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn#00`<br>`kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn#00`
  - top-3: `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply#02`<br>`kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn#00`<br>`kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn#02`
- **[착오송금 반환 신청] nat450-0076** — 돈을 잘못 보낸 사람은 반환 신청을 무슨 방법으로 하면 돼요?
  - gold: `kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn#00`
  - top-3: `kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn#00`<br>`kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn#00`<br>`kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn#01`
- **[고객 미수령금 신청] nat450-0085** — 애 명의로 남아 있는 돈은 부모가 어떤 서류로 신청해요?
  - gold: `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#00`<br>`kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#01`
  - top-3: `kdic-fins-cm-bbs-selectFaqNramtAply#25`<br>`kdic-fins-cm-bbs-selectFaqNramtAply#26`<br>`kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#03`
- **[고객 미수령금 신청] nat450-0088** — 회사 명의로 안 찾아간 돈이 있는데 법인은 뭘 준비해서 어디로 가야 하죠?
  - gold: `kdic-fins-cm-bbs-selectFaqNramtAply#20`<br>`kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn#00`<br>`kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn#00`
  - top-3: `kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn#00`<br>`kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn#00`<br>`kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn#01`
- **[예금자보호제도] nat450-0092** — 은행이냐 보험사냐에 따라 보호되는 상품이 다른가요?
  - gold: `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01`
  - top-3: `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#04`<br>`kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#03`
- **[예금자보호제도] nat450-0093** — 내가 가입한 데가 어디냐에 따라 보호 안 되는 상품 목록도 달라져요?
  - gold: `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#02`
  - top-3: `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn#04`<br>`kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#01`<br>`kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00`

## 9. 개선 우선순위

1. '착오송금 반환 신청' 업무 — 미적중 41/84건(48.8%)로 가장 취약함
2. '채무조정 안내' 업무 — 미적중 20/78건(25.6%)로 가장 취약함
3. '고객 미수령금 신청' 업무 — 미적중 20/75건(26.7%)로 가장 취약함
4. `and` relation(다중 근거 필요) Hit@3=0.275로 전체 평균(0.703)보다 낮음 — 다중 청크 회수 전략 점검 필요
5. `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#01` 청크가 미적중 10건에서 top-3를 잠식 — 업무 분류/부스트 파라미터 재검토 대상 1순위
