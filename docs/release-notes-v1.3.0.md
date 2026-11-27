### 按 OS 下载 / Download based on your OS

| 平台 | 架构 | 下载 |
|---|---|---|
| Windows | x64 | [![Windows x64 zip](https://img.shields.io/badge/Windows%20x64-zip-0078D4?logo=windows&logoColor=white)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept-windows-x64.zip) |
| Windows | ARM64 | [![Windows ARM64 zip mock](https://img.shields.io/badge/Windows%20ARM64-zip%20mock-0078D4?logo=windows&logoColor=white)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept-windows-arm64.zip) |
| Linux | amd64 | [![Linux amd64 tar.gz](https://img.shields.io/badge/Linux%20amd64-tar.gz-F0B429?logo=linux&logoColor=white)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept-linux-amd64.tar.gz) [![deb amd64](https://img.shields.io/badge/deb-amd64-F0B429?logo=linux&logoColor=white)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept_1.3.0_amd64.deb) [![rpm x86_64](https://img.shields.io/badge/rpm-x86__64-F0B429?logo=linux&logoColor=white)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept-1.3.0-1.x86_64.rpm) |
| Linux | ARM64 | [![Linux ARM64 tar.gz](https://img.shields.io/badge/Linux%20ARM64-tar.gz-F0B429?logo=linux&logoColor=white)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept-linux-arm64.tar.gz) [![deb arm64](https://img.shields.io/badge/deb-arm64-F0B429?logo=linux&logoColor=white)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept_1.3.0_arm64.deb) [![rpm aarch64](https://img.shields.io/badge/rpm-aarch64-F0B429?logo=linux&logoColor=white)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept-1.3.0-1.aarch64.rpm) |
| Python | any | [![Wheel py3-none-any](https://img.shields.io/badge/Wheel-py3--none--any-3776AB?logo=python&logoColor=white)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm_accept-1.3.0-py3-none-any.whl) [![sdist tar.gz](https://img.shields.io/badge/sdist-tar.gz-3776AB?logo=python&logoColor=white)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm_accept-1.3.0.tar.gz) |

> Windows ARM64 为 mock 预览版：pyarrow 不提供 win_arm64 轮子，EvalScope 引擎无法内置；真实验收请使用 Windows x64 或 Linux 版。

### Docker 镜像（多架构，amd64 / arm64 自动匹配）

```bash
docker pull ghcr.io/ucm-system/ucm-accept:1.3.0

# 单架构 / 离线加载（release 附带 docker save 导出包；若带 .part-00 分卷，先 cat 合并再 load）
docker load -i ucm-accept-1.3.0-amd64.tar.gz
docker load -i ucm-accept-1.3.0-arm64.tar.gz
```

### 离线资源包（UCM Accept 无感使用）

[![Offline Asset Pack 1.3.0 part-00+ 合并](https://img.shields.io/badge/Offline%20Asset%20Pack-1.3.0%20part--00+%20合并-E8833A)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-assets-1.3.0.tar.gz.part-00) [![SHA256 merged checksum](https://img.shields.io/badge/SHA256-merged%20checksum-6E6E73)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-assets-1.3.0.tar.gz.sha256)

包含 16 个 tokenizer、精度数据集、多轮场景与 AgentX traces（约 5GB）。超 2GiB 由 CI 自动分卷（GitHub Release 单文件上限）。三种导入方式任选：

**方式一（推荐，全平台零命令行）**：双击 `ucm-accept.exe` 打开验收菜单，输入 `G` 启动浏览器 GUI → 右上 ⚙ 齿轮 →「离线资产包」→ 填入 `part-00` 文件路径 → 点「导入并校验」。分卷合并、解压、SHA256 校验一步完成，当前会话即时生效。

**方式二 Linux / macOS：**

```bash
cat ucm-assets-1.3.0.tar.gz.part-* > ucm-assets-1.3.0.tar.gz
sha256sum -c ucm-assets-1.3.0.tar.gz.sha256
tar -xzf ucm-assets-1.3.0.tar.gz -C ~/ucm-assets
UCM_ASSETS_DIR=~/ucm-assets ucm-accept --doctor --mock   # 校验 SHA256 与就绪状态
```

**离线拉取（无法直连 ghcr 时）**：直接 curl Release 附件导入——

[![Docker Image amd64 tar.gz](https://img.shields.io/badge/Docker%20Image-amd64%20tar.gz-2496ED?logo=docker&logoColor=white)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept-1.3.0-amd64.tar.gz) [![Docker Image arm64 tar.gz](https://img.shields.io/badge/Docker%20Image-arm64%20tar.gz-2496ED?logo=docker&logoColor=white)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept-1.3.0-arm64.tar.gz)

```bash
curl -L -o ucm-accept-1.3.0-amd64.tar.gz \
  https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept-1.3.0-amd64.tar.gz
docker load -i ucm-accept-1.3.0-amd64.tar.gz
```

**方式三 Windows PowerShell**（Windows 10+ 自带 tar）：

```powershell
cmd /c copy /b ucm-assets-1.3.0.tar.gz.part-00+ucm-assets-1.3.0.tar.gz.part-01 ucm-assets-1.3.0.tar.gz
Get-FileHash ucm-assets-1.3.0.tar.gz -Algorithm SHA256   # 与 .sha256 文件对照
tar -xzf ucm-assets-1.3.0.tar.gz -C C:\ucm-assets
$env:UCM_ASSETS_DIR = "C:\ucm-assets"
ucm-accept --doctor --mock
```

### 离线工具链（现场无外网安装用）

[![Wheelhouse amd64](https://img.shields.io/badge/Wheelhouse-amd64-6E6E73)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept-offline-tooling-1.3.0-amd64.tar.gz) [![Wheelhouse arm64](https://img.shields.io/badge/Wheelhouse-arm64-6E6E73)](https://github.com/ucm-system/ucm-accept/releases/download/v1.3.0/ucm-accept-offline-tooling-1.3.0-arm64.tar.gz)

全部产物 SHA256 见 `SHA256SUMS`。所有测试均由 EvalScope 原生引擎执行，本工具不做任何自研判定口径。
