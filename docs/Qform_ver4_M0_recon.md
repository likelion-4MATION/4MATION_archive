# Qform_ver4 · M0 — 평가셋 스키마 정찰 · 기준선 잠금

> **브랜치** `Qform_ver4` · **실행** 2026-08-18 · **성격** 읽기 전용 정찰 (수정 파일 0)
> **명세** `docs/Qform_ver4_task_assignment.md` M0 절 · **규칙** `CLAUDE.md`
> **실행자** CC — 측정만 한다. 확정·판정은 §7-3에 모아 현욱에게 올린다.

읽는 순서 — §1 잠금값 → §2 `testset/` 전수 → §3 발동률 후보 → §4 슬롯 원천 →
§5 기존 자산 → §6 검증 7종 → §7 보고(CLAUDE.md §7 형식).

---

## §1. 잠금 정보 (A0-3)

### 1-1. 리비전

| 항목 | 값 | 취득 방법 |
|---|---|---|
| `.git/HEAD` 내용 | `ref: refs/heads/Qform_ver4` | 파일 읽기 |
| **HEAD SHA** | `d2a7c2053765a00e89b9c6722e6bbc12da3d49d6` | `.git/refs/heads/Qform_ver4` 파일 읽기 |
| 브랜치 | `Qform_ver4` | 위 두 파일로 확정 |
| 코퍼스 | `crawler/data/chunks.jsonl` · 215청크 / 38문서 | `verify_combos.py` 실측 |
| **코퍼스 sha256** | `6af9517ba0da80db1296b9c7f202b534ae23cd17d8e7746614f7d89d869bd381` | `shasum -a 256` |

**git 명령은 하나도 실행하지 않았다**(CLAUDE.md §0-1). `status`·`diff`·`log` 포함. 위 두 값은 `.git/` 하위 파일을 텍스트로 읽어 얻었다.

### 1-2. 평가셋 후보 파일 sha256

| 파일 | 행 | 바이트 | sha256 |
|---|---:|---:|---|
| `testset/gt_natural450.jsonl` | 450 | 385,081 | `d92fbc5135054215c2fc74c361bb1b0529caa0352388402aeeccdb7a284bbeda` |
| `testset/gt_natural505.jsonl` | 505 | 878,780 | `750c56aed84fccac91276963dc12a2499ac7fbeaa95b33054a9a212913d7ac30` |
| `crawler/data/testset_natural_450.jsonl` | 450 | 162,444 | `9df05aa1f6c6c3dcb620724974ba8d7845fa3100b9607d9359436bf890f055c5` |

부속 잠금값(조합/첨부 원천):

| 파일 | sha256 |
|---|---|
| `crawler/data/qform_combos_msdr.csv` | `0115fe35b0477484719d349b371c30f9ef3f1a027755a81d53f1984efa9ea7a2` |
| `crawler/data/doc_attachments.json` | `183e460f4b5febf2bb9cd5bef7c08a15110f6fef3a008cad46f7bd584726061c` |
| `crawler/yesom_분기분석/attachment_tagging_schema.md` | `69104e5bdf8d13b68ff617f9e48f777357cce0850c5379c6242c6a3d217b1ed8` |

### 1-3. 코퍼스 동일성 교차 확인 — 파일이 스스로 밝히는 것

| 파일 | 코퍼스 지문 필드 | 값 | chunks.jsonl 실측과 |
|---|---|---|---|
| `testset/gt_natural505.jsonl` | `_audit.corpus_sha256` (505행 전건, 단일값) | `6af9517b…9bd381` | **일치** ✅ |
| `testset/gt_natural450.jsonl` | **없음** | — | 파일만으로는 확인 불가 |
| `crawler/data/testset_natural_450.jsonl` | **없음** | — | 파일만으로는 확인 불가 |

읽는 법 — 505만 자기가 어느 코퍼스에서 생성됐는지 파일 안에 적고 있다. 450 두 파일은 K12가 요구하는 `sha256 병기`를 **외부(이 문서)에서 걸어 주는 수밖에 없다.**

### 1-4. 측정 환경

| | |
|---|---|
| Python | 3.11.9 |
| 네트워크·LLM 콜 | **0** (전 스크립트가 자기검사 모드) |
| 수정한 파일 | **0** (A0-6) |

`mtime`은 잠금 근거로 쓰지 않는다 — iCloud 동기화가 다수 파일의 mtime을 `2026-08-18 11:22:06`으로 일괄 갱신해 놓았고 내용 변경과 무관하다.

---

## §2. `testset/` 전수 조사 (A0-1)

### 2-1. 파일 목록 — 2개 (하위 디렉토리 없음)

| # | 경로 | 확장자 | 행 | 바이트 | 끝 개행 | 빈 줄 | sha256(앞16) |
|---|---|---|---:|---:|---|---:|---|
| 1 | `testset/gt_natural450.jsonl` | `.jsonl` | 450 | 385,081 | 있음 | 0 | `d92fbc5135054215` |
| 2 | `testset/gt_natural505.jsonl` | `.jsonl` | 505 | 878,780 | 있음 | 0 | `750c56aed84fccac` |

### 2-2. 필드 스키마

#### (1) `testset/gt_natural450.jsonl` — 450행 · 15키

| 키 | 존재 | 타입(건수) | null | null% | 고유값 |
|---|---:|---|---:|---:|---:|
| `id` | 450 | str:450 | 0 | 0.0% | 450 |
| `business_function` | 450 | str:450 | 0 | 0.0% | 6 |
| `question` | 450 | str:450 | 0 | 0.0% | 450 |
| `answerable` | 450 | bool:450 | 0 | 0.0% | 2 |
| `evidence_type` | 450 | str:450 | 0 | 0.0% | 3 |
| `chunk_relation` | 450 | str:450 | 0 | 0.0% | 3 |
| `gt_chunk_ids` | 450 | list:450 | 0 | 0.0% | 168 |
| `gt_chunk_id` | 450 | str:448, **null:2** | 2 | 0.4% | 125 |
| `multi_chunk` | 450 | bool:450 | 0 | 0.0% | 2 |
| `gt_anchor_span` | 450 | str:430, **null:20** | 20 | 4.4% | 307 |
| `answer_bf` | 450 | str:448, **null:2** | 2 | 0.4% | 8 |
| `cross_domain` | 450 | bool:450 | 0 | 0.0% | 2 |
| `span_verbatim_ok` | 450 | bool:450 | 0 | 0.0% | 2 |
| `confidence` | 450 | float:450 | 0 | 0.0% | 26 |
| `reason` | 450 | str:450 | 0 | 0.0% | 441 |

**`gt_docs` 필드가 없다.** 정답 라벨이 청크 단위(`gt_chunk_ids`)로만 있다.

#### (2) `testset/gt_natural505.jsonl` — 505행 · 16키 + 조건부 1키

| 키 | 존재 | 타입(건수) | null | null% | 고유값 |
|---|---:|---|---:|---:|---:|
| `id` | 505 | str:505 | 0 | 0.0% | 505 |
| `question` | 505 | str:505 | 0 | 0.0% | 505 |
| `gt_chunk_ids` | 505 | list:505 | 0 | 0.0% | 199 |
| `gt_chunk_id` | 505 | str:355, **null:150** | 150 | 29.7% | 192 |
| `gt_anchor_span` | 505 | str:355, **null:150** | 150 | 29.7% | 349 |
| `answerable` | 505 | bool:505 | 0 | 0.0% | 2 |
| `evidence_type` | 505 | str:505 | 0 | 0.0% | 2 |
| `business_function` | 505 | str:355, **null:150** | 150 | 29.7% | 8 |
| `confidence` | 505 | **null:505** | 505 | **100.0%** | 1 |
| `reason` | 505 | str:355, null:150 | 150 | 29.7% | 327 |
| `multi_chunk` | 505 | bool:505 (전건 `False`) | 0 | 0.0% | **1** |
| `chunk_relation` | 505 | **null:456**, str:49 | 456 | 90.3% | 4 |
| `cross_domain` | 505 | bool:505 (전건 `False`) | 0 | 0.0% | **1** |
| `answer_bf` | 505 | str:355, null:150 | 150 | 29.7% | 8 |
| `span_verbatim_ok` | 505 | bool:505 | 0 | 0.0% | 2 |
| `_audit` | 505 | dict:505 | 0 | 0.0% | 358 |
| `negative_type` | **150** (부재 355) | str:150 | — | (부재 70.3%) | 5 |

