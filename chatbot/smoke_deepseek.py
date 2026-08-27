"""DeepSeek Chat Completions 연결 스모크 테스트."""
import os

import requests
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    api_url = os.environ.get(
        "DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions"
    ).strip()
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash").strip()
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY가 비어 있습니다. .env에 키를 설정해 주세요.")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "너는 예금보험공사 안내 챗봇이다. 간결히 답한다."},
            {"role": "user", "content": "예금자보호 한도는 얼마야?"},
        ],
        "max_tokens": 256,
        "temperature": 0.3,
        "top_p": 0.8,
        "thinking": {"type": "disabled"},
        "stream": False,
    }
    response = requests.post(
        api_url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    print("HTTP", response.status_code)
    if response.status_code != 200:
        print(response.text[:500])
        raise SystemExit(1)
    try:
        print("\n답변:\n", response.json()["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        print("DeepSeek 응답 스키마가 예상과 다릅니다.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
