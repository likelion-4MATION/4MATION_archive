---
# ── 기계 판독부 (수합 LLM이 먼저 읽는 곳) · 값은 추측 금지, §확인 명령으로 뽑아 채운다 ──
author: 규남
branch: feature/kokopas
commit: be992d3
written_at: 2026-08-20
corpus:
  chunks_path: crawler/data/chunks.jsonl
  chunk_count: 181                  # 커밋됨(c942bc0). 워킹트리 clean
  file_sha256: d2197067fc8c
  embed_model: dragonkue/BGE-m3-ko
  embed_dim: 1024
  index_rebuilt: true               # pipeline.py --use-cache --rebuild, 181청크 기준
  router_used: false                # MOAI 라우터 배선을 rag.py에서 제거(c942bc0). 체크포인트도 로컬 없음
params:                             # be992d3 시점 rag.py 실제 값
  k: 30                             # RETRIEVAL_DEPTH=30, MRR은 @10 고정
  RRF_ALPHA: 0.6
  RRF_K: 5
  BF_MODE: soft
  BF_BOOST: 0.04
  BF_DOC_CAP: 3
  FACET_BOOST: 0.1
  rerank: none
  DENSE_W: 0.5                      # 표준 항목 외 — RRF 위 dense 원점수 연속항
  TITLE_W: 0.04                     # 표준 항목 외 — 제목 토큰 교집합 가산
  query_synonyms: 13                # 표준 항목 외 — BM25 질의측 동의어 확장
claims:
  - path: crawler/data/gt_natural450_v10_anchor.jsonl
    kind: gt
    supersedes: crawler/data/gt_natural450_v9_dupfix2.jsonl
  - path: crawler/eval_anchor_gold.py
    kind: eval
    supersedes: crawler/eval_anchor_v3.py
  - path: crawler/rag.py
    kind: param
    supersedes: none
open_questions: 4
---

# 평가 수합 제출서 — `feature/kokopas` (`규남`)

> **목적** 각 브랜치의 eval 방법과 GT 중 **가장 정확한 버전**을 골라 하나로 합치기 위한 제출서.
> **원칙** ① 값은 **실행해서** 채운다(기억·추정 금지) ② 모르는 건 `미측정`으로 남긴다
> ③ 수치에는 **항상 코퍼스 지문을 붙인다** — 지문이 다른 수치는 비교 대상이 아니다.

> **이 문서는 요약이다.** 라운드별 실험·기각 이력 전문은
> [eval_anchor_규남.md](eval_anchor_규남.md)(750줄, 4라운드 통합 리포트)에 있다.

---

## 1. 코퍼스 지문 (필수 · 이게 없으면 §4 수치는 무효)

| 항목 | 값 | 확인 방법 |
|---|---|---|
| `chunks.jsonl` 청크 수 | **181** (38문서) | `wc -l crawler/data/chunks.jsonl` |
| 파일 sha256 (앞 12자) | **d2197067fc8c** | `sha256sum crawler/data/chunks.jsonl` |
| 임베딩 모델 / 차원 | `dragonkue/BGE-m3-ko` / 1024 (FAISS IndexFlatIP) | `rag.py:20,22` |
| sparse | `rank_bm25` BM25Okapi + kiwi 형태소 토큰 | `rag.py` |
| 인덱스 재생성 여부 | **예** — `pipeline.py --use-cache --rebuild`로 181청크 기준 재빌드 후 측정 | 세션 기록 |
| 라우터 상태 | **폴백** — MOAI 라우터 배선을 `rag.py`에서 제거(c942bc0). 체크포인트도 로컬 미보유 | `grep -n router crawler/rag.py` → 히트 0 |
| 마지막 재청킹 커밋 | `c942bc0` | `git log -1 --format=%h -- crawler/data/chunks.jsonl` |

> ✅ **이전 제출서(60d3f86 시점)의 "미커밋 워킹트리" 경고는 해소됐다.** `chunks.jsonl`은
> `c942bc0`에 커밋돼 있고 워킹트리도 clean이다. §4 수치는 전부 커밋된 지문에서 재현 가능하다.

---

## 2. GT(정답셋) 목록

