#!/usr/bin/env python3
"""生成 / 校验离线资产清单（SHA256）。

本脚本不下载数据。数据集与 tokenizer 由构建机通过 EvalScope / ModelScope 预热后，
放入固定目录；本脚本负责把实际文件固化成可校验清单，供现场 doctor 和安装包使用。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_NAMES = {"manifest.json", ".DS_Store"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(relative: Path) -> str:
    text = str(relative).replace("\\", "/")
    if text.startswith("tokenizers/"):
        return "tokenizer"
    if "evalscope-cache" in text or "modelscope-cache" in text:
        return "dataset-cache"
    if text.endswith(".jsonl"):
        return "dataset"
    return "other"


def validate_jsonl(path: Path) -> None:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number} 不是合法 JSON：{exc}") from exc


def collect(assets_dir: Path) -> list[dict]:
    items = []
    for path in sorted(assets_dir.rglob("*")):
        if not path.is_file() or path.name in SKIP_NAMES:
            continue
        relative = path.relative_to(assets_dir)
        if relative.parts and relative.parts[0] == "wheelhouse":
            continue
        if path.suffix == ".jsonl":
            validate_jsonl(path)
        size = path.stat().st_size
        if size == 0:
            raise ValueError(f"资产为空文件：{relative}")
        items.append(
            {
                "path": str(relative).replace("\\", "/"),
                "sha256": sha256(path),
                "size": size,
                "category": classify(relative),
            }
        )
    return items


def write_manifest(assets_dir: Path, output: Path) -> int:
    assets = collect(assets_dir)
    if not assets:
        print(f"错误：{assets_dir} 下没有可打包资产", file=sys.stderr)
        return 2
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "ucm-accept/scripts/prepare_assets.py",
        "note": "离线资产 SHA256 清单；不要手工修改。",
        "assets": assets,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = sum(item["size"] for item in assets)
    print(f"已写入 {output}：{len(assets)} 个文件，{total / 1024 / 1024:.1f} MiB")
    return 0


def check_manifest(assets_dir: Path, manifest_path: Path) -> int:
    if not manifest_path.exists():
        print(f"错误：清单不存在：{manifest_path}", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    for item in manifest.get("assets", []):
        path = assets_dir / item["path"]
        if not path.exists():
            failures.append(f"缺失：{item['path']}")
            continue
        if item.get("sha256") and sha256(path) != item["sha256"]:
            failures.append(f"哈希不一致：{item['path']}")
    if failures:
        print("资产校验失败：", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"资产校验通过：{len(manifest.get('assets', []))} 个文件")
    return 0


def seed_bundled(assets_dir: Path) -> None:
    """把包内置的多轮预设复制到 assets/datasets，便于统一打包。"""
    source = ROOT / "ucm_accept" / "resources" / "datasets"
    target = assets_dir / "datasets"
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if path.is_file():
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    print(f"已复制内置多轮预设到 {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 / 校验 UCM 离线资产清单")
    parser.add_argument("--assets-dir", default="assets", help="资产根目录")
    parser.add_argument("--output", default="", help="manifest.json 输出路径")
    parser.add_argument("--check", action="store_true", help="按清单校验现有资产")
    parser.add_argument("--seed-bundled", action="store_true", help="复制内置多轮预设")
    args = parser.parse_args()
    assets_dir = Path(args.assets_dir).resolve()
    manifest = Path(args.output).resolve() if args.output else assets_dir / "manifest.json"
    if args.seed_bundled:
        seed_bundled(assets_dir)
    if args.check:
        return check_manifest(assets_dir, manifest)
    return write_manifest(assets_dir, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
