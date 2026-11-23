from __future__ import annotations

import json
from pathlib import Path

from ucm_accept.engine.parser import (
    extract_score,
    parse_accuracy_output,
    parse_agent_output,
    parse_multiturn_metrics,
    parse_perf_tables,
    parse_sla_json,
    parse_sla_output,
    parse_sla_selection,
)

PERF_TEXT = """
Benchmarking summary:
┌───────────────────────────┬───────────────┐
│ Metric                    │ Value         │
├───────────────────────────┼───────────────┤
│ Concurrency               │ 200           │
│ Total / Success / Failed  │ 200 / 199 / 1 │
│ Avg Latency (s)           │ 18.78         │
│ TTFT (ms)                 │ 717.63        │
│ TPOT (ms)                 │ 17.66         │
│ Output Throughput (tok/s) │ 10692.45      │
│ Req Throughput (req/s)    │ 10.44         │
│ Avg Input Tokens          │ 65536.00      │
│ Avg Output Tokens         │ 256.00        │
└───────────────────────────┴───────────────┘

Percentile results:
┌────────────────┬─────────┬─────────┬─────────┐
│ Metric         │ 50%     │ 90%     │ 99%     │
├────────────────┼─────────┼─────────┼─────────┤
│ TTFT (ms)      │ 600     │ 8500    │ 12000   │
│ TPOT (ms)      │ 17      │ 45      │ 60      │
│ Latency (s)    │ 15      │ 17      │ 20      │
└────────────────┴─────────┴─────────┴─────────┘
"""


def test_parse_perf_tables():
    points = parse_perf_tables(PERF_TEXT)
    assert len(points) == 1
    point = points[0]
    assert point.concurrency == 200
    assert point.requests == 200
    assert point.success_requests == 199
    assert point.ttft_p90_ms == 8500
    assert point.ttft_p99_ms == 12000
    assert point.tpot_p90_ms == 45
    assert point.tpot_p99_ms == 60
    assert point.latency_p90_s == 17
    assert point.throughput_tok_s == 10692.45
    assert abs(point.success_rate - 0.995) < 1e-9


def test_accuracy_extract_nested():
    data = {"results": {"gsm8k": {"accuracy": 86.4, "num": 100}}}
    assert extract_score(data, "gsm8k") == 0.864


def test_accuracy_extract_direct(tmp_path: Path):
    work = tmp_path / "run"
    work.mkdir()
    (work / "results.json").write_text(
        json.dumps({"gpqa_diamond": {"score": 0.5123}}), encoding="utf-8"
    )
    score, source = parse_accuracy_output(work, "gpqa_diamond")
    assert score == 0.5123
    assert "results.json" in source


def test_accuracy_extract_percent(tmp_path: Path):
    work = tmp_path / "run"
    work.mkdir()
    (work / "report.json").write_text(
        json.dumps({"datasets": {"bfcl_v3": {"score": 78.2}}}), encoding="utf-8"
    )
    score, _ = parse_accuracy_output(work, "bfcl_v3")
    assert score == 0.782


def test_accuracy_stdout_fallback():
    score, source = parse_accuracy_output("/nonexistent-path", "gsm8k", "gsm8k accuracy: 0.85")
    assert score == 0.85
    assert source == "stdout"


def test_parse_sla_selection():
    result = parse_sla_selection("Best parallel = 160, PASSED all constraints")
    assert result["recommended_concurrency"] == 160


def test_parse_sla_json(tmp_path: Path):
    path = tmp_path / "sla_summary.json"
    path.write_text(
        json.dumps(
            {
                "parallel_200": {
                    "metrics": {
                        "Concurrency": 200,
                        "Total Requests": 40,
                        "Success Requests": 40,
                        "TTFT (ms)": 8500,
                        "TPOT (ms)": 45,
                    },
                    "percentiles": {"Percentiles": ["90%", "99%"]},
                }
            }
        ),
        encoding="utf-8",
    )
    points = parse_sla_json(path)
    assert len(points) == 1
    assert points[0].concurrency == 200
    assert points[0].ttft_avg_ms == 8500


def test_parse_sla_output_merges_stdout_and_json(tmp_path: Path):
    path = tmp_path / "sla_summary.json"
    path.write_text(
        json.dumps({"parallel_160": {"metrics": {"Concurrency": 160, "TTFT (ms)": 7000, "TPOT (ms)": 38}}}),
        encoding="utf-8",
    )
    points = parse_sla_output(tmp_path, "")
    assert any(point.concurrency == 160 for point in points)


def test_parse_multiturn_metrics():
    text = """
Per-Request Metrics
┌────────────────┬────────┬─────────┬─────────┐
│ Metric         │ avg    │ p90     │ p99     │
├────────────────┼────────┼─────────┼─────────┤
│ Turns/Req      │ 3.20   │ -       │ -       │
│ Cache Hit (%)  │ 58.0%  │ -       │ -       │
└────────────────┴────────┴─────────┴─────────┘
"""
    metrics = parse_multiturn_metrics(text)
    assert metrics["turns_per_request"] == 3.2
    assert abs(metrics["cache_hit_rate"] - 0.58) < 1e-9


def test_parse_agent_output(tmp_path: Path):
    (tmp_path / "agentx_summary.json").write_text(
        json.dumps(
            {
                "successful_requests": 196,
                "total_requests": 200,
                "sessions": 4,
                "requests": 200,
                "tool_success_rate": 0.91,
                "submission_valid": True,
            }
        ),
        encoding="utf-8",
    )
    metrics = parse_agent_output(tmp_path)
    assert abs(metrics["completion_rate"] - 0.98) < 1e-9
    assert metrics["sessions"] == 4
    assert metrics["avg_steps"] == 50


