<!-- 상태:records -->
> **기록** — 2026-08-25 시점의 사실. 고치지 않는다(정정은 추기로)
> 문서 지도: `docs/README.md`(문서 지도) · `docs/프로젝트_전체흐름.md`(전체 그림·용어 해설)

---

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

### 9-7. 자산별 증거 모델 (K10 · M9-3b)

`pick_anchor` 는 **원 문자열이 없는 자산**에만 적용한다. 다음에 "왜 규칙을 통일하지 않았나" 논쟁이
반복되지 않도록 여기서 끊는다.

| 자산 | 증거 모델 | 스니펫의 정체 | pick_anchor 적용 |
|---|---|---|---|
| `qform_terms_v0.csv` | 정의문 | 원 문자열 존재 (one_line/discriminator) | ✗ |
| `qform_prompts.csv` | 버튼 라벨 | 원 문자열 존재 (phrase) | ✗ (K7 로 이행 제외) |
| `qform_combos_dpin.csv` | 없음 | 추출물 (청크에서 뽑음) | ✓ |

3-3 의 26/28 은 불일치가 아니라 규칙이 적용 범위를 벗어났을 때의 정상 반응이다.

### 9-8. H-6 주입 검사 훼손 사고 기록 (M9-3b 2-1)

- **훼손 파일**: `crawler/data/qform_combos_dpin.csv` → 0바이트.
- **버그 지점**: 인라인 원복 스크립트의 `open(path, "wb").write(open(path, "rb").read().replace(...))`.
  `wb` 오픈이 파일을 먼저 비워, `rb` 읽기가 빈 파일을 읽는다.
- **복원**: M9-3 재이행 스크립트 재실행. 복원 후 sha `d4fff0ff…9cd34f23` = **훼손 직전(재이행 후) sha 와 byte 동일**.
- **결론**: 훼손 직전 상태로 완전 복원(재생성 결정론 + sha 일치로 담보). 하네스가 데이터를 파괴할 수
  있다는 사실 자체가 인계 자산 — H46 으로 등재했다.

---

## §10. 이행 전건 41스팬 통합표 (M9-4 · 2-1)

> 구 청크 ID / 해석 청크는 청크 ID 말미만 표기(전체 ID 는 §2·§4B·§9 참조). `⚑` = 10자 미만(L1-b 플래그 · 게이트 아님).

