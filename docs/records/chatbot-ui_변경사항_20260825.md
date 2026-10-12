<!-- 상태:records -->
> **기록** — 2026-08-25 시점의 사실(레거시 Streamlit `chatbot/app.py` UI 변경). 고치지 않는다.
> 08-26부터 정식 사용자 UI는 `web/`(FastAPI)이다 — `web/README.md`

# 챗봇 UI 변경 사항 — `feature/chatbot-ui` (Qform_ver4 대비)

> **작성자** kungean · **브랜치** `feature/chatbot-ui` (`c844d33` + 워킹트리 변경분)
> **분기점** `Qform_ver4` PR #17 병합 시점(`2a23add`)
> **범위** `chatbot/app.py`, `chatbot/attachments.py`, `.mcp.json` — 이 3개 파일만 변경됨
>   (`git diff $(git merge-base feature/chatbot-ui origin/Qform_ver4) -- chatbot/ .mcp.json` 기준)

---

## 1. 요약

Qform_ver4 시점의 챗봇은 **Streamlit 기본 사이드바 + 단일 대화창** 구조였다. 이번 브랜치에서
예시 UI(서울 열린데이터광장 챗봇)를 참고해 **좌/중앙/우 3컬럼 상시 레이아웃**으로 전면 재구성했고,
업무 도메인 문맥을 활용한 추천 질문 기능을 새로 추가했다. 백엔드 로직(`qform_flow`·`chain`·
`rag` 등)은 건드리지 않았다 — **UI 레이어와 첨부 필터 버그 1건**만 손댔다.

---

## 2. 백엔드 버그 수정 1건 (`chatbot/attachments.py`)

`_load_combo_tables()`가 `qform_combos_dpin.csv`를 읽을 때 파일 앞부분의 주석 줄(`#`으로 시작)을
걸러내지 않아, 주석이 헤더로 잘못 인식되고 모든 행에서 `sub_task` 컬럼이 사라지는 문제가 있었다.
`sub_task` 슬롯이 채워지는 질의(대부분의 정상 플로우)에서 첨부 후단 필터가 `KeyError: 'sub_task'`로
죽는 재현성 있는 버그였다. `qform_state.py`·`qform_memory_panel.py`는 이미 같은 파일을 읽을 때
주석 필터링을 하고 있었는데 `attachments.py`만 빠져 있었던 것 — 같은 패턴으로 맞췄다.

```python
# Before
tables[bf] = list(csv.DictReader(fh))
# After
lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
tables[bf] = list(csv.DictReader(lines))
```

---

## 3. 레이아웃 — 사이드바 → 3컬럼 (`chatbot/app.py`)

```python
left, center, right = st.columns([1.1, 2.3, 1.1])
```

좌·우 폭은 동일, 중앙(대화)이 더 넓다. Streamlit 기본 사이드바(접었다 펼 수 있는 좌측 서랍)를
없애고, 세 컬럼 다 항상 펼쳐져 보이는 고정 패널로 바꿨다.

### 3-1. 좌측 — 정보

| 요소 | 상태 |
|---|---|
| 🔄 대화 초기화 | 맨 위, 큰 primary 버튼(빨강 — Streamlit 기본 테마색) |
| 세션 상태 (HCX 콜 카운트) | 상시 노출. 숫자만 별도로 크게(2rem, 제목의 2배) |
| 📎 근거 문서 | 상시 노출 — 마지막 답변의 근거 문서·검증 플래그 |
| ⚙️ 큐폼 설정 | 접이식(expander)으로 축소 — 되묻기 문구 모드·쿼리 부스트·슬롯 스코프·트레이스 토글 |
| 🧠 기억 | 접이식으로 축소 |
| 🔬 트레이스 패널 | "트레이스 패널" 토글 켰을 때만 추가로 노출(기본 꺼짐) |