| # | 파일 경로 | 문항 수 | 판정 필드 | 다중정답 | split | 검수 상태 | 상태 | 파생 관계 |
|---|---|---:|---|---|---|---|---|---|
| 1 | `crawler/data/gt_natural450_v10_anchor.jsonl` | 450 (평가대상 **448**) | **`gt_anchor_span`** (주) + `gt_chunk_ids`(soft 등급 보조) | 허용 (앵커 보유 청크 평균 1.21개 / 등급 포함 relevant 평균 1.97개) | 미분리 | **전수** — `answerable=true` 448건 전부 `span_verbatim_ok=true`, 앵커 공란 0건 | **정본 주장** | v9_dupfix2 → 앵커 공란 18건에 `anchor_basis="retrieval"`로 앵커 부여 |
| 2 | `crawler/data/gt_natural450_v9_dupfix2.jsonl` | 450 (448) | `gt_chunk_ids` (+구형 `gt_chunk_id`) | 허용 (`chunk_relation` single 376 / and 69 / or 5) | 미분리 | 부분 | **폐기** (무수정 보존) | 45문항이 코퍼스에 없는 chunk를 gold로 참조 → 영구 0점. 324ae4e에서 원인 확정 |
| 3 | `crawler/data/testset_natural_450.jsonl` | 450 | `gt_docs` | 허용 | 미분리 | 미검수 | 후보 (untracked, 미사용) | v9 GT 질문의 원본 계열 |
| 4 | `crawler/data/testset_natural_400.jsonl` | 400 | `gt_docs` | 허용 | 미분리 | 부분 | 후보 — `eval.py` 정본 GT (다른 축) | `origin_question`/`source` 보유 |
| 5 | `testset_natural_300{,_v2,_v3}.jsonl`, `testset_natural.jsonl`, `testset_merged.jsonl`, `testset.jsonl`, `testset_para20.jsonl`, `testset_yesom.jsonl`, `yesom_qa.jsonl` | 각 상이 | `gt_docs` | — | 미분리 | 미검수 | **폐기** | 7월 이전 초기 셋 |
| 6 | `crawler/data/router_testset_v3_1.jsonl` | — | 라우터 분류 라벨 (검색 GT 아님) | — | — | 미확인 | 폐기 (라우터 제거로 무의미) | 별도 축 |

**판정 필드 값 정의**

- [x] `gt_anchors` — **정본(#1)의 주 판정 필드.** `gt_anchor_span`을 **원문 그대로 포함한 청크**를
      매 평가마다 코퍼스에서 재계산 → chunk_id 매핑 자산이 아예 없다. 재청킹에 완전히 견딤
- [x] `gt_chunk_id` / `gt_chunk_ids` — #1에서는 **soft/nDCG 등급용 보조**로만 쓴다(GT가 함께 relevant로
      라벨한 청크). #2에서는 주 판정 필드였고, 그게 폐기 사유다
- [x] `gt_docs` — GT #3~#5. `eval.py`/`eval_TF.py` 계열이 소비
- [ ] 기타: `chunk_relation`은 #1의 파일에 남아 있으나 **`eval_anchor_gold.py`는 읽지 않는다** — v9의 ALL 판정 규칙은 폐기됐다

**필드 스키마 실물 1줄** (`gt_natural450_v10_anchor.jsonl`)

```
['id', 'business_function', 'question', 'answerable', 'evidence_type', 'chunk_relation', 'gt_chunk_ids', 'gt_chunk_id', 'multi_chunk', 'gt_anchor_span', 'answer_bf', 'cross_domain', 'span_verbatim_ok', 'confidence', 'reason']
```

`testset_natural_450.jsonl` / `testset_natural_400.jsonl`:

```
['question', 'gt_docs', 'business_function', 'source', 'representative', 'origin_question']
```

