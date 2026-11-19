from __future__ import annotations

import json
from pathlib import Path

from ucm_accept.cli import main


def test_cli_all_mock(tmp_path: Path, capsys):
    outputs = tmp_path / "outputs"
    code = main(["--mock", "--fast", "--all", "--outputs", str(outputs)])
    assert code == 0
    captured = capsys.readouterr().out
    assert "验收结论：通过" in captured
    report = outputs / "runs"
    reports = list(report.glob("*/report.json"))
    assert reports
    data = json.loads(reports[0].read_text(encoding="utf-8"))
    assert data["conclusion"] == "通过"
    assert len(data["items"]) == 5


def test_cli_single_item_with_scenario(tmp_path: Path, capsys):
    outputs = tmp_path / "outputs"
    code = main(
        [
            "--mock",
            "--fast",
            "--item",
            "multiturn",
            "--scenario",
            "code",
            "--outputs",
            str(outputs),
        ]
    )
    assert code == 0
    assert "多轮对话" in capsys.readouterr().out
    reports = list((outputs / "runs").glob("*/report.json"))
    data = json.loads(reports[0].read_text(encoding="utf-8"))
    assert data["items"]["multiturn"]["detail"]["scenario"] == "code"
    assert data["conclusion"] == "未完成"


def test_cli_doctor_mock(tmp_path: Path, capsys):
    code = main(["--mock", "--doctor"])
    assert code == 0
    assert "自检" in capsys.readouterr().out


def test_cli_report_export(tmp_path: Path, capsys):
    outputs = tmp_path / "outputs"
    target = tmp_path / "deliver" / "report.html"
    code = main(
        [
            "--mock",
            "--fast",
            "--item",
            "perf",
            "--outputs",
            str(outputs),
            "--report",
            str(target),
        ]
    )
    assert code == 0
    assert target.exists()
    assert "验收结论" in target.read_text(encoding="utf-8")


def test_cli_no_tty_requires_mode(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    code = main([])
    assert code == 2
