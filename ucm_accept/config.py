from __future__ import annotations

import copy
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PACKAGE_DIR / "resources" / "config.yaml"

_MISSING = object()
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class ConfigError(ValueError):
    """配置缺失或非法。错误信息面向交付人员，不暴露 Python 堆栈。"""


def _expand_env(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in os.environ and os.environ[name] != "":
            return os.environ[name]
        if default is not None:
            return default
        raise ConfigError(f"配置引用了未设置的环境变量 ${{{name}}}")

    return _ENV_PATTERN.sub(repl, value)


def _walk_expand(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: _walk_expand(val) for key, val in node.items()}
    if isinstance(node, list):
        return [_walk_expand(item) for item in node]
    if isinstance(node, str):
        return os.path.expanduser(_expand_env(node))
    return node


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """递归合并配置；列表与标量直接覆盖，便于高级选项整体替换。"""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _flatten_keys(data: dict[str, Any], prefix: str = "") -> Iterable[str]:
    for key, value in data.items():
        dotted = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            yield from _flatten_keys(value, dotted)
        else:
            yield dotted


class Config:
    """外部 YAML 配置的只读视图（支持显式运行时覆盖）。"""

    def __init__(self, data: dict[str, Any], *, source: Path | None = None):
        self._data = data
        self.source = source
        self.base_dir = source.parent if source else PACKAGE_DIR
        self.validate()

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> Config:
        source = Path(path).expanduser().resolve() if path else DEFAULT_CONFIG_PATH
        if not source.exists():
            raise ConfigError(f"配置文件不存在：{source}")
        try:
            user_data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"配置文件 YAML 语法错误：{exc}") from exc
        if not isinstance(user_data, dict):
            raise ConfigError("配置文件根节点必须是字典（key: value）")

        data = copy.deepcopy(user_data)
        if source != DEFAULT_CONFIG_PATH:
            default_data = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")) or {}
            data = deep_merge(default_data, user_data)
        if overrides:
            data = deep_merge(data, overrides)
        data = _walk_expand(data)
        return cls(data, source=source)

    # --------------------------------------------------------------- access
    def get(self, dotted: str, default: Any = _MISSING) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                if default is _MISSING:
                    raise ConfigError(f"缺少配置项：{dotted}（请检查 config.yaml）")
                return default
            node = node[part]
        return node

    def section(self, dotted: str) -> dict[str, Any]:
        value = self.get(dotted, {})
        if not isinstance(value, dict):
            raise ConfigError(f"配置项 {dotted} 必须是字典")
        return copy.deepcopy(value)

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self._data
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value

    def with_overrides(self, overrides: dict[str, Any]) -> Config:
        if not overrides:
            return Config(copy.deepcopy(self._data), source=self.source)
        merged = deep_merge(self._data, _walk_expand(overrides))
        return Config(merged, source=self.source)

    def clone(self) -> Config:
        return Config(copy.deepcopy(self._data), source=self.source)

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def keys(self) -> list[str]:
        return list(_flatten_keys(self._data))

    # ----------------------------------------------------------------- paths
    def resolve_asset(self, value: str | Path) -> Path:
        """解析数据集 / tokenizer 等资产路径。

        顺序：绝对路径 → 配置文件目录 → 包内置 resources → 当前工作目录。
        不存在的相对路径按配置文件目录返回，便于报错时展示预期位置。
        """
        raw = Path(str(value)).expanduser()
        if raw.is_absolute():
            return raw
        candidates = [
            self.base_dir / raw,
            PACKAGE_DIR / "resources" / raw,
            PACKAGE_DIR / raw,
            Path.cwd() / raw,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return (self.base_dir / raw).resolve()

    def resolve_output(self, value: str | Path) -> Path:
        raw = Path(str(value)).expanduser()
        if raw.is_absolute():
            return raw
        return (Path.cwd() / raw).resolve()

    @property
    def report_dir(self) -> Path:
        return self.resolve_output(self.get("app.report_dir", "./outputs"))

    @property
    def evalscope_outputs_dir(self) -> Path:
        return self.resolve_output(self.get("evalscope.outputs_dir", "./outputs/evalscope"))

    # ------------------------------------------------------------ validation
    def validate(self) -> None:
        required = [
            "app",
            "endpoint",
            "defaults",
            "perf",
            "multiturn",
            "sla",
            "accuracy",
            "agent",
            "evalscope",
            "report",
        ]
        for section in required:
            if not isinstance(self.get(section, None), dict):
                raise ConfigError(f"缺少配置章节：{section}")

        base_url = str(self.get("endpoint.base_url", "")).strip()
        if not re.match(r"^https?://", base_url):
            raise ConfigError("endpoint.base_url 必须以 http:// 或 https:// 开头")
        if not str(self.get("endpoint.model", "")).strip():
            raise ConfigError("endpoint.model 不能为空")

        parallel = self.get("perf.parallel", [])
        if isinstance(parallel, int):
            parallel = [parallel]
            self.set("perf.parallel", parallel)
        if not isinstance(parallel, list) or not parallel:
            raise ConfigError("perf.parallel 必须是非空列表，例如 [10, 20, 40]")
        try:
            parallel = [int(item) for item in parallel]
        except (TypeError, ValueError) as exc:
            raise ConfigError("perf.parallel 中的并发值必须是整数") from exc
        if any(item <= 0 for item in parallel):
            raise ConfigError("perf.parallel 中的并发值必须大于 0")
        self.set("perf.parallel", parallel)

        for key in ("perf.number", "perf.min_prompt_length", "perf.max_prompt_length", "perf.max_tokens"):
            if int(self.get(key, 0)) <= 0:
                raise ConfigError(f"{key} 必须大于 0")
        if int(self.get("perf.min_prompt_length")) > int(self.get("perf.max_prompt_length")):
            raise ConfigError("perf.min_prompt_length 不能大于 max_prompt_length")

        mode = self.get("sla.mode", "auto_tune")
        if mode not in {"verify", "auto_tune"}:
            raise ConfigError("sla.mode 只能是 verify 或 auto_tune")
        lower = int(self.get("sla.auto_tune.lower", 1))
        upper = int(self.get("sla.auto_tune.upper", 200))
        if lower <= 0 or upper <= 0 or lower > upper:
            raise ConfigError("SLA 自动调优区间非法：需满足 0 < lower <= upper")
        target_conc = int(self.get("sla.target.concurrency", 200))
        if mode == "auto_tune" and upper < target_conc:
            raise ConfigError("sla.auto_tune.upper 不能小于 sla.target.concurrency，否则无法判定目标并发是否达标")
        if target_conc <= 0:
            raise ConfigError("sla.target.concurrency 必须大于 0")
        for key in ("sla.target.context_length", "sla.target.ttft_p90_ms", "sla.target.tpot_p90_ms"):
            if float(self.get(key, 0)) <= 0:
                raise ConfigError(f"{key} 必须大于 0")

        if int(self.get("accuracy.runs", 2)) < 1:
            raise ConfigError("accuracy.runs 至少为 1")
        datasets = self.get("accuracy.datasets", {})
        if not isinstance(datasets, dict) or not datasets:
            raise ConfigError("accuracy.datasets 不能为空")
        for name, item in datasets.items():
            if not isinstance(item, dict) or not item.get("dataset"):
                raise ConfigError(f"accuracy.datasets.{name}.dataset 不能为空")

        if int(self.get("agent.context_required", 1)) <= 0:
            raise ConfigError("agent.context_required 必须大于 0")
        if not 0 < float(self.get("agent.success_threshold", 0.95)) <= 1:
            raise ConfigError("agent.success_threshold 必须在 (0, 1] 之间")
        duration = int(self.get("agent.duration_s", 900))
        if duration < 900:
            raise ConfigError("agent.duration_s 不能小于 900 秒（EvalScope AgentX benchmark 模式限制）")

        scenario = self.get("multiturn.scenario", "dialogue")
        if scenario not in self.get("multiturn.scenarios", {}):
            raise ConfigError(f"multiturn.scenario 未在预设中定义：{scenario}")

        timeout = float(self.get("endpoint.timeout_s", 60))
        if timeout <= 0:
            raise ConfigError("endpoint.timeout_s 必须大于 0")

    # --------------------------------------------------------------- helpers
    def apply_endpoint(self, base_url: str | None = None, model: str | None = None, api_key: str | None = None) -> None:
        if base_url is not None:
            base_url = base_url.strip().rstrip("/")
            if not re.match(r"^https?://", base_url):
                raise ConfigError("服务地址必须以 http:// 或 https:// 开头")
            self.set("endpoint.base_url", base_url)
        if model is not None:
            if not model.strip():
                raise ConfigError("模型名称不能为空")
            self.set("endpoint.model", model.strip())
        if api_key is not None:
            self.set("endpoint.api_key", api_key)

    def masked(self) -> dict[str, Any]:
        """用于报告快照的脱敏配置。"""
        data = self.to_dict()
        key = data.get("endpoint", {}).get("api_key")
        if key:
            data["endpoint"]["api_key"] = "***"
        env = data.get("evalscope", {}).get("env", {})
        if isinstance(env, dict):
            for name in list(env):
                if any(token in name.upper() for token in ("KEY", "TOKEN", "SECRET")):
                    env[name] = "***"
        return data


def load_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> Config:
    return Config.load(path, overrides)