`_audit` 내부 키 (505행 기준 존재 건수):

| 키 | 존재 | 키 | 존재 | 키 | 존재 |
|---|---:|---|---:|---|---:|
| `corpus_sha256` | 505 | `anchor_type` | 355 | `char_range` | 355 |
| `version` | 505 | `table_derived` | 355 | `window` | 355 |
| `quality_tier` | 505 | `case_numeric_suspect` | 355 | `unit` | 355 |
| `anchor_id` | 505 | `review_reasons` | 355 | `cand_idx` | 355 |
| `anchor_rationale` | 505 | `in_chunk_occ` | 355 | `reverse_jaccard` | 355 |
| `question_origin` | 505 | `uniqueness` | 355 | `nat_attempts` | 355 |
| `lcs_to_chunk` | 505 | `corpus_hit_chunks` | 355 | `raw_question` | 355 |
| `reverse_verdict` | 505 | `equiv_class` | 355 | `r_pass_classes` | **150** |
| `gen_model` | 505 | `equiv_members` | 355 | `postfilter` | **55** |
| `flags` | 505 | `supersets` | 355 | `recovered_round` | **11** |
| `review_required` | 505 | `span_len_norm` | 355 | | |
| `split` | 505 | `line_range` | 355 | | |

### 2-3. 값 분포

#### `testset/gt_natural450.jsonl`

| 필드 | 분포 |
|---|---|
| `business_function` | 예금자보호제도 84 · **착오송금 반환 신청 84** · 채무조정 안내 78 · 고객 미수령금 신청 77 · 예금보험금 안내 65 · 은닉재산 신고 62 |
| `answer_bf` | 예금보험금 안내 91 · 예금자보호제도 84 · 착오송금 반환 신청 84 · 채무조정 안내 78 · 은닉재산 신고 62 · 고객 미수령금 신청 47 · 공통 2 · null 2 |
| `evidence_type` | direct 418 · inferable 30 · none 2 |
| `chunk_relation` | single 376 · and 69 · or 5 |
| `answerable` | True 448 · False 2 |
| `multi_chunk` | False 376 · True 74 |
| `cross_domain` | False 421 · True 29 |
| `span_verbatim_ok` | True 430 · False 20 |

`business_function` ≠ `answer_bf`인 행이 존재한다(예: 미수령금 77 → 47, 예금보험금 65 → 91). 질의가 걸린 업무와 답이 있는 업무를 따로 라벨링한 셋이다.

#### `testset/gt_natural505.jsonl`

| 필드 | 분포 |
|---|---|
| `business_function` | **null 150** · 예금보험금 안내 91 · 채무조정 안내 78 · **착오송금 반환 신청 77** · 예금자보호제도 60 · 은닉재산 신고 34 · 고객 미수령금 신청 12 · 공통 3 |
| `answer_bf` | `business_function`과 **전건 동일** |
| `evidence_type` | direct 355 · none 150 |
| `answerable` | True 355 · False 150 |
| `chunk_relation` | null 456 · near_dup 35 · duplicate 12 · contained 2 |
| `negative_type` (150행) | false_premise 40 · not_in_corpus 40 · out_of_scope 40 · temporal 30 |
| `_audit.version` | v9-anchor-1 355 · v9-neg-1 150 |
| `_audit.split` | test 353 · validation 152 |
| `_audit.question_origin` | generated 505 (전건) |
| `_audit.review_required` | False 400 · **True 105** |
| `_audit.postfilter.action` | (필드 부재) 450 · regenerated 22 · flag 22 · regen_failed 11 |

**구조가 450과 다르다.** 505 = 앵커 기반 정답 355 + **네거티브 150**. 네거티브는 `business_function`이 `null`이고 `answerable=False`다.

### 2-4. 참조 정합성 (코퍼스 대조)

| 파일 | 참조 필드 | 참조 건수 | 미실재 | 영향 행 |
|---|---|---:|---:|---:|
| `testset/gt_natural450.jsonl` | `gt_chunk_ids` | 555 | **0** | 0 |
| `testset/gt_natural505.jsonl` | `gt_chunk_ids` | 405 | **0** | 0 |
| `crawler/data/testset_natural_450.jsonl` | `gt_docs` | 612 | **0** | 0 |

세 파일 모두 현 코퍼스(215청크 / 38문서)에 대해 **dangling 0**이다.

### 2-5. 샘플 3행 — 원문 그대로 (축약 없음)

#### `testset/gt_natural450.jsonl`

```json
{"id": "nat450-0001", "business_function": "예금자보호제도", "question": "예금자 보호 한도는 얼마인가요?", "answerable": true, "evidence_type": "direct", "chunk_relation": "single", "gt_chunk_ids": ["kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00"], "gt_chunk_id": "kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn#00", "multi_chunk": false, "gt_anchor_span": "원금과 소정이자를 합하여 1인당 1억원까지만 보호되며 초과금액은 보호되지 않습니다.", "answer_bf": "예금자보호제도", "cross_domain": false, "span_verbatim_ok": true, "confidence": 0.97, "reason": "보호한도 페이지가 1인당 1억원 한도를 명시적으로 진술함."}
{"id": "nat450-0002", "business_function": "예금보험금 안내", "question": "예금보험금은 어떻게 신청하나요?", "answerable": true, "evidence_type": "direct", "chunk_relation": "single", "gt_chunk_ids": ["kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn#00"], "gt_chunk_id": "kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn#00", "multi_chunk": false, "gt_anchor_span": "지급대행기관 방문신청 시\n홈페이지, 우편물 등을 통해 해당 금융회사에 대한 예금보험금 지급대행기관을 확인 후 이용하기 편리한 곳에 직접 방문하여 신청하면, 통상 익영업일내에 예금보험금이 입금 완료됨", "answer_bf": "예금보험금 안내", "cross_domain": false, "span_verbatim_ok": true, "confidence": 0.93, "reason": "신청절차 페이지가 방문/인터넷 신청 방법을 직접 설명."}
{"id": "nat450-0003", "business_function": "고객 미수령금 신청", "question": "고객 미수령금은 어떻게 조회하고 신청하나요?", "answerable": true, "evidence_type": "direct", "chunk_relation": "single", "gt_chunk_ids": ["kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn#01"], "gt_chunk_id": "kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn#01", "multi_chunk": false, "gt_anchor_span": "(온라인) 금융안심포털에서 미수령금통합신청\n여러분이 현재 받으실 미수령금이 있는지 금융안심포털에서 통합 확인 및 통합신청이 가능합니다.\n금융안심포털은 모바일에서도 가능합니다.\n(오프라인) 지급대행점 직접 방문\n예금보험공사는 미수령금 종류별 · 부실금융회사별로 독립되어 있던 지급대행점 운영 체계를 개선하여 미수령금 종류별 · 부실금융회사별 구분없이 '16.10월부터 전국 지급대행점 어디에서든 미수령금을 통합신청할 수 있도록 하였습니다.", "answer_bf": "고객 미수령금 신청", "cross_domain": false, "span_verbatim_ok": true, "confidence": 0.92, "reason": "온라인(금융안심포털) 및 오프라인(지급대행점) 조회·신청 방법을 직접 설명."}
```

