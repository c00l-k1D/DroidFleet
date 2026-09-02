$ErrorActionPreference = "Stop"

py -3 -m pip install pyinstaller psutil
py -3 -m PyInstaller --noconfirm --clean --onefile --name FarmAgent agent/agent.py
Write-Host "Built dist/FarmAgent.exe"
