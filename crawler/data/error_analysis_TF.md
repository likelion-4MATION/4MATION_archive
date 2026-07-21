# 오류 분석 리포트 — hybrid_bf 기준

- 대상: 전체 300건 중 **미적중 62건** · 미적중률 20.7%
- 미적중 = gt_docs 문서가 hybrid_bf top-3 밖. `rank=0` 은 top-10 내에도 정답 문서 없음.
- 태그: **✅정답** / **⚠️타업무혼입** / **❌동일업무오답**.
- 원인(질의 분류): **불명**(필터 미적용) / **오분류**(엉뚱한 업무로 필터) / **정분류**(업무 내부 랭킹·청킹 문제).

## 0. 미적중 원인 분포

| 원인 | 건수 |
|---|---|
| 정분류 | 38 |
| 불명 | 22 |
| 오분류 | 2 |

## 1. 업무별 미적중

| 업무 | 문항 | 미적중 | 미적중률 |
|---|---|---|---|
| 예금보험금 안내 | 40 | 13 | 32.5% |
| 착오송금 반환 신청 | 72 | 20 | 27.8% |
| 고객 미수령금 신청 | 44 | 11 | 25.0% |
| 은닉재산 신고 | 44 | 6 | 13.6% |
| 예금자보호제도 | 54 | 7 | 13.0% |
| 채무조정 안내 | 46 | 5 | 10.9% |

## 2. 혼입 문서 랭킹 (미적중 top-3를 잠식한 오답 문서)

