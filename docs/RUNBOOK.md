# RUNBOOK — 5개 축 실행 명령어 모음

`feature/merge` 기준. 다섯 축(라우팅 · RAG · 크롤링+청킹 · 관리자 UI · 챗봇)과
평가·검증을 실행하는 명령어만 모았다. 설계 근거는 각 모듈 docstring과
`docs/handoff/eval_유상.md` · `docs/router_checkpoint.md` 를 본다.

> **경로 규칙** — `crawler/` 스크립트는 전부 **cwd 상대경로**(`data/...`)를 쓴다.
> 반드시 `cd crawler` 후 실행한다. `chatbot/` · `admin/` 은 리포 루트 기준이거나
> 스스로 `sys.path` 를 잡으므로 아래 표기대로 쓴다.

---

## 0. 공통 준비

```bash
# 검색 스택 (faiss · numpy · rank_bm25 · sentence-transformers · kiwi)
pip install -r crawler/requirements.txt

# 관리자 콘솔 (FastAPI · uvicorn)
pip install -r admin/requirements.txt

# HCX 키 — .env (루트). chatbot/* 가 load_dotenv 로 읽는다
#   CLOVA_API_KEY · CLOVA_API_URL · CLOVA_MODEL
cp .env.example .env && $EDITOR .env
```

`admin` 과 `chatbot` 은 **같은 파이썬 환경**에 깔아야 한다. 콘솔의 `settings.apply_runtime()`
이 `rag` · `chain` · `qform_config` 모듈 상수에 값을 주입하는 방식이라, 환경이 갈리면
파라미터 조절이 챗봇에 닿지 않는다(`admin/runner.py:_need_stack`).

---

## 1. 라우팅 — MoAI 체크포인트 (로컬 실행)

**라우터는 로컬 디렉토리에서 돈다.** 가중치 `pytorch_model.bin` 2.38GB 는 git 에 없어서
(GitHub 단일 파일 100MB 상한) HF 프라이빗 repo `us788/moai_yebo_ft` 를 배포 경로로만 쓴다.
클론 직후 **한 번** 내려받아 `router_moai_embedding_model/` 에 두면 그 뒤로는 네트워크를
타지 않는다 — `router_source.resolve()` 가 로컬을 먼저 보고, 매니페스트의 9개 파일이 전부
있고 크기가 맞으면 로컬 경로를 돌려준다.

```bash
# ① 1회만 — HF repo → 레포 안 router_moai_embedding_model/
pip install "huggingface-hub>=0.23"
export HF_TOKEN=hf_...                        # read 권한이면 충분 (프라이빗 repo)
# 또는: huggingface-cli login

python3 scripts/download_router_hf.py             # 멱등 — 크기 맞는 파일은 건너뜀
python3 scripts/download_router_hf.py --dry-run    # 받을 목록만
python3 scripts/download_router_hf.py --verify-sha  # 받은 뒤 sha256 전수 검증

# ② 확인 — "로컬 상태: 사용 가능" + resolve() 가 로컬 경로를 가리키면 끝
python3 crawler/router_source.py
python3 crawler/router_source.py --verify          # sha256 전수(2.38GB 읽음, 느림)

# ③ 이후 실행 — 인자·환경변수 없이 그냥 돈다. HF 접속 0
cd crawler && python -c "
import rag
print(rag.ROUTER_PATH)                 # 로컬 절대경로
print(rag.classify_query_bf('착오송금 반환 신청 구비서류'))   # (업무, MSP)
"
```

받아 놓은 뒤 오프라인으로 강제하려면 `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` 을 붙인다
(`chatbot/*` 은 이미 스스로 그렇게 설정한다). 로컬이 완전하면 이 상태에서도 라우터가 뜬다.

**해석 순서** — `ROUTER_PATH`(env, 검증 없이 그대로) → **로컬 디렉토리(크기 일치)** →
`ROUTER_HF_REPO`/매니페스트 `hf_repo` → `None`(키워드 분류 폴백).
환경변수는 **다른 체크포인트로 A/B 할 때만** 쓴다. 평상시엔 건드리지 않는다.

```bash
export ROUTER_PATH=/path/to/other_ckpt    # 실험 체크포인트로 갈아끼울 때만

# 팀에 올리기 (write 토큰 필요, 체크포인트를 가진 사람이 1회)
HF_TOKEN=hf_... python3 scripts/upload_router_hf.py
python3 scripts/upload_router_hf.py --dry-run
```

