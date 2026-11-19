from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import shutil
import sys
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import iso_now


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(2)


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_text_atomic(path: str | Path, text: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    return target


def write_json_atomic(path: str | Path, data: Any) -> Path:
    return write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


def read_json(path: str | Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def shell_join(argv: Sequence[str]) -> str:
    return " ".join(shlex.quote(str(arg)) for arg in argv)


def display_width(text: str) -> int:
    width = 0
    for char in str(text):
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return width


def pad_display(text: Any, width: int, align: str = "left") -> str:
    text = str(text)
    current = display_width(text)
    if current > width:
        text = truncate_display(text, width)
        current = display_width(text)
    space = max(0, width - current)
    if align == "right":
        return " " * space + text
    if align == "center":
        left = space // 2
        return " " * left + text + " " * (space - left)
    return text + " " * space


def truncate_display(text: str, width: int) -> str:
    if display_width(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    result = ""
    current = 0
    for char in str(text):
        char_width = 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        if current + char_width > width - 1:
            break
        result += char
        current += char_width
    return result + "…"


def render_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[Any]],
    *,
    aligns: Sequence[str] | None = None,
    max_width: int = 34,
) -> str:
    matrix = [[str(cell) for cell in row] for row in rows]
    all_rows = [list(headers)] + matrix
    widths: list[int] = []
    for index in range(len(headers)):
        width = max(display_width(row[index]) for row in all_rows if index < len(row))
        widths.append(min(width, max_width))
    aligns = list(aligns or ["left"] * len(headers))

    def line(left: str, mid: str, right: str) -> str:
        return left + mid.join("─" * (width + 2) for width in widths) + right

    output = [line("┌", "┬", "┐")]
    output.append("│ " + " │ ".join(pad_display(cell, widths[i], aligns[i]) for i, cell in enumerate(headers)) + " │")
    output.append(line("├", "┼", "┤"))
    for row in matrix:
        output.append(
            "│ "
            + " │ ".join(
                pad_display(row[i] if i < len(row) else "", widths[i], aligns[i]) for i in range(len(headers))
            )
            + " │"
        )
    output.append(line("└", "┴", "┘"))
    return "\n".join(output)


def find_latest_report(outputs_root: str | Path = "./outputs") -> Path | None:
    root = Path(outputs_root)
    pointer = root / "latest.txt"
    if pointer.exists():
        try:
            candidate = Path(pointer.read_text(encoding="utf-8").strip())
            if candidate.is_file():
                return candidate
            candidate = pointer.parent / candidate
            if candidate.is_file():
                return candidate
        except OSError:
            pass
    runs = root / "runs"
    if not runs.exists():
        return None
    reports = sorted(runs.glob("*/report.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def latest_run_dir(outputs_root: str | Path = "./outputs") -> Path | None:
    report = find_latest_report(outputs_root)
    return report.parent if report else None


def set_latest_pointer(outputs_root: str | Path, run_dir: str | Path) -> None:
    root = ensure_dir(outputs_root)
    try:
        relative = Path(run_dir).resolve().relative_to(root.resolve())
        text = str(relative)
    except ValueError:
        text = str(Path(run_dir).resolve())
    write_text_atomic(root / "latest.txt", text + "\n")


def compare_versions(left: str, right: str) -> int:
    def parts(value: str) -> list[int]:
        return [int(item) for item in re.findall(r"\d+", value)[:3]]

    a, b = parts(left), parts(right)
    a += [0] * (3 - len(a))
    b += [0] * (3 - len(b))
    return (a > b) - (a < b)


def has_desktop() -> bool:
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def redact_secret(text: str, secret: str | None) -> str:
    if secret and len(secret) >= 4:
        return text.replace(secret, "***")
    return text


def safe_filename(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", text.strip())
    return cleaned or "report"


def relative_artifact(path: str | Path, base: str | Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(base).resolve()))
    except (ValueError, OSError):
        return str(Path(path))


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def now_text() -> str:
    return iso_now()


def shorten(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def deep_get(data: Any, *keys: str, default: Any = None) -> Any:
    node = data
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text in {"-", "—", "N/A", "nan", "None"}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def coerce_int(value: Any) -> int | None:
    number = coerce_float(value)
    return int(number) if number is not None else None
