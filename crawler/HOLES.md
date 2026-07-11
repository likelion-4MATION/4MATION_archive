# HOLES — 막힌 것 · 우회 · 팀 이관

> D0(금) 수집 스프린트에서 발생. 형식: 무엇이 막혔나 · 우회 방법 · 팀에 넘길 일.

## H1. 필수 건수 델타 (데일리 로그 30 ≠ 매니페스트 37)

- **막힘**: ASSIGNMENT 기준 데일리 로그 필수 30건인데, 02_검색범위정의서_초안.md의 필수(●) 표는 **37건**. 델타 **+7**.
- **원인**: 02 정의서 집계 주석 — "필수 37·분석필요 18·계 55, 노션 초기 분석(필수 33+분석필요 16=49)보다 6건 많음. 초과분은 이번 정찰 GNB 추가 발견분(fins FAQ 게시판, 보호한도 변천내역, 모의계산기 등)". 즉 30(데일리 로그)→33(노션)→37(정찰 반영) 순으로 증가.
- **우회**: 정의서(37)를 원천으로 매니페스트 확정. 임의 가감 없음.
- **팀 이관**: 노션 하위문서 "사이트맵 검색 범위 사전 조사"와 대조해 초과분(37−33=4, 나아가 55−49=6)의 포함 여부를 팀에서 확정. 멘토 확인 대기 "F4 건수 불일치"와 연결.

## H2. 분석필요태깅_포함여부분석.xlsx 부재 → 분석필요 18건 병합 보류

- **막힘**: xlsx가 폴더·~/Downloads·Spotlight 어디에도 없음. '포함' 판정분 병합 및 '링크만 5건' 판정 근거 확보 불가.
- **우회**: 필수 37건만으로 crawl_manifest.csv 확정(전 건 source=필수). build_manifest.py는 xlsx 인자를 선택적으로 만들어 CSV 단독 실행(DECISIONS 참조).
- **팀 이관 (추후 병합 필요)**: xlsx 확보 시 `python build_manifest.py kdic_필수페이지_URL매핑.csv 분석필요태깅_포함여부분석.xlsx -o crawl_manifest.csv`로 분석필요 '포함' 판정분(최대 18건 중 일부)을 병합. 병합 후 재수집·재검증.

## H3. 분석필요_예비판정.csv 부재 → 교차 확인 스킵

- **막힘**: 판정 교차 확인용 csv 부재.
- **우회**: 교차 확인 생략(스킵). 매니페스트는 정의서 단일 원천으로 확정했으므로 판정 충돌 위험 낮음.
- **팀 이관**: csv 확보 시 xlsx '포함' 판정과 예비판정 교차 대조.

## H4. robots.txt를 urllib.robotparser가 못 읽음 (전 페이지 unreachable 기록)

- **막힘**: 크롤러 로그에 `robots.txt 읽기 실패 → 보수적으로 진행`. 메타의 robots_status가 전부 `unreachable`로 기록됨.
- **실측**: `requests`로 직접 받으면 두 호스트 모두 **HTTP 200**. 즉 robots.txt는 실재. urllib이 실패하는 원인은 기본 UA(Python-urllib) 차단/넷퍼넬 트래픽제어 응답으로 추정.
  - www: `Disallow: /*List.do$`, `/*Dtl.do$`, `/../../srch/` (User-agent: Googlebot)
  - fins: `Disallow: /cm/bbs/`, `/cm/srch/selectItgrSrch.do` (User-agent: Googlebot)
- **우회**: 실측 robots 규칙을 config.POLICY_DISALLOW 오버레이로 하드코딩해 경로 패턴으로 명시 차단(H5). www 필수 URL은 List.do/Dtl.do/srch 미해당 → 정상 수집.
- **팀 이관**: 여유 시 robots.txt를 requests 세션으로 읽어 RobotFileParser.parse()에 주입하도록 개선(P4). 단 규칙이 Googlebot 전용이라 우리 UA엔 자동 미적용이므로 정책 오버레이는 계속 필요.

## H5. fins /cm/bbs/ 5건 정책 차단 (절대규칙 1) → 테스트셋 원천 막힘

- **막힘**: fins robots.txt `Disallow: /cm/bbs/` + 절대규칙 1("채무정보조회 FAQ fins /cm/bbs/ 계열 — 고객사 허용 확인 전 금지"). 매니페스트 내 해당 5건 전량 **수집 안 함(robots_blocked 기록만)**:
  - selectFaqNramtAply(미수령금 FAQ) · selectFaqMsdrGvbkAply(착오송금 FAQ) · selectFaqLbltInfoInq(채무정보조회 FAQ) · selectFaqCncmPrptDclr(은닉재산 FAQ) · selectFaqTop10(FAQ TOP10)
