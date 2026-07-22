# 오류 분석 리포트 — hybrid_bf 기준

- 대상: 전체 400건 중 **미적중 58건** · 미적중률 14.5%
- 미적중 = gt_docs 문서가 hybrid_bf top-3 밖. `rank=0` 은 top-10 내에도 정답 문서 없음.
- 태그: **✅정답** / **⚠️타업무혼입** / **❌동일업무오답**.
- 원인(질의 분류): **불명**(필터 미적용) / **오분류**(엉뚱한 업무로 필터) / **정분류**(업무 내부 랭킹·청킹 문제).

## 0. 미적중 원인 분포

| 원인 | 건수 |
|---|---|
| 정분류 | 26 |
| 불명 | 24 |
| 오분류 | 8 |

## 1. 업무별 미적중

| 업무 | 문항 | 미적중 | 미적중률 |
|---|---|---|---|
| 착오송금 반환 신청 | 72 | 20 | 27.8% |
| 고객 미수령금 신청 | 67 | 14 | 20.9% |
| 예금보험금 안내 | 65 | 9 | 13.8% |
| 예금자보호제도 | 66 | 6 | 9.1% |
| 채무조정 안내 | 68 | 5 | 7.4% |
| 은닉재산 신고 | 62 | 4 | 6.5% |

## 2. 혼입 문서 랭킹 (미적중 top-3를 잠식한 오답 문서)

