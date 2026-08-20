---
# ── 기계 판독부 (수합 LLM이 먼저 읽는 곳) · 값은 추측 금지, §확인 명령으로 뽑아 채운다 ──
author: 규남
branch: feature/kokopas
commit: 60d3f86
written_at: 2026-08-20
corpus:
  chunks_path: crawler/data/chunks.jsonl
  chunk_count: 181                  # 워킹트리 기준(커밋본은 185). ⚠️ 미커밋 상태
  file_sha256: d2197067fc8c         # 워킹트리. 커밋본(HEAD)은 92d91f0c9f40
  embed_model: dragonkue/BGE-m3-ko
  embed_dim: 1024
  index_rebuilt: true               # pipeline.py --use-cache --rebuild, 181청크 기준
  router_used: false                # MOAI 라우터 배선을 rag.py에서 제거(P0-4). 체크포인트도 로컬 없음
params:
  k: 30                             # RETRIEVAL_DEPTH=30, MRR은 @10 고정
  RRF_ALPHA: 0.6
  RRF_K: 5
  BF_MODE: soft
  BF_BOOST: 0.04
  BF_DOC_CAP: 4
  FACET_BOOST: 0.1
  rerank: none
claims:
  - path: crawler/data/gt_natural450_v9_dupfix2.jsonl
    kind: gt
    supersedes: crawler/data/testset_natural_450.jsonl
  - path: crawler/eval_anchor_v3.py
    kind: eval
    supersedes: crawler/eval.py
  - path: crawler/rag.py
    kind: param
    supersedes: none
open_questions: 5
---

# 평가 수합 제출서 — `feature/kokopas` (`규남`)

> **목적** 각 브랜치의 eval 방법과 GT 중 **가장 정확한 버전**을 골라 하나로 합치기 위한 제출서.
> **원칙** ① 값은 **실행해서** 채운다(기억·추정 금지) ② 모르는 건 `미측정`으로 남긴다
> ③ 수치에는 **항상 코퍼스 지문을 붙인다** — 지문이 다른 수치는 비교 대상이 아니다.

---

## 1. 코퍼스 지문 (필수 · 이게 없으면 §4 수치는 무효)

| 항목 | 값 | 확인 방법 |
|---|---|---|
| `chunks.jsonl` 청크 수 | **181** (워킹트리) / 185 (HEAD 커밋본) | `wc -l crawler/data/chunks.jsonl` |
| 파일 sha256 (앞 12자) | **d2197067fc8c** (워킹트리) / `92d91f0c9f40` (HEAD) | `sha256sum crawler/data/chunks.jsonl` |
| 임베딩 모델 / 차원 | `dragonkue/BGE-m3-ko` / 1024 | `rag.py:20,22` `MODEL_NAME`·`EMB_DIM` |
| 인덱스 재생성 여부 | **예** — `pipeline.py --use-cache --rebuild`로 181청크 기준 재빌드 후 측정 | 세션 핸드오프 기록 |
| 라우터 상태 | **폴백** — MOAI 라우터 배선 자체를 `rag.py`에서 제거(P0-4). 체크포인트(2.4GB)도 로컬 미보유 | `grep -n router crawler/rag.py` → 히트 0 |
| 마지막 재청킹 커밋 | `60d3f86` | `git log -1 --format=%h -- crawler/data/chunks.jsonl` |

> ⚠️ **이 제출서의 §4 수치는 전부 워킹트리(181청크 / `d2197067fc8c`) 기준이며 아직 커밋되지
> 않았다.** `git status`가 `M crawler/data/chunks.jsonl`. 수합 담당이 `git show 60d3f86:...`로
> 체크아웃하면 **185청크(`92d91f0c9f40`) — 다른 지문**이 나온다. §4 행 3번(커밋본 수치)과
> 행 1·2번(워킹트리 수치)은 **같은 표에 있지만 서로 다른 코퍼스**다.

---

## 2. GT(정답셋) 목록

