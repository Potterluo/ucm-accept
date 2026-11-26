from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import sys
import tarfile
import time
from pathlib import Path

from . import __version__
from .assetpack import import_asset_pack
from .assets import builtin_tokenizers, describe, find_assets_root, verify_manifest
from .compare import build_compare_html
from .config import Config, ConfigError, load_config
from .doctor import run_doctor
from .errors import UCMAcceptError
from .events import ProgressEvent
from .models import (
    ITEM_BY_KEY,
    ITEM_KEYS,
    STATUS_LABELS,
    STATUS_MARKS,
    AcceptanceReport,
    Status,
    human_duration,
)
from .report import export_pdf
from .service import AcceptanceService
from .utils import find_latest_report, render_table, shorten

# Windows 控制台默认可能是 GBK；统一为 UTF-8，避免中文表格/✓ 输出异常。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

_USE_COLOR = sys.stdout.isatty() and not bool(os.environ.get("NO_COLOR"))


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


GREEN = lambda text: _c(text, "32")  # noqa: E731
RED = lambda text: _c(text, "31")  # noqa: E731
YELLOW = lambda text: _c(text, "33")  # noqa: E731
DIM = lambda text: _c(text, "2")  # noqa: E731
BOLD = lambda text: _c(text, "1")  # noqa: E731
CYAN = lambda text: _c(text, "36")  # noqa: E731


def _status_text(status: Status) -> str:
    return f"{STATUS_MARKS[status]} {STATUS_LABELS[status]}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ucm-accept",
        description="UCM 推理加速产品 · 客户现网验收工具（EvalScope 统一承载）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  ucm-accept                         # 交互式菜单（容器 / 堡垒机）\n"
            "  ucm-accept --all                   # 按 run.items 范围跑完并生成报告\n"
            "  ucm-accept --items perf,sla        # 只跑基础性能 + SLA\n"
            "  ucm-accept --item perf             # 只跑基础性能\n"
            "  ucm-accept --save-config my.yaml   # 保存当前生效配置，之后 --config my.yaml 复用\n"
            "  ucm-accept --gui                   # 启动浏览器 GUI\n"
            "  ucm-accept --doctor --probe        # 现场自检\n"
            "  ucm-accept --mock --fast --all     # 演示 / CI 虚跑\n"
        ),
    )
    parser.add_argument("--config", help="外部 config.yaml 路径")
    parser.add_argument("--outputs", help="报告输出根目录（默认 ./outputs）")
    parser.add_argument("--base-url", help="覆盖服务地址，例如 http://127.0.0.1:8801/v1")
    parser.add_argument("--model", help="覆盖模型名称")
    parser.add_argument("--api-key", help="覆盖 API Key")
    parser.add_argument("--item", choices=list(ITEM_KEYS), help="只执行单个测试项")
    parser.add_argument(
        "--items",
        help="只执行指定测试项，逗号分隔，可用编号或名称，例如 perf,sla 或 1,3",
    )
    parser.add_argument("--save-config", help="把当前生效配置另存为 YAML 后退出（API Key 不落盘）")
    try:
        _scenario_keys = list((load_config(None).get("multiturn.scenarios", {}) or {}).keys())
    except Exception:  # noqa: BLE001 - 配置不可读时退化为自由文本
        _scenario_keys = None
    parser.add_argument(
        "--scenario",
        choices=_scenario_keys,
        help="多轮对话场景预设（来自 config multiturn.scenarios）",
    )
    parser.add_argument("--all", action="store_true", help="按配置 run.items 的范围顺序执行验收")
    parser.add_argument("--sla-mode", choices=["verify", "auto_tune"], help="覆盖 SLA 模式")
    parser.add_argument("--report", help="将本次 HTML 报告另存到指定路径")
    parser.add_argument("--pdf", action="store_true", help="同时导出 PDF（需 weasyprint 或 chromium）")
    parser.add_argument("--mock", action="store_true", help="使用模拟引擎（演示 / 虚跑，报告会标注）")
    parser.add_argument("--fast", action="store_true", help="模拟模式零延迟")
    parser.add_argument("--profile", choices=["nominal", "degraded"], default="nominal", help="模拟画像")
    parser.add_argument("--gui", action="store_true", help="启动浏览器 GUI（交互菜单 [G] 同效）")
    parser.add_argument("--host", default="127.0.0.1", help="GUI 监听地址")
    parser.add_argument("--port", type=int, default=0, help="GUI 端口，0 表示随机可用端口")
    parser.add_argument("--no-browser", action="store_true", help="GUI 启动时不自动打开浏览器")
    parser.add_argument("--doctor", action="store_true", help="执行现场环境自检")
    parser.add_argument("--probe", action="store_true", help="自检时探测服务连通性")
    parser.add_argument("--version", action="version", version=f"ucm-accept {__version__}")
    return parser


