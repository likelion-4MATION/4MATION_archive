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

## D1 (토) — 선행 처리

- **robots_status 근본 수정(0-a)**: `urllib.robotparser.read()`(기본 Python-urllib UA로 GET → KDIC 차단이 D0 unreachable 원인)를 폐기하고, `requests.get(robots.txt, UA=config.USER_AGENT)` 후 `RobotFileParser.parse(lines)`로 변경. 결과: 두 호스트 robots.txt HTTP 200 정상 파싱(www 89B·fins 80B), 정상 페이지 robots_status가 `unreachable`→`allowed`로 정확화. **GET 실패 시 fail-open 금지** — 빈 규칙+`unreachable` 기록 유지, 실제 차단은 POLICY_DISALLOW가 담당. POLICY_DISALLOW 오버레이는 이중 안전장치로 유지(robots 규칙이 Googlebot 전용이라 우리 UA엔 can_fetch=allowed로 나오므로 오버레이 없으면 fins /cm/bbs/가 뚫림). **검증**: fins /cm/bbs/ 2건 disallowed, fins /ua/·www /sp/ allowed — 기대와 일치. 즉 근본 수정 후에도 fins /cm/bbs/ 5건은 여전히 차단.
- **H6 승격(0-b)**: D1 통과 기준에 "국내 보호한도 청크에 '5천만'을 **현행 한도로** 서술하는 청크 0건" 추가. grep은 검출 수단일 뿐, 검출건은 맥락 분류(이력 설명 '종전 5천만원→1억원 상향'=정상 / 현행 서술=실패) 후 판정. 파싱 전 canonical raw 재확인: `data/raw/...ProtSystProtLmts...` 는 5천만원×0·1억원×5 → 1억원 변형(정상). (분류 결과는 T3 청킹 후 기록)
- **분석필요 xlsx(0-c)**: 여전히 부재(폴더·~/Downloads·Spotlight 0건) → 병합·link_registry 공란 2건 보류 그대로. 테스트셋 원천은 fins FAQ(차단) 대신 **www FAQ + 질문형 헤딩 페이지**로 전환(H5).

## D1 (토) — 파서→벡터DB→검색

- **파서 컨테이너**: `.contents` 채택 (32/32 페이지 1개씩 존재 확인). `#container`는 브레드크럼·타이틀 포함이라 더 넓음. 노이즈 제거: `script/style/floatTop(글자크기·언어)/floatBottom(챗봇·상단이동)/btnBottomArea(조회·신청 바로가기)/form/input/button`. 근거: KDIC 텍스트 90%+가 GNB 노이즈, 컨테이너 협소화가 규칙기반의 핵심(03 문서).
- **표 처리**: 값 유실 없이 행 텍스트("cell | cell")로 직렬화, markdown 미화는 안 함(P2). `<table>` 보유 12/32. **T2 값 유실 스팟체크 5/5 통과**(3개월·5년·2개월·15억·5억원, 5개 페이지 교차). 표값 청크 반영도 확인(양도성예금증서·뮤추얼펀드·후순위채권 등).
- **브레드크럼**: `.location` 최상위 li 직계자식 첫 링크만 → 홈>대분류>중분류>현재 (드롭다운 형제메뉴 무시). D0 extract_breadcrumb(20개 과다추출) 대체. sub_category = 브레드크럼[1:] " > " 조인.
- **coverage**: 안내부={상속인 금융거래조회}(assignment 지정, btnBottomArea 조회 기능부 제거로 안내부만 남김), 그 외 전체. 부채증명원은 분석필요라 필수셋에 없음.
- **청킹**: CHUNK_SIZE=800 · OVERLAP=100 (03 문서 노션 권고 준용, 1설정 고정). 표 블록(연속 |라인) 중간분할 금지=단독 청크. FAQ 페이지는 질문-답변 1쌍=1청크('열기' 토글 제거). MIN_CHUNK=60(표 사이 낀 짧은 파편 인접 병합). **결과 134청크(문서 32) · 스키마 11필드 전건 유효**.
- **0-b '5천만' 맥락 분류(7건)**: 예금자보호제도 5건=FAQ 사례/예시금액(1억5천만원·계좌 예시 등, 현행 한도 서술 아님) · 착오송금 2건=착오송금 한도(별개 도메인, 예금보호한도 아님) · 미수령금 상속 1건=stale 소스(H6b). **국내 보호한도 도메인의 '5천만 현행 서술' 청크 0건 → 0-b 통과.** 보호한도 페이지 청크 재확인: 1억원×6 · 5천만원×0 · 퇴직연금/연금저축/사고보험금 별도한도 서술 존재.
- **임베딩 모델**: `jhgan/ko-sroberta-multitask`(로컬 한국어 SBERT, 768d) 선택. 선택지: 다국어 MiniLM(작지만 한국어 약함) · bge-m3(강하나 2GB↑ 무거움) · ko-sroberta(한국어 STS 튜닝, ~440MB, 균형). PoC 규모(134청크)에 균형점. 오프라인 실행. FAISS `IndexFlatIP` + 정규화 임베딩(=코사인). **적재 134 = 청크 134**.
  - **확정(팀 표준 없음 → 유지)**: 로컬 PoC용 선택. 모델명은 `rag.py`의 `MODEL_NAME` 상수 한 줄로 교체 가능. 프로덕션은 CLOVA 임베딩 검토(P4).
- **하이브리드(C)**: BM25(kiwipiepy 형태소 토큰, 명사/어간/영숫자 keep · rank_bm25 BM25Okapi) + dense, **RRF(k=60, pool=20)**. 평가 결과 **hybrid가 dense를 전 지표에서 상회**: hit@1 0.865>0.827 · hit@3 0.923>0.904 · MRR 0.903>0.867 (52문항). 리랭킹·파라미터 튜닝은 D1 금지(D2 판단).
- **아키텍처(A)**: `recollect(url)=fetch→parse→chunk→upsert(by doc_id)` 원자함수(pipeline.py). content_hash=가시텍스트 sha256(D0 재현성 지표와 동일) 불변 시 parse/chunk/embed 스킵. 검증: 1차 32 upsert(134청크)·5 차단, 2차 재실행 32 skip → 재수집 트리거 프로토타입 충족(03 §4). robots_blocked/error는 store에서 제외.
- **평가셋(B)**: 52건(대표6+FAQ28+헤딩18), 6대 업무 전부 커버, 정답=문서(parent_doc_id) 단위 gt_docs 리스트. **대표 6문항 top-3: hybrid 5/6·dense 6/6 → D1 통과(5+)**. 유일 hybrid 미적중="착오송금 어떤 경우 신청?"(hybrid rank8·dense rank2) — 같은 업무 유의사항/절차 페이지가 신청대상 페이지를 밀어냄. BM25가 doc-정밀 질의에서 역효과(리랭킹으로 D2에서 해소 검토). **오염체크 0건**(국내 보호한도 top-3에 해외 수치 없음).
