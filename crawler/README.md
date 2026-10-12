# KDIC 데이터 파이프라인 v0 — 선발대 스프린트 (`crawler/`)

수집(crawl) → 본문추출(parse) → 청킹(chunk) → 임베딩·적재(index) → 검색·평가(eval)를 담는 폴더.
D0 수집 + D1 파이프라인 현행화판(2026-07-13)을 2026-10-12에 `dev`(08-27) 코드 기준으로 다시 맞췄다.
판단 근거는 루트 [`DECISIONS.md`](../DECISIONS.md), 미해결·팀 이관은 [`HOLES.md`](./HOLES.md).
전체 명령과 평가 옵션의 정본은 [`docs/current/RUNBOOK.md`](../docs/current/RUNBOOK.md) §2·§3·§6이다.

> **모든 명령은 이 폴더(`crawler/`)에서 실행한다.** 경로 상수가 전부 상대경로다.

## 빠른 시작 — 레포 클론 기준

`data/raw`·`data/meta`·`data/parsed`·`data/index`는 레포에 **없다**(.gitignore / 재생성 대상). 아래 두 명령이 전부 만들어 준다.

```bash
pip install -r requirements.txt

# 0) 가드 로직 검증 (네트워크 불필요)
python tests/test_guards.py
# ① 라이브 수집 → 파싱 → 첨부 다운로드·연결 → 청킹 (38건 · 요청당 1.5s+지터)
python build_dataset.py --crawl
# ② ①이 만든 data/raw 캐시로 임베딩·인덱스 생성 (무네트워크)
#    최초 실행 시 임베딩 모델 dragonkue/BGE-m3-ko 약 2.2GB 다운로드
python pipeline.py --manifest crawl_manifest.csv --use-cache --rebuild
# ③ 검색 평가 — 앵커텍스트 판정(정본) → 터미널 + data/eval_chunk_report.md
python eval.py chunk --gt ../final_testset/gt_natural430_anchored.jsonl
```

**수집 직후 필수 확인 (H6 — 보호한도 페이지 구버전 간헐 서빙)**: 서버가 낮은 빈도로 "5천만원" 스테일 변형을 내려준다. 재수집할 때마다 확인한다.

```bash
grep -c "5천만" data/raw/kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn.html
# 0 이어야 정상(1억원 변형). 1 이상이면 python pipeline.py 재실행 — content_hash가 달라져 해당 문서만 다시 수집·적재된다.
```

## 단계별 실행 — 디버깅·부분 재실행용

| 단계 | 명령 | 입력 → 출력 |
|---|---|---|
| ① 수집 | `python run_crawl.py --manifest crawl_manifest.csv` | 매니페스트 → `data/raw/*.html` · `data/meta/*.json` · `data/crawl_report.json` |
| ①' 스모크 | `python run_crawl.py --manifest crawl_manifest.csv --limit 3` | 앞 3건만 |
| ② 파싱 | `python parser.py` | `data/raw` → `data/parsed/*.json` |
| ②' 첨부 | `python fetch_attachments.py` → `python link_files.py` | 첨부 실파일 → `data/files/` · parsed 문서에 `local_path` 연결 |
| ③ 청킹 | `python chunk.py` | `data/parsed` → `data/chunks.jsonl` (14필드) · `data/doc_attachments.json` |
| ③' FAQ BF 태깅 | `python faq_bf_map.py --router <ckpt>` | `data/chunks.jsonl` → `data/bf_map.jsonl` · `data/bf_map_report.md` |
| ④⑤ 인덱스 | `python pipeline.py --use-cache --rebuild` | `data/raw` 캐시(무네트워크) → `data/index/` |
| 채점 | `python eval.py chunk --gt ../final_testset/gt_natural430_anchored.jsonl` | 앵커 GT + index → `data/eval_chunk_report.md` |

- 임베딩·적재 단독 스크립트는 없다 — `pipeline.py`(내부 `rag.Store`)가 담당.
- `--use-cache`는 `data/raw`가 이미 있을 때만 동작한다(없으면 전건 `cache_miss`). 클론 직후에는 빠른 시작 ①로 `data/raw`를 먼저 만든다.
- 인자 없는 `python eval.py`는 `chunk` + 기본 GT `data/gt_schema_v6.jsonl`(1,651행)로 돈다. 현행 수치와 비교하려면 위처럼 `--gt`를 명시한다.

## 재수집 — 운영 트리거 프로토타입

```bash
python pipeline.py        # 매니페스트 전 URL recollect — content_hash 불변이면 스킵
```

`recollect(url) = fetch(polite) → parse → chunk → upsert(by doc_id)`. robots 차단·오류 문서는 인덱스에서 제외된다. 라이브 실행은 `data/crawl_report.json`도 갱신한다(07-13). 03 결정문서 §4의 원자 함수 프로토타입.

## 매니페스트

`crawl_manifest.csv`(**38건 = 필수 37 + 분석포함 1**) **확정본이 커밋돼 있다** — 평시 재생성 불필요. 분석필요 xlsx는 07-13 복원본 병합 완료(H2 해소 — 부채증명원 1건 편입, 판정 분포는 DECISIONS 07-13).

```bash
# 재생성 (멱등 — 07-13 확정 방식: 필수 CSV + 분석필요 xlsx 병합)
python build_manifest.py kdic_필수페이지_URL매핑.csv 분석필요태깅_포함여부분석.xlsx -o crawl_manifest.csv
python pipeline.py        # 신규 편입분만 증분 수집·적재 (기존 건은 content_hash 스킵)
```

## D0 재현성 검증 (선택 — 통과 이력 있음)

이중 수집 후 가시 텍스트 해시로 비교한다. D0 결과: **31/32 일치**, 불일치 1건은 서버측 비결정성(H6)으로 크롤러 결함 아님.

