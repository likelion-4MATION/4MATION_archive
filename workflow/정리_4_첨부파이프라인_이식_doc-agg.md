# 정리 4 — 첨부문서 파이프라인 이식 (meta-doc → feature/doc-agg)

> 작성일: 2026-07-23 · 브랜치: feature/doc-agg (통합 브랜치)
> 목적: meta-doc의 "사이트 첨부파일 수집 + 청크 연결" 방식과 testset3의 파서
> 호환성 개선(lxml→html.parser 폴백)을 doc-agg로 이식. 그대로 머지하지 않고
> 방식만 분석해 재태깅(doc-agg 기존 기능)과 충돌 없이 병합.

---

## 1. 무엇을 이식했나

세 브랜치의 서로 다른 작업을 doc-agg 하나로 합쳤다.

| 출처 | 가져온 것 |
|---|---|
| meta-doc | 첨부 추출(direct/onclick 토큰) + 실다운로드 + 청크 연결 파이프라인 |
| feature/testset3 | `parse_html` — lxml 우선, `.contents` 미탐지 시 html.parser 폴백 (구 Windows lxml 이중 body 유실 대응) |
| doc-agg(기존) | business_function 청크별 재태깅 — **유지** |

핵심 판단: meta-doc의 "재태깅"은 **첨부 메타를 청크에 붙이는 것**이고, doc-agg의
재태깅은 **business_function 재분류**다. 둘은 직교하므로 chunk.py에서 **둘 다** 살렸다.

---

## 2. 변경/추가 파일

| 파일 | 상태 | 내용 |
|---|---|---|
| `crawler/parser.py` | 교체 | 첨부 추출(name·file_type·doc_kind·url·link_type·anchor_text·enc_real/enc_temp) + has_attachments + `parse_html` 폴백 |
| `crawler/crawler.py` | 수정 | 크롤 시점 파싱 4곳을 `parse_html`로 (import 포함) |
| `crawler/fetch_attachments.py` | 신규 | onclick 첨부 실다운로드 → `data/files/{doc_id}/` + `manifest.json` (네트워크) |
| `crawler/link_files.py` | 신규 | manifest ⋈ parsed 를 (doc_id, enc_real, enc_temp) 토큰으로 조인 → parsed에 local_path stamp. manifest 없으면 스킵(안 깨짐) |
| `crawler/chunk.py` | 병합 | 재태깅 유지 + `match_attachments`(청크 단위) + `doc_attachments.json`(문서 단위) + 스키마 11→14필드 |
| `crawler/build_dataset.py` | 신규 | 데이터셋 빌드 래퍼 (crawl→parse→fetch→link→chunk) |
| `.gitignore` | 수정 | `crawler/data/files/` ignore (재생성 산출물). `doc_attachments.json`은 커밋 대상 |
| `crawler/data/chunks.jsonl` | 재생성 | 첨부 필드 포함 |
| `crawler/data/doc_attachments.json` | 신규 | 문서 단위 첨부 집합 |

---

## 3. 첨부 처리 — 하이브리드(청크 + 문서 단위)

- **청크 단위**: 첨부 `anchor_text`가 그 청크 본문에 등장하면 해당 청크에만 부착(정밀).
- **문서 단위**: 페이지 전체 첨부 집합을 `data/doc_attachments.json`에 `doc_id`로 보존.
  Parent-Child 생성이 `parent_doc_id`로 조회 → **청크 매칭 실패 시에도 서식 누락 방지(안전망)**.

> 채택 이유: 검색은 청크 단위인데 생성은 부모 문서 문맥으로 이뤄져, 첨부가 청크에만
> 있으면 형제 청크의 서식이 누락될 수 있음. 문서 단위 집합이 이를 커버.

---

## 4. 두 개의 경로 — 청킹 로직은 하나

청킹 규칙은 `chunk.py`의 `make_chunks()` **한 곳**이 소스 오브 트루스. 두 진입점이 공유:

| 경로 | 진입점 | 청킹 호출 | 산출물 | local_path |
|---|---|---|---|---|
| 데이터셋 파일 | `chunk.py` (build_dataset가 호출) | 전체 문서 | `data/chunks.jsonl` + `data/doc_attachments.json` (커밋) | 있음(fetch+link 후) |
| 검색 인덱스 | `pipeline.py` recollect | `chunk_mod.make_chunks` 문서별 | FAISS `data/index/` | 없음 |

`pipeline.py`가 건드리는 것: `data/raw`(캐시)·`data/meta` 읽기 → `parse_one`(parsed 덮어씀)
→ `make_chunks` → `store.upsert`(FAISS) → `data/crawl_report.json`. **`chunks.jsonl`/
`doc_attachments.json`은 안 건드림**(chunk.py 몫).

> 주의: `pipeline.py`는 `parse_one`으로 parsed를 매번 새로 써서 그 시점 parsed의
> local_path는 되돌아감 → 검색 인덱스는 첨부 local_path를 싣지 않음(설계 의도).
> 챗봇은 답변 시 `parent_doc_id`로 `doc_attachments.json`에서 첨부를 조회.

---

## 5. 왜 fetch를 pipeline에 안 넣었나 (A안)

첨부 실다운로드(`fetch_attachments.py`)는 네트워크·비결정론이고 파일이 거의 안 바뀜.
recollect의 잦은 재실행 루프에 넣으면 (1) 매번 KDIC 다운로드 낭비 (2) 재실행 시 파일
중복(`_1` suffix) (3) recollect의 재파싱이 local_path를 덮어씀. 그래서 소스가 바뀔
때만 도는 `build_dataset.py` 배치로 분리.

---

## 6. 명령어 치트시트 (모두 `crawler/`에서)

```bash
# 첫 빌드 (라이브 크롤 + 첨부 + 인덱스)
python build_dataset.py --crawl                                        # 크롤→파싱→첨부→링크→청킹
python pipeline.py --manifest crawl_manifest.csv --use-cache --rebuild # 검색 인덱스(캐시 재사용)

# 소스(첨부 포함) 재수집
python build_dataset.py --crawl
python pipeline.py --manifest crawl_manifest.csv --use-cache --rebuild

# 청크 사이즈 등 파라미터 실험 (크롤·첨부 그대로)
python pipeline.py --manifest crawl_manifest.csv --use-cache --rebuild # 인덱스만 재빌드
python chunk.py                                                        # (선택) 커밋용 파일도 갱신

# 오프라인 데이터셋 재생성 (네트워크 없이, local_path 미채움)
python build_dataset.py --no-fetch
```

---

## 7. 검증 결과 (오프라인)

- parser 재실행: 첨부 6문서 · 46건(전부 onclick_dynamic), anchor_text·토큰 정상.
- chunk 재실행: 청크 215건 유지 · 스키마 전건 유효 · 재태깅 47건 유지 · 첨부 보유 청크 16 · doc_attachments 6문서.
- gitignore: `data/files/` ignore, `chunks.jsonl`·`doc_attachments.json` 커밋 대상 확인.
- 실다운로드(`fetch_attachments.py`)는 로컬 네트워크에서 1회 실행 필요(샌드박스 미도달).

## 8. 알려진 한계

- 첨부 2건('본인/대리인 신청서 샘플 다운로드')은 anchor_text가 본문에 안 남아 청크
  매칭 실패 → **문서 단위 집합이 커버**. 정밀도 더 필요하면 해당 버튼 anchor 규칙 보강.
- `enc_real`/`enc_temp` "렌더마다 고정" 가정은 실사 경험칙 — 사이트 개편 시 다운로드
  실패 가능. 재수집에 실패 알람 권장.