def _apply_args(config: Config, args: argparse.Namespace) -> Config:
    if args.outputs:
        config.set("app.report_dir", str(Path(args.outputs).expanduser()))
    config.apply_endpoint(args.base_url, args.model, args.api_key)
    if args.sla_mode:
        config.set("sla.mode", args.sla_mode)
    return config


def _parse_selection(text: str) -> list[str]:
    """把 1,3-5 / perf,sla 之类的输入解析为去重且有序的测试项列表。"""
    tokens = [token for token in re.split(r"[,，、\s]+", str(text).strip()) if token]
    if not tokens:
        raise ValueError("测试项选择不能为空，例如 1,3-5 或 perf,sla")
    picked: set[str] = set()
    for token in tokens:
        for part in _expand_range(token):
            if part.isdigit():
                index = int(part)
                if not 1 <= index <= len(ITEM_KEYS):
                    raise ValueError(f"测试项编号超出范围：{index}（有效 1-{len(ITEM_KEYS)}）")
                picked.add(ITEM_KEYS[index - 1])
            elif part.lower() in ITEM_KEYS:
                picked.add(part.lower())
            else:
                known = "、".join(f"{index + 1}={key}" for index, key in enumerate(ITEM_KEYS))
                raise ValueError(f"未知测试项：{part}（可用：{known}）")
    ordered = [key for key in ITEM_KEYS if key in picked]
    return ordered


def _expand_range(token: str) -> list[str]:
    match = re.fullmatch(r"(\d+)-(\d+)", token)
    if not match:
        return [token]
    start, end = int(match.group(1)), int(match.group(2))
    if start > end:
        raise ValueError(f"编号区间写反：{token}（应为 起始-结束）")
    return [str(value) for value in range(start, end + 1)]


def _progress_printer():
    last_shown = {"fraction": -1.0}

    def callback(event: ProgressEvent) -> None:
        prefix = f"[{event.overall * 100:5.1f}%]"
        if event.level == "start":
            print()
            print(BOLD(f"▶ {event.message}"))
        elif event.level == "success":
            print(GREEN(f"  ✓ {event.message}"))
        elif event.level == "warning":
            print(YELLOW(f"  ! {event.message}"))
        elif event.level == "error":
            print(RED(f"  ✗ {event.message}"))
        elif event.level == "command":
            print(DIM(f"  {prefix} {shorten(event.message, 180)}"))
        else:
            if event.fraction - last_shown["fraction"] >= 0.2 or event.fraction >= 1.0:
                last_shown["fraction"] = event.fraction
                print(DIM(f"  {prefix} {shorten(event.message, 160)}"))
            elif event.message:
                print(DIM(f"  {prefix} {shorten(event.message, 160)}"))
        last_shown["fraction"] = max(last_shown["fraction"], event.fraction)

    return callback


def _print_report_summary(report: AcceptanceReport, report_path: Path | None = None) -> None:
    print()
    print(BOLD("=" * 74))
    color = {"通过": GREEN, "有条件通过": YELLOW, "不通过": RED}.get(report.conclusion, DIM)
    print(BOLD("验收结论：") + color(report.conclusion))
    for reason in report.reasons:
        print(f"  · {reason}")
    print(BOLD("=" * 74))
    rows = []
    for key in ITEM_KEYS:
        item = report.items.get(key)
        if not item:
            rows.append([str(ITEM_KEYS.index(key) + 1), ITEM_BY_KEY[key].name, "○ 待执行", "—", "—"])
            continue
        rows.append(
            [
                str(ITEM_KEYS.index(key) + 1),
                item.name,
                _status_text(item.status),
                human_duration(item.duration_s) if item.finished_at else "—",
                shorten(item.summary or item.error or "—", 46),
            ]
        )
    print(render_table(["#", "测试项", "状态", "耗时", "结论摘要"], rows, aligns=["center", "left", "center", "right", "left"]))
    if report_path:
        print(f"报告：{report_path}")
        print(f"原始数据：{report.output_dir}")
    print()


def _exit_code(report: AcceptanceReport | None) -> int:
    if report is None:
        return 3
    return {"通过": 0, "有条件通过": 0, "不通过": 2, "未完成": 3}.get(report.conclusion, 3)


def _save_extra(report_path: Path | None, args: argparse.Namespace) -> None:
    if not report_path or not report_path.exists():
        return
    target = None
    if args.report:
        destination = Path(args.report).expanduser()
        if destination.is_dir() or args.report.endswith(("/", "\\")):
            destination = destination / "report.html"
        if destination.suffix.lower() not in {".html", ".htm"}:
            destination = destination.with_suffix(".html")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(report_path, destination)
        target = destination
        print(f"HTML 报告已另存：{target}")
    if args.pdf:
        html_source = target or report_path
        try:
            pdf = export_pdf(html_source)
            print(f"PDF 报告已导出：{pdf}")
        except Exception as exc:  # noqa: BLE001
            print(YELLOW(f"PDF 导出失败：{exc}"))
            print(DIM("可使用浏览器打开 HTML 后打印为 PDF。"))


