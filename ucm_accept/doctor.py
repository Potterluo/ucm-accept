from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import assets as assets_hub
from .config import Config
from .engine.base import Endpoint
from .engine.chat import ChatClient
from .utils import compare_versions


@dataclass
class CheckResult:
    name: str
    status: str  # ok | warn | fail | skip
    detail: str
    hint: str = ""


def _ok(name: str, detail: str) -> CheckResult:
    return CheckResult(name, "ok", detail)


def _warn(name: str, detail: str, hint: str = "") -> CheckResult:
    return CheckResult(name, "warn", detail, hint)


def _fail(name: str, detail: str, hint: str = "") -> CheckResult:
    return CheckResult(name, "fail", detail, hint)


def _skip(name: str, detail: str) -> CheckResult:
    return CheckResult(name, "skip", detail)


def _manifest_checks(config: Config) -> list[CheckResult]:
    manifest_path = Path(__file__).resolve().parent / "resources" / "assets_manifest.json"
    if not manifest_path.exists():
        return [_warn("离线资产清单", "未找到 assets_manifest.json")]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [_fail("离线资产清单", f"无法读取：{exc}")]
    results: list[CheckResult] = []
    root = manifest_path.parent
    missing = 0
    mismatched = 0
    for asset in manifest.get("assets", []):
        path = root / asset.get("path", "")
        if not path.exists():
            missing += 1
            results.append(_fail("离线资产", f"缺失：{asset.get('path')}", "请重新构建离线包或补齐物料"))
            continue
        expected = asset.get("sha256")
        if expected:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                mismatched += 1
                results.append(_fail("离线资产", f"校验和不一致：{asset.get('path')}"))
    if not missing and not mismatched:
        results.append(_ok("离线资产", f"{len(manifest.get('assets', []))} 项内置资产完整"))
    return results


def _asset_hub_checks(config: Config) -> list[CheckResult]:
    """统一资产包检查：来源、manifest 校验、数据集缓存。"""
    configured = ""
    try:
        configured = str(config.get("app.assets_dir", "") or "")
    except Exception:  # noqa: BLE001 - 配置缺失时按未配置处理
        configured = ""
    hub = assets_hub.find_assets_root(configured or None)
    results: list[CheckResult] = []
    if hub is None:
        results.append(
            _warn(
                "资产包",
                "未发现统一资产包",
                "设置 UCM_ASSETS_DIR / app.assets_dir，或将 assets/ 放在可执行文件同级；"
                "内置多轮预设仍可用",
            )
        )
        results.extend(_manifest_checks(config))
        return results
    results.append(_ok("资产包", assets_hub.describe(hub)))
    total, problems = assets_hub.verify_manifest(hub)
    if total == 0 and problems:
        results.append(_warn("资产包清单", problems[0], "用 scripts/prepare_assets.py 生成 manifest.json"))
    elif problems:
        for problem in problems:
            results.append(_fail("资产包校验", problem, "重新执行 scripts/prepare_assets.py 或补齐物料"))
        results.append(_ok("资产包清单", f"已检查 {min(total, len(problems) + 1)}/{total} 项，其余未展示"))
    else:
        results.append(_ok("资产包清单", f"{total} 项资产 SHA256 校验通过"))
    cache = assets_hub.cache_env(hub)
    if cache:
        detail = "；".join(f"{var}={Path(path)}" for var, path in cache.items())
        results.append(_ok("数据集缓存", detail))
    else:
        results.append(
            _warn(
                "数据集缓存",
                "资产包内无 evalscope-cache / modelscope-cache",
                "精度与 Agent 数据集需在构建机预热后放入；否则 evalscope 首次运行会尝试联网下载",
            )
        )
    return results


