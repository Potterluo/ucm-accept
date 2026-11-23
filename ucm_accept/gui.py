from __future__ import annotations

import html
import re
import socket
import traceback
from pathlib import Path
from typing import Any

from . import __version__
from . import assets as assets_hub
from .config import DEFAULT_CONFIG_PATH, Config, ConfigError
from .errors import UCMAcceptError
from .events import ProgressEvent
from .models import ITEM_BY_KEY, ITEM_KEYS, STATUS_LABELS, TEST_ITEMS, AcceptanceReport, Status
from .service import AcceptanceService
from .utils import find_latest_report, has_desktop

CSS = r"""
/* ===================== Apple 风格设计系统 =====================
   画布 #f5f5f7 · 白卡片 · 单一强调色 #0071e3 · 胶囊按钮 · 500ms 缓动 */
:root{
  --ink:#1d1d1f;--muted:#86868b;--muted-2:#6e6e73;
  --line:#e8e8ed;--line-2:#d2d2d7;
  --bg:#f5f5f7;--card:#ffffff;
  --blue:#0071e3;--blue-hover:#0077ed;--blue-soft:rgba(0,113,227,.10);
  --green:#34c759;--red:#ff3b30;--amber:#ff9f0a;
  --ease:cubic-bezier(.25,.1,.25,1);
  --radius-card:24px;--radius-input:12px;
  --shadow-rest:0 1px 2px rgba(0,0,0,.03),0 4px 12px rgba(0,0,0,.04);
  --shadow-hover:0 20px 40px rgba(0,0,0,.08);
  --shadow-btn:0 4px 14px rgba(0,113,227,.30);
}
body,.gradio-container{background:var(--bg)!important}
.gradio-container{max-width:1200px!important;margin:0 auto!important;
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","Segoe UI",
    "PingFang SC","HarmonyOS Sans SC","MiSans","Microsoft YaHei","Noto Sans CJK SC",sans-serif!important;
  color:var(--ink)!important;-webkit-font-smoothing:antialiased}

/* ===================== Gradio 原生样式扁平化 ===================== */
.gradio-container .form{border:none!important;box-shadow:none!important;background:transparent!important;padding:0!important}
.gradio-container fieldset.block{background:transparent!important;border:none!important;box-shadow:none!important}
.gradio-container span[data-testid="block-info"],.gradio-container label[data-testid="block-label"]{
  background:transparent!important;border:none!important;box-shadow:none!important;padding:0 0 5px!important;
  margin:0!important;font-weight:500!important;font-size:12px!important;color:var(--muted-2)!important}
.ucm-probe-status{background:transparent!important;border:none!important;box-shadow:none!important;padding:0!important}
.gradio-container .styler{background:transparent!important;border:none!important;box-shadow:none!important;padding:0!important}
.ucm-filebox{height:auto!important;min-height:0!important}
.ucm-filebox > div,.ucm-filebox button,.ucm-filebox .empty,.ucm-filebox .wrap,.ucm-filebox .file-preview{
  min-height:0!important;height:auto!important}
.ucm-filebox button{padding:10px 16px!important}
.ucm-import{height:auto!important;min-height:0!important}
.ucm-import > div,.ucm-import button,.ucm-import .empty,.ucm-import .wrap,.ucm-import .upload-container,
.ucm-import .file-preview,.ucm-import [data-testid="file"],.ucm-import .prose{
  min-height:0!important;height:auto!important;color:var(--muted)!important;font-size:12px!important}
.ucm-import button,.ucm-import .upload-container{background:var(--bg)!important;
  border:1.5px dashed var(--line-2)!important;border-radius:12px!important;padding:10px 14px!important;
  box-shadow:none!important;color:var(--muted-2)!important}
.gradio-container .container.show_textbox_border,.gradio-container .input-container{background:transparent!important}

/* ===================== 输入框 ===================== */
.gradio-container input[type="text"],.gradio-container input[type="number"],.gradio-container input[type="password"],
.gradio-container textarea{
  border-radius:var(--radius-input)!important;border:1px solid var(--line-2)!important;
  background:var(--card)!important;transition:box-shadow .5s var(--ease),border-color .5s var(--ease)!important}
.gradio-container input:focus,.gradio-container textarea:focus{
  border-color:var(--blue)!important;box-shadow:0 0 0 3px rgba(0,113,227,.22)!important;outline:none!important}
.gradio-container input::placeholder,.gradio-container textarea::placeholder{color:#aeaeb2}

/* ===================== 页头（Apple 极简：灰底大标题） ===================== */
.ucm-hero{padding:44px 4px 4px;margin:0}
.ucm-hero .eyebrow{font-size:12px;letter-spacing:.18em;color:var(--muted)!important;font-weight:600;
  display:inline-flex;align-items:center;gap:10px;text-transform:uppercase}
.ucm-hero h1{margin:10px 0 6px;font-size:34px;line-height:1.15;font-weight:700;letter-spacing:-.022em;
  color:var(--ink)!important}
.ucm-hero p{margin:0;color:var(--muted)!important;font-size:15px;max-width:56em;line-height:1.55}
.ucm-hero .chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
.ucm-chip{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:5px 13px;
  font-size:12px;color:var(--muted-2);font-weight:500}
.ucm-chip b{color:var(--ink);font-weight:600}
.ucm-mode-mock{background:#fff6e0!important;border-color:#ffd9a0!important;color:#8a5300!important}

/* ===================== 区块标题 ===================== */
.ucm-section-title{margin:34px 2px 14px;font-size:21px;font-weight:700;letter-spacing:-.01em;
  color:var(--ink);display:flex;align-items:baseline;gap:10px}
.ucm-section-title small{font-weight:400;color:var(--muted);font-size:13px}

/* ===================== 白卡片（服务地址 / 测试项列表 / 配置） ===================== */
.gradio-container .gr-group{background:transparent!important;border:none!important;box-shadow:none!important}
.ucm-endpoint,.ucm-items,.ucm-config{background:var(--card)!important;border-radius:var(--radius-card);
  box-shadow:var(--shadow-rest)!important;transition:box-shadow .5s var(--ease)}
.ucm-endpoint{padding:24px 26px 10px;margin-bottom:8px}
.ucm-endpoint input{border-radius:var(--radius-input)!important}
.ucm-config{margin-top:14px}
.ucm-config .wrap{background:transparent}
.ucm-config summary,.ucm-config > button{font-weight:600!important;color:var(--ink)!important}

/* ===================== 测试项列表（iOS 设置风格） ===================== */
.ucm-items{padding:8px 24px}
.ucm-item{padding:0!important;transition:background .5s var(--ease)}
.ucm-item + .ucm-item{border-top:1px solid var(--line)!important}
.ucm-item-row{display:flex!important;flex-direction:row!important;flex-wrap:nowrap!important;
  align-items:center!important;gap:16px;margin:0!important;padding:8px 0}
.ucm-item-row > .block,.ucm-item-row > button{min-width:0!important}
.ucm-item-row > .ucm-item-head-wrap{flex:1 1 auto!important;width:auto!important}
.ucm-item-row > .ucm-item-status{flex:0 0 auto!important;width:auto!important}
.ucm-item-row > .card-enable{flex:0 0 auto!important;width:auto!important}
.ucm-item-row > button.ucm-run-one{flex:0 0 auto!important;width:auto!important}
.ucm-item-head-wrap{flex:1 1 auto!important;min-width:0;display:flex!important;align-items:center!important}
.ucm-item-head{display:flex;align-items:center;gap:14px;min-width:0}
.ucm-item-icon{width:36px;height:36px;flex:none;border-radius:10px;display:flex;align-items:center;
  justify-content:center;font-size:17px;
  background:color-mix(in srgb,var(--accent,#0071e3) 12%,#fff);
  border:1px solid color-mix(in srgb,var(--accent,#0071e3) 24%,#fff)}
.ucm-item-name{min-width:0}
.ucm-item-title{font-size:15px;font-weight:600;letter-spacing:-.01em;line-height:1.3;
  display:flex;align-items:center;gap:8px;white-space:nowrap}
.ucm-item-eta{font-size:11px;color:var(--muted);background:var(--bg);border-radius:999px;
  padding:2px 9px;font-weight:500;white-space:nowrap}
.ucm-item-desc{font-size:12.5px;color:var(--muted);line-height:1.5;margin-top:2px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:460px}
.ucm-item-status{flex:0 0 auto!important;display:flex!important;align-items:center}
.ucm-item-status .status-line{display:flex;flex-direction:column;align-items:flex-end;gap:3px}
.ucm-item-status .status-summary{font-size:12px;color:var(--muted);max-width:260px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:right}
.ucm-item:has(.ucm-pill.running){background:rgba(0,113,227,.045)}
.ucm-item:has(.ucm-pill.running) .ucm-item-icon{animation:ucm-breathe 1.6s ease-in-out infinite}
@keyframes ucm-breathe{0%,100%{opacity:1}50%{opacity:.55}}

/* ===================== 状态徽章 ===================== */
.ucm-pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:2.5px 11px;
  font-size:11.5px;font-weight:600;letter-spacing:.01em;white-space:nowrap}
.ucm-pill::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}
.ucm-pill.passed{color:#1d7a3d;background:#e8f9ee}
.ucm-pill.warning{color:#9a6a00;background:#fff6e0}
.ucm-pill.failed{color:#c21b17;background:#ffecec}
.ucm-pill.pending,.ucm-pill.skipped{color:var(--muted-2);background:var(--bg)}
.ucm-pill.running{color:#0062c4;background:#e5f0ff}
.ucm-pill.running::before{animation:ucm-pulse 1.1s ease-in-out infinite}
@keyframes ucm-pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.72)}}

/* ===================== 纳入验收开关（iOS 拨动开关） ===================== */
.card-enable{flex:0 0 auto!important;display:flex!important;align-items:center!important}
.card-enable > div{margin:0!important}
.card-enable label{display:inline-flex!important;align-items:center;margin:0!important;cursor:pointer;min-height:28px}
.card-enable .label-text{display:none!important}
.card-enable input[type="checkbox"]{appearance:none;-webkit-appearance:none;width:44px;height:26px;margin:0;
  border-radius:999px!important;background:#e9e9eb!important;border:none!important;box-shadow:none!important;
  cursor:pointer;transition:background .5s var(--ease);position:relative;outline:none;flex:none}
.card-enable input[type="checkbox"]:checked{background:var(--green)!important}
.card-enable input[type="checkbox"]::after{content:"";position:absolute;top:2px;left:2px;width:22px;height:22px;
  border-radius:50%;background:#fff;box-shadow:0 2px 4px rgba(0,0,0,.18);transition:transform .5s var(--ease)}
.card-enable input[type="checkbox"]:checked::after{transform:translateX(18px)}

/* ===================== 按钮系统（胶囊） ===================== */
.gradio-container button.primary{background:var(--blue)!important;border:none!important;color:#fff!important;
  border-radius:999px!important;font-weight:600!important;box-shadow:var(--shadow-btn)!important;
  transition:all .5s var(--ease)}
.gradio-container button.primary:hover{background:var(--blue-hover)!important;transform:translateY(-1px)}
.gradio-container button.primary:active{transform:scale(.96)}
.gradio-container button.secondary{background:var(--card)!important;color:var(--blue)!important;
  border:1px solid var(--line-2)!important;border-radius:999px!important;font-weight:600!important;
  transition:all .5s var(--ease)}
.gradio-container button.secondary:hover{background:var(--bg)!important;transform:translateY(-1px)}
.gradio-container button.secondary:active{transform:scale(.96)}
.run-all{min-height:48px!important;font-size:15px!important;letter-spacing:-.01em;padding:0 40px!important}
.ucm-run-one{min-height:32px!important;font-size:12.5px!important;padding:0 18px!important;
  background:var(--blue-soft)!important;border:none!important;color:var(--blue)!important}
.ucm-run-one:hover{background:rgba(0,113,227,.16)!important;transform:none}
.probe-btn{min-height:40px!important}

/* ===================== 选项卡（分段控件） ===================== */
.ucm-config .tab-nav,.gradio-container .tab-nav{background:#ececee!important;border-bottom:none!important;
  border-radius:12px!important;padding:3px!important;gap:2px;width:fit-content}
.ucm-config .tab-nav button,.gradio-container .tab-nav button{border-radius:9px!important;background:transparent!important;
  font-weight:500!important;font-size:13px!important;color:var(--muted-2)!important;
  transition:all .5s var(--ease)}
.ucm-config .tab-nav button.selected,.gradio-container .tab-nav button.selected,
.ucm-config .tab-nav button[aria-selected="true"]{background:#fff!important;color:var(--ink)!important;
  box-shadow:0 1px 4px rgba(0,0,0,.10)!important}

/* ===================== 项内配置折叠区 ===================== */
.ucm-item-config{border:none!important;background:transparent!important;box-shadow:none!important;
  padding:0!important;margin:0 0 8px 50px!important}
.ucm-item-config .label-wrap,.ucm-item-config button,.ucm-item-config [role="button"]{
  width:100%;justify-content:flex-start!important;text-align:left;padding:3px 0!important;
  font-weight:500!important;font-size:12.5px!important;color:var(--blue)!important}
.ucm-item-config .label-wrap .icon,.ucm-item-config button .icon{display:none!important}
.ucm-item-config .wrap{background:transparent!important;border:none!important}
.ucm-config label span{font-weight:500!important;font-size:12px!important;color:var(--muted-2)!important}
.ucm-config input,.ucm-config input[type="number"],.ucm-config textarea{border-radius:var(--radius-input)!important}

/* ===================== 数据集表格 ===================== */
.ucm-ds-table{margin:6px 0 2px;overflow-x:auto}
.ucm-ds-table table{width:100%;border-collapse:separate;border-spacing:0;font-size:12.5px;
  border:1px solid var(--line);border-radius:12px;overflow:hidden}
.ucm-ds-table th{background:var(--bg);color:var(--muted-2);font-weight:600;text-align:left;
  padding:8px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
.ucm-ds-table td{padding:8px 12px;border-bottom:1px solid var(--line);color:var(--ink);vertical-align:top}
.ucm-ds-table tr:last-child td{border-bottom:none}
.ucm-ds-table .ds-key{font-size:10.5px;color:var(--muted);font-family:"SF Mono",ui-monospace,Consolas,monospace}
.ucm-ds-table .ds-desc{color:var(--muted);max-width:340px}
.ucm-ds-table .ds-src{color:var(--muted);white-space:nowrap}

/* ===================== 结论与日志 ===================== */
.ucm-summary{position:relative;background:var(--card);border:none!important;border-radius:var(--radius-card);
  padding:22px 26px;margin:4px 0 10px;box-shadow:var(--shadow-rest)}
.ucm-summary .label{font-size:11px;color:var(--muted);letter-spacing:.12em;font-weight:600}
.ucm-summary .verdict{font-size:28px;font-weight:700;letter-spacing:-.02em;line-height:1.2;margin-top:4px}
.ucm-summary ul{margin:8px 0 0;padding-left:20px;color:var(--muted-2);font-size:12.5px;line-height:1.7}
.ucm-summary .meta{font-size:11.5px;color:var(--muted);margin-top:8px;opacity:.9}
.ucm-log textarea{
  font-family:"SF Mono",ui-monospace,"Cascadia Code",Consolas,"JetBrains Mono",monospace!important;
  font-size:12px!important;line-height:1.55!important;background:var(--bg)!important;color:var(--ink)!important;
  border:1px solid var(--line)!important;border-radius:12px!important;box-shadow:none!important}
.ucm-report-frame{width:100%;height:820px;border:1px solid var(--line);border-radius:16px;background:#fff;
  box-shadow:var(--shadow-rest)}
.ucm-probe-ok{color:#1d7a3d;font-size:12.5px;margin-top:4px}
.ucm-probe-bad{color:#c21b17;font-size:12.5px;margin-top:4px}
.ucm-hint{font-size:12px;color:var(--muted);margin:2px 0 8px;line-height:1.6}
.ucm-footer{text-align:center;color:var(--muted);font-size:11.5px;padding:24px 0 8px}

/* ===================== 动效偏好 ===================== */
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{transition-duration:.01ms!important;animation-duration:.01ms!important}
}
"""


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _pill(status: Status) -> str:
    return f'<span class="ucm-pill {status.value}">{_esc(STATUS_LABELS[status])}</span>'