#### `testset/gt_natural505.jsonl`

```json
{"id": "kdic-fins-cm-bbs-selectFaqCncmPrptDclr#00#a1", "question": "숨긴 재산 신고 관련 자세한 내용은 어디서 보나요?", "gt_chunk_ids": ["kdic-fins-cm-bbs-selectFaqCncmPrptDclr#00", "kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn#11"], "gt_chunk_id": "kdic-fins-cm-bbs-selectFaqCncmPrptDclr#00", "gt_anchor_span": "기타 자세한 사항은 예금보험공사 홈페이지(www.kdic.or.kr)내의 『금융부실관련자 은닉재산 신고센터』창이나 상담전화(1588-0037, 02-758-0102∼4)를 이용하시기 바랍니다.", "answerable": true, "evidence_type": "direct", "business_function": "은닉재산 신고", "confidence": null, "reason": "예금보험공사 홈페이지(www.kdic.or.kr)내의 『금융부실관련자 은닉재산 신고센터』창이나 상담전화(1588-0037, 02-758-0102∼4)", "multi_chunk": false, "chunk_relation": "duplicate", "cross_domain": false, "answer_bf": "은닉재산 신고", "span_verbatim_ok": true, "_audit": {"corpus_sha256": "6af9517ba0da80db1296b9c7f202b534ae23cd17d8e7746614f7d89d869bd381", "version": "v9-anchor-1", "quality_tier": null, "anchor_id": "kdic-fins-cm-bbs-selectFaqCncmPrptDclr#00#a1", "anchor_type": "절차·순서", "anchor_rationale": "추가 정보 확인 방법을 홈페이지 창과 상담전화로 안내하는 자기완결적 사실 진술", "question_origin": "generated", "lcs_to_chunk": 4, "reverse_verdict": {"kdic-fins-cm-bbs-selectFaqCncmPrptDclr#00": "ANSWERS"}, "gen_model": "solar-pro4", "table_derived": false, "case_numeric_suspect": false, "flags": ["chunk_relation:duplicate"], "review_required": false, "review_reasons": [], "in_chunk_occ": 1, "uniqueness": "OK_UNIQUE_EQUIV", "corpus_hit_chunks": ["kdic-fins-cm-bbs-selectFaqCncmPrptDclr#00", "kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn#11"], "equiv_class": "kdic-fins-cm-bbs-selectFaqCncmPrptDclr#00", "equiv_members": ["kdic-fins-cm-bbs-selectFaqCncmPrptDclr#00", "kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn#11"], "supersets": [], "span_len_norm": 96, "line_range": [3, 3], "char_range": [35, 142], "window": 1, "unit": "line", "cand_idx": 2, "reverse_jaccard": 1.0, "nat_attempts": 1, "raw_question": "금융부실관련자 은닉재산 신고 관련 자세한 사항은 어디에서 확인하나요?", "postfilter": {"rule": "topic", "action": "regenerated", "prev_question": "더 궁금한 건 어디서 보면 되나요?"}, "split": "test"}}
{"id": "kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01#a1", "question": "돌려받는 돈이 5억 안 될 때 포상금은 몇 퍼센트인가요?", "gt_chunk_ids": ["kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01"], "gt_chunk_id": "kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01", "gt_anchor_span": "포상금 지급 기준\n회수기여금액 | 포상금\n5억원 이하 | 회수기여금액의 20%", "answerable": true, "evidence_type": "direct", "business_function": "은닉재산 신고", "confidence": null, "reason": "회수기여금액의 20%", "multi_chunk": false, "chunk_relation": null, "cross_domain": false, "answer_bf": "은닉재산 신고", "span_verbatim_ok": true, "_audit": {"corpus_sha256": "6af9517ba0da80db1296b9c7f202b534ae23cd17d8e7746614f7d89d869bd381", "version": "v9-anchor-1", "quality_tier": null, "anchor_id": "kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01#a1", "anchor_type": "수치·한도", "anchor_rationale": "포상금 지급 기준이라는 머리글과 첫 번째 구간 조건을 함께 제시하여 자기완결된 사실 진술", "question_origin": "generated", "lcs_to_chunk": 4, "reverse_verdict": {"kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01": "ANSWERS"}, "gen_model": "solar-pro4", "table_derived": true, "case_numeric_suspect": false, "flags": ["table_derived"], "review_required": true, "review_reasons": ["table_derived"], "in_chunk_occ": 1, "uniqueness": "OK_UNIQUE", "corpus_hit_chunks": ["kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01"], "equiv_class": "kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01", "equiv_members": ["kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01"], "supersets": [], "span_len_norm": 33, "line_range": [3, 5], "char_range": [28, 73], "window": 3, "unit": "line", "cand_idx": 28, "reverse_jaccard": 0.538, "nat_attempts": 1, "raw_question": "회수기여금액이 5억원 이하일 때 포상금 비율은 얼마인가요?", "split": "test"}}
{"id": "kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01#a2", "question": "포상금은 어느 기관에서 주나요?", "gt_chunk_ids": ["kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01"], "gt_chunk_id": "kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01", "gt_anchor_span": "- 포상금은 부실관련자의 은닉재산 신고를 통해 실질적으로 채권을 회수한 채권금융회사에서 지급합니다.", "answerable": true, "evidence_type": "direct", "business_function": "은닉재산 신고", "confidence": null, "reason": "부실관련자의 은닉재산 신고를 통해 실질적으로 채권을 회수한 채권금융회사", "multi_chunk": false, "chunk_relation": null, "cross_domain": false, "answer_bf": "은닉재산 신고", "span_verbatim_ok": true, "_audit": {"corpus_sha256": "6af9517ba0da80db1296b9c7f202b534ae23cd17d8e7746614f7d89d869bd381", "version": "v9-anchor-1", "quality_tier": null, "anchor_id": "kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01#a2", "anchor_type": "대상·자격", "anchor_rationale": "포상금 지급 주체에 관한 자기완결적 사실 진술", "question_origin": "generated", "lcs_to_chunk": 4, "reverse_verdict": {"kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01": "ANSWERS"}, "gen_model": "solar-pro4", "table_derived": true, "case_numeric_suspect": false, "flags": ["table_derived"], "review_required": true, "review_reasons": ["table_derived"], "in_chunk_occ": 1, "uniqueness": "OK_UNIQUE", "corpus_hit_chunks": ["kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01"], "equiv_class": "kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01", "equiv_members": ["kdic-fins-cm-bbs-selectFaqCncmPrptDclr#01"], "supersets": [], "span_len_norm": 45, "line_range": [11, 11], "char_range": [306, 361], "window": 1, "unit": "line", "cand_idx": 3, "reverse_jaccard": 0.977, "nat_attempts": 1, "raw_question": "포상금은 어느 기관에서 지급하나요?", "split": "test"}}
```

#### (참고) `crawler/data/testset_natural_450.jsonl` — §3에서 후보로 올라오므로 같이 싣는다

