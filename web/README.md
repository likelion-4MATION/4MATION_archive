# 사용자 웹 앱

`web/`은 기존 `chatbot/`의 Q-Form, 라우팅, RAG 답변 로직을 그대로 호출하는 사용자용
FastAPI 서버와 빌드 과정이 없는 정적 HTML/CSS/JavaScript UI입니다. 관리자 서버(`admin/`)와
분리되어 있으며, 대화 상태는 현재 프로세스 메모리에 최대 8시간 보관합니다.

## 실행

리포지토리 루트에서 실행합니다.

```bash
python -m pip install -r crawler/requirements.txt
python -m pip install -r admin/requirements.txt
python -m pip install python-dotenv
python -m uvicorn web.main:app --host 127.0.0.1 --port 8501
```

- 사용자 화면: <http://127.0.0.1:8501>
- API 문서: <http://127.0.0.1:8501/api/docs>
- 상태 확인: <http://127.0.0.1:8501/api/health>

서버를 재시작하면 대화 세션과 프로세스 단위 LLM 호출 카운터가 초기화됩니다. 첨부파일 API는
`crawler/data/files/` 아래의 기존 파일만 내려주며, 브라우저 화면에는 모델 응답을 HTML로
삽입하지 않고 일반 텍스트로 렌더링합니다.

## 테스트

```bash
python -m pytest -q tests/test_web_api.py
node --check web/static/app.js
```
