# UCM 推理加速验收工具

**给交付/服务人员的客户现网验收工具**：填一个服务地址，点一下运行，得到一份能直接交给客户的验收报告。

- 被测对象：任意 OpenAI 兼容的大模型推理服务（vLLM / SGLang / TGI 等部署的服务）
- 验收内容：基础性能、多轮对话、SLA 达标、精度一致性、Agent 长会话（五项，可选）
- 全程离线可用：客户现场没有外网，不影响工具本身运行
- 报告为单文件 HTML：图表、原始命令、原始数据索引全部内嵌，直接发客户

![UCM 验收工具 GUI](docs/gui-preview.png)

> 你**不需要**懂压测、懂 EvalScope、懂 Python。所有参数已按验收口径预设，照着下面三步做即可。

---

## 一、5 分钟上手（照着做就行）

### 第 0 步：确认你手里的东西

| 你拿到的 | 适用场景 | 对应章节 |
|---|---|---|
| 一个 `.zip`（`ucm-accept-windows-x64.zip`，里面有 `ucm-accept.exe` 和 `_internal` 目录） | Windows 客户机 | 2.1 |
| 一个 `.deb` / `.rpm` / `.tar.gz` | Linux 客户机 | 2.2 |
| 一个 Docker 镜像 tar 或镜像地址 | 服务器只允许容器 | 2.3 |
| 一个 `ucm-accept-offline-tooling-<版本>-<架构>.tar.gz`（离线依赖 + 工具 + 指南全在内） | 服务器有 Python、无外网 | 2.4 |

### 第 1 步：安装（按你的场景选一个，只做一次）

**2.1 Windows**

1. 把 zip **整个解压**（不要只拖出 exe 单个文件）；
2. 按 `Win+R`，输入 `cmd` 回车；
3. 在黑窗口里，用 `cd` 进入解压出来的目录（zip 里有示例路径），照抄：

```bat
cd /d D:\ucm-accept
ucm-accept.exe --gui
```

浏览器会自动打开验收工具页面。关掉窗口即退出。

**2.2 Linux（有管理员权限）**

```bash
# deb 系（麒麟 V10 / Ubuntu / Debian）：
sudo dpkg -i ucm-accept_1.2.0_amd64.deb
# rpm 系（openEuler / 麒麟中标版）：
sudo rpm -ivh ucm-accept-1.2.0-1.x86_64.rpm
# tar 包（没有管理员权限时，解压即用）：
tar -xzf ucm-accept-linux-amd64.tar.gz && ./ucm-accept-linux-amd64/ucm-accept --gui
```

装好后：桌面出现「UCM 验收工具」图标（双击打开），或在终端照抄：

```bash
ucm-accept --gui
```

**2.3 容器（服务器只允许 Docker 时）**

```bash
docker load -i ucm-accept-1.2.0-amd64.tar          # 导入镜像
docker run --rm -it -p 8080:8080 \
  -v /data/ucm:/data \
  ucm-accept:1.2.0 --gui --host 0.0.0.0 --port 8080
```

然后在**你自己的电脑浏览器**打开 `http://<服务器IP>:8080`。
（不想开页面也可以：去掉 `--gui --host 0.0.0.0 --port 8080`，直接进入命令行菜单。）

**2.4 有 Python 的服务器（离线工具包，推荐）**

offline-tooling 包里已经配好：全部依赖 wheel、验收工具本体、离线配置模板、本指南。解压后照抄三条命令：

```bash
tar -xzf ucm-accept-offline-tooling-1.2.0-amd64.tar.gz -C ucm-accept-offline && cd ucm-accept-offline
python -m venv .venv && source .venv/bin/activate
pip install --no-index --find-links wheelhouse "ucm-accept==1.2.0" "evalscope[perf,service]>=1.15,<2"
```

装完先自检，再打开界面：

```bash
ucm-accept --doctor --probe
ucm-accept --gui        # 浏览器打开；纯命令行就去掉 --gui
```

### 第 2 步：填两个空，点「检测连通」

打开页面后，只需要动两处：

1. **服务地址**：被测推理服务的地址，形如 `http://10.1.2.3:8000/v1`（问客户/部署同学要，注意以 `/v1` 结尾）；
2. **模型名称**：要验收的模型名（不确定就先点「检测连通」，工具会提示实际可用的名称）。

然后点 **「检测连通」**：

- 显示绿色 `● 服务连通` → 继续第 3 步；
- 显示红色 → 看本文第三章「出问题了」对照表。

### 第 3 步：点运行，等结果

