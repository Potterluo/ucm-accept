from __future__ import annotations

from pathlib import Path

import pytest

from ucm_accept.config import DEFAULT_CONFIG_PATH, Config, ConfigError, deep_merge


def test_default_config_loads(config: Config):
    assert config.get("schema_version") == 1
    assert config.get("endpoint.model")
    assert config.get("sla.mode") == "auto_tune"
    assert config.get("accuracy.runs") == 2
    assert config.source == DEFAULT_CONFIG_PATH or config.source.exists()


def test_partial_user_config_is_merged(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "endpoint:\n  base_url: http://10.0.0.1:9000/v1\n  model: test-model\n"
        "perf:\n  number: 12\n",
        encoding="utf-8",
    )
    cfg = Config.load(path)
    assert cfg.get("endpoint.base_url") == "http://10.0.0.1:9000/v1"
    assert cfg.get("perf.number") == 12
    assert cfg.get("sla.target.concurrency") == 200


def test_env_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UCM_TEST_URL", "http://127.0.0.1:9999/v1")
    path = tmp_path / "config.yaml"
    path.write_text(
        "endpoint:\n  base_url: ${UCM_TEST_URL}\n  model: ${UCM_MISSING:-fallback-model}\n",
        encoding="utf-8",
    )
    cfg = Config.load(path)
    assert cfg.get("endpoint.base_url") == "http://127.0.0.1:9999/v1"
    assert cfg.get("endpoint.model") == "fallback-model"


def test_missing_env_raises(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("endpoint:\n  base_url: ${UCM_NOT_SET_ANYWHERE}\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        Config.load(path)


def test_invalid_url_rejected():
    with pytest.raises(ConfigError):
        Config.load(overrides={"endpoint": {"base_url": "ftp://bad"}})


def test_invalid_sla_mode_rejected():
    with pytest.raises(ConfigError):
        Config.load(overrides={"sla": {"mode": "wrong"}})


def test_parallel_normalized_to_int_list():
    cfg = Config.load(overrides={"perf": {"parallel": ["10", "20"]}})
    assert cfg.get("perf.parallel") == [10, 20]


def test_deep_merge_lists_replace():
    merged = deep_merge({"a": {"b": [1, 2], "c": 1}}, {"a": {"b": [3], "d": 2}})
    assert merged == {"a": {"b": [3], "c": 1, "d": 2}}


def test_masked_api_key():
    cfg = Config.load(overrides={"endpoint": {"api_key": "secret-key"}})
    assert cfg.masked()["endpoint"]["api_key"] == "***"