라우터를 못 받아도 검색은 죽지 않는다 — `rag.get_router()` 가 실패를 삼키고
`classify_query_bf_keyword()` 로 폴백한다(콘솔에 `[router] 로드 실패` 1줄).
대신 업무 분류 기권률이 올라가 정확도가 떨어지므로 데모 전에는 ②로 확인한다.

**라우터를 쓰는 곳**

```bash
cd crawler

# 질의측 — 라우터 예측을 오프라인 1회로 굳혀 실험 캐시로 쓴다
python predict_query_bf.py --gt data/gt_schema_v6.jsonl --out data/query_bf_router.jsonl
python predict_query_bf.py --gt ... --router ../router_moai_embedding_model

# 문서측 — FAQ 청크 BF 재태깅 → data/bf_map.jsonl (chunks.jsonl 은 고치지 않는다)
python faq_bf_map.py --dry-run                                  # 추출·qhash 검증만(라우터 불필요)
python faq_bf_map.py --router ../router_moai_embedding_model
python faq_bf_map.py --router ../router_moai_embedding_model --msp 0.7
```

---

## 2. RAG — BGE-m3-ko 인덱스

임베딩은 `dragonkue/BGE-m3-ko`(1024d)를 sentence-transformers가 런타임에
HF에서 받아 `~/.cache/huggingface` 에 캐시한다. 별도 다운로드 명령이 없다.

```bash
# 인덱스 재생성 (chunks.jsonl → emb.npy · faiss.index · bm25.pkl · chunk_meta.jsonl)
cd crawler && python pipeline.py --manifest crawl_manifest.csv --use-cache --rebuild

# 인덱스·코퍼스 정합성 검증 (실패 시 exit 1)
cd crawler && python verify_integrity.py

# 검색 캐시 고정 — 450문항 × k=30 → data/retrieved_top30.jsonl (eval gold 입력)
cd crawler && python cache_retrieval.py
cd crawler && python cache_retrieval.py data/index_eval data/retrieved_ab.jsonl   # A/B용

# 검색 단발 확인 (rag.py 는 CLI 없음 — 라이브러리다)
cd crawler && python -c "
import rag
s = rag.Searcher()
for h in s.search('착오송금 반환 신청 구비서류', k=5, mode='hybrid_bf'):
    print(h['chunk_id'], h['page_title'])
"
```

`mode` 는 `dense` · `sparse` · `hybrid` · `hybrid_bf` 4종. 서비스 경로는 `hybrid_bf`.

---

## 3. 크롤링 + 청킹

원 저자가 정한 실행 순서: `run_crawl.py → parser.py → fetch_attachments.py → link_files.py → chunk.py`.
`build_dataset.py` 가 이 순서를 그대로 감싼 배치 래퍼다.

```bash
# 매니페스트 생성 (필수 CSV + 분석 XLSX 병합)
cd crawler && python build_manifest.py kdic_필수페이지_URL매핑.csv \
                                       분석필요태깅_포함여부분석.xlsx \
                                       -o crawl_manifest.csv

# 전량 수집만 — data/raw/*.html · data/meta/*.json
cd crawler && python run_crawl.py --manifest crawl_manifest.csv
cd crawler && python run_crawl.py --manifest crawl_manifest.csv --limit 3   # 스모크

# 데이터셋 배치 빌드 (parse → 첨부 다운로드 → 링크 → 청킹)
cd crawler && python build_dataset.py              # data/raw 캐시 사용
cd crawler && python build_dataset.py --crawl      # 라이브 크롤부터 전체
cd crawler && python build_dataset.py --no-fetch   # 첨부 다운로드 생략(오프라인)

# 단계별로 돌리기
cd crawler && python parser.py             # raw+meta → data/parsed/*.json
cd crawler && python fetch_attachments.py  # onclick 첨부 실다운로드 → data/files/
cd crawler && python link_files.py         # manifest ⋈ parsed → local_path stamp
cd crawler && python chunk.py              # parsed → data/chunks.jsonl + doc_attachments.json

# 수집→청킹→인덱싱 원자 파이프라인 (content_hash 불변이면 스킵)
cd crawler && python pipeline.py --manifest crawl_manifest.csv              # 라이브 재수집
cd crawler && python pipeline.py --manifest crawl_manifest.csv --use-cache  # 무네트워크
cd crawler && python pipeline.py --manifest crawl_manifest.csv --rebuild    # 인덱스 초기화 후 전량

# 첫 빌드 권장 순서
cd crawler && python build_dataset.py --crawl \
  && python pipeline.py --manifest crawl_manifest.csv --use-cache --rebuild
```

