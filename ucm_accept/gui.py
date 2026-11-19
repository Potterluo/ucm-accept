from __future__ import annotations

import html
import re
import socket
from pathlib import Path
from typing import Any

from . import __version__
from .config import Config
from .errors import UCMAcceptError
from .events import ProgressEvent
from .models import ITEM_BY_KEY, ITEM_KEYS, STATUS_LABELS, AcceptanceReport, Status
from .service import AcceptanceService
from .utils import find_latest_report, has_desktop

CSS = r"""
:root{--ucm-ink:#0f172a;--ucm-muted:#5b6779;--ucm-line:#dde3ec;--ucm-brand:#0b2a4a;--ucm-teal:#0f9d8a}
body,.gradio-container{background:#f3f6fb!important}
.gradio-container{max-width:1320px!important;margin:0 auto!important;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei","Noto Sans CJK SC",sans-serif!important}
.ucm-hero{background:linear-gradient(120deg,#07192c 0%,#0e3456 58%,#0f5a68 100%);border-radius:18px;padding:26px 30px;color:#fff;margin:8px 0 14px;box-shadow:0 10px 28px rgba(15,23,42,.14)}
.ucm-hero .eyebrow{font-size:11px;letter-spacing:.18em;color:#8fd8cf!important;font-weight:700}
.ucm-hero h1{margin:6px 0 4px;font-size:27px;line-height:1.25;font-weight:760;color:#fff!important}
.ucm-hero p{margin:0;color:#cfe1f2!important;font-size:13px}
.ucm-hero .chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.ucm-chip{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.22);border-radius:999px;padding:3px 11px;font-size:11.5px;color:#e8f7f4}
.ucm-mode-mock{background:#b45309!important;border-color:#f3d19b!important;color:#fff!important}
.ucm-endpoint{background:#fff;border:1px solid var(--ucm-line);border-radius:14px;padding:14px 16px 6px;margin-bottom:14px}
.ucm-section-title{margin:14px 0 8px;font-size:16px;font-weight:700;color:var(--ucm-ink);display:flex;align-items:center;gap:8px}
.ucm-section-title small{font-weight:400;color:var(--ucm-muted);font-size:12px}
.test-card{background:#fff!important;border:1px solid var(--ucm-line)!important;border-radius:14px!important;padding:10px 12px!important;box-shadow:0 2px 8px rgba(15,23,42,.035)!important;min-height:180px}
.test-card:hover{box-shadow:0 6px 18px rgba(15,23,42,.08)!important}
.card-top{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.card-icon{font-size:22px;line-height:1}
.card-title{font-weight:720;font-size:15px;margin-top:6px}
.card-eta{font-size:11.5px;color:var(--ucm-muted);background:#f1f5f9;border-radius:999px;padding:2px 8px;white-space:nowrap}
.card-desc{font-size:12.5px;color:var(--ucm-muted);line-height:1.55;margin:6px 0 8px;min-height:58px}
.status-line{margin-top:4px}
.ucm-pill{display:inline-flex;align-items:center;gap:4px;border-radius:999px;padding:2px 9px;font-size:11.5px;font-weight:650}
.ucm-pill.passed{color:#15803d;background:#eaf7ee;border:1px solid #b7e4c3}
.ucm-pill.warning{color:#b45309;background:#fff7e6;border:1px solid #f2d19a}
.ucm-pill.failed{color:#b91c1c;background:#fef2f2;border:1px solid #f2c0c0}
.ucm-pill.pending,.ucm-pill.skipped{color:#475569;background:#f1f5f9;border:1px solid #dbe3ec}
.ucm-pill.running{color:#1d4ed8;background:#eff6ff;border:1px solid #bfdbfe}
.status-summary{font-size:11.5px;color:var(--ucm-muted);margin-top:5px;line-height:1.45;min-height:32px}
.run-all{background:linear-gradient(90deg,#0f5a68,#0f9d8a)!important;border:none!important;color:#fff!important;font-weight:700!important;min-height:44px!important}
.run-all:hover{filter:brightness(1.06)}
.ucm-summary{background:#fff;border:1px solid var(--ucm-line);border-left:5px solid #0f9d8a;border-radius:12px;padding:14px 18px;margin:10px 0}
.ucm-summary .label{font-size:11px;color:var(--ucm-muted);letter-spacing:.08em}
.ucm-summary .verdict{font-size:24px;font-weight:800;line-height:1.2}
.ucm-summary ul{margin:6px 0 0;padding-left:20px;color:var(--ucm-muted);font-size:12.5px}
.ucm-summary .meta{font-size:11.5px;color:var(--ucm-muted);margin-top:7px}
.ucm-report-frame{width:100%;height:780px;border:1px solid var(--ucm-line);border-radius:12px;background:#fff}
.ucm-log textarea{font-family:"SFMono-Regular",Consolas,monospace!important;font-size:12px!important;background:#0f172a!important;color:#dbeafe!important;border-radius:10px!important}
.ucm-hint{font-size:12px;color:var(--ucm-muted);margin:2px 0 8px}
.ucm-footer{text-align:center;color:#8090a6;font-size:11.5px;padding:18px 0 8px}
.ucm-probe-ok{color:#15803d;font-size:12.5px;margin-top:2px}
.ucm-probe-bad{color:#b91c1c;font-size:12.5px;margin-top:2px}
"""


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _pill(status: Status) -> str:
    return f'<span class="ucm-pill {status.value}">{_esc(STATUS_LABELS[status])}</span>'


