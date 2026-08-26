<!-- 상태:records -->
> **기록** — 2026-08-25 시점의 사실. 고치지 않는다(정정은 추기로)
> 문서 지도: `docs/README.md`(문서 지도) · `docs/프로젝트_전체흐름.md`(전체 그림·용어 해설)

---

---
author: 유상
branch: feature/anc
commit: b0d70ee
written_at: 2026-08-20
corpus:
  chunks_path: crawler/data/chunks.jsonl
  chunk_count: 181            # HEAD 커밋본. ⚠️ 워킹트리는 178 (미커밋 변경 있음, §1 참조)
  file_sha256: fd205d813517   # HEAD 커밋본 / 워킹트리는 26031ab92d62
  embed_model: dragonkue/BGE-m3-ko
  embed_dim: 1024
  index_rebuilt: false        # 본 제출서 작성 시 재측정 미수행 — §4 는 기존 리포트·결론문서 인용
  router_used: true           # router_moai_embedding_model 로컬 존재(git 미추적, 2.3GB)
params:
  k: 5                        # 주지표 hit@5 기준. rag.Searcher.search 기본 k=5
  RRF_ALPHA: 0.65
  RRF_K: 4
  BF_MODE: soft
  BF_BOOST: 0.06
  BF_DOC_CAP: 5
  FACET_BOOST: 0.05
  rerank: none                # 리랭커 측정만 완료, 미채택
claims:
  - path: final_testset/gt_natural430_anchored.jsonl
    kind: gt
    supersedes: crawler/data/testset_natural_450.jsonl
  - path: final_testset/gt_natural505_val.jsonl
    kind: gt
    supersedes: none
  - path: crawler/eval_anchor_v3.py
    kind: eval
    supersedes: crawler/eval.py
  - path: crawler/rag.py
    kind: param
    supersedes: none
open_questions: 6
---

# 평가 수합 제출서 — `feature/anc` (`유상`)

> **목적** 각 브랜치의 eval 방법과 GT 중 **가장 정확한 버전**을 골라 하나로 합치기 위한 제출서.
> **원칙** ① 값은 **실행해서** 채운다 ② 모르는 건 `미측정`으로 남긴다
> ③ 수치에는 **항상 코퍼스 지문을 붙인다** — 지문이 다른 수치는 비교 대상이 아니다.

---

## 1. 코퍼스 지문 (필수)

| 항목 | 값 | 확인 방법 |
|---|---|---|
| `chunks.jsonl` 청크 수 (HEAD) | **181** | `git show HEAD:crawler/data/chunks.jsonl \| wc -l` |
| `chunks.jsonl` 청크 수 (워킹트리) | **178** ⚠️ | `wc -l crawler/data/chunks.jsonl` |
| 파일 sha256 앞 12자 (HEAD) | `fd205d813517` | `git show HEAD:… \| sha256sum` |
| 파일 sha256 앞 12자 (워킹트리) | `26031ab92d62` | `sha256sum crawler/data/chunks.jsonl` |
| 임베딩 모델 / 차원 | `dragonkue/BGE-m3-ko` / 1024 | `crawler/rag.py:22,28` |
| 인덱스 재생성 여부 | **아니오** — 본 제출서는 재측정 없이 기존 리포트·결론문서를 인용 | — |
| 라우터 상태 | **라우터 사용** (`router_moai_embedding_model` 로컬 존재, **git 미추적 2.3GB**) | 폴더 존재 확인 |
| 마지막 재청킹 커밋 | `e7e898f` (2026-08-18) "표 원자성 수정 코퍼스 반영 + 파라미터 재튜닝 + 앵커 라벨 보강" | `git log -1 -- chunks.jsonl` |

### ⚠️ 지문 경고 1 — 워킹트리가 커밋본과 다르다

미커밋 변경(`+19 / −22`)으로 **워킹트리가 178청크**다. §4의 모든 수치는 **181청크 기준**이며,
지금 그대로 재실행하면 **다른 값이 나온다.** 수합 전에 이 변경의 정체를 확정해야 한다(§8-1).

### ⚠️ 지문 경고 2 — 파라미터가 코퍼스에 종속

