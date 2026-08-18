# bf_map 파이프라인 검증 리포트

- 생성: 2026-08-18T05:21:19.422201+00:00
- 라우터: `../router_moai_embedding_model`
- MSP 임계: 0.7 (잠정 — θ 확정은 후속 단계)

## 검증 항목 (문서 6절)

| # | 확인 | 결과 |
|---|---|---|
| V1 | 라벨 매핑이 6개 BF 명칭과 일치 | 확인 |
| V2 | 질문 문장 추출 | 108건 성공 |
| V3 | 추출 실패 청크 | 0건 |
| V4 | qhash 충돌 (다른 질문 → 같은 hash) | 0건 |
| V5 | 대상 청크 수 (is_board) | 108 / 전체 181 |
| — | 고유 질문 수 | 96 (레코드 108 · 중복 게재 12) |
| V6 | 문서 내 BF가 갈리는 문서 | 5건 (**정상 동작**) |
| V7 | null 비율 | 3/108 = 2.8% |

## V5 — 대상 청크 내역

| doc_id | 청크 | page_type |
|---|---:|---|
| `kdic-fins-cm-bbs-selectFaqNramtAply` | 38 | FAQ — 미수령금통합신청 |
| `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn` | 17 | 예금자보호제도 FAQ |
| `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply` | 12 | FAQ — 착오송금 (2페이지, ~15건) |
| `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn` | 12 | 은닉재산신고 FAQ |
| `kdic-fins-cm-bbs-selectFaqCncmPrptDclr` | 12 | FAQ — 은닉재산신고 |
| `kdic-fins-cm-bbs-selectFaqTop10` | 10 | FAQ TOP10 — 테스트셋 v0 시드 |
| `kdic-fins-cm-bbs-selectFaqLbltInfoInq` | 7 | FAQ — 채무정보조회 |

## V6 — 문서별 BF 분포 (라우터 산출)

| doc_id | 청크 | BF 분포 |
|---|---:|---|
| `kdic-www-sp-dpstrprot-ProtSystFaq-selectScrn` | 17 | 예금자보호제도 16 · 예금보험금 안내 1 |
| `kdic-fins-cm-bbs-selectFaqNramtAply` | 38 | 예금보험금 안내 29 · 예금자보호제도 5 · 착오송금 반환 신청 2 · null 2 |
| `kdic-fins-cm-bbs-selectFaqMsdrGvbkAply` | 12 | 착오송금 반환 신청 10 · 고객 미수령금 신청 1 · 예금보험금 안내 1 |
| `kdic-fins-cm-bbs-selectFaqLbltInfoInq` | 7 | 착오송금 반환 신청 3 · 고객 미수령금 신청 2 · 채무조정 안내 1 · null 1 |
| `kdic-www-sp-sprtfund-SprtFndCncmDclrFaq-selectScrn` | 12 | 은닉재산 신고 12 |
| `kdic-fins-cm-bbs-selectFaqCncmPrptDclr` | 12 | 은닉재산 신고 12 |
| `kdic-fins-cm-bbs-selectFaqTop10` | 10 | 착오송금 반환 신청 9 · 고객 미수령금 신청 1 |