def _status_html(service: AcceptanceService, key: str, report: AcceptanceReport | None = None) -> str:
    report = report or service.current_report()
    item = report.items.get(key) if report else None
    if item is None:
        return '<div class="status-line"><span class="ucm-pill pending">○ 待执行</span><div class="status-summary">尚未执行</div></div>'
    summary = item.summary or item.error or "—"
    if item.status == Status.RUNNING:
        summary = "执行中…"
    return (
        f'<div class="status-line">{_pill(item.status)}'
        f'<div class="status-summary">{_esc(summary)}</div></div>'
    )


def _summary_html(service: AcceptanceService) -> str:
    report = service.current_report()
    if report is None:
        return (
            '<div class="ucm-summary"><div class="label">验收结论</div>'
            '<div class="verdict" style="color:#64748b">尚未执行</div>'
            '<div class="meta">配置服务地址后点击任意“运行”，或直接执行全部验收。</div></div>'
        )
    color = report.conclusion_color
    reasons = "".join(f"<li>{_esc(reason)}</li>" for reason in report.reasons) or "<li>暂无</li>"
    mode = "实机" if report.mode == "live" else "模拟（不作为验收依据）"
    return (
        f'<div class="ucm-summary" style="border-left-color:{color}">'
        f'<div class="label">验收结论 · {_esc(mode)}</div>'
        f'<div class="verdict" style="color:{color}">{_esc(report.conclusion)}</div>'
        f"<ul>{reasons}</ul>"
        f'<div class="meta">任务 {_esc(report.run_id)} · 开始 {_esc(report.started_at)} · 输出 {_esc(report.output_dir)}</div>'
        "</div>"
    )


def _report_frame(service: AcceptanceService) -> str:
    path = service.report_path()
    if not path:
        return (
            '<div style="border:1px dashed #cbd5e1;border-radius:12px;padding:36px;text-align:center;'
            'color:#64748b;background:#fbfdff">执行测试后，这里会显示完整验收报告。</div>'
        )
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        content = ""
    if not content:
        return '<div class="ucm-hint">报告尚未生成。</div>'
    return (
        f'<iframe class="ucm-report-frame" title="验收报告" srcdoc="{_esc(content)}"></iframe>'
        '<div class="ucm-hint">报告为离线自包含 HTML，可在下方下载或在新窗口打印为 PDF。</div>'
    )


