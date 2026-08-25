# 앵커 라벨 점검 — `../final_testset/gt_natural430.jsonl`

- 평가 대상 430문항 · gold 청크 519개 중 앵커가 덮는 것 **434개(83.6%)** · 미앵커 85개
- 미앵커가 걸린 고유 청크 **37개** (문항×청크 쌍 85건)

## relation별 커버리지

| relation | 문항 | gold 청크 | 앵커 커버 | 전부 덮인 문항 |
|---|---:|---:|---:|---:|
| `single` | 370 | 370 | 370 (100%) | 370 (100%) |
| `and` | 55 | 139 | 56 (40%) | 0 (0%) |
| `or` | 5 | 10 | 8 (80%) | 3 (60%) |

## 미앵커 gold 청크와 후보 앵커

후보는 **청크 원문에서 고른 줄**이다(창작 아님). 코퍼스 전체에서 그 청크에만 존재하는
줄 중 가장 짧은 것을 우선한다. **표 청크에서 뽑힌 후보는 근거 문장이 아니라 청크
식별자에 가깝다** — 재청킹에는 견디지만 '최소 근거 스팬'은 아니므로 사람 확인이 필요하다.

| 청크 | 걸린 문항 | 길이 | 문서 | 후보 앵커 |
|---|---:|---:|---|---|
| `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#02` | 15 | 272자 | selectScrn | `착오송금 반환지원 신청서 | 신청서양식`<br>`채권양도 통지 위임장 | 채권양도통지위임장`<br>`대리인 | 공통 서류 | 대리인 확인용 신분증` |
| `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#08` | 7 | 160자 | selectScrn | `※ 반환지원 신청일 기준 최근 3개월내`<br>`정부24, 대법원 전자 가족관계등록 시스템`<br>`친권자 혹은 후견인임을 증명하는 서류 (가족관계증명서 및 미성년자 기준 기본증명서(상세)등) ※ 미성년자의 대리는 친권자 또는 후견인만가능 | 친권합의서양식 | 주민센터/온라인발급` |
| `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#04` | 5 | 129자 | selectScrn | `수수료 확인 가능한 자료 | 금융거래정보제공동의서`<br>`착오송금인의 인감 날인된 착오송금 반환지원 신청 등 위임장 스캔파일 | 착오송금인의 인감 날인된 착오송금 반환지원 신청 등 위임장 | 착오송금반환지원신청위임장 양식` |
| `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#09` | 4 | 115자 | selectScrn | `인감증명서제출이 불가능한경우 군복무 확인서(소속부대장발금) 파일업로드 | 소속부대`<br>`인감증명서제출이 불가능한경우 군복무 확인서(소속부대장발금) 파일업로드 | 군복무자를 대리하는 경우` |
| `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#11` | 4 | 85자 | selectScrn | `구분, 온라인신청, 방문신청, 관련서식, 발급처 및 비고 항목으로 구성된 착오송금 반환지원 신청 철회 표` |
| `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#06` | 4 | 95자 | selectScrn | `고유번호증 파일업로드 | 비법인단체를 대리하는 경우`<br>`고유번호증 사본 | 부가가치세법에 의하여 고유번호를 부여 받은 단체` |
| `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#05` | 4 | 298자 | selectScrn | `추가 서류 | 법인을 대리하는 경우`<br>`사업자등록증 파일업로드 | 법인을 대리하는 경우`<br>`착오송금인의 인감 날인된 채권양도 통지 위임장 스캔파일 | 착오송금인의 인감 날인된 채권양도 통지 위임장` |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn#03` | 3 | 796자 | selectScrn | `파산·면책신청에 도움을 주는 기관`<br>`현재 소득이 있는 채무자의 고려사항`<br>`상세한 안내는 서울회생법원 홈페이지 > 도산제도 안내 > 개인파산/개인회생 재판지원제도를 참조하시기 바랍니다.` |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn#01` | 3 | 129자 | selectScrn | **후보 없음** |
| `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#03` | 3 | 195자 | selectScrn | `착오송금인의 인감 날인된 금융 거래정보제공요구(동의)서`<br>`수수료 확인 가능한 자료 | 착오송금인의 인감 날인된 금융 거래정보제공요구(동의)서` |
| `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#01` | 2 | 249자 | selectProtSystProtTrgtPrdctSumr | `정기적금, 주택청약부금, 상호부금 등 적립식예금`<br>`정기예금, 저축예금, 주택청약예금, 표지어음 등 저축성예금`<br>`원본이 보전되는 금전신탁 등 | 양도성예금증서(CD), 환매조건부채권(RP)` |
| `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#03` | 2 | 293자 | selectScrn | `예금보험금 등 지급청구 및 동의서`<br>`내용, 첨부 항목으로 구성된 양식 다운로드 표`<br>`현지 대사관의 공증을 받거나 해당국이 발급한 아포스티유를 첨부한 예금자 본인 명의의 위임장이어야 함` |
| `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#03` | 2 | 183자 | selectProtSystProtTrgtPrdctSumr | `자기신용대주담보금, 신용거래계좌 설정보증금, 신용공여담보금 등의 현금 잔액`<br>`원본이 보전되는 금전신탁 등 | 금융투자상품(수익증권, 뮤추얼펀드, MMF 등)` |
| `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#02` | 2 | 177자 | selectProtSystProtTrgtPrdctSumr | `특정금전신탁 등 실적배당형 신탁`<br>`주택청약저축 1 아래 도움말 참조 ,   주택청약종합저축 1 아래 도움말 참조 등`<br>`투자 매매업자·투자 중개업자 | 증권의 매수 등에 사용되지 않고 고객계좌에 현금으로 남아 있는 금액` |
| `kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn#01` | 2 | 502자 | selectScrn | `착오송금 이후 사망한 자`<br>`자금이체 금융회사등* (주석3)`<br>`착오송금 수취인 | 실지명의를 확인할 수 없는 경우` |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn#02` | 2 | 792자 | selectScrn | **후보 없음** |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn#01` | 1 | 712자 | selectScrn | `신용회복지원을 신청하기 위해서는 다음의 세가지 요건을 모두 갖추어야 합니다.`<br>`2. 최저생계비 이상의 수입이 있는 자 또는 채무상환이 가능하다고 심의위원회가 인정하는 자`<br>`채권금융회사가 부동의하게 되면 기각되며, 동의시 채무조정협의서(연체기록정보 해체)를 체결하게 됩니다.` |
| `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#00` | 1 | 379자 | selectProtSystProtTrgtPrdctSumr | `구분 | 보호 | 비보호`<br>`은행 | 보통예금, 기업자유예금, 별단예금, 당좌예금 등 요구불예금`<br>`구분[보호금융상품, 비보호금융상품], 은행, 투자 매매업자·투자 중개업자, 보험회사, 종합금융회사, 상호저축은행 및 상호저축 은행중앙회 항목으로 구성된 보호대상 금융회사 표` |
| `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn#02` | 1 | 781자 | selectScrn | `휴면계좌통합조회시스템』(www.sleepmoney.or.kr)`<br>`위임장, 위임자의 인감증명서, 대리인의 실명증표 등을 추가로 구비하여야 합니다.`<br>`* 현재 정상 영업중인 은행·보험 및 우체국의 휴면계좌 관련 정보는 전국은행연합회의 『` |
| `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#01` | 1 | 783자 | selectScrn | `상속인 본인의 확인증명`<br>`제적등본 또는 가족관계증명서`<br>`(공동·상속)미수령금 지분신고서` |
| `kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn#00` | 1 | 660자 | selectScrn | `파산 금융회사 정보 검색`<br>`지급대행점 목록 및 방문신청시 구비 서류`<br>`부실화된 금융회사의 예금자 등이 찾아가지 아니한 금액을 말합니다.` |
| `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#02` | 1 | 775자 | selectScrn | `소액 상속 간편 지급 안내`<br>`예금자가 국외거주 외국인, 유학생, 상사주재원인 경우`<br>`미성년자의 동의서는 친권자의 동의가 있어야 함(친권자의 인감증명서 필요)` |
| `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#04` | 1 | 366자 | selectProtSystProtTrgtPrdctSumr | `증권사 종합자산관리계좌(CMA)`<br>`보험회사 | 개인이 가입한 보험계약`<br>`청약자예수금, 제세금예수금, 유통금융대주담보금` |
| `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#07` | 1 | 166자 | selectProtSystProtTrgtPrdctSumr | `환매조건부채권(RP),양도성예금증서(CD), 기업어음(CP), 종금사 발행채권 등`<br>`상호저축은행 및 상호저축 은행중앙회 | 보통예금, 저축예금, 정기예금, 정기적금, 신용부금, 표지어음`<br>`종합금융회사 | 발행어음, 표지어음, 어음관리계좌(CMA) 등 | 금융투자상품(수익증권, 뮤추얼펀드, MMF 등)` |
| `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn#00` | 1 | 757자 | selectScrn | `예금자 본인의 확인 증명`<br>`예금자 본인이 찾을 경우`<br>`예금자 본인이 군복무 중일 경우` |
| `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#08` | 1 | 165자 | selectProtSystProtTrgtPrdctSumr | `상호저축은행중앙회 발행 자기앞수표 등 | 저축은행 발행채권(후순위채권 등) 등`<br>`개인종합자산관리계좌(ISA)에 편입된 금융상품 중 예금보호 대상으로 운용되는 금융상품 2 아래 도움말 참조`<br>`예금보호대상 금융상품으로 운용되는 확정기여형 퇴직연금제도 및 개인형 퇴직연금제도의 적립금 2 아래 도움말 참조` |
| `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr#06` | 1 | 90자 | selectProtSystProtTrgtPrdctSumr | `보증보험계약, 재보험계약`<br>`변액보험계약 주계약(최저사망보험금·최저연금적립금·최저중도인출금· 최저종신중도인출금 등 최저보증 제외) 등` |
| `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn#00` | 1 | 688자 | selectScrn | `착오송금 수취인 유의사항`<br>`이의제기는 온라인 [착오송금 수취인 - 이의제기] 메뉴 또한 직접 방문하여 할 수 있습니다.`<br>`지급명령 결정에 따라 반환하고자 하는 경우, 지급명령 결정문에 기재된 청구금액 등과 반환계좌를 확인하여 기한내에 반환해주시기 바랍니다.` |
| `kdic-www-sp-kmrs-kmrsItrd-selectScrn#00` | 1 | 108자 | selectScrn | `제도 소개 안내영상입니다.`<br>`잘못 보낸 돈 되찾기 서비스란 착오송금인이 실수로 잘못 보낸 돈을 최소한의 비용으로 빠르게 되찾을 수 있도록 도와드리는 제도입니다.` |
| `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn#00` | 1 | 800자 | selectScrn | `착오송금 반환지원의 절차`<br>`홍동길 하늘은행 1234-567-890`<br>`실수로 잘못 송금한 돈 돌려받을 수 있을까?` |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn#00` | 1 | 761자 | selectScrn | `최장 2년 이내에서 채무상환을 유예`<br>`무담보 채무의 경우 최장 8년(차상위 계층 이하 소득자의 경우 최장10년)간 분할상환 가능`<br>`채무감면 범위, 상환기간 등의 채무조정 내용은 대출금의 종류, 총채무액, 변제가능성, 담보, 채무자의 환경 및 신용 등을 고려하여 모두 다르게 적용됩니다.` |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn#02` | 1 | 109자 | selectScrn | `구분 | 내용 | 비고`<br>`구비서류 | 신용회복지원승인신청서`<br>`신청인 | 채무자 또는 대리인 | 대리인의 경우 채무자의 인감증명서와 위임장 (동의서)등 권리 위임에 따른 서류를 첨부하여 입증을 하여야함` |
| `kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn#00` | 1 | 362자 | selectScrn | `채무조정제도 신청 안내`<br>`구분[본인 신청시, 대리인 신청시 추가서류], 구비서류 항목으로 구성된 채무조정 신청자격 및 구비서류 표` |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn#01` | 1 | 763자 | selectScrn | `면책결정·면책불허가결정`<br>`파산절차폐지(이시페지)`<br>`파산이 선고되면 바로 면책되는 것인가요?` |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn#03` | 1 | 665자 | selectScrn | `재산 및 소득 수준 등 상환능력 심사`<br>`대국민포털 내에서도 채무정보를 조회하신 후 온라인으로 상담이 가능합니다.` |
| `kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn#02` | 1 | 117자 | selectScrn | `사망 또는 국내에 주소가 없는 경우`<br>`「채무자 회생 및 파산에 관한 법률」에 따른 회생 또는 파산절차가 진행되는 경우` |
| `kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn#03` | 1 | 469자 | selectScrn | `부당이득반환채권 매입계약 해제 요건`<br>`다음 중 하나에 해당하는 경우 공사와 착오송금인의 부당이득반환채권 매입계약이 해제됩니다.다만 착오송금인의 귀책 혹은 의사에 의해 계약이 해제되거나 착오송금인이 직접 회수하는 경우 공사가 청구하는 회수관련 비용을 상환한 후 계약이 해제됩니다.` |