| 혼입 문서 | 출현 | 소속 업무 |
|---|---|---|
| `kdic-fins-cm-bbs-selectFaqNramtAply` | 42 | 예금보험금 안내 |
| `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn` | 12 | 예금자보호제도 |
| `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn` | 11 | 착오송금 반환 신청 |
| `kdic-fins-cm-bbs-selectFaqCncmPrptDclr` | 11 | 은닉재산 신고 |
| `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn` | 10 | 착오송금 반환 신청 |
| `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn` | 9 | 예금보험금 안내 |
| `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply` | 9 | 착오송금 반환 신청 |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn` | 8 | 채무조정 안내 |
| `kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn` | 8 | 고객 미수령금 신청 |
| `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn` | 8 | 착오송금 반환 신청 |
| `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn` | 7 | 은닉재산 신고 |
| `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn` | 7 | 착오송금 반환 신청 |
| `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn` | 6 | 착오송금 반환 신청 |
| `kdic-www-sp-kmrs-kmrsItrd-selectScrn` | 5 | 착오송금 반환 신청 |
| `kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn` | 5 | 고객 미수령금 신청 |

## 3. 업무 간 혼입 흐름 (top-1이 엉뚱한 업무)

| 정답 업무 | → top-1 업무 | 건수 |
|---|---|---|
| 고객 미수령금 신청 | 예금보험금 안내 | 3 |
| 예금보험금 안내 | 예금자보호제도 | 3 |
| 예금자보호제도 | 예금보험금 안내 | 2 |
| 고객 미수령금 신청 | 예금자보호제도 | 2 |
| 고객 미수령금 신청 | 착오송금 반환 신청 | 1 |
| 착오송금 반환 신청 | 예금보험금 안내 | 1 |
| 예금보험금 안내 | 착오송금 반환 신청 | 1 |
| 예금보험금 안내 | 채무조정 안내 | 1 |

## 4. 미적중 문항 상세

### [고객 미수령금 신청 · heading] 개산지급금 '정산금'이라는 건 뭘 정산해서 주는 돈이죠?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn', 'kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 오분류(→예금보험금 안내, 정답배제 위험)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  3. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [고객 미수령금 신청 · heading] 망한 금융사 재산을 정리해서 예금자에게 나눠주는 돈이 뭐죠?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn', 'kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 9 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  2. [⚠️타업무혼입] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [⚠️타업무혼입] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [고객 미수령금 신청 · short] 개산지급금 정산금이 뭐예요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn', 'kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 오분류(→예금보험금 안내, 정답배제 위험)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  3. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [고객 미수령금 신청 · short] 군인 대신 미수령금 받으려면 서류가 뭐예요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn', 'kdic-fins-cm-bbs-selectFaqNramtAply']
- 질의분류: 고객 미수령금 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 2 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 고객 미수령금 신청 / 상속인 금융거래조회  `kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn`
  2. [❌동일업무오답] 고객 미수령금 신청 / 상속인 금융거래조회  `kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn`
  3. [❌동일업무오답] 고객 미수령금 신청 / 안내  `kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn`

### [고객 미수령금 신청 · short] 미수령금 대리 신청 서류 알려줘요
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn', 'kdic-fins-cm-bbs-selectFaqNramtAply']
- 질의분류: 고객 미수령금 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [❌동일업무오답] 고객 미수령금 신청 / 상속인 금융거래조회  `kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn`
  2. [❌동일업무오답] 고객 미수령금 신청 / 안내  `kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn`
  3. [❌동일업무오답] 고객 미수령금 신청 / 상속인 금융거래조회  `kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn`

### [고객 미수령금 신청 · short] 본인이 미수령금 신청할 때 준비물은요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn', 'kdic-fins-cm-bbs-selectFaqNramtAply']
- 질의분류: 고객 미수령금 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 1 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 고객 미수령금 신청 / 상속인 금융거래조회  `kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn`
  2. [❌동일업무오답] 고객 미수령금 신청 / 상속인 금융거래조회  `kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn`
  3. [❌동일업무오답] 고객 미수령금 신청 / 안내  `kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn`

### [고객 미수령금 신청 · short] 파산배당금이 뭔가요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn', 'kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 채무조정 안내 / 파산면책  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn`
  3. [⚠️타업무혼입] 채무조정 안내 / 파산면책  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn`

### [고객 미수령금 신청 · simple] 돌아가신 아버지 예금 찾는 방법 있어요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 3 · hybrid_bf rank: 7
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [고객 미수령금 신청 · simple] 해외 사는데 한국 미수령금 받을 수 있어요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn', 'kdic-fins-cm-bbs-selectFaqNramtAply']
- 질의분류: 고객 미수령금 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 2 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [❌동일업무오답] 고객 미수령금 신청 / 안내  `kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn`
  2. [❌동일업무오답] 고객 미수령금 신청 / 고객미수령금  `kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn`
  3. [❌동일업무오답] 고객 미수령금 신청 / 상속인 금융거래조회  `kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn`

### [고객 미수령금 신청 · yesom] 은행에서 못 받고 넘어간 돈이 있다는데 어디서 어떻게 받는 거예요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn', 'kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`
  2. [⚠️타업무혼입] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`
  3. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [고객 미수령금 신청 · yesom] 해외에 사는 사람은 한국에 남은 미수령 돈을 어떻게 받아요? 대리 신청 서류는요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn', 'kdic-fins-cm-bbs-selectFaqNramtAply']
- 질의분류: 고객 미수령금 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 1 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 고객 미수령금 신청 / 안내  `kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn`
  2. [❌동일업무오답] 고객 미수령금 신청 / 고객미수령금  `kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn`
  3. [❌동일업무오답] 고객 미수령금 신청 / 상속인 금융거래조회  `kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn`

### [예금보험금 안내 · heading] 예금보험금 나오기 전에 일부를 먼저 당겨 받는 돈을 뭐라고 해요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금보험금 안내 · short] 가지급금이 무슨 돈이에요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 7
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금보험금 안내 · short] 보험금 인터넷으로 신청 가능해요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 8
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [❌동일업무오답] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`

### [예금보험금 안내 · short] 예금보험금은 언제 지급돼요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 8 · hybrid_bf rank: 7
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금보험금 안내 · simple] 보험금 받는 데 얼마나 걸려요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 10 · hybrid_bf rank: 7
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  2. [⚠️타업무혼입] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  3. [❌동일업무오답] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`

### [예금보험금 안내 · simple] 예금보험금 안 찾으면 언제 없어져요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 8
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금보험금 안내 · simple] 예금주가 죽으면 보험금 누가 받아요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn', 'kdic-fins-cm-bbs-selectFaqNramtAply']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 1 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  2. [❌동일업무오답] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  3. [❌동일업무오답] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`

