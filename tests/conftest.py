from __future__ import annotations

from pathlib import Path

import pytest

from ucm_accept.config import Config


@pytest.fixture
def config(tmp_path: Path) -> Config:
    cfg = Config.load(
        overrides={
            "app": {
                "report_dir": str(tmp_path / "outputs"),
                "mock": {"delay_ms": 0, "profile": "nominal"},
            }
        }
    )
    return cfg


@pytest.fixture
def fake_evalscope(tmp_path: Path) -> Path:
    script = tmp_path / "fake_evalscope.py"
    script.write_text(
        '''#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
root = Path.cwd()
out = None
for flag in ("--outputs-dir", "--work-dir"):
    if flag in args:
        out = Path(args[args.index(flag) + 1])
if out is None:
    out = root / "outputs"
out.mkdir(parents=True, exist_ok=True)

if args and args[0] == "perf":
    if "--sla-auto-tune" in args:
        (out / "sla_summary.json").write_text(json.dumps({
            "parallel_160": {
                "metrics": {"Concurrency": 160, "Total Requests": 40, "Success Requests": 40,
                            "Avg Latency (s)": 12.0, "TTFT (ms)": 7000, "TPOT (ms)": 38,
                            "Output Throughput (tok/s)": 1900, "Req Throughput (req/s)": 8},
                "percentiles": {"Percentiles": ["90%", "99%"], "TTFT (ms)": [7000, 9000], "TPOT (ms)": [38, 42]}
            },
            "parallel_200": {
                "metrics": {"Concurrency": 200, "Total Requests": 40, "Success Requests": 40,
                            "Avg Latency (s)": 18.0, "TTFT (ms)": 8500, "TPOT (ms)": 45,
                            "Output Throughput (tok/s)": 2300, "Req Throughput (req/s)": 9},
                "percentiles": {"Percentiles": ["90%", "99%"], "TTFT (ms)": [8500, 12000], "TPOT (ms)": [45, 60]}
            }
        }), encoding="utf-8")
        print("SLA auto tune best parallel 160 PASSED")
        sys.exit(0)
    if "--scenario" in args:
        (out / "agentx_summary.json").write_text(json.dumps({
            "successful_requests": 196, "total_requests": 200,
            "sessions": 4, "requests": 200, "submission_valid": True
        }), encoding="utf-8")
        print("AgentX summary")
        sys.exit(0)
    if "--dataset" in args and args[args.index("--dataset") + 1] == "custom_multi_turn":
        print("Benchmarking summary:")
        print("│ Metric | Value │")
        print("│ Concurrency | 4 │")
        print("│ Total / Success / Failed | 12 / 12 / 0 │")
        print("│ Avg Latency (s) | 1.20 │")
        print("│ TTFT (ms) | 400 │")
        print("│ TPOT (ms) | 20 │")
        print("│ Output Throughput (tok/s) | 500 │")
        print("")
        print("Per-Request Metrics")
        print("│ Metric | avg | p90 | p99 │")
        print("│ Turns/Req | 3.2 | - | - │")
        print("│ Cache Hit (%) | 58.0% | - | - │")
        print("| Metric | 90% | 99% |")
        print("| TTFT (ms) | 650 | 900 |")
        print("| TPOT (ms) | 17 | 19 |")
        print("| Latency (s) | 17 | 20 |")
        sys.exit(0)
    print("Benchmarking summary:")
    print("┌───────────────────────────┬───────────────┐")
    print("│ Metric                    │ Value         │")
    print("├───────────────────────────┼───────────────┤")
    print("│ Concurrency               │ 200           │")
    print("│ Total / Success / Failed  │ 200 / 200 / 0 │")
    print("│ Avg Latency (s)           │ 18.78         │")
    print("│ TTFT (ms)                 │ 717.63        │")
    print("│ TPOT (ms)                 │ 17.66         │")
    print("│ Output Throughput (tok/s) │ 10692.45      │")
    print("│ Req Throughput (req/s)    │ 10.44         │")
    print("│ Avg Input Tokens          │ 1024.00       │")
    print("│ Avg Output Tokens         │ 1024.00       │")
    print("└───────────────────────────┴───────────────┘")
    print("Percentile results:")
    print("┌────────────────┬─────────┬─────────┐")
    print("│ Metric         │ 90%     │ 99%     │")
    print("├────────────────┼─────────┼─────────┤")
    print("│ TTFT (ms)      │ 8500    │ 12000   │")
    print("│ TPOT (ms)      │ 45      │ 60      │")
    print("│ Latency (s)    │ 17      │ 20      │")
    print("└────────────────┴─────────┴─────────┘")
    sys.exit(0)

if args and args[0] == "eval":
    datasets = "gsm8k"
    if "--datasets" in args:
        datasets = args[args.index("--datasets") + 1]
    payload = {datasets: {"score": 0.864, "limit": 100}}
    (out / "results.json").write_text(json.dumps(payload), encoding="utf-8")
    print(f"{datasets} accuracy: 0.864")
    sys.exit(0)

print("unknown command", file=sys.stderr)
sys.exit(2)
''',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script
