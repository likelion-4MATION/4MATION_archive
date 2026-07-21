import os, json, requests
from dotenv import load_dotenv

load_dotenv()  # 루트 .env를 상위 탐색으로 자동 로드
API_KEY = os.environ["CLOVA_API_KEY"]
API_URL = os.environ["CLOVA_API_URL"]

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "X-NCP-CLOVASTUDIO-REQUEST-ID": "smoke-001",
}
payload = {
    "messages": [
        {"role": "system", "content": "너는 예금보험공사 안내 챗봇이다. 간결히 답한다."},
        {"role": "user", "content": "예금자보호 한도는 얼마야?"},
    ],
    "maxTokens": 256,
    "temperature": 0.3,
    "topP": 0.8,
}

r = requests.post(API_URL, headers=headers, json=payload, timeout=30)
print("HTTP", r.status_code)
if r.status_code != 200:
    print(r.text[:500]); raise SystemExit

data = r.json()
print("status:", data.get("status"))
try:
    print("\n답변:\n", data["result"]["message"]["content"])
except (KeyError, TypeError):
    print("\n[스키마 예상과 다름 — 실제 구조]:")
    print(json.dumps(data, ensure_ascii=False, indent=2)[:800])