세션상태·근거문서만 상시 노출하고 나머지는 접어서, 스크롤을 줄이고 "지금 필요한 정보"에 집중하게
했다.

### 3-2. 중앙 — 대화

- **2단계 렌더링**: 질문을 보내면 ①사용자 메시지만 먼저 히스토리에 넣고 즉시 rerun → ②다음 런에서
  메시지 목록 바로 아래(입력창 바로 위)에 로딩 스피너를 띄우고 그제서야 실제 검색·생성 호출.
  기존엔 사용자 메시지와 답변이 동시에(응답 완료 후) 나타나서 "내가 뭘 물어봤는지" 바로 안 보이던
  문제를 해결했다. 우측 추천 질문 클릭도 같은 경로를 탄다.
- **사용자 메시지만 회색 말풍선 + 오른쪽 정렬**(아이콘·텍스트 둘 다). 챗봇 답변은 기존 `st.chat_input`
  기본 모양 그대로 유지(왼쪽 정렬, 배경 없음) — 여러 차례 스타일을 실험하다가 최종적으로 "질문만
  구분되면 충분하다"는 방향으로 정리됨.
- 첫 화면(대화 없음)에는 업무 6종 대표 질문 카드를 3열로 노출.

### 3-3. 우측 — 추천 질문 / 근거 조각 (탭 2개)

**💡 추천 질문 탭**
- 상단: 직전 질의의 업무 도메인을 판정할 수 있으면 **"🎯 현재 질문과 비슷한 질문"**(그 업무의
  구어체 질문 목록), 판정이 안 되거나 대화가 없으면 **"🔥 지금 뜨는 검색어"**(코퍼스 FAQ 페이지
  원문 질문)로 자동 폴백.
- 하단: **"📂 업무별 추천 검색어"** — 업무 6개를 세로 목록(6×1)으로 보여주고, 클릭하면 그 업무의
  대표 질문 목록으로 드릴다운(뒤로가기로 복귀). 클릭이 바로 질의로 안 나가고 목록을 한 번 더
  보여주는 2단 구조.
- 질문 카드 앞 **"Q."** 글자만 빨간색(Streamlit 테마 accent color, `#FF4B4B`)으로 강조.

**🧩 근거 조각 탭**
- 마지막 답변 생성에 실제로 쓰인 검색 청크를 결정론 재검색(HCX 콜 0)으로 다시 불러와 카드로 나열.
  카드마다 "펼치기"로 청크 전문·업무구분·원문 링크 확인 가능.

### 3-4. 문맥 추천 질문의 데이터 출처 — 두 섹션이 겹치지 않는 이유

