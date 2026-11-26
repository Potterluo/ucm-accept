# 在 Windows 构建机执行：PowerShell -ExecutionPolicy Bypass -File packaging/build_windows.ps1 [-Arch x64|arm64]
# PyInstaller 不支持交叉编译：x64 产物请在 x64 机器构建，ARM64 产物请在 ARM64 机器构建。
# 注意：$ErrorActionPreference 不拦原生命令退出码，每步 pip 后必须显式检查 $LASTEXITCODE。
param(
    [string]$Arch = ""
)
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

if (-not $Arch) {
    $Arch = if ($env:PROCESSOR_ARCHITECTURE -match "ARM64") { "arm64" } else { "x64" }
}

function Stop-OnExit {
    if ($LASTEXITCODE -ne 0) {
        Write-Error "上一步原生命令失败（退出码 $LASTEXITCODE），终止打包"
        exit $LASTEXITCODE
    }
}

pip install -e ".[gui,build]"
Stop-OnExit

if ($Arch -eq "arm64") {
    # cryptography 46.0.3 是最后一个提供 Windows ARM64 轮子的版本（abi3，兼容 py3.11+）；
    # 预装以满足 modelscope 链的 cryptography>=41，避免 pip 落到无轮子的新版本走源码编译。
    pip install "cryptography==46.0.3"
    Stop-OnExit
}

pip install "evalscope[perf,service]==1.15.0"
Stop-OnExit

pyinstaller --noconfirm --clean packaging/ucm-accept.spec
Stop-OnExit

Compress-Archive -Path "dist\ucm-accept\*" -DestinationPath "dist\ucm-accept-windows-$Arch.zip" -Force
Write-Host "完成：dist\ucm-accept-windows-$Arch.zip"
