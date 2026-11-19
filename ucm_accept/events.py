from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ProgressEvent:
    """统一进度事件。

    fraction: 当前测试项内的完成比例（0~1）。
    overall: 整个验收任务内的完成比例（0~1）；单项运行时与 fraction 相同。
    level: info | success | warning | error | command
    """

    item: str
    message: str
    fraction: float = 0.0
    overall: float = 0.0
    level: str = "info"
    command: str = ""


ProgressCallback = Callable[[ProgressEvent], None]


def emit(
    callback: ProgressCallback | None,
    item: str,
    message: str,
    *,
    fraction: float = 0.0,
    overall: float | None = None,
    level: str = "info",
    command: str = "",
) -> None:
    if callback is None:
        return
    fraction = max(0.0, min(1.0, float(fraction)))
    callback(
        ProgressEvent(
            item=item,
            message=message,
            fraction=fraction,
            overall=fraction if overall is None else max(0.0, min(1.0, float(overall))),
            level=level,
            command=command,
        )
    )