def _download_value(service: AcceptanceService) -> str | None:
    path = service.report_path()
    return str(path) if path else None


def _format_event(event: ProgressEvent) -> str:
    prefix = {
        "start": "▶",
        "success": "✓",
        "warning": "!",
        "error": "✗",
        "command": "$",
    }.get(event.level, "·")
    message = event.message.strip()
    if event.level == "command" and len(message) > 260:
        message = message[:257] + "…"
    return f"[{event.overall * 100:5.1f}%] {prefix} {message}"


def _status_tuple(
    service: AcceptanceService, report: AcceptanceReport | None = None
) -> tuple[str, ...]:
    return tuple(_status_html(service, key, report) for key in ITEM_KEYS)


def _all_outputs(
    service: AcceptanceService,
    logs: list[str],
    stage: str,
) -> tuple[Any, ...]:
    return (
        *_status_tuple(service),
        stage,
        "\n".join(logs[-160:]),
        _summary_html(service),
        _report_frame(service),
        _download_value(service),
    )


def _parse_parallel(text: str) -> list[int]:
    parts = [part for part in re.split(r"[,，、\s]+", str(text).strip()) if part]
    if not parts:
        raise UCMAcceptError("并发梯度不能为空，例如 20 或 10,20,40")
    values = []
    for part in parts:
        try:
            value = int(part)
        except ValueError as exc:
            raise UCMAcceptError(f"并发梯度包含非法值：{part}") from exc
        if value <= 0:
            raise UCMAcceptError("并发梯度必须大于 0")
        values.append(value)
    return values


def _map_sla_mode(label: str) -> str:
    return "auto_tune" if str(label).startswith("auto_tune") else "verify"


def _advanced_overrides(
    perf_parallel: str,
    perf_number: float,
    input_length: float,
    max_tokens: float,
    hit_rate: float,
    tokenizer: str,
    sla_mode: str,
    sla_concurrency: float,
    ttft_limit_s: float,
    tpot_limit_ms: float,
    accuracy_runs: float,
    accuracy_limit: float,
    mt_parallel: float,
    mt_conversations: float,
    agent_parallel: float,
    agent_duration_s: float,
) -> dict[str, Any]:
    parallel = _parse_parallel(perf_parallel)
    number = int(perf_number or 200)
    prompt = int(input_length or 65536)
    output_tokens = int(max_tokens or 256)
    if number <= 0 or prompt <= 0 or output_tokens <= 0:
        raise UCMAcceptError("请求数、输入长度、最大输出长度必须大于 0")
    if not 0 <= float(hit_rate) < 1:
        raise UCMAcceptError("命中率必须在 [0, 1) 之间")
    target_conc = int(sla_concurrency or 200)
    if target_conc <= 0:
        raise UCMAcceptError("SLA 目标并发必须大于 0")
    ttft_ms = float(ttft_limit_s or 10) * 1000
    tpot_ms = float(tpot_limit_ms or 50)
    if ttft_ms <= 0 or tpot_ms <= 0:
        raise UCMAcceptError("SLA 阈值必须大于 0")
    runs = int(accuracy_runs or 2)
    if runs < 1:
        raise UCMAcceptError("精度执行遍数至少为 1")
    overrides: dict[str, Any] = {
        "perf": {
            "parallel": parallel,
            "number": number,
            "min_prompt_length": prompt,
            "max_prompt_length": prompt,
            "max_tokens": output_tokens,
            "tokenizer_path": tokenizer.strip(),
        },
        "defaults": {"hit_rate": float(hit_rate)},
        "sla": {
            "mode": _map_sla_mode(sla_mode),
            "target": {
                "context_length": prompt,
                "concurrency": target_conc,
                "ttft_p90_ms": ttft_ms,
                "tpot_p90_ms": tpot_ms,
            },
            "verify": {"number": number},
        },
        "accuracy": {"runs": runs},
        "multiturn": {
            "parallel": int(mt_parallel or 4),
            "conversations": int(mt_conversations or 12),
        },
        "agent": {
            "parallel": int(agent_parallel or 4),
            "duration_s": int(agent_duration_s or 900),
        },
    }
    if int(accuracy_limit or 0) > 0:
        overrides["accuracy"]["datasets"] = {
            key: {"limit": int(accuracy_limit)}
            for key in ("gpqa", "gsm8k", "longbench_v2", "bfcl_v3")
        }
    return overrides


