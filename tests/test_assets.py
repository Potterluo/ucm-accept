from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ucm_accept import assets as hub
from ucm_accept.config import Config


def _make_pack(tmp_path: Path) -> Path:
    """构建一个最小但完整的资产包：tokenizer + 多轮覆盖 + 缓存 + 清单。"""
    root = tmp_path / "ucm-assets"
    tokenizer = root / "tokenizers" / "Qwen2.5-0.5B-Instruct"
    tokenizer.mkdir(parents=True)
    (tokenizer / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    datasets = root / "datasets" / "multiturn"
    datasets.mkdir(parents=True)
    (datasets / "dialogue.jsonl").write_text('{"turns": []}\n', encoding="utf-8")
    cache = root / "evalscope-cache"
    cache.mkdir()
    (cache / "placeholder.txt").write_text("cache", encoding="utf-8")
    ms_cache = root / "modelscope-cache" / "datasets"
    ms_cache.mkdir(parents=True)
    (ms_cache / "placeholder.txt").write_text("cache", encoding="utf-8")
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            entries.append(
                {
                    "path": str(path.relative_to(root)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "size": path.stat().st_size,
                }
            )
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "assets": entries}, ensure_ascii=False), encoding="utf-8"
    )
    return root


def test_find_assets_root_prefers_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    pack = _make_pack(tmp_path)
    other = tmp_path / "other-pack"
    other.mkdir()
    monkeypatch.setenv(hub.ENV_VAR, str(pack))
    assert hub.find_assets_root(str(other)) == pack.resolve()


def test_find_assets_root_prefers_config_over_exe_adjacent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    pack = _make_pack(tmp_path)
    monkeypatch.delenv(hub.ENV_VAR, raising=False)
    assert hub.find_assets_root(str(pack)) == pack.resolve()


def test_find_assets_root_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv(hub.ENV_VAR, raising=False)
    assert hub.find_assets_root(str(tmp_path / "nope")) is None


def test_resolve_in_hub_auto_prefixes(tmp_path: Path):
    pack = _make_pack(tmp_path)
    hit = hub.resolve_in_hub(pack, "Qwen2.5-0.5B-Instruct")
    assert hit is not None and hit.name == "Qwen2.5-0.5B-Instruct"
    hit2 = hub.resolve_in_hub(pack, "multiturn/dialogue.jsonl")
    assert hit2 is not None and hit2.exists()
    assert hub.resolve_in_hub(pack, "/abs/path") is None
    assert hub.resolve_in_hub(pack, "missing.txt") is None


def test_cache_env(tmp_path: Path):
    pack = _make_pack(tmp_path)
    env = hub.cache_env(pack)
    assert env["EVALSCOPE_CACHE"] == str((pack / "evalscope-cache").resolve())
    assert env["MODELSCOPE_CACHE"] == str((pack / "modelscope-cache").resolve())


def test_verify_manifest_detects_tamper(tmp_path: Path):
    pack = _make_pack(tmp_path)
    total, problems = hub.verify_manifest(pack)
    assert total == 4 and problems == []
    # 篡改一个文件后应检出哈希不一致
    (pack / "datasets" / "multiturn" / "dialogue.jsonl").write_text("tampered\n", encoding="utf-8")
    _, problems = hub.verify_manifest(pack)
    assert problems and "哈希不一致" in problems[0]