- 유일한 줄로 후보를 뽑은 청크 **35/37** · 후보 없음 2개

## 미앵커가 몰린 문서

| 문서 | 미앵커 청크 | 걸린 문항(중복 포함) |
|---|---:|---:|
| `kdic-www-sp-dpstrprot-selectProtSystProtTrgtPrdctSumr` | 8 | 11 |
| `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn` | 8 | 46 |
| `kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn` | 4 | 5 |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtCredRcvrySprt-selectScrn` | 3 | 3 |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtLbltAjmtSyst-selectScrn` | 3 | 6 |
| `kdic-fins-ir-msdrpr-MsdrprAttnMttr-selectScrn` | 3 | 4 |
| `kdic-www-rb-lbltajmt-LbltAjmtSprtPsnBr-selectScrn` | 2 | 4 |
| `kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn` | 1 | 1 |
| `kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn` | 1 | 1 |
| `kdic-fins-ir-addrse-AddrseAttnMttr-selectScrn` | 1 | 1 |
| `kdic-www-sp-kmrs-kmrsItrd-selectScrn` | 1 | 1 |
| `kdic-fins-ir-aplygudn-MtrsGvbkSprtProc-selectScrn` | 1 | 1 |
| `kdic-fins-lb-lbltinfo-LbltInfoInqItrdMthdGudn-selectScrn` | 1 | 1 |
