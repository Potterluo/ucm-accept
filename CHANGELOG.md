# Changelog

## 1.3.1 — 2026-11-27

### Fixed

- **产品与引擎能力同步**：所有交付形态（Docker / exe / deb / rpm / 离线 wheelhouse）的
  EvalScope 安装从 `[perf,service]` 统一升级为 `[perf,eval,bfcl,agentx]==1.15.0`——
  此前容器/桌面版跑真实精度（BFCL 缺 bfcl 包）与 AgentX（缺 aiperf）会失败
- **移除已弃用的 gradio**：`[service]` extra 与安装不再引入；doctor 的「GUI 依赖」
  检查改为 fastapi / uvicorn（GUI 已是 FastAPI 单页前端）
- Dockerfile 移除 INSTALL_AGENTX 开关（agentx 默认内置于镜像）

## 1.3.0 — 2026-11-27

### Added

- **纯离线验收全链路**（隔离网络 + 本地资产包实测五项通过）：多轮场景 `dataset_path` 本地直读、精度数据集 `--dataset-args` 的 `local_path` 本地镜像（打包时物化为普通数据目录）、AgentX `--dataset-path` 直读 traces 快照；`agent.force_smoke` 内存受限环境降级开关（WSL 15GB 实测 full 变体 393 traces 会 OOM）
- **CLI 交互菜单重构**（对齐 GUI 能力面）：执行/配置/结果/工具四区；`[G]` 打开浏览器 GUI（与 CLI 共用配置与输出目录）；每项测试配置（并发档位/场景多选/SLA 探测区间/精度 limit 默认全量/Agent 上下文）、Tokenizer 内置列表选择、资产包导入校验、历史结果对比（复用 GUI 同款渲染）、HTML/PDF/zip 导出
- **GUI 离线资产包导入**：齿轮面板「离线资产包」卡片——填 tar.gz / part-00 分卷 / 目录路径，自动合并分卷、解压、SHA256 校验、会话内生效并刷新内置 tokenizer 下拉；CLI/GUI 共用 `assetpack` 模块（Windows/Linux 行为一致）
- **发版流水线整合**：`build-products`（Windows x64/ARM64 + Linux amd64/ARM64 原生 PyInstaller + Docker 双架构推 GHCR + manifest 合并）；`release.yml` 升级——按 OS 徽标下载表（`gen_release_notes.py`）、离线资产包 job（含 AgentX traces）、超 2GiB 自动分卷、镜像命名空间随仓库 owner；evalscope 全链路钉 `==1.15.0`
- **资产包清单扩容**：16 个 tokenizer（DeepSeek-V4 系列 / GLM-5.x / Qwen3.x / Kimi-K 系列 / MiniMax-M 系列）；CLI `--tokenizer-repo` 支持逗号分隔多仓库

### Fixed

- evalscope 触发式下载的静默失败：参数/校验错误显式报错（此前 `--work-dir`→`--outputs-dir`、`--api-url`→`--url`、缺 `--model` 等失败被吞，资产包长期缺多轮数据集）
- CI 组装阶段磁盘翻倍耗尽被 SIGTERM：`--move-caches`（同卷 rename）+ runner 磁盘预清理
- GitHub Release 单文件 2GiB 上限：超限自动 1900M 分卷，说明附 `cat` 合并命令
- Windows ARM64 打包：PowerShell 显式检查原生命令退出码（`$ErrorActionPreference` 不拦），避免 pip 失败后打出无引擎瘦包
- Gradio GUI 移除：单页 FastAPI 前端为唯一 GUI 形态（上游合并时保持）

## 1.2.0 — 2026-11-22

### Changed

- **README 全面重写为服务人员视角**：5 分钟上手（四形态安装照抄）、命令速查表、报错/结论对照表、离线使用简明步骤；开发者内容（EvalScope 对应、构建流水线、设计原则）收敛到附录

### Added

