# archive_eval — 은퇴한 검색 평가 스크립트

목업 단계 진입(2026-08-20)에 맞춰 `crawler/` 루트를 정리하면서 옮긴 파일들.
**지운 게 아니라 옮긴 것**이므로 필요하면 그대로 복원해서 돌릴 수 있다.
다만 대부분은 `rag.py`가 그때 이후로 바뀌었으니, 되살릴 땐 상수·시그니처를 먼저 맞춰야 한다.

## 현역 평가기

| 용도 | 파일 |
|---|---|
| 청크 단위 검색 평가(현행) | `../eval_anchor_v3.py` — `admin/runner.py`가 `import eval_anchor_v3`로 직접 호출 |
| MODES 일괄 비교 · 오염 검사 · 문서 단위 평가 | `../eval.py`, `../eval_TF.py` |
| 원본↔변형 질문쌍 페어 평가 | `../eval_pair.py` |
| 청킹 파라미터 스윕 | `../eval_overlap.py`, `../eval_tablefix.py`, `../eval_docinput.py` |
| 라우터 · FACET_BOOST 스윕 | `../eval_router_facet.py` |

---

## 1. v3에 흡수된 구버전 (2)

| 파일 | 내용 | 후속 |
|---|---|---|
| `eval_anchor.py` | 앵커(청크) 단위 eval 1세대. gold BF 주입 + soft 경로 복제. 북극성 recall@10 | `eval_anchor_v3.py` |
| `eval_anchor_1.py` | 위의 파생본(거의 동일) | `eval_anchor_v3.py` |

`eval_anchor_v3.py`가 이 둘의 기능을 포함하면서 `chunk_id`/`anchor` 이중 채점,
`chunk_relation`(any/all) 기반 gold 관계 처리, recall@3/5/10/30/50, MRR@10,
오류 분석표, 리포트 생성까지 갖췄다. 산출 리포트도 `data/eval_anchor_report.md` →
`data/eval_anchor_v3_report.md` 계열로 승계됨.

## 2. 일회성 튜닝 실험 (9)

결론이 이미 `rag.py` 상수와 `data/*.md` 리포트에 박제되어, 스크립트를 다시 돌릴 이유가 없는 것들.

| 파일 | 물었던 질문 | 결론이 남은 곳 |
|---|---|---|
| `eval_rrf_tune.py` | 가중 RRF α × 소프트부스트 β 그리드 | `rag.py: RRF_ALPHA = 0.65`, `BF_BOOST = 0.06` · `data/tune_v2_summary.md` |
| `eval_rrfk.py` | RRF 상수 k 스윕(5/10/20/40/60) | `rag.py: RRF_K = 4` (낮은 k 채택) |
| `eval_softboost.py` | 업무 신호를 하드필터 대신 RRF 가산으로 | `rag.py: BF_MODE = "soft"` — 소프트부스트 채택 |
| `eval_facet.py` | 서브인텐트 패싯 부스트로 업무 내부 형제문서 구분 | `rag.py: FACET_BOOST = 0.05` (이후 `eval_router_facet.py`가 재튜닝 승계) |
| `eval_cap.py` | parent_doc당 청크 수 cap A/B (몬스터 문서 슬롯 독점) | doc-cap 채택 → `rag.py` · 후속 스윕은 `tune_cap_k.py`, `data/cap_k_430.md` / `cap_k_355.md` |
| `eval_mmr.py` | 팀원 구성(MMR-only + bge-m3, 정확도 95%) 재현 검증 | **기각**. hit@3 기준 hybrid_bf 우위 · 95%는 k를 키운 hit@10이었음 |
| `eval_rerank.py` | 로컬 cross-encoder 리랭킹 | **보류**. 진단은 `diag_rerank.py`로, 본격 실험은 `rerank_colab/`로 이관 |
| `eval_embedinput.py` | 문서측 임베딩 입력에 breadcrumb·sub_category 주입 | 후속 `eval_docinput.py`(현역)가 승계 · `data/eval_docinput_report.md` |
| `eval_exclude.py` | 문서 제외 ablation — `selectFaqNramtAply`(38청크 블랙홀) 상한선 | 진단용. 해법은 삭제가 아니라 Q&A 단위 재청킹으로 결론 |

## 3. 백업 잔재 (4)

`eval.py.bak` · `eval.py.bak_bf` · `eval_TF.py.bak_cap` · `eval_TF.py.bak_pre`

`.bak` 파일 방식의 수동 백업. git 히스토리로 대체된다.

---

## 복원 방법

```bash
cd crawler
mv archive_eval/eval_mmr.py .
```

주의: 이 스크립트들은 대부분 `rag.py`의 당시 상수(`RRF_K=60`, `BF_MODE="hard"`,
`ko-sroberta` 임베딩 등)와 `data/testset_natural_400.jsonl` 세대 평가셋을 전제로 한다.
현행 `final_testset/` 세대(450/430 · 505/355)에 그대로 물리지 않으니,
되살릴 땐 `TESTSET` 경로와 `rag` 함수 시그니처를 먼저 확인할 것.