def _doctor(config: Config, args: argparse.Namespace) -> int:
    print(BOLD("UCM 验收工具 · 现场自检"))
    print(DIM(f"配置：{config.source or '内置默认配置'}"))
    results = run_doctor(config, probe=args.probe, mock=args.mock)
    marks = {"ok": GREEN("✓ 通过"), "warn": YELLOW("! 关注"), "fail": RED("✗ 失败"), "skip": DIM("– 跳过")}
    rows = [[item.name, marks.get(item.status, item.status), item.detail, item.hint] for item in results]
    print(render_table(["检查项", "状态", "说明", "建议"], rows, aligns=["left", "left", "left", "left"]))
    failures = sum(1 for item in results if item.status == "fail")
    warnings = sum(1 for item in results if item.status == "warn")
    if failures:
        print(RED(f"自检发现 {failures} 项失败、{warnings} 项需关注。"))
        return 1
    print(GREEN(f"自检通过（{warnings} 项需关注）。"))
    return 0


def _run_noninteractive(service: AcceptanceService, args: argparse.Namespace) -> int:
    progress = _progress_printer()
    item_status: Status | None = None
    try:
        if args.items and args.item:
            print(RED("--item 与 --items 不能同时使用"))
            return 2
        if args.all or args.items:
            keys = _parse_selection(args.items) if args.items else None
            report = service.run_all(progress=progress, keys=keys)
        else:
            item = service.run_item(
                args.item,
                scenario=args.scenario if args.item == "multiturn" else None,
                progress=progress,
            )
            item_status = item.status
            report = service.current_report()
            if report is None:
                raise UCMAcceptError("未生成验收报告")
            print(f"单项结果：{item.name} · {STATUS_LABELS[item.status]}")
    except KeyboardInterrupt:
        service.cancel()
        service.shutdown(timeout=10.0)
        print(YELLOW("\n已中断验收。报告与原始数据已保存到输出目录。"))
        return 130
    except UCMAcceptError as exc:
        print(RED(f"执行失败：{exc}"))
        return 3

    report_path = service.report_path()
    _print_report_summary(report, report_path)
    _save_extra(report_path, args)
    if item_status is not None and not args.all:
        if item_status in {Status.PASSED, Status.WARNING}:
            return 0
        return 2 if item_status == Status.FAILED else 3
    return _exit_code(report)


def _list_runs(service: AcceptanceService) -> list[tuple[str, Path, Path]]:
    """历史验收列表：(run_id, report.json, report.html)，新到旧。"""
    root = service.outputs_root / "runs"
    runs: list[tuple[str, Path, Path]] = []
    if not root.is_dir():
        return runs
    for run_dir in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
        report_json = run_dir / "report.json"
        if report_json.is_file():
            runs.append((run_dir.name, report_json, run_dir / "report.html"))
    return runs


def _print_menu(service: AcceptanceService) -> None:
    mode = "模拟演示（不产生真实请求）" if service.mode == "mock" else "EvalScope 实机"
    hub = find_assets_root(service.config.get("app.assets_dir") or None)
    assets_hint = "未配置（离线能力受限，可用 [P] 导入）" if hub is None else describe(hub)
    runs = _list_runs(service)
    scope = "、".join(str(ITEM_BY_KEY[key].short) for key in service.config.run_items())
    width = 62
    print()
    print(BOLD("=" * width))
    print(BOLD(f" UCM 推理加速验收工具 (CLI)  v{__version__}"))
    print(BOLD("=" * width))
    print(f" 引擎: {CYAN(mode)}    范围: {scope}")
    print(f" 服务: {service.config.get('endpoint.base_url')}    模型: {service.config.get('endpoint.model')}")
    print(f" 资产包: {assets_hint}")
    print(f" 输出: {service.outputs_root}（历史报告 {len(runs)} 份）")
    print(DIM("-" * width))
    for key in ITEM_KEYS:
        meta = ITEM_BY_KEY[key]
        print(f" [{meta.order}] {meta.name:<14}{DIM(meta.eta)}")
    print(DIM("-" * width))
    print(" 执行  [编号] 跑单项/组合（如 1,3-5）  [A] 执行所选范围  [T] 选择范围")
    print(" 配置  [C] 每项测试配置  [S] 服务/模型/Tokenizer  [P] 资产包导入与校验")
    print(" 结果  [R] 最近报告  [L] 历史对比  [E] 导出 HTML/PDF/打包")
    print(" 工具  [D] 环境自检  [G] 打开 GUI（浏览器版）  [Q] 退出")
    print(DIM("-" * width))