`rag.py` 주석 명시: *"이 값들은 181청크 코퍼스와 한 세트다. 옛 청킹(215)에서 RRF_K=4를 쓰면…"*.
215청크 시절 리포트와 181청크 리포트는 **직접 비교 불가**다(§4에 지문 열로 구분).

---

## 2. GT(정답셋) 목록

| # | 파일 경로 | 문항 수 | 판정 필드 | 다중정답 | split | 검수 상태 | 상태 | 파생 관계 |
|---|---|---:|---|---|---|---|---|---|
| 1 | `final_testset/gt_natural430_anchored.jsonl` | 430 | `gt_anchors` + `gt_chunk_ids` | 허용 (`single`/`and`/`or`) | **TEST** | 전수 수작업 + 앵커 38개 수기 보강 | **정본** | `gt_natural430` + 앵커 컬럼 |
| 2 | `final_testset/gt_natural505_val.jsonl` | 505 | `gt_chunk_ids` (+`gt_anchor_span`) | 허용 | **VAL** | 부분 (앵커 12문항 id 폴백) | **정본(VAL)** | TEST와 문항 비중복 분리 |
| 3 | `final_testset/gt_natural430.jsonl` | 430 | `gt_chunk_ids` | 허용 | TEST | 전수 | 후보 | #1의 앵커 미부착본 |
| 4 | `final_testset/gt_natural355_anchored.jsonl` | 355 | `gt_anchors` + `gt_chunk_ids` | 허용 | 구 TEST | 전수 | **폐기** | relation 택소노미가 다름(`near_dup`/`duplicate`/`contained`) |
| 5 | `final_testset/gt_natural355.jsonl` | 355 | `gt_chunk_ids` | 허용 | 구 TEST | 전수 | 폐기 | #4의 앵커 미부착본 |
| 6 | `final_testset/gt_natural400.jsonl` | 400 | `gt_chunk_ids` | 허용 | 구 | 전수 | 폐기 | 라우터 학습셋과 겹침(§6) |
| 7 | `final_testset/gt_natural450.jsonl` | 450 | `gt_chunk_ids` | 허용 | 구 | 전수 | 폐기 | 상동 |
| 8 | `crawler/data/testset_natural_450.jsonl` | 450 | `gt_docs` | 문서 단위 | 구 | — | 폐기 | parent-child 입도 불일치 |
| 9 | `crawler/gt_testset_retrieval_450.jsonl` | 450 | `gt_chunk_ids` | 허용 | 구 | 부분 | 폐기 | `eval_router_facet` 전용으로 남아 있음 |

**판정 필드**

