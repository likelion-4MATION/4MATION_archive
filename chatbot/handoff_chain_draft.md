# handoff — chain.py 인수인계 초안 (체인 담당: 규남)

> 밤1(07-22) CC 작성. **answer()는 초안이며 동결 아님 — 동결 서명은 사람.** 근거 실측은 `exp/night1_report.md` 참조.

## 1. 계약 (crawler/DECISIONS.md 07-21 초안 기준)

```python
answer(query: str, k: int = 3) -> {
    "text": str | None,        # 생성 답변 (HCX 실패 시 None + _meta.error)
    "sources": [{"title", "url", "doc_id"}],   # top-3 parent_doc 중복 제거, 순서=랭크
    "confidence": float,       # 표시용 dense 코사인 top1 (아래 §3)
    "route": "rag"|"link"|"reject",            # 초안은 항상 "rag" (아래 §4 TODO)
    # ── 부가(계약 외 추가 — 축소 아님) ──
    "checks": {...},           # answer_checks 플래그 (차단하지 않음)
    "_meta": {...},            # model·hcx_status·latency_ms·error·k
}
```

- 4필드 축소 없음 보장·추가만 가능. **URL·전화번호는 모델 생성 금지, sources·컨텍스트에서만 조립**(전야 Q3 날조 실측).
- 검색은 `crawler/rag.py` Searcher(계약 동결) hybrid k=3 소비만. `_score`는 RRF — 절대 임계값 금지, 표기만.

## 2. 프롬프트 v2 — 5규칙과 각각의 실측 근거

| 규칙 | 근거 실측 |
|---|---|
| 1. 문서에 없으면 "확인되지 않는 내용" 답변 | 전야 Q3: 검색 적중에도 파인·어카운트인포 등 컨텍스트 밖 지식으로 답변 |
| 2. URL·전화번호는 문서 것만, 생성 금지 | 전야 Q3: fss.or.kr 출처 날조 / 맨몸 가짜 kdic URL |
| 3. 문장 끝 [출처N] 강제 | 전야 Q3·Q6: 출처 번호 미표기 |
| 4. 과거형·조건부 한정 유지 | 전야 Q1 롤렛: "보호한도가 5천만원인 **과거에는**"의 한정 탈락 → 현재형 오답 |
| 5. 금액 단위 환산 금지 | **밤1 발견**: 전야 Q6가 "100백만원"(=1억)을 "1,000만원"으로 오환산 |

관통 실측(밤1 3콜): 정상 문항 품질 유지 · FDIC 트랩 생성단 거절 성공(1/1) · **롤렛(보호한도)은 프롬프트로 안 고쳐짐**(3회 관측: 5천만→1억→5천만) — 검색 미적중은 생성단 방어 밖.

## 3. confidence — 표시용, 정책 금지 (멘토링 Q12)

- 정의: dense 코사인 top1 (`_confidence()`). 밤1 T2 실측에서 3후보 중 최강(AUC merged .716 / natural .562)이나 **분포 중첩 — 임계값 분기 불가**.
- **한계 실측**: 보호한도 미적중 문항이 .7734(정상군 수준) — "질문-문서 유사도"이지 정답 확신이 아님. UI 표기 시 "관련 문서 유사도" 류 문구 권장.

## 4. route 훅 — TODO(사람 결정 대기)

- 현재 항상 `"rag"`. **검색 신호 단독 라우팅은 밤1 실측상 불가**: reject 기대 트랩 11문항도 bf 다수결 10/11 충족, dense 대역 겹침(해외지점 질문 .841 > 정상 최저 .662).
- 채택 권고안: **질문 분류 단계(소관밖/모호/정상) 선행** — 트랩셋(`exp/trapset_v0.jsonl`, 검수 전) 기반 설계.
- 보조 신호(분류 뒤 강화용): ① top-3 bf 만장일치(정상 6/6 vs 트랩 5/20) ② 질문 의도 bf ≠ top-3 다수 bf(보호한도 미적중 시그니처 — 의도 bf는 분류가 선행돼야 산출 가능).

## 5. answer_checks 훅 — 플래그만, 차단 없음

- `run_all(text, hits, allow_context_urls=False)` — **확정(사람 결정)**: sources 목록에 없는 URL은 본문 유래여도 플래그. 전야 Q5(ccrs.or.kr, 본문 유래) 케이스는 이 기준으로는 걸림 — 날조 방지를 엄격 쪽으로 확정.
- 소급 성능(전야 6행, allow_context_urls=True 기준 참양성 6·경계 1·거짓양성 0)은 **재기준(False)으로 재판정 필요** — Q5가 새로 플래그될 것으로 예상됨. 상세는 night1_report T4, 재판정은 밤2 이전 1회 필요.
- **미결 버그**: 거절 응답("확인되지 않는 내용입니다")에 [출처] 없음 → citations 플래그 오탐. 거절 문구 패턴 예외 필요.

## 6. 미결 목록 (동결 대기)

1. route 활성화 — 질문 분류 설계·트랩셋 검수 후 (아침 결정 ②③)
2. confidence 정의 공식 채택 + UI 표기 문구 (아침 결정 ①)
3. `checks`·`_meta` 부가 필드의 계약 공식화 여부 (아침 결정 ④)
4. ~~allow_context_urls 확정~~ → **False로 확정(07-22)** · 거절 응답 검증 예외는 여전히 미결 (§5)
5. LLM-judge 2차 검증 층 (answer_checks.py 말미 설계 메모 — 콜 예산 확정 후)
6. "link" route 미구현 — 타기관 안내 URL 사전 필요(트랩 '타기관 소관' 5문항이 후보 시드)

## 실행

```
python3 chatbot/chain.py            # 관통 3콜 데모 (예산 가드 10콜)
python3 chatbot/answer_checks.py    # 전야 6행 소급 판정표 (0콜)
python3 exp/harness.py run|probe    # 검색 하네스 (0콜)
```