청킹 파라미터(`CHUNK_SIZE` · `OVERLAP` · `MIN_CHUNK` · `TABLE_GAP_MAX`)는
`chunk.py` 를 고치는 대신 **관리자 콘솔이 주입**한다(§4). `OVERLAP=0` 은 겹침 없음이
아니라 직전 조각 통째 복제로 동작하므로 러너가 1로 클램프한다(`runner.clamp_overlap`).

---

## 4. 관리자 UI — eval.py + rag.py 파라미터 조절 + 청킹 연결

```bash
export KDIC_REPO=$PWD            # 리포 루트 (기본값: admin/ 상위)
cd admin && uvicorn main:app --reload --port 8600
# → http://localhost:8600
```

콘솔 버튼이 실제로 돌리는 것은 `admin/runner.py` 다. 서브프로세스로 직접 실행할 수도 있다:

```bash
cd admin

# 평가만 — 샌드박스 인덱스(data/index_eval)에서 돌리고 지운다
python runner.py --mode eval    --config '{"CHUNK_SIZE":800,"OVERLAP":100,"MIN_CHUNK":60,"TABLE_KEEP":true,"TABLE_GAP_MAX":12}'

# 재빌드 — 청킹 상수 주입 후 pipeline.main() 호출. 산출물 백업·복원 포함
python runner.py --mode rebuild --config '{"CHUNK_SIZE":800,"OVERLAP":100}'
python runner.py --mode rebuild --config '{...}' --recrawl     # 홈페이지 재접속

# 재검증 — 서비스 인덱스를 그대로 평가(읽기 전용)
python runner.py --mode verify  --config '{}'

# 첨부 실파일만 다시 받아 청크 메타에 연결
python runner.py --mode files   --config '{}'
```

**연결 지도**

| 콘솔 탭 | 주입 대상 | 주입 시점 |
|---|---|---|
| ① 답변 품질 · ② 속도 | `chatbot/chain.py` (`GEN_PARAMS` · `CALL_BUDGET`) | `settings.apply_runtime()` — 저장 즉시 |
| ③ 되묻기 | `chatbot/qform_config.py` | `settings.apply_runtime()` — 저장 즉시 |
| ⑥ 고급 (검색 5축 + `BF_MODE` · `QBF_MSP_MIN`) | `crawler/rag.py` | `settings.apply_runtime()` — 저장 즉시 |
| ⑦ 문서 처리 | `crawler/chunk.py` | `runner.inject()` — 재빌드 때만 |
| 지표 | `crawler/eval.py` `evaluate_retrieval()` | `runner.run_eval()` |

평가 직전에 `apply_search_settings()` 가 저장된 검색 설정을 `rag` 에 주입한다.
이게 빠지면 콘솔에서 무엇을 바꿔도 측정은 `rag.py` 파일 기본값으로 나간다.

---

## 5. 챗봇 — HCX LLM 호출

```bash
# 데모 UI (Streamlit) — 큐폼 E2E 배선
streamlit run chatbot/app.py

# answer() 계약 관통 3문항 (정상·트랩·롤렛)
python3 chatbot/chain.py

# 분류만 1건 (1~2콜)
python3 chatbot/chain.py cls "예금보험금 지급 한도가 얼마인가요?"
python3 chatbot/chain.py smoke      # 분류 스모크 3문항
python3 chatbot/chain.py clsdemo    # 정상 6문항 분류만
python3 chatbot/chain.py e2e        # 트랩셋 20문항 E2E → exp/route_e2e_results.jsonl

# HCX 최소 호출 확인
python3 chatbot/smoke_hcx.py

# 맨몸 HCX vs RAG(top-3) 대조 데모 (프로덕션 아님, 관측용)
python3 chatbot/rag_hcx.py single "착오송금 반환 신청은 어떻게 하나요?"
python3 chatbot/rag_hcx.py batch    # 대표 6문항 × {rag, bare} → chatbot/demo_results.jsonl
```

`CALL_BUDGET` 은 프로세스 단위 안전장치다(`chain.py` 70콜, `rag_hcx.py` 20콜).
소진되면 즉시 중단되고, Streamlit 은 앱 재시작으로 리셋한다.

---

## 6. 평가 — `crawler/eval.py` (유일 정본)

