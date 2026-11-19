from __future__ import annotations

from ucm_accept.config import Config
from ucm_accept.errors import UCMAcceptError
from ucm_accept.service import AcceptanceService


def test_service_probe_and_run(config: Config):
    service = AcceptanceService(config, mode="mock", mock_delay_ms=0)
    probe = service.check_connection()
    assert probe.connected
    item = service.run_item("perf")
    assert item.status.value == "passed"
    assert service.current_report() is not None
    assert service.report_path() is not None


def test_service_accumulates_items_in_one_report(config: Config):
    service = AcceptanceService(config, mode="mock", mock_delay_ms=0)
    service.run_item("perf")
    report = service.current_report()
    run_id = report.run_id
    service.run_item("multiturn")
    assert service.current_report().run_id == run_id
    assert len(service.current_report().items) == 2


def test_endpoint_change_starts_new_report(config: Config):
    service = AcceptanceService(config, mode="mock", mock_delay_ms=0)
    service.run_item("perf")
    first = service.current_report().run_id
    service.update_endpoint(base_url="http://127.0.0.1:9999/v1", model="other")
    item = service.run_item("perf")
    second = service.current_report().run_id
    assert first != second
    assert item.detail["config"]["source"] == "mock"


def test_invalid_override_rejected(config: Config):
    service = AcceptanceService(config, mode="mock", mock_delay_ms=0)
    try:
        service.apply_overrides({"perf": {"parallel": [0]}})
    except Exception as exc:  # noqa: BLE001
        assert "并发" in str(exc)
    else:
        raise AssertionError("应当拒绝非法并发")


def test_service_export_pdf_without_report_errors(config: Config):
    service = AcceptanceService(config, mode="mock", mock_delay_ms=0)
    try:
        service.export_pdf()
    except UCMAcceptError:
        pass
    else:
        raise AssertionError("没有报告时应报错")


def test_reset_clears_session(config: Config):
    service = AcceptanceService(config, mode="mock", mock_delay_ms=0)
    service.run_item("perf")
    service.reset()
    assert service.current_report() is None