| 혼입 문서 | 출현 | 소속 업무 |
|---|---|---|
| `kdic-fins-cm-bbs-selectFaqNramtAply` | 25 | 예금보험금 안내 |
| `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn` | 11 | 예금보험금 안내 |
| `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn` | 11 | 착오송금 반환 신청 |
| `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn` | 11 | 착오송금 반환 신청 |
| `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply` | 11 | 착오송금 반환 신청 |
| `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn` | 9 | 예금자보호제도 |
| `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn` | 7 | 착오송금 반환 신청 |
| `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn` | 7 | 착오송금 반환 신청 |
| `kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn` | 6 | 예금보험금 안내 |
| `kdic-www-sp-kmrs-kmrsItrd-selectScrn` | 6 | 착오송금 반환 신청 |
| `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn` | 6 | 착오송금 반환 신청 |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn` | 6 | 채무조정 안내 |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn` | 6 | 채무조정 안내 |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn` | 5 | 채무조정 안내 |
| `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn` | 4 | 예금보험금 안내 |

## 3. 업무 간 혼입 흐름 (top-1이 엉뚱한 업무)

| 정답 업무 | → top-1 업무 | 건수 |
|---|---|---|
| 고객 미수령금 신청 | 예금보험금 안내 | 6 |
| 예금보험금 안내 | 채무조정 안내 | 3 |
| 고객 미수령금 신청 | 예금자보호제도 | 2 |
| 고객 미수령금 신청 | 착오송금 반환 신청 | 2 |
| 예금보험금 안내 | 예금자보호제도 | 2 |
| 고객 미수령금 신청 | 채무조정 안내 | 2 |
| 착오송금 반환 신청 | 예금보험금 안내 | 1 |
| 예금자보호제도 | 예금보험금 안내 | 1 |
| 은닉재산 신고 | 착오송금 반환 신청 | 1 |

## 4. 미적중 문항 상세

### [고객 미수령금 신청 · heading] 개산지급금 '정산금'이라는 건 뭘 정산해서 주는 돈이죠?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn', 'kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 오분류(→예금보험금 안내, 정답배제 위험)**
- dense rank: 미적중 · hybrid_bf rank: 9
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  3. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금 신청절차  `kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn`

### [고객 미수령금 신청 · heading] 망한 금융사 재산을 정리해서 예금자에게 나눠주는 돈이 뭐죠?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn', 'kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 9 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  2. [⚠️타업무혼입] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [⚠️타업무혼입] 예금자보호제도 / 보호한도  `kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn`

### [고객 미수령금 신청 · new] 개산지급금 정산금도 인터넷으로 신청할 수 있나요, 아니면 직접 가야 하나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 오분류(→예금보험금 안내, 정답배제 위험)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  3. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금 신청절차  `kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn`

### [고객 미수령금 신청 · new] 개산지급금 정산금이랑 파산배당금은 받으러 가는 곳이 다른가요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 오분류(→예금보험금 안내, 정답배제 위험)**
- dense rank: 미적중 · hybrid_bf rank: 10
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  2. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금 신청절차  `kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn`

### [고객 미수령금 신청 · new] 개산지급금을 받은 다음에 나중에 정산금이라는 걸 또 받을 수도 있다는 게 무슨 말이에요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 오분류(→예금보험금 안내, 정답배제 위험)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  3. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금 신청절차  `kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn`

### [고객 미수령금 신청 · new] 개인사업자로 거래했었는데 미수령금 신청할 때 서류가 법인이랑 같나요?
- 정답 gt_docs: ['kdic-fins-cm-bbs-selectFaqNramtAply']
- 질의분류: 고객 미수령금 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 1 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 고객 미수령금 신청 / 상속인 금융거래조회  `kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn`
  2. [⚠️타업무혼입] 예금보험금 안내 / 신청시 구비서류  `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn`
  3. [❌동일업무오답] 고객 미수령금 신청 / 고객미수령금  `kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn`

### [고객 미수령금 신청 · new] 부모님이 예금보험금 나오기 전에 돌아가셨을 때랑 후에 돌아가셨을 때 상속 처리가 다른가요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 오분류(→예금보험금 안내, 정답배제 위험)**
- dense rank: 5 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 예금보험금 안내 / 신청시 구비서류  `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn`
  3. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금 신청절차  `kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn`

### [고객 미수령금 신청 · new] 옛날에 망한 회사가 여러 곳인데 한 번에 다 조회하고 신청할 수 있나요?
- 정답 gt_docs: ['kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 5 · hybrid_bf rank: 8
- hybrid_bf top-3:
  1. [❌동일업무오답] 고객 미수령금 신청 / 상속인 금융거래조회  `kdic-www-sp-dpstrprot-ProtSystHrpeHistInq-selectScrn`
  2. [⚠️타업무혼입] 은닉재산 신고 / 신고 및 조회  `kdic-www-sp-sprtfund-SprtCncmDclrInqGudn-selectScrn`
  3. [⚠️타업무혼입] 채무조정 안내 / 채무정보 조회 ＆ 상담신청  `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltInfoInqDscsnAply-selectScrn`

### [고객 미수령금 신청 · new] 제가 가야 할 지급대행점이 어디인지는 어떻게 알아보나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`
  2. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [⚠️타업무혼입] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`

### [고객 미수령금 신청 · new] 제가 거래하던 곳이 파산금융회사 목록에 없으면 미수령금도 없다고 봐야 하나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 채무조정 안내 / 파산면책  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn`
  2. [⚠️타업무혼입] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [⚠️타업무혼입] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`

### [고객 미수령금 신청 · new] 제가 예전에 거래하던 회사가 진짜 파산한 게 맞는지 어디서 확인할 수 있나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 채무조정 안내 / 파산면책  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn`
  2. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  3. [⚠️타업무혼입] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn`

### [고객 미수령금 신청 · short] 개산지급금 정산금이 뭐예요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn', 'kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 오분류(→예금보험금 안내, 정답배제 위험)**
- dense rank: 미적중 · hybrid_bf rank: 8
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  3. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금 신청절차  `kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn`

### [고객 미수령금 신청 · short] 파산배당금이 뭔가요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn', 'kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 미적중(top10밖)
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 채무조정 안내 / 파산면책  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn`
  3. [⚠️타업무혼입] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`

### [고객 미수령금 신청 · yesom] 은행에서 못 받고 넘어간 돈이 있다는데 어디서 어떻게 받는 거예요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn', 'kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 8
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`
  2. [⚠️타업무혼입] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`
  3. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금보험금 안내 · new] 은행에서 채권채무 잔액조회서라는 걸 보내왔는데 이거 받으면 뭘 해야 하나요?
- 정답 gt_docs: ['kdic-fins-cm-bbs-selectFaqNramtAply']
- 질의분류: 채무조정 안내 · **원인: 오분류(→채무조정 안내, 정답배제 위험)**
- dense rank: 1 · hybrid_bf rank: 9
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 채무조정 안내 / 신용회복 지원  `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn`
  2. [⚠️타업무혼입] 채무조정 안내 / 채무정보 조회 ＆ 상담신청  `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltInfoInqDscsnAply-selectScrn`
  3. [⚠️타업무혼입] 채무조정 안내 / 채무조정제도  `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn`

### [예금보험금 안내 · new] 제가 다른 사람 빚 보증을 서준 상태인데 제 예금 지급이 언제쯤 풀리나요?
- 정답 gt_docs: ['kdic-fins-cm-bbs-selectFaqNramtAply']
- 질의분류: 채무조정 안내 · **원인: 오분류(→채무조정 안내, 정답배제 위험)**
- dense rank: 1 · hybrid_bf rank: 7
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  2. [⚠️타업무혼입] 채무조정 안내 / 채무조정제도  `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn`
  3. [⚠️타업무혼입] 채무조정 안내 / 소개와 방법 안내  `kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn`

### [예금보험금 안내 · new] 제가 예금한 은행이 다른 은행으로 넘어갔다는데 제 통장은 그대로 쓸 수 있는 건가요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`
  3. [⚠️타업무혼입] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`

### [예금보험금 안내 · short] 보험금 인터넷으로 신청 가능해요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  3. [⚠️타업무혼입] 채무조정 안내 / 부채증명원/금융거래정보신청  `kdic-www-sp-sprtfund-SprtFndDebtDlngAplyGudn-selectScrn`

### [예금보험금 안내 · simple] 보험금 받는 데 얼마나 걸려요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 10 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  2. [❌동일업무오답] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  3. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금보험금 안내 · simple] 인터넷 신청도 미성년자는 안 되나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 채무조정 안내 / 채무정보조회  `kdic-fins-cm-bbs-selectFaqLbltInfoInq`
  2. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  3. [⚠️타업무혼입] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`

