# Qform_ver4 · M9 — 스팬 기반 이행 대조표

> **브랜치** `Qform_ver4` · **작성** 2026-08-18 · **마일스톤** M9-0(조사) · M9-1/1b(도구+terms) · M9-2(prompts, combos 정지)
> **원천** `crawler/data/chunks.jsonl` 215행 sha256 `6af9517ba0da80db1296b9c7f202b534ae23cd17d8e7746614f7d89d869bd381`

---

## §0. 왜 이행하는가

청크 ID를 영속 자산의 키로 쓰지 않는다. 앵커 트랙이 **청크 사이즈를 동적으로 스윕**하므로
`chunk_id` 는 고정 식별자가 아니라 **실험 파라미터의 함수**다. 재청킹되면 `#00`·`#01` 이 재배치되고
그 ID를 박아 둔 CSV는 조용히 다른 텍스트를 가리킨다.

근거 포맷을 **`(doc_id, 텍스트 스니펫)`** 으로 옮긴다. 둘 다 청킹 불변이다.
런타임 조인은 **이미 문서 단위**(`source_doc_id`·`doc_attachments.json`·`eval.py gt_docs`)라
**아키텍처 재작성이 아니라 컬럼 포맷 이행**이다.

### 규격 (M9-1b 확립 · M9-2 승계)

| | |
|---|---|
| 직렬화 | `doc_id::스니펫` · 다중은 `\|` 연결 |
| **이행 게이트** | `resolves_to_chunk() != None` = **선언 문서 안에서 스니펫이 정확히 1회** |
| 진단값 | `evidence_span_hits` = 코퍼스 전체 히트 문서 수. **게이트 아님**(K3) |
| 구 컬럼 | `evidence_chunks_v0`·`evidence_chunk` **유지**(K1). 검증 정본은 신 컬럼 단독(K2) |
| 문자열 | **무편집.** 유일성 확보 목적이어도 자르거나 늘리지 않는다 |

---

## §1. 이행 현황 요약

| 대상 | 행 | 스팬 | 게이트 | 구 청크 일치 | 상태 |
|---|---:|---:|---|---|---|
| `qform_terms_v0.csv` | 10 | **20** | **20/20** | **20/20** | ✅ M9-1b 완료 |
| `qform_prompts.csv` (DPIN) | 8 | **8** | **8/8** | **8/8** | ✅ M9-2 완료 |
| `qform_prompts.csv` (MSDR) | 20 | — | **0/20** | — | ⛔ **이행 제외**(§3) |
| `qform_combos_dpin.csv` | 9 | **13** | **13/13** | **13/13** | ✅ M9-2b 완료(§4B) |
| `qform_combos_msdr.csv` | 14 | 39참조/29청크 | — | — | **미이행 · 동결**(§5) |

---

## §2. 이행 전건 대조 — `terms` 20 + `prompts` 8