def _status_html(service: AcceptanceService, key: str, report: AcceptanceReport | None = None) -> str:
    report = report or service.current_report()
    item = report.items.get(key) if report else None
    if item is None:
        return '<div class="status-line"><span class="ucm-pill pending">待执行</span></div>'
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
            '<div class="meta">配置服务地址后点击任意“运行”，或直接执行所选测试。</div></div>'
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
            '<div style="border:1px solid #e8e8ed;border-radius:16px;padding:48px;text-align:center;'
            'color:#86868b;background:#ffffff;font-size:13.5px">执行测试后，这里会显示完整验收报告。</div>'
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


# 每个测试项的图标色（iOS 设置风格：彩色小方块图标，页面其余部分保持单色系）
ITEM_ACCENTS: dict[str, str] = {
    "perf": "#0071e3",
    "multiturn": "#af52de",
    "sla": "#ff9500",
    "accuracy": "#34c759",
    "agent": "#30b0c7",
}


def _default_save_path(config: Config) -> str:
    """配置保存位置：外部配置文件原路径；内置默认配置则落到工作目录的用户配置。"""
    if config.source and config.source.resolve() != DEFAULT_CONFIG_PATH.resolve():
        return str(config.source)
    return "./ucm-accept.user.yaml"


def _registry_dataset_keys(cfg: Config) -> set[str]:
    """资产包注册表提供的数据集 key（与内置默认配置对比得出）。"""
    try:
        import yaml

        base = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        base_datasets = (base.get("accuracy", {}) or {}).get("datasets", {}) or {}
        return {key for key in (cfg.get("accuracy.datasets", {}) or {}) if key not in base_datasets}
    except Exception:  # noqa: BLE001 - 对比失败时全部按内置显示
        return set()