```json
{"question": "예금자 보호 한도는 얼마인가요?", "gt_docs": ["kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn", "kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn"], "business_function": "예금자보호제도", "source": "representative", "representative": true, "origin_question": "예금자 보호 한도는 얼마인가요?"}
{"question": "예금보험금은 어떻게 신청하나요?", "gt_docs": ["kdic-www-sp-dpstrprot-DpsmIbamtAplyProc-selectScrn", "kdic-www-sp-dpstrprot-DpsmIbamtAplyPossDcmnt-selectScrn", "kdic-www-sp-dpstrprot-DpsmIbamtExpln-selectScrn"], "business_function": "예금보험금 안내", "source": "representative", "representative": true, "origin_question": "예금보험금은 어떻게 신청하나요?"}
{"question": "고객 미수령금은 어떻게 조회하고 신청하나요?", "gt_docs": ["kdic-www-sp-dpstrprot-ProtSystNramtInqAplyNramtGudn-selectScrn", "kdic-fins-ua-aplygudn-NramtItgrAplyItrdMthdGudn-selectScrn"], "business_function": "고객 미수령금 신청", "source": "representative", "representative": true, "origin_question": "고객 미수령금은 어떻게 조회하고 신청하나요?"}
```

---

## §3. 되묻기 발동률 재측정 대상 후보 (A0-2)

### 3-1. 탐색 범위 — `testset/` 밖까지 훑었다

명세는 `testset/` 전수 조사를 지시했으나, **후보 선정만은 레포 전체를 훑었다.** 이유는 §7-2 #1에 적었다.
`.git/` 제외 전 `.json`·`.jsonl` 108개 중 **행수 450인 파일은 2개**다.

| 경로 | 행 | 후보? |
|---|---:|---|
| `testset/gt_natural450.jsonl` | 450 | ✅ |
| `crawler/data/testset_natural_450.jsonl` | 450 | ✅ |
| `testset/gt_natural505.jsonl` | 505 | 참고(행수 불일치) |
| `crawler/data/testset_natural_400.jsonl` | 400 | ✕ |
| `crawler/data/testset_natural_300{,_v2,_v3}.jsonl` | 300 | ✕ |
| 그 외 (`testset_merged` 150 · `testset.jsonl` 52 · `testset_yesom` 98 …) | ≠450 | ✕ |

### 3-2. 명세가 준 판단 근거 3축 대조

| 파일 | 행수 450 | `business_function` 계열 | 착오송금 84건 내외 | 현행 코드가 읽는가 |
|---|---|---|---|---|
| `crawler/data/testset_natural_450.jsonl` | ✅ 450 | ✅ `business_function` | ✅ **84** | ✅ `qform_state.py:222`·`qform_extract.py:291`·`qform_ask.py:321`·`qform_trace.py:341`·`crawler/eval_TF.py:27` |
| `testset/gt_natural450.jsonl` | ✅ 450 | ✅ `business_function` + `answer_bf` | ✅ **84** | ❌ 참조 코드 0곳 |
| `testset/gt_natural505.jsonl` | ❌ 505 | △ `business_function` (150행 null) | ❌ **77** | ❌ 참조 코드 0곳 |

### 3-3. 실측 재현 — 세 파일 전부 돌렸다

산식은 `qform_state.py` AC4 원문 그대로(`extract(question, business_function)` → `next_question()` 비-None 카운트). 코드 미수정, 별도 스크립트에서 import만 했다.

| 파일 | 행 | 발동 | 발동률 | 착오송금 n | 착오송금 발동 | 착오송금 발동률 | 기준선 9/450=2.0% |
|---|---:|---:|---:|---:|---:|---:|---|
| `crawler/data/testset_natural_450.jsonl` | 450 | **9** | **2.0%** | 84 | 9 | 10.7% | **정확 재현** ✅ |
| `testset/gt_natural450.jsonl` | 450 | **9** | **2.0%** | 84 | 9 | 10.7% | **정확 재현** ✅ |
| `testset/gt_natural505.jsonl` | 505 | 9 | 1.8% | 77 | 6 | 7.8% | 미재현 (분모·내용 상이) |

`crawler/data/testset_natural_450.jsonl` 행은 `python3 chatbot/qform_state.py` 정규 실행에서도 동일하게 `9건 (2.0%)`으로 나온다(§6).

### 3-4. 결정적 사실 — 두 450 파일은 **같은 질의셋**이다

| 대조 항목 | 결과 |
|---|---|
| `question` 450개 집합 동일 | ✅ |
| `question` **순서까지 동일** (리스트 == 리스트) | ✅ |
| `business_function` 행 인덱스별 일치 | ✅ **450/450** |
| 한쪽에만 있는 질문 | **0건** (양방향) |
| 발동 9건의 질문 원문 | **완전 동일** |

발동률 산식이 읽는 필드는 `question`·`business_function` 둘뿐이므로, **두 파일은 어느 쪽을 읽어도 같은 수를 낸다.** 지금 시점에서 후보 선택은 수치를 바꾸지 않는다.

두 파일이 갈리는 곳은 **정답 라벨 층**이다.

| | `crawler/data/testset_natural_450.jsonl` | `testset/gt_natural450.jsonl` |
|---|---|---|
| 정답 단위 | `gt_docs` (**문서**) | `gt_chunk_ids` (**청크**) |
| 부속 필드 | `source`·`representative`·`origin_question`·`grounding_chunk` | `answerable`·`evidence_type`·`chunk_relation`·`gt_anchor_span`·`confidence`·`reason`·`cross_domain`·`span_verbatim_ok` |
| `crawler/eval.py` 호환 | ✅ (`it["gt_docs"]` 사용) | ❌ `gt_docs` 없음 → **KeyError** |
| `id` 필드 | 없음 | 있음 (`nat450-0001`…) |

`crawler/eval.py`는 `it["gt_docs"]`를 직접 읽는다(L48). `gt_natural450.jsonl`로 갈아끼우면 **문서단위 hit@3 경로가 그대로 깨진다.** (다만 `eval.py`의 현재 `TESTSET` 상수는 `data/testset_natural_400.jsonl`이다 — §5-2 참조.)

### 3-5. 기준선 지문 — 발동 9건 원문

`id`는 `gt_natural450.jsonl` 기준(다른 후보에는 `id` 필드가 없다). 질문 원문·발동 슬롯은 세 후보 중 두 450 파일에서 동일.

| # | id | bf | 질문 | 발동 슬롯 |
|---:|---|---|---|---|
| 1 | `nat450-0087` | 착오송금 반환 신청 | 잘못 보낸 돈 반환 신청을 직접 찾아가서 하려면 어디로 가면 되나요? | `qualification` |
| 2 | `nat450-0100` | 착오송금 반환 신청 | 잘못 송금한 거 온라인으로 접수하는 절차가 어떻게 되나요? | `qualification` |
| 3 | `nat450-0101` | 착오송금 반환 신청 | 착오송금 반환 신청할 때 서류는 뭐뭐 챙겨야 하는지 알려줄 수 있어? | `qualification` |
| 4 | `nat450-0113` | 착오송금 반환 신청 | 다른 사람이 대신 방문해서 착오송금 반환 신청할 때 서류 알려주세요 | `subject` |
| 5 | `nat450-0132` | 착오송금 반환 신청 | 착오송금 반환을 대리인이 온라인으로 신청할 때 서류 좀 알려줘 | `subject` |
| 6 | `nat450-0223` | 착오송금 반환 신청 | 잘못 송금한 거 온라인 접수돼요? | `qualification` |
| 7 | `nat450-0225` | 착오송금 반환 신청 | 착오송금 반환 서류 뭐 챙겨요? | `qualification` |
| 8 | `nat450-0228` | 착오송금 반환 신청 | 착오송금 방문 접수는 어디로 가요? | `qualification` |
| 9 | `nat450-0232` | 착오송금 반환 신청 | 착오송금 대리 신청 서류는요? | `subject` |

분포 — `qualification` 6건 · `subject` 3건. **9건 전부 `bf=착오송금 반환 신청`이고 전부 `sub_task=반환신청` 계열이다.** M4에서 발동률이 움직이면 이 9건과의 차집합이 원인 분해의 출발점이다.

### 3-6. (참고) `gt_natural505.jsonl`의 발동 9건 — 숫자만 같고 내용이 다르다