def _parse_scenario(value: str) -> str:
    return {"对话": "dialogue", "代码": "code", "办公": "office"}.get(value, value or "dialogue")


def build_demo(service: AcceptanceService):
    try:
        import gradio as gr
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise UCMAcceptError("未安装 gradio，无法启动 GUI。请安装 ucm-accept[gui]。") from exc

    config = service.config
    mode_text = "EvalScope 实机" if service.mode == "live" else "模拟演示（不会产生真实请求）"
    mode_class = "" if service.mode == "live" else " ucm-mode-mock"
    theme = gr.themes.Soft(primary_hue="teal", neutral_hue="slate")

    with gr.Blocks(title=f"{config.get('app.title')} v{__version__}") as demo:
        gr.HTML(
            f"""
            <div class="ucm-hero">
              <div class="eyebrow">UCM INFERENCE ACCELERATION · ACCEPTANCE</div>
              <h1>{_esc(config.get('app.title'))}</h1>
              <p>{_esc(config.get('app.subtitle'))}</p>
              <div class="chips">
                <span class="ucm-chip{mode_class}">执行引擎：{_esc(mode_text)}</span>
                <span class="ucm-chip">底层：EvalScope 原生 perf / eval / AgentX</span>
                <span class="ucm-chip">离线可用 · 报告自包含</span>
              </div>
            </div>
            """
        )

        with gr.Group(elem_classes="ucm-endpoint"):
            with gr.Row():
                base_url = gr.Textbox(
                    label="服务地址",
                    value=str(config.get("endpoint.base_url")),
                    placeholder="http://127.0.0.1:8801/v1",
                    scale=3,
                )
                model = gr.Textbox(
                    label="模型名称",
                    value=str(config.get("endpoint.model")),
                    placeholder="Qwen2.5-0.5B-Instruct",
                    scale=2,
                )
                api_key = gr.Textbox(
                    label="API Key（可选）",
                    value=str(config.get("endpoint.api_key", "") or ""),
                    type="password",
                    scale=2,
                )
            with gr.Row():
                probe_btn = gr.Button("检测连通", variant="secondary", scale=0)
                probe_status = gr.HTML(
                    '<div class="ucm-hint">尚未检测。点击“检测连通”验证地址、模型与上下文窗口。</div>'
                )

        gr.HTML(
            '<div class="ucm-section-title">验收项目 <small>点击单项运行，或一键按顺序跑完五项</small></div>'
        )
        status_components: dict[str, Any] = {}
        run_buttons: dict[str, Any] = {}
        scenarios: dict[str, Any] = {}
        for row_keys in (("perf", "multiturn", "sla"), ("accuracy", "agent")):
            with gr.Row(equal_height=False):
                for key in row_keys:
                    meta = ITEM_BY_KEY[key]
                    with gr.Column(elem_classes="test-card"):
                        gr.HTML(
                            f"""
                            <div class="card-top">
                              <div><div class="card-icon">{meta.icon}</div>
                              <div class="card-title">{_esc(meta.name)}</div></div>
                              <div class="card-eta">{_esc(meta.eta)}</div>
                            </div>
                            <div class="card-desc">{_esc(meta.description)}</div>
                            """
                        )
                        status_components[key] = gr.HTML(_status_html(service, key))
                        if key == "multiturn":
                            scenarios[key] = gr.Radio(
                                choices=["对话", "代码", "办公"],
                                value={"dialogue": "对话", "code": "代码", "office": "办公"}.get(
                                    str(config.get("multiturn.scenario", "dialogue")), "对话"
                                ),
                                label="场景预设",
                                show_label=False,
                                container=False,
                            )
                        run_buttons[key] = gr.Button("运行", variant="secondary", size="sm")
                if len(row_keys) == 2:
                    with gr.Column(scale=1, min_width=180):
                        pass

        advanced_values = []
        with gr.Accordion("高级选项（一般无需修改）", open=False):
            gr.HTML(
                '<div class="ucm-hint">所有参数外置在 config.yaml；此处覆盖仅对本次会话生效。'
                "默认已按验收口径配置，交付人员通常无需展开。</div>"
            )
            with gr.Tabs():
                with gr.Tab("性能与 SLA"):
                    with gr.Row():
                        perf_parallel = gr.Textbox(
                            label="性能并发梯度",
                            value=",".join(str(item) for item in config.get("perf.parallel", [20])),
                            info="单点 20，或梯度 10,20,40",
                        )
                        perf_number = gr.Number(
                            label="性能请求数", value=int(config.get("perf.number", 200)), precision=0
                        )
                        input_length = gr.Number(
                            label="上下文长度",
                            value=int(config.get("perf.max_prompt_length", 65536)),
                            precision=0,
                        )
                        max_tokens = gr.Number(
                            label="最大输出 tokens", value=int(config.get("perf.max_tokens", 256)), precision=0
                        )
                    with gr.Row():
                        hit_rate = gr.Slider(
                            label="前缀命中率（高级）", minimum=0, maximum=0.9, step=0.05,
                            value=float(config.get("defaults.hit_rate", 0.0)),
                            info="映射为 EvalScope --prefix-length",
                        )
                        tokenizer = gr.Textbox(
                            label="Tokenizer 路径 / ID",
                            value=str(config.get("perf.tokenizer_path", "")),
                            info="离线环境请填镜像内本地路径",
                        )
                        sla_mode = gr.Radio(
                            label="SLA 模式",
                            choices=[
                                ("auto_tune（EvalScope 原生 P90，推荐）", "auto_tune"),
                                ("verify（只跑 200 并发复核）", "verify"),
                            ],
                            value=str(config.get("sla.mode", "auto_tune")),
                        )
                    with gr.Row():
                        sla_concurrency = gr.Number(
                            label="SLA 目标并发",
                            value=int(config.get("sla.target.concurrency", 200)),
                            precision=0,
                        )
                        ttft_limit = gr.Number(
                            label="TTFT.P90 阈值（秒）",
                            value=float(config.get("sla.target.ttft_p90_ms", 10000)) / 1000,
                        )
                        tpot_limit = gr.Number(
                            label="TPOT.P90 阈值（毫秒）",
                            value=float(config.get("sla.target.tpot_p90_ms", 50)),
                        )
                with gr.Tab("精度 / 多轮 / Agent"):
                    with gr.Row():
                        accuracy_runs = gr.Number(
                            label="精度每项遍数",
                            value=int(config.get("accuracy.runs", 2)),
                            precision=0,
                            info="默认 2 遍，用于 KVCache 一致性",
                        )
                        accuracy_limit = gr.Number(
                            label="精度样本数（0=按预设）",
                            value=0,
                            precision=0,
                        )
                        mt_parallel = gr.Number(
                            label="多轮并发", value=int(config.get("multiturn.parallel", 4)), precision=0
                        )
                        mt_conversations = gr.Number(
                            label="多轮会话数", value=int(config.get("multiturn.conversations", 12)), precision=0
                        )
                    with gr.Row():
                        agent_parallel = gr.Number(
                            label="AgentX 并发", value=int(config.get("agent.parallel", 4)), precision=0
                        )
                        agent_duration = gr.Number(
                            label="AgentX 持续时间（秒）",
                            value=int(config.get("agent.duration_s", 900)),
                            precision=0,
                            info="EvalScope 默认 30 分钟；现场可按验收窗口调整",
                        )

        with gr.Row():
            run_all_btn = gr.Button("执行全部验收测试", elem_classes="run-all", size="lg")
            refresh_btn = gr.Button("查看最新报告", variant="secondary")
            pdf_btn = gr.Button("导出 PDF", variant="secondary")

        with gr.Row():
            with gr.Column(scale=1):
                stage_md = gr.Markdown("就绪")
                log_box = gr.Textbox(
                    label="执行日志",
                    lines=12,
                    max_lines=12,
                    interactive=False,
                    autoscroll=True,
                    elem_classes="ucm-log",
                    placeholder="执行进度与 EvalScope 输出会显示在这里",
                )
            with gr.Column(scale=1):
                summary_html = gr.HTML(_summary_html(service))
                download_file = gr.File(label="下载完整 HTML 报告", interactive=False)
                pdf_file = gr.File(label="PDF 报告", interactive=False)

        gr.HTML(
            '<div class="ucm-section-title">验收报告 <small>报告内嵌图表与原始命令，可离线归档</small></div>'
        )
        report_html = gr.HTML(_report_frame(service))

        output_components = [
            *[status_components[key] for key in ITEM_KEYS],
            stage_md,
            log_box,
            summary_html,
            report_html,
            download_file,
            pdf_file,
        ]
        advanced_values = [
            perf_parallel,
            perf_number,
            input_length,
            max_tokens,
            hit_rate,
            tokenizer,
            sla_mode,
            sla_concurrency,
            ttft_limit,
            tpot_limit,
            accuracy_runs,
            accuracy_limit,
            mt_parallel,
            mt_conversations,
            agent_parallel,
            agent_duration,
        ]

        def _prepare(base: str, model_name: str, key_value: str, *adv: Any) -> dict[str, Any]:
            service.update_endpoint(base_url=base, model=model_name, api_key=key_value)
            overrides = _advanced_overrides(*adv)
            service.apply_overrides(overrides)
            return overrides

        def _render(
            logs: list[str],
            stage: str,
            *,
            pdf_clear: bool = True,
        ) -> tuple[Any, ...]:
            values = list(_all_outputs(service, logs, stage))
            if pdf_clear:
                values.append(None)
            return tuple(values)

        def probe_click(base: str, model_name: str, key_value: str):
            try:
                service.update_endpoint(base_url=base, model=model_name, api_key=key_value)
            except UCMAcceptError as exc:
                return f'<div class="ucm-probe-bad">✗ {_esc(exc)}</div>'
            result = service.check_connection()
            css = "ucm-probe-ok" if result.connected else "ucm-probe-bad"
            mark = "●" if result.connected else "○"
            latency = f" · {result.latency_ms:.0f} ms" if result.latency_ms is not None else ""
            context = f" · 上下文 {result.context_window}" if result.context_window else ""
            return (
                f'<div class="{css}">{mark} {_esc(result.message)}{latency}{context}'
                f'<div class="ucm-hint">{_esc(result.detail)}</div></div>'
            )

        def run_one(
            key: str,
            scenario_label: str,
            base: str,
            model_name: str,
            key_value: str,
            perf_parallel: str,
            perf_number: float,
            input_length: float,
            max_tokens: float,
            hit_rate: float,
            tokenizer_text: str,
            sla_mode_value: str,
            sla_concurrency_value: float,
            ttft_limit_value: float,
            tpot_limit_value: float,
            accuracy_runs_value: float,
            accuracy_limit_value: float,
            mt_parallel_value: float,
            mt_conversations_value: float,
            agent_parallel_value: float,
            agent_duration_value: float,
            progress=gr.Progress(track_tqdm=False),  # noqa: B008 - Gradio 注入约定
        ):
            logs: list[str] = []
            stage = "准备执行…"

            def on_progress(event: ProgressEvent) -> None:
                nonlocal stage
                stage = event.message
                logs.append(_format_event(event))
                try:
                    progress(event.overall, desc=event.message[:100])
                except Exception:  # noqa: BLE001 - 进度显示失败不应影响验收
                    pass

            adv = (
                perf_parallel, perf_number, input_length, max_tokens, hit_rate, tokenizer_text,
                sla_mode_value, sla_concurrency_value, ttft_limit_value, tpot_limit_value,
                accuracy_runs_value, accuracy_limit_value, mt_parallel_value, mt_conversations_value,
                agent_parallel_value, agent_duration_value,
            )
            try:
                _prepare(base, model_name, key_value, *adv)
            except Exception as exc:  # noqa: BLE001
                logs.append(f"✗ 参数校验失败：{exc}")
                return _render(logs, "参数校验失败")
            try:
                item = service.run_item(
                    key,
                    scenario=_parse_scenario(scenario_label) if key == "multiturn" else None,
                    progress=on_progress,
                )
                logs.append(f"✓ {item.name} 完成：{STATUS_LABELS[item.status]}")
                stage = f"完成 · {item.name}：{STATUS_LABELS[item.status]}"
            except Exception as exc:  # noqa: BLE001
                logs.append(f"✗ 执行失败：{exc}")
                stage = "执行失败"
                return _render(logs, stage)
            return _render(logs, stage)

        def run_all(
            base: str,
            model_name: str,
            key_value: str,
            perf_parallel: str,
            perf_number: float,
            input_length: float,
            max_tokens: float,
            hit_rate: float,
            tokenizer_text: str,
            sla_mode_value: str,
            sla_concurrency_value: float,
            ttft_limit_value: float,
            tpot_limit_value: float,
            accuracy_runs_value: float,
            accuracy_limit_value: float,
            mt_parallel_value: float,
            mt_conversations_value: float,
            agent_parallel_value: float,
            agent_duration_value: float,
            progress=gr.Progress(track_tqdm=False),  # noqa: B008 - Gradio 注入约定
        ):
            logs: list[str] = []

            def on_progress(event: ProgressEvent) -> None:
                logs.append(_format_event(event))
                try:
                    progress(event.overall, desc=event.message[:100])
                except Exception:  # noqa: BLE001
                    pass

            adv = (
                perf_parallel, perf_number, input_length, max_tokens, hit_rate, tokenizer_text,
                sla_mode_value, sla_concurrency_value, ttft_limit_value, tpot_limit_value,
                accuracy_runs_value, accuracy_limit_value, mt_parallel_value, mt_conversations_value,
                agent_parallel_value, agent_duration_value,
            )
            try:
                _prepare(base, model_name, key_value, *adv)
            except Exception as exc:  # noqa: BLE001
                logs.append(f"✗ 参数校验失败：{exc}")
                return _render(logs, "参数校验失败")
            try:
                report = service.run_all(progress=on_progress)
                logs.append(f"✓ 全部验收完成：{report.conclusion}")
                stage = f"全部完成 · {report.conclusion}"
            except Exception as exc:  # noqa: BLE001
                logs.append(f"✗ 执行失败：{exc}")
                stage = "执行失败"
            return _render(logs, stage)

        def refresh_latest():
            path = find_latest_report(service.outputs_root)
            if not path:
                return _render(["暂无历史报告。"], "暂无报告")
            try:
                report = AcceptanceReport.load_json(path)
            except Exception as exc:  # noqa: BLE001
                return _render([f"读取报告失败：{exc}"], "读取失败")
            logs = [
                f"已加载最近报告：{path}",
                f"结论：{report.conclusion}",
                f"任务：{report.run_id} · {report.started_at}",
            ]
            # 直接把最新 HTML 塞进 iframe，同时更新状态卡
            html_path = path.with_name("report.html")
            frame = (
                f'<iframe class="ucm-report-frame" title="验收报告" srcdoc="{_esc(html_path.read_text(encoding="utf-8"))}"></iframe>'
                if html_path.exists()
                else '<div class="ucm-hint">未找到对应 HTML 报告。</div>'
            )
            values = list(_status_tuple(service, report))
            values.extend(["已加载最近报告", "\n".join(logs), _latest_summary(report), frame, str(html_path) if html_path.exists() else None, None])
            return tuple(values)

        def _latest_summary(report: AcceptanceReport) -> str:
            reasons = "".join(f"<li>{_esc(reason)}</li>" for reason in report.reasons)
            return (
                f'<div class="ucm-summary" style="border-left-color:{report.conclusion_color}">'
                f'<div class="label">历史报告 · {_esc(report.mode)}</div>'
                f'<div class="verdict" style="color:{report.conclusion_color}">{_esc(report.conclusion)}</div>'
                f"<ul>{reasons}</ul><div class='meta'>任务 {_esc(report.run_id)}</div></div>"
            )

        def pdf_click():
            try:
                path = service.export_pdf()
                return str(path), f"PDF 已导出：{path}"
            except Exception as exc:  # noqa: BLE001
                return None, f"PDF 导出失败：{exc}"

        probe_btn.click(
            probe_click,
            inputs=[base_url, model, api_key],
            outputs=[probe_status],
        )
        for key in ITEM_KEYS:
            inputs = [base_url, model, api_key, *advanced_values]
            if key == "multiturn":
                inputs = [scenarios[key], base_url, model, api_key, *advanced_values]
                run_buttons[key].click(
                    run_one,
                    inputs=[gr.State(key), *inputs],
                    outputs=output_components,
                    concurrency_limit=1,
                )
            else:
                run_buttons[key].click(
                    run_one,
                    inputs=[gr.State(key), gr.State(""), *inputs],
                    outputs=output_components,
                    concurrency_limit=1,
                )
        run_all_btn.click(
            run_all,
            inputs=[base_url, model, api_key, *advanced_values],
            outputs=output_components,
            concurrency_limit=1,
        )
        refresh_btn.click(refresh_latest, inputs=[], outputs=output_components)
        pdf_btn.click(pdf_click, inputs=[], outputs=[pdf_file, stage_md])

    demo.queue(default_concurrency_limit=1, max_size=32)
    demo._ucm_theme = theme  # type: ignore[attr-defined]
    demo._ucm_css = CSS  # type: ignore[attr-defined]
    return demo


