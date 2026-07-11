# KDIC 화이트리스트 크롤러 v0 — 선발대 스프린트 P0

07-10 정찰 반영: 사이트맵 폐기 → 매니페스트 = 화이트리스트 · 세션 선행 · 오류 페이지 가드.

## 실행 순서 (D0 밤 목표)

```bash
pip install -r requirements.txt

# 0) 가드 로직 검증 (네트워크 불필요, 이미 통과 확인됨)
python tests/test_guards.py

# 1) 매니페스트 병합 (csv+xlsx → crawl_manifest.csv) — 컬럼 매핑 출력 눈으로 확인
python build_manifest.py kdic_필수페이지_URL매핑.csv 분석필요태깅_포함여부분석.xlsx -o crawl_manifest.csv

# 2) 스모크 3건
python run_crawl.py --manifest crawl_manifest.csv --limit 3

# 3) 전량 수집 (밤에 돌려놓기) — 30건 × ~2초 ≈ 2분 내외
python run_crawl.py --manifest crawl_manifest.csv --out run1

# 4) 재현성 검증 (통과조건 1번) — 한 번 더 돌리고 비교
python run_crawl.py --manifest crawl_manifest.csv --out run2
python verify_rerun.py run1 run2
```

## 산출물

- `data/raw/{doc_id}.html` — 원본 바이트 그대로 보존
- `data/meta/{doc_id}.json` — source_url · business_function · sub_category · page_type · coverage · variant · robots_status · breadcrumb · collected_at · raw/text sha256
- `data/crawl_report.json` — 상태별 카운트 · robots 차단 목록 · 실패 목록 (구멍 목록 초안으로 사용)

## 로드맵 요구사항 매핑

| P0 요구 | 구현 |
|---|---|
| 화이트리스트 크롤링 (사이트맵 폐기) | 매니페스트 행만 수집, 발견형 크롤링 없음 |
| kdic 세션 선행 필수 | `ensure_session()` — www는 `/sp/main.do` 진입(루트 `/`는 502), fins는 루트 진입 후 순회 |
| 오류 페이지 가드 | `error404` URL / `오류 \| KDIC` 타이틀 / 오류 본문 감지 → **raw 저장 안 함** |
| robots.txt 준수 | disallow → 수집 절대 금지, report에 기록만 (운영 룰: 데모 용도라도 예외 없음) |
| 1~2초 딜레이 · 명시적 UA | 1.5s + 지터 0.7s · `config.USER_AGENT` (**contact 이메일 TODO 채울 것**) |
| raw 원본 + 메타 JSON | 위 산출물 구조 |
| variant 분기 관리 | 쿼리스트링 해시로 doc_id 구분, 매니페스트 variant 컬럼 메타 전파 |
| 재실행 동일 결과 | `verify_rerun.py` — 텍스트 해시 기준 (raw 바이트는 CSRF/세션값 변동으로 제외) |

## 주의

- 대기열 마커 문구는 정상 페이지에도 숨김 모달로 존재 → 본문이 짧을 때만 대기열 판정
- 채무정보조회 FAQ(robots 차단 건)는 매니페스트에 넣지 말 것 — 허용(D5) 확인 전 수집 금지
- 첨부(PDF/HWP)는 이번 스프린트 스킵 — 파서 단계에서 링크 목록만 보존 예정
