# 기존 streamlit 인스턴스를 정리하고 앱을 실행한다.
# torch/faiss 를 로드한 좀비 프로세스가 쌓이면 commit limit 초과로 WinError 1455 가 난다.
param([int]$Port = 8501)

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*streamlit*run*chatbot/app.py*' -or $_.CommandLine -like '*streamlit*run*chatbot\app.py*' } |
  ForEach-Object {
    Write-Host "kill stale streamlit: PID $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }

Set-Location (Split-Path $PSScriptRoot -Parent)
python -m streamlit run chatbot/app.py --server.address 127.0.0.1 --server.port $Port