def _show_latest(service: AcceptanceService) -> None:
    path = find_latest_report(service.outputs_root)
    if not path:
        print(YELLOW("暂无可查看的报告。"))
        return
    try:
        report = AcceptanceReport.load_json(path)
    except Exception as exc:  # noqa: BLE001
        print(RED(f"读取报告失败：{exc}"))
        return
    _print_report_summary(report, path.with_suffix(".html") if path.suffix == ".json" else path)


def _prompt(text: str, default: str = "") -> str:
    prompt = f"{text}" + (f"（默认 {default}）" if default else "") + "："
    try:
        value = input(prompt).strip()
    except EOFError:
        return default
    return value or default


def _prompt_int(text: str, default: int) -> int:
    raw = _prompt(text, str(default))
    try:
        return int(raw)
    except ValueError:
        print(YELLOW(f"输入「{raw}」不是整数，保留默认 {default}。"))
        return default


def _parse_numbers(text: str, upper: int, least: int = 1) -> list[int]:
    """把 1,3-5 之类的编号输入解析为有序去重列表（1-based）。"""
    tokens = [token for token in re.split(r"[,，、\s]+", str(text).strip()) if token]
    if not tokens:
        raise ValueError("选择不能为空")
    picked: set[int] = set()
    for token in tokens:
        match = re.fullmatch(r"(\d+)-(\d+)", token)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if start > end:
                raise ValueError(f"编号区间写反：{token}")
            picked.update(range(start, end + 1))
        elif token.isdigit():
            picked.add(int(token))
        else:
            raise ValueError(f"无法识别的选择：{token}")
    ordered = sorted(value for value in picked if 1 <= value <= upper)
    if len(ordered) < least:
        raise ValueError(f"至少选择 {least} 项")
    return ordered


# ---------------------------------------------------------------- 配置子菜单


def _config_menu(service: AcceptanceService) -> None:
    editors = {"1": _config_perf, "2": _config_multiturn, "3": _config_sla,
               "4": _config_accuracy, "5": _config_agent}
    while True:
        cfg = service.config
        print(BOLD("\n── 每项测试配置（回车保留现值）──"))
        groups = cfg.get("perf.groups", []) or []
        if groups:
            perf_desc = "；".join("并发" + "/".join(str(v) for v in g.get("parallel") or []) for g in groups)
        else:
            perf_desc = "未配置"
        print(f" [1] 基础性能   {perf_desc} · 数据集 {cfg.get('perf.dataset')}")
        presets = cfg.get("multiturn.scenarios", {}) or {}
        selected = cfg.get("multiturn.scenarios_selected", []) or []
        sel_label = "、".join(
            str((presets.get(key) or {}).get("label", key)) for key in selected
        ) or "未选择"
        print(f" [2] 多轮对话   {sel_label} · 会话 {cfg.get('multiturn.conversations')}"
              f" · 并行 {cfg.get('multiturn.parallel')}"
              f" · 轮次 {cfg.get('multiturn.min_turns')}-{cfg.get('multiturn.max_turns')}")
        print(f" [3] SLA        {cfg.get('sla.mode')} · 输入 {cfg.get('sla.input_length')}"
              f" / 输出 {cfg.get('sla.output_tokens')}"
              f" · 并发 {cfg.get('sla.auto_tune.lower')}-{cfg.get('sla.auto_tune.upper')}")
        datasets = cfg.get("accuracy.datasets", {}) or {}
        enabled = sum(1 for item in datasets.values() if item.get("enabled", True))
        print(f" [4] 精度       {enabled}/{len(datasets)} 个数据集 · runs {cfg.get('accuracy.runs')}")
        print(f" [5] Agent      context {cfg.get('agent.context_required')}"
              f" · 时长 {int(cfg.get('agent.duration_s') or 900) // 60}min"
              f" · {cfg.get('agent.dataset_name')}")
        print(" [B] 返回")
        choice = _prompt("选择", "B").upper()
        if choice == "B":
            return
        editor = editors.get(choice)
        if editor is None:
            print(YELLOW("无效选择，请输入 1-5 或 B。"))
            continue
        editor(service)


