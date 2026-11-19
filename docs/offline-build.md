# 离线构建与交付手册

本文面向内部 CI / 交付构建人员。目标：产出**客户现网可直接使用、无需联网**的物料，并确保客户能用报告里的命令逐条复现。

> 工具本身不包含 EvalScope、数据集或 tokenizer。离线包由构建流水线把下列物料固化到镜像/安装包中。

---

## 一、物料清单

| 类别 | 建议路径 | 说明 |
|---|---|---|
| 工具源码 / wheel | `/opt/ucm-accept` | `pip install --no-index` 安装 |
| Python 运行时 | 镜像或 PyInstaller 内置 | 建议 Python 3.11（AgentX 要求 3.11–3.13） |
| EvalScope | venv | `evalscope[perf,service]>=1.15,<2`，Agent 场景加 `[agentx]` |
| Python wheels | `/opt/ucm-accept/wheelhouse` | `pip download` 产物，供离线重装/修复 |
| 数据集缓存 | `/opt/ucm-accept/assets/evalscope-cache` | EvalScope / ModelScope 缓存整目录 |
| Tokenizer | `/opt/ucm-accept/assets/tokenizers/<model>` | `config.yaml` 的 `perf.tokenizer_path` |
| 多轮预设 | 包内置 `resources/datasets/multiturn` | 随 wheel 安装 |
| 配置 | `/etc/ucm-accept/config.yaml` | 所有参数外置 |
| 资产清单 | `/opt/ucm-accept/assets/manifest.json` | SHA256 校验 |

### 数据集来源（EvalScope 1.15 内置）

| 验收项 | EvalScope 数据集名 | ModelScope ID |
|---|---|---|
| GPQA Diamond | `gpqa_diamond` | `AI-ModelScope/gpqa_diamond` |
| GSM8K | `gsm8k` | `AI-ModelScope/gsm8k` |
| LongBench-v2 | `longbench_v2` | `ZhipuAI/LongBench-v2` |
| BFCL-v3 | `bfcl_v3` | `AI-ModelScope/bfcl_v3` |
| AgentX 256K | `agentx` | `evalscope/cc-traces-weka-062126-256k` |

> 数据集加载由 EvalScope 负责。不要在工具层复制/改写数据格式；离线构建只负责把 EvalScope 实际使用的缓存目录完整打包，并记录哈希。

---

## 二、构建机（联网）流程

### 1. 准备 Python 与 wheelhouse

```bash
python3.11 -m venv /opt/ucm-build/venv
source /opt/ucm-build/venv/bin/activate
pip install --upgrade pip wheel

mkdir -p /opt/ucm-build/wheelhouse
pip download -d /opt/ucm-build/wheelhouse \
  "ucm-accept==1.1.0" \
  "evalscope[perf,service,agentx]>=1.15,<2"
```

如果从源码构建：

```bash
pip wheel -w /opt/ucm-build/wheelhouse .
```

### 2. 预热 EvalScope 数据与 tokenizer

在构建机上用 EvalScope 原生命令预热。**这一步必须使用与现场一致的 EvalScope 版本**，避免缓存格式差异。

```bash
export EVALSCOPE_CACHE=/opt/ucm-build/assets/evalscope-cache
export MODELSCOPE_CACHE=/opt/ucm-build/assets/modelscope-cache

# 数据集预热：指向任意可达的 OpenAI 兼容服务；limit 1 即可触发下载，不要求跑完。
evalscope eval \
  --model Qwen2.5-0.5B-Instruct \
  --api-url http://127.0.0.1:8801/v1 \
  --datasets gpqa_diamond gsm8k longbench_v2 bfcl_v3 \
  --limit 1 \
  --work-dir /tmp/warmup

# AgentX 256K 数据集预热（需要 aiperf 与 256K 服务；也可只下载数据集）
evalscope perf \
  --scenario '{"name":"agentx","mode":"smoke"}' \
  --model Qwen2.5-0.5B-Instruct \
  --tokenizer-path /opt/ucm-build/assets/tokenizers/Qwen2.5-0.5B-Instruct \
  --url http://127.0.0.1:8801/v1/chat/completions \
  --parallel 1
```

> 若构建机没有模型服务，可在内网部署一个最小 OpenAI 兼容 stub，仅用于触发 EvalScope 的数据集下载；**不要**把 stub 或预热结果作为验收数据。

### 3. 准备 tokenizer

```bash
mkdir -p /opt/ucm-build/assets/tokenizers
modelscope download --model Qwen/Qwen2.5-0.5B-Instruct \
  --local_dir /opt/ucm-build/assets/tokenizers/Qwen2.5-0.5B-Instruct
```

### 4. 生成资产清单

```bash
python scripts/prepare_assets.py \
  --assets-dir /opt/ucm-build/assets \
  --output /opt/ucm-build/assets/manifest.json
```

脚本会：

- 遍历 `assets/` 下文件，写 SHA256 与大小；
- 校验内置多轮 JSONL 可被 JSON 解析；
- 输出 `manifest.json`，供现场 `--doctor` 或安装脚本校验。

### 5. 虚跑校验

在构建机上先不接客户模型，用模拟引擎验证工具链：