def _find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def main(
    config: Config | None = None,
    *,
    mode: str = "live",
    mock_profile: str = "nominal",
    mock_delay_ms: int | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
) -> int:
    try:
        import gradio as gr  # noqa: F401
    except ImportError:
        print("未安装 gradio，无法启动 GUI。请安装：pip install 'ucm-accept[gui]'")
        return 1
    config = config or Config.load()
    service = AcceptanceService(
        config,
        mode=mode,
        mock_profile=mock_profile,
        mock_delay_ms=mock_delay_ms,
    )
    demo = build_demo(service)
    chosen_port = port or _find_free_port(host)
    should_open = bool(open_browser and has_desktop())
    url = f"http://{host}:{chosen_port}"
    print(f"UCM 验收工具 GUI 已启动：{url}")
    if not has_desktop():
        print("未检测到桌面环境，已降级为打印访问地址；请在浏览器中手动打开。")
        should_open = False
    try:
        demo.launch(
            server_name=host,
            server_port=chosen_port,
            inbrowser=should_open,
            show_error=True,
            quiet=False,
            allowed_paths=[str(service.outputs_root), str(Path.cwd())],
            theme=getattr(demo, "_ucm_theme", None),
            css=getattr(demo, "_ucm_css", None),
        )
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"GUI 启动失败：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