def _dataset_table_html(cfg: Config) -> str:
    """数据集一览表：来自 config 与资产包注册表，含描述与样本数。"""
    datasets = cfg.get("accuracy.datasets", {}) or {}
    if not datasets:
        return '<div class="ucm-hint">未配置精度数据集。</div>'
    registry_keys = _registry_dataset_keys(cfg)
    rows = []
    for key, item in datasets.items():
        enabled = bool(item.get("enabled", True))
        badge = (
            '<span class="ucm-pill passed">启用</span>'
            if enabled
            else '<span class="ucm-pill skipped">停用</span>'
        )
        dataset_name = str(item.get("dataset", key))
        subset = str(item.get("subset", "") or "")
        limit = item.get("limit", "")
        limit_text = f"{limit} 条" if limit not in ("", None) else "按预设"
        source = "资产包注册表" if key in registry_keys else "内置配置"
        rows.append(
            f"<tr><td><b>{_esc(item.get('label', key))}</b>"
            f"<div class='ds-key'>{_esc(key)}</div></td>"
            f"<td>{_esc(dataset_name)}{_esc(' / ' + subset if subset else '')}</td>"
            f"<td>{_esc(limit_text)}</td><td>{badge}</td>"
            f"<td class='ds-desc'>{_esc(item.get('description', '') or '—')}</td>"
            f"<td class='ds-src'>{_esc(source)}</td></tr>"
        )
    return (
        '<div class="ucm-ds-table"><table><thead><tr>'
        "<th>数据集</th><th>标识</th><th>样本数</th><th>状态</th><th>说明</th><th>来源</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _keys_for_labels(labels: Any) -> list[str]:
    """把勾选的测试项名称映射为有序 key 列表。"""
    chosen = set(labels or [])
    return [meta.key for meta in TEST_ITEMS if meta.name in chosen]


def _extra_overrides(
    timeout_s: float,
    perf_min_tokens: float,
    perf_dataset: str,
    perf_warmup: float,
    mt_min_turns: float,
    mt_max_turns: float,
    sla_lower: float,
    sla_upper: float,
    acc_label_to_key: dict[str, str],
    acc_labels: Any,
    agent_dataset: str,
    report_title: str,
    report_company: str,
    report_operator: str,
) -> dict[str, Any]:
    """配置中心扩展字段 → 覆盖项；与 _advanced_overrides 的结果按 deep_merge 合并。"""
    overrides: dict[str, Any] = {
        "endpoint": {"timeout_s": float(timeout_s or 180)},
        "perf": {
            "min_tokens": int(perf_min_tokens or 256),
            "dataset": str(perf_dataset).strip() or "random",
            "warmup_num": max(0, int(perf_warmup or 0)),
        },
        "multiturn": {
            "min_turns": int(mt_min_turns or 2),
            "max_turns": int(mt_max_turns or 5),
        },
        "sla": {
            "auto_tune": {
                "lower": int(sla_lower or 1),
                "upper": int(sla_upper or 200),
            }
        },
        "agent": {"dataset_name": str(agent_dataset).strip()},
        "report": {
            "title": str(report_title).strip(),
            "company": str(report_company).strip(),
            "operator": str(report_operator).strip(),
        },
    }
    if int(perf_min_tokens or 0) <= 0:
        del overrides["perf"]["min_tokens"]
    chosen = set(acc_labels or [])
    overrides["accuracy"] = {
        "datasets": {
            key: {"enabled": label in chosen}
            for label, key in acc_label_to_key.items()
        }
    }
    if int(mt_min_turns or 0) <= 0:
        del overrides["multiturn"]["min_turns"]
    if int(mt_max_turns or 0) <= 0:
        del overrides["multiturn"]["max_turns"]
    if not overrides["report"]["title"]:
        del overrides["report"]["title"]
    return overrides


def build_demo(service: AcceptanceService):
    try:
        import gradio as gr
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise UCMAcceptError("未安装 gradio，无法启动 GUI。请安装 ucm-accept[gui]。") from exc

    config = service.config
    mode_text = "EvalScope 实机" if service.mode == "live" else "模拟演示（不会产生真实请求）"
    mode_class = "" if service.mode == "live" else " ucm-mode-mock"
    theme = gr.themes.Soft(primary_hue="blue", neutral_hue="slate")

    # 内置 tokenizer 候选
    try:
        hub = assets_hub.find_assets_root(str(config.get("app.assets_dir", "") or "") or None)
        builtin_tok = assets_hub.builtin_tokenizers(hub) if hub else []
    except Exception:  # noqa: BLE001
        builtin_tok = []
    tok_path = str(config.get("perf.tokenizer_path", "") or "")
    builtin_match = next(
        (name for name in builtin_tok if name and (name in tok_path or tok_path.endswith("/" + name))),
        None,
    )
    tok_builtin_choices = [f"内置：{name}" for name in builtin_tok] + ["自定义路径"]
    tok_default_index = builtin_tok.index(builtin_match) if builtin_match in builtin_tok else len(builtin_tok)

    with gr.Blocks(title=f"{config.get('app.title')} v{__version__}") as demo:
        gr.HTML(
            f"""
            <div class="ucm-hero">
              <div class="eyebrow">UCM Inference Acceleration · Acceptance</div>
              <h1>{_esc(config.get('app.title'))}</h1>
              <p>{_esc(config.get('app.subtitle'))}</p>
              <div class="chips">
                <span class="ucm-chip{mode_class}">执行引擎 · {_esc(mode_text)}</span>
                <span class="ucm-chip">EvalScope 原生执行</span>
                <span class="ucm-chip">离线可用 · 报告自包含</span>
                <span class="ucm-chip">v{_esc(__version__)}</span>
              </div>
            </div>
            """
        )

        # ============== 端点区 ==============
        with gr.Group(elem_classes="ucm-endpoint"):
            with gr.Row():
                base_url = gr.Textbox(
                    label="服务地址",
                    value=str(config.get("endpoint.base_url")),
                    placeholder="http://127.0.0.1:8801/v1",
                    scale=4,
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
                probe_btn = gr.Button("检测连通", variant="secondary", scale=0, elem_classes="probe-btn")
            with gr.Row():
                tokenizer_mode = gr.Radio(
                    choices=tok_builtin_choices,
                    value=tok_builtin_choices[tok_default_index],
                    label="模型路径（Tokenizer）",
                    info="「内置」来自离线资产包 tokenizers/ 目录",
                    scale=3,
                )
                tokenizer_custom = gr.Textbox(
                    label="自定义路径 / 模型 ID",
                    value="" if builtin_match else tok_path,
                    placeholder="/opt/ucm-assets/tokenizers/<模型名>",
                    visible=not builtin_tok or builtin_match is None,
                    scale=2,
                )
            probe_status = gr.HTML(
                '<div class="ucm-hint">尚未检测。点击“检测连通”验证地址、模型与上下文窗口。</div>',
                elem_classes="ucm-probe-status",
            )

        # ============== 验收项目：每卡片勾选 + 卡内配置 ==============
        run_items_cfg = config.run_items()
        presets = config.get("multiturn.scenarios", {}) or {}
        mt_labels = [str(presets[k].get("label", k)) for k in presets]
        mt_label_to_key = {str(presets[k].get("label", k)): k for k in presets}
        mt_selected = [str(k) for k in (config.get("multiturn.scenarios_selected", []) or [])] or [
            str(config.get("multiturn.scenario", "dialogue"))
        ]
        datasets_cfg = config.get("accuracy.datasets", {}) or {}
        acc_labels_all = [str(item.get("label", key)) for key, item in datasets_cfg.items()]
        acc_labels_enabled = [
            str(item.get("label", key))
            for key, item in datasets_cfg.items()
            if bool(item.get("enabled", True))
        ]

        def _item_head(key: str) -> str:
            """测试项列表行左侧：图标 + 名称 + 预计耗时 + 一行说明。"""
            meta = ITEM_BY_KEY[key]
            accent = ITEM_ACCENTS[key]
            return (
                f'<div class="ucm-item-head">'
                f'<div class="ucm-item-icon" style="--accent:{accent}">{meta.icon}</div>'
                f'<div class="ucm-item-name">'
                f'<div class="ucm-item-title">{_esc(meta.name)}<span class="ucm-item-eta">{_esc(meta.eta)}</span></div>'
                f'<div class="ucm-item-desc">{_esc(meta.description)}</div>'
                f"</div></div>"
            )

        gr.HTML(
            '<div class="ucm-section-title">验收项目 <small>开关决定是否纳入验收，「配置」展开单项参数，「运行」执行单项</small></div>'
        )
        status_components: dict[str, Any] = {}
        run_buttons: dict[str, Any] = {}
        card_enable: dict[str, Any] = {}

        with gr.Group(elem_classes="ucm-items"):
            # ---- 基础性能 ----
            with gr.Group(elem_classes="ucm-item", elem_id="card-perf"):
                with gr.Row(elem_classes="ucm-item-row"):
                    gr.HTML(_item_head("perf"), elem_classes="ucm-item-head-wrap")
                    status_components["perf"] = gr.HTML(_status_html(service, "perf"), elem_classes="ucm-item-status")
                    card_enable["perf"] = gr.Checkbox(value="perf" in run_items_cfg, label="纳入验收",
                                                      show_label=False, container=False, elem_classes="card-enable")
                    run_buttons["perf"] = gr.Button("运行", variant="secondary", size="sm", elem_classes="ucm-run-one")
                with gr.Accordion("配置", open=False, elem_classes="ucm-item-config"):
                    perf_parallel_card = gr.Textbox(
                        label="并发梯度",
                        value=",".join(str(v) for v in config.get("perf.parallel", [20])),
                        info="单点 20，或梯度 10,20,40（可增删）",
                    )
                    perf_number_card = gr.Number(
                        label="请求数", value=int(config.get("perf.number", 200)), precision=0
                    )
                    perf_input_len_card = gr.Number(
                        label="输入长度（tokens）", value=int(config.get("perf.max_prompt_length", 65536)), precision=0
                    )
                    perf_output_len_card = gr.Number(
                        label="输出长度（tokens）", value=int(config.get("perf.max_tokens", 256)), precision=0
                    )
            # ---- 多轮对话 ----
            with gr.Group(elem_classes="ucm-item", elem_id="card-multiturn"):
                with gr.Row(elem_classes="ucm-item-row"):
                    gr.HTML(_item_head("multiturn"), elem_classes="ucm-item-head-wrap")
                    status_components["multiturn"] = gr.HTML(_status_html(service, "multiturn"), elem_classes="ucm-item-status")
                    card_enable["multiturn"] = gr.Checkbox(value="multiturn" in run_items_cfg, label="纳入验收",
                                                           show_label=False, container=False, elem_classes="card-enable")
                    run_buttons["multiturn"] = gr.Button("运行", variant="secondary", size="sm", elem_classes="ucm-run-one")
                with gr.Accordion("配置", open=False, elem_classes="ucm-item-config"):
                    mt_scenarios_card = gr.CheckboxGroup(
                        choices=mt_labels,
                        value=[str(presets[k].get("label", k)) for k in presets if k in mt_selected],
                        label="数据集（多选，按顺序执行）",
                    )
                    mt_parallel_card = gr.Number(
                        label="并发", value=int(config.get("multiturn.parallel", 4)), precision=0
                    )
                    mt_conv_card = gr.Number(
                        label="每组会话数", value=int(config.get("multiturn.conversations", 12)), precision=0
                    )
            # ---- SLA 自动调优 ----
            with gr.Group(elem_classes="ucm-item", elem_id="card-sla"):
                with gr.Row(elem_classes="ucm-item-row"):
                    gr.HTML(_item_head("sla"), elem_classes="ucm-item-head-wrap")
                    status_components["sla"] = gr.HTML(_status_html(service, "sla"), elem_classes="ucm-item-status")
                    card_enable["sla"] = gr.Checkbox(value="sla" in run_items_cfg, label="纳入验收",
                                                     show_label=False, container=False, elem_classes="card-enable")
                    run_buttons["sla"] = gr.Button("运行", variant="secondary", size="sm", elem_classes="ucm-run-one")
                with gr.Accordion("配置", open=False, elem_classes="ucm-item-config"):
                    sla_mode_card = gr.Radio(
                        choices=[
                            ("auto_tune（原生 P90，推荐）", "auto_tune"),
                            ("verify（只跑目标并发）", "verify"),
                        ],
                        value=str(config.get("sla.mode", "auto_tune")),
                        label="模式",
                    )
                    sla_ttft_card = gr.Number(
                        label="TTFT.P90 阈值（秒）",
                        value=float(config.get("sla.target.ttft_p90_ms", 10000)) / 1000,
                    )
                    sla_tpot_card = gr.Number(
                        label="TPOT.P90 阈值（毫秒）",
                        value=float(config.get("sla.target.tpot_p90_ms", 50)),
                    )
                    sla_conc_card = gr.Number(
                        label="目标并发", value=int(config.get("sla.target.concurrency", 200)), precision=0
                    )
            # ---- 模型精度 ----
            with gr.Group(elem_classes="ucm-item", elem_id="card-accuracy"):
                with gr.Row(elem_classes="ucm-item-row"):
                    gr.HTML(_item_head("accuracy"), elem_classes="ucm-item-head-wrap")
                    status_components["accuracy"] = gr.HTML(_status_html(service, "accuracy"), elem_classes="ucm-item-status")
                    card_enable["accuracy"] = gr.Checkbox(value="accuracy" in run_items_cfg, label="纳入验收",
                                                          show_label=False, container=False, elem_classes="card-enable")
                    run_buttons["accuracy"] = gr.Button("运行", variant="secondary", size="sm", elem_classes="ucm-run-one")
                with gr.Accordion("配置", open=False, elem_classes="ucm-item-config"):
                    acc_datasets_card = gr.CheckboxGroup(
                        choices=acc_labels_all,
                        value=acc_labels_enabled,
                        label="数据集（多选）",
                    )
                    acc_runs_card = gr.Number(
                        label="每项遍数", value=int(config.get("accuracy.runs", 2)), precision=0,
                        info="默认 2 遍，用于一致性核验",
                    )
                    acc_limit_card = gr.Number(label="每项样本数（0=按预设）", value=0, precision=0)
            # ---- Agent 场景 ----
            with gr.Group(elem_classes="ucm-item", elem_id="card-agent"):
                with gr.Row(elem_classes="ucm-item-row"):
                    gr.HTML(_item_head("agent"), elem_classes="ucm-item-head-wrap")
                    status_components["agent"] = gr.HTML(_status_html(service, "agent"), elem_classes="ucm-item-status")
                    card_enable["agent"] = gr.Checkbox(value="agent" in run_items_cfg, label="纳入验收",
                                                       show_label=False, container=False, elem_classes="card-enable")
                    run_buttons["agent"] = gr.Button("运行", variant="secondary", size="sm", elem_classes="ucm-run-one")
                with gr.Accordion("配置", open=False, elem_classes="ucm-item-config"):
                    agent_ctx_card = gr.Number(
                        label="目标上下文（tokens）",
                        value=int(config.get("agent.context_required", 262144)),
                        precision=0,
                        info="低于模型上限时自动降级 smoke 模式",
                    )
                    agent_duration_card = gr.Number(
                        label="持续时长（分钟）",
                        value=max(15, int(config.get("agent.duration_s", 900)) // 60),
                        precision=0,
                    )

        # ============== 运行与结果 ==============
        with gr.Row():
            run_all_btn = gr.Button("执行勾选的验收测试", variant="primary", size="lg",
                                    elem_classes="run-all", scale=2)
            refresh_btn = gr.Button("查看最新报告", variant="secondary")
            pdf_btn = gr.Button("导出 PDF", variant="secondary")

        with gr.Row():
            with gr.Column(scale=1):
                stage_md = gr.Markdown("就绪")
                log_box = gr.Textbox(
                    label="实时日志",
                    lines=12,
                    max_lines=12,
                    interactive=False,
                    autoscroll=True,
                    elem_classes="ucm-log",
                    placeholder="执行进度与 EvalScope 输出会显示在这里",
                )
            with gr.Column(scale=1):
                summary_html = gr.HTML(_summary_html(service))
                download_file = gr.File(label="下载完整 HTML 报告", interactive=False, elem_classes="ucm-filebox")
                pdf_file = gr.File(label="PDF 报告", interactive=False, elem_classes="ucm-filebox")

        gr.HTML(
            '<div class="ucm-section-title">验收报告 <small>报告内嵌图表与原始命令，可离线归档</small></div>'
        )
        report_html = gr.HTML(_report_frame(service))

        # ============== 高级配置（低频项） ==============
        with gr.Accordion("⚙️ 高级配置（低频项）", open=False, elem_classes="ucm-config"):
            gr.HTML(
                '<div class="ucm-hint">各测试项的主要参数已在上方对应测试项的「配置」内。此处为低频高级参数，'
                "修改仅对本次会话生效，点击「保存到配置文件」后持久化。API Key 不落盘。</div>"
            )
            with gr.Tabs():
                with gr.Tab("性能"):
                    with gr.Row():
                        min_tokens_field = gr.Number(
                            label="最小输出 tokens", value=int(config.get("perf.min_tokens", 256)), precision=0
                        )
                        perf_dataset = gr.Textbox(
                            label="数据集",
                            value=str(config.get("perf.dataset", "random")),
                            info="默认 random 合成长输入；离线镜像可换本地数据集",
                        )
                        hit_rate = gr.Slider(
                            label="前缀命中率", minimum=0, maximum=0.9, step=0.05,
                            value=float(config.get("defaults.hit_rate", 0.0)),
                            info="映射为 EvalScope --prefix-length",
                        )
                    with gr.Row():
                        perf_warmup = gr.Number(
                            label="预热请求数", value=int(config.get("perf.warmup_num", 0)), precision=0
                        )
                        endpoint_timeout = gr.Number(
                            label="请求超时（秒）",
                            value=float(config.get("endpoint.timeout_s", 180)),
                            precision=0,
                        )
                with gr.Tab("多轮 / SLA / Agent"):
                    with gr.Row():
                        mt_min_turns = gr.Number(
                            label="多轮最少轮次", value=int(config.get("multiturn.min_turns", 2)), precision=0
                        )
                        mt_max_turns = gr.Number(
                            label="多轮最多轮次", value=int(config.get("multiturn.max_turns", 5)), precision=0
                        )
                        sla_lower = gr.Number(
                            label="自动调优下限", value=int(config.get("sla.auto_tune.lower", 2)), precision=0
                        )
                        sla_upper = gr.Number(
                            label="自动调优上限", value=int(config.get("sla.auto_tune.upper", 200)), precision=0
                        )
                    with gr.Row():
                        agent_dataset = gr.Textbox(
                            label="Agent 数据集",
                            value=str(config.get("agent.dataset_name", "AgentX-claudecode")),
                        )
                with gr.Tab("报告信息"):
                    with gr.Row():
                        report_title_field = gr.Textbox(
                            label="报告标题", value=str(config.get("report.title", "")), scale=2
                        )
                        report_company = gr.Textbox(
                            label="客户/公司名称", value=str(config.get("report.company", "") or "")
                        )
                        report_operator = gr.Textbox(
                            label="测试执行人", value=str(config.get("report.operator", "") or "")
                        )
            gr.HTML(
                '<div class="ucm-hint">数据集在 config.yaml 或资产包 datasets/registry.yaml 中声明；下表随配置与资产包更新。</div>'
            )
            dataset_table = gr.HTML(_dataset_table_html(config))
            with gr.Row():
                save_btn = gr.Button("保存到配置文件", variant="primary", size="sm")
                export_btn = gr.Button("导出当前配置", size="sm")
                import_file = gr.File(
                    label="导入配置文件（YAML）", file_types=[".yaml", ".yml"], interactive=True,
                    elem_classes="ucm-import",
                )
                reset_btn = gr.Button("恢复默认值", size="sm")
            with gr.Row():
                save_path = gr.Textbox(
                    label="配置保存路径",
                    value=str(_default_save_path(config)),
                    info="保存后可用 ucm-accept --config 该路径 复用",
                    scale=3,
                )
                cfg_export_file = gr.File(label="导出的配置", interactive=False, elem_classes="ucm-filebox")
            cfg_status = gr.Markdown("")

        # ============== 事件处理 ==============
        output_components = [
            *[status_components[key] for key in ITEM_KEYS],
            stage_md,
            log_box,
            summary_html,
            report_html,
            download_file,
            pdf_file,
        ]
        enables_list = [card_enable[key] for key in ITEM_KEYS]

        def _unchanged(count: int) -> tuple[Any, ...]:
            return tuple(gr.update() for _ in range(count))

        def _run_field_values(cfg: Config) -> tuple[Any, ...]:
            """按 [5 勾选, 端点/tokenizer(5), 卡内字段(16), 高级低频项(13)] 顺序返回全部字段值。"""
            items = cfg.run_items()
            ds = cfg.get("accuracy.datasets", {}) or {}
            mt_sel = [str(k) for k in (cfg.get("multiturn.scenarios_selected", []) or [])] or [
                str(cfg.get("multiturn.scenario", "dialogue"))
            ]
            tok = str(cfg.get("perf.tokenizer_path", "") or "")
            hub = None
            try:
                hub = assets_hub.find_assets_root(str(cfg.get("app.assets_dir", "") or "") or None)
            except Exception:  # noqa: BLE001
                hub = None
            builtin_names = assets_hub.builtin_tokenizers(hub) if hub else []
            builtin_match = next(
                (name for name in builtin_names if name and (name in tok or tok.endswith("/" + name))),
                None,
            )
            if builtin_match:
                tok_mode, tok_custom = f"内置：{builtin_match}", ""
            else:
                tok_mode, tok_custom = "自定义路径", tok
            mt_sel_labels = [
                str(item.get("label", k))
                for k, item in (cfg.get("multiturn.scenarios", {}) or {}).items()
                if k in mt_sel
            ]
            ds_limits = [int(item.get("limit", 0) or 0) for item in ds.values()]
            uniform = ds_limits[0] if ds_limits and all(value == ds_limits[0] for value in ds_limits) else 0
            return (
                *[key in items for key in ITEM_KEYS],
                str(cfg.get("endpoint.base_url", "")),
                str(cfg.get("endpoint.model", "")),
                str(cfg.get("endpoint.api_key", "") or ""),
                tok_mode,
                tok_custom,
                ",".join(str(v) for v in cfg.get("perf.parallel", [20])),
                int(cfg.get("perf.number", 200)),
                int(cfg.get("perf.max_prompt_length", 65536)),
                int(cfg.get("perf.max_tokens", 256)),
                mt_sel_labels,
                int(cfg.get("multiturn.parallel", 4)),
                int(cfg.get("multiturn.conversations", 12)),
                str(cfg.get("sla.mode", "auto_tune")),
                float(cfg.get("sla.target.ttft_p90_ms", 10000)) / 1000,
                float(cfg.get("sla.target.tpot_p90_ms", 50)),
                int(cfg.get("sla.target.concurrency", 200)),
                [str(item.get("label", key)) for key, item in ds.items() if bool(item.get("enabled", True))],
                int(cfg.get("accuracy.runs", 2)),
                uniform,
                int(cfg.get("agent.context_required", 262144)),
                max(15, int(cfg.get("agent.duration_s", 900)) // 60),
                float(cfg.get("defaults.hit_rate", 0.0) or 0.0),
                str(cfg.get("perf.dataset", "random")),
                int(cfg.get("perf.min_tokens", 256)),
                int(cfg.get("perf.warmup_num", 0)),
                float(cfg.get("endpoint.timeout_s", 180)),
                int(cfg.get("multiturn.min_turns", 2)),
                int(cfg.get("multiturn.max_turns", 5)),
                int(cfg.get("sla.auto_tune.lower", 2)),
                int(cfg.get("sla.auto_tune.upper", 200)),
                str(cfg.get("agent.dataset_name", "AgentX-claudecode")),
                str(cfg.get("report.title", "")),
                str(cfg.get("report.company", "") or ""),
                str(cfg.get("report.operator", "") or ""),
            )

        _ACC_FIELD_INDEX = 21  # 5 勾选 + 端点/tokenizer(5) + 卡内第 11 个

        def _field_refresh(cfg: Config) -> tuple[Any, ...]:
            """按 [*enables_list, *run_inputs] 的输出顺序返回全部字段值。"""
            return _run_field_values(cfg)

        def _apply_config_values(cfg: Config, status: str) -> tuple[Any, ...]:
            values = list(_field_refresh(cfg))
            ds = cfg.get("accuracy.datasets", {}) or {}
            values[_ACC_FIELD_INDEX] = gr.update(
                choices=[str(item.get("label", key)) for key, item in ds.items()],
                value=[str(item.get("label", key)) for key, item in ds.items() if bool(item.get("enabled", True))],
            )
            return (*values, _dataset_table_html(cfg), status)

        def _resolve_tokenizer(mode: str, custom: str) -> str:
            if str(mode).startswith("内置："):
                name = str(mode).split("内置：", 1)[1].strip()
                hub = assets_hub.find_assets_root(str(service.config.get("app.assets_dir", "") or "") or None)
                if hub is not None:
                    return str(hub / "tokenizers" / name)
                return name
            return str(custom or "").strip()

        def _prepare(
            enables: Any,
            base: str,
            model_name: str,
            key_value: str,
            tokenizer_mode: str,
            tokenizer_custom: str,
            *fields: Any,
        ) -> list[str]:
            keys = [
                key for key in ITEM_KEYS
                if bool(enables[ITEM_KEYS.index(key)])
            ]
            if not keys:
                raise UCMAcceptError("请至少勾选一个测试项")
            service.update_endpoint(base_url=base, model=model_name, api_key=key_value)
            service.config.set("run.items", keys)
            service.config.set("perf.tokenizer_path", _resolve_tokenizer(tokenizer_mode, tokenizer_custom))
            (perf_parallel, perf_number, perf_input_len, perf_output_len,
             mt_scenarios, mt_parallel, mt_conv,
             sla_mode, sla_ttft, sla_tpot, sla_conc,
             acc_datasets, acc_runs, acc_limit,
             agent_ctx, agent_duration,
             hit_rate, perf_dataset, min_tokens, perf_warmup, endpoint_timeout,
             mt_min_turns, mt_max_turns, sla_lower, sla_upper, agent_dataset,
             rpt_title, rpt_company, rpt_operator) = fields
            mt_keys_sel = [mt_label_to_key.get(sel, sel) for sel in (mt_scenarios or [])]
            ds = service.config.get("accuracy.datasets", {}) or {}
            _label_to_key = {str(item.get("label", key)): key for key, item in ds.items()}
            chosen = {_label_to_key.get(sel, sel) for sel in (acc_datasets or [])}
            service.config.set("perf.parallel", _parse_parallel(perf_parallel))
            service.config.set("perf.number", int(perf_number))
            service.config.set("perf.min_prompt_length", int(perf_input_len))
            service.config.set("perf.max_prompt_length", int(perf_input_len))
            service.config.set("perf.max_tokens", int(perf_output_len))
            service.config.set("multiturn.scenarios_selected", mt_keys_sel)
            service.config.set("multiturn.parallel", int(mt_parallel))
            service.config.set("multiturn.conversations", int(mt_conv))
            service.config.set("sla.mode", str(sla_mode))
            service.config.set("sla.target.ttft_p90_ms", float(sla_ttft) * 1000)
            service.config.set("sla.target.tpot_p90_ms", float(sla_tpot))
            service.config.set("sla.target.concurrency", int(sla_conc))
            for key in ds:
                ds[key]["enabled"] = key in chosen
            service.config.set("accuracy.datasets", ds)
            service.config.set("accuracy.runs", int(acc_runs))
            if int(acc_limit or 0) > 0:
                for key in ds:
                    ds[key]["limit"] = int(acc_limit)
                service.config.set("accuracy.datasets", ds)
            service.config.set("agent.context_required", int(agent_ctx))
            service.config.set("agent.duration_s", int(agent_duration) * 60)
            overrides = {
                "defaults": {"hit_rate": float(hit_rate or 0.0)},
                "perf": {
                    "dataset": str(perf_dataset).strip() or "random",
                    "min_tokens": int(min_tokens or 256),
                    "warmup_num": max(0, int(perf_warmup or 0)),
                },
                "endpoint": {"timeout_s": float(endpoint_timeout or 180)},
                "multiturn": {
                    "min_turns": int(mt_min_turns or 2),
                    "max_turns": int(mt_max_turns or 5),
                },
                "sla": {
                    "auto_tune": {
                        "lower": int(sla_lower or 2),
                        "upper": int(sla_upper or 200),
                    }
                },
                "agent": {"dataset_name": str(agent_dataset).strip()},
                "report": {
                    "title": str(rpt_title).strip(),
                    "company": str(rpt_company).strip(),
                    "operator": str(rpt_operator).strip(),
                },
            }
            service.apply_overrides(overrides)
            return keys

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
            *values: Any,
            progress=gr.Progress(track_tqdm=False),  # noqa: B008 - Gradio 注入约定
        ):
            # inputs = [State(key), *5 勾选, *run_inputs(34)]：按位置统一解包
            enables, (base, model_name, key_value, tokenizer_mode, tokenizer_custom), fields = list(values[:5]), values[5:10], values[10:]
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

            try:
                _prepare(enables, base, model_name, key_value, tokenizer_mode, tokenizer_custom, *fields)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                logs.append(f"✗ 参数校验失败：{exc}")
                return _render(logs, "参数校验失败")
            try:
                item = service.run_item(key, progress=on_progress)
                logs.append(f"✓ {item.name} 完成：{STATUS_LABELS[item.status]}")
                stage = f"完成 · {item.name}：{STATUS_LABELS[item.status]}"
            except Exception as exc:  # noqa: BLE001
                logs.append(f"✗ 执行失败：{exc}")
                stage = "执行失败"
                return _render(logs, stage)
            return _render(logs, stage)

        def run_all(
            *values: Any,
            progress=gr.Progress(track_tqdm=False),  # noqa: B008 - Gradio 注入约定
        ):
            # inputs = [*5 勾选, *run_inputs(34)]：按位置统一解包
            enables, (base, model_name, key_value, tokenizer_mode, tokenizer_custom), fields = list(values[:5]), values[5:10], values[10:]
            logs: list[str] = []

            def on_progress(event: ProgressEvent) -> None:
                logs.append(_format_event(event))
                try:
                    progress(event.overall, desc=event.message[:100])
                except Exception:  # noqa: BLE001
                    pass

            try:
                keys = _prepare(enables, base, model_name, key_value, tokenizer_mode, tokenizer_custom, *fields)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                logs.append(f"✗ 参数校验失败：{exc}")
                return _render(logs, "参数校验失败")
            try:
                report = service.run_all(progress=on_progress, keys=keys)
                logs.append(f"✓ 验收完成（{'、'.join(keys)}）：{report.conclusion}")
                stage = f"验收完成 · {report.conclusion}"
            except Exception as exc:  # noqa: BLE001
                logs.append(f"✗ 执行失败：{exc}")
                stage = "执行失败"
            return _render(logs, stage)

        def save_click(path_value: str, *values: Any):
            enables, (base, model_name, key_value, tokenizer_mode, tokenizer_custom), fields = list(values[:5]), values[5:10], values[10:]
            try:
                _prepare(enables, base, model_name, key_value, tokenizer_mode, tokenizer_custom, *fields)
                target = service.config.save(path_value or _default_save_path(service.config))
                return (
                    *_field_refresh(service.config),
                    _dataset_table_html(service.config),
                    f"✅ 配置已保存：`{target}`\n下次启动复用：`ucm-accept --config {target}`",
                )
            except Exception as exc:  # noqa: BLE001
                return (*_unchanged(39), _dataset_table_html(service.config), f"❌ 保存失败：{exc}")

        def export_click(*values: Any):
            enables, (base, model_name, key_value, tokenizer_mode, tokenizer_custom), fields = list(values[:5]), values[5:10], values[10:]
            try:
                _prepare(enables, base, model_name, key_value, tokenizer_mode, tokenizer_custom, *fields)
                target = service.outputs_root / "ucm-accept.export.yaml"
                service.config.save(target)
                return str(target), f"✅ 已导出当前生效配置：`{target}`"
            except Exception as exc:  # noqa: BLE001
                return None, f"❌ 导出失败：{exc}"

        def import_click(file_obj: Any):
            if file_obj is None:
                return (*_unchanged(39), _dataset_table_html(service.config), "⚠️ 未选择配置文件")
            path = file_obj.name if hasattr(file_obj, "name") else str(file_obj)
            try:
                cfg = Config.load(path)
            except ConfigError as exc:
                return (*_unchanged(39), _dataset_table_html(service.config), f"❌ 配置无效：{exc}")
            except OSError as exc:
                return (*_unchanged(39), _dataset_table_html(service.config), f"❌ 读取失败：{exc}")
            try:
                service.replace_config(cfg)
            except Exception as exc:  # noqa: BLE001
                return (*_unchanged(39), _dataset_table_html(service.config), f"❌ 应用失败：{exc}")
            return _apply_config_values(cfg, f"✅ 已导入并应用：`{path}`")

        def reset_click():
            try:
                cfg = Config.load(overrides={"app": {"report_dir": str(service.outputs_root)}})
            except ConfigError as exc:
                return (*_unchanged(39), _dataset_table_html(service.config), f"❌ 加载默认配置失败：{exc}")
            try:
                service.replace_config(cfg)
            except Exception as exc:  # noqa: BLE001
                return (*_unchanged(39), _dataset_table_html(service.config), f"❌ 应用失败：{exc}")
            return _apply_config_values(cfg, "♻️ 已恢复内置默认配置（输出目录保持不变）")

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

        # ============== 事件绑定 ==============
        probe_btn.click(probe_click, inputs=[base_url, model, api_key], outputs=[probe_status])
        enables_list = [card_enable[key] for key in ITEM_KEYS]
        run_inputs = [
            base_url, model, api_key, tokenizer_mode, tokenizer_custom,
            perf_parallel_card, perf_number_card, perf_input_len_card, perf_output_len_card,
            mt_scenarios_card, mt_parallel_card, mt_conv_card,
            sla_mode_card, sla_ttft_card, sla_tpot_card, sla_conc_card,
            acc_datasets_card, acc_runs_card, acc_limit_card,
            agent_ctx_card, agent_duration_card,
            hit_rate, perf_dataset, min_tokens_field, perf_warmup, endpoint_timeout,
            mt_min_turns, mt_max_turns, sla_lower, sla_upper, agent_dataset,
            report_title_field, report_company, report_operator,
        ]
        for key in ITEM_KEYS:
            run_buttons[key].click(
                run_one,
                inputs=[gr.State(key), *enables_list, *run_inputs],
                outputs=output_components,
                concurrency_limit=1,
            )
        run_all_btn.click(
            run_all,
            inputs=[*enables_list, *run_inputs],
            outputs=output_components,
            concurrency_limit=1,
        )
        refresh_btn.click(refresh_latest, inputs=[], outputs=output_components)
        pdf_btn.click(pdf_click, inputs=[], outputs=[pdf_file, stage_md])
        save_btn.click(
            save_click,
            inputs=[save_path, *enables_list, *run_inputs],
            outputs=[*enables_list, *run_inputs, dataset_table, cfg_status],
            concurrency_limit=1,
        )
        export_btn.click(
            export_click,
            inputs=[*enables_list, *run_inputs],
            outputs=[cfg_export_file, cfg_status],
            concurrency_limit=1,
        )
        import_file.upload(
            import_click,
            inputs=[import_file],
            outputs=[*enables_list, *run_inputs, dataset_table, cfg_status],
            concurrency_limit=1,
        )
        reset_btn.click(
            reset_click,
            inputs=[],
            outputs=[*enables_list, *run_inputs, dataset_table, cfg_status],
            concurrency_limit=1,
        )

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