| # | 자산 | 키 | 구 청크 ID | 신 스팬 (doc::스니펫) | 해석 청크 | 일치 |
|---:|---|---|---|---|---|---|
| 1 | terms | `PAY-01`/one_line | `…t-DpsmIbamtExpln-selectScrn#00` | `…-DpsmIbamtExpln-selectScrn::예금보험공사가 해당 금융회사를 대신하여 지급하는` | `…-selectScrn#00` | ✅ |
| 2 | terms | `PAY-01`/discriminator | `…t-DpsmIbamtExpln-selectScrn#00` | `…-DpsmIbamtExpln-selectScrn::보험사고로 인하여 고객의 예금을 지급할 수 없는` | `…-selectScrn#00` | ✅ |
| 3 | terms | `PAY-02`/one_line | `…t-DpsmIbamtExpln-selectScrn#00` | `…-DpsmIbamtExpln-selectScrn::예금자의 신청에 의해 미리 지급하는 금전` | `…-selectScrn#00` | ✅ |
| 4 | terms | `PAY-02`/discriminator | `…t-DpsmIbamtExpln-selectScrn#00` | `…-DpsmIbamtExpln-selectScrn::예금보험금 지급 이전에 예금보험금 지급한도 내에` | `…-selectScrn#00` | ✅ |
| 5 | terms | `PAY-03`/one_line | `…t-DpsmIbamtExpln-selectScrn#00` | `…-DpsmIbamtExpln-selectScrn::보호한도 초과 예금 등 채권을 예금자의 청구에 ` | `…-selectScrn#00` | ✅ |
| 6 | terms | `PAY-03`/discriminator | `…t-DpsmIbamtExpln-selectScrn#00` | `…-DpsmIbamtExpln-selectScrn::향후 파산배당으로 받게 될 예상배당률을 고려하여` | `…-selectScrn#00` | ✅ |
| 7 | terms | `PAY-04`/one_line | `…tSystHrpeHistInq-selectScrn#00` | `…SystHrpeHistInq-selectScrn::수령한 개산지급금을 초과하는 때에 그 초과금액을` | `…-selectScrn#00` | ✅ |
| 8 | terms | `PAY-04`/discriminator | `…tSystHrpeHistInq-selectScrn#00` | `…SystHrpeHistInq-selectScrn::파산배당금 등으로 회수한 금액에서 소요비용을 공` | `…-selectScrn#00` | ✅ |
| 9 | terms | `PAY-05`/one_line | `…tSystHrpeHistInq-selectScrn#00` | `…SystHrpeHistInq-selectScrn::남은 자산을 현금화하여 채권자들에게 그 채권액 ` | `…-selectScrn#00` | ✅ |
| 10 | terms | `PAY-05`/discriminator | `…tSystHrpeHistInq-selectScrn#00` | `…SystHrpeHistInq-selectScrn::금융회사가 파산하는 경우` | `…-selectScrn#00` | ✅ |
| 11 | terms | `DEBT-01`/one_line | `…SprtLbltAjmtSyst-selectScrn#00` | `…prtLbltAjmtSyst-selectScrn::파산한 경우 채무자의 연체대출금에 대한 채무조정` | `…-selectScrn#00` | ✅ |
| 12 | terms | `DEBT-01`/discriminator | `…SprtLbltAjmtSyst-selectScrn#00` | `…prtLbltAjmtSyst-selectScrn::파산된 저축은행 등의 주채무자 또는 보증채무자로` | `…-selectScrn#00` | ✅ |
| 13 | terms | `DEBT-02`/one_line | `…prtCredRcvrySprt-selectScrn#00` | `…rtCredRcvrySprt-selectScrn::상환기간의 연장, 분할상환, 이자율 조정,변제기` | `…-selectScrn#00` | ✅ |
| 14 | terms | `DEBT-02`/discriminator | `…prtCredRcvrySprt-selectScrn#00` | `…rtCredRcvrySprt-selectScrn::신용회복위원회(개별 금융회사에 신청하는 것이 아` | `…-selectScrn#00` | ✅ |
| 15 | terms | `DEBT-03`/one_line | `…bltAjmtSprtPsnRg-selectScrn#00` | `…ltAjmtSprtPsnRg-selectScrn::지급불능 상태에 있는 사람이 일정한 소득을 얻고` | `…-selectScrn#00` | ✅ |
| 16 | terms | `DEBT-03`/discriminator | `…bltAjmtSprtPsnRg-selectScrn#00` | `…ltAjmtSprtPsnRg-selectScrn::매달 월급이나 연금, 사업소득 등 정기적이고, ` | `…-selectScrn#00` | ✅ |
| 17 | terms | `DEBT-04`/one_line | `…bltAjmtSprtPsnBr-selectScrn#00` | `…ltAjmtSprtPsnBr-selectScrn::자신의 재산으로 모든 채무를 변제할 수 없는 상` | `…-selectScrn#00` | ✅ |
| 18 | terms | `DEBT-04`/discriminator | `…bltAjmtSprtPsnRg-selectScrn#00` | `…ltAjmtSprtPsnRg-selectScrn::개인회생절차, 일반회생절차 등을 통하여 충분히 ` | `…-selectScrn#00` | ✅ |
| 19 | terms | `DEBT-05`/one_line | `…bltAjmtSprtPsnBr-selectScrn#00` | `…ltAjmtSprtPsnBr-selectScrn::파산절차를 통하여 변제되지 아니한 나머지 채무에` | `…-selectScrn#00` | ✅ |
| 20 | terms | `DEBT-05`/discriminator | `…bltAjmtSprtPsnBr-selectScrn#00` | `…ltAjmtSprtPsnBr-selectScrn::개인파산을 신청하는 채무자가 면책을 받기 위해서` | `…-selectScrn#00` | ✅ |
| 21 | prompts | `qualification`/본인 | `…amtAplyPossDcmnt-selectScrn#00` | `…mtAplyPossDcmnt-selectScrn::예금자 본인이 찾을 경우` | `…-selectScrn#00` | ✅ |
| 22 | prompts | `qualification`/대리인 | `…amtAplyPossDcmnt-selectScrn#00` | `…mtAplyPossDcmnt-selectScrn::대리인이 찾을 경우` | `…-selectScrn#00` | ✅ |
| 23 | prompts | `subject`/본인 | `…amtAplyPossDcmnt-selectScrn#00` | `…mtAplyPossDcmnt-selectScrn::예금자 본인이 찾을 경우` | `…-selectScrn#00` | ✅ |
| 24 | prompts | `subject`/대리인 | `…amtAplyPossDcmnt-selectScrn#00` | `…mtAplyPossDcmnt-selectScrn::대리인이 찾을 경우` | `…-selectScrn#00` | ✅ |
| 25 | prompts | `subject`/군복무자 | `…amtAplyPossDcmnt-selectScrn#00` | `…mtAplyPossDcmnt-selectScrn::예금자 본인이 군복무 중일 경우` | `…-selectScrn#00` | ✅ |
| 26 | prompts | `subject`/미성년자 | `…amtAplyPossDcmnt-selectScrn#00` | `…mtAplyPossDcmnt-selectScrn::예금자가 미성년자인 경우` | `…-selectScrn#00` | ✅ |
| 27 | prompts | `subject`/사망 예금자 | `…amtAplyPossDcmnt-selectScrn#01` | `…mtAplyPossDcmnt-selectScrn::예금자가 사망한 경우` | `…-selectScrn#01` | ✅ |
| 28 | prompts | `subject`/국외거주 또는 유학생 | `…amtAplyPossDcmnt-selectScrn#02` | `…mtAplyPossDcmnt-selectScrn::예금자가 국외거주 외국인, 유학생, 상사주재원인` | `…-selectScrn#02` | ✅ |