### [예금보험금 안내 · yesom] 예금보험금 온라인 신청은 어느 사이트에서 하고 본인확인은 뭐가 필요해요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn']
- 질의분류: 예금보험금 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  3. [❌동일업무오답] 예금보험금 안내 / 신청시 구비서류  `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn`

### [예금보험금 안내 · yesom] 은행 망했을 때 보험금은 어떤 방법으로 신청할 수 있어?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 8 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`
  2. [⚠️타업무혼입] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  3. [❌동일업무오답] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금보험금 안내 · yesom] 파산 배당 나올 걸 미리 어림잡아 당겨 받는 돈을 뭐라고 하죠?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 9
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  3. [⚠️타업무혼입] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`

### [예금자보호제도 · new] 예금자보호를 해주는 은행이나 저축은행이 전국에 몇 곳이나 되는지 알 수 있나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-selectProtSystProtSumr']
- 질의분류: 예금자보호제도 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  3. [❌동일업무오답] 예금자보호제도 / 예금자보호제도  `kdic-www-sp-dpstrprot-ProtSyst-selectScrn`

### [예금자보호제도 · short] 예금보험 가입 따로 해야 하나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 2 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금자보호제도 / 개요  `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr`
  3. [⚠️타업무혼입] 예금보험금 안내 / 예금보험금이란?  `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn`

### [예금자보호제도 · short] 예금자보호제도가 뭐예요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSyst-selectScrn']
- 질의분류: 예금자보호제도 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금자보호제도 / 보호한도  `kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn`
  2. [❌동일업무오답] 예금자보호제도 / 표시·설명·확인 제도 안내  `kdic-www-sp-dpstrprot-ProtSystProtGudn-selectScrn`
  3. [❌동일업무오답] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금자보호제도 · yesom] 나라에서 예금을 지켜준다는 제도가 뭔지 설명해줄래요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSyst-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금자보호제도 / 개요  `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr`
  2. [❌동일업무오답] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  3. [❌동일업무오답] 예금자보호제도 / 보호한도  `kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn`

### [예금자보호제도 · yesom] 어떤 금융회사에 맡긴 돈이어야 보호를 받을 수 있는 거죠?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-selectProtSystProtSumr']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`
  2. [❌동일업무오답] 예금자보호제도 / 예금자보호제도  `kdic-www-sp-dpstrprot-ProtSyst-selectScrn`
  3. [❌동일업무오답] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [예금자보호제도 · yesom] 한 사람당 예금은 최대 얼마까지 지켜주나요?
