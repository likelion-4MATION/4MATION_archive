> **통합됨** — 이 문서의 내용은 `docs/eval_anchor_규남.md`(라운드1~4 통합본)에 흡수됐다.
> 최신 지표·결정은 그쪽 0절을 볼 것. 이 파일은 당시 기록으로만 보존한다.

# 세션 핸드오프 (2026-08-20, feature/kokopas)

> 이어서 볼 것: `DECISIONS.md`의 "P0-1"·"P0-2" 항목(이 문서 이전 판단 근거) +
> 이 문서(P0-2 적용 결과 · P0-3 GT 재매핑 · 다음 결정 지점).

## 지금 워킹트리 상태 (P0-2 적용 완료)

- `crawler/chunk.py`: (`TABLE_GAP_MAX` 12줄 표 흡수 방식).
  stash의 "OVERLAP 200 + 표 병합" 버전은 **미사용**(폐기 아님, 그냥 안 씀).
- `crawler/rag.py`: (anchor 임베딩, `[업무][페이지주제] 제목` 접두사)으로 되돌림 — 사람 지정. `git diff`로 확인 가능한 유일한
  국소 변경(diff는 이 파일 하단에 남아 있음, `MM` 상태).
  - **주의**: anc의 `SIBLING_BOOST` 로직은 사라진 상태(anc에 없었음, 의도한 대로).
    `DECISIONS.md` P0-1이 지적한 "sibling-boost 파라미터를 stash값(0.10/5/cap5)으로
    되돌릴지" 질문은 **이번 P0-2 적용으로 무의미해짐** — anc 채택으로 그 로직 자체가 없음.
- `crawler/faq_bf_map.py`: -(rag.py의 import 의존성, 신규 추가 `A` 상태).
- 라우터 체크포인트(`router_moai_embedding_model`, 2.4GB)는 로컬에 없음 → 항상
  키워드 분류 폴백으로 동작(정상, 크래시 아님). 재현 시 `[router] 로드 실패(OSError)`
  로그가 매번 뜨는 게 정상.
- 인덱스는 181청크 기준으로 `pipeline.py --use-cache --rebuild` 완료.

## 오늘 한 일 — P0-3: GT 재매핑 (완료, 신뢰 가능한 수치 확보)

**문제였던 것**: `gt_natural450_v9_dupfix2.jsonl`은 kokopas 계열(옛 215청크) `chunk_id` 기준으로
라벨링된 GT인데, 이걸 새 181청크(anc) corpus로 그대로 채점하면 `chunk_id` 불일치로 인한
가짜 미적중이 섞여 수치를 못 믿는 상태였음(`eval_anchor_v3.py` 최초 실행 결과 Hit@5=.741,
anc 자체 브랜치 수치 .831대와 괴리).

**시도했다가 안 한 것**: `promote_gt_anchors.py`라는 재라벨링 스크립트를 찾았으나 로컬에도
anc 브랜치에도 존재하지 않음(과거 계획서가 참조했지만 실물 없음) — 새로 안 짬.

**실제로 한 것**: 기존 `crawler/data/build_gt_dupfix.py`(이미 있던 스크립트, anchor_span
verbatim 매칭으로 gt_chunk_ids에 중복 게재 청크를 보강하는 결정론적 로직)를 **새 181청크
corpus 대상으로 그대로 재실행**. 이 스크립트는 old gold id가 새 corpus에 존재하는지 여부와
무관하게 동작(그냥 `chunk["text"]`에 `gt_anchor_span`이 verbatim으로 들어있는 청크를
찾아 리스트에 추가) — 그래서 corpus 세대가 바뀌어도 재사용 가능했음.

- 재실행 전 진단: answerable 448건 중 **6건**만 새 corpus에 유효 chunk_id가 0개(완전 깨짐).
  나머지 442건은 옛 chunk_id 포맷이 anc 재청킹에도 대부분 그대로 살아있었음(표가 없는 문서는
  `TABLE_GAP_MAX` 병합의 영향을 안 받으므로).