| # | id | bf | 질문 | 발동 슬롯 |
|---:|---|---|---|---|
| 1 | `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply#02#a1` | 착오송금 반환 신청 | 인증서 파일 형식 바꾸려면 어디서 바꿔야 하나요? | `qualification` |
| 2 | `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply#02#a2` | 착오송금 반환 신청 | 공동인증서로 들어가기 전에 뭘 먼저 해야 하나요? | `qualification` |
| 3 | `kdic-fins-cm-bbs-selectFaqTop10#04#a1` | 착오송금 반환 신청 | 잘못 보낸 돈 돌려달라고 할 때 인터넷으로만 접수되나요? | `qualification` |
| 4 | `kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#01#a1` | 착오송금 반환 신청 | 보험금 받을 때 신분증 대신 뭘 가져가도 되나요? | `subject` |
| 5 | `kdic-fins-ir-aplygudn-MtrsVstRcptGudn-selectScrn#00#a1` | 착오송금 반환 신청 | 예금보험금 방문 신청할 때 창구 몇 시에 문 여나요? | `qualification` |
| 6 | `kdic-www-sp-kmrs-kmrsItrdAplyMthd-selectScrn#00#a2` | 착오송금 반환 신청 | 예보공사 갈 때 뭐 챙겨가야 하나요? | `qualification` |
| 7 | `v9neg-out_of_scope-009` | **null (네거티브)** | 실손보험 청구 서류가 누락됐다는데 보험사에 재요청하는 방법이 있나요? | `qualification` |
| 8 | `v9neg-out_of_scope-031` | **null (네거티브)** | 개인회생 신청 서류 예보가 대신 접수해 주나요? | `subject` |
| 9 | `v9neg-temporal-029` | **null (네거티브)** | 방금 접수한 파산신청 서류가 오늘 중 처리되나요? | `qualification` |

**9라는 숫자는 우연 일치다.** 450셋의 9건과 겹치는 질문은 0건이고(두 셋의 질문 교집합 자체가 0), 505에서는 `bf=null` 네거티브 3건이 새로 발동한다 — 450셋에는 존재하지 않는 발동 유형이다.

### 3-7. 후보 선정 결과

| 후보 | 근거 | 리스크 |
|---|---|---|
| **A. `crawler/data/testset_natural_450.jsonl`** | 3축 전부 충족 + **현행 코드 5곳이 실제로 읽는 파일** + `qform_state.py` 정규 실행이 9/2.0%를 그대로 출력 | K12가 말하는 "개정 중인 평가셋"의 구본일 가능성 |
| **B. `testset/gt_natural450.jsonl`** | 3축 전부 충족 + 발동 9건 완전 동일 + 청크단위 라벨·`id`·`answerable` 등 감사 필드 보유 | 코드가 안 읽는다 · `gt_docs` 없어 `eval.py` 비호환 · 코퍼스 지문 필드 없음 |

**단일 확정은 하지 않는다** (A0-2). §7-3 #1로 올린다.

---

## §4. 슬롯 필드 5종 · 허용값 풀 (A0-4)

원천 — `crawler/yesom_분기분석/attachment_tagging_schema.md` §2 (작성 2026-08-03, T1-b 보완 2026-08-07).
sha256 `69104e5bdf8d13b68ff617f9e48f777357cce0850c5379c6242c6a3d217b1ed8`.

### 4-1. 좌표 필드 5종 — 원문 옮김

| # | 필드 | 카디널리티 | 허용값 풀 | 공란 |
|---:|---|---|---|---|
| 1 | `party` | 단일 | `송금인` / `수취인` | **허용** (착오송금 전용 최상위 분기) |
| 2 | `sub_task` | 단일 | `제도안내`* / `반환신청` / `이의제기` / `이체수수료환급` / `신청철회` / `매입계약해제` / `수령계좌변경` / `대리인변경` / `보험금신청` / `부보금융회사조회` / `부채증명` | — |
| 3 | `qualification` | **다중(`;`)** | `본인` / `대리인` | **허용** |
| 4 | `subject` | **다중(`;`)** | `본인` / `대리인` / `미성년자` / `군복무자` / `사망 예금자` / `국외거주 또는 유학생` / `법인` / `비법인단체` / **`공통`** | 허용 |
| 5 | `method` | **다중(`;`)** | `온라인` / `방문` / `우편` / `이메일` / `팩스`* | **허용** |

`*` = T1-b(2026-08-07) 추가분. `제도안내`는 착오송금 제도 개요 질의 라벨(조합 `C01` = `outcome:정보`, 반환 첨부 없음), `팩스`는 근거 `MsdrAddrsePossDcmntGudn#01`·`AddrseAttnMttr#00` (수취인 이체수수료 환급 접수: 팩스 02-758-0270).

상위 축 `business_function`(단일): `착오송금 반환 신청` / `예금보험금 안내` / `예금자보호제도` / `채무조정 안내` — **4종.** 450셋의 6업무(+`고객 미수령금 신청`·`은닉재산 신고`)와 다르다.

### 4-2. 매칭 규칙 (스키마 §3 원문 취지)

| 규칙 | 내용 |
|---|---|
| `공통` | `subject`의 **와일드카드**. 질의 `subject`가 특정값이면 `subject ∈ {그 값, 공통}`인 첨부를 모두 후보로 |
| 공란 | 해당 축 무제약(와일드카드) |
| 다중값 | `;` 구분, 매칭은 **overlap** |
| 주체 전용 서식 | 해당 주체만 표기 (`친권합의서 → 미성년자`, `위임해지통지서 → 대리인`) |

### 4-3. 런타임 대조 — `crawler/verify_combos.py` `ALLOWED`

문서(§4-1)와 코드가 **완전히 일치한다.** 검증 스크립트가 값 풀의 실질 게이트다.

| 필드 | 스키마 문서 | `verify_combos.ALLOWED` | 일치 |
|---|---|---|---|
| `business_function` | 4종 | 4종 (동일) | ✅ |
| `party` | 송금인/수취인 + 공란 | `{송금인, 수취인}` + 공란 허용 주석 | ✅ |
| `sub_task` | 11종(제도안내 포함) | 11종 (동일) | ✅ |
| `qualification` | 본인/대리인 + 공란 | `{본인, 대리인}` + 공란 허용 | ✅ |
| `subject` | 9종(공통 포함) | 9종 (동일) | ✅ |
| `method` | 5종(팩스 포함) | 5종 (동일) | ✅ |

`T1B_WHITELIST = {("sub_task","제도안내"), ("method","팩스")}` — 예외값이 코드에 명시돼 있고, 실행 로그가 두 값의 사용을 그대로 보고한다(§6-2).

### 4-4. M2가 물릴 지점 — 기록만 (판정 없음)

| 관측 | 내용 |
|---|---|
| `party`는 착오송금 전용 | 스키마 원문이 "**착오송금 전용** 최상위 분기"로 명시. 예금보험금 조합에서 이 축이 성립하는지는 M2-2 판정 사항 |
| `sub_task` 풀에 예금보험금 값이 이미 있다 | `보험금신청`·`부보금융회사조회`. 신설이 아니라 **미사용 상태** |
| `subject` 풀에 상속 계열이 있다 | `사망 예금자`. 상속 4하위분기 좌표가 여기에 걸린다 |
| 스키마 §5 검증필요 2건 | `지분신고서 및 수령권한 위임 동의서`(사망 예금자 추정 [med]) · `손해담보 약정서`(상속 미확정 담보 추정 [low]) — **둘 다 예금보험금 페이지**다. M2 재료가 정확히 이 두 건을 포함한다 |

---

## §5. 기존 자산 상태 (M0-4)

