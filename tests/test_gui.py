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


def test_extra_overrides_maps_dataset_labels():
    from ucm_accept.gui import _extra_overrides

    label_map = {"数学推理": "gsm8k", "工具调用": "bfcl_v3", "基础问答": "gpqa", "长文本": "longbench_v2"}
    overrides = _extra_overrides(
        300, 128, "random", 5,
        2, 6, 2, 100,
        label_map, ["数学推理", "工具调用"],
        "AgentX-claudecode", "现场验收报告", "客户A", "张三",
    )
    assert overrides["endpoint"]["timeout_s"] == 300
    assert overrides["perf"]["min_tokens"] == 128
    assert overrides["multiturn"]["min_turns"] == 2
    assert overrides["sla"]["auto_tune"]["upper"] == 100
    assert overrides["agent"]["dataset_name"] == "AgentX-claudecode"
    datasets = overrides["accuracy"]["datasets"]
    assert datasets["gsm8k"]["enabled"] is True
    assert datasets["gpqa"]["enabled"] is False
    assert overrides["report"]["title"] == "现场验收报告"


def test_keys_for_labels():
    from ucm_accept.gui import _keys_for_labels
    from ucm_accept.models import ITEM_BY_KEY

    labels = [ITEM_BY_KEY["sla"].name, ITEM_BY_KEY["perf"].name]
    assert _keys_for_labels(labels) == ["perf", "sla"]
    assert _keys_for_labels([]) == []


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