def run_doctor(config: Config, *, probe: bool = False, mock: bool = False) -> list[CheckResult]:
    results: list[CheckResult] = []
    version = sys.version_info
    if version >= (3, 10):
        results.append(_ok("Python", f"{version.major}.{version.minor}.{version.micro}"))
    else:
        results.append(_fail("Python", f"{version.major}.{version.minor}.{version.micro}", "需要 Python 3.10+"))

    try:
        config.validate()
        results.append(_ok("配置", str(config.source or "内置默认配置")))
    except Exception as exc:  # noqa: BLE001
        results.append(_fail("配置", str(exc)))

    report_dir = config.report_dir
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=report_dir, prefix=".ucm-write-", delete=True):
            pass
        results.append(_ok("报告目录", f"{report_dir}（可写）"))
    except OSError as exc:
        results.append(_fail("报告目录", f"{report_dir} 不可写：{exc}"))

    if mock:
        results.append(_skip("EvalScope", "模拟模式不需要 EvalScope"))
    else:
        executable = str(config.get("evalscope.executable", "evalscope"))
        first = executable.split()[0] if executable else "evalscope"
        resolved = first if Path(first).exists() else shutil.which(first)
        if resolved:
            results.append(_ok("EvalScope", str(resolved)))
            try:
                proc = subprocess.run(
                    [*executable.split(), "--version"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                text = (proc.stdout or proc.stderr).strip().splitlines()
                if proc.returncode == 0 and text:
                    version_line = text[0][:160]
                    result = _ok("EvalScope 版本", version_line)
                    minimum = str(config.get("evalscope.min_version", "1.15.0"))
                    if compare_versions(version_line, minimum) < 0:
                        result = _warn(
                            "EvalScope 版本",
                            f"{version_line} 低于要求的 {minimum}",
                            "p90_ttft/p90_tpot 原生 SLA 参数需要 EvalScope >= 1.15",
                        )
                    results.append(result)
                else:
                    results.append(_warn("EvalScope 版本", "无法读取版本号"))
            except (OSError, subprocess.SubprocessError) as exc:
                results.append(_warn("EvalScope 版本", f"检查失败：{exc}"))
        else:
            results.append(
                _fail(
                    "EvalScope",
                    f"未找到 {first}",
                    "请安装 evalscope，或在 config.yaml 中设置 evalscope.executable",
                )
            )

    gui_missing = [name for name in ("fastapi", "uvicorn")
                   if importlib.util.find_spec(name) is None]
    if gui_missing:
        results.append(_warn(
            "GUI 依赖", "未安装 " + "、".join(gui_missing),
            "CLI 不受影响；GUI 需 pip install 'ucm-accept[gui]'（gradio 已弃用）"))
    else:
        results.append(_ok("GUI 依赖", "fastapi / uvicorn 已安装"))

    results.extend(_asset_hub_checks(config))

    tokenizer = str(config.get("perf.tokenizer_path", "") or "")
    if tokenizer and tokenizer.startswith(("/", "./", "../", "~")):
        path = config.resolve_asset(tokenizer)
        if path.exists():
            results.append(_ok("Tokenizer", str(path)))
        else:
            results.append(_warn("Tokenizer", f"路径不存在：{path}", "离线包内应预置 tokenizer"))
    elif tokenizer:
        # 模型 ID 风格（如 Qwen/Qwen2.5-0.5B-Instruct）：先尝试从资产包按名称解析
        resolved = None
        hub = assets_hub.find_assets_root(str(config.get("app.assets_dir", "") or "") or None)
        if hub is not None:
            for name in (tokenizer.split("/")[-1], str(config.get("endpoint.model", "") or "")):
                if not name:
                    continue
                hit = assets_hub.resolve_in_hub(hub, name)
                if hit is not None and hit.is_dir():
                    resolved = hit
                    break
        if resolved is not None:
            results.append(_ok("Tokenizer", f"{resolved}（资产包自动解析：{tokenizer}）"))
        else:
            results.append(_warn("Tokenizer", f"使用模型 ID：{tokenizer}", "离线环境需提前缓存或放入资产包 tokenizers/<模型名>/"))

    missing_scenarios = []
    for key, presets in (config.get("multiturn.scenarios", {}) or {}).items():
        path = config.resolve_asset(presets.get("dataset_path", ""))
        if not path.exists():
            missing_scenarios.append(f"{key}:{path}")
    if missing_scenarios:
        results.append(_fail("多轮预设", "缺失：" + "；".join(missing_scenarios)))
    else:
        results.append(_ok("多轮预设", f"{len(config.get('multiturn.scenarios', {}) or {})} 个场景数据可用"))

    if probe and mock:
        results.append(_skip("服务连通", "模拟模式不探测真实服务"))
    elif probe:
        endpoint = Endpoint(
            base_url=str(config.get("endpoint.base_url")),
            model=str(config.get("endpoint.model")),
            api_key=str(config.get("endpoint.api_key", "") or ""),
            timeout_s=float(config.get("endpoint.timeout_s", 180)),
            connect_timeout_s=float(config.get("endpoint.connect_timeout_s", 8)),
            probe_mode=str(config.get("endpoint.probe_mode", "auto")),
        )
        result = ChatClient(endpoint).probe()
        results.append(
            _ok("服务连通", result.message) if result.connected else _fail("服务连通", result.message)
        )

    if importlib.util.find_spec("aiperf"):
        results.append(_ok("AgentX 依赖", "aiperf 已安装"))
    else:
        results.append(
            _warn(
                "AgentX 依赖",
                "未安装 aiperf",
                "Agent 场景需要 pip install 'evalscope[agentx]' 且 Python 3.11–3.13",
            )
        )

    if importlib.util.find_spec("weasyprint") or any(
        shutil.which(tool) for tool in ("chromium", "chromium-browser", "google-chrome", "microsoft-edge")
    ):
        results.append(_ok("PDF 导出", "可用"))
    else:
        results.append(_warn("PDF 导出", "未安装 weasyprint / chromium", "HTML 报告不受影响，可用浏览器打印为 PDF"))

    return results
