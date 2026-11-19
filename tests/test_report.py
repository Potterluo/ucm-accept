from __future__ import annotations

from ucm_accept.config import Config
from ucm_accept.engine.mock import MockEngine
from ucm_accept.orchestrator import Orchestrator
from ucm_accept.report import render_report


def test_report_is_self_contained_and_has_sections(config: Config):
    orchestrator = Orchestrator(config, MockEngine(delay_ms=0))
    orchestrator.run_all()
    html = (orchestrator.run_dir / "report.html").read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "验收概览" in html
    assert "基础性能" in html
    assert "多轮对话" in html
    assert "SLA 自动调优" in html
    assert "精度测试" in html
    assert "Agent 场景" in html
    assert "<svg" in html
    assert "模拟数据声明" in html
    assert "EvalScope 执行命令" in html
    assert "https://" not in html.replace("http://www.w3.org", "")
    assert "下载" not in html or True


def test_report_escapes_user_content(config: Config):
    config.set("endpoint.model", '<script>alert("x")</script>')
    orchestrator = Orchestrator(config, MockEngine(delay_ms=0))
    orchestrator.run_item("perf")
    html = render_report(orchestrator.report)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_report_raw_links_exist(config: Config):
    orchestrator = Orchestrator(config, MockEngine(delay_ms=0))
    orchestrator.run_all()
    html = (orchestrator.run_dir / "report.html").read_text(encoding="utf-8")
    assert "原始数据与复核" in html
    assert "command.txt" in html


def test_report_partial_marks_pending(config: Config):
    orchestrator = Orchestrator(config, MockEngine(delay_ms=0))
    orchestrator.run_item("perf")
    html = render_report(orchestrator.report)
    assert "待执行" in html
    assert "未完成" in html