**판정 기준은 앵커텍스트뿐이다.** `gt_chunk_ids` 는 특정 청킹에 대한 좌표라 재청킹하면
값이 변한다 — 그걸 지표로 쓰면 청크 파라미터를 바꿀 때마다 수치가 검색 성능이 아니라
판정 방식 때문에 움직인다. 그래서 `--score` 기본값이 `anchor` 이고, chunk_id 폴백은
꺼져 있다(`--id-fallback` 로만 켠다). 앵커가 하나도 없는 문항은 미적중이 아니라
**판정 불가**로 보고 분모에서 뺀다.

청크·스팬·앵커 3종 판정이 한 파일의 서브커맨드로 들어있다. K 범위와 검색 깊이가
판정마다 다르므로 섞어 쓰면 수치가 조용히 틀린다.

```bash
cd crawler

# chunk — 정본. 앵커텍스트 판정. 관리자 콘솔이 쓰는 경로
python eval.py chunk --gt ../final_testset/gt_natural430_anchored.jsonl
python eval.py chunk --gt ../final_testset/gt_natural430_anchored.jsonl --mode hybrid_bf
python eval.py chunk --gt ... --retrieved data/retrieved_top30.jsonl     # 검색 생략, 캐시 판정
python eval.py                                                          # 인자 없으면 chunk

# 감사용 — 라벨 잔량(앵커가 안 덮는 gold)이 얼마나 되는지 볼 때만
python eval.py chunk --gt ... --id-fallback      # 구 하이브리드 판정(chunk_id 섞임)
python eval.py chunk --gt ... --score chunk_id   # chunk_id 단독 — 오류 분석·감사표용
python eval.py chunk --gt ... --score both       # 두 판정 병기

# span — gt_anchor_spans 전부 발견해야 AND hit. KS=1~10
python eval.py span --gt ../final_testset/gt_natural430_anchored.jsonl --mode hybrid_bf
python eval.py span --gt ... --id-fallback --limit 50

# gold — 앵커 포함한 모든 청크를 host 로. Wilson CI · 등급 nDCG · McNemar
python eval.py gold --gt <앵커GT>.jsonl --retrieved data/retrieved_top30.jsonl
python eval.py gold --gt ... --retrieved data/retrieved_top30.jsonl --compare data/retrieved_ab.jsonl
python eval.py gold --gt ... --retrieved ... --dump-miss data/miss30.json
```

`--retrieved` 를 생략하면 그 자리에서 `rag.Searcher` 로 검색한다 → **현재 rag.py 설정이
그대로 반영된다.** 파라미터를 고정한 비교를 하려면 `cache_retrieval.py` 로 굳힌
`retrieved_*.jsonl` 을 넘긴다.

읽을 때 봐야 하는 두 줄 — `판정` 이 `앵커텍스트 전용` 인지, `앵커 커버율` 이 얼마인지.
커버율이 낮으면 지표의 모집단이 작다는 뜻이므로 수치를 그대로 믿으면 안 된다.

```
score_mode     : anchor
판정             : 앵커텍스트 전용 (chunk_id 미사용)
앵커 채점/결측 : 430 / 0
앵커 커버율    : 100.0%
```

`--score chunk_id` 로 나오는 수치는 **판정이 아니라 참고값**이다. 리포트·콘솔에서
`chunk_id 기준` 열은 앵커 전환 효과를 보기 위해 나란히 놓은 것일 뿐이다.

> `gold` · `cache_retrieval.py` 의 기본 GT 파일명(`data/gt_natural450_v10_anchor.jsonl`)은
> 현재 디스크에 없다. `gold` 는 `--gt`/`--retrieved` 를 명시해 쓰고,
> `cache_retrieval.py` 는 GT 경로가 하드코딩이라 파일을 두거나 그 한 줄을 고쳐야 돈다.

---

## 7. 검증 · 테스트

```bash
# eval.py 등가성 회귀 — archive/superseded/ 구 평가기와 판정이 같은지. 검색 스택 불필요
python3 crawler/tests/test_eval_equivalence.py
pytest crawler/tests/test_eval_equivalence.py

# 관리자 가드
python3 crawler/tests/test_guards.py

cd crawler
python verify_integrity.py     # 인덱스·코퍼스 개수 정합
python verify_combos.py        # 큐폼 조합 테이블 재현 (실패 시 exit 1)
python verify_terms.py         # 용어 사전
python verify_natural.py       # 자연어 평가셋
python audit_anchors.py --gt ../final_testset/gt_natural430.jsonl   # 앵커 커버리지

cd ..
python3 chatbot/verify_qform_e2e.py           # 큐폼 상태전이 (UI 없이)
python3 chatbot/verify_qform_integration.py
python3 chatbot/verify_qform_multiturn.py
python3 chatbot/verify_qform_panel.py
python3 chatbot/verify_docs.py
python3 chatbot/answer_checks.py
```

