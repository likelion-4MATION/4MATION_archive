---
# ── 기계 판독부 (상황 LLM이 먼저 읽는 곳) · 추측 금지, §확인 명령으로 뽑아 채운다 ──
author: kungean
branch: emb-ko
commit: b810b10
written_at: 2026-08-20
corpus:
  chunks_path: crawler/data/chunks.jsonl
  chunk_count: 181
  file_sha256: cd1fffa4de5e
  embed_model: dragonkue/BGE-m3-ko
  embed_dim: 1024
  index_rebuilt: true
  router_used: fallback   # 체크포인트 없음(router_electra/router_moai 미학습). 키워드 분류기 + 1차 검색결과 업무 역추론(PRF)
params:
  k: 10
  RRF_ALPHA: 0.6
  RRF_K: 5
  BF_MODE: soft
  BF_BOOST: 0.04
  BF_DOC_CAP: 5
  FACET_BOOST: 0.05
  rerank: none
claims:
  - path: crawler/data/gt_natural430_curated.jsonl
    kind: gt
    supersedes: crawler/data/gt_natural430_fresh.jsonl, crawler/data/gt_natural430.jsonl
  - path: crawler/eval_anchor_span_multi.py
    kind: eval
    supersedes: crawler/eval_anchor_v3.py(삭제됨)
  - path: crawler/rag.py (QBF_PRF_TOPN/QBF_PRF_MIN_SHARE)
    kind: param
    supersedes: none
  - path: crawler/chunk.py (TABLE_GAP_MAX)
    kind: param
    supersedes: none
open_questions: 3
---

# 평가 상황 제출 — `emb-ko` (`kungean`)

> **목적** 각 브랜치의 eval 방법과 GT 중 **가장 정확한 버전**을 골라 하나로 합치기 위한 제출서.
> **원칙** — 값은 **실행해서** 채운다(기억·추측 금지) ⟡ 모르는 건 `미측정`으로 남긴다
> ⁚ 수치에는 **항상 코퍼스 질문을 붙인다** — 질문이 다른 수치는 비교 대상이 아니다.

---

## 1. 코퍼스 질문 (필수 · 이것 없으면 §4 수치는 무효)

| 항목 | 값 | 확인 방법 |
|---|---|---|
| `chunks.jsonl` 청크 수 | 181 | `wc -l crawler/data/chunks.jsonl` |
| 파일 sha256 (앞 12자) | `cd1fffa4de5e` | `sha256sum crawler/data/chunks.jsonl` |
| 임베딩 모델 / 차원 | `dragonkue/BGE-m3-ko` / `1024` | `rag.py` `MODEL_NAME` · `EMB_DIM` |
| 인덱스 재생성 여부 | 예 | `data/index/faiss.index`·`chunk_meta.jsonl` mtime이 `chunks.jsonl`과 동일(2026-08-18 17:44), `chunk_meta.jsonl` 181줄로 일치 확인 |
| 라우터 상태 | 폴백(키워드+역추론) | `router_electra/`·`router_moai/`에 학습된 체크포인트(.pt/.bin) 없음. `rag.py`의 `classify_query_bf()`(키워드) + 기권 시 `Searcher._infer_bf_from_pool()`(1차 검색결과 업무 역추론)로 대체 |
| 마지막 재청킹 커밋 | `b810b10` | `git log -1 --format=%h -- crawler/data/chunks.jsonl` — 단, 이 커밋에 chunks.jsonl 자체 변경이 포함돼 있고 이후 워킹트리 재수정 없음 확인 |

> ⚠️ 청크 수가 다른 브랜치끼리는 **hit@k를 직접 비교할 수 없다.** 상황 LLM은 질문이 다르면
> "더 크다/낮다"로 판정하지 않고 **재측정 대상**으로 분류한다.

---

## 2. GT(정답셋) 목록

브랜치에 있는 GT 파일 **전부**. 폐기한 것도 `상태=폐기`로 남긴다 — 다른 사람이
같은 파일명을 정본이라 주장할 수 있기 때문이다.

