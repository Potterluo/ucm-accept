from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from . import __version__
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
            "  ucm-accept --all                   # 无交互跑完五项并生成报告\n"
            "  ucm-accept --item perf             # 只跑基础性能\n"
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
    parser.add_argument("--item", choices=list(ITEM_KEYS), help="只执行指定测试项")
    parser.add_argument("--scenario", choices=["dialogue", "code", "office"], help="多轮对话场景预设")
    parser.add_argument("--all", action="store_true", help="顺序执行全部五项测试")
    parser.add_argument("--sla-mode", choices=["verify", "auto_tune"], help="覆盖 SLA 模式")
    parser.add_argument("--report", help="将本次 HTML 报告另存到指定路径")
    parser.add_argument("--pdf", action="store_true", help="同时导出 PDF（需 weasyprint 或 chromium）")
    parser.add_argument("--mock", action="store_true", help="使用模拟引擎（演示 / 虚跑，报告会标注）")
    parser.add_argument("--fast", action="store_true", help="模拟模式零延迟")
    parser.add_argument("--profile", choices=["nominal", "degraded"], default="nominal", help="模拟画像")
    parser.add_argument("--gui", action="store_true", help="启动 Gradio GUI")
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
        if args.all:
            report = service.run_all(progress=progress)
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
        print(YELLOW("\n已中断验收。原始数据仍保留在输出目录。"))
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


def _print_menu(service: AcceptanceService, args: argparse.Namespace) -> None:
    mode = "模拟演示（不产生真实请求）" if service.mode == "mock" else "EvalScope 实机"
    print()
    print(BOLD("=" * 52))
    print(BOLD(f" UCM 推理加速验收工具 (CLI)  v{__version__}"))
    print(f" 执行引擎: {CYAN(mode)}")
    print(BOLD("=" * 52))
    print(f"服务地址: {service.config.get('endpoint.base_url')}")
    print(f"模型:     {service.config.get('endpoint.model')}")
    print(f"报告目录: {service.outputs_root}")
    print(DIM("-" * 52))
    for key in ITEM_KEYS:
        meta = ITEM_BY_KEY[key]
        print(f" [{meta.order}] {meta.name}    {DIM(meta.eta)}")
    print(" [A] 执行全部验收测试")
    print(" [R] 查看最近报告")
    print(" [S] 修改服务地址 / 模型")
    print(" [Q] 退出")
    print(DIM("-" * 52))


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


def _choose_scenario(default: str = "dialogue") -> str:
    mapping = {"1": "dialogue", "2": "code", "3": "office"}
    print("   [1] 对话   [2] 代码   [3] 办公")
    choice = _prompt("请选择场景", default)
    return mapping.get(choice, choice if choice in {"dialogue", "code", "office"} else "dialogue")


def _interactive(service: AcceptanceService, args: argparse.Namespace) -> int:
    progress = _progress_printer()
    while True:
        _print_menu(service, args)
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
        if normalized in {"A", "1", "2", "3", "4", "5"}:
            key = None if normalized == "A" else ITEM_KEYS[int(normalized) - 1]
            scenario = None
            if key == "multiturn":
                scenario = _choose_scenario(str(service.config.get("multiturn.scenario", "dialogue")))
            try:
                if key is None:
                    report = service.run_all(progress=progress)
                else:
                    service.run_item(key, scenario=scenario, progress=progress)
                    report = service.current_report()
                if report is not None:
                    _print_report_summary(report, service.report_path())
            except KeyboardInterrupt:
                service.cancel()
                print(YELLOW("\n已中断当前验收。"))
            except UCMAcceptError as exc:
                print(RED(f"执行失败：{exc}"))
                if "EvalScope" in str(exc):
                    print(DIM("提示：可先运行 --doctor；演示可用 --mock --fast。"))
            except Exception as exc:  # noqa: BLE001
                print(RED(f"执行失败：{exc}"))
            try:
                input(DIM("按回车返回菜单…"))
            except EOFError:
                return 0
        elif normalized == "R":
            _show_latest(service)
        elif normalized == "S":
            base_url = _prompt("服务地址", str(service.config.get("endpoint.base_url")))
            model = _prompt("模型名称", str(service.config.get("endpoint.model")))
            try:
                service.update_endpoint(base_url=base_url, model=model)
                print(GREEN("服务配置已更新；下一项测试将开启新报告。"))
            except UCMAcceptError as exc:
                print(RED(str(exc)))
        else:
            print(YELLOW("无效选择，请输入 1-5 / A / R / S / Q。"))


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

    if args.doctor:
        return _doctor(config, args)
    if args.gui:
        from .gui import main as gui_main

        return gui_main(
            config=config,
            mode="mock" if args.mock else "live",
            mock_profile=args.profile,
            mock_delay_ms=0 if args.fast else None,
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
        )

    if not (args.all or args.item):
        if not sys.stdin.isatty():
            parser.print_help()
            print(RED("\n非交互环境请使用 --all 或 --item，或显式 --gui。"))
            return 2

    service = AcceptanceService(
        config,
        mode="mock" if args.mock else "live",
        mock_profile=args.profile,
        mock_delay_ms=0 if args.fast else None,
    )
    if args.all or args.item:
        return _run_noninteractive(service, args)
    return _interactive(service, args)


if __name__ == "__main__":
    raise SystemExit(main())
