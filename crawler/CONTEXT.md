# CONTEXT — 예솜24·FAQ 확장 실행 세션 (2026-07-15 완료분)

> 목적: 이전 `context.md`(예솜24 챗봇 버튼트리 크롤 + FAQ 인벤토리 첨부 세션)에서 넘겨받은
> 산출물을 실제로 **레포에 반영하고 RAG/eval 파이프라인에 적용**한 실행 세션 기록.
> 이 문서 + `HOLES.md`(H13~H21) + `link_registry.json`만 보면 무엇을 실행했고
> 무엇이 남았는지 전부 파악된다. 기준 시각: 2026-07-15.

---

## 0. 전달받은 것 → 반영한 위치

`crawler/ref/`에 첨부된 5개 파일을 다음과 같이 처리했다(레포엔 `ref/` 자체가 남아있지 않음 — 정리 완료).

| 원본(ref/) | 처리 | 최종 위치 |
|---|---|---|
| `build_yesom_testset.py` | 이동 후 SSL·헤더 수정, 재실행 | `crawler/build_yesom_testset.py` |
| `faq_links.json` | 이동만 | `crawler/faq_links.json` |
| `testset_yesom.jsonl` | 폐기 후 스크립트 재실행으로 신규 생성(값 동일, 재현) | `crawler/data/testset_yesom.jsonl` |
| `testset_merged.jsonl` | 〃 | `crawler/data/testset_merged.jsonl` |
| `link_registry_merged.json` | `entries`(H7 보강분) + `faq_pages` 섹션을 기존 파일에 병합 후 폐기 | `crawler/link_registry.json` |

---

## 1. 스크립트 실행 중 발견한 실행 환경 문제 2건 (HOLES H19)

첨부받은 `build_yesom_testset.py`를 그대로 로컬(이 세션 환경)에서 돌리면 **답변노드 0건**이 나왔다.
원인은 스크립트 로직이 아니라 실행 환경 문제 두 가지가 겹친 것.

1. **SSL 인증서**: macOS python.org 배포판이 `cert.pem`을 설치하지 않아 `urllib`이 매 요청
   `CERTIFICATE_VERIFY_FAILED`로 실패(`curl`·`requests`는 자체 CA 번들을 써서 영향 없음 —
   그래서 기존 `crawler.py`는 `requests` 기반이라 이 문제를 겪지 않았음).
2. **WAF User-Agent 차단**: 인증서를 우회해도 `urllib` 기본 UA(`Python-urllib/3.x`)로 보낸
   POST는 KDIC WAF가 `DMZ WAF` 오류 HTML(EUC-KR)로 되돌림 → JSON 파싱 전 단계에서
   `ask()`의 예외 처리가 조용히 삼켜 모든 노드가 fallback-only로 보였음.

**조치**: 실행 시 `SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")` 지정 +
`build_yesom_testset.py`의 `ask()`에 `config.USER_AGENT`(기존 크롤러와 동일 식별 UA)와
`Referer: https://pubkbot.kdic.or.kr/chatbot.html?source=homepage` 헤더 추가.
이후 **98개 답변노드** 정상 수집 (첨부본과 `(gt_docs, business_function)` 멀티셋 100% 일치).

### 1-1. 팀원 로컬 실행이 5분 넘게 끝나지 않은 문제 (HOLES H21)

위 조치 후에도 다른 로컬 환경에서 스크립트가 **5분 넘게 완료되지 않아 Ctrl+C로 중단**되는
사례가 있었다. 단발 요청 진단(같은 헤더로 `ask()` 1회 호출)은 0.13초·200 정상 응답이라
네트워크·SSL·WAF 문제는 아니었음 — 원인은 `crawl()`의 **바깥 while 루프가 패스마다 큐
전체를 재조회**하는 설계였다. 이미 버튼을 확보해 더 알아낼 게 없는 노드까지 매 패스 다시
조회되어, 노드가 늘수록(6→28→53→82→98→98) 패스당 요청 수가 계속 커지고 누적 방문이
300회를 넘어갔다. 개별 요청이 빨라도 이게 쌓이면, 특히 네트워크 지연이 조금만 더해져도
5분 이상으로 불어날 수 있다.

**조치**: `to_visit`을 "이번 패스 신규 발견 노드" + "fallback만 본 노드(최대 3회 추가 재시도)"로
한정, 이미 버튼 확보한 노드는 이후 패스에서 제외. 진행률 print(`[예솜 크롤 pass N] …`)도 추가.
결과: **5패스·66초**에 동일한 98개 노드 완료(누적 방문 98회로 축소, 기존 대비 3배 이상 절감).

> 신규 로컬 환경에서 처음 돌릴 때 같은 증상이 재현되면 위 두 조치를 그대로 적용하면 된다.

---

## 2. 실행 순서 (실제로 돌린 커맨드, 재현용)

