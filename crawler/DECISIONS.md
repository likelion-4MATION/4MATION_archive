# DECISIONS — 기술 선택·판단 로그

> 형식: 선택지 · 결정 · 근거. D2 핸드오프 보고서가 이 파일을 소스로 씀.

## D0 (금) — 수집 파이프

- **매니페스트 원천**: 02_검색범위정의서_초안.md vs 실물 kdic_필수페이지_URL매핑.csv(부재) → **02 정의서를 원천으로 필수 37건 확정**. 근거: csv 실물 없음이 사용자 확인됨, md가 단일 진실 원천.
- **kdic_필수페이지_URL매핑.csv 생성 방식**: 02 정의서 필수(●) 표 37행을 형식만 변환(사용자 승인). 컬럼 url·business_function·sub_category·page_type·coverage·variant. 근거: 규칙 7(임의 재구성 금지)의 승인된 예외. **sub_category·coverage·variant는 정의서에 없어 공란**(내용 창작 금지) — D1에서 브레드크럼/페이지 유형으로 채움. page_type엔 정의서 '페이지' 라벨을 그대로 보존.
- **build_manifest.py analysis_xlsx 선택 인자화**: 필수 positional → `nargs='?'`. 근거: 분석필요 xlsx 부재 시에도 필수 CSV 단독으로 매니페스트 확정 필요(사용자 지시 #3). 컬럼 자동 탐지·미리보기 로직은 그대로.
- **매니페스트 병합 결과 검수**: 컬럼 매핑 6/6 정확 일치, 37건 전량 source=필수, 링크만/제외/보류 유입 0건(xlsx 부재로 애초에 없음). 미리보기 눈 확인 완료.
- **robots 준수 방식**: urllib.robotparser가 KDIC robots.txt 읽기 실패(전 페이지 unreachable) + 실측 규칙이 Googlebot 전용이라 우리 UA엔 자동 미적용. → **config.POLICY_DISALLOW 경로 오버레이 신설**로 명시 차단. 근거: 절대규칙 1 준수는 robots 기술적 해석보다 우선. fins /cm/bbs/·www List.do/Dtl.do/srch를 실측 robots.txt대로 하드코딩. 차단 건은 수집 안 하고 report 기록만.
- **fins /cm/bbs/ 처리**: 매니페스트에 유지(화이트리스트, 규칙 6) + robots_blocked로 차단(규칙 1). 근거: 규칙 6(매니페스트=화이트리스트)과 규칙 1(disallow 수집 금지) 양립 — 목록엔 남기되 수집만 차단. 고객사 허용 시 즉시 해제 가능.
- **USER_AGENT contact**: TODO@example.com → hyunuk200202@gmail.com(현재 담당자). 근거: 팀 공식 주소 미확정. 확정 시 교체(주석 명시). KDIC 서버로 매 요청 전송되는 값이므로 공식 주소 권장.
- **재현성 판정 기준**: text_sha256 유지(raw는 CSRF/세션값 변동). 보호한도 1건 불일치는 **외부 사이트 비결정성(각주 금액 토큰 1억원↔5천만원)** 으로 판정 — 크롤러 결함 아님(HOLES H6). 크롤러 자체는 31/32 완전 재현.
- **캐노니컬 data/**: run1을 채택(보호한도=1억원 정상 변형). run2는 5천만원 스테일 변형 포함이라 미채택. run1/run2 디렉토리는 재현성 증거로 보존.
- **link_registry url 정책**: 02 정의서에서 확인되는 URL만 채우고 미확보분 공란 + HOLES 기록(사용자 지시 #5, 규칙 T3 창작 금지). 4건 채움/2건 공란. keywords는 함정 대비 각 5개(동의어 3+ 충족).