def _config_perf(service: AcceptanceService) -> None:
    cfg = service.config
    print(BOLD("\n── 基础性能 ──"))
    groups = cfg.get("perf.groups", []) or [{}]
    first = groups[0]
    parallel_raw = _prompt("并发档位（逗号分隔，如 1,2,4,8）",
                           ",".join(str(v) for v in first.get("parallel") or [8]))
    try:
        parallel_values = [int(v) for v in re.split(r"[,，\s]+", parallel_raw) if v.strip()]
        if not parallel_values:
            raise ValueError
    except ValueError:
        print(RED(f"并发档位格式错误：{parallel_raw}"))
        return
    number = _prompt_int("每组请求数", int(first.get("number") or 64))
    input_tokens = _prompt_int("输入 tokens", int(first.get("input") or 512))
    output_tokens = _prompt_int("输出 tokens", int(first.get("output") or 64))
    ratio = _prompt_int("前缀命中率 %（0-100）", int(round(float(first.get("prefix_ratio") or 0) * 100)))
    prefix_count = _prompt_int("前缀块数", int(first.get("prefix_count") or 2))
    warmup = _prompt_int("预热请求数", int(cfg.get("perf.warmup_num") or 0))
    dataset = _prompt("数据集", str(cfg.get("perf.dataset") or "random"))
    timeout = _prompt_int("请求超时（秒）", int(cfg.get("endpoint.timeout_s", 180) or 180))
    cfg.set("perf.groups", [{
        "parallel": [value],
        "number": max(1, number),
        "input": max(1, input_tokens),
        "output": max(1, output_tokens),
        "prefix_ratio": max(0.0, min(1.0, ratio / 100)),
        "prefix_count": max(1, prefix_count),
    } for value in parallel_values])
    cfg.set("perf.dataset", dataset.strip() or "random")
    cfg.set("perf.warmup_num", max(0, warmup))
    cfg.set("endpoint.timeout_s", max(30, timeout))
    print(GREEN(f"基础性能已更新：{len(parallel_values)} 组并发（{'/'.join(map(str, parallel_values))}）"))


def _config_multiturn(service: AcceptanceService) -> None:
    cfg = service.config
    print(BOLD("\n── 多轮对话 ──"))
    presets = cfg.get("multiturn.scenarios", {}) or {}
    selected = set(cfg.get("multiturn.scenarios_selected", []) or [])
    keys = list(presets.keys())
    for index, (key, item) in enumerate(presets.items(), 1):
        mark = GREEN("✓") if key in selected else DIM("○")
        print(f" [{index}] {mark} {item.get('label', key)}")
    text = _prompt("启用场景编号（如 1,3；all=全部；回车保持）", "")
    if text:
        try:
            if text.strip().lower() == "all":
                chosen = set(keys)
            else:
                chosen = {keys[i - 1] for i in _parse_numbers(text, len(keys))}
        except ValueError as exc:
            print(RED(str(exc)))
            return
        cfg.set("multiturn.scenarios_selected", [key for key in keys if key in chosen])
    conversations = _prompt_int("会话组数", int(cfg.get("multiturn.conversations", 12) or 12))
    parallel = _prompt_int("并发会话", int(cfg.get("multiturn.parallel", 4) or 4))
    min_turns = _prompt_int("最少轮数", int(cfg.get("multiturn.min_turns", 2) or 2))
    max_turns = _prompt_int("最多轮数", int(cfg.get("multiturn.max_turns", 5) or 5))
    cfg.set("multiturn.conversations", max(1, conversations))
    cfg.set("multiturn.parallel", max(1, parallel))
    cfg.set("multiturn.min_turns", max(1, min_turns))
    cfg.set("multiturn.max_turns", max(1, max_turns))
    print(GREEN("多轮对话配置已更新"))


def _config_sla(service: AcceptanceService) -> None:
    cfg = service.config
    print(BOLD("\n── SLA 自动调优 ──"))
    mode = _prompt("模式 verify/auto_tune", str(cfg.get("sla.mode") or "auto_tune")).lower()
    input_len = _prompt_int("输入长度（tokens）", int(cfg.get("sla.input_length") or 65536))
    output = _prompt_int("输出 tokens", int(cfg.get("sla.output_tokens") or 512))
    ratio = _prompt_int("前缀命中率 %", int(round(float(cfg.get("sla.prefix_ratio") or 0.9) * 100)))
    prefix_count = _prompt_int("前缀块数", int(cfg.get("sla.prefix_count") or 8))
    lower = _prompt_int("调优下限并发", int(cfg.get("sla.auto_tune.lower") or 2))
    upper = _prompt_int("调优上限并发", int(cfg.get("sla.auto_tune.upper") or 256))
    cfg.set("sla.mode", mode if mode in {"verify", "auto_tune"} else "auto_tune")
    cfg.set("sla.input_length", max(1, input_len))
    cfg.set("sla.output_tokens", max(1, output))
    cfg.set("sla.prefix_ratio", max(0.0, min(1.0, ratio / 100)))
    cfg.set("sla.prefix_count", max(1, prefix_count))
    cfg.set("sla.auto_tune.lower", max(1, lower))
    cfg.set("sla.auto_tune.upper", max(1, upper))
    cfg.set("sla.target.concurrency", max(1, upper))
    print(GREEN("SLA 配置已更新（判定完全由 EvalScope --sla-auto-tune 原生执行）"))


