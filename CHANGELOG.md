# Changelog

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
