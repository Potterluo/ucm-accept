from __future__ import annotations

import html
import re
import socket
from pathlib import Path
from typing import Any

from . import __version__
from .config import DEFAULT_CONFIG_PATH, Config, ConfigError, deep_merge
from .errors import UCMAcceptError
from .events import ProgressEvent
from .models import ITEM_BY_KEY, ITEM_KEYS, STATUS_LABELS, TEST_ITEMS, AcceptanceReport, Status
from .service import AcceptanceService
from .utils import find_latest_report, has_desktop

CSS = r"""
/* ===================== 基础与字体 ===================== */
:root{
  --ucm-ink:#0d1a2b;--ucm-muted:#5d6b81;--ucm-line:#e5eaf3;--ucm-line-strong:#d5dce8;
  --ucm-brand:#0b2a4a;--ucm-teal:#0e9f8c;--ucm-teal-deep:#0b6b63;
  --ucm-bg:#eef2f8;--ucm-card:#ffffff;
  --shadow-sm:0 1px 2px rgba(13,26,43,.05),0 2px 8px rgba(13,26,43,.05);
  --shadow-md:0 4px 14px rgba(13,26,43,.08),0 1px 3px rgba(13,26,43,.06);
  --shadow-lg:0 14px 34px rgba(11,42,74,.16);
}
body,.gradio-container{background:
  radial-gradient(1200px 420px at 18% -6%, rgba(14,159,140,.10), transparent 62%),
  radial-gradient(900px 380px at 88% -10%, rgba(37,99,235,.08), transparent 58%),
  var(--ucm-bg)!important;}
.gradio-container{max-width:1360px!important;margin:0 auto!important;
  font-family:"Segoe UI","HarmonyOS Sans SC","MiSans","PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif!important;
  color:var(--ucm-ink)!important;}
.gradio-container h1,.gradio-container h2,.gradio-container h3{letter-spacing:.01em}

/* ===================== Gradio 原生样式扁平化 ===================== */
.gradio-container .form{border:none!important;box-shadow:none!important;background:transparent!important;
  padding:0!important}
.gradio-container fieldset.block{background:transparent!important;border:none!important;box-shadow:none!important}
.gradio-container span[data-testid="block-info"]{background:transparent!important;border:none!important;
  box-shadow:none!important;padding:0 0 4px!important;margin:0!important;font-weight:640!important;
  font-size:12.5px!important;color:#3d4c63!important;letter-spacing:.01em}
.gradio-container label[data-testid="block-label"]{background:transparent!important;border:none!important;
  box-shadow:none!important;font-weight:640!important;font-size:12.5px!important;color:#3d4c63!important}
.ucm-probe-status{background:transparent!important;border:none!important;box-shadow:none!important;padding:0!important}
.gradio-container .styler{background:transparent!important;border:none!important;box-shadow:none!important;padding:0!important}
.ucm-filebox{height:auto!important;min-height:0!important}
.ucm-filebox > div, .ucm-filebox button, .ucm-filebox .empty, .ucm-filebox .wrap, .ucm-filebox .file-preview{
  min-height:0!important;height:auto!important}
.ucm-filebox button{padding:10px 14px!important}
.ucm-import{height:auto!important;min-height:0!important}
.ucm-import > div, .ucm-import button, .ucm-import .empty, .ucm-import .wrap, .ucm-import .upload-container,
.ucm-import .file-preview, .ucm-import [data-testid="file"], .ucm-import .prose{
  min-height:0!important;height:auto!important;color:var(--ucm-muted)!important;font-size:12px!important}
.ucm-import button, .ucm-import .upload-container{background:#f6f9fc!important;border:1.5px dashed var(--ucm-line-strong)!important;
  border-radius:10px!important;padding:10px 14px!important;box-shadow:none!important}
.gradio-container .container.show_textbox_border, .gradio-container .input-container{background:transparent!important}

/* ===================== Hero ===================== */
.ucm-hero{position:relative;overflow:hidden;border-radius:20px;padding:30px 34px;color:#fff;margin:6px 0 18px;
  background:linear-gradient(118deg,#071523 0%,#0b2a4a 46%,#0d5060 84%,#0f7a6d 108%);
  box-shadow:var(--shadow-lg)}
.ucm-hero::before{content:"";position:absolute;inset:0;opacity:.5;pointer-events:none;
  background:
   radial-gradient(520px 220px at 82% 120%, rgba(18,181,160,.32), transparent 70%),
   radial-gradient(420px 200px at 96% -20%, rgba(59,130,246,.25), transparent 70%)}
.ucm-hero::after{content:"";position:absolute;inset:0;pointer-events:none;opacity:.14;
  background:repeating-linear-gradient(135deg,transparent 0 22px,rgba(255,255,255,.5) 22px 23px)}
.ucm-hero>*{position:relative;z-index:1}
.ucm-hero .eyebrow{font-size:11px;letter-spacing:.24em;color:#7fe3d4!important;font-weight:700;
  display:inline-flex;align-items:center;gap:8px}
.ucm-hero .eyebrow::before{content:"";width:22px;height:2px;border-radius:2px;background:#12b5a0}
.ucm-hero h1{margin:10px 0 6px;font-size:29px;line-height:1.25;font-weight:760;color:#fff!important}
.ucm-hero p{margin:0;color:#c9dcf0!important;font-size:13.5px;max-width:56em}
.ucm-hero .chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.ucm-chip{background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.2);border-radius:999px;
  padding:4px 12px;font-size:11.5px;color:#e9f7f4;backdrop-filter:blur(6px)}
.ucm-chip b{color:#8fe8d9;font-weight:700}
.ucm-mode-mock{background:#b45309!important;border-color:#f3d19b!important;color:#fff!important}

/* ===================== 区块标题 ===================== */
.ucm-section-title{margin:20px 0 10px;font-size:16px;font-weight:750;color:var(--ucm-ink);
  display:flex;align-items:center;gap:10px}
.ucm-section-title::before{content:"";width:4px;height:16px;border-radius:3px;
  background:linear-gradient(180deg,#12b5a0,#0b6b63)}
.ucm-section-title small{font-weight:400;color:var(--ucm-muted);font-size:12px;margin-left:2px}

/* ===================== 服务地址卡片 ===================== */
.ucm-endpoint{background:var(--ucm-card);border:1px solid var(--ucm-line);border-radius:16px;
  padding:16px 18px 8px;margin-bottom:6px;box-shadow:var(--shadow-sm)}
.ucm-endpoint input{border-radius:10px!important}

/* ===================== 测试项卡片 ===================== */
.test-card{position:relative;background:var(--ucm-card)!important;border:1px solid var(--ucm-line)!important;
  border-radius:16px!important;padding:14px 16px!important;box-shadow:var(--shadow-sm)!important;
  transition:box-shadow .18s ease,transform .18s ease,border-color .18s ease;overflow:hidden}
/* 网格对齐：行内等高、内容纵向排布、按钮统一沉底 */
.gradio-container .row:has(.test-card){display:flex!important;align-items:stretch!important}
.gradio-container .row:has(.test-card) > .column{display:flex!important}
.test-card{display:flex!important;flex-direction:column!important;min-height:344px!important}
/* 状态徽章 + 按钮组成底部信息区，多余留白集中在中部 */
.test-card > :nth-child(1){order:1}
.test-card > :nth-child(2){order:3;margin-top:auto!important}
.test-card > :nth-child(3):not(button){order:2}
.test-card > button{order:4;margin-top:12px!important;width:100%!important}
.test-card:hover{box-shadow:var(--shadow-md)!important;transform:translateY(-2px);border-color:var(--ucm-line-strong)!important}
.test-card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent,#0e9f8c);opacity:.85}
.card-top{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.card-head{display:flex;align-items:center;gap:10px;min-width:0}
.card-icon{width:38px;height:38px;flex:none;border-radius:11px;display:flex;align-items:center;justify-content:center;
  font-size:19px;background:color-mix(in srgb,var(--accent,#0e9f8c) 13%,#fff);border:1px solid color-mix(in srgb,var(--accent,#0e9f8c) 26%,#fff)}
.card-title{font-weight:730;font-size:15px;margin-top:0;line-height:1.2}
.card-eta{font-size:11px;color:var(--ucm-muted);background:#f1f5f9;border-radius:999px;padding:3px 9px;white-space:nowrap}
.card-desc{font-size:12.5px;color:var(--ucm-muted);line-height:1.6;margin:8px 0 8px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
  min-height:40px!important;max-height:40px!important}
.status-line{margin-top:2px}
.status-summary{font-size:12px;color:var(--ucm-muted);margin-top:6px;line-height:1.5;min-height:36px}
.test-card:has(.ucm-pill.running){border-color:#93c5fd!important;box-shadow:0 0 0 3px rgba(37,99,235,.10),var(--shadow-md)!important}
.test-card:has(.ucm-pill.running)::after{content:"";position:absolute;left:0;right:0;top:0;height:2.5px;
  background:linear-gradient(90deg,transparent,#3b82f6,transparent);animation:ucm-slide 1.6s linear infinite}
@keyframes ucm-slide{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}

/* ===================== 状态徽章 ===================== */
.ucm-pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 11px;
  font-size:11.5px;font-weight:680;letter-spacing:.02em}
.ucm-pill::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;flex:none}
.ucm-pill.passed{color:#15803d;background:#e9f8ef;border:1px solid #b9e6c9}
.ucm-pill.warning{color:#b45309;background:#fff7e6;border:1px solid #f2d19a}
.ucm-pill.failed{color:#b91c1c;background:#fef1f1;border:1px solid #f3c2c2}
.ucm-pill.pending,.ucm-pill.skipped{color:#55637a;background:#f2f5f9;border:1px solid #dde4ee}
.ucm-pill.running{color:#1d4ed8;background:#eaf1ff;border:1px solid #bdd4fd}
.ucm-pill.running::before{animation:ucm-pulse 1.1s ease-in-out infinite}
@keyframes ucm-pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.72)}}

/* ===================== 验收范围勾选（芯片化） ===================== */
#items-check .wrap{gap:8px}
#items-check label{border:1.5px solid var(--ucm-line-strong)!important;background:#fff!important;
  border-radius:999px!important;padding:6px 14px!important;font-size:12.5px!important;font-weight:600!important;
  color:var(--ucm-muted)!important;transition:all .15s ease;cursor:pointer;margin:0!important;
  box-shadow:0 1px 2px rgba(13,26,43,.04)}
#items-check label:hover{border-color:var(--ucm-teal)!important;color:var(--ucm-teal-deep)!important}
#items-check label:has(input:checked){background:linear-gradient(120deg,#0b6b63,#12b5a0)!important;
  border-color:transparent!important;color:#fff!important;box-shadow:0 3px 10px rgba(14,159,140,.32)}
#items-check input[type="checkbox"]{accent-color:#0e9f8c}

/* ===================== 配置面板 ===================== */
.ucm-config{background:var(--ucm-card);border:1px solid var(--ucm-line);border-radius:16px;
  box-shadow:var(--shadow-sm);margin-top:14px}
.ucm-config .wrap{background:transparent}
.ucm-config summary,.ucm-config > button{font-weight:700!important;color:var(--ucm-ink)!important}
.ucm-config .tab-nav,.gradio-container .tab-nav{background:transparent!important;border-bottom:1px solid var(--ucm-line)}
.ucm-config .tab-nav button,.gradio-container .tab-nav button{border-radius:10px 10px 0 0!important;
  font-weight:620!important;font-size:13px!important;color:var(--ucm-muted)!important}
.ucm-config .tab-nav button.selected,.gradio-container .tab-nav button.selected,
.ucm-config .tab-nav button[aria-selected="true"]{color:var(--ucm-teal-deep)!important;
  box-shadow:inset 0 -2px 0 var(--ucm-teal)}
.ucm-config .form{gap:8px}
.ucm-ds-table{margin:6px 0 2px;overflow-x:auto}
.ucm-ds-table table{width:100%;border-collapse:separate;border-spacing:0;font-size:12px;
  border:1px solid var(--ucm-line);border-radius:10px;overflow:hidden}
.ucm-ds-table th{background:#f4f7fb;color:#3d4c63;font-weight:640;text-align:left;
  padding:7px 10px;border-bottom:1px solid var(--ucm-line);white-space:nowrap}
.ucm-ds-table td{padding:7px 10px;border-bottom:1px solid var(--ucm-line);color:#2b3852;vertical-align:top}
.ucm-ds-table tr:last-child td{border-bottom:none}
.ucm-ds-table .ds-key{font-size:10.5px;color:#8a95a9;font-family:Consolas,monospace}
.ucm-ds-table .ds-desc{color:var(--ucm-muted);max-width:340px}
.ucm-ds-table .ds-src{color:#8a95a9;white-space:nowrap}
.ucm-config label span{font-weight:600!important;font-size:12px!important;color:#43506a!important}
.ucm-config input,.ucm-config input[type="number"],.ucm-config textarea{border-radius:10px!important}
.ucm-hint{font-size:12px;color:var(--ucm-muted);margin:2px 0 8px;line-height:1.6}

/* ===================== 按钮 ===================== */
.gradio-container button.primary{border-radius:12px!important;font-weight:700!important}
.gradio-container button.secondary{border-radius:12px!important;font-weight:640!important}
.run-all{background:linear-gradient(92deg,#0b6b63 0%,#0e9f8c 55%,#14c2a8 100%)!important;border:none!important;
  color:#fff!important;font-weight:760!important;min-height:46px!important;font-size:14.5px!important;
  letter-spacing:.03em;box-shadow:0 8px 20px rgba(14,159,140,.34)!important}
.run-all:hover{filter:brightness(1.05);transform:translateY(-1px)}
.run-all:active{transform:translateY(0)}

/* ===================== 结论与日志 ===================== */
.ucm-summary{position:relative;background:var(--ucm-card);border:1px solid var(--ucm-line);border-left:5px solid #0e9f8c;
  border-radius:14px;padding:16px 20px;margin:4px 0 10px;box-shadow:var(--shadow-sm)}
.ucm-summary .label{font-size:10.5px;color:var(--ucm-muted);letter-spacing:.14em;font-weight:700}
.ucm-summary .verdict{font-size:26px;font-weight:800;line-height:1.25;margin-top:2px}
.ucm-summary ul{margin:8px 0 0;padding-left:20px;color:var(--ucm-muted);font-size:12.5px;line-height:1.7}
.ucm-summary .meta{font-size:11.5px;color:var(--ucm-muted);margin-top:8px;opacity:.85}
.ucm-log textarea{font-family:"Cascadia Code","SFMono-Regular",Consolas,"JetBrains Mono",monospace!important;
  font-size:12px!important;line-height:1.55!important;background:#0c1524!important;color:#c8dcf5!important;
  border:1px solid #1d2c45!important;border-radius:12px!important;
  box-shadow:inset 0 2px 10px rgba(0,0,0,.35)}
.ucm-report-frame{width:100%;height:820px;border:1px solid var(--ucm-line);border-radius:14px;background:#fff;
  box-shadow:var(--shadow-sm)}
.ucm-probe-ok{color:#15803d;font-size:12.5px;margin-top:2px}
.ucm-probe-bad{color:#b91c1c;font-size:12.5px;margin-top:2px}
.ucm-footer{text-align:center;color:#8090a6;font-size:11.5px;padding:20px 0 8px}
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


# 每个测试项的主题色（卡片左侧色条 + 图标徽章）
ITEM_ACCENTS: dict[str, str] = {
    "perf": "#2563eb",
    "multiturn": "#7c3aed",
    "sla": "#d97706",
    "accuracy": "#059669",
    "agent": "#0891b2",
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
                <span class="ucm-chip">底层：<b>EvalScope</b> 原生 perf / eval / AgentX</span>
                <span class="ucm-chip">离线可用 · 报告自包含</span>
                <span class="ucm-chip">v{_esc(__version__)}</span>
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
                    '<div class="ucm-hint">尚未检测。点击“检测连通”验证地址、模型与上下文窗口。</div>',
                    elem_classes="ucm-probe-status",
                )

        items_check = gr.CheckboxGroup(
            choices=[meta.name for meta in TEST_ITEMS],
            value=[ITEM_BY_KEY[key].name for key in config.run_items()],
            label="验收范围（勾选要执行的测试项）",
            info="取消勾选即跳过对应测试项；下方“执行所选测试项”只跑勾选内容。",
            elem_id="items-check",
        )

        gr.HTML(
            '<div class="ucm-section-title">验收项目 <small>点击单项运行，或按上方勾选的范围一键执行</small></div>'
        )
        status_components: dict[str, Any] = {}
        run_buttons: dict[str, Any] = {}
        scenarios: dict[str, Any] = {}
        for row_keys in (("perf", "multiturn", "sla"), ("accuracy", "agent")):
            with gr.Row(equal_height=True):
                for key in row_keys:
                    meta = ITEM_BY_KEY[key]
                    accent = ITEM_ACCENTS.get(key, "#0e9f8c")
                    with gr.Column(elem_classes="test-card", elem_id=f"card-{key}"):
                        gr.HTML(
                            f"""
                            <div class="card-top">
                              <div class="card-head">
                                <div class="card-icon" style="--accent:{accent}">{meta.icon}</div>
                                <div>
                                  <div class="card-title">{_esc(meta.name)}</div>
                                  <div class="card-eta">{_esc(meta.eta)}</div>
                                </div>
                              </div>
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
        datasets_cfg = config.get("accuracy.datasets", {}) or {}
        acc_labels_all = [str(item.get("label", key)) for key, item in datasets_cfg.items()]
        acc_labels_enabled = [
            str(item.get("label", key))
            for key, item in datasets_cfg.items()
            if bool(item.get("enabled", True))
        ]
        acc_label_to_key = {str(item.get("label", key)): key for key, item in datasets_cfg.items()}
        with gr.Accordion("⚙️ 测试配置（改完即生效，可保存为配置文件）", open=False, elem_classes="ucm-config"):
            gr.HTML(
                '<div class="ucm-hint">所有参数外置在 config.yaml；此处修改只对本次会话生效，'
                "点击「保存到配置文件」后持久化，下次可用 ucm-accept --config 复用。API Key 不落盘。</div>"
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
                        endpoint_timeout = gr.Number(
                            label="请求超时（秒）",
                            value=float(config.get("endpoint.timeout_s", 180)),
                            precision=0,
                        )
                    with gr.Row():
                        min_tokens_field = gr.Number(
                            label="最小输出 tokens", value=int(config.get("perf.min_tokens", 256)), precision=0
                        )
                        perf_dataset = gr.Textbox(
                            label="数据集",
                            value=str(config.get("perf.dataset", "random")),
                            info="默认 random 合成长输入；离线镜像可换本地数据集",
                        )
                        perf_warmup = gr.Number(
                            label="预热请求数", value=int(config.get("perf.warmup_num", 0)), precision=0
                        )
                        hit_rate = gr.Slider(
                            label="前缀命中率（高级）", minimum=0, maximum=0.9, step=0.05,
                            value=float(config.get("defaults.hit_rate", 0.0)),
                            info="映射为 EvalScope --prefix-length",
                        )
                    with gr.Row():
                        tokenizer = gr.Textbox(
                            label="Tokenizer 路径 / ID",
                            value=str(config.get("perf.tokenizer_path", "")),
                            info="离线环境请填镜像内本地路径",
                        )
                        sla_mode = gr.Radio(
                            label="SLA 模式",
                            choices=[
                                ("auto_tune（EvalScope 原生 P90，推荐）", "auto_tune"),
                                ("verify（只跑目标并发复核）", "verify"),
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
                        sla_lower = gr.Number(
                            label="自动调优下限", value=int(config.get("sla.auto_tune.lower", 2)), precision=0
                        )
                        sla_upper = gr.Number(
                            label="自动调优上限", value=int(config.get("sla.auto_tune.upper", 200)), precision=0
                        )
                with gr.Tab("多轮 / 精度 / Agent"):
                    with gr.Row():
                        mt_parallel = gr.Number(
                            label="多轮并发", value=int(config.get("multiturn.parallel", 4)), precision=0
                        )
                        mt_conversations = gr.Number(
                            label="多轮会话数", value=int(config.get("multiturn.conversations", 12)), precision=0
                        )
                        mt_min_turns = gr.Number(
                            label="多轮最少轮次", value=int(config.get("multiturn.min_turns", 2)), precision=0
                        )
                        mt_max_turns = gr.Number(
                            label="多轮最多轮次", value=int(config.get("multiturn.max_turns", 5)), precision=0
                        )
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
                        acc_datasets = gr.CheckboxGroup(
                            choices=acc_labels_all,
                            value=acc_labels_enabled,
                            label="启用的精度数据集",
                            info="按现场时间增减；全部取消会被拒绝",
                        )
                        agent_dataset = gr.Textbox(
                            label="Agent 数据集",
                            value=str(config.get("agent.dataset_name", "AgentX-claudecode")),
                        )
                    gr.HTML(
                        '<div class="ucm-hint">数据集在 config.yaml 或资产包 '
                        "datasets/registry.yaml 中声明（含描述与样本数）；下表随配置与资产包自动更新。</div>"
                    )
                    dataset_table = gr.HTML(_dataset_table_html(config))
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
        extra_values = [
            endpoint_timeout,
            min_tokens_field,
            perf_dataset,
            perf_warmup,
            mt_min_turns,
            mt_max_turns,
            sla_lower,
            sla_upper,
            acc_datasets,
            agent_dataset,
            report_title_field,
            report_company,
            report_operator,
        ]
        run_inputs = [base_url, model, api_key, *advanced_values, *extra_values]

        with gr.Row():
            run_all_btn = gr.Button("执行所选测试项", elem_classes="run-all", size="lg")
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
                download_file = gr.File(label="下载完整 HTML 报告", interactive=False, elem_classes="ucm-filebox")
                pdf_file = gr.File(label="PDF 报告", interactive=False, elem_classes="ucm-filebox")

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

        def _unchanged(count: int) -> tuple[Any, ...]:
            return tuple(gr.update() for _ in range(count))

        def _advanced_field_values(cfg: Config) -> tuple[Any, ...]:
            ds_limits = [
                int(item.get("limit", 0) or 0)
                for item in (cfg.get("accuracy.datasets", {}) or {}).values()
            ]
            uniform = ds_limits[0] if ds_limits and all(value == ds_limits[0] for value in ds_limits) else 0
            return (
                ",".join(str(value) for value in cfg.get("perf.parallel", [20])),
                int(cfg.get("perf.number", 200)),
                int(cfg.get("perf.max_prompt_length", 65536)),
                int(cfg.get("perf.max_tokens", 256)),
                float(cfg.get("defaults.hit_rate", 0.0) or 0.0),
                str(cfg.get("perf.tokenizer_path", "")),
                str(cfg.get("sla.mode", "auto_tune")),
                int(cfg.get("sla.target.concurrency", 200)),
                float(cfg.get("sla.target.ttft_p90_ms", 10000)) / 1000,
                float(cfg.get("sla.target.tpot_p90_ms", 50)),
                int(cfg.get("accuracy.runs", 2)),
                uniform,
                int(cfg.get("multiturn.parallel", 4)),
                int(cfg.get("multiturn.conversations", 12)),
                int(cfg.get("agent.parallel", 4)),
                int(cfg.get("agent.duration_s", 900)),
            )

        def _extra_field_values(cfg: Config) -> tuple[Any, ...]:
            ds = cfg.get("accuracy.datasets", {}) or {}
            return (
                float(cfg.get("endpoint.timeout_s", 180)),
                int(cfg.get("perf.min_tokens", 256)),
                str(cfg.get("perf.dataset", "random")),
                int(cfg.get("perf.warmup_num", 0)),
                int(cfg.get("multiturn.min_turns", 2)),
                int(cfg.get("multiturn.max_turns", 5)),
                int(cfg.get("sla.auto_tune.lower", 2)),
                int(cfg.get("sla.auto_tune.upper", 200)),
                [str(item.get("label", key)) for key, item in ds.items() if bool(item.get("enabled", True))],
                str(cfg.get("agent.dataset_name", "AgentX-claudecode")),
                str(cfg.get("report.title", "")),
                str(cfg.get("report.company", "") or ""),
                str(cfg.get("report.operator", "") or ""),
            )

        def _field_refresh(cfg: Config) -> tuple[Any, ...]:
            """按 [items_check, *run_inputs] 的输出顺序返回全部字段值。"""
            return (
                [ITEM_BY_KEY[key].name for key in cfg.run_items()],
                str(cfg.get("endpoint.base_url")),
                str(cfg.get("endpoint.model")),
                str(cfg.get("endpoint.api_key", "") or ""),
                *_advanced_field_values(cfg),
                *_extra_field_values(cfg),
            )

        # 字段刷新元组里精度数据集 Checkbox 的位置（items + endpoint + advanced 之后第 9 个）
        _ACC_FIELD_INDEX = 1 + 3 + 16 + 8

        def _apply_config_values(cfg: Config, status: str) -> tuple[Any, ...]:
            values = list(_field_refresh(cfg))
            ds = cfg.get("accuracy.datasets", {}) or {}
            values[_ACC_FIELD_INDEX] = gr.update(
                choices=[str(item.get("label", key)) for key, item in ds.items()],
                value=[str(item.get("label", key)) for key, item in ds.items() if bool(item.get("enabled", True))],
            )
            return (*values, _dataset_table_html(cfg), status)

        def _prepare(
            base: str,
            model_name: str,
            key_value: str,
            items_labels: Any,
            *fields: Any,
        ) -> list[str]:
            keys = _keys_for_labels(items_labels)
            if not keys:
                raise UCMAcceptError("请至少勾选一个测试项")
            service.update_endpoint(base_url=base, model=model_name, api_key=key_value)
            service.config.set("run.items", keys)
            advanced, extra = fields[:16], fields[16:]
            overrides = _advanced_overrides(*advanced)
            overrides = deep_merge(
                overrides,
                _extra_overrides(*extra[:8], dict(acc_label_to_key), extra[8], *extra[9:]),
            )
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
            scenario_label: str,
            items_labels: Any,
            base: str,
            model_name: str,
            key_value: str,
            *fields: Any,
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

            try:
                _prepare(base, model_name, key_value, items_labels, *fields)
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
            items_labels: Any,
            base: str,
            model_name: str,
            key_value: str,
            *fields: Any,
            progress=gr.Progress(track_tqdm=False),  # noqa: B008 - Gradio 注入约定
        ):
            logs: list[str] = []

            def on_progress(event: ProgressEvent) -> None:
                logs.append(_format_event(event))
                try:
                    progress(event.overall, desc=event.message[:100])
                except Exception:  # noqa: BLE001
                    pass

            try:
                keys = _prepare(base, model_name, key_value, items_labels, *fields)
            except Exception as exc:  # noqa: BLE001
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

        def save_click(path_value: str, items_labels: Any, base: str, model_name: str, key_value: str, *fields: Any):
            try:
                _prepare(base, model_name, key_value, items_labels, *fields)
                target = service.config.save(path_value or _default_save_path(service.config))
                return (
                    *_field_refresh(service.config),
                    _dataset_table_html(service.config),
                    f"✅ 配置已保存：`{target}`\n下次启动复用：`ucm-accept --config {target}`",
                )
            except Exception as exc:  # noqa: BLE001
                return (*_unchanged(34), f"❌ 保存失败：{exc}")

        def export_click(items_labels: Any, base: str, model_name: str, key_value: str, *fields: Any):
            try:
                _prepare(base, model_name, key_value, items_labels, *fields)
                target = service.outputs_root / "ucm-accept.export.yaml"
                service.config.save(target)
                return str(target), f"✅ 已导出当前生效配置：`{target}`"
            except Exception as exc:  # noqa: BLE001
                return None, f"❌ 导出失败：{exc}"

        def import_click(file_obj: Any):
            if file_obj is None:
                return (*_unchanged(34), "⚠️ 未选择配置文件")
            path = file_obj.name if hasattr(file_obj, "name") else str(file_obj)
            try:
                cfg = Config.load(path)
            except ConfigError as exc:
                return (*_unchanged(34), f"❌ 配置无效：{exc}")
            except OSError as exc:
                return (*_unchanged(34), f"❌ 读取失败：{exc}")
            try:
                service.replace_config(cfg)
            except Exception as exc:  # noqa: BLE001
                return (*_unchanged(34), f"❌ 应用失败：{exc}")
            ds = cfg.get("accuracy.datasets", {}) or {}
            acc_label_to_key.clear()
            acc_label_to_key.update({str(item.get("label", key)): key for key, item in ds.items()})
            return _apply_config_values(cfg, f"✅ 已导入并应用：`{path}`")

        def reset_click():
            try:
                cfg = Config.load(overrides={"app": {"report_dir": str(service.outputs_root)}})
            except ConfigError as exc:
                return (*_unchanged(34), f"❌ 加载默认配置失败：{exc}")
            try:
                service.replace_config(cfg)
            except Exception as exc:  # noqa: BLE001
                return (*_unchanged(34), f"❌ 应用失败：{exc}")
            ds = cfg.get("accuracy.datasets", {}) or {}
            acc_label_to_key.clear()
            acc_label_to_key.update({str(item.get("label", key)): key for key, item in ds.items()})
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
            if key == "multiturn":
                inputs = [scenarios[key], items_check, *run_inputs]
                run_buttons[key].click(
                    run_one,
                    inputs=[gr.State(key), *inputs],
                    outputs=output_components,
                    concurrency_limit=1,
                )
            else:
                run_buttons[key].click(
                    run_one,
                    inputs=[gr.State(key), gr.State(""), items_check, *run_inputs],
                    outputs=output_components,
                    concurrency_limit=1,
                )
        run_all_btn.click(
            run_all,
            inputs=[items_check, *run_inputs],
            outputs=output_components,
            concurrency_limit=1,
        )
        refresh_btn.click(refresh_latest, inputs=[], outputs=output_components)
        pdf_btn.click(pdf_click, inputs=[], outputs=[pdf_file, stage_md])
        save_btn.click(
            save_click,
            inputs=[save_path, items_check, *run_inputs],
            outputs=[items_check, *run_inputs, dataset_table, cfg_status],
            concurrency_limit=1,
        )
        export_btn.click(
            export_click,
            inputs=[items_check, *run_inputs],
            outputs=[cfg_export_file, cfg_status],
            concurrency_limit=1,
        )
        import_file.upload(
            import_click,
            inputs=[import_file],
            outputs=[items_check, *run_inputs, dataset_table, cfg_status],
            concurrency_limit=1,
        )
        reset_btn.click(
            reset_click,
            inputs=[],
            outputs=[items_check, *run_inputs, dataset_table, cfg_status],
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