### 5-1. 명세 지정 자산 — 존재 여부 · 줄수

| 파일 | 존재 | 줄 | 바이트 | sha256(앞16) |
|---|---|---:|---:|---|
| `chatbot/qform_extract.py` | ✅ | 389 | 22,672 | `d4f49d047abbac38` |
| `chatbot/qform_state.py` | ✅ | 270 | 13,165 | `345bf34abb402728` |
| `chatbot/qform_flow.py` | ✅ | 389 | 21,499 | `69202e43608793a6` |
| `chatbot/qform_config.py` | ✅ | 162 | 8,259 | `59a5580f818c5084` |
| `chatbot/attachments.py` | ✅ | 209 | 8,953 | `a0aa1425d4ed89cf` |
| `chatbot/app.py` | ✅ | 517 | 27,283 | `2219de8640bfd96b` |
| `chatbot/verify_qform_e2e.py` | ✅ | 299 | 16,577 | `3a9472ca2e4a5f85` |
| `chatbot/verify_qform_multiturn.py` | ✅ | 357 | 20,284 | `4e2066685f762afd` |
| `crawler/verify_combos.py` | ✅ | 184 | 8,424 | `61da07e413df9282` |
| `crawler/data/qform_combos_msdr.csv` | ✅ | 15 (헤더 1 + 14행) | 4,787 | `0115fe35b0477484` |
| `crawler/data/doc_attachments.json` | ✅ | 657 | 39,314 | `183e460f4b5febf2` |
| `crawler/yesom_분기분석/attachment_tagging_schema.md` | ✅ | 77 | 6,348 | `69104e5bdf8d13b6` |
| `crawler/data/chunks.jsonl` | ✅ | 215 | 337,572 | `6af9517ba0da80db` |
| `chatbot/chain.py` (동결) | ✅ | 324 | 17,000 | `a37b2a77eed5a5bf` |
| **`chatbot/rag.py`** (동결 목록) | ❌ **없음** | — | — | — |
| **`chatbot/eval.py`** (동결 목록) | ❌ **없음** | — | — | — |
| `crawler/verify_terms.py` (M1 신규 예정) | ❌ 없음 (정상) | — | — | — |
| `crawler/data/qform_terms_v0.csv` (M1 신규 예정) | ❌ 없음 (정상) | — | — | — |
| `crawler/data/qform_combos_dpin.csv` (M2 신규 예정) | ❌ 없음 (정상) | — | — | — |

### 5-2. 경로 불일치 — 동결 파일 2건이 다른 디렉토리에 있다

| CLAUDE.md §2 표기 | 실제 경로 | 줄 | sha256(앞16) |
|---|---|---:|---|
| `chatbot/rag.py` | **`crawler/rag.py`** | 341 | `84247b7c0aa6b6ad` |
| `chatbot/eval.py` | **`crawler/eval.py`** | 216 | `2d5b07a30db809ec` |

`chatbot/` 아래 유사 파일은 `chatbot/rag_hcx.py`(8,027B, HCX용 별개)뿐이다. 동결 대상이 실제로 가리키는 것은 `crawler/` 쪽 두 파일로 읽는 것이 맞아 보이나 **CLAUDE.md 본문 정정은 현욱 소관**이므로 §7-3 #2로 올린다.

부수 관측 — `crawler/eval.py`의 `TESTSET` 상수는 `data/testset_natural_400.jsonl`(**400건**)이다. CLAUDE.md가 `eval.py`를 "문서단위 hit@3 기준선 0.945의 주인"이라 적었는데, 그 0.945가 400셋 기준인지 450셋 기준인지는 이 파일만으로 판별되지 않는다. **M0 범위 밖이라 재지 않았다.**

### 5-3. CLAUDE.md에 없는 큐폼 자산 7개

동결·수정가능 어느 목록에도 없다. M3에서 손댈 가능성이 있으므로 기록만 한다.

| 파일 | 줄 | 성격 (docstring 요지) |
|---|---:|---|
| `chatbot/qform_ask.py` | 617 | 되묻기 **문구 생성** (T2 템플릿 ⓐ / T3 LLM ⓑ + 값 고정 가드) |
| `chatbot/qform_trace.py` | 723 | 큐폼 **트레이스 수집기** — `rag.py` 무수정, 상수 import 후 판정 재계산 |
| `chatbot/qform_panel.py` | 456 | **우측 트레이스 패널 (T6)** — `qform_trace.collect()` → 화면 모델 |
| `chatbot/qform_followup.py` | 201 | 후속 질문 추천 (ver3 T7 B5, LLM 콜 +0) |
| `chatbot/verify_qform_integration.py` | 106 | `collect()` 후단 필터 검증 (graceful·부분집합·계약 불변) |
| `chatbot/verify_docs.py` | 157 | 문서-코드 정합 검증. **`qform_flow.MAX_ASK_TURNS`를 읽는다** |
| `chatbot/answer_checks.py` | 193 | 생성 품질 규칙 검증기 골격 |

⚠ **이름 충돌 주의** — `qform_panel.py`는 이미 존재하지만 **트레이스 패널**이다. M3의 "메모리 패널"과 다른 물건이다. §7-3 #3.

`verify_qform_integration.py`는 M2-AC4(`collect(hits, qform=None)` 바이트 동일)와 검사 목적이 겹친다 — M2에서 재활용 가능 자산.

---

## §6. 검증 스크립트 7종 현 상태 (A0-5)

### 6-1. 실행 결과 — CLAUDE.md §5 목록 그대로

| # | 스크립트 | 기대 | 실측 | 종료코드 | 판정 |
|---:|---|---|---|---:|---|
| 1 | `crawler/verify_combos.py` | 전체 통과 ✅ · 14행 | **전체 통과 ✅** · 14행 · 위반 0 · 조인 합계 38 | 0 | OK |
| 2 | `crawler/verify_terms.py` | 전체 통과 ✅ | **파일 없음** (M1 산출물) | — | **미존재** |
| 3 | `chatbot/qform_extract.py` | 전체 통과 · 수기 20/20 | 20/20 (100%) · 오추출 0 · 미추출 0 · 허용값 위반 0 · 게이트 누출 0 | 0 | OK |
| 4 | `chatbot/qform_state.py` | 전체 통과 ✅ | **전체 통과 ✅** · **450셋 9건 (2.0%)** | 0 | OK |
| 5 | `chatbot/qform_config.py` | 전체 통과 ✅ | **전체 통과 ✅** · 기본값 4종 일치 | 0 | OK |
| 6 | `chatbot/verify_qform_multiturn.py` | 24/24 통과 ✅ | **24/24 통과 ✅** | 0 | OK |
| 7 | `chatbot/verify_qform_e2e.py` | 전체 통과 ✅ | **전체 통과 ✅** · AC1~AC7 | 0 | OK |

**실패한 스크립트는 없다.** 2번은 실패가 아니라 미존재이며 M1 산출물이다(명세 M1 §3). 고치지 않았다.

### 6-2. 잠가 둘 기준선 수치