`crawler/data/testset_natural_450.jsonl`의 각 문항은 구어체 `question` 외에 더 formal한
`origin_question` 필드를 갖고 있다(예: "돌아가신 부모님 계좌가 어디 있는지 확인하는 서비스
있나요?" ← origin_question **"상속인 금융거래 조회서비스란?"**). 이 구조를 그대로 활용해 **두 개의
분리된 풀**을 만들었다:

| 함수 | 필드 | 쓰이는 곳 |
|---|---|---|
| `_load_domain_questions()` | `question`(구어체) | "현재 질문과 비슷한 질문" — 방금 물은 것과 같은 결로 자연스럽게 이어지게 |
| `_load_representative_domain_questions()` | `origin_question`(공식 대표 질문) | "업무별 추천 검색어" — 개인 사연 섞인 구어체 없이 공적·일반적인 질문만 |

두 기능이 같은 도메인을 가리켜도 서로 다른 문구를 보여주므로 화면에 완전히 같은 질문 목록이
중복 노출되는 상황을 피한다. 둘 다 코퍼스 원문 그대로 쓰고 새로 문구를 창작하지 않는다(이
리포의 기존 원칙 — `docs/qform_시험질의셋.md`·`testset_natural_450.jsonl` 밖 문구를 만들지 않음).

---

## 4. 디자인 CSS — Streamlit 컴포넌트 커스터마이징

Streamlit이 표준으로 제공하지 않는 요소(좌·우 고정, 카드 배경, 말풍선 정렬 등)는 `st.markdown`으로
주입한 CSS와 안 보이는 마커(`<span>`) + `:has()` 선택자 조합으로 구현했다. 핵심 기법:

- **마커 + `:has()` 스코핑**: 좌/우 컬럼 맨 앞에 `<span class="col-anchor-left/right">`를 심고
  `[data-testid="stColumn"]:has(.col-anchor-left)`로 그 컬럼 자체를 지정 — 안쪽에 중첩된
  `st.columns()`(도메인 버튼 그리드 등)에는 안 걸리게 스코핑을 정확히 함.
- **`st.container(key="card-...")` 활용**: Streamlit이 위젯 `key`를 `st-key-<key>` 클래스로 그대로
  붙여주는 걸 이용해 특정 카드(근거 조각)만 흰 배경으로 지정. `st-key-qcard-*` 접두사로 "Q." 빨간
  글자 스타일도 같은 방식으로 스코핑.
- **좌·우 컬럼 고정(sticky) + 스크롤바 숨김**: `position: sticky` + `overflow-y: auto` +
  `scrollbar-width: none`. 이게 동작하려면 Streamlit이 기본적으로 앱 전체를 뷰포트 높이에 가두는
  내부 컨테이너(`stApp`·`stAppViewContainer`·`stAppScrollToBottomContainer` 등)의 `overflow:hidden`을
  먼저 풀어줘야 했다.
- **하단 입력창 폭 동기화**: `st.chat_input`은 컬럼 밖(고정 하단 영역)에 그려져서 CSS만으론 폭을
  맞출 수 없다 — `components.html`로 작은 JS를 심어 중앙 컬럼의 실제 렌더 폭을 재서 입력창에
  반영(중앙 폭 + 140px 여유), 가운데 정렬은 `margin: auto`.
- **회색 톤 통일**: `--panel-gray: #F1F3F4` 변수 하나로 좌·우 배경과 사용자 말풍선 배경을 통일.

---

## 5. 새 파일

- **`.mcp.json`** — `chrome-devtools-mcp` 등록. 이번 UI 작업 전체를 실제 브라우저로 라이브 검증하며
  진행하기 위해 추가(Node.js·MCP 셋업 필요, 상세는 커밋 로그 참고).

---

## 6. Qform_ver4 대비 변경 없음 (확인용)

- `qform_flow.py`·`qform_state.py`·`qform_ask.py`·`qform_extract.py` 등 큐폼 상태전이 로직 — 무변경
- `chain.py`·`rag.py` — 무변경 (답변 생성·검색 로직 그대로)
- `qform_panel.py`(트레이스 패널 자체 렌더링) — 무변경, 위치만 좌측으로 이동
- 계약 4필드(`answer()` 반환 스키마) — 무변경

---

## 7. 알려진 제약·확인 필요 사항

- CSS가 Streamlit 내부 DOM 구조(`data-testid`, `st-key-*` 클래스)에 의존한다 — Streamlit 버전이
  크게 바뀌면(현재 1.62.0 기준) 일부 스타일이 깨질 수 있다. `data-testid` 계열은 비교적 안정적인
  훅이지만 100% 보장은 아니다.
- "현재 질문과 비슷한 질문"의 업무 판정은 `qform_trace.bf_debug()`(로컬 키워드 기반 결정론 분류,
  HCX 콜 0)를 재사용한다 — 점수·마진 미달 시 자동으로 트렌드 목록 폴백, 별도 처리 불필요.
- 하단 입력창 폭 동기화는 JS(`components.html`, `window.parent.document` 접근) 방식이라, 브라우저
  보안 정책이 더 엄격해지면 무효화될 수 있다(그래도 실패 시 조용히 기본 폭으로 돌아갈 뿐 에러는
  안 남).