---

## 부록 A. 파라미터 튜닝 · 실험 (필요할 때만)

```bash
cd crawler

# 검색 5축 그리드
python tune_params.py --gt ../final_testset/gt_natural430.jsonl
python tune_params.py --gt ../final_testset/gt_natural430.jsonl --verify   # eval.py 와 판정 일치 확인만
python tune_params.py --gt ... --top 20

# 8,064 조합 그리드 — 콘솔 프리셋 3종의 출처
python tune_params_v2.py                      # 표 수정 코퍼스(TABLE_GAP_MAX=12)
python tune_params_v2.py --gap 0               # 옛 청킹 대조
python tune_params_v2.py --chunks data/chunks.jsonl

# BF_DOC_CAP × k
python tune_cap_k.py
python tune_cap_k.py --sets 430 --report data/cap_k_430.md

# 패싯 부스트 — 라우터 질의 예측 캐시가 선행이다
python predict_query_bf.py
python exp_router_facet.py
python exp_router_facet.py --gt data/gt_schema_v6.jsonl --depth 50

python exp_tablefix.py           # 표 유지 on/off
python exp_overlap.py            # OVERLAP 100/200/300
python exp_docinput.py           # 문서 입력 표현
python diag_rerank.py            # 리랭커 진단 (torch 필요)
python make_val_split.py                    # 505 + 355 둘 다 생성
python make_val_split.py --answerable-only  # 355만

cd .. && python3 exp/harness.py run     # 검색 실험 하네스 (HCX 0콜)
python3 exp/harness.py probe            # 트랩셋 프로브
```

## 부록 B. 평가셋 · 라벨링 도구

```bash
cd crawler
python build_testset.py
python build_yesom_testset.py

# 앵커 승격 — gold chunk_id 에 앵커텍스트를 붙인다
python promote_gt_anchors.py --gt gt_testset_retrieval_450.jsonl
python promote_gt_anchors.py --gt ... --out data/gt_450_v2.jsonl

python fill_anchors.py --map /tmp/anchor_fill.json          # 수동 보정분 주입
python filter_anchored.py --gt ../final_testset/gt_natural450.jsonl
python filter_anchored.py --gt ... --mode full-anchor

python audit_anchors.py --gt ../final_testset/gt_natural430.jsonl   # chunk_id 폴백 비율

cd .. && python3 crawler/span_tools.py     # 자기검사(왕복·유일성). 파일 수정 0
```

## 부록 C. 정본 1개 원칙 (2026-08-24 확인)

**은퇴 기준은 참조 여부다** — 다른 파일이 쓰지 않는 평가기는 은퇴한 것으로 본다.
실험을 위해 만든 평가기가 여러 개 있었고, 검증용으로만 남은 것은 연결이 없어야 정상이다.

- 리포 전체에 `rag.py` 는 `crawler/rag.py` **1개**, `eval.py` 는 `crawler/eval.py` **1개**뿐이다.
- 모든 소비자(`admin/runner.py` · `admin/settings.py` · `chatbot/chain.py` ·
  `chatbot/rag_hcx.py` · `chatbot/answer_checks.py` · `crawler/*` · `exp/harness.py`)가
  `sys.path` 에 `crawler/` 를 넣고 같은 모듈 객체를 import 한다.
- `Searcher` · `Store` · 임베딩 모델 로드는 `crawler/rag.py` 에만 있다(중복 구현 0).
- 은퇴한 평가기 19개 — `archive/eval_retired/`(11) · `archive/label_retired/`(2) ·
  `archive/superseded/`(6). **라이브 참조 0건.**
- 유일하게 남은 참조는 `crawler/tests/test_eval_equivalence.py` → `archive/superseded/` 다.
  통합 결과가 구 평가기와 같은 판정을 내는지 대조하는 **회귀 테스트**이므로 의도된 연결이다.
  이 테스트가 기준값으로 쓰기 때문에 `superseded/eval_anchor_v3.py` 는 지우면 안 된다.
- `backup/` · `crawler/*.bak_*` 의 옛 사본은 `.bak` 확장자라 import 대상이 아니다
  (`backup/` 은 git 미추적).