- `build_gt_dupfix.py` 재실행 → 89/450건 `gt_chunk_ids` 갱신, 6건 전부 복구(zero-valid-gold
  0건으로 확인).
- `HF_HUB_OFFLINE=1` 필요(SSL 인증서 검증 실패로 huggingface.co 접근 실패 — 로컬 캐시 모델은
  이미 있으므로 오프라인 강제로 우회. `PYTHONIOENCODING=utf-8`도 같이 줘야 함, 안 그러면
  router 폴백 로그의 em dash(—) 출력에서 `cp949` 인코딩 에러로 죽음 — Windows 콘솔 이슈,
  코드 버그 아님).
- **재평가 결과 (`eval_anchor_v3_report.md`, hybrid_bf, GT=`gt_natural450_v9_dupfix2.jsonl`,
  181청크)**:

| Hit@1 | Hit@3 | Hit@5 | Hit@10 | Hit@30 | MRR@10 |
|---:|---:|---:|---:|---:|---:|
| 0.469 | 0.717 | **0.812** | 0.884 | 0.933 | 0.609 |

  Hit@5 .741 → **.812**로 상승, anc 자체 수치(.831대)와 근접한 신뢰 가능 범위로 들어옴.
  n_evaluated=448, n_excluded(answerable=false)=2, n_inconsistent=0.

## 다음 세션이 판단할 것

1. **.812를 현재 baseline으로 확정할지, v2(패러프레이즈) 보강까지 갈지.**
   `build_gt_dupfix_v2.py`(숫자앵커+임베딩 유사도 기반 비-verbatim 중복 탐지)는 **그대로는
   못 씀** — 코드가 `gold`(옛 chunk_id)로 `idx_of`(새 emb.npy 인덱스)를 조회하는데, 옛 chunk_id
   가 새 인덱스에 없으면 `gold_embs`가 비어 그 문항은 조용히 스킵됨. 쓰려면 조회 부분을
   "새로 갱신된 gt_chunk_ids(1단계 통과분)로 embedding 조회"하도록 한 줄 고쳐야 함 — 아직 안 함.
2. **DECISIONS.md에 이번 재매핑 근거·수치를 정식 기록할지.** 지금은 이 핸드오프 파일에만 있음.
3. `sibling-boost` 관련 P0-1의 미결 질문은 위에서 설명한 대로 **anc 채택으로 자동 해소**됨 —
   재확인 불필요.
4. 워킹트리에 이전 세션(또는 anc 체크아웃)에서 남은 미검토 산출물들이 있음(이번 세션에서
   내용 확인 안 함, 존재만 확인):
   - `crawler/p2_parent_expand.py` — parent 인접 청크 확장 실험용 신규 진단 스크립트(GT/corpus
     비수정, 헬퍼만 재사용한다고 docstring에 명시).
   - `crawler/data/reembed.py` — 청크 재파싱 없이 `chunk_embed_text()`만 최신판으로 바꿔
     임베딩·인덱스만 재계산하는 유틸.
   - `crawler/data/eval_report_B_anc_181chunks.md`, `eval_report_450_ov0_gtv9.md`,
     `label_eval_audit_report.md`, `dupfix_v2_ambiguous.md`, `anchor_labeling_handoff.md`,
     `testset_natural_450.jsonl` — 전부 untracked, 이번 세션에서 내용 확인·사용 안 함.
   커밋 전에 이 파일들이 이번 브랜치에 필요한지 스코프 정리 필요(전부 add 하지 말 것).

## 커밋 안 함

이번 세션에서 스테이징/커밋 안 함 — `git status` 그대로 유지. 재실행 재현 순서:
`cd crawler/data && python build_gt_dupfix.py` → `cd .. && HF_HUB_OFFLINE=1 PYTHONIOENCODING=utf-8
python eval_anchor_v3.py --gt data/gt_natural450_v9_dupfix2.jsonl --mode hybrid_bf`.