| 자산 | 행 | 구 청크 ID | 신 스팬 | 해석 청크 | 일치 | hits | 길이 |
|---|---|---|---|---|---|---|---|
| terms | PAY-01/one_line | amtExpln#00 | 예금보험공사가 해당 금융회사를 대신하여 지급하는 금전 | amtExpln#00 | ✅ | 1 | 29 |
| terms | PAY-01/disc | amtExpln#00 | 보험사고로 인하여 고객의 예금을 지급할 수 없는 경우 | amtExpln#00 | ✅ | 1 | 29 |
| terms | PAY-02/one_line | amtExpln#00 | 예금자의 신청에 의해 미리 지급하는 금전 | amtExpln#00 | ✅ | 2 | 22 |
| terms | PAY-02/disc | amtExpln#00 | 예금보험금 지급 이전에 예금보험금 지급한도 내에서 | amtExpln#00 | ✅ | 2 | 27 |
| terms | PAY-03/one_line | amtExpln#00 | 보호한도 초과 예금 등 채권을 예금자의 청구에 의하여 공사가 매입하고, 그 매입의 대가로 예금자에게 지급하는 금전 | amtExpln#00 | ✅ | 1 | 63 |
| terms | PAY-03/disc | amtExpln#00 | 향후 파산배당으로 받게 될 예상배당률을 고려하여 | amtExpln#00 | ✅ | 1 | 26 |
| terms | PAY-04/one_line | eHistInq#00 | 수령한 개산지급금을 초과하는 때에 그 초과금액을 예금자에게 추가로 지급 | eHistInq#00 | ✅ | 3 | 39 |
| terms | PAY-04/disc | eHistInq#00 | 파산배당금 등으로 회수한 금액에서 소요비용을 공제한 금액이 | eHistInq#00 | ✅ | 3 | 32 |
| terms | PAY-05/one_line | eHistInq#00 | 남은 자산을 현금화하여 채권자들에게 그 채권액 비율대로 배당하는 금액 | eHistInq#00 | ✅ | 3 | 38 |
| terms | PAY-05/disc | eHistInq#00 | 금융회사가 파산하는 경우 | eHistInq#00 | ✅ | 3 | 13 |
| terms | DEBT-01/one_line | AjmtSyst#00 | 파산한 경우 채무자의 연체대출금에 대한 채무조정을 지원 | AjmtSyst#00 | ✅ | 1 | 30 |
| terms | DEBT-01/disc | AjmtSyst#00 | 파산된 저축은행 등의 주채무자 또는 보증채무자로서 재산상태나 소득수준 등을 감안하여 채무변제를 기대할 수 없다고 판단되는 채무자 | AjmtSyst#00 | ✅ | 2 | 71 |
| terms | DEBT-02/one_line | cvrySprt#00 | 상환기간의 연장, 분할상환, 이자율 조정,변제기 유예, 채무감면 등의 채무조정 수단을 통해 신용회복을 지원 | cvrySprt#00 | ✅ | 1 | 59 |
| terms | DEBT-02/disc | cvrySprt#00 | 신용회복위원회(개별 금융회사에 신청하는 것이 아닙니다.)에 구비서류를 지참하여 신청 | cvrySprt#00 | ✅ | 1 | 46 |
| terms | DEBT-03/one_line | prtPsnRg#00 | 지급불능 상태에 있는 사람이 일정한 소득을 얻고 있을 경우에 3~5년간 일정한 금액을 갚으면 채무를 면제받는 제도 | prtPsnRg#00 | ✅ | 1 | 63 |
| terms | DEBT-03/disc | prtPsnRg#00 | 매달 월급이나 연금, 사업소득 등 정기적이고, 확실한 수입을 계속하여 얻을 가능성이 있는 사람이어야 합니다 | prtPsnRg#00 | ✅ | 1 | 59 |
| terms | DEBT-04/one_line | prtPsnBr#00 | 자신의 재산으로 모든 채무를 변제할 수 없는 상태에 빠진 경우에 그 채무의 정리를 위하여 채무자 또는 채권자가 파산신청 | prtPsnBr#00 | ✅ | 1 | 66 |
| terms | DEBT-04/disc | prtPsnRg#00 | 개인회생절차, 일반회생절차 등을 통하여 충분히 회생을 도모할 수 있다고 인정되는 경우에 개인파산신청을 하게 되면 절차남용으로 각하될 수 있습니다 | prtPsnRg#00 | ✅ | 1 | 80 |
| terms | DEBT-05/one_line | prtPsnBr#00 | 파산절차를 통하여 변제되지 아니한 나머지 채무에 대한 변제책임을 파산법원의 재판으로 면제 | prtPsnBr#00 | ✅ | 1 | 49 |
| terms | DEBT-05/disc | prtPsnBr#00 | 개인파산을 신청하는 채무자가 면책을 받기 위해서는 파산신청과 별개로 면책을 신청하여야 하며 | prtPsnBr#00 | ✅ | 1 | 50 |
| prompts | qualification/본인 | ossDcmnt#00 | 예금자 본인이 찾을 경우 | ossDcmnt#00 | ✅ | 1 | 13 |
| prompts | qualification/대리인 | ossDcmnt#00 | 대리인이 찾을 경우 | ossDcmnt#00 | ✅ | 1 | 10 |
| prompts | subject/본인 | ossDcmnt#00 | 예금자 본인이 찾을 경우 | ossDcmnt#00 | ✅ | 1 | 13 |
| prompts | subject/대리인 | ossDcmnt#00 | 대리인이 찾을 경우 | ossDcmnt#00 | ✅ | 1 | 10 |
| prompts | subject/군복무자 | ossDcmnt#00 | 예금자 본인이 군복무 중일 경우 | ossDcmnt#00 | ✅ | 1 | 17 |
| prompts | subject/미성년자 | ossDcmnt#00 | 예금자가 미성년자인 경우 | ossDcmnt#00 | ✅ | 2 | 13 |
| prompts | subject/사망 예금자 | ossDcmnt#01 | 예금자가 사망한 경우 | ossDcmnt#01 | ✅ | 2 | 11 |
| prompts | subject/국외거주 또는 유학생 | ossDcmnt#02 | 예금자가 국외거주 외국인, 유학생, 상사주재원인 경우 | ossDcmnt#02 | ✅ | 1 | 29 |
| combos | DPIN-C01 | amtExpln#00 | 가지급금이란? | amtExpln#00 | ✅ | 1 | 7 ⚑ |
| combos | DPIN-C01 | AplyProc#00 | 인터넷 신청 시 | AplyProc#00 | ✅ | 1 | 8 ⚑ |
| combos | DPIN-C02 | ossDcmnt#00 | 대리인이 찾을 경우 | ossDcmnt#00 | ✅ | 1 | 10 |
| combos | DPIN-C03 | ossDcmnt#00 | 대리인이 찾을 경우 | ossDcmnt#00 | ✅ | 1 | 10 |
| combos | DPIN-C04 | ossDcmnt#00 | 대리인이 찾을 경우 | ossDcmnt#00 | ✅ | 1 | 10 |
| combos | DPIN-C05 | ossDcmnt#00 | 대리인이 찾을 경우 | ossDcmnt#00 | ✅ | 1 | 10 |
| combos | DPIN-C05 | ossDcmnt#01 | 친권자의 도장 | ossDcmnt#01 | ✅ | 1 | 7 ⚑ |
| combos | DPIN-C06 | ossDcmnt#01 | 친권자의 도장 | ossDcmnt#01 | ✅ | 1 | 7 ⚑ |
| combos | DPIN-C07 | ossDcmnt#01 | 친권자의 도장 | ossDcmnt#01 | ✅ | 1 | 7 ⚑ |
| combos | DPIN-C07 | ossDcmnt#02 | 상속인의 도장 | ossDcmnt#02 | ✅ | 1 | 7 ⚑ |
| combos | DPIN-C08 | ossDcmnt#02 | 상속인의 도장 | ossDcmnt#02 | ✅ | 1 | 7 ⚑ |
| combos | DPIN-C08 | ossDcmnt#03 | 손해담보 약정서 | ossDcmnt#03 | ✅ | 1 | 8 ⚑ |
| combos | DPIN-C09 | AplyProc#00 | 인터넷 신청 시 | AplyProc#00 | ✅ | 1 | 8 ⚑ |

