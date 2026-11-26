"""离线资产包导入：分卷自动合并 → 安全解压 → manifest 校验 → 运行时生效。

CLI（[P] 资产包）与 GUI（齿轮面板「离线资产包」）共用，Windows / Linux 行为一致。
"""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path
from typing import Any

from .assets import verify_manifest

PART_SUFFIX = ".part-"
DEFAULT_EXTRACT_DIR = Path.home() / "ucm-assets"


def merge_parts(source: Path) -> Path:
    """把 ``<name>.part-00/01/…`` 分卷合并为 ``<name>``；完整文件已存在则复用。"""
    merged = source.parent / source.name.rsplit(PART_SUFFIX, 1)[0]
    if merged.exists():
        return merged
    parts = sorted(source.parent.glob(merged.name + PART_SUFFIX + "*"))
    if not parts:
        raise FileNotFoundError(f"未找到分卷文件：{merged.name}{PART_SUFFIX}*")
    with open(merged, "wb") as out:
        for part in parts:
            with open(part, "rb") as chunk:
                shutil.copyfileobj(chunk, out)
    return merged


def safe_extract(tar_path: Path, dest: Path) -> Path:
    """解压 tar.gz 到 dest（拒绝压缩包内路径越界），返回解压根目录。"""
    dest = dest.resolve()
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if not str(target).startswith(str(dest)):
                raise tarfile.TarError(f"压缩包内路径越界：{member.name}")
        tar.extractall(dest)
    return dest


def import_asset_pack(config: Any, raw: str) -> dict[str, Any]:
    """按路径导入资产包并写入 ``app.assets_dir``（仅校验通过时生效）。

    支持三种输入：已解压目录 / ``tar.gz`` / ``part-00`` 分卷（自动合并同目录分卷）。
    返回 ``{"hub", "total", "problems"}``；problems 非空表示校验未通过。
    """
    source = Path(str(raw).strip()).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"路径不存在：{source}")
    if PART_SUFFIX in source.name and source.is_file():
        source = merge_parts(source)
    if source.is_dir():
        hub = source
    elif source.is_file() and source.name.endswith((".tar.gz", ".tgz")):
        dest = DEFAULT_EXTRACT_DIR
        dest.mkdir(parents=True, exist_ok=True)
        hub = safe_extract(source, dest)
    else:
        raise ValueError("不支持的类型：请提供 tar.gz / part-00 分卷 / 已解压目录")
    total, problems = verify_manifest(hub)
    if not problems:
        config.set("app.assets_dir", str(hub))
    return {"hub": str(hub), "total": total, "problems": problems}