def _config_accuracy(service: AcceptanceService) -> None:
    cfg = service.config
    print(BOLD("\n── 精度 ──"))
    datasets = cfg.get("accuracy.datasets", {}) or {}
    keys = list(datasets.keys())
    for index, (key, item) in enumerate(datasets.items(), 1):
        mark = GREEN("✓") if item.get("enabled", True) else DIM("○")
        print(f" [{index}] {mark} {item.get('label', key)}（{item.get('dataset', key)}）")
    text = _prompt("启用数据集编号（如 1,2,4；all=全部；回车保持）", "")
    if text:
        try:
            if text.strip().lower() == "all":
                chosen = set(keys)
            else:
                chosen = {keys[i - 1] for i in _parse_numbers(text, len(keys))}
        except ValueError as exc:
            print(RED(str(exc)))
            return
        for key, item in datasets.items():
            item["enabled"] = key in chosen
        cfg.set("accuracy.datasets", datasets)
    runs = _prompt_int("执行轮数（KVCache 一致性判定需 ≥2）", int(cfg.get("accuracy.runs") or 2))
    limit = _prompt_int("每数据集样本上限（0 = 全量）", 0)
    cfg.set("accuracy.runs", max(1, runs))
    datasets = cfg.get("accuracy.datasets", {}) or {}
    for item in datasets.values():
        if limit > 0:
            item["limit"] = limit
        else:
            item.pop("limit", None)
    cfg.set("accuracy.datasets", datasets)
    print(GREEN("精度配置已更新（判定由 EvalScope 原生执行）"))