**일치 41/41 · 10자 미만 9건(L1-b 플래그)** — terms 20 · prompts DPIN 8 · combos_dpin 13.

---

## §11. 미이행 · 안 깨지는 것 · 폐기 계보 · ver1 보전 (M9-4)

### 11-1. 미이행 명시표 (2-2)

| 자산 | 참조 수 | 사유 |
|---|---:|---|
| `qform_combos_msdr.csv` | 39 | 동결. 다음 스프린트 해제 1회에 P16(party 강등)·P18(subject 정규화)·source_status 컬럼과 동시 처리 |
| `qform_prompts.csv` MSDR | 20 | phrase 가 버튼 라벨. 구조적 불가 (K7) |

**이행 41 / 미이행 59** — 전체 참조 96개 기준 미이행 59개(61%), 그중 MSDR combos 39개가 41%.
이 정도가 남는 것은 **수용된 상태**다(MSDR은 215 기준, `chunks.jsonl`도 동결이라 내부 정합 유지).

### 11-2. 「안 깨지는 것」 표 (2-3 · M9-0 C·D 실측 근거)

| 대상 | 묶여 있는 키 | 근거 |
|---|---|---|
| 조합 테이블 조인 | `source_doc_id` (문서 단위) | 설계상 |
| 첨부 후단 필터 | `doc_attachments.json` (문서 단위) | 설계상 |
| `eval.py` hit@k | `gt_docs` (문서 단위) | 설계상 |
| 첨부 태깅 CSV | 청크 컬럼 0 / 6좌표 조인 | M9-0 C 실측 |
| `bf_match` 이월 방벽 | 질의 문자열 + 상수표 | M9-0 D 실측 |
| 앵커 트랙 테스트셋 | 앵커 스팬 | 전제 |

### 11-3. 폐기 규칙 계보 (2-4)

| 단계 | 규칙 | 폐기 사유 |
|---|---|---|
| M9-1 | (a) 코퍼스 전체 유일성 → **(b) 쌍해소** | (a) 6/10 실패. 실패 4행은 선언 doc 안 1회였고 충돌은 동일 문구 재게재. 구 chunk_id 도 유일성 보증한 적 없음 → (b)가 구 포맷과 해상도 동일 |
| M9-2 | 선두 1문장 + 확장 + 상한 120자 | 게이트를 근거 가치의 대리로 씀. `01` 통과(청크 선두가 목록 번호) |
| M9-3 | 길이 단독 정렬 (M9-2b) | `01` 이 hits=9 로 선택됨(목록 번호 5청크). "가장 짧다" ≠ "가장 특징적". → **hit_docs 우선 정렬**로 교체 |

### 11-4. ver1 실측 계보 보전 확인 (2-5)

41스팬 전건 **구 청크 ID == 해석 청크(일치 41/41)** — 신 스니펫이 구 chunk_id 가 가리켰던 텍스트와
동일 대상임을 §10 통합표가 증명한다. M9-2·M9-3 폐기 규칙 기록은 삭제하지 않았다(§4B-1·§9-2).