| # | 파일 경로 | 문항 수 | 판정 필드 | 다중정답 | split | 검수 상태 | 상태 | 파생 관계 |
|---|---|---:|---|---|---|---|---|---|
| 1 | `crawler/data/gt_natural450_v9_dupfix2.jsonl` | 450 (평가대상 448) | `gt_chunk_ids` (+구형 `gt_chunk_id` 폴백), `gt_anchor_span` 보조 | **허용** (`chunk_relation` = single 376 / and 69 / or 5) | 미분리 | 부분 — `span_verbatim_ok=true` 430건 / `false` 20건, `confidence<0.7` 28건 | **정본 주장** | `gt_natural450_v7` → v9 → `build_gt_dupfix.py`로 중복게재 청크 보강(dupfix2). 2026-08-20 181청크 corpus 대상 **재실행**해 89/450건 `gt_chunk_ids` 갱신 |
| 2 | `crawler/data/testset_natural_450.jsonl` | 450 | `gt_docs` | 허용(문서 리스트) | 미분리 | 미검수 | 후보 (untracked, 미사용) | v9 GT의 질문 원본 계열. 이 브랜치에서는 채점에 안 씀 |
| 3 | `crawler/data/testset_natural_400.jsonl` | 400 | `gt_docs` | 허용 | 미분리 | 부분 (`label_eval_audit_report.md` 진단 있음) | 후보 — `eval.py` 정본 GT | 400셋. `origin_question`/`source`(new/yesom/short) 보유 |
| 4 | `crawler/data/testset_natural_300{,_v2,_v3}.jsonl` | 300 | `gt_docs` | 허용 | 미분리 | 미검수 | 폐기 (실험 스크립트 전용) | 400셋의 선행판 |
| 5 | `crawler/data/testset_natural.jsonl`, `testset_merged.jsonl`, `testset.jsonl`, `testset_para20.jsonl`, `testset_yesom.jsonl`, `yesom_qa.jsonl` | 각 상이 | `gt_docs` | — | 미분리 | 미검수 | **폐기** | 7월 이전 초기 셋 |
| 6 | `crawler/data/router_testset_v3_1.jsonl` | — | 라우터 분류 라벨 (검색 GT 아님) | — | — | 미확인 | 폐기 (라우터 제거로 무의미) | 별도 축 |

**판정 필드 값 정의**

