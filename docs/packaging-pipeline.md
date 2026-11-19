# 打包与验证流水线

仓库：<https://github.com/ucm-system/ucm-accept>（private）
产物：<https://github.com/ucm-system/ucm-accept/releases>
镜像：`ghcr.io/ucm-system/ucm-accept:<version>` 与 `:latest`

> 仓库已 public，但 GHCR 包是在仓库 private 时创建的，包可见性可能仍为 private。
> 无 GHCR 登录的客户请直接使用 Release 中的 `ucm-accept-<version>-<arch>.tar.gz`，`docker load` 即可；
> 或由组织管理员在 Package settings 中把包改为 public。

所有二进制包与镜像均由 GitHub Actions 从源码构建，不使用本地交叉编译，也不使用 QEMU 模拟：
amd64 使用 `ubuntu-latest`，arm64 使用 GitHub 原生 `ubuntu-24.04-arm`。

---

## 一、日常 CI（`.github/workflows/ci.yml`）

触发：push 到 `main` / PR / 手动。

| Job | 内容 | 目的 |
|---|---|---|
| `actionlint` | actionlint + shellcheck | 防止 workflow / shell 语法和常见错误 |
| `test (3.10–3.13)` | `ruff check` + `pytest -q` | 四版本兼容性与 62 项测试 |
| `virtual acceptance (mock)` | `--doctor --mock`、`--mock --fast --all`、报告校验 | 五项全流程虚跑 |
| `build wheel` | `python -m build`、`twine check`、干净 venv 安装、`pip check`、CLI smoke | Python 打包标准校验 |
| `windows exe` | 手动/tag 触发，构建并上传 zip | Windows 产物 |
| `docker buildx` | 手动/tag 触发 | 镜像构建模板 |

---

## 二、发布流水线（`.github/workflows/release.yml`）

触发：

```bash
# tag
git tag v1.1.0 && git push origin v1.1.0

# 或手动指定版本
gh workflow run release.yml --ref main -f version=1.1.0
```

### 构建/验证矩阵

| 产物 | Runner | 构建 | 验证 |
|---|---|---|---|
| wheel + sdist | ubuntu-latest | `python -m build` | `twine check`、干净 venv 安装、`pip check`、`--version`、mock 单项 |
| Linux amd64 deb/rpm/tar | ubuntu-latest | PyInstaller + nfpm | 可执行文件 `--version`、mock 单项、`dpkg-deb --info/--contents`、`rpm -qip` |
| Linux arm64 deb/rpm/tar | **ubuntu-24.04-arm** | 同上，原生 ARM | 同上，原生运行 |
| Windows x64 exe | windows-latest | PyInstaller onedir | exe `--version`、mock 单项、报告存在 |
| offline wheelhouse amd64 | ubuntu-latest | `pip download` + 源码包装 wheel | `pip install --no-index --find-links` + mock 单项 |
| offline wheelhouse arm64 | **ubuntu-24.04-arm** | 同上 | 同上，原生 ARM |
| Docker amd64 | ubuntu-latest | Dockerfile（内置 EvalScope） | 容器内 `--version`、`--doctor --mock`、mock 单项 |
| Docker arm64 | **ubuntu-24.04-arm** | 同上 | 同上，原生 ARM |
| 多架构 manifest | ubuntu-latest | `docker manifest create` | `docker manifest inspect` |
| GitHub Release | ubuntu-latest | 下载各 artifact、SHA256SUMS | 发布全部 assets |

### 产物命名

```text
ucm_accept-1.1.0-py3-none-any.whl
ucm_accept-1.1.0.tar.gz
ucm-accept-windows-x64.zip
ucm-accept_1.1.0_amd64.deb
ucm-accept_1.1.0_arm64.deb
ucm-accept-1.1.0-1.x86_64.rpm
ucm-accept-1.1.0-1.aarch64.rpm
ucm-accept-linux-amd64.tar.gz       # PyInstaller portable
ucm-accept-linux-arm64.tar.gz
ucm-accept-1.1.0-amd64.tar.gz       # docker save 离线镜像
ucm-accept-1.1.0-arm64.tar.gz
ucm-accept-offline-tooling-1.1.0-amd64.tar.gz
ucm-accept-offline-tooling-1.1.0-arm64.tar.gz
SHA256SUMS
```

### 校验和

```bash
gh release download v1.1.0
sha256sum -c SHA256SUMS
```

---

## 三、标准依据

- Python：PEP 517/518（`pyproject.toml`）、`python -m build`、`twine check`、干净 venv 安装、`pip check`
- Debian：`dpkg-deb --info` / `--contents`，安装路径 `/opt/ucm-accept`、`/etc/ucm-accept`、`/usr/bin`
- RPM：`rpm -qip`，架构映射 `amd64 → x86_64`、`arm64 → aarch64`
- Windows：PyInstaller one-dir，必须整目录分发，不能只发单个 exe
- OCI：单个 arch 原生构建并 push，再用 `docker manifest` 合并为多架构 manifest；同时 `docker save` 离线 tar
- 供应链：Release 附 `SHA256SUMS`；所有产物来自同一 tag/commit

---

## 四、仍需人工准备的内容

Actions 构建的是**工具与运行时**，不包含 GB 级数据集与模型 tokenizer：

1. 在联网构建机按 [`offline-build.md`](offline-build.md) 预热 EvalScope 数据集缓存；
2. 下载目标 tokenizer；
3. 用 `scripts/prepare_assets.py` 生成 SHA256 清单；
4. 将 `assets/` 挂载/复制到镜像或安装包。

这样客户现场只需 `docker load` / `dpkg -i` / 解压 exe，不再访问外网。