```bash
python run_crawl.py --manifest crawl_manifest.csv --out run1
python run_crawl.py --manifest crawl_manifest.csv --out run2
python verify_rerun.py run1 run2
```

- `--out run1`은 산출을 `run1/data/` 아래에 만든다 — **캐노니컬 `./data/`와 별개**이며 파이프라인 후속 단계의 입력이 아니다.
- 캐노니컬 채택 시에는 H6 확인(위 grep) 후 1억원 변형인 run의 `data/`를 `./data/`로 복사한다. D0에서는 run1을 채택했다(run2는 5천만원 스테일 변형 포함 — DECISIONS 참조).

## 산출물

| 구분 | 파일 | 비고 |
|---|---|---|
| 레포 포함 | `crawl_manifest.csv` · `kdic_필수페이지_URL매핑.csv` · `분석필요태깅_포함여부분석.xlsx` | 38건 = 필수 37 + 분석포함 1 (xlsx는 판정 원천) |
| 레포 포함 | `data/chunks.jsonl` · `data/doc_attachments.json` | 181청크 × 14필드 — 검색 대상 핵심 · 문서별 첨부 메타 |
| 레포 포함 | `data/eval_report.md` | 구세대 지표 리포트(450건 · RRF k=5). 현행 평가는 `eval.py chunk` |
| 레포 포함 | `data/crawl_report.json` | 상태별 카운트 · robots 차단 목록(07-22 수집: 38 ok / 0 blocked) |
| 레포 포함 | `link_registry.json` | 소관 밖 라우팅 6건 — **전건 url 충전 완료(H7 해소, 07-13)** |
| 레포 포함 | `data/bf_map.jsonl` | FAQ 청크 108건의 BF(라우터 산출) — qhash 조인 레이어, `chunks.jsonl` 무수정 |
| 레포 제외 | `data/raw/*.html` · `data/meta/*.json` | .gitignore(`data/raw/`) — 클론 후 라이브 재수집으로 확보 |
| 레포 제외 | `data/parsed/*.json` · `data/index/*` · `data/files/` | 재생성 가능 산출물 |
| 레포 제외 | `router_moai_embedding_model/pytorch_model.bin` | 라우터 가중치 2.38GB만 제외 — 설정·토크나이저 8개는 커밋 |

`data/meta/{doc_id}.json` 필드: source_url · business_function · sub_category · page_type · coverage · variant · robots_status · breadcrumb · collected_at · raw/text sha256.

## 로드맵 요구사항 매핑

| 요구 | 구현 |
|---|---|
| 화이트리스트 크롤링 (사이트맵 폐기) | 매니페스트 행만 수집, 발견형 크롤링 없음 |
| kdic 세션 선행 필수 | `ensure_session()` — www는 `/sp/main.do` 진입(루트 `/`는 502), fins는 루트 진입 |
| 오류 페이지 가드 | `error404` URL / `오류 \| KDIC` 타이틀 / 오류 본문 감지 → **raw 저장 안 함** |
| robots.txt 준수 (이중 안전장치) | ① 명시 UA로 robots.txt 직접 GET→parse, 실패 시 **fail-open 금지**(unreachable 기록) ② `config.POLICY_DISALLOW` 경로 오버레이 — KDIC robots가 Googlebot 전용이라 우리 UA엔 자동 미적용되는 문제 대응. disallow는 수집 절대 금지, report 기록만 |
| 1~2초 딜레이 · 명시적 UA | 1.5s + 지터 0.7s · `config.USER_AGENT` — 연락처는 개인 메일 임시(팀 공식 주소 확정 시 교체) |
| raw 원본 + 메타 JSON | 위 산출물 구조 |
| variant 분기 관리 | 쿼리스트링 해시로 doc_id 구분, 매니페스트 variant 컬럼 메타 전파 |
| 재실행 동일 결과 | `verify_rerun.py` — 텍스트 해시 기준 (raw 바이트는 CSRF/세션값 변동으로 제외) |
| 파서 v0 (값 유실 없음) | `parser.py` — `.contents` 컨테이너 · 표 행 직렬화 · 스팟체크 5/5 |
| 청킹 + 스키마 | `chunk.py` — 800자/오버랩 100 · 표 중간분할 금지 · FAQ 1쌍=1청크 |
| 임베딩·벡터DB | `rag.py` — `dragonkue/BGE-m3-ko`(1024d) + FAISS IndexFlatIP + BM25(kiwi) + 가중 RRF(`RRF_ALPHA` 0.65 · `RRF_K` 4) + 6업무 soft boost |
| 재수집 트리거 | `pipeline.py` `recollect()` — content_hash 스킵 |
| 평가셋 + 지표 | `eval.py chunk`(앵커 판정) — 430 앵커셋 `hybrid_bf` hit@5 0.884(08-24, RUNBOOK 부록 C) |

## 주의

- **fins `/cm/bbs/` FAQ 게시판 5건**(미수령금·착오송금·채무정보조회·은닉재산·TOP10): 초기에는 robots_blocked로 차단했으나 robots 해석 변경 뒤 `config.POLICY_DISALLOW["fins.kdic.or.kr"]`가 비어 수집·인덱싱된다(HOLES H18 해소).
- 대기열 마커 문구는 정상 페이지에도 숨김 모달로 존재 → 본문이 짧을 때만 대기열 판정.
- 첨부(PDF/HWP)는 `fetch_attachments.py` → `link_files.py`(또는 `build_dataset.py`)가 실파일을 받아 연결한다. `pipeline.py`만으로는 다시 받지 않는다.
- **소스 원문 무수정 원칙**: H6b(상속 페이지 stale 5천만) 등 구값은 raw/청크를 고치지 않는다 — 보정은 D2 답변 레이어에서만.
