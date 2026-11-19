from __future__ import annotations

from ucm_accept.models import (
    ITEM_KEYS,
    AcceptanceReport,
    ItemResult,
    Status,
    human_duration,
    percent,
)


def make_report() -> AcceptanceReport:
    report = AcceptanceReport(
        run_id="r1",
        mode="live",
        endpoint={"base_url": "http://x/v1", "model": "m"},
        started_at="2026-01-01T00:00:00+08:00",
    )
    for key in ITEM_KEYS:
        report.items[key] = ItemResult(key=key, name=key, status=Status.PASSED, summary="ok")
    return report


def test_all_pass():
    report = make_report()
    report.finalize()
    assert report.conclusion == "通过"


def test_missing_is_incomplete():
    report = make_report()
    report.items.pop("agent")
    report.finalize()
    assert report.conclusion == "未完成"


def test_warning_is_conditional():
    report = make_report()
    report.items["sla"].status = Status.WARNING
    report.finalize()
    assert report.conclusion == "有条件通过"


def test_failed_is_fail():
    report = make_report()
    report.items["agent"].status = Status.FAILED
    report.finalize()
    assert report.conclusion == "不通过"


def test_skipped_is_incomplete():
    report = make_report()
    report.items["perf"].status = Status.SKIPPED
    report.finalize()
    assert report.conclusion == "未完成"


def test_roundtrip_json(tmp_path):
    report = make_report()
    report.finalize()
    path = report.save_json(tmp_path / "report.json")
    loaded = AcceptanceReport.load_json(path)
    assert loaded.run_id == report.run_id
    assert loaded.items["perf"].status == Status.PASSED
    assert loaded.conclusion == "通过"


def test_format_helpers():
    assert human_duration(65) == "1 分 05 秒"
    assert human_duration(3661) == "1 小时 01 分"
    assert percent(0.9123) == "91.2%"
    assert percent(None) == "—"