### [예금보험금 안내 · simple] 위임장 없이 대리 신청 되나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 2 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  2. [⚠️타업무혼입] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  3. [⚠️타업무혼입] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`

### [예금보험금 안내 · simple] 인터넷 신청도 미성년자는 안 되나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 채무조정 안내 / 채무정보조회  `kdic-fins-cm-bbs-selectFaqLbltInfoInq`
  2. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [⚠️타업무혼입] 채무조정 안내 / 채무정보조회  `kdic-fins-cm-bbs-selectFaqLbltInfoInq`

### [예금보험금 안내 · yesom] 예금보험금 온라인 신청은 어느 사이트에서 하고 본인확인은 뭐가 필요해요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 10
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금보험금 안내 · yesom] 예금보험금을 창구에서 직접 받으려면 어느 지점으로 가야 하나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 7
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  3. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금보험금 안내 · yesom] 은행 망했을 때 보험금은 어떤 방법으로 신청할 수 있어?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 8 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  2. [⚠️타업무혼입] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  3. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금보험금 안내 · yesom] 파산 배당 나올 걸 미리 어림잡아 당겨 받는 돈을 뭐라고 하죠?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  3. [⚠️타업무혼입] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`

### [예금자보호제도 · faq] 이자까지 쳐서 돌려주나요, 아니면 원금만인가요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn', 'kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금자보호제도 · short] 예금보험 가입 따로 해야 하나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 2 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금자보호제도 / 개요  `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr`
  3. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`

### [예금자보호제도 · short] 예금자보호제도가 뭐예요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSyst-selectScrn']
- 질의분류: 예금자보호제도 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금자보호제도 / 보호한도  `kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn`
  2. [❌동일업무오답] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  3. [❌동일업무오답] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`

### [예금자보호제도 · simple] 저축은행 정기예금 보호되나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr']
- 질의분류: 예금자보호제도 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 7
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  2. [❌동일업무오답] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [❌동일업무오답] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금자보호제도 · yesom] 나라에서 예금을 지켜준다는 제도가 뭔지 설명해줄래요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSyst-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 10
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금자보호제도 / 개요  `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr`
  2. [❌동일업무오답] 예금자보호제도 / 개요  `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr`
  3. [❌동일업무오답] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`

### [예금자보호제도 · yesom] 어떤 금융회사에 맡긴 돈이어야 보호를 받을 수 있는 거죠?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-selectProtSystProtSumr']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  2. [❌동일업무오답] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  3. [❌동일업무오답] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`

### [예금자보호제도 · yesom] 한 사람당 예금은 최대 얼마까지 지켜주나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 고객 미수령금 신청 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [❌동일업무오답] 예금자보호제도 / 개요  `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr`

### [은닉재산 신고 · short] 숨긴 재산 신고 어떻게 해요?
- 정답 gt_docs: ['kdic-www-sp-sprtfund-SprtCncmDclrInqGudn-selectScrn', 'kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn']
- 질의분류: 은닉재산 신고 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`
  2. [❌동일업무오답] 은닉재산 신고 / FAQ  `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn`
  3. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`