| # | 파일 경로 | 문항 수 | 판정 필드 | 다중정답 | split | 검색 의미 | 상태 | 부모 관계 |
|---|---|---:|---|---|---|---|---|---|
| 1 | `crawler/data/gt_natural450.jsonl` | 450 | `gt_anchors` / `gt_anchor_span` 단수 폴백 | 혼합(and/or 포함) | 미분리(TEST 원천) | 실제검색 | 원본 | (팀 원본, 무수정) |
| 2 | `crawler/data/gt_natural430_curated.jsonl` | 430 | `gt_anchors` + `gt_anchor_spans`(다중, 청크마다 1개) | and 55 / or 5 / single 370 | test | 실제검색 | **후보(정본 제안)** | `gt_natural450.jsonl` → `filter_anchored.py`(has-anchor) → `curate_anchors_450.py`(근거 직접 채움) |
| 3 | `crawler/data/gt_natural430_fresh.jsonl` | 430 | 원본 앵커 그대로(부족분 미보강) | 혼합 | test | 실제검색 | 폐기(중간산출물) | `gt_natural450.jsonl` → `filter_anchored.py` (재실행하면 언제든 재생성됨) |
| 4 | `crawler/data/gt_natural430.jsonl` | 430 | `gt_anchor_span` 단수 위주 | 혼합 | test | 실제검색 | 폐기(미사용, 커밋 안 됨/untracked) | `gt_natural450.jsonl` (초기 재현 시도, curated 이전 버전) |
| 5 | `crawler/data/gt_natural505.jsonl` | 505 | `gt_anchor_span` | 혼합 | val(answerable 355 + unanswerable 150) | 실제검색 | 원본 | (팀 원본, 무수정) |
| 6 | `crawler/data/gt_natural355.jsonl` | 355 | `gt_anchor_span` | near_dup/duplicate/contained 포함 | val | 실제검색 | **후보(현재 사용중인 VAL)** | `gt_natural505.jsonl` → `make_val_split.py`(answerable==True 필터) |

**판정 필드 값 정의** (해당하는 것 √)

- [√] `gt_anchors`/`gt_anchor_spans` — 정답 근거(텍스트 스팬) 포함 여부로 판정. **재청킹에 강건**
      (chunk_id 일치가 아니라 `normalize(span) ⊂ normalize(chunk.text)` 텍스트 포함관계)
- [ ] `gt_chunk_id` 단독 — 청크 ID 일치로만 판정. 재청킹에 취약(사용 안 함, 폴백으로만 존재)
- [ ] `gt_docs` — 문서 단위 판정. 사용 안 함
- [√] 기타: `--id-fallback` 옵션 — `evidence_type=inferable`(계산·추론형이라 스팬이 구조적으로
      없는 문항)만 gold `chunk_id` 등장 여부로 대체 판정. `gt_natural430_curated.jsonl`은 이
      유형을 애초에 걸러냈으므로(§3.6 근거는 부록 참고) 이 옵션이 실제로 발동할 일은 거의 없다.

**정본 스키마 실물 1줄** (`gt_natural430_curated.jsonl`)

```
['id', 'business_function', 'question', 'answerable', 'evidence_type', 'chunk_relation',
 'gt_chunk_ids', 'gt_chunk_id', 'multi_chunk', 'gt_anchor_span', 'answer_bf', 'cross_domain',
 'span_verbatim_ok', 'confidence', 'reason', 'gt_anchors', 'gt_anchor_spans']
```

**알려진 오라벨 / 미검증 구간**

- `evidence_type=inferable`(계산·추론형) 문항은 `gt_natural430_curated.jsonl`에 원본 앵커가
  있던 것만 포함되고, 없던 것은 `filter_anchored.py`가 애초에 걸러 430 밖이다. 이 유형을
  전부 포함해 채점하려면 `filter_anchored.py`를 거치지 않은 450 전체 GT가 따로 필요하다.