| 항목 | 값 | 출처 |
|---|---|---|
| **450셋 되묻기 발동률** | **9건 / 450 = 2.0%** · 착오송금 84건 중 9건 = 10.7% | `qform_state.py` AC4 |
| 조합 시뮬 분포 | 0턴 7행 / 1턴 1행 / 2턴 6행 · **평균 0.93턴** | `qform_state.py` AC1 |
| 되묻는 슬롯 종류 | `['qualification', 'subject']` — `method`·`party` 미발동 | `qform_state.py` AC3 |
| 슬롯 추출률(착오송금 84) | party 64/84 76% · sub_task 74/84 88% · qualification 33/84 39% · subject 26/84 31% · method 29/84 35% | `qform_extract.py` |
| 기타 366건 슬롯 | **전부 None (0%)** — 스코프 게이트 정상 | `qform_extract.py` |
| 수기 20문항 sub_task | **20/20 (100%)** · 오추출 0 · 미추출 0 | `qform_extract.py` |
| 조합 테이블 | 14행 · 허용값 위반 0 · evidence 앵커 39개 미실재 0 · doc 참조 23개 미실재 0 | `verify_combos.py` |
| combo별 조인 첨부 합계 | **38** (C01=0 … C14=1, 전건 기대 일치) | `verify_combos.py` AC4 |
| outcome 분포 | `{정보:1, 서류:8, 서류;정보:5}` | `verify_combos.py` AC1 |
| T1-b 예외값 사용 | `[('method','팩스'), ('sub_task','제도안내')]` | `verify_combos.py` AC1 |
| **멀티턴 결과 지문** | **sha256 `e6d0fe7ff4540b89`** (AC4-4) | `verify_qform_multiturn.py` |
| 멀티턴 첨부 ON/OFF | C1 12→8 · C2 12→8 | `verify_qform_multiturn.py` |
| E2E 콜 회계 | 되묻기 2턴 = `answer()` 1회 · 되묻기 문구 LLM 콜 0 · chain 미로딩 | `verify_qform_e2e.py` AC1 |
| 정책 기본값 | `SLOT_CARRYOVER=True` · **`CARRYOVER_TTL=2`** · `CARRYOVER_SCOPE=bf_match` · `MAX_ASK_TURNS=2` | `qform_config.py` |

`CARRYOVER_TTL`은 현재 **2**다. K6이 3으로 올리라 했고 그 변경은 **M3-8** 소관이다. M0에서는 건드리지 않았다.

### 6-3. 재현성 확인

`verify_qform_multiturn.py`·`qform_state.py`를 각각 2회 실행했다.

| 항목 | 1회차 | 2회차 | 판정 |
|---|---|---|---|
| 멀티턴 결과 지문 | `e6d0fe7ff4540b89` | `e6d0fe7ff4540b89` | **동일** ✅ |
| 멀티턴 통과 수 | 24/24 | 24/24 | 동일 ✅ |
| 450셋 발동률 | 9건 (2.0%) | 9건 (2.0%) | **동일** ✅ |

### 6-4. E1·E2 현행 동작 — M3에서 뒤집힐 자리 (기록)

M3-7이 개정 대상으로 지정한 하니스 항목의 **개정 전 실측 문구**를 그대로 남긴다.

| 시나리오 | 대상 AC | 현행 실측 |
|---|---|---|
| E1 | AC6-1 | `subject 법인→None · ask(subject)` — **해제 직후 되묻기 재발동** |
| E2 | AC6-2 | `asked ['qualification','subject']→['qualification'] · 턴 2(상한)→2 · pending=subject` — **`asked` 정리 + 상한에서 재질문** |
| C6 | AC2-4 | `신규 → 이월 → 이월 → 미채움` (TTL=2 기준 4원소) |

K4·K6이 이 셋을 전부 뒤집는다. 개정은 M3-7이며 **M0에서는 어떤 수정도 하지 않았다.**

---

## §7. 보고 (CLAUDE.md §7 형식)

## M0 완료

### 실측

| 항목 | 기대 | 실측 | 판정 |
|---|---|---|---|
| A0-1 `testset/` 전 파일 스키마·행수·sha256 | 표로 | 2파일 · 15키/16+1키 · sha256 2건 (§2-1~2-2) | ✅ |
| A0-1 샘플 3행 원문 | 축약 금지 | 3파일 × 3행 원문 그대로 (§2-5) | ✅ |
| A0-2 발동률 후보 근거와 함께 나열 | 단일 확정 금지 | 후보 2건 + 3축 대조 + 실측 재현 (§3-2·3-3·3-7) · **확정 안 함** | ✅ |
| A0-3 HEAD SHA | 기록 | `d2a7c2053765a00e89b9c6722e6bbc12da3d49d6` | ✅ |
| A0-3 `chunks.jsonl` sha256 | 기록 | `6af9517ba0da80db1296b9c7f202b534ae23cd17d8e7746614f7d89d869bd381` | ✅ |
| A0-4 슬롯 필드 5종 · 값 풀 | 옮겨 적기 | `party`/`sub_task`/`qualification`/`subject`/`method` + 런타임 대조 (§4) | ✅ |
| A0-5 검증 7종 결과 | 표로 | 6종 통과 · 1종(`verify_terms.py`) 미존재 (§6-1) | ✅ |
| A0-6 **수정된 파일 0개** | 0 | **0** — 신규 산출 `docs/Qform_ver4_M0_recon.md` 1건뿐. 부수효과는 아래 주석 참조 | ✅ |
| 기준선 재현 | 9건 / 450 = 2.0% | **9건 / 450 = 2.0%** (후보 A·B 모두) | ✅ |
| git 명령 실행 | 0회 | **0회** (`status`·`diff`·`log` 포함) | ✅ |

> **A0-6 부수효과 명시** — §5의 검증 스크립트를 실행한 결과 `__pycache__` 바이트코드 8개가 재생성됐다
> (`chatbot/`: qform_trace·qform_extract·qform_state·attachments·qform_flow·qform_ask·qform_config · `crawler/`: rag).
> `.gitignore`의 `__pycache__/` 대상이라 커밋 경로에 들어가지 않고 소스 파일은 아니지만, "수정 0"이라 쓸 때
> 조용히 넘기지 않는다. **추적 대상 소스 파일은 실행 전후 sha256 재대조로 전건 무변동을 확인했다**
> (평가셋 3 · chunks.jsonl · 조합 CSV · `qform_state.py` · `qform_config.py` · `verify_qform_multiturn.py` ·
> `verify_combos.py` · 태깅 스키마).

### 명세와 다르게 간 것

| # | 명세 | 실제 | 이유 |
|---:|---|---|---|
| 1 | "`testset/` 디렉토리 전수 조사" | 후보 선정 단계에서만 **레포 전체 108개 json/jsonl로 범위를 넓혔다** | `testset/` 안에만 국한하면 **현행 코드가 실제로 읽는 파일**(`crawler/data/testset_natural_450.jsonl`)을 놓친다. 그 파일을 못 찾으면 "기준선을 재현할 수 있는 파일"이라는 A0-2 질문 자체에 답할 수 없다. `testset/` 전수 조사(§2)는 명세대로 따로 완료 |
| 2 | "CLAUDE.md §5의 목록을 그대로 실행" | 7종 중 **6종만 실행** | `crawler/verify_terms.py`가 아직 없다. M1 산출물이며(명세 M1 §3), 만들지 않았다 — M0는 읽기 전용 |
| 3 | "슬롯 필드 5종" | 5종 + 상위 축 `business_function`을 **별도로** 적었다 | 태깅 스키마 §2의 좌표 필드는 6개이고 그중 `business_function`은 업무 축이라 슬롯 5종과 성격이 다르다. 5종은 명세대로 옮기고 bf는 구분해 병기 |
| 4 | 선행 문서 `docs/Qform_ver4_논의정리.md` | 실제 파일명은 **`docs/Qform_ver4_논의정리_0817_v4.md`** | 그 파일을 읽었다. 동명 파일은 존재하지 않는다 |

### [판정 필요]