- [x] `gt_chunk_id` / `gt_chunk_ids` — 청크 ID 일치로 정오 판정. **재청킹에 취약** → 정본 주장 GT(#1)의 주 판정 필드
- [x] `gt_anchors` — `gt_anchor_span` 필드로 보유. **채점에는 안 쓰고**, `build_gt_dupfix.py`가 재청킹 후 chunk_id를 **복구**하는 데 쓴다 (= 앵커로 청크ID를 재생성하는 하이브리드)
- [x] `gt_docs` — GT #2~#5. `eval.py`/`eval_TF.py` 계열이 소비
- [x] 기타: `chunk_relation`(single/or=ANY, and=ALL)로 다중근거 판정 강도를 문항별로 지정

**필드 스키마 실물 1줄** (`gt_natural450_v9_dupfix2.jsonl`)

```
['id', 'business_function', 'question', 'answerable', 'evidence_type', 'chunk_relation', 'gt_chunk_ids', 'gt_chunk_id', 'multi_chunk', 'gt_anchor_span', 'answer_bf', 'cross_domain', 'span_verbatim_ok', 'confidence', 'reason']
```

`testset_natural_450.jsonl` / `testset_natural_400.jsonl`:

```
['question', 'gt_docs', 'business_function', 'source', 'representative', 'origin_question']
```

**알려진 오라벨 / 미검수 구간**

- `span_verbatim_ok=false` **20건** — 앵커가 원문 verbatim이 아님 → `build_gt_dupfix.py`의 복구 대상에서 빠지므로 재청킹 시 dangling 위험이 남아 있는 구간.
- `confidence < 0.7` **28건** (최저 0.45) — 라벨러 자기신뢰도 낮은 구간, 전수 재검수 안 함.
- `evidence_type='inferable'` **30건** — 직접 근거가 아니라 추론 근거. 청크 단위 채점과 궁합이 나쁠 수 있음.
- `crawler/data/dupfix_v2_ambiguous.md` — dupfix v2(임베딩 유사도 기반)가 후보로 올렸으나 **자동 채택 안 한** 중복게재 후보 목록. 미판정 상태로 남아 있음.
- 2026-08-20 재매핑 전 기준으로 **6건**이 새 181청크 corpus에서 유효 gold 0개(완전 깨짐)였고, 재실행으로 전부 복구됨(zero-valid-gold 0건 확인).

---

## 3. 평가 스크립트 목록

| # | 파일 | 용도 | 판정 로직 (한 줄) | 소비 GT | 산출 리포트 | 상태 |
|---|---|---|---|---|---|---|
| 1 | `crawler/eval_anchor_v3.py` | **정본 평가** (청크 단위) | 검색 top-30의 `chunk_id`를 gold `gt_chunk_ids`와 직접 비교, `chunk_relation`으로 ANY/ALL 판정, `answerable=false`는 분모 제외 | `gt_natural450_v9_dupfix2.jsonl` | `crawler/data/eval_anchor_v3_report.md` | **정본** |
| 2 | `crawler/eval.py` | 문서 단위 평가 (D1 게이트) | `chunk["parent_doc_id"] in gt_docs`면 적중. micro/macro 병기 | `testset_natural_400.jsonl` | `crawler/data/eval_report.md` | 후보 (다른 축) |
| 3 | `crawler/eval_TF.py` | 원인분석판 | `eval.py`와 판정 로직 **완전 동일**, 미적중 원인 분류를 덧붙임 | `testset_natural_400.jsonl` | `crawler/data/error_analysis_TF.md` | 후보 |
| 4 | `crawler/eval_facet.py` | 파라미터 스윕 (FACET_BOOST A/B) | doc 단위 | `testset_natural_400.jsonl` | 콘솔 | 실험 |
| 5 | `crawler/eval_softboost.py` | 파라미터 스윕 (BF_BOOST) | doc 단위 | `testset_natural_400.jsonl` | 콘솔 | 실험 |
| 6 | `crawler/eval_rrf_tune.py`, `eval_rrfk.py` | 파라미터 스윕 (RRF_ALPHA / RRF_K) | doc 단위 | `testset_natural_400.jsonl` | 콘솔 | 실험 |
| 7 | `crawler/eval_embedinput.py` | 실험 (`chunk_embed_text` 입력 A/B) | doc 단위 | `testset_natural_400.jsonl` | 콘솔 | 실험 |
| 8 | `crawler/eval_mmr.py` | 실험 (MMR 다양화) | doc 단위 | `testset_natural_400.jsonl` | 콘솔 | 실험 (미채택) |
| 9 | `crawler/eval_cap.py`, `eval_rerank.py` | 실험 (BF_DOC_CAP / 리랭커) | doc 단위 | `testset_natural_300_v3.jsonl` | 콘솔 | 실험 (리랭커 미채택) |
| 10 | `crawler/eval_exclude.py` | 실험 (제외 필터) | doc 단위 | `testset_natural_300_v2.jsonl` | 콘솔 | 실험 |
| 11 | `crawler/eval_pair.py` | 실험 (원본 vs 패러프레이즈 랭크 비교) | 페어 랭크 델타 | 페어셋 | 콘솔 | 실험 |
| 12 | `crawler/p2_parent_expand.py` | 실험 (parent 인접청크 확장 진단) | 순위 무관 evidence-set 회수율 | `gt_natural450_v9_dupfix2.jsonl` | `crawler/data/p2_parent_expand_report.md` | 실험 (untracked, 미채택) |

**정본으로 주장하는 스크립트 1개**

- 파일: `crawler/eval_anchor_v3.py`
- 실행 명령:
  ```bash
  cd crawler && HF_HUB_OFFLINE=1 PYTHONIOENCODING=utf-8 \
    python eval_anchor_v3.py --gt data/gt_natural450_v9_dupfix2.jsonl --mode hybrid_bf
  ```
  ⚠️ `--gt`를 **반드시 넘겨야 한다.** 기본값이 `data/gt_natural450_v7.jsonl`인데 이 파일은
  브랜치에 실물이 없다(`eval_anchor_v3.py:485`). 기본값으로 돌리면 FileNotFound.
  ⚠️ Windows에서 `HF_HUB_OFFLINE=1`(SSL 검증 실패 우회) · `PYTHONIOENCODING=utf-8`
  (폴백 로그의 em dash가 cp949에서 죽음) 없이는 실행 실패. 코드 버그 아님.
- **결정론 여부**: **결정론적.** `eval_anchor_v3.py`·`rag.py` 어디에도 `random`/`seed`/`shuffle`
  호출이 없다(`grep -nE "random|seed|shuffle"` → 히트 0). 리랭커·LLM 미사용. 같은 인덱스에
  대해 재실행하면 같은 수치가 나온다. 단 **인덱스를 재빌드하면** 임베딩 부동소수 차이로
  말단 순위가 흔들릴 수 있음 — 미측정.

---

## 4. 측정 결과 (실행해서 채운 것만)

| # | GT | 스크립트 | mode | k | hit@1 | hit@3 | hit@5 | MRR | 코퍼스 지문 | 측정일 | 재현 명령 |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|
| 1 | `gt_natural450_v9_dupfix2.jsonl` (448) | `eval_anchor_v3.py` | hybrid_bf | 30 | **0.473** | **0.732** | **0.821** | 0.617 (@10) | 181 / `d2197067fc8c` (워킹트리) | 2026-08-20 | `HF_HUB_OFFLINE=1 PYTHONIOENCODING=utf-8 python eval_anchor_v3.py --gt data/gt_natural450_v9_dupfix2.jsonl --mode hybrid_bf` |
| 2 | 〃 | `eval_anchor_v3.py` | hybrid_bf | 30 | 0.469 | 0.717 | 0.812 | 0.609 (@10) | 181 / `d2197067fc8c` | 2026-08-20 | 위와 동일 (P0-4 파라미터 채택 **이전** baseline) |
| 3 | 〃 | `eval_anchor_v3.py` | hybrid_bf | 30 | 0.438 | 0.703 | 0.826 | 0.596 (@10) | **185 / `92d91f0c9f40`** (HEAD 커밋본) | 2026-08-20 이전 | `git stash && python eval_anchor_v3.py --gt ... --mode hybrid_bf` — **다른 지문, 행 1과 비교 불가** |
| 4 | `testset_natural_400.jsonl` (400) | `eval.py` | dense | 10 | 0.665 | 0.900 | 미측정 | 0.785 | 미확인 (리포트에 청크수·해시 미기재, RRF k=4 표기 → 현 파라미터와 불일치) | 미확인 | `python eval.py` |
| 5 | 〃 | `eval.py` | hybrid | 10 | 0.660 | 0.885 | 미측정 | 0.780 | 〃 | 〃 | 〃 |
| 6 | 〃 | `eval.py` | hybrid_bf | 10 | 0.703 | 0.922 | 미측정 | 0.817 | 〃 | 〃 | 〃 |

**지표 정의가 표준과 다른 점 (행 1~3, `eval_anchor_v3.py`)**

- **MRR은 항상 MRR@10 고정** (`MRR_DEPTH=10`, RETRIEVAL_DEPTH=30과 무관). 2026-08-11 결정.
- **hit@k는 `chunk_relation` 조건부**: `single`/`or`는 ANY(gold 하나만 top-k에 있으면 적중),
  `and`는 **ALL**(gold 전부가 top-k 안에 있어야 적중). 표준 hit@k보다 엄격하다.
- 분모는 `answerable=true` 448건 (전체 450 − 2).
- 주지표는 hit@k가 아니라 **MacroRecall@k**라고 리포트가 명시. 행 1 기준
  MacroRecall@3/5/10 = 0.639 / 0.758 / 0.862.

**행 1의 relation별 분해** (수합 시 hit@k 해석에 필요)

| relation | 문항수 | Hit@3 | Hit@5 | MRR |
|---|---:|---:|---:|---:|
| single | 374 | 0.829 | 0.906 | 0.704 |
| or | 5 | 0.800 | 1.000 | 0.740 |
| **and** | 69 | **0.203** | **0.348** | 0.137 |

→ 전체 hit@5 0.821은 `and` 69건의 0.348에 강하게 끌려내려간 값이다. **`and`를 ANY로
채점하는 다른 브랜치 수치와 직접 비교하면 안 된다.**

- 행 4~6은 **리포트에 코퍼스 지문이 없다.** 리포트 헤더가 `RRF(k=4)`로 되어 있는데 현재
  `rag.py`의 `RRF_K=5`라 **측정 시점 파라미터가 현재와 다르다.** 재측정 대상.

---

## 5. 이 브랜치가 정본이라 주장하는 것 (claim)

| # | 대상 파일 | 종류 | 대체 대상 | 근거 (한 줄) |
|---|---|---|---|---|
| 1 | `crawler/data/gt_natural450_v9_dupfix2.jsonl` | GT | `testset_natural_450.jsonl`, `testset_natural_400.jsonl` | 청크 단위 gold(`gt_chunk_ids`) + 다중근거 강도(`chunk_relation`) + 앵커스팬을 함께 보유 — 문서 단위 GT가 못 잡는 "같은 문서면 정답" 거품을 제거하고, 앵커로 재청킹 후 chunk_id를 결정론적으로 복구할 수 있다(181청크 corpus로 실제 재실행해 6건 전부 복구 확인). |
| 2 | `crawler/eval_anchor_v3.py` | eval | `crawler/eval.py`(문서 단위 판정) | `parent_doc_id` 매칭의 과대평가(`label_eval_audit_report.md`가 hit@3=0.945를 "과대평가 가능성"으로 진단)를 청크 ID 직접 비교로 대체. relation별/도메인별 분해와 gold coverage까지 산출하고, 랜덤 요소가 없어 결정론적. |
| 3 | `crawler/rag.py` 검색 파라미터 (`RRF_ALPHA=0.6`/`RRF_K=5`/`BF_BOOST=0.04`/`BF_DOC_CAP=4`/`FACET_BOOST=0.1`/`BF_MODE=soft`) | 파라미터 | anc 브랜치 파라미터 세트 | 같은 GT·같은 181청크에서 anc 값 대비 **개별 격리 A/B**로 전 지표 비하락 확인(hit@3 +0.013). 기각한 것(sibling-boost 복원 = hit@5 −0.011)도 같은 절차로 근거를 남김. `DECISIONS.md` P0-4 표 참고. |
| 4 | `crawler/data/build_gt_dupfix.py` | GT 생성 | none | 앵커스팬 verbatim 매칭으로 중복게재 청크를 gold에 보강하는 결정론적 스크립트. **corpus 세대가 바뀌어도 재사용 가능**(old chunk_id 존재 여부와 무관하게 동작) — 재청킹이 계속 도는 이 프로젝트의 GT 유지보수 도구. |

**주장하지 않는 것**

- `crawler/eval.py` / `eval_TF.py` — 문서 단위 판정이라 청크 단위와 다른 축. 폐기가 아니라 **다른 목적**(D1 게이트)으로 유지. 이 축의 정본은 다른 브랜치 것이 나을 수 있음.
- `crawler/data/testset_natural_400.jsonl` — 이 브랜치에서 검수·개선하지 않았음.
- 리랭커 관련(`eval_rerank.py`) — 미채택 상태, 정본 후보 아님.
- `crawler/faq_bf_map.py` — rag.py에서 **미참조**(P0-4에서 배선 제거). 삭제 안 하고 보존만 함, 정본 주장 아님.
- `crawler/p2_parent_expand.py`, `crawler/data/reembed.py` — untracked 실험/유틸, 미채택.
- MOAI 라우터 관련 일체 — 체크포인트 미보유로 검증 불가.

---

## 6. 알려진 결함·캐비앗 (필수 · 빈칸 금지)

| 항목 | 값 | 비고 |
|---|---|---|
| self-referential 문항 비율 | **미확인** | GT #1의 질문은 코퍼스 문서 본문에서 파생된 계열(`origin_question` 필드가 선행 셋에 존재). 정확한 비율은 세지 않았다. `evidence_type='direct'` 418/450은 근거 유형이지 self-referential 여부가 아님 — 혼동 금지. |
| held-out 여부 | **개발 중 노출됨** | §4 행 1의 파라미터(P0-4 채택분)를 **같은 GT로 골랐다.** 아래 참조. |
| 파라미터 튜닝에 사용한 셋 | `crawler/data/gt_natural450_v9_dupfix2.jsonl` (§4 행 1과 **동일 셋**) | **순환.** P0-4의 개별 격리 A/B가 이 셋에서 hit 지표를 보고 채택/기각을 결정했고, 최종 baseline 0.821도 같은 셋에서 냈다. 부록 B-5에 따라 이 수치는 held-out 수치보다 **약한** 근거로 취급되어야 한다. |
| 시드 분산 | **단일 시드** (사실상 결정론) | 랜덤 요소 없음(§3 확인). 단 인덱스 재빌드 시 부동소수 재현성은 미측정. |
| 청크 ID 참조 자산 유무 | **있음** — `gt_natural450_v9_dupfix2.jsonl`(`gt_chunk_ids`/`gt_chunk_id`), `eval_anchor_v3_report.md`(미적중 사례의 gold/top-3 chunk_id), `dupfix_v2_ambiguous.md` | 재청킹 시 dangling 위험 직접 노출. 완화책: `build_gt_dupfix.py` 재실행으로 복구 가능하되, `span_verbatim_ok=false` 20건은 복구 불가. |
| 기타 알려진 문제 | (1) **§4 수치가 미커밋 워킹트리 기준** — HEAD를 체크아웃하면 185청크로 다른 지문. (2) `and` relation 69건을 **ALL 조건**으로 채점 → 전체 hit@k가 표준 정의보다 낮게 나온다. ANY 채점 브랜치와 직접 비교 불가. (3) `eval_anchor_v3.py`의 `--gt` 기본값이 실물 없는 `gt_natural450_v7.jsonl`. (4) `eval_report.md`(행 4~6)는 코퍼스 지문 없음 + `RRF(k=4)` 표기로 현재 파라미터와 불일치 — **무효 처리 권장**. (5) `build_gt_dupfix_v2.py`(임베딩 기반 비-verbatim 중복 탐지)는 old chunk_id로 새 인덱스를 조회해 해당 문항이 **조용히 스킵**되는 버그가 있어 미적용. | |

---

## 7. 충돌 예상 (수합 전 확인용)

| 파일 | 다른 브랜치도 수정했을 가능성 | 비고 |
|---|---|---|
| `crawler/rag.py` | **높음** | 이 브랜치는 anc 골격 + kokopas 파라미터/패싯규칙 + `chunk_embed_text()`(앵커 임베딩) 혼합. FAQ BF map·MOAI router 배선을 **삭제**함 — 그 배선을 유지하는 브랜치와 양립 불가. |
| `crawler/chunk.py` | **높음** | anc 버전(`TABLE_GAP_MAX=12`, 표 흡수)으로 통째 교체. 청크 수가 181로 바뀌므로 **chunk_id 기반 GT 전부에 영향**. |
| `crawler/data/chunks.jsonl` | **높음** | 재청킹 산출물. 지문이 바뀌면 §4 전체 재측정. |
| `crawler/data/gt_natural450_v9_dupfix2.jsonl` | **중간** | 같은 파일명으로 다른 corpus 세대에 매핑된 버전이 존재할 수 있다(이 브랜치 것은 **181청크 재매핑본**, 2026-08-20 15:36). 파일명만 보고 같다고 판단하면 안 됨. |
| `crawler/eval_anchor_v3.py` | **중간** | 청크 단위 + relation ALL 판정. 문서 단위 판정 버전과 양립 불가. |
| `crawler/eval.py` | 낮음 | 이 브랜치에서 미수정. |
| `crawler/faq_bf_map.py` | 낮음 | 신규 추가, 미참조. |

---

## 8. 수합에 넘기는 미결 사항

1. **`and` relation(69건)의 채점 규칙을 ALL로 갈지 ANY로 갈지.** 이 브랜치는 ALL이라
   전체 hit@5가 0.821로 나오지만, ANY로 채점하는 브랜치 수치와 같은 표에 놓을 수 없다.
   수합 시 **하나로 통일하고 전 브랜치 재측정**이 필요하다.
2. **파라미터 튜닝 셋과 평가 셋이 같은 문제(§6)를 어떻게 처리할지.** GT 450건을
   train/val/test로 분할해 재측정할지, 아니면 별도 held-out 셋을 새로 만들지.
   현재 이 브랜치의 0.821은 순환 근거다.
3. **`span_verbatim_ok=false` 20건 + `confidence<0.7` 28건을 GT에서 제외할지, 재검수할지.**
   제외하면 문항 수가 달라져 기존 수치와 비교 불가.
4. **주지표를 hit@k로 할지 MacroRecall@k로 할지.** `eval_anchor_v3.py` 리포트는
   MacroRecall을 주지표로 선언하는데, 다른 브랜치 제출서는 hit@k로 낼 가능성이 높다.
5. **`crawler/data/chunks.jsonl` 미커밋 상태(181청크)를 정본으로 인정할지.**
   현재 HEAD 커밋본은 185청크로 다른 지문이다. 인정한다면 커밋이 선행돼야 하고,
   인정하지 않는다면 §4 행 1·2는 재현 불가 수치가 된다.