- `gt_chunk_ids`에는 재청킹(215→181)으로 코퍼스에서 사라진 chunk_id가 다수 남아있다(§6 참고).
  판정은 텍스트 포함관계라 무관하지만, `gt_chunk_ids` 필드 자체를 좌표로 쓰는 다른 코드가
  있다면 dangling 참조에 주의해야 한다.

---

## 3. 평가 스크립트 목록

`crawler/eval*.py` 전부. 실행용 일회성 스크립트는 적고 `용도=실험`으로 표시한다.

| # | 파일 | 용도 | 판정 로직 (한 줄) | 의존 GT | 산출 리포트 | 상태 |
|---|---|---|---|---|---|---|
| 1 | `eval_anchor_span_multi.py` | 정본 평가 / 파라미터 설정 / 실행 | `gt_anchor_spans` 각 스팬을 top-10 청크 본문에서 텍스트 포함관계로 검색, and=전부/or·single=하나 | `gt_natural430_curated.jsonl`, `gt_natural355.jsonl` | `crawler/data/eval_gt430_curated_report.md`, `eval_gt355_report.md` | **원본** |
| 2 | `eval_span_tune.py` | 실행(파라미터 스윕, 리포트 없음·콘솔 출력) | 위와 동일 판정을 `RRF_ALPHA`/`BF_BOOST`/`FACET_BOOST`/`BF_DOC_CAP` 축별로 스윕 | `gt_natural430_curated.jsonl` | 없음(콘솔) | 실행 |
| 3 | `eval_prf_bf.py` | 실행(채택된 처방 A/B 재검증) | 위와 동일 판정 + 업무 역추론 topN/임계 스윕 | `gt_natural430_curated.jsonl`, `gt_natural355.jsonl` | 없음(콘솔) | 실행 |
| 4 | `eval_sibling_boost.py` | 실행(기각 실험 재현) | 형제 청크 점수 전파(λ) A/B | 〃 | 없음(콘솔) | 실행(기각됨) |
| 5 | `eval_mmr_rerank.py` | 실행(기각 실험 재현) | MMR 다양성 재랭킹(β) A/B | 〃 | 없음(콘솔) | 실행(기각됨) |
| 6 | `eval_query_decomp.py` | 실행(기각 실험 재현) | 복합질의 분해 후 RRF 재융합 A/B | 〃 | 없음(콘솔) | 실행(기각됨) |
| 7 | `eval.py`, `eval_TF.py`, `eval_cap.py`, `eval_embedinput.py`, `eval_exclude.py`, `eval_facet.py`, `eval_mmr.py`, `eval_pair.py`, `eval_rerank.py`, `eval_rrf_tune.py`, `eval_rrfk.py`, `eval_softboost.py` | 미상 | 이번 브랜치 작업(§표 원자성 청킹/GT 다중스팬/업무 역추론)과 무관한 이전 실험 스크립트 | 미확인 | 미확인 | **미검토**(이 제출서 범위 밖) |

**정본으로 주장하는 스크립트 1개 지정** (필수)

- 파일: `crawler/eval_anchor_span_multi.py`
- 실행 명령: `python eval_anchor_span_multi.py --gt data/gt_natural430_curated.jsonl --mode hybrid_bf --id-fallback --report data/eval_gt430_curated_report.md`
- **결정론 여부**: 예. dense(FAISS `IndexFlatIP`)·sparse(BM25) 검색과 판정 로직 모두 시드가
  없는 결정적 계산이라, 같은 코퍼스·같은 GT·같은 파라미터면 재실행 시 소수점까지 동일한
  수치가 나온다(이번 세션에서 동일 조건 재실행으로 실측 확인).

---

## 4. 측정 결과 (실행해서 채운 것만)

**한 행 = 한 번의 실행.** 질문·파라미터가 다르면 다른 행이다. 재현 명령을 반드시 적는다.

