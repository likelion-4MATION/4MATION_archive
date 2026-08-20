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

## 07-13 (일) — HOLES 해소 세션 (0-c 병합 · H7/H8 정리)

- **xlsx 복원본 판정 분포(12행 — H1 경위 대조 자료)**: `분석필요태깅_포함여부분석.xlsx` Sheet1, 판정컬럼=예비판정. **포함 2**(no.1 예금자보호 FAQ · no.5 착오송금 신청대상) · **포함(안내부) 2**(no.4 상속인 금융거래조회 · no.9 부채증명원/금융거래정보신청) · **포함(D5대기) 1**(no.10 fins 채무정보조회 FAQ) · **링크만 5**(no.2 해외 보호한도 · no.3 지급대상 금융회사 검색 · no.6 신용회복 · no.7 파산면책 · no.8 개인회생) · **측정후결정 1**(no.11 불법행위신고 — 단 '최종 판단 근거' 텍스트는 "링크만…링크 전달"로 정제) · **제외 1**(no.12 부실책임조사 진행현황 조회). **주의: xlsx는 12행 — 02 정의서 집계 '분석필요 18건'·노션 초기 16건과 모두 불일치(H1 델타 대조 시 함께 확인 필요)**.
- **분석필요_예비판정.csv 부재(H3)**: 작업 폴더·~/Downloads 재탐색 0건 → 외부 교차 대조 불가, H3 잔존. 대체로 xlsx 내부 대조(예비판정 vs 최종 판단 근거) 수행 — 충돌성 항목 1건: no.11 예비판정 '측정후결정' vs 최종판단 '링크만'(병합 판단엔 무영향 — 두 판정 모두 비수집, link_registry 충전 근거로는 최종판단 채택). no.3도 다음액션("안내부 텍스트만 수집")과 최종판단("데이터 낡음 → 링크만")이 상충하나 예비판정=링크만 기준 비수집 유지.
- **build_manifest.py 병합 전 수정(자동매핑 검수 반영)**: ① 판정컬럼이 variant 힌트 '판'에 걸려 `variant←예비판정` 오매핑 → 판정컬럼을 필드 매핑에서 제외. ② `page_name`을 page_type 힌트에 추가(필수 CSV의 page_type=페이지 라벨 관행과 정합). ③ xlsx 업무명 번호 프리픽스('5. 채무조정 안내') 제거 — 기존 청크 business_function 표기와 통일. ④ 판정 '포함(안내부)' → coverage=안내부 전파(판정 텍스트 유래, 창작 아님). 근거: docstring의 "미리보기 눈 확인" 절차를 재현 가능하게 코드화.
- **병합 결과(0-c 완료)**: 37→**38건**(+부채증명원 1건, source=분석포함·coverage=안내부). 기존 37건 무변경(diff 확인). xlsx 포함 판정 중 3건(FAQ·상속인·착오송금 신청대상)은 필수와 URL 중복 → dedup(필수 우선). fins 채무 FAQ '포함(D5대기)'는 '대기' 필터로 병합 배제 — 이미 필수 매니페스트에 존재하며 **POLICY_DISALLOW 차단 유지(H5 허용 회신 전 수집 금지, robots_blocked 기록만)**.
- **link_registry 6건 전량 url 충전(H7 완결)**: ① illegal_act_report — 라이브 검증(200) 후 충전. 페이지 실체가 **예보 자체 '금융부실관련자 불법행위 신고센터'**(횡령·배임 신고 → 부실책임조사 → 수사의뢰, 02-758-0797)로 확인돼 기존 message의 "금감원 접수" 단정을 보정(부실관련자 불법행위=예보 소관 / 불법사금융·채권추심=금감원 병기). 판정 근거는 xlsx no.11 최종판단("재확인 후 링크 전달") — 측정후결정 A/B는 링크만으로 확정. ② overseas — xlsx no.2 '링크만' 판정 URL(KDIC 자체 해외 한도 비교표, 검증 200·'25.12 기준 한국 1억원)로 충전. **수집·청킹은 계속 제외**(타국 수치 오염 방지). FDIC/IADI 외부 직링크는 문서 미확보 → 창작 안 함. ③ 기존 4건(지급대행점·신용회복·파산면책·개인회생) — xlsx no.3/6/7/8 '링크만' 판정·소관 org 교차 일치 확인, 외부 직링크는 xlsx에도 없어 KDIC 안내 URL 유지. 지급대행점 조회 URL도 라이브 검증(200, 동적 검색 폼). 검증 3건 모두 저장 없음(수집 아님).
- **증분 recollect(38건)**: 31 skip · 2 upsert(부채증명원 신규 2청크 + 보호한도 재적재 2청크) · 5 robots_blocked(fins /cm/bbs/ 전부). **인덱스 136청크 · 문서 33 · faiss=emb=chunk_meta=chunks.jsonl 전부 136 일치 · 스키마 위반 0**. crawl_report.json 38건 기준 갱신(ok 33 / robots_blocked 5).
- **보호한도 upsert 원인 분석(H6 관측 추가)**: 07-13 저녁 fetch 텍스트가 **D0 캐노니컬 run1과 완전 동일**(9653자 · 5천만 0 · 1억 5)인데 스토어 해시와 불일치 → 재적재됨. 즉 오전(11:05) 인덱스 빌드 시점의 보호한도 텍스트가 다른 변형(H6 비결정성)이었다는 방증. recollect 트리거가 스테일을 자가 치유한 사례 — 현 인덱스는 정상 변형 확정.
- **pipeline.py 확장**: 라이브 recollect 실행 시 crawl_report.json을 run_crawl.py와 동일 스키마로 갱신(skipped/upserted→fetch 관점 ok 매핑). 근거: 매니페스트 38건 확장 후 리포트가 37건 기준으로 낡는 문제 — run_crawl 재실행(전량 이중 크롤) 없이 산출물 규약 유지.
- **crawler.py 레거시 정리(H8 완결)**: D0 best-effort extract_breadcrumb(GNB ~20개 과다 추출) 제거, parser의 D1 정제판(.location 직계 li 첫 링크만)을 crawler가 import해 단일 소스화 — data/meta breadcrumb도 정제판으로 기록됨(라이브 fetch 시 전 문서 meta 갱신 확인). tests/test_guards.py 픽스처를 실물 KDIC DOM(ol>li 직계+ulSelectBox 드롭다운)으로 교체, 드롭다운 형제 제외 검증 포함 8/8 통과.
- **신규 문서 검증(부채증명원)**: breadcrumb `['홈','제도·정책','지원자금관리','부채증명원/금융거래정보신청']` — 신규 유형(sprtfund 계열)에서도 .location 구조 유지(H8 재검증 통과). coverage=안내부 반영(parser COVERAGE_ANNAE 등록). 구비서류 표 값 전량 보존(공인인증서·휴대폰·위임장·인감증명서 등). **관찰 1**: 표 셀 내부 `<br>` 다항목이 비-파이프 라인을 생성해 표 원자성 휴리스틱(연속 |라인)이 끊김 → 긴 표가 행 경계에서 청크 분할될 수 있음(값 유실 없음·오버랩 유지, HOLES H13 신설·P2 표→markdown 파싱 근거 사례). **관찰 2**: 페이지 원문의 교부방법/유의사항 문단이 '경력증명서/확인서'를 언급(부채증명원 문맥과 불일치 — KDIC 원문 자체 오기 추정), 무수정 원칙에 따라 보존.
- **0-b 확장 재검증('5천만' 전수, 136청크)**: 검출 청크 6 · 발생 8회 — ① 예금자보호 FAQ 4청크(#03/#09/#11/#14) = 사례·예시금액(1억5천만원 적립금, 3/4/5천만원 계좌 예시 등)이며 현행 한도는 일관되게 1억원 병기 → 정상. ② 상속인 조회 1청크 = H6b 기지 stale(미수령금 도메인, 제외 대상). ③ 착오송금 반환지원절차 1청크 = H9 기지(별개 도메인 한도, 예솜이 웹툰 인용 stale). **국내 보호한도 도메인 '5천만 현행 서술' 0건 → 통과.** 신규 stale 발견 0(부채증명원 검출 없음), 보호한도 페이지 청크 1억원×6·5천만×0. 소스 무수정 유지. (D1 '7건'과의 수치 차이는 셈법(발생 vs 청크) 차이 — 이번 기록 기준: 청크 6·발생 8)
- **평가 재실행(52문항 유지)**: dense 3지표 D1 대비 ±0(.827/.904/.867), hybrid hit@1 .865·hit@3 .923 ±0, MRR만 .903→.900(−0.003 — 신규 2청크 BM25 idf 편입에 따른 미세 변동, 회귀 아님). 대표 6문항 문항별 랭크까지 D1과 동일(hybrid 5/6·dense 6/6, 유일 미적중=H10 기지). 오염체크 0건 — 해외 페이지는 미수집(링크만)이라 구조적으로 혼입 불가. **평가 문항 확장은 안 함** — 부채증명원 문항 갭(커버리지 1문서)만 eval_report에 기록, 팀 확장 시 2~3문항 권장. eval_report.md에 D1 델타 병기(수기 주석 — eval.py 재실행 시 재생성되므로 본 항목이 원본 보존).

## 07-21 (화) — 실전2 P0: 검색·체인 인터페이스 계약

- **rag.Searcher 계약 동결 — 코드 무수정**: `search(query, k=5, mode="dense"|"bm25"|"hybrid") -> list[dict]`. 반환 = 청크 메타 11필드 flat + `_score` 부가, **리스트 순서 = 랭크**(별도 rank 필드 없음), 출처 조립은 `page_title`·`source_url` 사용. mode 유효값 3종이며 그 외 문자열은 hybrid로 폴백(실물 동작). 선택지: 중첩 반환(`{"chunk","meta","score","rank"}`)으로 재설계 vs 실물 유지 → **실물 유지 채택**. 근거: eval.py가 flat 구조(`c["text"]`·`c["parent_doc_id"]` 등)를 이미 소비 중이라 반환 변경은 불가침 원칙의 eval.py 연쇄 수정을 유발. 이후 검색 개선(업무 필터·리랭커·Parent-Child)은 전부 이 시그니처 **뒤에서** 수행 — 입출력 불변이 트랙 병렬화의 전제.
- **`filters` kwarg 지금 미추가**: optional kwarg는 후행 추가해도 기존 호출부 하위호환(파이썬 시맨틱). B트랙 business_function 필터 구현 시점에 `filters: dict | None = None`으로 편입 예정 — 자리 예약만 계약에 명시.
- **`_score` 스케일 경고 — 저신뢰 가드 설계 제약**: 모드별 스케일 상이. dense=코사인(대략 0.3~0.8대) / hybrid=RRF 점수(rrf_k=60 기준 이론 최대 2/61≈0.033) / bm25=원점수. **hybrid `_score`에 절대 임계값 직접 적용 금지.** confidence 정의(dense 코사인 병기 / top1–top2 마진 / 순위 기반 중 택1)는 HCX 스파이크에서 실측 후 확정.
- **answer() 계약 초안 — 동결 아님**: `answer(query) -> {"text": str, "sources": [{"title","url","doc_id"}], "confidence": float, "route": "rag"|"link"|"reject"}`. route 하나로 정상 답변/소관 밖 라우팅/저신뢰 거절 분기까지 UI가 구분(D트랙 mock 기준). confidence 정의 확정과 함께 동결하며, 4필드는 축소 없음 보장(필드 추가만 가능).
- **베이스라인 버전 규약(v1 락)**: dev 병합본 기준 `pipeline.py --use-cache --rebuild` → eval 재현(기대: hybrid hit@3 .873/150) 확인 후 `data/chunks.jsonl` + 평가셋(eval.py TESTSET 경로 파일)의 sha256과 HEAD SHA를 `data/baseline_v1.lock`으로 커밋. 이후 모든 평가 리포트에 corpus/testset 버전 병기, 코퍼스·라벨 변경이 dev에 랜딩할 때마다 동일 절차로 v2·v3 재락. 근거: 팀 병행 작업(코퍼스 확장·라벨 재교정·URL 태깅) 중 수치 변동의 원인 분리(검색 개선 vs 데이터 변경) — 07-13 MRR −0.003 미세 변동 같은 사례를 버전 축으로 귀속시키기 위함.

## 07-21 (화) — 실전2 ②: 베이스라인 v1 락 (B4 판정 · 코퍼스 경위 · .873 정정)

- **B4 수치 판정 — 재현 성공(계획치 .873은 오기, 다음 항목에서 정정)**: 재빌드 코퍼스 215청크 기준, eval.py(TESTSET=merged) hybrid **.673/.853/.768**(h3_macro .835) · natural(sed 사본으로 TESTSET만 교체한 무수정 측정) hybrid **.513/.753/.647**(h3_macro .759). 07-15 hw 페어 평가(원본 .667/.853/.765 · 자연어 .520/.753/.650)와 **hit@3 정확 일치**, dense는 양 셋 3지표 전부 소수점 셋째 자리까지 동일(.567/.727/.661 · .420/.680/.562) — 임베딩·FAISS 경로 완전 재현. hybrid hit@1·MRR ±1문항(±.003)은 부채증명원 +2청크의 BM25 idf 효과(07-13 "MRR −0.003" 선례와 동규모·동성질, 회귀 아님). 대표 6문항 5/6 유지 — 미적중(보호한도 질문 top-3를 미수령금 FAQ가 점유)은 07-15 ys 세션부터의 기지 D2 과제, 회귀 아님. 평가셋 두 파일의 blob 불변도 확증: merged 현재 blob=08f3a81 시점과 동일(e926e2d95d) · natural 현재 blob=1e80c58(#064 수정) 시점과 동일(95c43a17e5) — 재현 성공 판정의 마지막 조각.
- **".873 = 자연어화 평가셋" 표기 정정(재발 방지 기록)**: .873은 **07-15 ys 로컬 · merged(원본 질문) 기준** 수치(재라벨 68건+FAQ 페이지네이션 수정 직후 .580→.873). 자연어화 셋의 공식 수치는 **.753**. 수치 계보: .923(52건, 자기참조 부풀림) → .580(150 확장, gt 오류 노출) → .853(hw 로컬)/.873(ys 로컬)(재라벨) → .753(자연어화, 정직 수치). 발표 프레이밍 "공식 .873 / 자연어 조건 ~.75"(07-20 확정) 유지. 위 계약 섹션 "베이스라인 버전 규약" 항목의 기대치 ".873/150"은 이 오기에 기반한 계획치였음(원문 유지, 본 항목이 정정). **잔존 미해명 1건**: 동일 merged 셋에서 ys 로컬 .873 vs hw 로컬 .853의 3문항 크로스머신 격차 — BM25 토크나이저(kiwipiepy) 버전 차이 의심, ys에 재측정(현 dev 재빌드 후 eval.py 실행 + kiwipiepy 버전 회신) 요청. 락은 hw 재현치 기준이며 회신 후 HOLES 등재 여부 판단.
  - **[상태 07-21] ys 재측정 보류 — 판별은 v2 재락으로 이월**: kiwi 완전 동일 확인(엔진 0.23.2 · 사전 0.23.0 양쪽 일치 — **토크나이저 가설 기각**), Python만 상이(hw 3.11.9 / ys 3.13.7 — venv 세대 차이의 간접 지표, 직접 요인 아님). ys가 dataset2 코퍼스 확장 작업 중이라 dev 재실행 요청은 비용 대비 실익 낮음 판단(hw). 확장분 랜딩 → **v2 재락 시 ys의 v2 수치 재현 여부가 곧 크로스머신 vs 크로스상태(07-15 미커밋 로컬 상태) 판별 실험**이 됨 — 별도 요청 없이 자동 판별. v1 유효성 무영향(락=hw 재현치 기준으로 이미 유효). 유상 메시지는 재측정 요청 제외 2건(머지 유실 공유 · merged canonical)으로 축소.
- **코퍼스 경위(211→215) — dev 병합본 아티팩트 후퇴 2건 복원**: dev의 chunks.jsonl(211청크)은 독립 유실 2건의 누적 상태였음. ① 부채증명원 2청크 — 07-15 전량 재빌드(08f3a81)가 **구 매니페스트(38행·DebtDlng 0행=37건)** 로 수행되어 213에 원천 미포함. 즉 "매니페스트 38건·213청크" 페어는 성립한 적 없음(213=37건 코퍼스; 현 매니페스트 39행·DebtDlng 1행으로 확증). ② 보호한도 2청크 — 07-20 머지(a923d57) 충돌 해소 중 소실. 양 부모(466816d=213 · 80b513b=136) 모두 동일 text 해시(e56a6afcaea7·8e6416cd163c) 보유 → H6 변형 충돌 아님, 대형 JSONL 수동 해소 과정의 누락. **검증**: 재빌드 215 = 08f3a81 공통 213청크 text 해시 전부 동일 + 부채증명원 2청크만 추가(전용 0/2·공통 불일치 0) · 인덱스 정합 faiss=emb=chunk_meta=chunks.jsonl=215 · 스키마 위반 0. **재발 방지 제안(P2 논의)**: 생성물 JSONL(chunks 등)은 머지 충돌 해소 대상에서 제외하고 재빌드로 확정하는 규약.
- **baseline_v1.lock 구성 확정**: sha256 3종 — chunks.jsonl(7528f31b…) · testset_merged(a5073d3e…) · testset_natural(b575658a…) + 주석 1줄(HEAD 50530d9 · corpus=215 · merged_h3=.853 · natural_h3=.753). 평가셋을 단수가 아닌 **2종 병기**로 락: merged=gt 진실원본·공식 수치 연속성(eval.py 담당) / natural=정직 벤치마크(eval_pair.py 담당) — 07-15 역할 분리 구조를 그대로 버전 축에 편입. 따라서 **eval.py TESTSET=merged 유지, 코드 무수정** — B2 경로 판정 결과 "TESTSET≠natural"은 불일치가 아니라 공식 수치 계보와의 일치였음(불가침 보존, 소유자 조율 불요). 이후 모든 평가 리포트에 corpus v1 · merged .853 · natural .753 병기.
- **구 testset.jsonl 처리 미결 승계**: data/testset.jsonl(원본 52건, 재라벨 미반영 18건 stale) 잔존 확인. merged canonical 명문화(구 파일 동기화 or 폐기)는 07-15 미결 그대로 — ys 라벨 확장 작업 완료 후 팀 결정. 그 전까지 신규 산출물의 gt 조인은 merged 기준(07-15 처리 방침 유지).

## 2026-07-22 — CC end-to-end 데모용 임시 결정 (사람 정식 서명 아님)

> 아래 항목은 실전2 end 구현/데모(D트랙 포함, 별도 담당자 분리 없이 이어서 진행)를
> 굴러가게 하기 위한 임시 채택값이다. 팀 차원의 정식 논의·서명은 별도로 진행 예정.
> 원본 포인터: 계약·베이스라인 = 07-21 두 섹션 / 밤1 실측 = `exp/night1_report.md` /
> 트랩셋 원본 = `exp/trapset_v0.jsonl` / 관통 코드 = `chatbot/chain.py`.

- **confidence 표시**: dense 코사인 top1, UI 문구 "관련 문서 유사도" (임시)
  - 근거: 밤1 T2 실측 — AUC merged .716/natural .562로 3후보 중 최강이나
    분포 중첩(미적중 문항도 .7734)으로 "정답 확신"이 아닌 "문서 유사도"임을 명시.
- **라우팅 방향**: 질문 분류 선행 + LLM 프롬프트 방식 채택 (임시, 실제 구현은 밤2 이월)
  - 근거: 검색 신호(bf 다수결·dense 대역) 단독으로는 라우팅 분리 불가(밤1 실측,
    reject 기대 트랩 11문항 중 10문항이 bf 다수결 통과).
  - 참고: LLM 분류 채택 시 질문당 HCX 콜이 1회 추가(분류+생성 2콜) — 콜 예산 재산정 필요.
- **트랩셋 20문항**: `exp/trapset_v0.jsonl` 4유형 확인 완료 — 해외 보호한도(5, reject) ·
  타기관 소관(5, reject) · 업무 혼동(5, 4×rag+정정/1×reject) · 구정보 확인형(5, rag+정정).
  reject 11 / rag+정정 9 일치 확인. **라벨 정식 검수는 미완**(draft=true 전 행).
- **answer() 인터페이스**: 기존 계약(text/sources/confidence/route + 부가 checks/_meta)
  그대로 임시 동결. 4필드 축소 없음 보장, route 내부 구현(라우팅 로직)만 이후 교체 가능.
- **allow_context_urls**: False로 임시 확정 — sources 목록에 없는 URL은 본문 유래여도 플래그.
  전야 Q5(ccrs.or.kr, 본문 유래) 케이스가 이 기준으로는 걸림(날조 방지 엄격 쪽 선택).
  기존 소급 판정표(참양성6·경계1·거짓양성0, allow_context_urls=True 기준)는
  False 기준으로 재실행 필요(미실행).
- **link route**: 미구현 상태로 훅만 유지(`chain.py`의 `_route()`는 항상 "rag").
  타기관 안내 URL 목록은 추후 채움.
- **거절응답 검증 예외**: `answer_checks.py`에 `_is_rejection()` 패턴 감지 추가,
  거절 문구("확인되지 않는", "안내된 내용이 아니" 등) 감지 시 `check_citations`의
  "출처 번호 미표기" 오탐 방지. 정상 답변의 출처 누락은 계속 플래그됨(검증 완료).

## 2026-08-20 — P0-1: feature/kokopas 부분 stash 복원 확인 (유실 아님)

`stash@{0}` (`WIP on feature/kokopas: b1ea86d`)이 그대로 남아 있음을 확인. **유실 아님** —
60d3f86 커밋 시 chunk.py 변경분만 빠뜨렸을 뿐, stash 자체는 온전.

- **stash@{0} 내용**: chunk.py(19줄) + rag.py(71줄) + 기타 데이터 파일. 두 파일 다 들어있음.
- **chunk.py**: `OVERLAP` 100→200, `split_generic()`에서 표 블록도 먼저 인접 텍스트와
  병합 시도(CHUNK_SIZE 이내면 합침) 후 초과 시에만 단독 청크로 플러시 — "표 병합 청킹".
  현재 워킹트리 `chunk.py`는 stash 베이스(`eb32e6b`)와 diff 없음 = **아직 미적용 상태**.
  워킹트리에 uncommitted 변경 없음 (`git status --short` 결과 없음) → stash pop 시 충돌 없이 깨끗하게 적용 가능할 것으로 보임(미검증, 실제 pop 전 재확인 필요).
- **rag.py 비교**: stash 버전과 60d3f86 커밋 버전이 **다른 값**을 채택하고 있음.
  - stash: `BF_DOC_CAP=5`, `SIBLING_BOOST=0.10`, `SIBLING_TOPN=5` — 커밋 메시지 근거상
    v9_dupfix2 grid에서 hit@5=.830 (해당 grid 내 최선).
  - 60d3f86(현재 HEAD): `BF_DOC_CAP=4`, `SIBLING_BOOST=0.05`, `SIBLING_TOPN=3` — 커밋 코멘트가
    스스로 "사용자 지정 복원값"이라 칭하며 hit@5=.808. 같은 코멘트 안에 "0.10/5 조합이 .830으로
    더 높게 나온 기록 있음 — 재현/비교 필요 시 이 값으로 바꿔 다시 돌려볼 것"이라고 자인.
  - 즉 **현재 HEAD가 stash보다 낮은 성능 값을 채택한 상태로 배포됨**. grid 최선값(stash)이
    사람 지정값(커밋)으로 대체된 이유는 커밋 메시지에 없음 — 왜 낮은 값을 의도적으로
    골랐는지 불명. P0-2 (A)/(B) 결정 시 "sibling-boost 파라미터를 stash 값(0.10/5/cap5)으로
    되돌릴지, 커밋된 값(0.05/3/cap4)을 유지할지"도 함께 결정해야 함 — 이건 원래 P0-2가
    묻던 A/B 축과는 별개의 세 번째 축이므로 사람 확인 필요.
- **chunk_embed_text (anchor 임베딩) 부분**: stash와 HEAD 사이 diff 없음 — 이미 d547597에서
  별도로 반영된 것으로 확인, P0-1 범위 밖.
- **다음 단계**: P0-2 진행 가능(스태시 유실 없음 확정). 단, (A)/(B) 결정과 별개로
  sibling-boost 파라미터값 자체(stash 0.10/5 vs 커밋 0.05/3)를 어느 쪽으로 할지
  사람 승인 필요 — 자동으로 stash 값으로 덮어쓰지 않음.

## 2026-08-20 — P0-2 적용 · P0-3: GT 181청크 재매핑

- **P0-2 적용 완료**: (B) anc 방식 채택(사람 승인). `chunk.py`·`rag.py` anc 버전으로 교체,
  `rag.py`의 `chunk_embed_text()`만 kokopas 값(anchor 임베딩)으로 되돌림. `faq_bf_map.py`
  anc에서 추가(import 의존성). anc에 `SIBLING_BOOST` 로직 자체가 없어 P0-1이 남긴
  "sibling-boost 파라미터 stash값 복원 여부" 질문은 **자동 해소**(그 로직이 사라졌으므로
  선택지 자체가 없음). 인덱스 181청크로 재빌드 완료.
- **P0-3 GT 재매핑 — `promote_gt_anchors.py` 새로 안 짬, 기존 `build_gt_dupfix.py` 재사용**:
  `gt_natural450_v9_dupfix2.jsonl`이 옛 215청크 `chunk_id` 기준이라 새 181청크 corpus 채점 시
  신뢰 불가(Hit@5=.741, anc 자체 .831대와 괴리)였던 문제. `build_gt_dupfix.py`(anchor_span
  verbatim 매칭, old id 존재 여부 무관하게 동작)를 새 corpus로 재실행 → 89/450건 gt_chunk_ids
  갱신, 완전 깨진 6건(zero-valid-gold) 전부 복구. 재평가 결과 **Hit@5 .741 → .812**로 신뢰
  가능 범위 확보. 상세 수치·재현 절차·잔여 미결(v2 dupfix는 old-id 임베딩 조회라 그대로 못
  씀)은 `crawler/data/session_handoff_0820_gt_remap.md` 참고.

## 2026-08-20 — P0-4: anc 차이점 개별 격리 검증 · 최종 baseline 확정 (Hit@5 .812 → .821)

P0-2에서 anc를 통째로 채택했으나, anc가 kokopas 대비 실제로 바꾼 항목(TABLE_GAP,
FAQ BF map, MOAI router, retrieval 파라미터, 그 외 질의측 로직)을 **하나씩 격리해**
같은 GT(`gt_natural450_v9_dupfix2.jsonl`, 448문항, hybrid_bf)로 재검증했다. 한 번에
여러 변경을 섞지 않고, baseline(P0-3, Hit@5=.812) 대비 개별 효과만 측정.

**rag.py — 개별 결과**(baseline Hit@1/3/5/10 = .469/.717/.812/.884):
| 변경 | Hit@1 | Hit@3 | Hit@5 | Hit@10 | 판정 |
|---|---:|---:|---:|---:|---|
| 질의 키워드 가중치 anc→kokopas 복원 | .464 | .717 | .812 | .886 | 기각(잡음 수준, Hit@1 소폭 악화) |
| 패싯 규칙 복원("방문접수/구비서류"→"신청방법", anc가 제거했던 것) | .469 | .719 | .812 | .891 | **채택**(전 지표 비하락) |
| sibling-boost 복원(SIBLING_BOOST=0.05/TOPN=3, kokopas 옛값) | .469 | .714 | **.801** | .882 | 기각(Hit@5 -0.011 악화 — 표가 자기완결적인 181청크 코퍼스에서 역효과, DECISIONS 이전 우려대로) |
| RRF_ALPHA/RRF_K/BF_BOOST/FACET_BOOST/BF_DOC_CAP → kokopas 값(0.6/5/0.04/0.1/4) | .471 | .730 | .812 | .886 | **채택**(전 지표 비하락, Hit@3 +0.013) |
| FAQ BF map(fbm 조인) · MOAI router 배선 | — | — | — | — | **제거**(로컬에 bf_map.jsonl·라우터 체크포인트 없어 두 경로 다 상시 폴백 = 코드상 no-op 증명. 죽은 코드만 삭제, 동작 변화 없음) |

위 채택분(패싯 규칙 + kokopas 파라미터 + FAQ맵/router 제거)을 합쳐 재검증:
**Hit@1/3/5/10 = .473/.732/.821/.893 — 전 지표 개선.**

**chunk.py — TABLE_GAP_MAX 대조군 실험은 중도 폐기**: TABLE_GAP_MAX=0(옛 동작)으로
재청킹해 표 병합/OVERLAP 축과 분리 검증하려 했으나, 청크 수가 181→215로 회귀해
(재청킹 10분+GT 재매핑 필요) 방향 전환 — 이미 anc의 TABLE_GAP_MAX=12는 코퍼스
실측 근거(코드 주석에 명시: 흡수 구간 37개 중 최장 11줄, 전부 실제 셀 내용, 산문
오흡수 0건)로 정당화돼 있어 **추가 격리 스윕 없이 그대로 확정**(탑다운 — 이미
근거가 있는 결정은 재실험하지 않는다). OVERLAP=100·split_generic(표는 항상 단독
플러시, 병합 없음)도 anc 그대로 유지. chunk.py는 kokopas 대비 anc와 100% 동일.

**최종 baseline**: Hit@5 = **0.821**(n=448, `gt_natural450_v9_dupfix2.jsonl`,
hybrid_bf, 181청크). chunk.py=anc 그대로, rag.py=anc 골격 + kokopas 파라미터/패싯
규칙 + chunk_embed_text(anchor 임베딩, kokopas) + FAQ맵/router 코드 제거.
`crawler/faq_bf_map.py`는 삭제하지 않고 보존(router 체크포인트 확보 시 재검토 대상,
현재는 rag.py에서 미참조).

---

## 2026-08-20 — 앵커 448 리포트 사후 감사 (feature/kokopas)

리포트(`docs/eval_anchor_규남.md` A~C)의 결론을 실측으로 재검증. 상세는 같은 문서 **D절**.

- **평가 지표 수정**: GT의 `gt_chunk_ids`(문항당 평균 1.97개 relevant)를 무시하고 앵커 청크
  1개만 정답으로 세고 있었다. 실패 217건 중 40건(18.4%)은 top-1이 GT가 relevant로 라벨한 청크.
  등급 relevance 도입 시 **soft Hit@1 0.605 · soft Hit@5 0.920 · nDCG@5 0.705** — 목표 미달 결론이 뒤집힌다.
  `eval_anchor_gold.py`에 nDCG·soft-hit·Wilson CI·McNemar(`--compare`) 추가.
- **유의성 기준 확립**: n=448에서 Hit@1의 95% CI는 **±4.6pp**. 이전 스윕의 +0.2~+1.1pp Reject는
  판정 불가한 차이였다(결론은 동일, 근거만 교정). 채택안은 McNemar 24/6, **p=0.0014로 유의**.
- **미실험 레버 실측**: RRF→질의별 정규화 융합(α 0.5~0.9 전 구간 악화), 제목 겹침 IDF 가중(악화),
  재청킹 acc/sect 188청크(ns) → 기각. 신규 하네스 `eval_fusion_sweep.py`(파리티 448/448 검증) 추가.
- **rag.py 반영(2차)**: 업무부스트 상수→dense 비례 곱셈 + BM25 질의측 동의어 확장 13항
  (`QUERY_SYNONYMS`/`expand_query_tokens`) + `BF_DOC_CAP` 99→3. 각각은 유의성 미달이지만
  **셋 다 악화 0건**이라 채택 — "+0.6pp 개선"을 주장하지는 않는다.
  **최종: Hit@1 0.522 · Hit@3 0.808 · Hit@5 0.895 · MRR@10 0.678 · soft@1 0.612 · nDCG@5 0.724**
  (vs baseline McNemar 27/6, p=0.0003). 대가는 Hit@30 0.996→0.980(cap=3) — 리랭커를 top-30 위에
  얹으면 cap을 리랭킹 이후로 옮길 것. 상세는 `docs/eval_anchor_규남.md` E절.
- **`DENSE_W` 민감도 곡선**: 0.4~0.75가 고원(Hit@1 0.513~0.518), 채택값 0.5는 그 한가운데 — 과적합 아님.
- **`BF_DOC_CAP` 재해석**: Hit 기준으로는 no-op이 맞지만 nDCG@5는 cap=3에서 유의하게 개선
  (0.705→0.722, 부트스트랩 95% CI [+0.011,+0.024]). 단 후보 풀에 걸면 Hit@30 0.996→0.980.
  서빙 K=3에서는 무의미하므로 현행 유지, **컨텍스트에 top-5 이상을 넣으면 cap=3으로 전환** 권고.
- **남은 공백 2가지**: (1) 엔드투엔드(LLM 답변) 평가 부재 — Hit@1 우선이라는 목표 설정 자체가
  미검증. (2) `span_verbatim_ok`가 448건 전량 True라 평가셋 편향 미검증, 실로그 검증셋 필요.

---

## 2026-08-20 — soft Hit@5 최적화: `BF_DOC_CAP` 99 → 3 (feature/kokopas)

목표를 Hit@1에서 **soft Hit@5**로 옮기고, 실패 36건을 전수 분류한 뒤 그 유형만 공략했다.
재임베딩·재청킹·리랭킹 없이 캐시(`data/qscore_cache.npz`) 위 융합/랭킹 항만 탐색.

- **실패 유형(baseline 36건)**: `top-30엔 있으나 top-5 밖` 31건 · `dense/BM25 모두 놓침` 5건.
  전자의 상당수가 **한 문서(FAQ 38청크 등)가 top-5를 도배**한 사례 — 문서 중복이 실제 Hit@5 실패 원인.
- **채택: `BF_DOC_CAP=3`**. soft Hit@5 **.9196→.9263**(개선 3 · 악화 0, McNemar p=0.25 ns) ·
  nDCG@5 .7048→.7225 · soft Hit@1 .6049 불변 · strict Hit@5 .893→.897.
  홀짝 분할 양쪽 개선(.9286→.9330 / .9107→.9196)이라 과적합으로 보지 않는다.
  비용: soft Hit@30 .9955→.9888(top-30이 최소 10개 문서에서 나와야 해 한 문서 4번째+ 청크가
  정답인 3문항 손실). 서빙 K=3~5에서 이득이 크다.
  → 직전 항목의 "cap은 Hit 기준 no-op" 판정은 **strict Hit 기준**이었고, soft 기준에서는 성립하지 않는다.
- **전 파라미터 재스윕 결과 현행값이 이미 최적**: RRF_K(1~60), RRF_ALPHA(0.4~0.8), DENSE_W(0.3~0.7),
  TITLE_W(0~0.12), BF_BOOST(0~0.12), FACET_BOOST(0~0.3) 모두 현행값이 고원 정점이거나 동률.
  FACET_BOOST=0.2가 soft Hit@5 .9263로 동률이나 soft Hit@1을 .605→.596으로 깎아 기각.
- **cap 조합 튜닝 기각**: cap=3 + (alpha .55 | title_w .08)이 .9286로 1문항 더 얹지만 짝수반에서만
  나오고 soft Hit@1을 깎는다 — 과적합으로 판단.
- **cap 변형 `capq`(초과분 절단 대신 후순위로 밀어내기) 기각**: 38문서×3=114>30이라 밀린 청크가
  top-30에 못 돌아와 cap과 결과 완전 동일. 단순한 쪽 유지.
- **종료**: 잔여 실패 33건은 dense·BM25가 나란히 6~20위인 문항으로, 융합식 조정으로 얻을 신호가 없다.
  추가 개선은 금지된 레버(재임베딩/리랭킹/재청킹)를 요구한다 → 현 구조에서의 탐색 종료.
- 신규 하네스: `crawler/diag_hit5.py`(실패 전수 분류), `crawler/eval_hit5.py`(soft Hit@5 그리드),
  `crawler/eval_hit5_final.py`(홀짝 교차확인), `crawler/eval_hit5_capq.py`(cap 변형 A/B).
  최종 검색 결과 `crawler/data/retrieved_top30_cap3_real.jsonl` — 시뮬레이터와 top-30 448/448 일치.

---

## 2026-08-20 — 최종 확정: 동의어 확장 + 업무부스트 곱셈화 + `cap=3` (feature/kokopas)

같은 날 두 세션이 `crawler/rag.py`를 **병행 수정**했다(서로 모르는 채로). 양쪽 변경이 모두
현재 코드에 들어가 있고, 실측으로 정합성을 확인한 뒤 **현재 코드를 최종본으로 확정**했다.

| 라운드 | 채택 | 기준 |
|---|---|---|
| 3 (E절) | `BF_DOC_CAP` 99→3 | soft Hit@5 최우선, 손실 0 |
| 4 (F절) | 동의어 13항(BM25 질의측) + 업무부스트 곱셈화 + `cap=3` | 악화 0건이면 유의성 미달이어도 채택 |

- **두 라운드가 독립적으로 `cap=3`에 도달** — 상호 검증으로 본다.
- **최종 지표(448문항)**: strict Hit@1 **0.522** / Hit@3 0.808 / Hit@5 0.895 / Hit@30 0.980 ·
  MRR@10 0.678 · soft Hit@1 **0.612** / Hit@5 **0.924** · nDCG@5 **0.724**.
  vs 라운드1 baseline McNemar 개선 27 · 악화 6 · **p=0.0003 유의**.
  `eval_fusion_sweep.py` 파리티 top-30 **448/448** 재확인.
- **목표 지표는 soft Hit@5로 확정**(LLM에 top-5를 넣으므로 Hit@5가 답변 가능 여부를 가른다).
  cap 단독안(라운드3)이 soft Hit@5 .926으로 현재 코드 .924보다 1문항 앞서지만 **448문항에서
  순증 1문항은 유의성이 없어** 동의어·곱셈부스트를 되돌리지 않는다. 문서에만 기록한다.
  → "cap 단독이 Hit@5에서 낫다"고 주장하지 않는다. 두 값은 이 평가셋에서 구분 불가하다.
- **D-3의 기각을 F-1이 뒤집은 건에 대한 정리**: 동의어·곱셈부스트는 D-3에서 "유의하지 않음"으로
  기각됐다가 F-1에서 "악화 0건의 비대칭성"을 근거로 채택됐다. **F-1의 해석을 채택**한다 —
  손실 없는 방향의 변경을 유의성 미달만으로 되돌릴 이유는 없다. 단 개선폭을 주장하지도 않는다.
- **baseline 파일 보존**: 병행 세션의 재실행이 `data/retrieved_top30_kunam.jsonl`(라운드1 baseline)을
  덮어썼다. git 인덱스에서 복구해 `data/retrieved_top30_base_cap99.jsonl`로 분리 보존했다.
  이후 A/B의 `--compare` 기준은 이 파일이다.
- **문서 통합**: 라운드1~4 전 기록을 `docs/eval_anchor_규남.md` 한 파일로 통합(0절 요약 · A~G절 ·
  뒤집힌 결론 목록). 이 문서가 단일 handoff 산출물이다.