```bash
cd crawler

# (1) 예솜 테스트셋 재생성 — 환경변수로 SSL 우회, 헤더는 코드에 이미 반영됨
SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())") python3 build_yesom_testset.py
#  → data/testset_yesom.jsonl (98건) · data/yesom_qa.jsonl · data/testset_merged.jsonl (150건)

# (2) fins FAQ 5건 수집 재개 — config.py POLICY_DISALLOW에서 fins '/cm/bbs/' 제거(완료 반영됨)
python3 pipeline.py
#  → crawl_manifest.csv 37건 중 5건 upserted(FAQ) · 32건 skipped(불변) · 인덱스 재빌드(181청크)

# (3) 평가 — eval.py TESTSET을 testset_merged.jsonl로 전환(완료 반영됨)
python3 eval.py
#  → data/eval_report.md 재산출
```

---

## 3. 코드 변경 내역 (이번 세션)

- **`config.py`**: `POLICY_DISALLOW["fins.kdic.or.kr"]`를 `[r"^/cm/bbs/"]` → `[]`로 변경(주석에 07-15 근거 명기). `www.kdic.or.kr` 규칙은 무변경.
- **`eval.py`**: `TESTSET = "data/testset.jsonl"` → `"data/testset_merged.jsonl"`. 원본 `data/testset.jsonl`(52건) 자체는 무수정.
- **`build_yesom_testset.py`**: `from config import USER_AGENT` 추가, `ask()`에 `User-Agent`·`Referer` 헤더 추가. `crawl()`의 바깥 재조회 루프를 "신규 노드 + fallback 노드만" 방문하도록 재작성(H21) + 진행률 print 추가. SEEDS·gt_docs 매핑 로직은 무수정.
- **`link_registry.json`**: `entries` 6건을 `link_registry_merged.json` 버전(07-13 H7 완결분 — url 공란 2건 충전, xlsx 교차확인 note 보강)으로 교체. `faq_pages` 섹션 신규 추가(www 2 + fins 5, 전부 `in_corpus: true`로 갱신).

---

## 4. 현재 파이프라인 상태 (2026-07-15 실행 결과)

- **RAG 코퍼스**: 37건 매니페스트 중 32건 기존 유지(콘텐츠 불변 skip) + fins FAQ 5건 신규 upsert → **총 181청크**, `data/index/` 재빌드 완료.
- **평가셋**: `data/testset.jsonl`(원본 52, 불변) + `data/testset_yesom.jsonl`(예솜 98) = **`data/testset_merged.jsonl` 150건**(dedup 0). `eval.py`가 이 150건을 평가.
- **eval 결과** (`data/eval_report.md`):

  | mode | hit@1 | hit@3 | MRR |
  |---|---|---|---|
  | dense | 0.360 | 0.507 | 0.460 |
  | hybrid | 0.400 | 0.587 | 0.511 |

  - 대표 6문항 top-3 적중: **hybrid 5/6 · dense 5/6 → D1 판정 통과**
  - 오염체크(국내 보호한도 top-3 해외수치 혼입): **0건**
  - 유일 미적중: "착오송금 반환은 어떤 경우에 신청할 수 있나요?" (hybrid rank 미적중, dense rank 4) — H17(착오송금 37건 동일 타겟 쏠림)과 무관하지 않을 것으로 추정.

> **재현성 검증(완료)**: §2의 3단계를 이 세션에서 한 번 더 연속 실행해 문서대로 동작하는지 확인했다.
> 결과: 답변노드 98건·D1 판정(5/6)은 동일하게 재현됐으나, hybrid hit@1 0.400→0.393·hit@3 0.587→0.580·
> MRR 0.511→0.505로 소폭 변동(H20 — 질문 라벨 문구가 검색 쿼리 자체이기 때문). 판정 결론에는 영향 없음.

---

## 5. 열린 이슈 (HOLES.md 참조, 이번 세션에서 새로 닫지 않은 것)

| Hole | 내용 | 상태 |
|---|---|---|
| H16 | gt_docs 업무 대표문서 근사(예금보험금 서류 vs 미수령금 서류 경계 등) | 열림 — 사람 검토 필요 |
| H17 | 착오송금 37건이 대부분 동일 정답문서(`kmrsItrdAplyMthd`) → eval 표본 쏠림 | 열림 — 설계 판단 필요 |
| H20 | (신규) `crawl()`의 BFS 큐가 `set`이라 재실행마다 일부 질문 라벨 문구가 바뀜(의미·gt_docs는 불변) | 열림 — 급하지 않음, 재현성 원하면 `set`→순서보존 구조로 교체 |

H13~H15·H18·H19·H21은 이번 세션에서 해소 확인(HOLES.md 본문 참조).

---

## 6. 다음 단계 후보 (미착수)

- FAQ 상세페이지(특히 신규 수집된 fins 5건) 기반 Q-A를 평가셋에 반영(현재는 코퍼스 편입만 완료, 테스트셋 추가는 범위 밖).
- H16 gt_docs 경계 사람 확인, H17 착오송금 세부 타겟 축약 여부 결정.
- H20 재현성 개선(선택) — `crawl()` 큐 자료구조 교체.
