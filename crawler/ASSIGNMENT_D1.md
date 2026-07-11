# ASSIGNMENT_D1 — 데이터 → 벡터DB (토)

**목표**: raw HTML을 검색 가능한 형태로 — 파서 v0 → 청킹/스키마 → 임베딩 → 벡터DB 적재 → 검색 스모크 통과.
전제: D0 통과 기준 전부 충족. 미충족이면 D0 잔여부터 처리한다.

## 태스크 (순서 고정)

**T1. 파서 v0** (`parser.py`) — 결정론적 BeautifulSoup. LLM 사용 금지.
- 입력: `run1/data/raw/*.html` + 대응 메타 JSON
- 네비게이션·푸터·숨김 모달 등 노이즈 제거 (KDIC 페이지는 텍스트의 90%+가 네비 노이즈 — 본문 컨테이너를 좁혀 잡을 것)
- 본문과 **표의 값을 유실 없이** 텍스트로 추출. 표 구조 미화(markdown 변환)는 하지 않는다 — P2 몫
- **안내부만 추출**: coverage가 `안내부`인 페이지(상속인 금융거래조회 · 부채증명원)는 안내 섹션만 남기고 조회/신청 기능부 제거
- 첨부(PDF/HWP) 링크는 파싱하지 않고 `attachments` 필드에 목록만 보존
- 산출: `data/parsed/{doc_id}.json` (doc_id · text · attachments · 메타 상속)

**T2. 값 유실 스팟체크** — 원본 HTML에서 표 안의 수치·금액 5개를 샘플링해 파싱 결과에 전부 존재하는지 확인. 실패 시 파서 수정 후 재검. 결과를 DECISIONS에 기록.

**T3. 청킹 + 스키마 부착** → `data/chunks.jsonl`
- 섹션/문단 경계 우선, 크기·오버랩은 1개 설정으로 고정하고 값과 근거를 DECISIONS에 기록 (튜닝 비교는 P2 몫)
- 청크 스키마: `chunk_id · parent_doc_id · business_function · sub_category · page_type · coverage · variant · source_url · page_title · breadcrumb · text`
- 전 청크가 스키마를 만족하는지 검증 스크립트로 확인

**T4. 임베딩 → 벡터DB 적재** — FAISS 또는 Chroma, 로컬.
- 임베딩 모델은 로컬 실행 가능한 한국어 지원 모델로 선택(예: sentence-transformers 다국어/한국어 계열). **선택지·결정·근거를 DECISIONS에 기록.** CLOVA 임베딩 연동은 P4 몫
- 적재 건수 = 청크 수 일치 확인, 인덱스는 `data/index/`에 저장

**T5. 검색 스모크** (`search_smoke.py`)
- 매니페스트의 business_function 6종에서 대표 질문 1개씩 확정하고 DECISIONS에 기록 (예: "예금자 보호 한도는 얼마인가요?")
- 각 질문 top-3 검색 → 정답 문서 적중 여부 판정
- **오염 체크**: 국내 보호한도 질문의 top-3 청크에 해외 한도 수치가 섞여 있지 않은지 확인

## 통과 기준 (전부 예/아니오)

- [ ] 값 유실 스팟체크 5/5 통과
- [ ] chunks.jsonl 전 청크 스키마 유효
- [ ] 벡터DB 적재 건수 = 청크 수
- [ ] 대표 질문 6개 중 5개 이상 top-3 적중
- [ ] 국내 한도 질문 결과에 해외 수치 혼입 0건

## 끌어올림 규칙 (유일한 예외)

한도·금액 질문이 **표 파싱 때문에** 깨지면 → P2의 표→markdown 구조 보존 파싱을 지금 승격해 적용. 그 외 P2 항목(하이브리드·리랭킹·평가셋·청킹 튜닝)은 손대지 않는다.

## 범위 밖

RAG 체인 · LLM 답변 · UI · 라우팅(내일 D2) · 첨부 파싱 · robots 차단 건.
마감: 진행 로그 + HOLES/DECISIONS 갱신 + 커밋 대상 목록 보고. git 명령은 실행하지 않는다 — 커밋은 사용자 직접.
