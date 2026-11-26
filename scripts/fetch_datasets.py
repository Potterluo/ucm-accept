#!/usr/bin/env python3
"""联网预热 EvalScope 数据集缓存，并组装离线资产包的数据层。

原理：用 `evalscope eval/perf` 指向一个不存在的 api-url 触发数据集下载
（下载发生在评测请求之前，请求失败不影响缓存落盘），然后把
~/.cache 下的三类缓存复制进资产包：

  <assets-dir>/evalscope-cache/   ← ~/.cache/evalscope        （AgentX traces）
  <assets-dir>/modelscope-cache/  ← ~/.cache/modelscope/{hub/datasets,datasets}
                                     （精度数据集 + 多轮场景 + swe_smith）

离线验收时 UCM_ASSETS_DIR 指向该资产包，EVALSCOPE_CACHE / MODELSCOPE_CACHE
由资产包发现机制自动注入，全部命中本地缓存。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ACCURACY_DATASETS = ["gsm8k", "gpqa_diamond", "longbench_v2", "bfcl_v3"]
MULTITURN_SCENARIOS = ["share_gpt_zh_multi_turn", "share_gpt_en_multi_turn",
                       "trie_agentic_coding", "trie_code_qa", "trie_office_work"]
LIVE_DATASETS = ["swe_smith"]

CACHE_ROOTS = {
    "evalscope-cache": Path.home() / ".cache" / "evalscope",
    "modelscope-cache": Path.home() / ".cache" / "modelscope",
}


def trigger_download(evalscope_bin: str, dataset_args: list[str], work_dir: Path,
                     tokenizer_path: str) -> tuple[bool, str]:
    """用一个必然失败的 api-url 触发数据集下载（下载先于请求，缓存落盘后失败退出）。"""
    cmd = [evalscope_bin, "eval", "--model", "mock-model",
           "--api-url", "http://127.0.0.1:9/v1",
           *dataset_args, "--work-dir", str(work_dir),
           "--no-timestamp", "--limit", "1"]
    if tokenizer_path:
        cmd += ["--tokenizer-path", tokenizer_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-400:]


def main() -> int:
    parser = argparse.ArgumentParser(description="预热 EvalScope 数据集缓存（离线资产包数据层）")
    parser.add_argument("--assets-dir", required=True, help="资产包根目录")
    parser.add_argument("--datasets", default="all",
                        help="all / accuracy / multiturn / agentx / 逗号分隔的单项名")
    parser.add_argument("--evalscope-bin", default="evalscope")
    parser.add_argument("--tokenizer-path", default="",
                        help="传给 evalscope 的 tokenizer（多轮 live 场景需要）")
    parser.add_argument("--include-agentx", action="store_true",
                        help="额外下载 AgentX traces（约 1.9GB）")
    args = parser.parse_args()

    assets_dir = Path(args.assets_dir).resolve()
    work_dir = assets_dir / ".fetch-work"
    work_dir.mkdir(parents=True, exist_ok=True)

    wanted = args.datasets.lower()
    tasks: list[tuple[str, list[str]]] = []
    if wanted in ("all", "accuracy") or "gsm8k" in wanted:
        for ds in ACCURACY_DATASETS:
            tasks.append((ds, ["--datasets", ds]))
    if wanted in ("all", "multiturn") or any(s in wanted for s in MULTITURN_SCENARIOS[:1]):
        for scenario in MULTITURN_SCENARIOS:
            tasks.append((scenario, [
                "--dataset", scenario, "--multi-turn",
                "--parallel", "1", "--number", "1", "--min-turns", "1", "--max-turns", "1",
            ]))
    if wanted in ("all", "multiturn") or "swe_smith" in wanted:
        tasks.append(("swe_smith", [
            "--dataset", "swe_smith", "--multi-turn", "--parallel", "1", "--number", "1",
            "--min-turns", "5", "--max-turns", "5",
        ]))

    results = []
    for name, dataset_args in tasks:
        print(f"== 预热 {name} ...", flush=True)
        ok, tail = trigger_download(args.evalscope_bin, dataset_args, work_dir / name,
                                    args.tokenizer_path)
        results.append((name, ok, tail))
        print(f"   {'ok' if ok else 'done-with-errors'}（缓存已尽力落盘）", flush=True)

    if args.include_agentx or wanted in ("all", "agentx"):
        print("== 预热 agentx（traces 约 1.9GB）...", flush=True)
        ok, tail = trigger_download(
            args.evalscope_bin,
            ["--scenario", json.dumps({"name": "agentx", "variant": "full"}),
             "--model", "mock-model", "--parallel", "1", "--duration", "900"],
            work_dir / "agentx", args.tokenizer_path)
        results.append(("agentx", ok, tail))
        print("   done-with-errors（缓存已尽力落盘）", flush=True)

    # ---- 组装数据层 ----
    for dest_name, cache_root in CACHE_ROOTS.items():
        if not cache_root.is_dir():
            print(f"跳过 {dest_name}：{cache_root} 不存在")
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
        print(f"已复制 {dest_name} ← {cache_root}")

    summary = {name: {"ok": ok, "tail": tail[-200:]} for name, ok, tail in results}
    (assets_dir / "fetch-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"汇总写入 {assets_dir / 'fetch-summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
