# 개발 환경 세팅 — 새 로컬에서 챗봇 띄우기까지

> 클론만 한 상태에서 **모델 다운로드 → 크롤링 → 인덱스 → 챗봇 실행**까지.
> **모든 명령은 레포 루트(`4MATION/`)에서 실행합니다.**
> 전체 30~60분, 대부분 모델 다운로드와 크롤링 대기 시간입니다.

프로젝트 개요는 [README.md](./README.md), 파이프라인 상세는 [crawler/README.md](./crawler/README.md).

---

## 빠른 경로

세 줄이면 끝납니다.

```bash
python3 -m venv .venv && source .venv/bin/activate
make setup          # 설치 → 크롤 → 인덱스 → 점검
make chat           # 챗봇 실행 (.env 채운 뒤)
```

`make setup` 중간에 `.env`가 생성되니, **`make chat` 전에 CLOVA 키를 채워야** 합니다([4절](#4-env-작성)).

무엇이 있는지 보려면:

```bash
make help
```

아래는 각 단계를 나눠서 설명합니다. 문제가 생겼을 때 어디를 보면 되는지 알기 위한 것입니다.

---

## 1. 사전 준비

| 항목 | 요구 | 확인 |
|---|---|---|
| Python | **3.11 이상** (3.13에서 검증) | `python3 --version` |
| make | macOS·Linux 기본 탑재 | `make --version` |
| 디스크 | **최소 8GB** 여유 | 임베딩 2.2GB + 라우터 2.4GB + 원본·인덱스 |
| CLOVA Studio | API 키 (챗봇 답변 생성용) | 팀 리드에게 요청 |
| HuggingFace | 계정 + 라우터 repo 접근권 (선택) | [7절](#7-라우터-체크포인트-선택) |

**Windows**: `make`가 없으면 [부록 A](#부록-a--make-없이-실행)의 원시 명령을 쓰세요. 가상환경 활성화는 `.venv\Scripts\activate`입니다.

## 2. 클론 · 가상환경

```bash
git clone https://github.com/likelion-4MATION/4MATION.git
cd 4MATION
git checkout Qform_ver4          # 현재 통합 브랜치

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

가상환경을 꼭 쓰세요. `torch`·`faiss`·`sentence-transformers`가 시스템 파이썬을 오염시키기 쉽습니다. **`make`는 가상환경을 관리하지 않으니 먼저 활성화**해야 합니다.

## 3. 의존성 설치

```bash
make install
```

`crawler/requirements.txt` + **`streamlit`·`python-dotenv`** 를 설치합니다.

> 뒤의 두 개는 `requirements.txt`에 빠져 있습니다. `pip install -r crawler/requirements.txt`만 하면 크롤링·인덱스까지는 되고 **챗봇 실행에서 `ModuleNotFoundError`가 납니다.** `make install`은 이걸 함께 넣습니다.

확인:

```bash
make doctor
#   파이프라인 OK
#   챗봇 OK
#   .env 없음 → make env
```

## 4. `.env` 작성

```bash
make env          # .env.example → .env (기존 파일이 있으면 건드리지 않음)
```

`.env`를 열어 CLOVA 항목을 채웁니다. **`.env`는 커밋 금지**입니다(`.gitignore`에 등록돼 있음).

```ini
CLOVA_API_KEY=발급받은키
CLOVA_API_URL=https://clovastudio.stream.ntruss.com/...
CLOVA_MODEL=HCX-...
```

라우터를 쓸 거면 `HF_TOKEN`도 채웁니다([7절](#7-라우터-체크포인트-선택)). 안 쓸 거면 비워두세요.

## 5. 임베딩 모델 — 자동

별도 명령이 없습니다. 6절에서 인덱스를 만들 때 `sentence-transformers`가 `dragonkue/BGE-m3-ko`(약 2.2GB)를 받아 `~/.cache/huggingface`에 캐시합니다. **최초 1회만** 걸립니다.

미리 받아두려면:

```bash
python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('dragonkue/BGE-m3-ko')"
```

## 6. 크롤링 → 인덱스

```bash
make crawl        # 가드 검증 → 수집 38문서 → 보호한도 스테일 자동 점검 (2~3분)
make index        # 파싱 → 청킹 → 임베딩 → 인덱스
```

요청당 1.5초 + 지터의 폴라이트 크롤링이라 수집이 느린 게 정상입니다.

### 보호한도 스테일 (H6) — `make crawl`이 자동으로 봅니다

예보 서버가 낮은 빈도로 **한도 상향 이전('5천만원') 페이지**를 내려줍니다. 그대로 색인하면 챗봇이 틀린 금액을 답합니다. `make crawl`이 끝에 이 검사를 돌리고, 걸리면 실패로 멈춥니다.

```
보호한도 스테일 검사(H6): 실패 — '5천만' 1건 발견
  → make recrawl 로 재수집하세요 (0 나올 때까지)
```

```bash
make recrawl      # 캐시 무시하고 라이브 재수집 + 재점검
make check-stale  # 검사만 다시
```

`content_hash`가 달라져 해당 문서만 다시 수집·적재됩니다. **정상이 나올 때까지 반복**하세요.

### 결과 확인

```bash
make check
#   보호한도 스테일 검사(H6): 정상 (1억원 판)
#   청크 수        : 181
#   FAISS 인덱스   : 있음
#   라우터         : ...

make eval         # 검색 평가 → crawler/data/eval_report.md
```

## 7. 라우터 체크포인트 (선택)

질의를 6대 업무로 분류하는 파인튜닝 모델(Qwen3 기반, 2.38GB)입니다. **없어도 됩니다** — `rag.get_router()`가 실패를 한 번 보고하고 키워드 분류로 폴백합니다.

| | 라우터 있음 | 없음(키워드 폴백) |
|---|---|---|
| 업무 분류 기권률 | 0% | **28.6%** (128/448) |
| 기권 구간 | — | 업무 부스트를 못 받음 |

> **수치를 리포트할 때는 라우터 사용 여부를 반드시 함께 적으세요.** 같은 코드라도 BF 소스가 다르면 다른 측정입니다.

### 받는 법

가중치는 git에 없고(2.38GB) HF 프라이빗 repo `us788/moai_yebo_ft`에 있습니다.

1. **repo 접근 권한을 받으세요** — 개인 네임스페이스 프라이빗이라 collaborator로 추가돼야 합니다
2. HF 토큰 발급 (**Read** 권한이면 충분): <https://huggingface.co/settings/tokens>
3. 로그인 후 확인:

```bash
hf auth login                # 구버전: huggingface-cli login
hf auth whoami               # 본인 계정이 나오면 성공
make router                  # resolve() -> us788/moai_yebo_ft
```

### ⚠️ 챗봇 실행 전에 미리 받아두세요

`chatbot/rag_hcx.py`가 `HF_HUB_OFFLINE=1`을 설정합니다 — 챗봇 실행 중에는 **네트워크를 CLOVA API 한 곳으로만 제한**하기 때문에, 그 시점에 캐시가 없으면 라우터도 임베딩 모델도 못 받고 조용히 폴백합니다.

```bash
make router-cache            # 미리 캐시에 내려받기 (2.38GB)
```

상세는 [docs/router_checkpoint.md](./docs/router_checkpoint.md).

## 8. 챗봇 실행

```bash
make chat
```

브라우저가 `http://localhost:8501`로 열립니다. 질문을 넣어 **출처가 함께** 나오면 정상입니다.

---

## 자주 걸리는 문제

**`ModuleNotFoundError: No module named 'streamlit'` / `'dotenv'`**
`make install` 대신 `pip install -r crawler/requirements.txt`만 하신 경우입니다. `make install`을 다시 돌리세요.

**`KeyError: 'CLOVA_API_KEY'`**
`.env`가 없거나 비어 있습니다. `make env` 후 키를 채우세요. `.env.example`이 아니라 `.env`여야 합니다.

**`FileNotFoundError: data/index/faiss.index`**
`make index`를 안 했거나 인덱스가 깨졌습니다. `make clean-index && make index`.

**`[router] 로드 실패(OSError) — 키워드 분류로 폴백`**
정상 동작입니다. 라우터를 쓰려면 7절, 안 쓸 거면 무시하세요.

**라우터 401 / `Invalid username or password`**
`hf auth login`을 안 했거나, repo collaborator로 추가되지 않았습니다.

**크롤링이 `robots_blocked`로 일부를 건너뜀**
의도된 동작입니다. fins `/cm/bbs/` FAQ 게시판 5건은 robots 준수로 차단하되 매니페스트에는 유지합니다(DECISIONS D0). **매니페스트에서 빼지 마세요.**

**`zsh: command not found: python`**
macOS는 `python3`입니다. Makefile은 이미 `python3`을 씁니다. 다른 인터프리터를 쓰려면 `make PY=python3.12 index`.

**임베딩 다운로드가 느리거나 끊김**
`~/.cache/huggingface`에 이어받기가 됩니다. 같은 명령을 다시 돌리세요.

---

## 부록 A — `make` 없이 실행

`crawler/`의 스크립트는 경로 상수가 상대경로라 **그 폴더 안에서** 돌아야 합니다. 루트에서 쓰려면 서브셸로 감싸면 됩니다(현재 위치는 안 바뀝니다).

```bash
# 설치
python3 -m pip install -r crawler/requirements.txt
python3 -m pip install streamlit python-dotenv

# .env
cp .env.example .env

# 수집
(cd crawler && python3 tests/test_guards.py)
(cd crawler && python3 build_dataset.py --crawl)

# 보호한도 스테일 확인 — 0 이어야 정상
grep -c "5천만" crawler/data/raw/kdic-www-sp-dpstrprot-ProtSystProtLmts-selectScrn.html

# 인덱스
(cd crawler && python3 pipeline.py --manifest crawl_manifest.csv --use-cache --rebuild)

# 재수집(스테일이 걸렸을 때)
(cd crawler && python3 pipeline.py --manifest crawl_manifest.csv --rebuild)

# 평가 · 라우터 확인
(cd crawler && python3 eval.py)
(cd crawler && python3 router_source.py)

# 챗봇 — 루트에서
streamlit run chatbot/app.py
```

## 부록 B — 더 볼 것

| 문서 | 내용 |
|---|---|
| [README.md](./README.md) | 프로젝트 개요·아키텍처·팀 |
| [crawler/README.md](./crawler/README.md) | 파이프라인 단계별 실행·재수집·매니페스트 |
| [crawler/DECISIONS.md](./crawler/DECISIONS.md) | 설계 판단 근거 |
| [crawler/HOLES.md](./crawler/HOLES.md) | 미해결 이슈 |
| [docs/router_checkpoint.md](./docs/router_checkpoint.md) | 라우터 배포·업로드·제약 |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | 협업 규칙 |