| # | 항목 | 선택지 | 근거 수치 |
|---:|---|---|---|
| 1 | **발동률 재측정 대상 파일 확정** (A0-2) | **(A)** `crawler/data/testset_natural_450.jsonl` — 현행 코드 5곳이 읽는 파일, 하니스 무개정 · **(B)** `testset/gt_natural450.jsonl` — 감사 필드·`id`·청크단위 라벨 보유, 대신 `qform_state.py` 수정 필요(수정가능 목록 안) · **(C)** 둘 다 잠그고 M4에서 병기 | 발동률 **A=B, 9건/450=2.0%로 완전 동일**. 질문 450개 순서까지 동일, bf 450/450 일치, 발동 9건 원문 동일 → **지금 고르는 것이 수치를 바꾸지 않는다.** 갈리는 곳은 라벨 층: `gt_docs`(A) vs `gt_chunk_ids`(B). `crawler/eval.py`는 `it["gt_docs"]`를 직접 읽으므로 B로 갈아끼우면 문서단위 경로가 깨진다 |
| 2 | **CLAUDE.md §2 동결 목록 경로 정정** | (A) `chatbot/rag.py`·`chatbot/eval.py` → `crawler/`로 정정 · (B) 그대로 두고 "존재하지 않는 경로"로 남김 | `chatbot/rag.py` **없음** · `chatbot/eval.py` **없음**. 실재는 `crawler/rag.py`(341줄) · `crawler/eval.py`(216줄). `chatbot/` 아래 유사물은 `rag_hcx.py` 하나뿐. CLAUDE.md는 미커밋 문서이고 수정 주체가 현욱이라 CC가 손대지 않았다 |
| 3 | **M3 메모리 패널의 파일 위치** | (A) `qform_panel.py`에 구역 추가 · (B) 신규 파일 분리 · (C) `app.py` 안에서 렌더 | `chatbot/qform_panel.py`가 **이미 456줄로 존재**하며 내용은 **트레이스 패널(T6)**이다 — M3의 메모리 패널과 다른 물건. CLAUDE.md 수정가능 목록에 `qform_panel.py`가 **없다**(§2). M3 착수 전에 정해야 "범위 밖 손대기"(규칙12)가 되지 않는다 |
| 4 | **(리마인드) M2 착수 판정 미탑재** | 명세 §0-2가 지정한 "확장 1순위 기준을 단일 문서 내 고유 첨부 수로 읽을지" | 명세 §0-2가 **"CC는 M2 착수 프롬프트에 이 판정이 실려 있는지 확인하고, 없으면 묻고 멈춘다"**고 지시. 현 시점 미탑재 상태를 기록만 해 둔다 |

**참고 관측 — 판정 대상 아님, 손대지 않음(K12):**
`testset/gt_natural505.jsonl`에서 `_audit.postfilter.action=regenerated` 22건 중 최소 2건이 **재생성 과정에서 다른 업무 어휘를 질문에 넣었다.**
`kdic-fins-ir-aplygudn-MsdrprPossDcmntGudn-selectScrn#01#a1` — 원문 `본인 확인용 신분증으로 사용할 수 있는 것은 무엇인가요?` → 최종 `보험금 받을 때 신분증 대신 뭘 가져가도 되나요?` (근거 청크는 착오송금).
`kdic-fins-ir-aplygudn-MtrsVstRcptGudn-selectScrn#00#a1` — 원문 `방문접수 운영 시간은 언제인가요?` → 최종 `예금보험금 방문 신청할 때 창구 몇 시에 문 여나요?` (근거 청크는 착오송금).
`business_function` 라벨은 근거 청크와 일치하므로 **틀린 것은 라벨이 아니라 질문 문구**다. 505의 `_audit.review_required=True`가 105건이다. **K12에 따라 평가셋은 읽기만 했고 수정하지 않았다.**

### 커밋 대상

```
신규: docs/Qform_ver4_M0_recon.md
수정: 없음
문서: 없음
```

커밋 대상 아님(참고): `__pycache__/*.pyc` 8개 재생성 — `.gitignore` 대상.

**수정된 파일 0개** (A0-6). 위 신규 파일 1건 외에 레포에 쓴 것이 없다.

---

## §8. 다음 마일스톤에 넘기는 잠금값

M1~M4가 K12 규약(측정 시 sha256 + HEAD SHA 병기)을 지킬 때 그대로 인용할 값이다.

```
HEAD                 d2a7c2053765a00e89b9c6722e6bbc12da3d49d6   (branch Qform_ver4)
chunks.jsonl         6af9517ba0da80db1296b9c7f202b534ae23cd17d8e7746614f7d89d869bd381
후보A testset_natural_450.jsonl
                     9df05aa1f6c6c3dcb620724974ba8d7845fa3100b9607d9359436bf890f055c5
후보B gt_natural450.jsonl
                     d92fbc5135054215c2fc74c361bb1b0529caa0352388402aeeccdb7a284bbeda
참고  gt_natural505.jsonl
                     750c56aed84fccac91276963dc12a2499ac7fbeaa95b33054a9a212913d7ac30
qform_combos_msdr.csv
                     0115fe35b0477484719d349b371c30f9ef3f1a027755a81d53f1984efa9ea7a2
발동률 기준선        9건 / 450 = 2.0%  (착오송금 84건 중 9건 = 10.7%)
멀티턴 결과 지문     e6d0fe7ff4540b89
측정일               2026-08-18 · Python 3.11.9 · 네트워크·LLM 콜 0
```

**M1로 넘어가지 않는다.** 보고 후 대기 (CLAUDE.md §0-2).

---

## §9. 판정 결과 (2026-08-18 · 현욱) — 사후 추기

M0 §7-3에 올린 [판정 필요] 4건에 대한 회신. **이 절만 사후 추기이며 위 본문은 무수정이다.**

| # | 항목 | 판정 | 후속 |
|---:|---|---|---|
| 1 | 발동률 재측정 대상 | **(A) `crawler/data/testset_natural_450.jsonl`** 확정. 단 M4 리포트에 `testset/gt_natural450.jsonl` sha256 **병기**. `qform_state.py`는 이 건으로 수정하지 않음 | M4-AC2 |
| 2 | CLAUDE.md §2 동결 목록 | **경로 정정** `crawler/rag.py` · `crawler/eval.py`. 추가로 **`chatbot/qform_panel.py` 동결 편입** — T6 트레이스 패널은 이번 스프린트 무변경 | 즉시 적용 |
| 3 | M3 메모리 패널 위치 | **(B) 신규 파일 `chatbot/qform_memory_panel.py`.** `qform_panel.py`에 얹지 않음 | M3에서 수행 |
| 4 | M2 착수 기준 | 확장 1순위를 **"단일 문서 내 고유 첨부 수"**로 읽는다. **예금보험금 확장 성립.** M2 예정대로 진행 | M2 착수 가능 |

부기 — 선행 문서 파일명은 `docs/Qform_ver4_논의정리_0817_v4.md`가 맞다(§7-2 #4 확정).

### 9-1. 판정 2 적용 후 동결 목록 (이번 스프린트 유효본)

```
crawler/rag.py                          검색
chatbot/chain.py                        생성. 4필드 계약의 주인
crawler/eval.py                         문서단위 hit@3 기준선의 주인
chatbot/verify_qform_e2e.py             ver2 기준선 검증 자산
chatbot/qform_panel.py                  T6 트레이스 패널 — 이번 스프린트 무변경  ← 신규 편입
crawler/data/qform_combos_msdr.csv      착오송금 조합 14행
crawler/data/chunks.jsonl               코퍼스 215청크
crawler/data/doc_attachments.json       문서단위 첨부
```

⚠ **디스크상 `CLAUDE.md`는 아직 정정 전이다.** mtime `2026-08-18 02:49:58`, §2 동결 블록이
여전히 `chatbot/rag.py`·`chatbot/eval.py`로 적혀 있고 `chatbot/qform_panel.py`가 없다.
**CC는 판정 내용을 기준으로 동작하며, 파일 본문은 손대지 않았다**(수정 주체 = 현욱).
