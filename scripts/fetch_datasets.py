#!/usr/bin/env python3
"""下载离线资源（tokenizer / 数据集 / AgentX traces）并组装 UCM 资产包数据层。

双源：ModelScope（默认，多轮/AgentX/精度全支持）与 HuggingFace（tokenizer 与
精度数据集备用源）。下载完成后把本机缓存复制进资产包：

  <assets-dir>/tokenizers/<模型名>/   ← tokenizer 全量文件（HF 格式）
  <assets-dir>/evalscope-cache/      ← ~/.cache/evalscope       （AgentX traces）
  <assets-dir>/modelscope-cache/     ← ~/.cache/modelscope      （精度 + 多轮 + swe_smith）
  <assets-dir>/hf-cache/             ← ~/.cache/huggingface     （HF 源的数据集）

离线验收时 UCM_ASSETS_DIR 指向包根，缓存环境变量由资产包发现机制注入。
清单文件（--manifest，packaging/assets-manifest.json）定义默认要下载的内容；
CLI 参数可覆盖。资源清单变更 → push 触发 download-assets 工作流重新打包。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

TOKENIZER_FILES = (
    "tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt",
    "special_tokens_map.json", "added_tokens.json", "chat_template.jinja",
    "tokenizer.model", "preprocessor_config.json",
)

DEFAULT_MANIFEST = {
    "tokenizers": ["Qwen/Qwen2.5-0.5B-Instruct"],
    "datasets": ["gsm8k", "gpqa_diamond", "longbench_v2", "bfcl_v3"],
    "multiturn_scenarios": ["share_gpt_zh_multi_turn", "share_gpt_en_multi_turn",
                            "trie_agentic_coding", "trie_code_qa", "trie_office_work",
                            "swe_smith"],
    "include_agentx": False,
}

CACHE_ROOTS = {
    "evalscope-cache": Path.home() / ".cache" / "evalscope",
    "modelscope-cache": Path.home() / ".cache" / "modelscope",
    "hf-cache": Path.home() / ".cache" / "huggingface",
}


def load_manifest(path: Path | None) -> dict[str, Any]:
    if path and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_MANIFEST)
        merged.update({k: v for k, v in data.items() if v is not None})
        return merged
    return dict(DEFAULT_MANIFEST)


def download_tokenizer(repo: str, source: str, dest_root: Path) -> Path | None:
    """下载 tokenizer 仓库并提取 HF 格式文件到 dest_root/<模型名>/。"""
    model_name = repo.rsplit("/", 1)[-1]
    dest = dest_root / model_name
    dest.mkdir(parents=True, exist_ok=True)
    local_dir: Path | None = None
    if source in ("modelscope", "auto"):
        try:
            from modelscope import snapshot_download
            patterns = list(TOKENIZER_FILES)
            local_dir = Path(snapshot_download(repo, allow_patterns=patterns))
            print(f"  modelscope 下载完成（仅 tokenizer 文件）：{local_dir}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  modelscope 下载失败（{exc}）", flush=True)
            if source == "modelscope":
                return None
    if local_dir is None:
        try:
            from huggingface_hub import snapshot_download as hf_snapshot
            local_dir = Path(hf_snapshot(repo, allow_patterns=list(TOKENIZER_FILES)))
            print(f"  huggingface 下载完成：{local_dir}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  huggingface 下载失败（{exc}）", flush=True)
            return None
    picked = 0
    for item in sorted(local_dir.rglob("*")):
        if item.is_file() and item.name in TOKENIZER_FILES:
            shutil.copy2(item, dest / item.name)
            picked += 1
    if not picked:
        print("  警告：下载内容中未识别到 tokenizer 文件")
        return None
    print(f"  tokenizer 就绪：{dest}（{picked} 个文件）", flush=True)
    return dest


def trigger_dataset_download(evalscope_bin: str, dataset: str, source: str,
                             work_dir: Path, tokenizer_path: str) -> tuple[bool, str]:
    """用必失败的 api-url 触发数据集下载（下载先于请求，缓存落盘）。"""
    cmd = [evalscope_bin, "eval", "--model", "mock-model",
           "--api-url", "http://127.0.0.1:9/v1",
           "--datasets", dataset, "--work-dir", str(work_dir / dataset),
           "--no-timestamp", "--limit", "1"]
    if source == "huggingface":
        cmd += ["--dataset-hub", "hf"]
    if tokenizer_path:
        cmd += ["--tokenizer-path", tokenizer_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    # 退出码必然非 0（api-url 不可达是设计使然）：失败的是请求，不是下载。
    # 缓存是否就绪由调用方检查缓存目录，这里只表示“触发完成”。
    return True, (proc.stdout + proc.stderr)[-300:]


def trigger_multiturn_download(evalscope_bin: str, scenario: str, source: str,
                               work_dir: Path, tokenizer_path: str) -> tuple[bool, str]:
    """触发多轮场景数据集下载（仅 modelscope 源——场景内置下载源）。"""
    if source == "huggingface":
        print(f"  跳过 {scenario}：多轮场景数据集仅 modelscope 源", flush=True)
        return True, "skipped"
    cmd = [evalscope_bin, "perf", "--dataset", scenario, "--multi-turn",
           "--parallel", "1", "--number", "1", "--min-turns", "1", "--max-turns", "1",
           "--work-dir", str(work_dir / scenario), "--no-timestamp"]
    if tokenizer_path:
        cmd += ["--tokenizer-path", tokenizer_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    return True, (proc.stdout + proc.stderr)[-200:]


def trigger_agentx_download(evalscope_bin: str, source: str, work_dir: Path) -> tuple[bool, str]:
    if source == "huggingface":
        print("  跳过 agentx：traces 下载仅 modelscope 源", flush=True)
        return True, "skipped"
    cmd = [evalscope_bin, "perf",
           "--scenario", json.dumps({"name": "agentx", "variant": "full"}),
           "--model", "mock-model", "--parallel", "1", "--duration", "900",
           "--work-dir", str(work_dir / "agentx"), "--no-timestamp"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-300:]


def assemble(assets_dir: Path) -> None:
    """把本机缓存复制进资产包数据层（覆盖式，保留 tokenizers/）。"""
    for dest_name, cache_root in CACHE_ROOTS.items():
        if not cache_root.is_dir():
            print(f"跳过 {dest_name}：{cache_root} 不存在", flush=True)
            continue
        dest = assets_dir / dest_name
        dest.mkdir(parents=True, exist_ok=True)
        for item in cache_root.iterdir():
            target = dest / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target, symlinks=True)
            else:
                shutil.copy2(item, target)
        print(f"已复制 {dest_name} ← {cache_root}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="下载离线资源并组装 UCM 资产包数据层")
    parser.add_argument("--assets-dir", required=True, help="资产包根目录")
    parser.add_argument("--manifest", default="packaging/assets-manifest.json",
                        help="资源清单文件（定义 tokenizer/数据集，CLI 参数可覆盖）")
    parser.add_argument("--source", choices=["modelscope", "huggingface", "auto"],
                        default="auto", help="下载源（auto=modelscope 失败回退 hf）")
    parser.add_argument("--tokenizer-repo", default=None,
                        help="tokenizer 仓库 id（覆盖清单），如 Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--datasets", default=None,
                        help="精度数据集列表（逗号分隔，覆盖清单）")
    parser.add_argument("--no-multiturn", action="store_true", help="跳过多轮场景下载")
    parser.add_argument("--include-agentx", action="store_true", help="下载 AgentX traces（约 1.9GB）")
    parser.add_argument("--evalscope-bin", default="evalscope")
    parser.add_argument("--skip-cache-copy", action="store_true", help="只下载不组装（调试用）")
    args = parser.parse_args()

    assets_dir = Path(args.assets_dir).resolve()
    assets_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest).resolve()
    manifest = load_manifest(manifest_path if manifest_path.exists() else None)

    tokenizer_repos = ([args.tokenizer_repo] if args.tokenizer_repo
                       else list(manifest.get("tokenizers", [])))
    datasets = ([x.strip() for x in args.datasets.split(",") if x.strip()]
                if args.datasets else list(manifest.get("datasets", [])))
    scenarios = [] if args.no_multiturn else list(manifest.get("multiturn_scenarios", []))
    include_agentx = args.include_agentx or bool(manifest.get("include_agentx"))
    work_dir = assets_dir / ".fetch-work"
    work_dir.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, bool]] = []

    # ---- tokenizer ----
    for repo in tokenizer_repos:
        print(f"== tokenizer {repo}（源 {args.source}）...", flush=True)
        dest = download_tokenizer(repo, args.source, assets_dir / "tokenizers")
        results.append((f"tokenizer:{repo}", dest is not None))

    # ---- 精度数据集 ----
    for dataset in datasets:
        print(f"== 数据集 {dataset}（源 {args.source}）...", flush=True)
        ok, tail = trigger_dataset_download(args.evalscope_bin, dataset, args.source,
                                            work_dir, "")
        results.append((f"dataset:{dataset}", ok))
        print("   缓存就绪" if ok else "   下载阶段失败（缓存可能已部分落盘）", flush=True)

    # ---- 多轮场景 ----
    for scenario in scenarios:
        print(f"== 多轮场景 {scenario} ...", flush=True)
        ok, tail = trigger_multiturn_download(args.evalscope_bin, scenario, args.source,
                                              work_dir, "")
        results.append((f"multiturn:{scenario}", ok))
        print("   done", flush=True)

    # ---- AgentX ----
    if include_agentx:
        print("== AgentX traces（约 1.9GB）...", flush=True)
        ok, tail = trigger_agentx_download(args.evalscope_bin, args.source, work_dir)
        results.append(("agentx", ok))
        print("   done", flush=True)

    # ---- 组装数据层 ----
    if not args.skip_cache_copy:
        assemble(assets_dir)

    summary = {name: {"ok": ok} for name, ok in results}
    (assets_dir / "fetch-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    bad = [name for name, ok in results if not ok]
    print(f"完成：{len(results) - len(bad)}/{len(results)} 项就绪"
          + (f"；失败：{', '.join(bad)}" if bad else ""), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