- 정답 gt_docs: ['kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [❌동일업무오답] 예금자보호제도 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [❌동일업무오답] 예금자보호제도 / 개요  `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr`
  3. [❌동일업무오답] 예금자보호제도 / 예금자보호제도 FAQ  `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn`

### [은닉재산 신고 · new] 그 사람이 가족 이름으로 재산을 몰래 넘겨놓은 것 같은데 이것도 신고할 수 있나요?
- 정답 gt_docs: ['kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`
  2. [❌동일업무오답] 은닉재산 신고 / FAQ  `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn`
  3. [⚠️타업무혼입] 예금보험금 안내 / 신청시 구비서류  `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn`

### [은닉재산 신고 · new] 그 사람이 남한테 빌려준 돈이나 받을 채권이 있어도 그것도 신고 대상이 되나요?
- 정답 gt_docs: ['kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 10
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`
  2. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`
  3. [❌동일업무오답] 은닉재산 신고 / FAQ  `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn`

### [은닉재산 신고 · new] 신고하기 전에 이게 신고 대상이 맞는지 먼저 상담부터 받아볼 수 있나요?
- 정답 gt_docs: ['kdic-www-sp-sprtfund-SprtCncmDclrInqGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 은닉재산 신고 / FAQ  `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn`
  2. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`
  3. [❌동일업무오답] 은닉재산 신고 / 신고센터  `kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn`

### [은닉재산 신고 · new] 지금까지 이 제도로 실제로 얼마나 재산을 찾아냈는지 알 수 있나요?
- 정답 gt_docs: ['kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 9 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [❌동일업무오답] 은닉재산 신고 / 은닉재산신고  `kdic-fins-cm-bbs-selectFaqCncmPrptDclr`
  2. [❌동일업무오답] 은닉재산 신고 / FAQ  `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn`
  3. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`

### [착오송금 반환 신청 · paraphrase] 착오송금 반환지원 대상이 어떻게 돼요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn', 'kdic-www-sp-kmrs-kmrsItrd-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 8
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / TOP 10  `kdic-fins-cm-bbs-selectFaqTop10`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  3. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn`

### [착오송금 반환 신청 · paraphrase] 착오송금 신청 시 유의할 점이 있나요?
- 정답 gt_docs: ['kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn', 'kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 5 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금수취인  `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn`

### [착오송금 반환 신청 · paraphrase] 착오송금 처리 단계가 어떻게 돼요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdProc-selectScrn', 'kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / TOP 10  `kdic-fins-cm-bbs-selectFaqTop10`

### [착오송금 반환 신청 · short] 잘못 송금한 거 온라인 접수돼요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 9
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`

### [착오송금 반환 신청 · short] 착오송금 방문 접수는 어디로 가요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn', 'kdic-fins-ir-aplygudn-MtrsVstRcptGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 8 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금수취인  `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn`

### [착오송금 반환 신청 · short] 착오송금 어떻게 신청해요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 10
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금수취인  `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`

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
- dense rank: 미적중 · hybrid_bf rank: 9
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 제도란  `kdic-www-sp-kmrs-kmrsItrd-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`

### [착오송금 반환 신청 · yesom] 군인이 착오송금한 경우 반환 신청 서류는 뭘 준비해야 해?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 1 · hybrid_bf rank: 7
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
- dense rank: 2 · hybrid_bf rank: 7
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
- dense rank: 3 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [⚠️타업무혼입] 예금보험금 안내 / 미수령금통합신청  `kdic-fins-cm-bbs-selectFaqNramtAply`
  2. [⚠️타업무혼입] 채무조정 안내 / 부채증명원/금융거래정보신청  `kdic-www-sp-sprtfund-SprtFndDebtDlngAplyGudn-selectScrn`
  3. [⚠️타업무혼입] 은닉재산 신고 / 신고센터  `kdic-www-sp-sprtfund-SprtFndCncmDclrGudn-selectScrn`

### [착오송금 반환 신청 · yesom] 외국 거주자가 잘못 보낸 돈 반환 신청할 땐 서류가 어떻게 되나요?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 2 · hybrid_bf rank: 6
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  2. [❌동일업무오답] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`

### [착오송금 반환 신청 · yesom] 잘못 받은 돈 돌려주면서 낸 이체수수료도 돌려받을 수 있는 건가?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn']
- 질의분류: None · **원인: 불명(필터 미적용)**
- dense rank: 미적중 · hybrid_bf rank: 5
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

### [착오송금 반환 신청 · yesom] 잘못 보낸 본인이 인터넷으로 접수할 때 필요한 게 뭐뭐예요?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 3 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 제도란  `kdic-www-sp-kmrs-kmrsItrd-selectScrn`

### [착오송금 반환 신청 · yesom] 잘못 송금한 거 온라인으로 접수하는 절차가 어떻게 되나요?
- 정답 gt_docs: ['kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 9
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원신청  `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금인  `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`

### [착오송금 반환 신청 · yesom] 제가 직접 가서 잘못 보낸 돈 반환 신청하면 뭘 들고 가야 하나요?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 9
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 반환지원절차  `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 신청대상  `kdic-www-sp-kmrs-kmrsItrdAplyTrgt-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 착오송금반환지원 제도란  `kdic-www-sp-kmrs-kmrsItrd-selectScrn`

### [착오송금 반환 신청 · yesom] 회사 돈을 잘못 이체했는데 법인 반환 신청 서류가 따로 있나요?
- 정답 gt_docs: ['kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn']
- 질의분류: 착오송금 반환 신청 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 7
- hybrid_bf top-3:
  1. [❌동일업무오답] 착오송금 반환 신청 / 착오송금수취인  `kdic-fins-ir-aplygudn-MsdrAddrsePossDcmntGudn-selectScrn`
  2. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn`
  3. [❌동일업무오답] 착오송금 반환 신청 / 유의사항  `kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn`

### [채무조정 안내 · new] 빚이 얼마 안 되는 사람은 절차를 더 간단하게 해주는 제도가 있나요?
- 정답 gt_docs: ['kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn']
- 질의분류: 채무조정 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 2 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  2. [❌동일업무오답] 채무조정 안내 / 파산면책  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn`
  3. [❌동일업무오답] 채무조정 안내 / 신용회복 지원  `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn`

### [채무조정 안내 · new] 예전에 망한 저축은행에서 대출받은 게 있었는데, 그 빚 관련 증명서를 떼야 하는데 어디서 받나요?
- 정답 gt_docs: ['kdic-www-sp-sprtfund-SprtFndDebtDlngAplyGudn-selectScrn']
- 질의분류: 채무조정 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  2. [❌동일업무오답] 채무조정 안내 / 채무조정제도  `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn`
  3. [❌동일업무오답] 채무조정 안내 / 소개와 방법 안내  `kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn`

### [채무조정 안내 · short] 빚 조정 신청은 어디서 해요?
- 정답 gt_docs: ['kdic-www-rb-lbltajmt-LbltAjmtSprtLbltInfoInqDscsnAply-selectScrn', 'kdic-fins-cm-bbs-selectFaqLbltInfoInq']
- 질의분류: 채무조정 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 5
- hybrid_bf top-3:
  1. [❌동일업무오답] 채무조정 안내 / 신용회복 지원  `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn`
  2. [❌동일업무오답] 채무조정 안내 / 소개와 방법 안내  `kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn`
  3. [❌동일업무오답] 채무조정 안내 / 채무조정제도  `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn`

### [채무조정 안내 · simple] 내 빚이 얼마인지 어디서 확인해요?
- 정답 gt_docs: ['kdic-www-rb-lbltajmt-LbltAjmtSprtLbltInfoInqDscsnAply-selectScrn', 'kdic-fins-cm-bbs-selectFaqLbltInfoInq']
- 질의분류: 채무조정 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 미적중 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  2. [❌동일업무오답] 채무조정 안내 / 신용회복 지원  `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn`
  3. [❌동일업무오답] 채무조정 안내 / 채무조정제도  `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn`

### [채무조정 안내 · yesom] 내 빚이 어디에 얼마나 있는지는 어디에 물어봐야 하나요?
- 정답 gt_docs: ['kdic-www-rb-lbltajmt-LbltAjmtSprtLbltInfoInqDscsnAply-selectScrn', 'kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn']
- 질의분류: 채무조정 안내 · **원인: 정분류(업무내 랭킹/청킹)**
- dense rank: 7 · hybrid_bf rank: 4
- hybrid_bf top-3:
  1. [❌동일업무오답] 채무조정 안내 / 개인회생  `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnRg-selectScrn`
  2. [❌동일업무오답] 채무조정 안내 / 채무조정제도  `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn`
  3. [❌동일업무오답] 채무조정 안내 / 신용회복 지원  `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn`

