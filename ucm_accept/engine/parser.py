from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..models import PerfPoint
from ..utils import coerce_float, coerce_int

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_SCORE_KEYS = {
    "score",
    "scores",
    "accuracy",
    "acc",
    "acc_norm",
    "averageaccuracy",
    "average_accuracy",
    "avg_accuracy",
    "mean_accuracy",
    "exact_match",
    "pass@1",
    "pass_at_1",
    "f1",
    "win_rate",
    "overall",
    "primary_score",
}
_METRIC_SUFFIXES = ("%")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "")


def normalize_label(text: str) -> str:
    return re.sub(r"[\s_\-]+", " ", str(text).strip().lower())


def _cells(line: str) -> list[str]:
    line = line.strip()
    if not line:
        return []
    if line.startswith("│") or line.startswith("|"):
        parts = re.split(r"[│|]", line)
        if parts and not parts[0].strip():
            parts = parts[1:]
        if parts and not parts[-1].strip():
            parts = parts[:-1]
        return [part.strip() for part in parts]
    return []


def parse_rich_tables(text: str) -> list[list[list[str]]]:
    """解析 rich / tabulate 风格的控制台表格（Unicode 或 ASCII 边框）。"""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for raw_line in strip_ansi(text).splitlines():
        clean = raw_line.strip()
        if re.fullmatch(r"\+[-=+:]+\+", clean):
            # simple_grid / markdown 分隔线，不结束当前表格
            continue
        if clean and re.fullmatch(r"[┌┬┐├┼┤└┴┘─━═╒╕╘╛╞╡╪╪]+", clean):
            # rich Unicode 边框，不结束当前表格
            continue
        cells = _cells(raw_line)
        if cells:
            if all(set(cell) <= set("-: ") for cell in cells if cell) and any(cell for cell in cells):
                continue
            current.append(cells)
        else:
            if current:
                tables.append(current)
                current = []
    if current:
        tables.append(current)
    return tables


def _table_to_dicts(table: list[list[str]]) -> list[dict[str, str]]:
    if len(table) < 2:
        return []
    header = table[0]
    rows = []
    for row in table[1:]:
        if not any(cell for cell in row):
            continue
        if all(set(cell) <= set("─- ") for cell in row):
            continue
        values = {}
        for index, name in enumerate(header):
            values[name] = row[index] if index < len(row) else ""
        rows.append(values)
    return rows


def _find_key(header: Iterable[str], *needles: str) -> str | None:
    for name in header:
        normalized = normalize_label(name)
        if any(needle in normalized for needle in needles):
            return name
    return None


def _percentile_value(headers: list[str], row: list[str], percentile: int) -> float | None:
    for index, name in enumerate(headers):
        match = re.search(r"(\d+)\s*%", name)
        if match and int(match.group(1)) == percentile and index < len(row):
            return coerce_float(row[index])
    return None


