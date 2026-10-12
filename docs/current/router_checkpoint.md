<!-- 상태:current -->
> **정본** — 지금 이대로 돌아간다. 바꾸려면 코드와 함께 바꿀 것
> 문서 지도: `docs/README.md`(문서 지도) · `docs/프로젝트_전체흐름.md`(전체 그림·용어 해설)

---

# 질의 BF 라우터 체크포인트 — 배포와 설정

> **한 줄** 가중치 2.38GB는 git에 못 넣는다. HF 프라이빗 repo에서 `scripts/download_router_hf.py`로 레포 안 `router_moai_embedding_model/`에 **한 번** 받아 두면 이후엔 로컬에서 돈다. 없어도 검색은 돈다(키워드 폴백).

---

## 1. 이 체크포인트가 뭔가

`crawler/faq_bf_map.py`의 `Router`가 로드하는 **6대 업무 시퀀스 분류기**다. 질의를 받아 업무 하나를 예측하고, `rag.classify_query_bf()`가 그 결과로 소프트부스트 대상을 정한다.

| 항목 | 값 |
|---|---|
| 아키텍처 | `Qwen3ForSequenceClassification` (28층 · hidden 1024 · vocab 151669) — 파인튜닝본 |
| 라벨 | 6개. `config.json`의 `id2label`이 `faq_bf_map.CANONICAL_BF`와 **정확히 일치해야** 로드된다(V1 검증) |
| dtype / 크기 | float32 / `pytorch_model.bin` **2,383,231,423 B (2.22 GiB)** |
| 설정파일 8개 | 15.9 MB — **레포에 커밋돼 있다** |
| HF repo | `us788/moai_yebo_ft` (**private**) |

**왜 설정파일만 커밋했나** — `id2label`이 6대 업무와 맞는지, 아키텍처가 뭔지가 코드리뷰에서 보여야 한다. 가중치 없이도 `config.json`만으로 V1 검증 조건을 확인할 수 있다. 15.9MB는 레포에 부담이 아니다.

**왜 가중치는 못 넣나** — GitHub 단일 파일 상한 100MB, Release 에셋도 2GB 상한이다. 2.38GB는 어느 쪽도 안 된다. Git LFS는 되지만 히스토리에 박히고 대역폭 쿼터가 있다.

---

## 2. 팀원 설정 — 라우터를 쓰려면

```bash
pip install -r crawler/requirements.txt        # torch · transformers · huggingface-hub 포함
export HF_TOKEN=hf_...                          # read 권한이면 충분
python scripts/download_router_hf.py            # 레포 안 router_moai_embedding_model/ 로 (크기 맞는 파일은 건너뜀)
python scripts/download_router_hf.py --verify-sha   # 받은 뒤 sha256 전수 검증
```

토큰 발급: <https://huggingface.co/settings/tokens> → **Read** 권한.

**프라이빗 repo라 접근 권한이 따로 필요하다.** `us788` 개인 네임스페이스이므로, repo 설정에서 팀원 계정을 collaborator로 추가받아야 한다. 팀이 커지면 HF 조직(`4mation` 등)으로 옮기는 게 관리가 쉽다.

확인:

```bash
cd crawler && python router_source.py
```

```
매니페스트 : .../crawler/data/router_manifest.json
로컬 경로  : .../router_moai_embedding_model  (있음)
HF repo    : us788/moai_yebo_ft (프라이빗 — HF_TOKEN 필요)

로컬 상태  : 사용 불가
   - 없음: pytorch_model.bin

resolve() -> us788/moai_yebo_ft
```

위는 가중치를 아직 안 받은 상태다(`resolve()`가 HF repo id로 해석). 이때 `transformers`를 직접 부르면 HF 캐시로 받을 수 있지만, 챗봇(`chatbot/chain.py`, 이를 import 하는 `web/`)과 관리자 작업(`admin/jobs.py`)은 `HF_HUB_OFFLINE=1`로 돌아 **자동 다운로드가 일어나지 않고 키워드 폴백**으로 간다. 그래서 위 `download_router_hf.py`로 받아 `로컬 상태 : 사용 가능`이 나오게 해 둔다.

### 라우터 없이 쓰기

**아무것도 안 해도 된다.** `HF_TOKEN`이 없거나 네트워크가 막혀 있으면 `get_router()`가 실패를 한 번 보고하고 `classify_query_bf_keyword()`로 폴백한다. 검색은 정상 동작한다.

```
[router] 로드 실패(OSError) — 키워드 분류로 폴백: us788/moai_yebo_ft
```

다만 폴백 시 **키워드 분류 기권률이 28.6%(128/448)** 이고 그 구간은 부스트를 못 받는다(`rag.py`의 PRF 단계 — `QBF_PRF_TOPN`·`QBF_PRF_MIN_SHARE` — 가 기권 질의 일부를 1차 검색 상위 문서의 업무 투표로 다시 분류한다). 수치를 리포트할 때는 라우터 사용 여부를 반드시 밝힐 것 — 같은 코드라도 `bf_source`가 다르면 다른 측정이다.

---

## 3. 위치 해석 순서

`crawler/router_source.py`의 `resolve()`가 정한다. 먼저 맞는 것에서 멈춘다.

