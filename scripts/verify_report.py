#!/usr/bin/env python3
"""CI / 构建虚跑校验：检查报告结构、命令追溯与离线自包含性。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REQUIRED_ITEMS = {"perf", "multiturn", "sla", "accuracy", "agent"}
EXTERNAL = re.compile(r"(?:src|href)=[\"']https?://", re.IGNORECASE)


def fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def main() -> int:
    if len(sys.argv) != 2:
        print("用法：verify_report.py <report.json>", file=sys.stderr)
        return 2
    report_path = Path(sys.argv[1])
    if not report_path.exists():
        return fail(f"报告不存在：{report_path}")
    data = json.loads(report_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        return fail("schema_version 不是 1")
    items = data.get("items") or {}
    if set(items) != REQUIRED_ITEMS:
        return fail(f"测试项不完整：{sorted(items)}")
    if data.get("conclusion") not in {"通过", "有条件通过", "不通过", "未完成"}:
        return fail(f"结论非法：{data.get('conclusion')}")
    for key, item in items.items():
        detail = item.get("detail") or {}
        commands = detail.get("commands") or []
        if not detail.get("command") and not commands:
            return fail(f"{key} 缺少可复现命令")
        if item.get("status") in {"failed", "skipped"} and not item.get("summary"):
            return fail(f"{key} 失败但缺少摘要")
    run_dir = report_path.parent
    html_path = run_dir / "report.html"
    if not html_path.exists() or html_path.stat().st_size < 10_000:
        return fail("report.html 缺失或过小")
    html = html_path.read_text(encoding="utf-8")
    if EXTERNAL.search(html):
        return fail("report.html 含外部 http(s) 资源，不满足离线要求")
    for required in ("验收概览", "基础性能", "SLA 自动调优", "精度测试", "Agent 场景", "原始数据与复核"):
        if required not in html:
            return fail(f"report.html 缺少章节：{required}")
    print(
        f"[OK] {data['conclusion']} · {len(items)} 项 · "
        f"{html_path.stat().st_size / 1024:.1f} KiB · {run_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
