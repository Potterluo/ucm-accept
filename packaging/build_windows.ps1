# 在 Windows 构建机执行：PowerShell -ExecutionPolicy Bypass -File packaging/build_windows.ps1 [-Arch x64|arm64]
# PyInstaller 不支持交叉编译：x64 产物请在 x64 机器构建，ARM64 产物请在 ARM64 机器构建。
param(
    [string]$Arch = ""
)
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

if (-not $Arch) {
    $Arch = if ($env:PROCESSOR_ARCHITECTURE -match "ARM64") { "arm64" } else { "x64" }
}

pip install -e ".[gui,build]"
pip install "evalscope[perf,service]==1.15.0"
pyinstaller --noconfirm --clean packaging/ucm-accept.spec

Compress-Archive -Path "dist\ucm-accept\*" -DestinationPath "dist\ucm-accept-windows-$Arch.zip" -Force
Write-Host "完成：dist\ucm-accept-windows-$Arch.zip"