| 순위 | 조건 | 반환 |
|---|---|---|
| 1 | 환경변수 `ROUTER_PATH`가 설정됨 | 그 값 그대로 (검증 없음 — 실험 체크포인트용) |
| 2 | 로컬 `router_moai_embedding_model/`이 매니페스트와 일치 | 로컬 절대경로 (**네트워크 안 탐**) |
| 3 | `ROUTER_HF_REPO` 또는 매니페스트 `hf_repo` | HF repo id |
| 4 | 위가 전부 실패 | `None` → 키워드 폴백 |

2단계 무결성 검사는 기본이 **파일 존재 + 크기**만 본다. 부분 다운로드와 빈 파일을 잡는다. sha256 전수는 2.38GB를 매번 읽어야 해서 명시 요청할 때만 돈다:

```bash
python router_source.py --verify        # 느림
```

`from_pretrained()`가 로컬 경로와 repo id를 모두 받기 때문에 이 구조가 성립한다. 호출부(`rag.py`)는 한 줄만 바뀌었고 `get_router()`의 폴백 로직은 그대로다.

---

## 4. 체크포인트 올리기 — 가진 사람이 1회

```bash
pip install "huggingface-hub>=0.23"
export HF_TOKEN=hf_...                          # write 권한

python scripts/upload_router_hf.py --dry-run    # 올릴 목록 확인
python scripts/upload_router_hf.py              # 실행 (2.3GB, 회선에 따라 수십 분)
```

동작:

1. 로컬 9개 파일을 매니페스트와 대조 — **불일치가 하나라도 있으면 올리지 않고 중단**한다. 깨진 걸 올리면 팀 전체가 깨진 걸 받는다
2. 원격 목록을 읽어 **크기가 같은 파일은 건너뛴다**(멱등). 중간에 끊겨도 다시 돌리면 된다
3. repo가 없으면 `private=True`로 만든다

`--verify-sha`를 붙이면 업로드 전에 sha256 전수 검증을 한다. 처음 올릴 때 한 번은 권장한다.

이 스크립트는 **로컬 파일을 읽기만 한다.** 삭제·수정하지 않는다.

---

## 5. 매니페스트

`crawler/data/router_manifest.json`에 9개 파일의 크기와 sha256이 들어 있다. 무결성 검사와 업로드가 모두 이 파일을 기준으로 한다.

**체크포인트를 재학습하면 매니페스트도 함께 갱신해야 한다.** 안 그러면 `resolve()`가 새 로컬 파일을 "크기 불일치"로 보고 HF의 옛 가중치를 받아온다 — 조용히 다른 모델을 쓰게 되는 최악의 실패다.

```bash
cd router_moai_embedding_model
for f in *; do printf '%s %s ' "$f" "$(stat -f%z "$f")"; shasum -a 256 "$f" | cut -d' ' -f1; done
```

---

## 6. 알려진 제약

**(a) pickle이다.** `pytorch_model.bin`은 `torch.load` 경로라 임의 코드 실행 위험이 있는 포맷이다. 프라이빗 repo라 외부 노출은 없지만, `safetensors`로 바꾸면 이 위험이 사라지고 크기도 절반(bf16 기준 ~1.2GB)이 된다. 바꾸려면 **448문항 예측 일치 검증을 거친 뒤** 매니페스트를 다시 만들 것.

**(b) MSP를 OOS 판정에 쓰지 말 것.** 이 체크포인트는 450셋에서 MSP 최솟값 0.9991 · 중앙값 1.0000으로 체계적 과신 상태다. `QBF_MSP_MIN`을 0.00~0.99 어디에 둬도 걸러지는 게 한 건도 없고, 6업무 밖 질의도 1.000이 나온다. 소관밖 판정은 다른 신호(예: PRF 투표 비중과의 불일치)가 필요하다.

> **정정(2026-10-12 추기)** — 위 450셋은 라우터 학습셋 `testset_natural_450`과 같은 450문항이라 held-out이 아니다. 학습에 쓰지 않은 dev 1,150셋에서는 전 문항 최솟값 0.3022 · in-scope 최솟값 0.4319로 분포가 다르다(`docs/records/router_판정경계_측정_20260825.md`). 현행 코드는 `rag.classify_query_bf()`가 MSP < `QBF_MSP_MIN`(0.70)이면 기권(`None`)하고, 오케스트레이터가 기권한 절을 OOS 정책으로 보낸다 — 경계 성능은 같은 측정 기록을 본다.

**(c) 파라미터가 라우터 유무에 종속된다.** `BF_BOOST`는 "분류가 거의 안 틀린다"는 전제 위에서만 안전하다. 라우터 착륙 후에는 `router` / `fallback` 두 구성에서 각각 재스윕해 두 세트를 병기할 것.

**(d) `bf_map.jsonl`은 이미 커밋돼 있다.** 문서측 BF 조인(`rag.load_bf_map` / `Searcher._resolve_bf`)은 라우터 산출물인 `crawler/data/bf_map.jsonl`(108행)만 있으면 되고, 이 파일은 레포에 있다. **체크포인트가 필요한 건 새 질의를 분류할 때뿐이다.**
