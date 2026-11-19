from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ucm_accept.errors import UCMAcceptError

pytestmark = pytest.mark.gui


def test_advanced_overrides_validation():
    from ucm_accept.gui import _advanced_overrides

    overrides = _advanced_overrides(
        "20, 40", 200, 65536, 256, 0.2, "/models/tokenizer",
        "auto_tune", 200, 10, 50, 2, 0, 4, 12, 4, 600,
    )
    assert overrides["perf"]["parallel"] == [20, 40]
    assert overrides["sla"]["target"]["ttft_p90_ms"] == 10000
    assert overrides["defaults"]["hit_rate"] == 0.2

    with pytest.raises(UCMAcceptError):
        _advanced_overrides(
            "20, bad", 200, 65536, 256, 0.2, "", "verify", 200, 10, 50,
            2, 0, 4, 12, 4, 600,
        )


def test_build_demo_subprocess(tmp_path: Path):
    """Gradio keeps internal threads alive; verify construction in a child process."""
    pytest.importorskip("gradio")
    outputs = str(tmp_path / "outputs")
    code = f"""
import os
from ucm_accept.config import Config
from ucm_accept.service import AcceptanceService
from ucm_accept.gui import build_demo
cfg = Config.load(overrides={{"app": {{"report_dir": {outputs!r}}}}})
cfg.set("app.report_dir", {outputs!r})
service = AcceptanceService(cfg, mode="mock", mock_delay_ms=0)
demo = build_demo(service)
print("blocks", len(demo.blocks), flush=True)
os._exit(0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=45,
        env={**os.environ, "GRADIO_ANALYTICS_ENABLED": "False"},
    )
    assert result.returncode == 0, result.stderr
    assert "blocks" in result.stdout
