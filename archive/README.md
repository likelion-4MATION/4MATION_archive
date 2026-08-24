# archive — 은퇴한 스크립트 보관소

여기 있는 파일은 **더 이상 참조되지 않는다.** 지우지 않는 이유는 수치의 계보와
판정 방식의 변경 근거가 이 코드에 남아 있어서다. 되살릴 때는 아래 표의 "대체" 열을
먼저 읽고, 지금 정본이 같은 일을 하지 않는지 확인할 것.

`git mv` 로 옮겼으므로 `git log --follow <파일>` 로 원래 이력을 그대로 볼 수 있다.

**예외 하나** — `superseded/eval_doc_legacy.py` 는 `--follow` 가 끊긴다. 원 경로
`crawler/eval.py` 에 **같은 이름의 새 파일(통합 평가기)** 이 들어와서, 이동 커밋에
짝지을 삭제가 없어 git 이 rename 으로 인식하지 못한다(`A` 로 기록됨). 이 파일의
이력은 통합 커밋 이전 구간에서 봐야 한다:

```bash
git log --oneline -- crawler/eval.py           # 통합 커밋 이후/이전이 섞여 나온다
git log --oneline <통합커밋>^ -- crawler/eval.py  # 구세대 eval.py 만의 이력
```

---

## superseded/ — 통합으로 대체된 평가기 (2026-08-24)

6개 평가 스크립트를 `crawler/eval.py` 한 파일로 합쳤다. 서로 다른 디렉토리가
같은 기능의 다른 파일을 참조하던 상태를 끝내는 것이 목적이었다.

| 파일 | 원 경로 | 대체 | 은퇴 사유 |
|---|---|---|---|
| `eval_anchor_v3.py` | `crawler/` | `crawler/eval.py chunk` | **정본이었다.** 로직을 이름 변경 0건으로 통합 파일 §4 에 이식. 여기 사본은 등가성 회귀 테스트의 기준값 역할을 한다 — 지우면 `crawler/tests/test_eval_equivalence.py` 가 못 돈다 |
| `eval_anchor_span_multi.py` | `crawler/` | `crawler/eval.py span` | `gt_anchor_spans` 다중 span AND 판정. 외부 참조 0건이었다. 통합 파일 §5 |
| `eval_anchor_gold.py` | `crawler/` | `crawler/eval.py gold` | 앵커-host 판정 + Wilson CI · 등급 nDCG · McNemar. 참조 0건이었다. 통합 파일 §6 (통계 3종은 §2 로 올려 모든 서브커맨드가 쓴다) |
| `eval_doc_legacy.py` | `crawler/eval.py` | (없음) | 구세대 `parent_doc_id` 판정. `docs/handoff/eval_유상.md` §3 이 "폐기(참조용)"로 판정했고, 기본 평가셋 `data/testset_natural_400.jsonl` 이 디스크에 없어 **실행 불가**였다. 지표 함수 `first_hit_rank`·`_row`·`group_metrics` 만 통합 파일 §3 에 보존 |
| `eval_TF.py` | `crawler/` | (없음) | `eval_doc_legacy.py` 의 드리프트 포크. 6개 함수를 복제하고 `ANALYZE_MODE`·오류분석만 더한 상위집합이었다. 기본 평가셋 `data/router_trainset_v1.jsonl` 이 없어 실행 불가 |
| `eval_pair.py` | `crawler/` | (없음) | 원본 vs 자연어화 질문쌍 페어 평가. 기본 평가셋 `data/testset_natural.jsonl` 이 없어 실행 불가. `from eval import first_hit_rank, group_metrics` 를 쓰므로 되살릴 때 임포트를 통합 파일 기준으로 고쳐야 한다 |

### 되살리는 방법

```bash
# 1. 파일을 crawler/ 로 옮긴다
git mv archive/superseded/eval_pair.py crawler/eval_pair.py

# 2. 평가셋을 복구한다 — 없으면 실행되지 않는다
#    eval_pair : data/testset_natural.jsonl   (baseline_v1.lock 에 sha256 있음)
#    eval_TF   : data/router_trainset_v1.jsonl
#    doc_legacy: data/testset_natural_400.jsonl (baseline_v2.lock 에 sha256 있음)

# 3. 임포트를 통합 파일 기준으로 고친다
#    from eval import first_hit_rank, group_metrics   → 그대로 동작(§3 에 보존됨)
#    import eval_anchor_v3 as ev3                     → import eval as ev3
```

⚠ `superseded/eval_anchor_v3.py` 는 **옮기거나 지우지 말 것.** 등가성 회귀 테스트의
기준값이다. 통합 파일 §4 가 훼손됐는지 판별하는 유일한 대조군이다.

---

## eval_retired/ — 은퇴한 검색 실험 스크립트

원 경로 `crawler/archive_eval/`. 자체 `README.md` 에 각 스크립트의 실험 내용과
결론(채택/기각)이 정리돼 있으니 그것을 먼저 읽을 것. 전부 `import rag` 후
`rag.Searcher()` 를 직접 쓰는 단발 ablation 스크립트다.

되살릴 때 주의 — 이 파일들이 참조하는 `rag` 파라미터 기본값은 **그 시점 코퍼스와
한 세트**다(`crawler/rag.py` 주석: "이 값들은 181청크 코퍼스와 한 세트다").
지금 코퍼스에서 그대로 돌린 수치는 당시 리포트와 비교할 수 없다.

```bash
git mv archive/eval_retired/eval_mmr.py crawler/eval_mmr.py   # 되살리기
```

---

## label_retired/ — 은퇴한 라벨링 파이프라인

원 경로 `archive_label/`. 앵커 라벨링 초기 파이프라인(`judge_label.py`,
`eval_anchor.py`, `eval_anchor_v3.py` 의 구 사본)과 그 중간 산출물
(`data/gt_*.jsonl`, `router_trainset_*.jsonl`, `*_ids.txt`)이다.

여기 있는 `eval_anchor_v3.py` 는 `crawler/` 정본의 **오래된 사본**이다.
`superseded/eval_anchor_v3.py` 와 혼동하지 말 것 — 대조군은 그쪽이다.

현행 라벨링 도구는 `crawler/promote_gt_anchors.py` · `crawler/fill_anchors.py` ·
`crawler/audit_anchors.py` 이며, 정답셋 정본은 `final_testset/` 아래에 있다
(`docs/handoff/eval_유상.md` §2 참조).