**전 28건 일치 · 이행이 근거 대상을 바꾸지 않았다.**

---

## §3. `qform_prompts.csv` MSDR 20행 — 이행 제외 (1-3)

게이트 **0 / 20**. 사유 분류:

| 사유 | 행 | 예 |
|---|---:|---|
| 선언 문서 내 **7회** 출현 | 5 | `대리인` |
| 선언 문서 내 **3회** 출현 | 5 | `본인` |
| 선언 문서 내 **2회** 출현 | 8 | `법인을 대리하는 경우` |
| **비축자 — 선언 청크에 없음** | **2** | `국외거주 또는 유학생을 대리하는 경우` |

**MSDR `phrase` 는 근거 스니펫이 아니라 버튼 라벨이다.** `본인`·`대리인` 같은 짧은 라벨은
문서 어디에나 나오므로 "정확히 1회"를 만족할 수 없다. 문자열 편집 금지(K5)라 늘릴 수도 없다.

> ⚠ **비축자 2행은 별개 발견이다.** `subject/반환신청/국외거주 또는 유학생` 과 `subject/*/…` 의
> `phrase` `국외거주 또는 유학생을 대리하는 경우` 가 선언 청크 `MsdrprPossDcmntGudn#09` 에 **없다.**
> `qform_prompts.csv` 는 **축자성 검증을 받는 스크립트가 없어**(verify_terms 는 terms CSV만 본다)
> ver3 시점부터 지금까지 안 걸렸다.

신 컬럼은 **공란**으로 두었다. `evidence_chunk` 구 컬럼은 그대로다.

---

## §4. `qform_combos_dpin.csv` — 2-2(c) 정지

### 4-1. 적용한 추출 규칙 (코드 인용)

```python
SENT = re.compile(r"(?<=[.?!])\s+|\n")     # 문장 경계 = 종결부호(.?!) 뒤 공백 또는 개행
# (a) 선두 1문장 → (b) resolves_to_chunk 가 None 이면 다음 문장까지 확장 → (c) 상한 120자
```