- 页面中部有 **5 张测试卡片**，每张都可单独点「运行」；
- 或直接点绿色大按钮 **「执行所选测试项」**（默认五项全选，按需取消勾选）；
- 每项测试的预计耗时显示在卡片上（默认口径合计约 1 小时）；
- 全部跑完后，页面下方自动生成**验收报告**，点「下载完整 HTML 报告」即可保存/发客户。

> 首次接触不知道怎么选？**默认全选就是标准验收口径**（64K 上下文、200 并发、SLA 10s/50ms、精度双跑），不用改任何参数。

---

## 二、日常使用速查

### 命令速查（GUI 不方便时的等价命令）

| 想做什么 | 照抄（替换尖括号部分） |
|---|---|
| 打开图形界面 | `ucm-accept --gui` |
| 不打开页面跑完全部 | `ucm-accept --all` |
| 只跑性能测试 | `ucm-accept --items perf` |
| 跑性能 + SLA | `ucm-accept --items perf,sla` |
| 指定服务地址 | `ucm-accept --all --base-url http://10.1.2.3:8000/v1 --model 模型名` |
| 命令行菜单（服务器/堡垒机） | `ucm-accept` |
| 现场自检（装完先跑这个） | `ucm-accept --doctor --probe` |
| 查看最近一次报告 | `ucm-accept` 菜单里按 `R` |
| 保存本次参数下次复用 | `ucm-accept --save-config my.yaml`，之后加 `--config my.yaml` |

### CLI 菜单（纯命令行环境）

```
[1] 基础性能测试      ← 输入数字单独跑
[2] 多轮对话测试
[3] SLA 自动调优
[4] 精度测试
[5] Agent 场景测试
[A] 执行所选测试项     ← 按 T 先勾选范围，再按 A
[T] 选择要执行的测试项 ← 例：输入 1,3-5
[R] 查看最近报告
[S] 修改服务地址 / 模型
[Q] 退出
```

### 报告在哪、怎么用

- GUI：页面底部「验收报告」实时预览，「下载完整 HTML 报告」保存；
- CLI：命令行最后会打印 `报告：<路径>`；输出根目录默认 `./outputs`，最新一次在 `outputs/runs/<任务号>/report.html`；
- 报告是**单个 HTML 文件**：双击浏览器打开即可，微信/邮件直接发客户，无需带其他文件；
- 需要正式 PDF：浏览器打开报告 → `Ctrl+P` → 另存为 PDF（或装了 weasyprint/chromium 时点 GUI 的「导出 PDF」）。

### 每次验收前 30 秒检查单

1. `ucm-accept --doctor --probe` 全绿（红项按第三章处理）；
2. 服务地址、模型名与客户确认一致；
3. GPU 推理服务已就绪、有并发余量（验收会真实打流量）；
4. 磁盘剩余 ≥ 2GB（报告与原始数据）。

---

## 三、出问题了？按这里排查

### 连通检测失败（红色）

| 现象 | 原因 | 怎么办 |
|---|---|---|
| `无法连接服务 http://…` | 地址写错 / 服务没起 / 端口不通 | 在服务器上照抄 `curl http://<地址>/models`，通不了就找部署同学 |
| 地址末尾不是 `/v1` | 常见笔误 | 改成 `http://<IP>:<端口>/v1` |
| 连通但模型名报错 | 模型名与服务不一致 | 浏览器打开 `http://<地址>/models`，把列表里的名字抄进「模型名称」 |

### 自检（doctor）出现红/黄项

| 检查项 | 说明 | 怎么办 |
|---|---|---|
| EvalScope 未找到 | 缺压测引擎 | 按 2.4 离线安装；或 `pip install "evalscope[perf]>=1.15"` |
| EvalScope 版本 < 1.15 | 旧版缺 SLA 参数 | 升级 evalscope；或临时把 SLA 模式改为 `verify` |
| Tokenizer 不存在 | 资产包未带 tokenizer | 找构建同学要 `ucm-assets` 资产包，放到工具同级 `assets/` 目录 |
| 数据集缓存 缺失 | 精度数据集未预热 | 联网机器预热一次（见离线文档），或现场只跑性能/SLA/多轮 |
| 服务连通 失败 | 同上连通检测 | 见上表 |

### 验收结论看不懂？

| 结论 | 含义 | 你要做的 |
|---|---|---|
| 通过 | 全部达标 | 下载报告交客户 |
| 有条件通过 | 有黄项（如两遍精度略有波动） | 看报告黄项说明，与客户确认口径 |
| 不通过 | 有红项（指标未达 SLA / 请求失败） | 看报告对应章节的差距说明，转给调优同学 |
| 未完成 | 中途取消/出错 | 看日志（GUI 日志区 / `outputs/runs/<任务号>/run.log`）排除后重跑 |