def parse_perf_tables(text: str) -> list[PerfPoint]:
    """从 EvalScope perf 控制台输出中提取每个并发点的核心指标。"""
    points: list[PerfPoint] = []
    current: PerfPoint | None = None
    for table in parse_rich_tables(text):
        if not table:
            continue
        headers = table[0]
        normalized = [normalize_label(header) for header in headers]
        is_summary = "metric" in normalized and "value" in normalized
        is_percentile = "metric" in normalized and any("%" in header for header in headers)
        if is_summary:
            pairs: dict[str, str] = {}
            for row in table[1:]:
                if len(row) >= 2:
                    pairs[normalize_label(row[0])] = row[1]
            if not any("concurrency" in key for key in pairs):
                continue
            concurrency = coerce_int(_lookup(pairs, "concurrency")) or 0
            total = success = 0
            total_success = _lookup(pairs, "total / success / failed", "total/success/failed")
            if total_success:
                numbers = re.findall(r"\d+", total_success)
                if len(numbers) >= 2:
                    total, success = int(numbers[0]), int(numbers[1])
            current = PerfPoint(
                concurrency=concurrency,
                requests=total,
                success_requests=success if total else total,
                throughput_tok_s=coerce_float(_lookup(pairs, "output throughput", "throughput (tok")) or 0.0,
                rps=coerce_float(_lookup(pairs, "req throughput", "request throughput")) or 0.0,
                ttft_avg_ms=coerce_float(_lookup(pairs, "ttft")) or 0.0,
                tpot_avg_ms=coerce_float(_lookup(pairs, "tpot")) or 0.0,
                latency_avg_s=coerce_float(_lookup(pairs, "avg latency")) or 0.0,
                input_tokens=coerce_float(_lookup(pairs, "avg input tokens")) or 0.0,
                output_tokens=coerce_float(_lookup(pairs, "avg output tokens")) or 0.0,
            )
            points.append(current)
        elif is_percentile and current is not None:
            for row in table[1:]:
                if not row:
                    continue
                label = normalize_label(row[0])
                if "ttft" in label:
                    current.ttft_p90_ms = _percentile_value(headers, row, 90) or current.ttft_p90_ms
                    current.ttft_p99_ms = _percentile_value(headers, row, 99) or current.ttft_p99_ms
                elif "tpot" in label:
                    current.tpot_p90_ms = _percentile_value(headers, row, 90) or current.tpot_p90_ms
                    current.tpot_p99_ms = _percentile_value(headers, row, 99) or current.tpot_p99_ms
                elif "latency" in label:
                    current.latency_p90_s = _percentile_value(headers, row, 90) or current.latency_p90_s
                    current.latency_p99_s = _percentile_value(headers, row, 99) or current.latency_p99_s
            if not current.ttft_p90_ms:
                current.ttft_p90_ms = current.ttft_avg_ms
            if not current.tpot_p90_ms:
                current.tpot_p90_ms = current.tpot_avg_ms
            if not current.ttft_p99_ms:
                current.ttft_p99_ms = current.ttft_p90_ms
            if not current.tpot_p99_ms:
                current.tpot_p99_ms = current.tpot_p90_ms
    return [point for point in points if point.concurrency > 0]


def _lookup(pairs: dict[str, str], *needles: str) -> str:
    for key, value in pairs.items():
        if any(needle in key for needle in needles):
            return value
    return ""


def parse_perf_summary_file(path: str | Path) -> list[PerfPoint]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return parse_perf_tables(text)