def test_verify_manifest_missing(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    total, problems = hub.verify_manifest(empty)
    assert total == 0 and "manifest.json" in problems[0]


def test_config_resolve_asset_uses_hub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    pack = _make_pack(tmp_path)
    monkeypatch.delenv(hub.ENV_VAR, raising=False)
    config = Config.load(overrides={"app": {"assets_dir": str(pack)}})
    resolved = config.resolve_asset("Qwen2.5-0.5B-Instruct")
    assert resolved.is_relative_to(pack.resolve())
    assert (resolved / "tokenizer_config.json").exists()
    # 多轮预设：相对路径经 hub 解析
    resolved2 = config.resolve_asset("datasets/multiturn/dialogue.jsonl")
    assert resolved2.exists()


def test_env_var_resolves_without_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    pack = _make_pack(tmp_path)
    monkeypatch.setenv(hub.ENV_VAR, str(pack))
    config = Config.load()
    resolved = config.resolve_asset("Qwen2.5-0.5B-Instruct")
    assert resolved.is_relative_to(pack.resolve())
    monkeypatch.delenv(hub.ENV_VAR)


def test_doctor_reports_asset_pack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from ucm_accept.doctor import run_doctor

    pack = _make_pack(tmp_path)
    monkeypatch.delenv(hub.ENV_VAR, raising=False)
    config = Config.load(
        overrides={
            "app": {"assets_dir": str(pack), "report_dir": str(tmp_path / "outputs")},
        }
    )
    results = run_doctor(config, mock=True)
    names = {result.name: result for result in results}
    assert "资产包" in names
    assert str(pack.resolve()) in names["资产包"].detail
    assert names["资产包清单"].status == "ok"
    assert names["数据集缓存"].status == "ok"
    # tokenizer 名字经 hub 自动解析后应通过
    assert names["Tokenizer"].status == "ok"


def test_doctor_warns_without_pack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from ucm_accept.doctor import run_doctor

    monkeypatch.delenv(hub.ENV_VAR, raising=False)
    config = Config.load(overrides={"app": {"report_dir": str(tmp_path / "outputs")}})
    results = run_doctor(config, mock=True)
    pack_results = [result for result in results if result.name == "资产包"]
    assert pack_results and pack_results[0].status == "warn"
    # 无资产包时回退到内置多轮清单检查
    assert any(result.name == "离线资产" for result in results)


def test_prepare_assets_init_scaffold(tmp_path: Path):
    import subprocess
    import sys

    target = tmp_path / "pack"
    script = Path(__file__).resolve().parents[1] / "scripts" / "prepare_assets.py"
    result = subprocess.run(
        [sys.executable, str(script), "--assets-dir", str(target), "--init", "--seed-bundled"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    for name in ("tokenizers", "datasets/multiturn", "evalscope-cache", "modelscope-cache"):
        assert (target / name).is_dir()
    assert (target / "README.txt").exists()
    assert (target / "datasets" / "multiturn" / "dialogue.jsonl").exists()
    # 生成的清单可校验
    gen = subprocess.run(
        [sys.executable, str(script), "--assets-dir", str(target)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert gen.returncode == 0, gen.stderr
    check = subprocess.run(
        [sys.executable, str(script), "--assets-dir", str(target), "--check"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert check.returncode == 0, check.stdout + check.stderr


def test_asset_registry_extends_datasets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    pack = _make_pack(tmp_path)
    (pack / "datasets" / "registry.yaml").write_text(
        "accuracy:\n"
        "  datasets:\n"
        "    customer_qa:\n"
        "      label: 客户问答集\n"
        "      dataset: customer_qa\n"
        "      limit: 50\n"
        "      description: 客户自有业务问答集\n"
        "multiturn:\n"
        "  scenarios:\n"
        "    telecom:\n"
        "      label: 电信客服\n"
        "      description: 电信多轮工单场景\n"
        "      dataset_path: datasets/multiturn/telecom.jsonl\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(hub.ENV_VAR, str(pack))
    cfg = Config.load()
    ds = cfg.get("accuracy.datasets.customer_qa")
    assert ds["label"] == "客户问答集" and ds["limit"] == 50
    assert cfg.get("multiturn.scenarios.telecom.dataset_path") == "datasets/multiturn/telecom.jsonl"
    # 内置数据集不受影响
    assert cfg.get("accuracy.datasets.gsm8k.dataset") == "gsm8k"
    # 用户配置可覆盖注册表（禁用新数据集）
    user = tmp_path / "user.yaml"
    user.write_text("accuracy:\n  datasets:\n    customer_qa:\n      enabled: false\n", encoding="utf-8")
    cfg2 = Config.load(user)
    assert cfg2.get("accuracy.datasets.customer_qa.enabled") is False


def test_asset_registry_rejects_unknown_section(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from ucm_accept.config import ConfigError

    pack = _make_pack(tmp_path)
    (pack / "datasets" / "registry.yaml").write_text("perf:\n  number: 1\n", encoding="utf-8")
    monkeypatch.setenv(hub.ENV_VAR, str(pack))
    with pytest.raises(ConfigError):
        Config.load()


def test_evalscope_dataset_dir(tmp_path: Path):
    pack = _make_pack(tmp_path)
    assert hub.evalscope_dataset_dir(pack) == str((pack / "evalscope-cache").resolve())
    empty = tmp_path / "empty-pack"
    empty.mkdir()
    assert hub.evalscope_dataset_dir(empty) == ""


def test_accuracy_params_pass_dataset_dir(config: Config, fake_evalscope: Path, tmp_path: Path):
    """资产包 modelscope-cache 应注入 --dataset-dir（离线直读本地数据集）。"""
    from ucm_accept.engine.base import Endpoint
    from ucm_accept.engine.evalscope_engine import EvalScopeEngine
    from ucm_accept.orchestrator import Orchestrator

    pack = _make_pack(tmp_path)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv(hub.ENV_VAR, str(pack))
    try:
        config.set("evalscope.executable", str(fake_evalscope))
        config.set("app.assets_dir", str(pack))
        orchestrator = Orchestrator(config, EvalScopeEngine(config))
        params = orchestrator._accuracy_params("gsm8k", {"label": "数学", "dataset": "gsm8k"}, 1)
        assert params.dataset_dir == str((pack / "evalscope-cache").resolve())
        engine_argv = orchestrator.engine._accuracy_argv(
            Endpoint(base_url="http://127.0.0.1:8080/v1", model="m"),
            params,
            tmp_path / "out",
        )
        assert "--dataset-dir" in engine_argv
    finally:
        monkeypatch.undo()