개행을 경계로 넣은 이유 — 코퍼스가 **개행 구분 목록**을 많이 쓴다(구비서류 나열).

### 4-2. 결과 — 고유 6청크 중 **2개만 해소**

| 청크 | 해소 n문장 | 그 길이 | 120자 | 선두 1문장 실물 |
|---|---:|---:|---|---|
| `DpsmIbamtExpln#00` | 1 | **162** | ⛔ 초과 | `예금보험에 가입한 금융회사가 예금의 지급정지, 영업 인 · 허가의 취소, 해산 또는 파산 등으로…` |
| `DpsmIbamtAplyProc#00` | 1 | 2 | ✅ | **`01`** |
| `DpsmIbamtAplyPossDcmnt#00` | 1 | 2 | ✅ | **`01`** |
| `…PossDcmnt#01` | 5 | **144** | ⛔ 초과 | `친권자 혹은 후견인이 예금보험금 수령` |
| `…PossDcmnt#02` | 2 | **159** | ⛔ 초과 | `의서(양식에 구애받지 않고 동의한 사실이 나타나면 됨)를 받으면 예외적으로 방문없이 신청이 가능하며…` |
| `…PossDcmnt#03` | 5 | **156** | ⛔ 초과 | `여권 등 공공기관에서 발행한 사진이 들어간 본인임을 확인할 수 있는 증명` |

**정지 사유 둘 — 판정 대상이다.**

| # | 문제 | 실측 |
|---:|---|---|
| 1 | **상한 120자에서 4/6 미해소** | 해소에 필요한 길이 144·156·159·**162**자 |
| 2 | **해소된 2개의 스니펫이 `01`** | 청크 선두가 목록 번호다. 게이트는 통과하지만 **근거로 읽을 수 없다** |

2-5가 요구한 "근거로 뽑힌 스니펫 전문"이 위 표다. **CSV는 수정하지 않았다.**

---

## §4-B. `qform_combos_dpin.csv` 이행 완료 (M9-2b) — 앵커 스팬 규칙

### 4B-1. 폐기된 규칙과 사유 (기록 보존)

M9-2 의 **"선두 1문장 + 확장 + 상한 120자"** 는 폐기했다.

| | |
|---|---|
| 무엇이 틀렸나 | **게이트(청크를 결정하는가)를 근거 가치의 대리로 썼다** |
| 증거 | 청크 선두가 목록 번호인 문서에서 스니펫 **`01`** 이 게이트를 통과했다 — 청크는 확정하지만 근거로 읽을 수 없다 |
| 상한 상향은? | **증상만 덮는다.** 실측상 4/6 청크가 144·156·159·162자를 요구했고, 올려도 `01` 문제는 그대로다 |

### 4B-2. 앵커 스팬 규칙 (`span_tools.pick_anchor`)

```python
SENTENCE_BOUNDARY = re.compile(r"(?<=[.?!])\s+|\n")   # M9-2 정의 승계
# (a) 청크를 문장 단위 분할  (b) 각 문장을 후보 — **선두 고정 없음**
# (c) resolves_to_chunk(doc, 후보) == 대상 chunk_id 인 것만
# (d) 남은 것 중 **가장 짧은 것**, 동률이면 문서 내 먼저 나온 것
# (e) 없으면 인접 2연결 → 3연결, max_len=200 초과는 버림  (f) 끝내 없으면 None
```

후보는 **원문의 연속 슬라이스**로만 만든다(오프셋 기반) — 문자열로 쪼갠 뒤 이어 붙이면
사이 공백·개행이 소실돼 부분문자열이 깨진다.

### 4B-3. 선택 근거 (1-2)

| 청크 | 후보 | 통과 | 연결 | 길이 | 선택된 스니펫 |
|---|---:|---:|---:|---:|---|
| `…p-dpstrprot-DpsmIbamtExpln-selectScrn#00` | 13 | 9 | 1문장 | 7 | **`가지급금이란?`** |
| `…pstrprot-DpsmIbamtAplyProc-selectScrn#00` | 30 | 21 | 1문장 | 2 | **`01`** |
| `…rot-DpsmIbamtAplyPossDcmnt-selectScrn#00` | 37 | 16 | 1문장 | 2 | **`01`** |
| `…rot-DpsmIbamtAplyPossDcmnt-selectScrn#01` | 24 | 18 | 1문장 | 2 | **`05`** |
| `…rot-DpsmIbamtAplyPossDcmnt-selectScrn#02` | 19 | 11 | 1문장 | 2 | **`06`** |
| `…rot-DpsmIbamtAplyPossDcmnt-selectScrn#03` | 17 | 8 | 1문장 | 2 | **`07`** |