def test_parse_real_benchmark_files(tmp_path: Path):
    run_dir = tmp_path / "parallel_200"
    run_dir.mkdir()
    (run_dir / "benchmark_summary.json").write_text(
        json.dumps(
            {
                "Concurrency": 200,
                "Total Requests": 200,
                "Success Requests": 200,
                "Avg TTFT (ms)": 8500,
                "Avg TPOT (ms)": 45,
                "Avg Latency (s)": 17,
                "Output Throughput (tok/s)": 2300,
                "Req Throughput (req/s)": 10,
                "Avg Input Tokens": 65536,
                "Avg Output Tokens": 256,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "benchmark_percentile.json").write_text(
        json.dumps(
            [
                {"Percentiles": "50%", "TTFT (ms)": 6000, "TPOT (ms)": 30, "Latency (s)": 12},
                {"Percentiles": "90%", "TTFT (ms)": 8500, "TPOT (ms)": 45, "Latency (s)": 17},
                {"Percentiles": "99%", "TTFT (ms)": 12000, "TPOT (ms)": 60, "Latency (s)": 20},
            ]
        ),
        encoding="utf-8",
    )
    from ucm_accept.engine.parser import parse_perf_output_dir

    points = parse_perf_output_dir(tmp_path)
    assert len(points) == 1
    assert points[0].ttft_p90_ms == 8500
    assert points[0].ttft_p99_ms == 12000
    assert points[0].tpot_p99_ms == 60


def test_parse_sla_selection_from_table():
    text = """
SLA Auto-tune Summary:
+----------------+----------+---------+--------+
| Criteria       | Selected | Status  | Reason |
+================+==========+=========+========+
| p90_ttft <10s  | 160      | PASS    | ok     |
+----------------+----------+---------+--------+
"""
    result = parse_sla_selection(text)
    assert result["recommended_concurrency"] == 160
    assert result["target_met"] is True


def test_parse_agentx_real_metric_blocks(tmp_path: Path):
    (tmp_path / "agentx_summary.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "concurrency": 4,
                "submission_valid": True,
                "metrics": {
                    "request_count": {"unit": "requests", "avg": 200.0},
                    "error_request_count": {"unit": "requests", "avg": 4.0},
                    "output_token_throughput": {"unit": "tok/s", "avg": 1200.0},
                },
            }
        ),
        encoding="utf-8",
    )
    metrics = parse_agent_output(tmp_path)
    assert metrics["completion_rate"] == 0.98
    assert metrics["sessions"] == 4
    assert metrics["requests"] == 200
    assert metrics["avg_steps"] == 50


def test_parse_sla_json_with_percentile_arrays(tmp_path: Path):
    path = tmp_path / "sla_summary.json"
    path.write_text(
        json.dumps(
            {
                "parallel_200": {
                    "metrics": {
                        "Concurrency": 200,
                        "Total Requests": 40,
                        "Success Requests": 40,
                        "Avg TTFT (ms)": 7100,
                        "Avg TPOT (ms)": 40,
                    },
                    "percentiles": {
                        "Percentiles": ["50%", "90%", "99%"],
                        "TTFT (ms)": [5000, 8500, 12000],
                        "TPOT (ms)": [30, 45, 60],
                        "Latency (s)": [12, 17, 20],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    points = parse_sla_json(path)
    assert len(points) == 1
    assert points[0].ttft_p90_ms == 8500
    assert points[0].ttft_p99_ms == 12000
    assert points[0].tpot_p90_ms == 45


def test_extract_score_evalscope_15_metrics_list():
    """EvalScope 1.15 报告：分数位于 metrics 数组内。"""
    from ucm_accept.engine.parser import extract_score

    report = {
        "schema_version": 2,
        "name": "qwen2.5-0.5b-instruct@gsm8k",
        "dataset_name": "gsm8k",
        "metrics": [
            {"num_correct": 1, "score": 0.2, "macro_score": 0.2,
             "categories": [{"score": 0.2, "subsets": [{"score": 0.2}]}]}
        ],
    }
    assert extract_score(report, "gsm8k") == 0.2


def test_parse_accuracy_output_rich_table_row():
    """EvalScope 1.15 汇总表格行（含全角框线字符）兜底解析。"""
    from ucm_accept.engine.parser import parse_accuracy_output

    stdout = (
        "│ Model                 │ Dataset │ Metric     │ Subset │ Num │ Correct │ Score │\n"
        "│ qwen2.5-0.5b-instruct │ GSM8K   │ Accuracy ↑ │ main   │   5 │       1 │ 20%   │\n"
    )
    score, source = parse_accuracy_output("/nonexistent", "gsm8k", stdout)
    assert score == 0.2
    assert source == "stdout"


def test_builtin_multiturn_presets_are_openai_format():
    """内置多轮预设必须为 OpenAI 消息数组（evalscope 1.15 custom_multi_turn 要求）。"""
    import json
    from pathlib import Path

    preset_dir = Path(__file__).resolve().parents[1] / "ucm_accept" / "resources" / "datasets" / "multiturn"
    for path in sorted(preset_dir.glob("*.jsonl")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            data = json.loads(line)
            assert isinstance(data, list), f"{path.name}:{line_no} 不是消息数组"
            assert data, f"{path.name}:{line_no} 会话为空"
            roles = [m["role"] for m in data]
            assert "user" in roles and "assistant" in roles, f"{path.name}:{line_no} 缺少 user/assistant"