### [은닉재산 신고 · short] 신고 접수되면 어떻게 처리돼요?
- 정답 gt_docs: ['kdic-www-sp-sprtfund-SprtCncmDclrInqGudn-selectScrn', 'kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 5 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 은닉재산 신고 / FAQ  `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn`
  2. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`
  3. [❌동일업무오답] 은닉재산 신고 / FAQ  `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn`

### [은닉재산 신고 · simple] 숨긴 재산 제보 방법 여러 개예요?
- 정답 gt_docs: ['kdic-www-sp-sprtfund-SprtCncmDclrInqGudn-selectScrn', 'kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn']
- 질의분류: 은닉재산 신고 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 8 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 은닉재산 신고 / FAQ  `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn`
  2. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`
  3. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`

### [은닉재산 신고 · simple] 은닉재산 신고 우편으로 보내도 돼요? 주소는요?
- 정답 gt_docs: ['kdic-www-sp-sprtfund-SprtCncmDclrInqGudn-selectScrn', 'kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn']
- 질의분류: 은닉재산 신고 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`
  2. [❌동일업무오답] 은닉재산 신고 / FAQ  `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn`
  3. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`

### [은닉재산 신고 · yesom] 그 재산 정보를 어떻게 알았는지까지 밝혀야 신고가 되나요?
- 정답 gt_docs: ['kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 은닉재산 신고 / FAQ  `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn`
  2. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`
  3. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`

### [은닉재산 신고 · yesom] 숨긴 재산 신고를 메일로 보내도 되나요? 주소는요?
- 정답 gt_docs: ['kdic-www-sp-sprtfund-SprtCncmDclrInqGudn-selectScrn', 'kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn']
- 질의분류: 은닉재산 신고 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 8
- hybrid_bf top-3:
  1. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`
  2. [❌동일업무오답] 은닉재산 신고 / FAQ  `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn`
  3. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`

### [착오송금 반환 신청 · paraphrase] 착오송금 반환지원 대상이 어떻게 돼요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn', 'kdic-www-sp-kmrs-kmrsItrd-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / TOP 10  `kdic-fins-cm-bbs-selectFaqTop10`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`

### [착오송금 반환 신청 · paraphrase] 착오송금 신청 시 유의할 점이 있나요?
- 정답 gt_docs: ['kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn', 'kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 5 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금수취인  `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn`

### [착오송금 반환 신청 · paraphrase] 착오송금 처리 단계가 어떻게 돼요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdProc-selectScrn', 'kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금수취인  `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn`

### [착오송금 반환 신청 · short] 이체수수료도 돌려받아요?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn`

### [착오송금 반환 신청 · short] 잘못 송금한 거 온라인 접수돼요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`

### [착오송금 반환 신청 · short] 착오송금 방문 접수는 어디로 가요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn', 'kdic-fins-ir-aplygudn-MtrsVstRcptGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 8 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`

### [착오송금 반환 신청 · short] 착오송금 어떻게 신청해요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금수취인  `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금수취인  `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn`

### [착오송금 반환 신청 · short] 해외 사는데 착오송금 반환 서류가 뭐예요?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 2 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금수취인  `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn`

### [착오송금 반환 신청 · yesom] 계좌 잘못 눌러서 딴 사람한테 돈을 보냈는데, 나라에서 받아주는 제도가 있다던데?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 제도란  `kdic-www-sp-kmrs-kmrsItrd-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`

### [착오송금 반환 신청 · yesom] 군인이 착오송금한 경우 반환 신청 서류는 뭘 준비해야 해?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 1 · hybrid_bf rank: 8
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금수취인  `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn`

### [착오송금 반환 신청 · yesom] 돈을 잘못 보낸 사람은 반환 신청을 무슨 방법으로 하면 돼요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 제도란  `kdic-www-sp-kmrs-kmrsItrd-selectScrn`

### [착오송금 반환 신청 · yesom] 미성년자가 잘못 송금했을 때 반환 신청에 필요한 서류가 궁금해요
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 2 · hybrid_bf rank: 8
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금수취인  `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn`

### [착오송금 반환 신청 · yesom] 법인 대표가 온라인으로 반환 신청하면 인증서 말고 또 뭐가 필요한가요?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 2 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청방법  `kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn`
  3. [⚠️타업무혼입] 채무조정 안내 / 채무정보조회  `kdic-fins-cm-bbs-selectFaqLbltInfoInq`

### [착오송금 반환 신청 · yesom] 비법인 단체 직원이 인터넷으로 대신 접수하려면 뭘 준비하죠?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 3 · hybrid_bf rank: 7
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 채무조정 안내 / 부채증명원/금융거래정보신청  `kdic-www-sp-sprtfund-SprtFndDebtDlngAplyGudn-selectScrn`
  3. [⚠️타업무혼입] 은닉재산 신고 / 신고센터  `kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn`

### [착오송금 반환 신청 · yesom] 외국 거주자가 잘못 보낸 돈 반환 신청할 땐 서류가 어떻게 되나요?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 2 · hybrid_bf rank: 9
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  2. [❌동일업무오답] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`

### [착오송금 반환 신청 · yesom] 잘못 받은 돈 돌려주면서 낸 이체수수료도 돌려받을 수 있는 건가?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 10
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 제도란  `kdic-www-sp-kmrs-kmrsItrd-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`

### [착오송금 반환 신청 · yesom] 잘못 보낸 돈 반환 신청을 직접 찾아가서 하려면 어디로 가면 되나요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn', 'kdic-fins-ir-aplygudn-MtrsVstRcptGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 제도란  `kdic-www-sp-kmrs-kmrsItrd-selectScrn`

### [착오송금 반환 신청 · yesom] 잘못 송금한 거 온라인으로 접수하는 절차가 어떻게 되나요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`

### [착오송금 반환 신청 · yesom] 제가 직접 가서 잘못 보낸 돈 반환 신청하면 뭘 들고 가야 하나요?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 제도란  `kdic-www-sp-kmrs-kmrsItrd-selectScrn`

### [착오송금 반환 신청 · yesom] 회사 돈을 잘못 이체했는데 법인 반환 신청 서류가 따로 있나요?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 9
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금수취인  `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn`

### [채무조정 안내 · paraphrase] 채무조정하고 개인파산은 뭐가 달라요?
- 정답 gt_docs: ['kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn', 'kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn']
- 질의분류: 채무조정 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 1 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 채무조정 안내 / 신용회복 지원  `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn`
  2. [❌동일업무오답] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  3. [❌동일업무오답] 채무조정 안내 / 신용회복 지원  `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn`

### [채무조정 안내 · short] 내 채무 어디에 얼마 있는지 조회돼요?
- 정답 gt_docs: ['kdic-www-rb-lbltajmt-LbltAjmtSprtLbltInfoInqDscsnAply-selectScrn', 'kdic-fins-cm-bbs-selectFaqLbltInfoInq']
- 질의분류: 채무조정 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  2. [❌동일업무오답] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  3. [❌동일업무오답] 채무조정 안내 / 소개와 방법 안내  `kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn`

### [채무조정 안내 · short] 빚 조정 신청은 어디서 해요?
- 정답 gt_docs: ['kdic-www-rb-lbltajmt-LbltAjmtSprtLbltInfoInqDscsnAply-selectScrn', 'kdic-fins-cm-bbs-selectFaqLbltInfoInq']
- 질의분류: 채무조정 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 8
- hybrid_bf top-3:
  1. [❌동일업무오답] 채무조정 안내 / 신용회복 지원  `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn`
  2. [❌동일업무오답] 채무조정 안내 / 소개와 방법 안내  `kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn`
  3. [❌동일업무오답] 채무조정 안내 / 채무조정제도  `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn`

### [채무조정 안내 · simple] 내 빚이 얼마인지 어디서 확인해요?
- 정답 gt_docs: ['kdic-www-rb-lbltajmt-LbltAjmtSprtLbltInfoInqDscsnAply-selectScrn', 'kdic-fins-cm-bbs-selectFaqLbltInfoInq']
- 질의분류: 채무조정 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  2. [❌동일업무오답] 채무조정 안내 / 신용회복 지원  `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn`
  3. [❌동일업무오답] 채무조정 안내 / 소개와 방법 안내  `kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn`

### [채무조정 안내 · yesom] 내 빚이 어디에 얼마나 있는지는 어디에 물어봐야 하나요?
- 정답 gt_docs: ['kdic-www-rb-lbltajmt-LbltAjmtSprtLbltInfoInqDscsnAply-selectScrn', 'kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn']
- 질의분류: 채무조정 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 7 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  2. [❌동일업무오답] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  3. [❌동일업무오답] 채무조정 안내 / 채무조정제도  `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn`