**예외 1건** — `exp/harness.py` 는 `eval.py` 를 import 하지 않고 지표 셈법(`KMAX=10`,
랭크 계산)을 **복제**해 갖고 있다. 스스로 그렇게 밝히고 있고(`"실행·수정 없이 셈법만 복제"`)
어느 라이브 경로도 이 파일을 부르지 않으므로 정본은 여전히 하나지만, `eval.py` 의
셈법을 바꾸면 여기가 조용히 어긋난다.

**판정 기준 단일화 (2026-08-24)** — 평가셋 판정은 앵커텍스트 전용으로 못박았다.

| 위치 | 무엇이 바뀌었나 |
|---|---|
| `crawler/eval.py` | `evaluate_retrieval(..., id_fallback=)` 신설 · CLI `--score` 기본값 `both` → `anchor` · `--id-fallback` 플래그(기본 꺼짐) |
| `admin/runner.py` | `run_eval()` 이 `score="anchor", id_fallback=False` 로 호출 · `hit@k`·`mrr@10` 이 앵커 판정값 · chunk_id 값은 `chunk_hit@5` 로 분리 |
| `admin/metrics.py` | 실측 계열 이름을 `anchor hit@k` 로 통일 · `chunk_hit5` 는 `chunk_hit@5` 를 읽는다 |
| `admin/static/app.js` | 표시 문구를 `앵커 hit@k` 로 · 청크 hit@5 행에 "참고 · 판정 미사용" 표기 |
| `crawler/tests/test_eval_equivalence.py` | 앵커 전용 판정 검사 1건 추가(§8) · run_eval 키 검사를 새 계약으로 갱신 |

`evaluate_retrieval()` 의 **함수 기본값은 `id_fallback=True` 로 남겨 뒀다.** 등가성 회귀
테스트가 구 평가기의 반환 dict·리포트 바이트와 대조하는 기준 경로라서 그렇다. 평가셋
정책 경로(CLI·콘솔)는 전부 `False` 로 부른다.

실측 차이(430문항 앵커셋, `hybrid_bf`) — 분모는 같고(430문항, 앵커 미보유 0) 22문항에
섞여 있던 chunk_id 조건이 빠졌다.

| 지표 | 구 하이브리드 | 앵커 전용 | Δ |
|---|---:|---:|---:|
| hit@1 | 0.507 | 0.505 | -0.002 |
| hit@3 | 0.779 | 0.781 | +0.002 |
| hit@5 | 0.879 | 0.884 | +0.005 |
| hit@10 | 0.942 | 0.947 | +0.005 |
| MRR@10 | 0.657 | 0.657 | 0.000 |

`and` 문항은 앵커 없는 gold 를 더 이상 요구하지 않아 올라가고, `or`/`single` 문항은
gold id 로 적중하던 경로가 사라져 내려간다. 상쇄되어 순변화가 작다.

---

## 부록 D. 확인 중 발견한 배선 공백

정본 중복은 없었지만 아래 3건은 손대야 맞는 것들이다.

1. **랭킹 레버 3종이 콘솔에 없다.** `d37c47c` 로 `rag.py` 에 들어온 `DENSE_W` ·
   `TITLE_W` · `BF_BOOST_SCALING` · `QBF_PRF_TOPN` · `QBF_PRF_MIN_SHARE` 가
   `admin/registry.py:PARAMS` 에 없다. 콘솔 ⑥ 고급 탭에서 조절할 수 없고
   `settings.apply_runtime()` 의 주입 키 목록(7종)에도 빠져 있어, 이 값들은
   항상 `rag.py` 파일 기본값으로만 돈다.

2. **`verify_integrity.py` 의 임베딩 차원이 낡았다.** `EMB_DIM = 768`(20행)인데
   현행 모델 `dragonkue/BGE-m3-ko` 는 1024d 다(`rag.py:29`). "임베딩 차원 == 768"
   체크(51행)가 정상 인덱스를 실패로 판정한다.

3. **`gold` 판정의 기본 GT 파일이 없다.** `eval.py gold` 와 `cache_retrieval.py` 가
   기대하는 `data/gt_natural450_v10_anchor.jsonl` 이 디스크에 없다.
   `eval.py gold` 는 `--gt`/`--retrieved` 를 명시하면 되지만
   `cache_retrieval.py` 는 GT 경로가 하드코딩이라 그대로는 실행되지 않는다.