### 其他常见问题

- **页面打不开（远程服务器）**：启动时加 `--host 0.0.0.0 --port 8080`，浏览器访问 `http://<服务器IP>:8080`，防火墙放行该端口；
- **想换默认参数**（并发/上下文/阈值）：GUI「测试配置」面板可改、可保存；不要直接改软件内置文件；
- **报告目录想换地方**：GUI「测试配置」或 `--outputs /data/xxx`；
- **想加自家的测试数据集**：见离线文档的「数据集注册表」，纯配置、不用改代码。

---

## 四、离线环境（客户现场无外网）

工具本身、依赖、数据集、tokenizer **全部离线可用**，前提是拿到两样东西：

1. **工具安装包**（第一章任选一种形态）；
2. **统一资产包 `ucm-assets/`**（构建同学产出）：内含 tokenizer、多轮预设、精度数据集缓存和 SHA256 清单。

使用方法（三种形态通用）：

- Docker：`-v /data/ucm-assets:/opt/ucm-accept/assets:ro` 挂载即可；
- deb/rpm：解压到 `/opt/ucm-accept/assets`（工具自动发现）；
- Windows exe / portable tar：改名为 `assets/` 放在 exe 同级（自动发现）；
- 其他：环境变量 `UCM_ASSETS_DIR=<资产包路径>`，或 GUI「测试配置」里填。

装好后第一件事永远是：

```bash
ucm-accept --doctor --probe
```

工具会自动发现资产包、逐文件校验 SHA256、检查 tokenizer 与数据集缓存，全部 ✓ 即可开始验收。

> 交付包组装、资产包构建、离线踩坑清单（libgomp 版本、chat template、ModelScope 离线变量等）见 **[docs/offline-build.md](docs/offline-build.md)**（给构建同学）。

---

## 五、五项验收是什么（向客户解释用）

| 验收项 | 一句话说明 | 默认口径 | 预计耗时 |
|---|---|---|---|
| 基础性能 | 64K 长输入下的吞吐 / 首字延迟 / 逐字延迟 | 20 并发 × 200 请求 | ~5 分钟 |
| 多轮对话 | 多轮连续会话的稳定性与 KV Cache 命中 | 12 组 × 2–5 轮 | ~10 分钟 |
| SLA 自动调优 | 实测 P90 是否满足时延阈值（TTFT<10s、TPOT<50ms） | 200 并发 | ~8 分钟 |
| 精度测试 | 数学/问答/长文本/工具调用得分，两遍对比验证一致性 | 4 数据集 × 2 遍 | ~20 分钟 |
| Agent 场景 | 256K 超长会话服务级压测 | 15 分钟持续负载 | ~15 分钟 |

所有数值均来自 [EvalScope](https://github.com/modelscope/evalscope) 原生输出，本工具只做编排与呈现，报告内附可复现的原始命令。

---

## 附录（给构建 / 维护 / 开发人员）

- **设计原则**：测试逻辑全部由 EvalScope 原生承担（perf / eval / sla-auto-tune / AgentX），本工具不实现任何自研压测或评分算法；模拟模式（`--mock --fast`）用于演示与 CI 虚跑，报告会明确标注「不作为验收结论」。
- **配置项全表**：[`ucm_accept/resources/config.yaml`](ucm_accept/resources/config.yaml) 内注释即文档；支持 `${ENV:-默认值}` 展开；GUI「测试配置」是它的可视化子集。
- **与 EvalScope 对应关系**：性能 `evalscope perf`；多轮 `--multi-turn --dataset custom_multi_turn`；SLA `--sla-auto-tune`（p90_ttft/p90_tpot）；精度 `evalscope eval`；Agent `--scenario agentx`。可用 `evalscope.<xx>_command` 整体覆写 argv 适配客户版本。
- **离线资产构建**：[docs/offline-build.md](docs/offline-build.md)（统一资产包 `ucm-assets/` 一次构建、Docker/deb/exe/wheel 四形态共用；含实测踩坑清单）。
- **打包流水线**：[docs/packaging-pipeline.md](docs/packaging-pipeline.md)。CI 产物：wheel/sdist、Windows exe、Linux deb/rpm/portable tar、amd64/arm64 Docker 镜像（GHCR）、离线 wheelhouse、SHA256SUMS。
- **本地开发**：

```bash
pip install -e ".[dev,gui]"
ruff check ucm_accept tests scripts && pytest -q      # 100+ 用例
ucm-accept --mock --fast --all                        # 不接模型虚跑全流程
```

- **版本**：[CHANGELOG.md](CHANGELOG.md)。当前 1.2.0。