- [x] `gt_anchors` — 정답 구절(앵커텍스트) 포함 여부로 판정. **재청킹에 견딤** ← 정본이 쓰는 방식
- [x] `gt_chunk_ids` — 청크 ID 일치. 재청킹에 취약. 앵커 결측 문항의 **폴백**으로만 사용
- [x] `gt_docs` — 문서 단위. 구세대(#8). '같은 문서면 적중' 거품이 있어 폐기

**필드 스키마 실물 (정본 #1의 키 목록)**

```
id · business_function · question · answerable · evidence_type · chunk_relation ·
gt_chunk_ids · gt_chunk_id · multi_chunk · gt_anchor_span · answer_bf ·
cross_domain · span_verbatim_ok · confidence · reason · gt_anchors
```

**relation 정규화 규칙** (`eval_anchor_v3.py`) — `single`/`or` = ANY(하나만 맞아도 적중),
`and` = ALL(전부 맞아야 적중), null/누락 = `single`.

**알려진 오라벨 / 미검수 구간**

- TEST **22문항**·VAL **12문항**이 앵커 결측으로 `chunk_id` 폴백. 표 청크 스팬은 locator 형태.
  → P2 "표 → markdown 파싱" 선행 필요
- `and` 문항(TEST 55건)의 지표가 구조적으로 낮음(Hit@5 0.291). 가설 4개 기각 후 진단 진행 중

---

## 3. 평가 스크립트 목록

| # | 파일 | 용도 | 판정 로직 (한 줄) | 소비 GT | 산출 리포트 | 상태 |
|---|---|---|---|---|---|---|
| 1 | `crawler/eval_anchor_v3.py` | **정본 평가** | `--score chunk_id\|anchor\|both`. anchor = top-k 청크 본문이 `gt_anchor_span`을 포함하는지. relation 조건 결합 | #1, #2 | `crawler/data/eval_v3_*.md` · `eval_anchor_v3_*.md` | **정본** |
| 2 | `crawler/eval.py` | 구세대 평가 | `parent_doc_id ∈ gt_docs` 로 최초 적중 rank. hit@1/3 + MRR, `KMAX=10`, 3모드(dense/hybrid/hybrid_bf) | #8 | `crawler/data/eval_report.md` | 폐기(참조용) |
| 3 | `crawler/eval_tablefix.py` | 실험 — 표 원자성 A/B (`TABLE_GAP_MAX`) | 청크 수·앵커 잔존·`and` 병합 병기 | #1 | `eval_tablefix_report.md` | 실험(완료) |
| 4 | `crawler/eval_router_facet.py` | 실험 — 질의 BF 소스(키워드 vs 라우터) × facet 방식 | 라우터 θ 스윕 | #9 | `eval_router_facet_450*.md` | 실험(완료·채택) |
| 5 | `crawler/eval_overlap.py` | 실험 — OVERLAP 100/200/300 | — | #1 | `eval_overlap_report.md` | 실험 |
| 6 | `crawler/eval_docinput.py` | 실험 — 문서 단위 반환 비용 | — | #1 | `eval_docinput_report.md` | 실험 |
| 7 | `crawler/eval_TF.py` | 실험 — 소프트부스트/λ 스윕 계열 | — | 구셋 | — | 실험 |
| 8 | `crawler/eval_pair.py` | 실험 | — | 구셋 | — | 실험 |
| 9 | `crawler/tune_params_v2.py` · `tune_cap_k.py` | 파라미터 스윕 (181청크) | — | #2(VAL) | — | 도구 |
| 10 | `crawler/audit_anchors.py` · `fill_anchors.py` | 앵커 커버리지 점검 · 수기 앵커 주입 | — | #1 | `anchor_audit_*.md` | 도구 |

**정본으로 주장하는 스크립트**

- 파일: `crawler/eval_anchor_v3.py`
- 실행 명령: `cd crawler && python eval_anchor_v3.py --gt ../final_testset/gt_natural430_anchored.jsonl`
- **결정론 여부**: 검색 자체는 결정론. 단 **동점 처리에 구현 의존성**이 있음 —
  dense는 faiss 반환 순서, sparse는 `argsort[::-1]`. 대리 하네스(`tune_params.py` 초기본)가
  이 때문에 hit@1에서 2문항 어긋난 전례가 있다. **대리 하네스는 정본과 동치 검증 후에만 사용.**

---

## 4. 측정 결과

**본 제출서는 재측정을 수행하지 않았다.** 아래는 기존 리포트와
`docs/방법론_정확도개선_결론_20260818.md` §1(수치 계보) 인용이다. 재측정 필요 여부는 §8-1.

### 4-A. 정본 수치 (앵커 채점 · 181청크)

| # | GT | 스크립트 | 채점 | k | hit@5 | 비고 | 코퍼스 지문 | 출처 |
|---|---|---|---|---:|---:|---|---|---|
| 1 | `gt_natural430_anchored` (TEST) | `eval_anchor_v3.py` | anchor | 5 | **0.891** | gold `business_function` 주입 경로 | 181 / `fd205d…` | 결론문서 §1 |
| 2 | `gt_natural430_anchored` (TEST) | `eval_anchor_v3.py` | anchor | 5 | **0.8907** | **실제 배포 경로**(라우터 BF) | 181 / `fd205d…` | 결론문서 §1 |
| 3 | `gt_natural505_val` (VAL) | `eval_anchor_v3.py` | anchor | 5 | **0.8535** | 실제 배포 경로 | 181 / `fd205d…` | 결론문서 §1 |
| 4 | TEST | `eval_anchor_v3.py` | anchor | 20 | 0.947 | **K 확대 참고치** — 생성 품질·지연 미검증 | 181 | 결론문서 §7 |

**수치 계보 (누적 · 독립 기여분 아님)**

| 단계 | hit@5 | 바꾼 것 |
|---|---:|---|
| 시작점 | .765 | 215청크 · `chunk_id` 판정 · 08-12 파라미터 |
| 1 판정 전환 | .828 | 앵커텍스트 판정 도입 |
| 2 질의 분류 | .837 | 키워드 → 라우터 (+ FACET 분리) |
| 3 파라미터 1차 | .855 | RRF 재튜닝 |
| 4 표 원자성 | .888 | `TABLE_GAP_MAX` · 181청크 · 재튜닝 2차 · 평가기 stale 수정 |
| 5 라벨 보강 | **.891** | 앵커 38개 수기 작성 |

### 4-B. 커밋된 리포트 파일 수치 (⚠️ 채점 방식·지문 주의)

| # | 리포트 | GT | 채점 | 지문 | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR@10 |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| 5 | `eval_v3_430_anchored.md` | 430_anchored | **chunk_id** | 181 | 0.335 | 0.614 | 0.740 | 0.798 | 0.495 |
| 6 | `eval_v3_430.md` | 430 | chunk_id | 181 | 0.335 | 0.614 | 0.740 | 0.798 | 0.495 |
| 7 | `eval_anchor_v3_report.md` | `gt_testset_retrieval_450` | chunk_id | 181 | 0.326 | 0.605 | 0.728 | 0.790 | 0.486 |
| 8 | `eval_anchor_v3_450_both.md` | `gt_testset_retrieval_450` | both | **215** | 0.310 | 0.605 | 0.754 | 0.855 | 0.487 |
| 9 | `eval_v3_355_anchored.md` | 355_anchored | chunk_id | 181 | 0.459 | 0.707 | 0.794 | 0.851 | 0.598 |

> ⚠️ **#5와 #6의 수치가 완전히 동일하다.** 앵커 부착본과 미부착본이 같은 값을 낸다는 것은
> 이 리포트들이 **앵커 채점이 아니라 `chunk_id` 채점**으로 생성됐다는 뜻이다.
> 즉 **커밋된 `.md` 리포트에는 정본 수치(.891)가 없다.** 수합 시 4-A를 쓰고, 4-B는
> "구세대 채점 기준의 참고치"로만 취급할 것. → §8-2

### 4-C. 표 원자성 A/B (참고 · `eval_tablefix.py`)

| 설정 | 청크 | K5 전체 | K5 single | K5 and | K3 single | K10 single |
|---|---:|---:|---:|---:|---:|---:|
| off (구) | 215 | 0.8209 | 0.8946 | 0.3091 | 0.7973 | 0.9541 |
| on `gap<=12` (채택) | **181** | **0.8977** | 0.9081 | 0.8182 | 0.8108 | 0.9541 |

`and` 상승분(0.309 → 0.818)에는 **gold 병합 30건(판정 완화)** 이 섞여 있다. 순수 검색 변화는 `single` 열.

---

## 5. 이 브랜치가 정본이라 주장하는 것 (claim)

| # | 대상 파일 | 종류 | 대체 대상 | 근거 (한 줄) |
|---|---|---|---|---|
| 1 | `final_testset/gt_natural430_anchored.jsonl` | GT (TEST) | `testset_natural_450.jsonl` · `gt_natural355*` | **앵커텍스트 판정**으로 전환해 재청킹에 견딤. 430건 전수 수작업 + 앵커 38개 수기 보강. relation(single/and/or) 정규화 완료 |
| 2 | `final_testset/gt_natural505_val.jsonl` | GT (VAL) | 없음 | **TEST와 분리된 held-out.** 파라미터 스윕을 VAL에서 확정해 순환 측정을 끊음 |
| 3 | `crawler/eval_anchor_v3.py` | eval | `crawler/eval.py` | `parent_doc_id` 판정의 '같은 문서면 적중' 거품 제거. `chunk_id`/`anchor`/`both` 3채점 + relation 조건 + macro recall |
| 4 | `crawler/rag.py` 파라미터 세트 | param | 없음 | 181청크에서 5축 그리드(3,360 config) 재튜닝. **181청크와 한 세트로만 유효** |
| 5 | `crawler/chunk.py` `TABLE_GAP_MAX` | param/코퍼스 | 없음 | 표 셀 `<br>`이 표 원자성을 깨던 문제 수정. K5 전체 .8209 → .8977 |

**주장하지 않는 것**

- **리랭커 계열** (`rerank_colab/*`) — hit@5 이득이 2문항. hit@1은 `+.0605`/`+.1127`로 크지만
  **미채택 상태**이며 UI 방향 결정(`phase3_milestone` M4.2)이 선행이다. 정본 후보 아님
- **`gt_testset_retrieval_450.jsonl`** — `eval_router_facet` 실험 전용으로만 남아 있음
- **`eval.py`** — 구세대 판정. 다른 브랜치가 이걸 개선했다면 그쪽을 따르되, 판정 기준은 #3로 통일 권고

---

## 6. 알려진 결함·캐비앗

| 항목 | 값 | 비고 |
|---|---|---|
| self-referential 문항 비율 | **미확인** | H12/H18 계열. 자연어 확장분은 구어체로 재작성했으나 비율 미집계 |
| held-out 여부 | **TEST/VAL 분리 완료** | 단 TEST는 개발 중 반복 노출됨. VAL(.8535)이 더 정직한 수치 |
| 파라미터 튜닝에 사용한 셋 | VAL (`gt_natural505_val`) | TEST와 분리. 단 표 원자성 A/B는 TEST에서 봤다 |
| 시드 분산 | **미확인** | 검색은 결정론이라 시드 무관. 단 **동점 처리 구현 의존성** 있음(§3) |
| 청크 ID 참조 자산 유무 | **있음 — 위험** | 앵커 결측 34문항(TEST 22·VAL 12)이 `chunk_id` 폴백. 재청킹 시 이 문항들이 조용히 깨진다 |
| 평가셋 ↔ 라우터 학습셋 겹침 | **과거 100% 겹침 → 해소** | `gt_natural400`이 라우터 학습셋과 전량 중복이었다. 폐기 사유 |
| QFORM 문항 혼입 | **TEST에 27건** | 검색 지표에 섞여 검색을 실제보다 나쁘게 보이게 한다. 주지표 정의 합의 필요 |
| 라우터 일반화 | **355셋 오분류 16.6%** | 학습셋이 어휘 신호 있는 질문에 편중된 것으로 추정 |
| `and` 문항 구조적 저성능 | Hit@5 0.291 (55건) | 가설 4개 기각 후 진단 진행 중 |
| 라우터 모델 배포 | **git 미추적 2.3GB** | 클론만 하면 **키워드 폴백**으로 돌고 위 수치가 재현되지 않는다. `BF_BOOST`가 0.005→0.06(12배)이라 폴백 시 오분류를 증폭할 수 있다 |

---

## 7. 충돌 예상

| 파일 | 다른 브랜치도 수정했을 가능성 | 비고 |
|---|---|---|
| `crawler/eval.py` | **높음** | 이 브랜치는 판정을 앵커로 옮겼고 `eval_anchor_v3.py`를 별 파일로 뒀다. 다른 브랜치가 `eval.py` 내부를 고쳤다면 **양립 불가** — 파일 단위로 택일 |
| `crawler/rag.py` | **높음** | 파라미터 6종 + 라우터 주입. Qform 트랙은 rag.py 무수정 원칙이라 충돌은 적을 것으로 예상하나 값이 전부 다르다 |
| `crawler/data/chunks.jsonl` | **높음** | 181 vs 215. 코퍼스는 원자 교체 대상 |
| `crawler/chunk.py` | 중간 | `TABLE_GAP_MAX` 신설 |
| `final_testset/*` | 낮음 | 이 브랜치에서 신설 |
| `crawler/data/eval_*.md` | 중간 | 리포트 산출물. 재생성 가능하므로 충돌 시 재생성 권고 |

---

## 8. 수합에 넘기는 미결 사항

1. **워킹트리 178청크 vs HEAD 181청크** — 미커밋 변경(+19/−22)의 정체 확정.
   커밋할지 되돌릴지 정해야 §4 수치의 유효성이 결정된다. **재측정 필요 여부가 여기 걸림.**
2. **커밋된 `.md` 리포트에 정본 수치가 없다** (§4-B 경고). 앵커 채점으로 리포트를 **재생성**할지,
   결론문서 §1을 수치 원천으로 인정할지.
3. **주지표 정의** — TEST에 섞인 QFORM 27건을 검색 지표에서 분리할지. 분리하면 수치가 올라가므로
   **분리 전/후를 같은 표에 병기**해야 한다.
4. **TEST 430 vs VAL 505** 중 어느 것을 브랜치 간 비교의 공통 축으로 쓸지.
   TEST는 개발 중 노출됐고 VAL이 더 정직하지만, 다른 브랜치가 VAL을 갖고 있지 않을 수 있다.
5. **앵커 결측 34문항** — `chunk_id` 폴백을 유지할지, 표→markdown 파싱(P2)을 선행할지.
   재청킹이 상수라면 이 34문항이 반복 파손 지점이다.
6. **라우터 모델 배포 방식** — 별도 다운로드 / LFS / 폴백 전제 운영. 미결이면 다른 사람이
   이 브랜치의 수치를 재현할 수 없다.

---

## 부록 A. 확인 명령 모음

```bash
# 메타
git rev-parse --abbrev-ref HEAD && git rev-parse --short HEAD

# 코퍼스 지문 (워킹트리 / HEAD 양쪽)
wc -l crawler/data/chunks.jsonl
sha256sum crawler/data/chunks.jsonl | cut -c1-12
git show HEAD:crawler/data/chunks.jsonl | wc -l
git show HEAD:crawler/data/chunks.jsonl | sha256sum | cut -c1-12
git log -1 --format=%h -- crawler/data/chunks.jsonl

# 파라미터 실제 값
grep -nE "^(MODEL_NAME|EMB_DIM|RRF_ALPHA|RRF_K|BF_BOOST|BF_MODE|BF_DOC_CAP|FACET_BOOST)" crawler/rag.py

# GT 문항 수·키
for f in final_testset/*.jsonl; do echo -n "$f "; wc -l < "$f"; done
head -1 final_testset/gt_natural430_anchored.jsonl | python3 -c "import json,sys;print(list(json.load(sys.stdin).keys()))"

# 정본 평가 재현
cd crawler && python eval_anchor_v3.py --gt ../final_testset/gt_natural430_anchored.jsonl
```

## 부록 B. 수합 LLM을 위한 판정 규칙 (제출자는 수정하지 말 것)

1. **지문 우선.** `corpus.chunk_count` 또는 `file_sha256`이 다른 제출서의 §4 수치는
   서로 비교하지 않는다. 비교하려면 동일 지문에서 **재측정**을 요구한다.
2. **판정 방식이 다르면 다른 축.** `gt_chunk_id` 판정 수치와 `gt_anchors` 판정 수치를
   같은 표에 놓고 우열을 말하지 않는다.
3. **근거 없는 claim 기각.** §5에 근거 한 줄이 없으면 후보에서 제외한다.
4. **no-numbers-no-merge.** §4가 `미측정`인 claim은 정본으로 채택하지 않는다.
5. **held-out 아님을 우대하지 않는다.** 튜닝 셋으로 낸 높은 수치는 낮은 held-out 수치보다
   **약한** 근거다.
6. **재청킹 내구성을 가점한다.** 청크 ID 판정보다 앵커텍스트 판정을 선호한다 —
   코퍼스가 계속 재생성되는 프로젝트이기 때문이다.
7. 판정 결과는 **파일 단위로** 낸다(브랜치 단위 승자 선정 금지). GT는 A 브랜치,
   eval 스크립트는 B 브랜치가 정본일 수 있다.

---

## 부록 C. 2026-08-24 eval 통합 반영표 (제출서 본문 무수정 · 경로 변경 안내)

> 본문(§1~§8·부록 A·B)은 제출 당시 상태로 **한 글자도 고치지 않았다.** 아래는 그 이후
> 수합 작업에서 파일 경로가 바뀐 것만 옮겨 적은 것이다. 수치·판정 규약·GT 선정 결과는
> 전부 그대로 유효하다. 근거: `DECISIONS.md` D13 (08-24).

§3 이 열거한 평가 스크립트 6개를 **`crawler/eval.py` 한 파일로 합쳤다.** 이 제출서가
"정본"으로 주장한 `eval_anchor_v3.py` 의 로직은 **이름 변경 0건으로** 통합 파일 §4 에
이식했고, 등가성을 `crawler/tests/test_eval_equivalence.py` 가 회귀 테스트로 못박았다
(구 평가기와 반환 dict·리포트 마크다운 바이트 동일 · faiss 없이 실행 가능).

| 제출서 본문의 경로 | 현재 경로 | 실행 명령 |
|---|---|---|
| `crawler/eval_anchor_v3.py` (**정본**) | `crawler/eval.py` §4 | `python eval.py chunk --gt …` (인자 없이 `python eval.py` 도 동일) |
| `crawler/eval.py` (구세대·폐기) | `archive/superseded/eval_doc_legacy.py` | 기본 평가셋 `data/testset_natural_400.jsonl` 부재 → 실행 불가 |
| `crawler/eval_TF.py` | `archive/superseded/eval_TF.py` | 기본 평가셋 `data/router_trainset_v1.jsonl` 부재 → 실행 불가 |
| `crawler/eval_pair.py` | `archive/superseded/eval_pair.py` | 기본 평가셋 `data/testset_natural.jsonl` 부재 → 실행 불가 |
| `crawler/eval_tablefix.py` | `crawler/exp_tablefix.py` | `python exp_tablefix.py` |
| `crawler/eval_router_facet.py` | `crawler/exp_router_facet.py` | `python exp_router_facet.py` |
| `crawler/eval_overlap.py` | `crawler/exp_overlap.py` | `python exp_overlap.py` |
| `crawler/eval_docinput.py` | `crawler/exp_docinput.py` | `python exp_docinput.py` |
| (제출서 미기재) `eval_anchor_span_multi.py` | `crawler/eval.py` §5 | `python eval.py span --gt …` |
| (제출서 미기재) `eval_anchor_gold.py` | `crawler/eval.py` §6 | `python eval.py gold --gt … --retrieved …` |

산출 리포트 기본 파일명도 바뀌었다 — `eval_anchor_v3_report.md` → `eval_chunk_report.md`,
`eval_anchor_span_multi_report.md` → `eval_span_report.md`. §4-B 가 인용한 **커밋된 리포트
파일들은 덮이지 않는다**(옛 이름 그대로 남는다). 실험 스크립트의 산출물명
(`eval_tablefix_report.md` 등)은 `admin/metrics.py` 가 수치 근거로 인용하고 있어 **바꾸지 않았다.**

### 부록 A 명령 갱신분

```bash
# 정본 평가 재현 (제출서 부록 A 마지막 줄의 현행 등가 명령)
cd crawler && python eval.py chunk --gt ../final_testset/gt_natural430_anchored.jsonl

# 통합이 판정을 바꾸지 않았음을 확인 (검색 스택 불필요)
python3 crawler/tests/test_eval_equivalence.py
```

### §8 미결 사항에 대한 영향

§8 의 6개 미결 사항은 **하나도 해소되지 않았다.** 통합은 코드 배치만 바꿨고
코퍼스 지문(178 vs 181) · 리포트 재생성 · 주지표 정의 · TEST/VAL 축 선정 · 앵커 결측 34문항 ·
라우터 배포 방식은 전부 그대로 열려 있다. 특히 §8-2("커밋된 .md 에 정본 수치가 없다")는
리포트 기본 파일명이 바뀌면서 **옛 리포트가 덮이지 않게 됐을 뿐**이며, 앵커 채점으로
재생성할지 결론문서 §1 을 수치 원천으로 인정할지는 여전히 미결이다.