def _extract_metrics_from_dict(data: dict[str, Any]) -> PerfPoint | None:
    """兼容 EvalScope 某些版本写出的 per-run JSON。"""
    flat: dict[str, Any] = {}

    def walk(node: Any, prefix: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{prefix} {key}".strip())
        elif isinstance(node, (int, float, str)):
            flat[normalize_label(prefix)] = node

    walk(data)
    concurrency = None
    for key, value in flat.items():
        if "concurrency" in key or key.endswith(" parallel"):
            concurrency = coerce_int(value)
            if concurrency:
                break
    if not concurrency:
        return None

    def first(*needles: str) -> float | None:
        for key, value in flat.items():
            if all(needle in key for needle in needles):
                number = coerce_float(value)
                if number is not None:
                    return number
        return None

    point = PerfPoint(
        concurrency=concurrency,
        requests=coerce_int(first("total requests") or 0) or 0,
        success_requests=coerce_int(first("success requests") or 0) or 0,
        throughput_tok_s=first("output throughput") or first("throughput tok") or 0.0,
        rps=first("req throughput") or first("request throughput") or 0.0,
        ttft_avg_ms=first("avg ttft") or first("ttft avg") or 0.0,
        ttft_p90_ms=first("p90 ttft") or first("ttft p90") or 0.0,
        ttft_p99_ms=first("p99 ttft") or first("ttft p99") or 0.0,
        tpot_avg_ms=first("avg tpot") or first("tpot avg") or 0.0,
        tpot_p90_ms=first("p90 tpot") or first("tpot p90") or 0.0,
        tpot_p99_ms=first("p99 tpot") or first("tpot p99") or 0.0,
        latency_avg_s=first("avg latency") or 0.0,
        latency_p90_s=first("p90 latency") or 0.0,
        latency_p99_s=first("p99 latency") or 0.0,
        input_tokens=first("input tokens") or 0.0,
        output_tokens=first("output tokens") or 0.0,
    )
    if not point.success_requests:
        point.success_requests = point.requests
    return point if point.ttft_p90_ms or point.tpot_p90_ms else None


def iter_json_files(root: str | Path, max_bytes: int = 30 * 1024 * 1024) -> Iterable[Path]:
    base = Path(root)
    if base.is_file() and base.suffix == ".json":
        yield base
        return
    if not base.exists():
        return
    for path in sorted(base.rglob("*.json")):
        if any(part in {"node_modules", ".git", "__pycache__"} for part in path.parts):
            continue
        try:
            if path.stat().st_size <= max_bytes:
                yield path
        except OSError:
            continue


def read_json_safe(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def _pick_percentile_row(rows: Any, percentile: int) -> dict[str, Any]:
    if not isinstance(rows, list):
        return {}
    wanted = f"{percentile}%"
    for row in rows:
        if isinstance(row, dict) and str(row.get("Percentiles", "")).strip() == wanted:
            return row
    return {}


def _point_from_summary(
    summary: dict[str, Any],
    percentile_row: dict[str, Any] | None = None,
    p99_row: dict[str, Any] | None = None,
) -> PerfPoint | None:
    concurrency = coerce_int(summary.get("Concurrency") or summary.get("concurrency"))
    if not concurrency:
        return None
    row = percentile_row or {}
    point = PerfPoint(
        concurrency=concurrency,
        requests=coerce_int(summary.get("Total Requests") or summary.get("total_requests")) or 0,
        success_requests=coerce_int(summary.get("Success Requests") or summary.get("succeed_requests")) or 0,
        throughput_tok_s=coerce_float(summary.get("Output Throughput (tok/s)")) or 0.0,
        rps=coerce_float(summary.get("Req Throughput (req/s)")) or 0.0,
        ttft_avg_ms=coerce_float(summary.get("Avg TTFT (ms)") or summary.get("TTFT (ms)")) or 0.0,
        ttft_p90_ms=coerce_float(row.get("TTFT (ms)")) or 0.0,
        ttft_p99_ms=coerce_float((p99_row or {}).get("TTFT (ms)")) or coerce_float(row.get("TTFT (ms)")) or 0.0,
        tpot_avg_ms=coerce_float(summary.get("Avg TPOT (ms)") or summary.get("TPOT (ms)")) or 0.0,
        tpot_p90_ms=coerce_float(row.get("TPOT (ms)")) or 0.0,
        tpot_p99_ms=coerce_float((p99_row or {}).get("TPOT (ms)")) or coerce_float(row.get("TPOT (ms)")) or 0.0,
        latency_avg_s=coerce_float(summary.get("Avg Latency (s)") or summary.get("Latency (s)")) or 0.0,
        latency_p90_s=coerce_float(row.get("Latency (s)")) or 0.0,
        latency_p99_s=coerce_float((p99_row or {}).get("Latency (s)")) or coerce_float(row.get("Latency (s)")) or 0.0,
        input_tokens=coerce_float(summary.get("Avg Input Tokens")) or 0.0,
        output_tokens=coerce_float(summary.get("Avg Output Tokens")) or 0.0,
    )
    if not point.success_requests and point.requests:
        point.success_requests = point.requests
    if not point.ttft_p90_ms:
        point.ttft_p90_ms = point.ttft_avg_ms
    if not point.tpot_p90_ms:
        point.tpot_p90_ms = point.tpot_avg_ms
    if not point.ttft_p99_ms:
        point.ttft_p99_ms = point.ttft_p90_ms
    if not point.tpot_p99_ms:
        point.tpot_p99_ms = point.tpot_p90_ms
    return point


def _parse_perf_run_dir(run_dir: Path) -> PerfPoint | None:
    summary_path = run_dir / "benchmark_summary.json"
    summary = read_json_safe(summary_path)
    if not isinstance(summary, dict):
        return None
    percentile_rows = read_json_safe(run_dir / "benchmark_percentile.json")
    p90_row = _pick_percentile_row(percentile_rows, 90)
    p99_row = _pick_percentile_row(percentile_rows, 99)
    return _point_from_summary(summary, p90_row, p99_row)


def parse_perf_output_dir(root: str | Path) -> list[PerfPoint]:
    base = Path(root)
    points: list[PerfPoint] = []
    for summary_path in base.rglob("benchmark_summary.json"):
        point = _parse_perf_run_dir(summary_path.parent)
        if point:
            points.append(point)
    for path in iter_json_files(base):
        data = read_json_safe(path)
        if isinstance(data, dict) and path.name not in {"benchmark_summary.json", "sla_summary.json"}:
            if "Total Requests" in data or "Concurrency" in data:
                point = _extract_metrics_from_dict(data)
                if point:
                    points.append(point)
    for path in base.rglob("*.txt"):
        if "performance_summary" in path.name or "benchmark" in path.name:
            points.extend(parse_perf_summary_file(path))
    unique: dict[int, PerfPoint] = {}
    for point in points:
        existing = unique.get(point.concurrency)
        if existing is None or (point.ttft_p90_ms and not existing.ttft_p90_ms):
            unique[point.concurrency] = point
    return [unique[key] for key in sorted(unique)]


# --------------------------------------------------------------------- SLA
def parse_sla_selection(text: str) -> dict[str, Any]:
    clean = strip_ansi(text)
    result: dict[str, Any] = {}
    patterns = [
        r"best observed\s+(?:parallel|concurrency|rate)\s*[:=]\s*(\d+)",
        r"(?:best|recommended|selected|optimal)[^\n]{0,80}?(?:parallel|concurrency|rate)[^\n]{0,20}?(\d+)",
        r"(?:parallel|concurrency|rate)[^\n]{0,20}?[=:]\s*(\d+)[^\n]{0,50}?(?:selected|best|PASSED)",
    ]
    for pattern in patterns:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            result["recommended_concurrency"] = int(match.group(1))
            break
    # EvalScope format_sla_tables: Criteria | Selected | Status | Reason
    for table in parse_rich_tables(clean):
        if not table:
            continue
        header = [normalize_label(cell) for cell in table[0]]
        selected_index = next((i for i, name in enumerate(header) if name == "selected"), None)
        status_index = next((i for i, name in enumerate(header) if name == "status"), None)
        if selected_index is None:
            continue
        for row in table[1:]:
            if selected_index >= len(row):
                continue
            selected = coerce_int(row[selected_index])
            status = row[status_index] if status_index is not None and status_index < len(row) else ""
            if selected:
                result["recommended_concurrency"] = selected
                result["selection_status"] = status
                if status and not re.search(r"fail|none|unsatisf", status, re.IGNORECASE):
                    result["target_met"] = True
                return result
    if re.search(r"(?:not satisf|no .*?satisf|无法满足|未找到|infeasible)", clean, re.IGNORECASE):
        result["satisfiable"] = False
    return result


def parse_sla_json(path: str | Path) -> list[PerfPoint]:
    data = read_json_safe(path)
    if not isinstance(data, dict):
        return []
    points: list[PerfPoint] = []
    for key, value in data.items():
        match = re.search(r"(?:parallel|rate)_(\d+)", str(key))
        if not match or not isinstance(value, dict):
            continue
        concurrency = int(match.group(1))
        metrics = value.get("metrics") if isinstance(value.get("metrics"), dict) else {}
        percentiles = value.get("percentiles")
        p90_row: dict[str, Any] = {}
        p99_row: dict[str, Any] = {}
        if isinstance(percentiles, dict):
            labels = percentiles.get("Percentiles") or []
            for index, label in enumerate(labels if isinstance(labels, list) else []):
                row = {
                    metric: values[index]
                    for metric, values in percentiles.items()
                    if metric != "Percentiles" and isinstance(values, list) and index < len(values)
                }
                if str(label) == "90%":
                    p90_row = row
                elif str(label) == "99%":
                    p99_row = row
        elif isinstance(percentiles, list):
            p90_row = _pick_percentile_row(percentiles, 90)
            p99_row = _pick_percentile_row(percentiles, 99)
        summary = dict(metrics)
        if "Concurrency" not in summary:
            summary["Concurrency"] = concurrency
        point = _point_from_summary(summary, p90_row, p99_row)
        if point is None:
            flat = {**metrics, **p90_row, "concurrency": concurrency}
            point = _extract_metrics_from_dict(flat)
        if point:
            point.concurrency = concurrency
            if p99_row:
                point.ttft_p99_ms = coerce_float(p99_row.get("TTFT (ms)")) or point.ttft_p99_ms
                point.tpot_p99_ms = coerce_float(p99_row.get("TPOT (ms)")) or point.tpot_p99_ms
                point.latency_p99_s = coerce_float(p99_row.get("Latency (s)")) or point.latency_p99_s
            points.append(point)
    return points


def parse_sla_output(root: str | Path, text: str) -> list[PerfPoint]:
    points = parse_perf_tables(text)
    base = Path(root)
    for path in base.rglob("sla_summary.json") if base.exists() else []:
        points.extend(parse_sla_json(path))
    unique: dict[int, PerfPoint] = {}
    for point in points:
        unique[point.concurrency] = point
    return [unique[key] for key in sorted(unique)]


# ----------------------------------------------------------------- accuracy
def _looks_like_score_key(key: str) -> bool:
    return normalize_label(key).replace(" ", "_") in _SCORE_KEYS or normalize_label(key) in _SCORE_KEYS


def _normalize_score(value: Any) -> float | None:
    number = coerce_float(value)
    if number is None:
        return None
    if number > 1.0 + 1e-9 and number <= 100.0:
        number /= 100.0
    if -0.001 <= number <= 1.001:
        return round(max(0.0, min(1.0, number)), 6)
    return None


def extract_score(data: Any, dataset: str) -> float | None:
    """在 EvalScope 结果 JSON 中递归定位指定数据集的主分数。"""
    aliases = {
        dataset,
        dataset.replace("-", "_"),
        dataset.replace("_", "-"),
        dataset.lower(),
    }

    def find_metric(node: Any) -> float | None:
        if not isinstance(node, dict):
            return None
        # 直接分数键
        for key, value in node.items():
            if _looks_like_score_key(str(key)):
                score = _normalize_score(value)
                if score is not None:
                    return score
        # 常见包装：{"accuracy": {"value": 0.5}} / {"score": {"mean": 0.5}}
        for key, value in node.items():
            if _looks_like_score_key(str(key)) and isinstance(value, dict):
                for nested_key in ("value", "mean", "avg", "score", "accuracy"):
                    if nested_key in value:
                        score = _normalize_score(value[nested_key])
                        if score is not None:
                            return score
        return None

    def walk(node: Any, path: list[str]) -> float | None:
        if isinstance(node, dict):
            for key, value in node.items():
                normalized_key = str(key).lower()
                if any(alias.lower() == normalized_key for alias in aliases):
                    score = find_metric(value)
                    if score is not None:
                        return score
                    if isinstance(value, (int, float)):
                        score = _normalize_score(value)
                        if score is not None:
                            return score
                    # 数据集节点下可能还有子集/任务层级
                    nested = walk(value, path + [str(key)])
                    if nested is not None:
                        return nested
                # 文件内单数据集结果：顶层直接是分数结构
                if set(map(lambda item: str(item).lower(), node.keys())) & {
                    "accuracy",
                    "score",
                    "acc",
                    "averageaccuracy",
                }:
                    score = find_metric(node)
                    if score is not None:
                        return score
                if isinstance(value, dict):
                    nested = walk(value, path + [str(key)])
                    if nested is not None:
                        return nested
                # EvalScope 1.15+：分数常位于数组内（如 metrics[0].score）
                if isinstance(value, list):
                    nested = walk(value, path + [str(key)])
                    if nested is not None:
                        return nested
        elif isinstance(node, list):
            for item in node:
                nested = walk(item, path)
                if nested is not None:
                    return nested
        return None

    return walk(data, [])


def parse_accuracy_output(root: str | Path, dataset: str, stdout: str = "") -> tuple[float | None, str]:
    candidates: list[tuple[float, str]] = []
    base = Path(root)
    report_root = base / "reports"
    search_root = report_root if report_root.exists() else base
    for path in iter_json_files(search_root):
        data = read_json_safe(path)
        if data is None:
            continue
        score = extract_score(data, dataset)
        if score is not None:
            candidates.append((score, str(path)))
    if candidates:
        # 优先 results/report 文件，其次取最后一个
        candidates.sort(key=lambda item: (("result" not in item[1].lower()), item[1]))
        return candidates[0]

    clean = strip_ansi(stdout)
    dataset_pattern = re.escape(dataset)
    patterns = [
        rf"{dataset_pattern}[^\n]{{0,120}}?(?:accuracy|score|acc)[^\n]{{0,20}}?[:=]\s*([\d.]+%?)",
        rf"(?:accuracy|score|acc)[^\n]{{0,20}}?[:=]\s*([\d.]+%?)[^\n]{{0,120}}?{dataset_pattern}",
    ]
    for pattern in patterns:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            raw = match.group(1)
            score = _normalize_score(raw[:-1] if raw.endswith("%") else raw)
            if score is not None:
                return score, "stdout"
    # EvalScope 1.15 汇总表行：│ qwen… │ GSM8K │ Accuracy ↑ │ main │ 5 │ 1 │ 20% │
    # 取数据集所在行内“最后一个百分比/小数”，避免误抓 Num/Correct 等计数字段
    for line_match in re.finditer(
        rf"{dataset_pattern}[^\n]*(?:accuracy|score|acc)[^\n]*$", clean, re.IGNORECASE | re.MULTILINE
    ):
        line = line_match.group(0)
        numbers = re.findall(r"(\d+(?:\.\d+)?)\s*%", line) or re.findall(r"(\d+\.\d+)", line)
        if numbers:
            score = _normalize_score(numbers[-1])
            if score is not None:
                return score, "stdout"
    return None, ""


# --------------------------------------------------------------- multiturn
def parse_multiturn_metrics(text: str) -> dict[str, float]:
    clean = strip_ansi(text)
    metrics: dict[str, float] = {}
    for table in parse_rich_tables(clean):
        if not table or "metric" not in normalize_label(table[0][0]):
            continue
        for row in table[1:]:
            if not row:
                continue
            label = normalize_label(row[0])
            if label in {
                "turns/req",
                "turns per req",
                "avg turns/request",
                "cache hit (%)",
                "cache hit",
                "kv cache hit rate (%)",
            }:
                value = None
                for index in range(1, len(row)):
                    value = coerce_float(row[index])
                    if value is not None:
                        break
                if value is not None:
                    metrics[label] = value
    for pattern, key in (
        (r"(?:KV )?Cache Hit[^\n]{0,30}?[:|]\s*([\d.]+)\s*%", "cache_hit_rate"),
        (r"(?:Avg )?Turns/(?:Req|Request)[^\n]{0,20}?[:|]\s*([\d.]+)", "turns_per_request"),
    ):
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            value = coerce_float(match.group(1))
            if value is not None:
                metrics[key] = value / 100 if key == "cache_hit_rate" else value
    for key in ("cache hit (%)", "kv cache hit rate (%)"):
        if key in metrics:
            metrics["cache_hit_rate"] = metrics.pop(key) / 100
    for key in ("turns/req", "avg turns/request"):
        if key in metrics:
            metrics["turns_per_request"] = metrics.pop(key)
    return metrics


# ------------------------------------------------------------------- agent
def _numeric_by_keys(data: Any, keys: tuple[str, ...]) -> float | None:
    wanted = {normalize_label(key) for key in keys}
    if isinstance(data, dict):
        for key, value in data.items():
            if normalize_label(key) in wanted:
                number = coerce_float(value)
                if number is not None:
                    return number
        for value in data.values():
            found = _numeric_by_keys(value, keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _numeric_by_keys(item, keys)
            if found is not None:
                return found
    return None


def _metric_average(data: Any, names: tuple[str, ...]) -> float | None:
    """EvalScope AgentX metrics are ``{unit, avg, ...}`` blocks, not scalars."""
    if not isinstance(data, dict):
        return None
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
    for name in names:
        metric = metrics.get(name) if isinstance(metrics, dict) else None
        if isinstance(metric, dict):
            for key in ("avg", "mean", "value"):
                number = coerce_float(metric.get(key))
                if number is not None:
                    return number
        number = coerce_float(metric)
        if number is not None:
            return number
        number = coerce_float(data.get(name))
        if number is not None:
            return number
    return _numeric_by_keys(data, names)


def parse_agent_output(root: str | Path, stdout: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    base = Path(root)
    for name in ("agentx_summary.json", "agentx_sweep_summary.json"):
        for path in base.rglob(name) if base.exists() else []:
            data = read_json_safe(path)
            if isinstance(data, dict):
                result["raw"] = data
                result["source_file"] = str(path)
                break
        if result:
            break
    data = result.get("raw", {})
    request_count = _metric_average(data, ("request_count",))
    error_count = _metric_average(data, ("error_request_count",)) or 0.0
    total = _metric_average(data, ("total_requests", "request_count"))
    success = _metric_average(data, ("successful_requests", "success_requests", "succeeded_requests"))
    completion = _numeric_by_keys(data, ("completion_rate", "success_rate", "request_success_rate"))
    if completion is not None and completion > 1.5:
        completion /= 100.0
    if completion is None and request_count:
        completion = max(0.0, 1.0 - error_count / request_count)
    if completion is None and total and success is not None:
        completion = success / total
    concurrency = coerce_int(data.get("concurrency")) if isinstance(data, dict) else None
    sessions = concurrency or _numeric_by_keys(data, ("sessions", "session_count"))
    requests = request_count or total or 0.0
    avg_steps = _numeric_by_keys(data, ("avg_steps", "avg_requests_per_session", "steps_per_session"))
    if avg_steps is None and sessions and requests:
        avg_steps = requests / sessions
    valid = data.get("submission_valid") if isinstance(data, dict) else None
    status = data.get("status") if isinstance(data, dict) else None
    throughput = _metric_average(
        data, ("output_token_throughput", "request_throughput")
    )
    latency = _metric_average(data, ("request_latency", "time_to_first_token"))
    result.update(
        {
            "completion_rate": completion,
            "avg_steps": avg_steps,
            "sessions": int(sessions) if sessions else 0,
            "requests": int(requests) if requests else 0,
            "submission_valid": valid,
            "status": status,
            "output_token_throughput": throughput,
            "request_latency": latency,
            "request_count": request_count,
            "error_request_count": error_count,
        }
    )
    if completion is None and not data:
        clean = strip_ansi(stdout)
        match = re.search(r"Success[^\n]{0,40}?(\d+(?:\.\d+)?)\s*%", clean, re.IGNORECASE)
        if match:
            result["completion_rate"] = float(match.group(1)) / 100.0
    return result