### 11-5. verify_h6_inject.py 미실행 상태 커밋 (2-6 · M5)

`crawler/verify_h6_inject.py` 는 **미실행 상태로 커밋**한다. 실사용 검증은 다음 H-6 사용 시가 첫 기회다.
검증하려고 파괴 위험을 감수하는 것은 순서가 거꾸로다.

---

## §12. HOLES 3분류 (M9-4 · 3-2)

> H41·H42·H43·H44·H46 은 08-18 일괄 반영 블록 이후 등재분이라 그 블록에서 분류 밖이었다. 아래 표로 편입한다.

**닫힌 것 (19)** — H2 · H4 · H5 · H6 · H6b · H7 · H8 · H9 · H13 · H14 · H15 · H18 · H19 · H21 · H24 · H26 · H37 · H38 · H40

**범위 밖 (6)** — H1(팀·멘토 대기) · H3(외부 csv 대기) · H10 · H11 · H12(실전1 밖) · H43(용어 사전 발동 전 선결)

**열린 것 (21)** — H16 · H17 · H20 · H22 · H23 · H25 · H27 · H28 · H29 · H30 · H31 · H32 · H33 · H34 · H35 · H36 · H39 · H41 · H42 · H44 · H46

---

## §13. M9 최종 상태표 (M9-4 · 4-1)

| 항목 | 값 |
|---|---|
| 멀티턴 하니스 지문 | `246d07124d333c9b` (24/24) |
| 패널 하니스 지문 | `12619f9c100feb6e` (11/11) |
| 450셋 발동률 | 9건 / 2.0% · 착오송금 10.7% |
| verify_combos 조인 | MSDR 38 / DPIN 11 |
| 검증 스크립트 7종(A군) + 모듈 자기검사 4종(B군) | 전건 rc=0 |
| 동결 8종 sha256 | rag 84247b7c · eval 2d5b07a3 · chain a37b2a77 · e2e 3a9472ca · panel 34d5f435 · msdr 0115fe35 · chunks 6af9517b · doc_attach 183e460f |
| 원천 chunks.jsonl | 215행 / 6af9517b…9bd381 |
| HEAD / origin | `7255df89b934…` / `0001985130af…` |
| 이행 / 미이행 | **41 / 59** |
| combos_dpin hits 분포 | `{1:13}` (combos_dpin 한정) |

### 13-1. 다음 스프린트 인계 (4-2)

1. AC4·AC5·AC6 스코프 의존 제거 → QFORM_SCOPE 전환 (H39)
2. MSDR CSV 일괄 개정 (스팬 이행 + P16 + P18 + source_status)
3. H41 큐 처리 액션
4. H43 discriminator 재설계 — 용어 사전 발동 전 선결
5. 증거 모델 재설계 (K10 파생 — terms/prompts 증거 모델)
6. G13 해소 → DPIN 부스트 오라클 실험
7. H30 오분류 축 재정의
8. H35 평가셋 재측정

### 13-2. 미배정 잔여 2건 (4-3)

- 큐 구역 회색 처리 여부 (데모 전 액션)
- OOS `route=handoff` ↔ 큐폼 상담연결 통합

---

## §14. M10 반영 — 검증 종수 재분류 (M7) · 커밋 순서 (M8)

### 14-1. 검증 종수 재분류 (M7 · 1-1)

"검증 11종" 은 **검증 커버리지를 과대 표기**한다. 검증 스크립트(verify_*) 와 모듈 자기검사(rc=0 은 import 성립에 가깝다)를 구분한다.

| 군 | 종 | 스크립트 |
|---|---|---|
| **A군 — 검증 스크립트 7종** | 7 | verify_terms · verify_combos · verify_qform_multiturn · verify_qform_e2e · verify_qform_integration · verify_qform_panel · verify_docs |
| **B군 — 모듈 자기검사 4종** | 4 | qform_extract · qform_state · qform_config · span_tools |

B군을 빼지 않는다 — 분류만 한다. 이후 보고는 "검증 7종 + 자기검사 4종" 으로 표기한다.

### 14-2. 커밋 순서 위반 기록 (M8 · 0-3)

**docs 커밋이 tool·data 보다 선행했다.** K11 의 tool→data→docs 순서 위반.
그 결과 docs 가 서술하는 도구·데이터(verify_terms·verify_combos·verify_h6_inject·terms CSV·prompts CSV)가
미커밋 상태로 남았다. **사후 정리(도구·데이터 커밋)로 해소.**