- **다운스트림 영향(중요)**: 03_파서_스키마_청킹_결정문서가 계획한 **평가 테스트셋 v0의 주 원천이 fins FAQ 게시판 7종 + TOP10**인데 그 계열이 통째로 막힘. D1/D2 테스트셋 규모(30~50건) 확보 경로 재검토 필요.
- **우회(D1)**: www쪽 FAQ(예금자보호 FAQ·은닉재산 FAQ, selectScrn형 — 수집됨) + 본문 h4 질문형 헤딩(신청대상 페이지 등)에서 Q&A 추출로 대체.
- **팀 이관**: 고객사에 fins /cm/bbs/ 수집 허용 확인. 허용 시 POLICY_DISALLOW에서 fins 항목 제거 후 재수집하면 5건 즉시 편입.

## H6. 보호한도 페이지 각주 금액 토큰 비결정성 (verify_rerun 1건 불일치)

- **막힘**: `verify_rerun run1 run2` — 32건 중 **31건 완전 일치, 1건 불일치**. 불일치 doc = `kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn`(보호한도, 1억 상향 핵심 페이지). text 9653↔9654자.
- **원인**: 본문 각주(도움말/greenBox '보험사고' 정의) 안의 보호금액 토큰이 서버측에서 **"1억원" ↔ "5천만원"(구버전)** 으로 비결정적으로 렌더. 관측 6회 중 **5천만원 1회**(run2), 나머지(run1+추가 4회 조회)는 1억원. 저빈도 → 로드밸런스 캐시 노드 스테일/CMS 글리치 추정. **크롤러 결함 아님(외부 사이트 비결정성)**.
- **콘텐츠 리스크(중요)**: 하필 대표 질문(예금보호한도 1억)의 페이지에서 구버전 5천만원이 간헐 노출 → 청킹 시 오답 소스가 될 수 있음.
- **우회(D1)**: 이 페이지 본문의 한도 표/헤딩은 일관되게 1억원. 파서에서 각주 '보험사고' 금액 토큰을 (a) 휘발성으로 간주해 청크 제외, 또는 (b) 현행 한도(1억원)로 정규화, 또는 (c) 5천만원 감지 시 재수집. 캐노니컬 data/는 정상 변형(run1, 1억원)으로 채택.
- **팀 이관**: 예보 담당자에 각주 스테일 값 문의(캐시 무효화 요청). 테스트셋에 "5천만원 함정" 케이스 반영.

## H7. link_registry 외부 담당기관 URL 미확보 (창작 금지)

- **막힘**: link_registry 6건 중 외부 담당기관 실제 URL은 xlsx '링크만' 판정에 있었으나 xlsx 부재. 02 정의서엔 외부기관 URL 없음(KDIC 자체 안내 페이지만 존재).
- **우회**: 창작 금지 원칙 준수. url 필드는 **02 정의서에서 확인되는 URL만** 채움 —
  - 채움(4): payout_target_search(지급대행점 조회, KDIC 동적) · credit_recovery/bankruptcy_discharge/personal_rehabilitation(KDIC 채무조정 안내 페이지)
  - 공란(2): overseas_deposit_protection(해외 예금보험기구 URL 문서 없음) · illegal_act_report(불법행위신고, 측정후결정 A/B 보류)
- **팀 이관**: xlsx '링크만' 판정 확보 후 (a) 신용회복위원회·법원·해외기구·금감원 등 실제 외부 URL로 교체, (b) 4건의 KDIC 안내 URL이 최종 링크로 적절한지(외부기관 직링크 대체 여부) 판단. org 필드도 xlsx 판정과 교차 확인.

## H8. breadcrumb 과다 추출 (GNB 전체 20개)

- **막힘**: crawler.extract_breadcrumb가 best-effort로 GNB 전체 메뉴(~20개)를 수집. 예: 보호한도 페이지 breadcrumb에 '통합검색·모의계산기·예금보험료안내' 등 형제 메뉴가 섞임. title도 탭·개행 포함 다단 문자열.
- **영향**: D0 통과 기준(breadcrumb·title 비어있지 않음)은 충족. 단 sub_category 원천으로 쓰기엔 노이즈.
- **우회/팀 이관(D1)**: 03 문서 설계대로 "홈으로 시작하는 ol의 각 li 첫 링크만" 취하도록 파서 정제. title은 마지막 세그먼트만 취득.
