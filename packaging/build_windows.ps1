# 在 Windows 构建机执行：PowerShell -ExecutionPolicy Bypass -File packaging/build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

pip install -e ".[gui,build]"
pip install "evalscope[perf,service]>=1.15,<2"
pyinstaller --noconfirm --clean packaging/ucm-accept.spec

Compress-Archive -Path "dist\ucm-accept\*" -DestinationPath "dist\ucm-accept-windows-x64.zip" -Force
Write-Host "完成：dist\ucm-accept-windows-x64.zip"