> ⚠ **6개 중 4개가 목록 번호(`01`·`05`·`06`·`07`)로 뽑혔다.**
> 규칙이 "가장 짧은 것"을 고르는데 청크 선두의 목록 번호가 유일하게 해소되기 때문이다.
> **CC 는 규칙만 적용했고 근거 가치는 판정하지 않았다**(2-5). `evidence_span_hits` 가
> 이 값들을 **`9`**(코퍼스 전체 9개 문서에 출현)로 표시해 수치로 드러낸다.

### 4B-4. 전건 대조 (2-4)

| combo_id | 구 청크 | 신 스니펫 | 해석 청크 | 일치 | hits |
|---|---|---|---|---|---:|
| `DPIN-C01` | `…smIbamtExpln-selectScrn#00` | `가지급금이란?` | `…-selectScrn#00` | ✅ | 1 |
| `DPIN-C01` | `…bamtAplyProc-selectScrn#00` | `01` | `…-selectScrn#00` | ✅ | 9 |
| `DPIN-C02` | `…plyPossDcmnt-selectScrn#00` | `01` | `…-selectScrn#00` | ✅ | 9 |
| `DPIN-C03` | `…plyPossDcmnt-selectScrn#00` | `01` | `…-selectScrn#00` | ✅ | 9 |
| `DPIN-C04` | `…plyPossDcmnt-selectScrn#00` | `01` | `…-selectScrn#00` | ✅ | 9 |
| `DPIN-C05` | `…plyPossDcmnt-selectScrn#00` | `01` | `…-selectScrn#00` | ✅ | 9 |
| `DPIN-C05` | `…plyPossDcmnt-selectScrn#01` | `05` | `…-selectScrn#01` | ✅ | 5 |
| `DPIN-C06` | `…plyPossDcmnt-selectScrn#01` | `05` | `…-selectScrn#01` | ✅ | 5 |
| `DPIN-C07` | `…plyPossDcmnt-selectScrn#01` | `05` | `…-selectScrn#01` | ✅ | 5 |
| `DPIN-C07` | `…plyPossDcmnt-selectScrn#02` | `06` | `…-selectScrn#02` | ✅ | 2 |
| `DPIN-C08` | `…plyPossDcmnt-selectScrn#02` | `06` | `…-selectScrn#02` | ✅ | 2 |
| `DPIN-C08` | `…plyPossDcmnt-selectScrn#03` | `07` | `…-selectScrn#03` | ✅ | 2 |
| `DPIN-C09` | `…bamtAplyProc-selectScrn#00` | `01` | `…-selectScrn#00` | ✅ | 9 |

**스팬 13개 · 게이트 13/13 · 구 청크 일치 13/13 · 미이행 행 0**

### 4B-5. 참고 — 기존 이행 자산과의 일관성 (2-6)

| 자산 | 스팬 | 앵커 규칙이 같은 청크로 해석 |
|---|---:|---:|
| `qform_terms_v0.csv` | 20 | **20 / 20** |
| `qform_prompts.csv` (DPIN) | 8 | **8 / 8** |

CSV 는 건드리지 않았다. 기존 이행이 앵커 규칙과 **모순되지 않음**만 확인한 수치다.

### 4B-6. `verify_combos.py` AC2 개정

| | |
|---|---|
| 개정 | `evidence_spans` 각 스팬에 `resolves_to_chunk != None` — **텍스트 실재 대조로 격상** |
| 구 컬럼 | **참고 출력만.** 종료코드 미반영(K2) — 재청킹으로 구 기준이 전부 실패해도 통과해야 한다 |
| MSDR 폴백 | `evidence_spans` 부재 → 구 검사(chunk_id 실재)로 폴백하고 **그 사실을 출력에 명시** |
| 고의 실패 주입 | `가지급금이란?` → `가지급금이람?` 1글자 → **미해소 1건 · exit 1** · 원복 후 해시 동일 |