```bash
ucm-accept --mock --fast --all --outputs /tmp/ucm-smoke
ucm-accept --doctor --mock
python scripts/verify_report.py /tmp/ucm-smoke/runs/*/report.json
```

这一步必须检查：

- 五项全部完成；
- `report.html` 存在、无外网 URL；
- 每项 `detail.command` 或 accuracy `commands` 非空；
- `report.json` 可被 `AcceptanceReport.load_json` 加载。

### 6. 打包

#### 6.1 Linux GUI / deb / rpm

```bash
bash scripts/build_linux.sh 1.1.0 amd64
bash scripts/build_linux.sh 1.1.0 arm64
```

依赖：

- `pyinstaller`
- `nfpm`（生成 deb/rpm）
- 对应架构的构建机（PyInstaller 不能交叉编译）

产物：

```text
dist/
├── ucm-accept-linux-amd64/          # PyInstaller onedir
├── ucm-accept_1.1.0_amd64.deb
└── ucm-accept-1.1.0-1.aarch64.rpm
```

deb 安装后：

```bash
sudo dpkg -i ucm-accept_1.1.0_amd64.deb
ucm-accept --doctor
ucm-accept --gui
```

桌面快捷方式见 `packaging/ucm-accept.desktop`。

#### 6.2 Windows exe

在 `windows-latest` 上：

```powershell
pip install -e ".[build]"
pyinstaller packaging/ucm-accept.spec
Compress-Archive -Path dist/ucm-accept -DestinationPath dist/ucm-accept-windows-x64.zip
```

产物为 `ucm-accept.exe` + `_internal` 目录。分发时整目录打包，不要只发单个 exe。

#### 6.3 双架构 Docker 镜像

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.com/ucm/ucm-accept:1.1.0 \
  --build-arg INSTALL_AGENTX=0 \
  --push .
```

离线构建时，把 wheelhouse 与 assets 放到构建上下文，使用：

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --build-arg OFFLINE=1 \
  --build-arg INSTALL_AGENTX=0 \
  -t registry.example.com/ucm/ucm-accept:1.1.0 \
  .
```

`Dockerfile` 在 `OFFLINE=1` 时只从 `wheelhouse/` 安装，不访问 PyPI。

运行：

```bash
docker run --rm -it \
  -v /data/ucm:/data \
  -e UCM_BASE_URL=http://172.17.0.1:8801/v1 \
  registry.example.com/ucm/ucm-accept:1.1.0 \
  --config /etc/ucm-accept/config.yaml --outputs /data/outputs
```

---

## 三、现场离线安装

### 3.1 容器（推荐，屏蔽麒麟服务器 openEuler 差异）

```bash
docker load -i ucm-accept-1.1.0-arm64.tar
docker run --rm -it \
  -v /data/ucm:/data \
  ucm-accept:1.1.0 \
  --config /etc/ucm-accept/config.yaml --outputs /data/outputs
```

若现场禁止 Docker，可使用 PyInstaller onedir + systemd/ssh 直接运行。

### 3.2 验证物料

```bash
ucm-accept --doctor --probe
```

应全部通过；若有 `EvalScope 版本`、`AgentX 依赖`、`Tokenizer` 警告，按提示补齐。

### 3.3 真实验收

```bash
ucm-accept --all --report /data/ucm-accept-report.html
```

或 GUI：

```bash
ucm-accept --gui --no-browser
```

---

## 四、构建校验清单

- [ ] `pip install --no-index --find-links wheelhouse` 可在无网环境完成
- [ ] EvalScope 版本 >= 1.15，`--doctor` 无失败项
- [ ] 四个精度数据集缓存齐全，`evalscope eval` 预热命令不触发下载
- [ ] AgentX 数据集缓存齐全，`--scenario agentx` 可离线启动
- [ ] tokenizer 路径存在且与 `config.yaml` 一致
- [ ] 内置多轮 JSONL 哈希与 `assets_manifest.json` 一致
- [ ] `--mock --fast --all` 虚跑通过，报告无外网依赖
- [ ] 双架构镜像均能 `--doctor`
- [ ] deb/rpm 在对应麒麟版本可安装、可启动 GUI/CLI
- [ ] Windows exe 在 Windows 10/11 可启动并打开浏览器
- [ ] 报告中的 `command.txt` 可在现场原样复现

---

## 五、常见问题

**Q：为什么报告里 Agent 没有“任务完成率”？**
A：EvalScope AgentX 是服务级长会话压测，不输出任务质量分。工具不自行计算；需要任务级指标请另配 Agent 评测任务集。

**Q：为什么多轮对话没有回放内容？**
A：EvalScope 多轮压测只输出统计指标。工具不生成伪造记录，保留原始 EvalScope 报告供人工复核。

**Q：SLA 的 P90 参数在旧版 EvalScope 不存在怎么办？**
A：升级到 >= 1.15；或在 `config.yaml` 将 `sla.mode` 设为 `verify`，只测目标并发（200）的 P90。

**Q：能否只用 CLI，不安装 Gradio？**
A：可以。GUI 依赖是可选 extra，CLI 与报告不依赖 Gradio。

**Q：报告能直接发邮件吗？**
A：可以。`report.html` 自包含，无外网依赖；图表为内嵌 SVG。原始数据目录较大，按需单独打包。