- **统一离线资产包（AssetHub）**：一次构建 `ucm-assets/`（tokenizers + datasets + evalscope-cache + SHA256 清单），所有交付形态共用——Docker 烤镜像/挂载、deb/rpm 固定路径、exe 同级 `assets/`、wheel 用 `UCM_ASSETS_DIR` 或 `app.assets_dir`；tokenizer 可只写模型名自动解析；数据集缓存自动注入 EvalScope 环境变量；`--doctor` 自动发现并逐文件校验清单；`prepare_assets.py --init` 生成包骨架
- **测试范围可配置**：新增 `run.items` 配置节；GUI 验收范围勾选框 +「执行所选测试项」按钮；CLI `--items perf,sla`（支持编号 `1,3-5`）、交互菜单多选输入与 `[T]` 范围编辑；报告结论按所选范围计算，部分执行时在报告中明确标注
- **测试配置中心（GUI）**：全部测试参数集中在一个「测试配置」面板（性能/SLA/多轮/精度/Agent/报告信息），改完即生效；支持保存到配置文件、导出、导入 YAML、恢复默认值；API Key 不落盘
- **精度数据集开关**：`accuracy.datasets.*.enabled`，现场可临时剔除单项数据集
- **CLI 配置落盘**：`--save-config` 保存当前生效配置，`--config` 复用
- **数据集注册表**：资产包 `datasets/registry.yaml` 纯配置声明新精度数据集/多轮场景（label/dataset/limit/enabled/description），GUI 数据集一览表（含描述、样本数、来源标注）自动更新；CI 增加资产包冒烟步骤
- **离线精度数据集直读**：资产包 `modelscope-cache` 经 `--dataset-dir` 传给 evalscope，命中本地缓存时不访问 hub；离线部署清单（libgomp 版本、chat_template.jinja、缓存目录属主、ModelScope 离线变量）固化至 docs/offline-build.md
- **prepare_assets**：跳过 ModelScope 缓存的 0 字节 `.lock` 文件（真实缓存目录校验误报）
- **离线精度全链路跑通**（真机 `--network=none` 容器验证）：`EVALSCOPE_CACHE`/`MODELSCOPE_CACHE` 强制指向资产包（覆盖镜像内置只读路径）；ModelScope SDK snapshot 自动布置到 evalscope 工作目录（LOCAL 分支完全离线）；datasets arrow 缓存移植方案与预热流程固化至 docs/offline-build.md
- **界面全面重设计**：统一设计系统（配色/阴影/圆角/动效）——渐变 Hero、彩色图标徽章与左侧主题色条、验收范围勾选芯片化、执行中卡片高亮扫光动画、状态徽章圆点化、终端风格日志、扁平化 Gradio 原生组件样式；更新 docs/gui-preview.png

### Changed

- CLI `--all` 语义：按 `run.items` 声明的范围执行（默认仍为全部五项）
- 报告概览新增「执行范围」；部分执行时结论口径为所选测试项
- 内置多轮预设转换为 OpenAI 消息数组格式（EvalScope 1.15 `custom_multi_turn` 实际要求；旧格式会导致 `produced no conversations`），文档注明资产包自定义多轮数据同格式

### Fixed（经 llama.cpp + Qwen2.5-0.5B 真机实测发现）

- `extract_score` 无法解析 EvalScope 1.15 报告——分数位于 `metrics[0].score` 数组内，walk 未递归 list 值；两遍精度全部解析失败
- 精度文本兜底正则误抓汇总表行内的 Num/Correct 等计数字段，改为取数据集行内最后一个百分比

## 1.1.0 — 2026-11-19

### Added

- Gradio GUI（浏览器、随机端口、无桌面自动降级为打印地址）
- 容器/堡垒机 CLI 菜单与 `--all` / `--item` 非交互模式
- 五项验收统一编排：基础性能、多轮对话、SLA、精度、Agent
- 统一自包含 HTML 报告：内嵌 SVG、原始命令、EvalScope 原生报告索引、打印/PDF
- 离线资产清单与现场自检 `--doctor`
- 标准打包流水线：wheel/sdist、Windows exe、Linux deb/rpm/portable tar、amd64/arm64 Docker 镜像与 multi-arch manifest
- 离线 wheelhouse（amd64/arm64）与干净环境安装验证

### Native EvalScope only

- 性能：`evalscope perf`
- 多轮：`evalscope perf --multi-turn --dataset custom_multi_turn`
- SLA：`evalscope perf --sla-auto-tune`（`p90_ttft` / `p90_tpot`）
- 精度：`evalscope eval`
- Agent：`evalscope perf --scenario agentx`

### Not included

- 多轮对话 transcript 回放（EvalScope 不提供，拒绝伪造）
- Agent 任务级完成率 / 工具调用成功率（AgentX 是服务级压测）
- 数据集与 tokenizer 本体（由离线构建机预热并按 `docs/offline-build.md` 固化）