def _config_agent(service: AcceptanceService) -> None:
    cfg = service.config
    print(BOLD("\n── Agent（AgentX）──"))
    context = _prompt_int("服务上下文窗口（tokens）", int(cfg.get("agent.context_required") or 262144))
    duration = _prompt_int("benchmark 时长（分钟，EvalScope 要求 ≥15）",
                           int(cfg.get("agent.duration_s") or 900) // 60)
    dataset = _prompt("数据集名", str(cfg.get("agent.dataset_name") or "AgentX-claudecode"))
    parallel = _prompt_int("并发", int(cfg.get("agent.parallel") or 4))
    cfg.set("agent.context_required", max(1, context))
    cfg.set("agent.duration_s", max(900, max(1, duration) * 60))
    cfg.set("agent.dataset_name", dataset.strip() or "AgentX-claudecode")
    cfg.set("agent.parallel", max(1, parallel))
    print(GREEN("Agent 配置已更新（traces 与判定由 EvalScope 原生执行）"))


# ---------------------------------------------------------------- 服务 / Tokenizer


def _service_menu(service: AcceptanceService) -> None:
    cfg = service.config
    print(BOLD("\n── 服务与模型 ──"))
    base_url = _prompt("服务地址", str(cfg.get("endpoint.base_url")))
    model = _prompt("模型名称", str(cfg.get("endpoint.model")))
    try:
        service.update_endpoint(base_url=base_url, model=model)
    except UCMAcceptError as exc:
        print(RED(str(exc)))
        return
    print(GREEN("服务配置已更新；下一项测试将开启新报告。"))
    _tokenizer_menu(service)


def _tokenizer_menu(service: AcceptanceService) -> None:
    cfg = service.config
    hub = find_assets_root(cfg.get("app.assets_dir") or None)
    builtin = builtin_tokenizers(hub) if hub else []
    current = str(cfg.get("perf.tokenizer_path") or "")
    print(f"\n当前 tokenizer：{current or '（跟随服务端模型）'}")
    if builtin:
        print(" 资产包内置：")
        for index, name in enumerate(builtin[:12], 1):
            print(f"  [{index}] {name}")
        if len(builtin) > 12:
            print(f"  … 共 {len(builtin)} 个")
    text = _prompt("选择编号 / 输入路径或 hub id（回车保持）", "")
    if not text:
        return
    if text.isdigit() and builtin and 1 <= int(text) <= min(len(builtin), 12):
        path = str(hub / "tokenizers" / builtin[int(text) - 1])
        cfg.set("perf.tokenizer_path", path)
        print(GREEN(f"tokenizer 已设为资产包内置：{path}"))
        return
    if text.lower() in {"0", "clear", "none"}:
        cfg.set("perf.tokenizer_path", "")
        print(GREEN("tokenizer 已清空（跟随服务端模型）。"))
        return
    candidate = Path(text).expanduser()
    if candidate.exists():
        cfg.set("perf.tokenizer_path", str(candidate.resolve()))
    else:
        cfg.set("perf.tokenizer_path", text)  # hub id 形式，在线时由 evalscope 下载
    print(GREEN(f"tokenizer 已更新：{cfg.get('perf.tokenizer_path')}"))


# ---------------------------------------------------------------- 资产包


def _import_asset_pack(service: AcceptanceService) -> None:
    raw = _prompt("资源包路径（tar.gz / part-00 分卷 / 已解压目录）", "")
    if not raw:
        return
    print(DIM("导入中：合并分卷 → 解压 → SHA256 校验…（大包需要几分钟）"))
    try:
        result = import_asset_pack(service.config, raw)
    except (FileNotFoundError, ValueError, tarfile.TarError, OSError) as exc:
        print(RED(f"导入失败：{exc}"))
        return
    total, problems = result["total"], result["problems"]
    if problems:
        print(RED(f"校验失败：manifest {total} 项中 {len(problems)} 个问题："))
        for problem in problems:
            print(f"  · {problem}")
        return
    print(GREEN(f"资产包已导入并校验通过（manifest {total} 项）：{result['hub']}"))
    print(DIM(f"持久化方式：export UCM_ASSETS_DIR={result['hub']}"))


def _assets_menu(service: AcceptanceService) -> None:
    while True:
        hub = find_assets_root(service.config.get("app.assets_dir") or None)
        print(BOLD("\n── 资产包 ──"))
        print(f" 当前：{describe(hub)}")
        if hub:
            total, problems = verify_manifest(hub)
            if problems:
                print(YELLOW(f" 校验：manifest {total} 项，发现 {len(problems)} 个问题："))
                for problem in problems:
                    print(f"   · {problem}")
            else:
                print(GREEN(f" 校验：manifest {total} 项全部完整"))
            toks = builtin_tokenizers(hub)
            head = "、".join(toks[:4]) + ("…" if len(toks) > 4 else "")
            print(f" 内置 tokenizer：{len(toks)} 个" + (f"（{head}）" if toks else ""))
        print(" [1] 导入资源包（tar.gz / part-00 分卷 / 目录）")
        print(" [2] 刷新状态与校验")
        print(" [3] 设置 Tokenizer（内置列表 / 自定义）")
        print(" [B] 返回")
        choice = _prompt("选择", "B").upper()
        if choice == "B":
            return
        if choice == "1":
            _import_asset_pack(service)
        elif choice == "2":
            continue
        elif choice == "3":
            _tokenizer_menu(service)
        else:
            print(YELLOW("无效选择，请输入 1-3 或 B。"))


# ---------------------------------------------------------------- 结果


def _compare_menu(service: AcceptanceService) -> None:
    runs = _list_runs(service)
    if len(runs) < 2:
        print(YELLOW("历史报告不足 2 份，先完成几次验收再来对比。"))
        return
    print(BOLD("\n── 历史验收 ──"))
    for index, (run_id, report_json, _html) in enumerate(runs[:12], 1):
        try:
            conclusion = AcceptanceReport.load_json(report_json).conclusion
        except Exception:  # noqa: BLE001
            conclusion = "?"
        print(f" [{index}] {run_id}   {conclusion}")
    text = _prompt("选择 2-5 份对比（如 1,2,3；回车返回）", "")
    if not text:
        return
    try:
        picks = _parse_numbers(text, min(len(runs), 12), least=2)
    except ValueError as exc:
        print(RED(str(exc)))
        return
    entries = [{"label": runs[i - 1][0], "report": AcceptanceReport.load_json(runs[i - 1][1])}
               for i in picks[:5]]
    target = service.outputs_root / f"compare-{time.strftime('%Y%m%d_%H%M%S')}.html"
    target.write_text(build_compare_html(entries), encoding="utf-8")
    print(GREEN(f"对比报告已生成：{target}"))


def _export_menu(service: AcceptanceService) -> None:
    runs = _list_runs(service)
    if not runs:
        print(YELLOW("暂无验收报告可导出。"))
        return
    run_id, report_json, report_html = runs[0]
    print(f"\n最新验收：{run_id}")
    print(" [1] HTML 另存   [2] 导出 PDF   [3] 打包 zip（报告+原始数据）   [B] 返回")
    choice = _prompt("选择", "B").upper()
    if choice == "1":
        target = Path(_prompt("另存为", str(service.outputs_root / f"export-{run_id}.html"))).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(report_html if report_html.exists() else report_json.with_suffix(".html"), target)
        print(GREEN(f"已导出：{target}"))
    elif choice == "2":
        try:
            print(GREEN(f"已导出：{export_pdf(report_html if report_html.exists() else report_json)}"))
        except Exception as exc:  # noqa: BLE001
            print(YELLOW(f"PDF 导出失败：{exc}"))
            print(DIM("需要 weasyprint 或 chromium（pip install '.[pdf]'）。"))
    elif choice == "3":
        target = service.outputs_root / f"{run_id}-bundle"
        shutil.make_archive(str(target), "zip", report_json.parent)
        print(GREEN(f"已打包：{target}.zip"))


# ---------------------------------------------------------------- GUI


def _launch_gui(service: AcceptanceService, args: argparse.Namespace) -> None:
    from .webapp import main as web_main

    print(BOLD("\n启动浏览器 GUI（Ctrl+C 返回菜单）…"))
    print(DIM(f"  地址：http://{args.host}:{args.port or '随机端口'}"))
    print(DIM("  GUI 与 CLI 共用同一配置与输出目录；菜单内 [Q] 之外的改动会同步生效。"))
    try:
        web_main(
            config=service.config,
            mode=service.mode,
            mock_profile=args.profile,
            mock_delay_ms=0 if args.fast else None,
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
        )
    except KeyboardInterrupt:
        pass
    print(GREEN("GUI 已退出，返回菜单。"))


def _interactive(service: AcceptanceService, args: argparse.Namespace) -> int:
    progress = _progress_printer()
    while True:
        _print_menu(service)
        try:
            choice = input("请选择: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not choice:
            continue
        normalized = choice.upper()
        if normalized == "Q":
            return 0
        looks_like_selection = bool(re.search(r"\d", choice)) or any(
            token in choice.lower() for token in ITEM_KEYS
        )
        if normalized == "A" or looks_like_selection:
            if normalized == "A":
                keys = service.config.run_items()
            else:
                try:
                    keys = _parse_selection(choice)
                except ValueError as exc:
                    print(RED(str(exc)))
                    continue
            try:
                if len(keys) == 1:
                    service.run_item(keys[0], progress=progress)
                    report = service.current_report()
                else:
                    report = service.run_all(keys=keys, progress=progress)
                if report is not None:
                    _print_report_summary(report, service.report_path())
            except KeyboardInterrupt:
                service.cancel()
                service.shutdown(timeout=10.0)
                report = service.current_report()
                _print_report_summary(report, service.report_path())
                print(YELLOW("\n已中断当前验收。报告与原始数据已保存到输出目录。"))
            except UCMAcceptError as exc:
                print(RED(f"执行失败：{exc}"))
                if "EvalScope" in str(exc):
                    print(DIM("提示：可先运行 [D] 自检；演示可用 --mock --fast。"))
            except Exception as exc:  # noqa: BLE001
                print(RED(f"执行失败：{exc}"))
            try:
                input(DIM("按回车返回菜单…"))
            except EOFError:
                return 0
        elif normalized == "T":
            current = "、".join(str(service.config.run_items()))
            print(DIM(f"当前范围：{current}"))
            text = _prompt("输入要执行的测试项（如 1,3-5 / perf,sla；回车保持不变）", "")
            if not text:
                continue
            try:
                keys = _parse_selection(text)
            except ValueError as exc:
                print(RED(str(exc)))
                continue
            service.config.set("run.items", keys)
            print(GREEN("验收范围已更新：" + "、".join(ITEM_BY_KEY[key].name for key in keys)))
        elif normalized == "C":
            _config_menu(service)
        elif normalized == "S":
            _service_menu(service)
        elif normalized == "P":
            _assets_menu(service)
        elif normalized == "R":
            _show_latest(service)
        elif normalized == "L":
            _compare_menu(service)
        elif normalized == "E":
            _export_menu(service)
        elif normalized == "D":
            probe = _prompt("探测服务连通性 y/N", "N").lower() == "y"
            _doctor(service.config, argparse.Namespace(mock=service.mode == "mock", probe=probe))
        elif normalized == "G":
            _launch_gui(service, args)
        else:
            print(YELLOW("无效选择，请输入 1-5 / A / T / C / S / P / R / L / E / D / G / Q。"))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        config = _apply_args(config, args)
    except ConfigError as exc:
        print(RED(f"配置错误：{exc}"))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(RED(f"加载配置失败：{exc}"))
        return 1

    if args.save_config:
        try:
            target = config.save(args.save_config)
            print(GREEN(f"配置已保存：{target}"))
            print(DIM(f"下次使用：ucm-accept --config {target}"))
            return 0
        except OSError as exc:
            print(RED(f"保存配置失败：{exc}"))
            return 1

    if args.doctor:
        return _doctor(config, args)
    if args.gui:
        from .webapp import main as web_main

        return web_main(
            config=config,
            mode="mock" if args.mock else "live",
            mock_profile=args.profile,
            mock_delay_ms=0 if args.fast else None,
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
        )

    if not (args.all or args.item or args.items):
        if not sys.stdin.isatty():
            parser.print_help()
            print(RED("\n非交互环境请使用 --all、--items 或 --item，或显式 --gui。"))
            return 2

    service = AcceptanceService(
        config,
        mode="mock" if args.mock else "live",
        mock_profile=args.profile,
        mock_delay_ms=0 if args.fast else None,
    )
    # SIGTERM（终端关闭 / kill）：停止当前任务、终止子进程并落盘报告
    def _graceful(signum: int, _frame: object) -> None:
        service.shutdown(timeout=10.0)
        print(YELLOW("\n收到退出信号，验收已中断，报告与原始数据已保存到输出目录。"))
        raise SystemExit(130)

    for _sig in (signal.SIGTERM,):
        try:
            signal.signal(_sig, _graceful)
        except (ValueError, OSError):  # noqa: BLE001 - 非主线程等场景忽略
            pass

    if args.all or args.item or args.items:
        return _run_noninteractive(service, args)
    return _interactive(service, args)


if __name__ == "__main__":
    raise SystemExit(main())