---

## §5. `qform_combos_msdr.csv` — 미이행

| 항목 | 값 |
|---|---|
| 행 / 참조 / 고유 청크 | 14행 / **39참조** / **29청크** |
| 사유 | **동결**(CLAUDE.md §2). 어떤 이유로도 수정하지 않는다 |
| 처리 계획 | **다음 스프린트 동결 해제 1회에 P16·P18과 동시 처리** |
| 현 대응 | `verify_combos.py` 에서 **구 검사 폴백**(§6) |

전체 청크 참조 중 MSDR 비중 — 39 / 96 = **41%**. 이행 후에도 청크 ID가 레포에 남는다.

---

## §6. `verify_combos.py` AC2 개정 — **완료** (§4B-6)

---

## §7. 회귀 (M9-2 시점)

| 항목 | 기대 | 실측 |
|---|---|---|
| 검증 10종 + `span_tools` | exit 0 | **전건 0** |
| 멀티턴 지문 | `246d07124d333c9b` | **동일** |
| 패널 지문 | `12619f9c100feb6e` | **동일** |
| 450셋 발동률 | 9건 / 2.0% · 착오송금 10.7% | **동일** |
| `verify_combos` 조인 | MSDR 38 / DPIN 11 | **동일** |
| 동결 8종 | 무변동 | **해시 전건 동일** |

---

## §8-5. 이행해도 **안 깨지는 것** — 결합 0 실측 (M9-0 C·D)

| 대상 | 왜 안 깨지나 | 실측 근거 |
|---|---|---|
| **첨부 태깅 CSV** (`attachment_tagging_template.csv`) | **청크 컬럼이 0개다.** 컬럼 20개 중 `chunk`/`evidence`/`span` 포함 **0개**. 런타임 조인 키는 `(source_doc_id, canonical_filename)` + 6좌표(`business_function`·`party`·`sub_task`·`qualification`·`subject`·`method`) | M9-0 C-1~C-4 · `attachments.py:103` · `_joins_combo` L113~127 |
| **이월 방벽 `bf_match`** | **질의 키워드 기반이다.** `classify_query_bf(query)` 가 읽는 것은 질의 문자열 + `rag.BF_QUERY_KEYWORDS` 상수뿐. `chunks` 참조 **없음**(소스 검사) | M9-0 D-1~D-3 · `qform_flow.py:122`·`162`·`79-80` · `rag.py:113-116` |

**따라서 이행 범위는 CSV 4종(terms·prompts·dpin·msdr)뿐이고, 런타임 조인 경로는 손대지 않는다.**

---

## §9. `qform_combos_dpin.csv` 재이행 (M9-3) — 선택 기준 교체

### 9-1. 개정 사유 (L1 판정 · D 채택)

**게이트(청크를 결정하는가)와 근거 가치는 다른 층이다.** M9-2b 앵커 규칙은 게이트 통과분 중
**가장 짧은 것**을 골랐다. 그런데 "가장 짧다"가 곧 "가장 특징적"이 아니었다 — 목록 번호
`01`·`05`·`06`·`07` 은 선언 문서 안에서 정확히 1회(게이트 통과)지만 코퍼스 여러 문서에 흩어져
근거로 읽히지 않는다.

M9-3 은 **정렬 키만** 교체한다. 게이트(`resolves_to_chunk != None`)는 무수정이다.

```
현행: 게이트 통과 후보 → 길이 오름차순 → 첫 번째
개정: 게이트 통과 후보 → hit_docs 오름차순 → 길이 오름차순 → 문서 내 먼저 나온 것
```

`hit_docs` 는 여전히 **게이트가 아니라 정렬 키**다(K3). 길이 하한·목록 번호 패턴 제외 같은
임의 규칙은 추가하지 않는다. 단 **스팬 조인 구분자 `|` 를 포함하는 후보**는 직렬화 불가이므로
후보에서 제외한다 — `format_span` 이 이미 거절하는 계약(M9-3 판정 A)이다.

### 9-2. 폐기된 기준 (길이 단독 정렬)과 실패 사례