| # | GT | 스크립트 | mode | k | hit@1 | hit@3 | hit@5 | MRR | 코퍼스 질문 | 측정일 | 재현 명령 |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|
| 1 | `gt_natural430_curated.jsonl` | `eval_anchor_span_multi.py` | `hybrid_bf` | 10 | 0.449 | 0.760 | 0.877 | 0.622 | 181청크/`cd1fffa4de5e` | 2026-08-20 | `python eval_anchor_span_multi.py --gt data/gt_natural430_curated.jsonl --mode hybrid_bf --id-fallback --report data/eval_gt430_curated_report.md` |
| 2 | `gt_natural355.jsonl` | `eval_anchor_span_multi.py` | `hybrid_bf` | 10 | 0.493 | 0.761 | 0.839 | 0.637 | 181청크/`cd1fffa4de5e` | 2026-08-20 | `python eval_anchor_span_multi.py --gt data/gt_natural355.jsonl --mode hybrid_bf --id-fallback --report data/eval_gt355_report.md` |

relation별(#1, TEST 430) — 참고용 세부치

| relation | 문항수 | hit@5 | MRR |
|---|---:|---:|---:|
| single | 370 | 0.895 | 0.641 |
| and | 55 | 0.745 | 0.487 |
| or | 5 | 1.000 | 0.707 |

- 미측정 칸은 **빈칸이 아니라 `미측정`**으로 적는다. 빈칸은 0으로 읽힐 수 있다. (이 제출서는
  §4 표에 해당 사항 없음 — 두 행 모두 완주 측정)
- 지표 정의가 표준과 다르면 여기 적는다: hit@5는 `and` relation의 경우 필요한 스팬 전부가
  top-5 안에서 동시에 발견돼야 적중(ALL 판정) — 하나만 맞아도 적중인 or/single과 다르다.

---

## 5. 이 브랜치가 정본이라 주장하는 것 (claim)

상황이 실제 입력. **항목마다 근거 한 줄**을 붙인다. 근거 없는 claim은 상황에서 기각한다.

| # | 대상 파일 | 종류 | 대체 대상 | 근거 (한 줄) |
|---|---|---|---|---|
| 1 | `crawler/data/gt_natural430_curated.jsonl` | GT | `gt_natural430_fresh.jsonl`, `gt_natural430.jsonl` | and/or 문항의 gold 청크 40개 원문을 직접 대조해 근거 문장을 채웠고, 채운 스팬 전부 (a)출처 원문 (b)현재 181청크 코퍼스 verbatim 이중 검증 통과(커버리지 100%) |
| 2 | `crawler/eval_anchor_span_multi.py` | eval | `eval_anchor_v3.py`(삭제됨, chunk_id 완전일치 판정) | 텍스트 포함관계 판정이라 재청킹으로 청크 경계가 바뀌어도 채점이 살아남는다(구 판정 방식은 필드명 버그로 `and`의 ALL 판정이 한 번도 작동하지 않았던 사고 발견·수정 이력 있음) |
| 3 | `crawler/rag.py`(`QBF_PRF_TOPN`/`QBF_PRF_MIN_SHARE`) | param | 없음(신규) | 키워드 분류기 기권 구간(사전에 없는 어휘)을 1차 검색결과 업무 역추론으로 메움. TEST `.872→.877`·VAL `.839→.842` 두 셋 모두 개선 확인 후 채택 |
| 4 | `crawler/chunk.py`(`TABLE_GAP_MAX=12`) | param | 없음(신규) | 표 셀 안 `<br>` 다항목이 만드는 비-파이프 줄을 흡수해 표 파편화 해소. 청크 215→181, TEST·VAL `single` 지표 둘 다 상승 |

**주장하지 않는 것** (다른 사람이 버전을 얹는 걸 막는다고 보는 항목)

- `eval_prf_bf.py`/`eval_sibling_boost.py`/`eval_mmr_rerank.py`/`eval_query_decomp.py` — 미채택
  실험(3개는 기각) 재현용 하네스일 뿐, 정본 GT/eval 후보 아님.
- 질의 분류기 자체(라우터 학습 모델) — 체크포인트 미보유. 오라클 상한 측정상 `+0.011`
  여지가 있다는 사실만 기록하고, 실제 학습·교체는 이 브랜치가 하지 않았다.

---

## 6. 알려진 결함·캐비어트 (필수 · 빈칸 금지)

동그라미표향을 숨기면 상황이 잘못된 정본을 고른다. **모르면 `미확인`이라고 적는다.**

| 항목 | 값 | 비고 |
|---|---|---|
| self-referential 문항 비율 | 미측정 | 질문 문자열이 정답 청크 본문에서 그대로 뽑혔는가 — 이번 세션에서 체크 안 함 |
| held-out 여부 | **held-out 아님, 개발 중 노출됨** | §4의 두 GT(`gt_natural430_curated.jsonl`, `gt_natural355.jsonl`)를 파라미터 재튜닝(`eval_span_tune.py`)과 처방 채택(`eval_prf_bf.py` 등)에 **직접** 사용했다. A/B 판정 자체는 "두 셋 모두 개선"이라는 보수적 규율로 했지만, 별도의 held-out 셋은 없다 |
| 파라미터 튜닝에 사용한 셋 | `gt_natural430_curated.jsonl`(TEST), `gt_natural355.jsonl`(VAL) | 위와 같은 셋 — §4 결과가 이미 튜닝에 쓰인 값 위에서 측정된 것 |
| 실행 분산 | 단일 실행 | 검색이 결정론적(시드 없음)이라 반복 실행해도 동일 수치. 평균±표준편차 개념 자체가 해당 없음 |
| 청크 ID 참조 잔존 여부 | **있음(의도됨)** | `gt_chunk_ids` 필드에 재청킹(215→181)으로 사라진 chunk_id가 다수 남아있다. 판정은 `gt_anchor_spans` 텍스트로만 하므로 무해하지만, `gt_chunk_ids`를 좌표로 직접 쓰는 코드가 있다면 dangling 상태다 |
| 기타 알려진 문제 | `QBF_PRF_TOPN` 도입 후 VAL `hit@1`이 `.493→.482`로 소폭 하락 | `hit@5`를 목표 지표로 채택했으나, top-1만 노출하는 UI라면 재검토 필요(끄려면 `QBF_PRF_TOPN=None`) |
| 기타 알려진 문제 2 | `_relation_mode()`가 `and` 외 모든 라벨을 조용히 ANY로 처리 | 현재 라벨(`single`/`or`/`near_dup`/`duplicate`/`contained`)엔 우연히 맞지만, 새 라벨이 들어오면 경고 없이 관대하게 채점될 수 있음(미조치) |

---

## 7. 충돌 예상 (상황 전 확인용)

| 파일 | 다른 브랜치도 손댔을 가능성 | 비고 |
|---|---|---|
| `crawler/eval_anchor_span_multi.py` | 높음 | 판정 프레임 자체를 chunk_id 완전일치에서 텍스트 포함관계로 바꿨다 — 다른 브랜치가 chunk_id 기준 판정기를 여전히 쓰고 있다면 병합이 아니라 **택일**이 필요하다 |
| `crawler/rag.py` | 중간 | `QBF_PRF_TOPN`/`QBF_PRF_MIN_SHARE` 신규 상수·`Searcher._infer_bf_from_pool()` 추가. 다른 브랜치가 같은 함수(`search()`의 `hybrid_bf` 분기)를 건드렸다면 충돌 가능 |
| `crawler/chunk.py` | 낮음 | `TABLE_GAP_MAX` 단일 상수 추가라 병합 자체는 쉽다. 다만 값이 다른 브랜치와 다르면 청크 수·`chunks.jsonl` sha256이 달라져 §1 질문이 안 맞게 된다 |

---

## 8. 상황이 대기할 미결 사항

내가 결정할 수 없는 것만. 번호를 붙여 상황 LLM이 인용할 수 있게 한다.

1. 재청킹으로 사라진 gold `chunk_id`를 **되살릴지(현재, 엄격) vs 조건에서 제외할지(느슨)** —
   팀 표준을 정해야 한다. 실측 차이는 작다(TEST 430 기준 되살림 0.872 vs 제외 0.874, 초기
   자동 채움 버전 기준).
2. 질의 분류기를 키워드+역추론 폴백으로 계속 둘지, 학습 모델(`router_electra`/`router_moai`)로
   교체할지 — 오라클 상한 실측은 `+0.011`(현재 0.877 → 완벽 분류 시 0.888)뿐이라 투자 대비
   이득이 작을 수 있다.
3. §6에서 밝힌 대로 파라미터 튜닝에 held-out이 아닌 TEST/VAL 자체를 썼다 — 별도 held-out
   셋을 새로 만들지, 지금 수치를 "두 셋 모두 개선"이라는 보수적 규율로 계속 신뢰할지 판단이
   필요하다.

---

## 부록 A. 확인 명령 모음 (그대로 복사해서 값 채우기)

```bash
# 메타
git rev-parse --abbrev-ref HEAD && git rev-parse --short HEAD

# 코퍼스 질문
wc -l crawler/data/chunks.jsonl
sha256sum crawler/data/chunks.jsonl | cut -c1-12
git log -1 --format=%h -- crawler/data/chunks.jsonl
grep -nE "MODEL_NAME|EMB_DIM" crawler/rag.py

# 파라미터 설정 값
grep -nE "^(RRF_ALPHA|RRF_K|BF_BOOST|BF_MODE|BF_DOC_CAP|FACET_BOOST|QBF_PRF)" crawler/rag.py

# GT 목록·문항 수·키
ls crawler/data/*.jsonl
wc -l crawler/data/gt_natural430_curated.jsonl
head -1 crawler/data/gt_natural430_curated.jsonl | python3 -c "import json,sys;print(list(json.load(sys.stdin).keys()))"

# 평가 스크립트 목록
ls crawler/eval*.py

# 평가 실행(정본)
cd crawler
python eval_anchor_span_multi.py --gt data/gt_natural430_curated.jsonl --mode hybrid_bf --id-fallback --report data/eval_gt430_curated_report.md
python eval_anchor_span_multi.py --gt data/gt_natural355.jsonl --mode hybrid_bf --id-fallback --report data/eval_gt355_report.md
```

## 부록 B. 상황 LLM이 지켜야 할 판정 규칙 (제출자가 임의로 못 바꿀 것)

1. **질문 우선.** `corpus.chunk_count` 또는 `file_sha256`이 다른 제출서와 §4 수치를
   서로 비교하지 않는다. 비교하려면 동일 질문에서 **재측정**을 요구한다.
2. **판정 방식이 다르면 다른 축.** `gt_chunk_id` 판정 수치와 `gt_anchors` 판정 수치를
   같은 축에 두고 이어붙이지 않는다.
3. **근거 없는 claim 기각.** §5의 근거 한 줄이 없으면 후보에서 제외한다.
4. **no-numbers-no-merge.** §4가 `미측정`인 claim을 정본으로 채택하지 않는다.
5. **held-out 아닌 수치는 우대하지 않는다.** 파라미터 튜닝으로 낸 수치는 별도 held-out 수치보다
   **약한** 근거다 — 이 제출서 §6에 명시된 대로다.
6. **재청킹 내구성을 가산한다.** 청크 ID 판정보다 앵커텍스트 판정을 선호한다 — 코퍼스가
   계속 재생성되는 프로젝트이기 때문이다.
7. 판정 결과는 **파일 단위로** 낸다(브랜치 단위 승자 선정 금지). GT는 A 브랜치,
   eval 스크립트는 B 브랜치가 정본일 수 있다.