**알려진 오라벨 / 미검수 구간** (GT #1 기준)

- `confidence < 0.7` **27건** (평가대상 448 중, 최저 0.45) — 라벨러 자기신뢰도 낮은 구간, 전수 재검수 안 함.
- `evidence_type='inferable'` **30건** — 직접 근거가 아닌 추론 근거. 앵커 스팬 판정과 궁합이 나쁠 수 있음.
- `anchor_basis="retrieval"` **18건** — generator가 "단일 verbatim 정답 문장 없음"으로 판정했던 문항에
  검색 기준 회수 대상 스팬을 부여한 것. 나머지 430건과 라벨 근거가 다르다.
- `crawler/data/dupfix_v2_ambiguous.md` — v9 시절 dupfix v2가 후보로 올렸으나 자동 채택 안 한 중복게재 후보. 미판정.
- `answerable=false` 2건은 분모에서 제외.

---

## 3. 평가 스크립트 목록

| # | 파일 | 용도 | 판정 로직 (한 줄) | 소비 GT | 산출 리포트 | 상태 |
|---|---|---|---|---|---|---|
| 1 | `crawler/eval_anchor_gold.py` | **정본 평가** | gold 앵커 스팬을 **공백 정규화 후 부분문자열 포함**하는 청크를 매번 코퍼스에서 재계산 → top-k 내 최초 적중 rank. strict/soft/nDCG + Wilson CI + McNemar | `gt_natural450_v10_anchor.jsonl` | 콘솔 → `docs/handoff/eval_anchor_규남.md` | **정본** |
| 2 | `crawler/cache_retrieval.py` | 정본 평가의 전단 | `rag.Searcher.search(q, k=30, mode="hybrid_bf")` 결과를 jsonl로 캐시 | — | `data/retrieved_top30_*.jsonl` | 정본(부속) |
| 3 | `crawler/eval_anchor_v3.py` | 구 정본 (청크 ID 판정) | top-30 `chunk_id`를 `gt_chunk_ids`와 직접 비교, `chunk_relation`으로 ANY/ALL | `gt_natural450_v9_dupfix2.jsonl` | `data/eval_anchor_v3_report.md` | **폐기** (무수정 보존) |
| 4 | `crawler/eval_fusion_sweep.py` | 융합식 파라미터 스윕 하네스 | `data/qscore_cache.npz`(질의×청크 점수 캐시) 위에서 모델 재실행 없이 스윕 | 〃 #1 | 콘솔 | 후보(실험 도구) |
| 5 | `crawler/eval.py` | 문서 단위 평가 (D1 게이트) | `chunk["parent_doc_id"] in gt_docs`면 적중. micro/macro 병기 | `testset_natural_400.jsonl` | `data/eval_report.md` | 후보 (다른 축) |
| 6 | `crawler/eval_TF.py` | 원인분석판 | `eval.py`와 판정 로직 동일 + 미적중 원인 분류 | 〃 | `data/error_analysis_TF.md` | 후보 |
| 7 | `eval_facet.py`, `eval_softboost.py`, `eval_rrf_tune.py`, `eval_rrfk.py`, `eval_embedinput.py`, `eval_mmr.py`, `eval_cap.py`, `eval_hit5*.py`, `eval_exclude.py`, `eval_pair.py`, `eval_rerank.py` | 파라미터 스윕 / 실험 | 전부 **doc 단위** 판정 | `testset_natural_300*/400` | 콘솔 | 실험 (리랭커·MMR 미채택) |
| 8 | `crawler/p2_parent_expand.py` | 실험 (parent 인접청크 확장 진단) | 순위 무관 evidence-set 회수율 | v9 GT | `data/p2_parent_expand_report.md` | 실험 (untracked, 미채택) |
| 9 | `diag_hit5.py`, `diag_ndcg.py`, `diag_rerank.py` | 실패 진단 | 지표 없음, 사례 덤프 | — | 콘솔 | 실험 |

**정본으로 주장하는 스크립트 1개**

- 파일: `crawler/eval_anchor_gold.py`
- 실행 명령:
  ```bash
  cd crawler
  # 1) 현재 코드의 검색 결과 재생성 (모델 로드 필요)
  HF_HUB_OFFLINE=1 PYTHONIOENCODING=utf-8 \
    python cache_retrieval.py data/index data/retrieved_top30_kunam.jsonl
  # 2) 평가 (+ 라운드1 baseline 대비 McNemar)
  python eval_anchor_gold.py --retrieved data/retrieved_top30_kunam.jsonl \
         --compare data/retrieved_top30_base_cap99.jsonl --label "현재"
  ```
  ⚠️ Windows에서 1단계는 `HF_HUB_OFFLINE=1`(SSL 검증 우회) 없이는 실패. 코드 버그 아님.
  2단계는 캐시된 jsonl만 읽으므로 모델 없이 수초 내에 돈다.
- **결정론 여부**: **결정론적.** `eval_anchor_gold.py`·`rag.py` 어디에도 `random`/`seed`/`shuffle`
  호출이 없다. 리랭커·LLM 미사용. 2026-08-20 이 제출서 작성 시 §4 행 1을 **재실행해 소수점까지 동일**
  함을 확인했다. 단 **인덱스를 재빌드하면** 임베딩 부동소수 차이로 말단 순위가 흔들릴 수 있음 — 미측정.

---

## 4. 측정 결과 (실행해서 채운 것만)

**지문은 전 행 공통: 181청크 / `d2197067fc8c` (커밋 `c942bc0`).** GT #1의 sha256(앞 12자)은 `ce2282aa5042`.

| # | GT | 스크립트 | mode | k | hit@1 | hit@3 | hit@5 | MRR | 설정 | 측정일 | 재현 명령 |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|
| 1 | v10_anchor (448) | `eval_anchor_gold.py` | hybrid_bf | 30 | **0.522** | **0.808** | **0.895** | **0.678** (@10) | **현재 코드 (E+F, HEAD)** — strict 기준 | 2026-08-20 | `python eval_anchor_gold.py --retrieved data/retrieved_top30_kunam.jsonl` |
| 2 | 〃 | 〃 | 〃 | 30 | **0.612** | **0.846** | **0.924** | 미측정 | 현재 코드 — **soft 기준** (아래 지표 정의 참조) | 2026-08-20 | 위와 동일 (같은 실행이 두 기준을 함께 출력) |
| 3 | 〃 | 〃 | 〃 | 30 | 0.516 | 0.806 | 0.897 | 0.674 | 라운드3 (cap=3만, 동의어·곱셈부스트 없음) — strict | 2026-08-20 | `--retrieved data/retrieved_top30_cap3_real.jsonl` |
| 4 | 〃 | 〃 | 〃 | 30 | 0.605 | 0.844 | **0.926** | 미측정 | 라운드3 — **soft**. Hit@5 최고값이나 행 2와 순증 1문항, 유의성 없음 | 2026-08-20 | 위와 동일 |
| 5 | 〃 | 〃 | 〃 | 30 | 0.516 | 0.806 | 0.893 | 0.673 | 라운드1 baseline (`BF_DOC_CAP=99`) — strict | 2026-08-20 | `--retrieved data/retrieved_top30_base_cap99.jsonl` |
| 6 | 〃 | 〃 | 〃 | 30 | 0.475 | 0.804 | 0.888 | 0.649 | 라운드1 **이전** baseline (`DENSE_W`/`TITLE_W` 도입 전) — strict | 2026-08-20 | 리포트 D-1 |
| 7 | v9_dupfix2 (448) | `eval_anchor_v3.py` | hybrid_bf | 30 | 0.473 | 0.732 | 0.821 | 0.617 (@10) | **구 판정 기준(chunk_id + relation ALL)** — 행 1~6과 **다른 축, 비교 불가** | 2026-08-20 | `python eval_anchor_v3.py --gt data/gt_natural450_v9_dupfix2.jsonl --mode hybrid_bf` |
| 8 | `testset_natural_400` (400) | `eval.py` | dense / hybrid / hybrid_bf | 10 | 0.665 / 0.660 / 0.703 | 0.900 / 0.885 / 0.922 | 미측정 | 0.785 / 0.780 / 0.817 | **지문 미확인** — 리포트에 청크수·해시 없음, `RRF(k=4)` 표기로 현 `RRF_K=5`와 불일치 | 미확인 | `python eval.py` |

**보조 지표 (행 1·2 = HEAD)**

| nDCG@3 | nDCG@5 | nDCG@10 | Hit@10 (strict) | Hit@30 (strict) |
|---:|---:|---:|---:|---:|
| 0.676 | **0.724** | 0.762 | 0.962 | 0.980 |

**지표 정의 — 표준과 다른 점 (행 1~6)**

| 지표 | 정의 |
|---|---|
| **strict Hit@k** | gold 앵커 스팬을 **원문 그대로(공백 정규화 후) 포함한 청크**가 top-k에 있으면 성공. 문항당 앵커 보유 청크 평균 **1.21개**, ANY 판정 |
| **soft Hit@k** | 위 앵커 청크 **∪ GT가 함께 라벨한 `gt_chunk_ids`** 중 하나라도 top-k에 있으면 성공. 문항당 relevant 평균 **1.97개** |
| **nDCG@k** | 앵커 청크=2 / GT 라벨 청크=1 등급 |
| **MRR** | 항상 **MRR@10 고정** (RETRIEVAL_DEPTH=30과 무관). 2026-08-11 결정 |
| 분모 | `answerable=true` **448건** (450 − 2) |

> **목표 지표는 soft Hit@5**로 확정했다 — 서빙이 LLM에 top-5를 넣으므로 Hit@5가 답변 가능 여부를 가른다.
> Hit@1의 Wilson 95% CI 폭이 **±4.6pp**(n=448)이므로, **이보다 작은 차이는 이 평가셋으로 구분 불가**다.
> 행 2 vs 행 4(0.924 vs 0.926 = 1문항)를 우열로 읽지 말 것.

**업무별 분해 (행 1, strict)**

| 업무 | n | Hit@1 | Hit@3 | Hit@5 | Hit@10 |
|---|---:|---:|---:|---:|---:|
| 예금자보호제도 | 84 | 0.536 | 0.869 | 0.976 | 0.988 |
| 착오송금 반환 신청 | 84 | 0.548 | 0.762 | 0.869 | 0.976 |
| 채무조정 안내 | 78 | 0.577 | 0.885 | 0.923 | 0.962 |
| **고객 미수령금 신청** | 75 | **0.347** | 0.733 | 0.827 | 0.880 |
| 예금보험금 안내 | 65 | 0.523 | 0.800 | 0.892 | 0.985 |
| 은닉재산 신고 | 62 | 0.613 | 0.790 | 0.871 | 0.984 |

**유의성 (행 1 vs 행 5, McNemar)** — 27/6, **p=0.0003 (유의)**. 행 5 vs 행 6은 24/6, p=0.0014 (유의).

---

## 5. 이 브랜치가 정본이라 주장하는 것 (claim)

| # | 대상 파일 | 종류 | 대체 대상 | 근거 (한 줄) |
|---|---|---|---|---|
| 1 | `crawler/data/gt_natural450_v10_anchor.jsonl` | GT | `gt_natural450_v9_dupfix2.jsonl`, `testset_natural_4[05]0.jsonl` | 판정을 chunk_id에서 앵커 스팬으로 옮겨 **chunk_id 매핑 자산을 GT에서 완전히 제거** — 재청킹해도 GT가 썩지 않는다. v9에서 45문항이 코퍼스에 없는 chunk를 gold로 참조해 검색기와 무관하게 영구 0점이던 결함을 실측으로 확인하고 제거했다(앵커 미수록 0건). |
| 2 | `crawler/eval_anchor_gold.py` | eval | `crawler/eval_anchor_v3.py`, `crawler/eval.py`(문서 단위) | 앵커 포함 청크를 **매 평가마다 코퍼스에서 재계산**하므로 코퍼스 세대와 무관하게 동작. strict/soft/nDCG를 함께 내 판정 기준 차이를 숨기지 않고, Wilson CI와 McNemar를 내장해 "구분 불가한 차이"를 수치로 표시한다. 랜덤 요소 없음(재실행 소수점 일치 확인). |
| 3 | `crawler/rag.py` 검색 파라미터 (`RRF_ALPHA=0.6`/`RRF_K=5`/`BF_MODE=soft`/`BF_BOOST=0.04`/`BF_DOC_CAP=3`/`FACET_BOOST=0.1`/`DENSE_W=0.5`/`TITLE_W=0.04`/동의어 13항) | 파라미터 | anc 브랜치 파라미터 세트 | 같은 GT·같은 181청크에서 라운드1→4 누적 A/B. 최종 vs 라운드1 baseline McNemar **p=0.0003 유의**. `BF_DOC_CAP=3`은 **독립 진행된 두 세션이 각각 도달**한 값(상호 검증). 전 파라미터 재스윕에서 현행값이 고원 정점임을 확인했고, 기각 이력(정규화 fusion·제목 IDF·MMR·재청킹 188청크 등)도 같은 절차로 남겼다. |
| 4 | `docs/handoff/eval_anchor_규남.md` | 리포트 | none | 라운드1~4 전 실험의 채택·기각 근거와 **뒤집힌 결론 목록(0-7)** 까지 한 파일에 통합. 재실험 금지 목록을 명시해 수합 후 중복 탐색을 막는다. |

**주장하지 않는 것**

- `crawler/eval.py` / `eval_TF.py` — 문서 단위 판정이라 **다른 축**(D1 게이트). 폐기 아님, 이 축의 정본은 다른 브랜치 것이 나을 수 있음.
- `crawler/data/testset_natural_400.jsonl` — 이 브랜치에서 검수·개선하지 않았음.
- `crawler/eval_anchor_v3.py` + `gt_natural450_v9_dupfix2.jsonl` — **폐기하되 무수정 보존.** 다른 브랜치가 이 파일명을 정본이라 주장할 경우 §2 #2의 45문항 결함을 근거로 기각을 요청한다.
- 리랭커 관련(`eval_rerank.py`, `diag_rerank.py`) — 이번 라운드 금지 조건이었음. 미채택.
- `crawler/faq_bf_map.py` — `rag.py`에서 미참조(c942bc0에서 배선 제거). 보존만.
- `crawler/p2_parent_expand.py`, `crawler/data/reembed.py` — untracked 실험/유틸, 미채택.
- MOAI 라우터 관련 일체 — 체크포인트 미보유로 검증 불가.

---

## 6. 알려진 결함·캐비앗 (필수 · 빈칸 금지)

| 항목 | 값 | 비고 |
|---|---|---|
| self-referential 문항 비율 | **미확인 (사실상 높다고 봐야 함)** | 질문이 코퍼스 문서 본문에서 파생된 계열이고, 앵커 448건이 **전량 `span_verbatim_ok=true`**(앵커가 청크 원문 그대로)다. 실사용 질의는 이보다 낮게 나올 것 — **§4 수치를 배포 기대치로 쓰면 안 된다.** 실로그 50~100건 검증셋이 필요(리포트 G-3.2). |
| held-out 여부 | **개발 중 노출됨** | §4 행 1의 파라미터를 **같은 448건으로 골랐다.** 아래 참조. |
| 파라미터 튜닝에 사용한 셋 | `gt_natural450_v10_anchor.jsonl` (§4 행 1~6과 **동일 셋**) | **순환.** 라운드1~4의 A/B가 전부 이 셋에서 채택/기각을 결정했고 최종 수치도 같은 셋. 부록 B-5에 따라 held-out 수치보다 **약한** 근거로 취급되어야 한다. |
| 시드 분산 | **단일 시드** (사실상 결정론) | 랜덤 요소 없음(§3). 재실행 소수점 일치 확인. 단 인덱스 재빌드 시 부동소수 재현성은 미측정. |
| 청크 ID 참조 자산 유무 | **정본 GT의 주 판정에는 없음.** 단 `gt_chunk_ids`가 soft/nDCG 등급에 쓰이므로 **soft 지표는 재청킹에 취약**하다 | strict 지표는 앵커만 쓰므로 재청킹 무관. 재청킹 시 **soft/nDCG만 재라벨 필요**. 그 밖에 `retrieved_top30_*.jsonl`(검색결과 캐시)과 v9 GT·`eval_anchor_v3_report.md`가 chunk_id 참조 — 전자는 재생성하면 되고 후자는 폐기 자산. |
| 기타 알려진 문제 | (1) **엔드투엔드 평가 부재** — 전 지표가 retrieval-only. top-k 개선이 답변 정확도로 얼마나 옮겨가는지 미측정. 실패의 29%는 "같은 문서 내 다른 청크가 1위" 유형이라 답변 품질에 무해할 수 있고, 그렇다면 목표 지표 설정 자체가 재검토 대상. (2) `BF_DOC_CAP=3`의 **비용으로 Hit@30이 0.996→0.980**으로 떨어졌다. top-10 이상을 컨텍스트로 쓰는 서빙이면 되돌려야 한다. (3) **`고객 미수령금 신청` 75건이 단독 최약점**(strict Hit@1 0.347) — 타 업무 혼입이 큼. (4) 라운드2(D절)가 동의어·곱셈부스트를 유의성 미달로 **기각**했다가 라운드4(F절)가 "악화 0건"으로 **채택**했다 — 같은 실측치의 해석을 뒤집은 것이며, 채택 기준이 라운드마다 달랐다는 뜻이다. (5) `eval_report.md`(행 8)는 코퍼스 지문 없음 + `RRF(k=4)` 불일치 — **무효 처리 권장**. (6) `build_gt_dupfix_v2.py`는 old chunk_id로 새 인덱스를 조회해 문항이 조용히 스킵되는 버그가 있어 미적용. | |

---

## 7. 충돌 예상 (수합 전 확인용)

| 파일 | 다른 브랜치도 수정했을 가능성 | 비고 |
|---|---|---|
| `crawler/rag.py` | **높음** | anc 골격 + kokopas `chunk_embed_text()`(앵커 임베딩) 혼합에, `DENSE_W`/`TITLE_W`/`QUERY_SYNONYMS`/`expand_query_tokens()`/업무부스트 곱셈화가 추가됐다. FAQ BF map·MOAI router 배선은 **삭제**됨 — 그 배선을 유지하는 브랜치와 양립 불가. |
| `crawler/chunk.py` | **높음** | anc 버전(`TABLE_GAP_MAX=12`, 표 흡수)으로 교체. 청크 181. |
| `crawler/data/chunks.jsonl` | **높음** | 재청킹 산출물. 지문이 바뀌면 §4 **soft/nDCG만** 재라벨, strict는 재측정만 하면 됨. |
| `crawler/data/gt_natural450_v9_dupfix2.jsonl` | **중간** | 같은 파일명으로 다른 corpus 세대 매핑본이 존재할 수 있다. 어느 쪽이든 이 브랜치는 **폐기 주장**(§5). |
| `crawler/eval_anchor_gold.py` | **낮음** | 이 브랜치 신규(324ae4e). 다만 판정 축이 앵커라 chunk_id·doc 판정 스크립트와 양립 불가. |
| `crawler/eval_anchor_v3.py` | **중간** | 무수정 보존. 다른 브랜치가 정본 주장할 수 있음. |
| `crawler/eval.py` | 낮음 | 이 브랜치에서 미수정. |
| `docs/handoff/eval_*.md` | **없음** | 1인 1파일 규약. |

---

## 8. 수합에 넘기는 미결 사항

1. **주지표를 strict Hit@k로 할지 soft Hit@k로 할지.** 이 브랜치는 **soft Hit@5**를 목표로 확정했으나
   (서빙이 top-5를 LLM에 넣으므로), soft는 `gt_chunk_ids`에 의존해 **재청킹에 취약**하다.
   재청킹 내구성을 우선하면 strict로 가야 하고, 그러면 Hit@5가 0.924 → 0.895로 바뀐다.
   **수합은 하나로 통일하고 전 브랜치 재측정해야 한다.**
2. **판정 축 통일.** 이 브랜치는 앵커 스팬, 다른 브랜치는 chunk_id 또는 `gt_docs`일 가능성이 높다.
   부록 B-6(재청킹 내구성 가점)에 따르면 앵커가 우선이지만, 그러려면 **다른 브랜치 GT에도
   앵커 스팬을 부여**해야 한다 — 그 작업 비용을 누가 지는지 결정 필요.
3. **파라미터 튜닝 셋 = 평가 셋 문제(§6)를 어떻게 처리할지.** 448건을 train/val/test로 분할해
   재측정할지, 실로그 기반 held-out 셋(50~100건)을 새로 만들지. 현재 수치는 전부 순환 근거다.
   리포트 G-3.2가 후자를 권고한다.
4. **`confidence<0.7` 27건 + `anchor_basis="retrieval"` 18건을 GT에서 제외할지, 재검수할지.**
   제외하면 분모가 달라져 기존 수치와 비교 불가.

> **이전 제출서의 미결 2건은 해소됐다.** (구 #1 `and` relation ALL 판정 → 앵커 판정 전환으로 소멸.
> 구 #5 `chunks.jsonl` 미커밋 → `c942bc0`에 커밋 완료.)