| 폐기 | 실패 사례 |
|---|---|
| 게이트 통과분 중 **가장 짧은 것** (M9-2b) | `01` 이 `hits=9` 로 선택됨. 목록 번호가 **5청크**에서 뽑힘(`01`·`05`·`06`·`07`) |

> ⚠ **M9-2b 수치 오보고 정정** — M9-2b 보고의 "DPIN hits 분포 `1` 1개 · `9` 12개" 는 뭉갠
> 수치다. 실제(13스팬): `9`×6 · `5`×3 · `2`×3 · `1`×1. 목록 번호 청크도 **4건이 아니라 5건**이다
> (`01` 이 `AplyProc#00`·`AplyPossDcmnt#00` 두 청크에 걸침).

### 9-3. 전/후 대조표 (1-4)

| 청크(끝) | 전 스니펫 | 전 길이 | 전 hits | 후 스니펫 | 후 길이 | 후 hits | 변경 |
|---|---|---|---|---|---|---|---|
| DpsmIbamtExpln#00 | 가지급금이란? | 7 | 1 | 가지급금이란? | 7 | 1 | 유지 |
| DpsmIbamtAplyProc#00 | 01 | 2 | 9 | 인터넷 신청 시 | 8 | 1 | ✅ |
| AplyPossDcmnt#00 | 01 | 2 | 9 | 대리인이 찾을 경우 | 10 | 1 | ✅ |
| AplyPossDcmnt#01 | 05 | 2 | 5 | 친권자의 도장 | 7 | 1 | ✅ |
| AplyPossDcmnt#02 | 06 | 2 | 2 | 상속인의 도장 | 7 | 1 | ✅ |
| AplyPossDcmnt#03 | 07 | 2 | 2 | 손해담보 약정서 | 8 | 1 | ✅ |

### 9-4. 갱신 13스팬 (2-5) — `⚑` = 10자 미만(L1-b 플래그 · 게이트 아님)

| combo_id | 스니펫 | 길이 | hits | 플래그 |
|---|---|---|---|---|
| DPIN-C01 | 가지급금이란? | 7 | 1 | ⚑ |
| DPIN-C01 | 인터넷 신청 시 | 8 | 1 | ⚑ |
| DPIN-C02 | 대리인이 찾을 경우 | 10 | 1 | |
| DPIN-C03 | 대리인이 찾을 경우 | 10 | 1 | |
| DPIN-C04 | 대리인이 찾을 경우 | 10 | 1 | |
| DPIN-C05 | 대리인이 찾을 경우 | 10 | 1 | |
| DPIN-C05 | 친권자의 도장 | 7 | 1 | ⚑ |
| DPIN-C06 | 친권자의 도장 | 7 | 1 | ⚑ |
| DPIN-C07 | 친권자의 도장 | 7 | 1 | ⚑ |
| DPIN-C07 | 상속인의 도장 | 7 | 1 | ⚑ |
| DPIN-C08 | 상속인의 도장 | 7 | 1 | ⚑ |
| DPIN-C08 | 손해담보 약정서 | 8 | 1 | ⚑ |
| DPIN-C09 | 인터넷 신청 시 | 8 | 1 | ⚑ |

게이트 13/13 · 구 청크 대조 13/13 · 목록 번호 스니펫 잔여 **0** · 분리자 포함 0.
→ §4B-3·§4B-4 (M9-2b 결과)의 13스팬은 본 절로 대체된다.

### 9-5. hits 분포 전후 (2-7)

| | 분포 |
|---|---|
| 전(M9-2b) | `1`×1 · `9`×6 · `5`×3 · `2`×3 |
| 후(M9-3) | `1`×13 |

### 9-6. terms/prompts 일관성 (3-1 · 3-3)

| 항목 | 값 |
|---|---|
| 3-1 청크 레벨 일치 | **28/28** (terms 20 + prompts 8) |
| 3-3 스니펫 바뀌려는 건수 | **26/28** |

terms 는 **정의(one_line/discriminator)**, prompts 는 **값 라벨(phrase)** 증거라 개정 anchor 규칙을
적용하면 의미가 깨진다(terms: 정의→헤딩, prompts: `본인`→`대리인` 역전). 따라서 **terms/prompts 는
무수정**(3-2). 개정 규칙은 combos_dpin 에만 적용한다.
