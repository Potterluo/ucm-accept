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
    # pyarrow 从未发布 win_arm64 轮子 → datasets→pyarrow 链在 ARM64 Windows 上无法安装，
    # evalscope 引擎不可用。ARM64 版打包 mock 版（流程/报告完整，内置假端点演示）；
    # 真实验收请使用 Windows x64 或 Linux 版本。
    Write-Host "ARM64 Windows: 打包 mock 版（evalscope 因 pyarrow 缺 win_arm64 轮子而不可用）"
} else {
    pip install "evalscope[perf,eval,agentx]==1.15.0" "pyarrow==21.0.0"
    Stop-OnExit

    # bfcl-eval 依赖链含 pathlib backport（py3.11 无发行版）与 numpy 钉死，走 --no-deps + 显式清单
    $BFCL_EVAL_DEPS = (Get-Content packaging/bfcl-eval-deps.txt) -join " "
    pip install "bfcl-eval==2025.10.27.1" --no-deps
    if ($LASTEXITCODE -gt 2) { Stop-OnExit }
    pip install $BFCL_EVAL_DEPS.Split()
    if ($LASTEXITCODE -gt 2) { Stop-OnExit }
}

pyinstaller --noconfirm --clean packaging/ucm-accept.spec
Stop-OnExit

Compress-Archive -Path "dist\ucm-accept\*" -DestinationPath "dist\ucm-accept-windows-$Arch.zip" -Force
Write-Host "完成：dist\ucm-accept-windows-$Arch.zip"
