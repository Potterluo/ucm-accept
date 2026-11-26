#!/usr/bin/env python3
"""生成 Release 说明：按 OS 下载的徽标表格 + Docker 拉取 + 离线资源包。

用法：python scripts/gen_release_notes.py --tag v1.2.0 --repo Potterluo/ucm-accept \
        --image ghcr.io/potterluo/ucm-accept --output notes.md
"""

from __future__ import annotations

import argparse

COLORS = {
    "windows": "0078D4",
    "linux": "F0B429",
    "apple": "0071e3",
    "docker": "2496ED",
    "python": "3776AB",
    "assets": "E8833A",
    "grey": "6E6E73",
}

LOGOS = {"windows": "windows", "linux": "linux", "docker": "docker",
         "python": "python", "assets": ""}


def _esc(text: str) -> str:
    """shields.io 徽标文本转义：- → --，_ → __，空格 → %20。"""
    return text.replace("-", "--").replace("_", "__").replace(" ", "%20")


def badge(label: str, message: str, kind: str, target: str) -> str:
    color = COLORS[kind]
    logo = LOGOS.get(kind, "")
    logo_q = f"?logo={logo}&logoColor=white" if logo else ""
    url = f"https://img.shields.io/badge/{_esc(label)}-{_esc(message)}-{color}{logo_q}"
    return f"[![{label} {message}]({url})]({target})"


def build_notes(tag: str, repo: str, image: str) -> str:
    version = tag.removeprefix("v")
    base = f"https://github.com/{repo}/releases/download/{tag}"
    lines: list[str] = []
    add = lines.append

    add("### 按 OS 下载 / Download based on your OS")
    add("")
    add("| 平台 | 架构 | 下载 |")
    add("|---|---|---|")
    add(f"| Windows | x64 | {badge('Windows x64', 'zip', 'windows', f'{base}/ucm-accept-windows-x64.zip')} |")
    add(f"| Windows | ARM64 | {badge('Windows ARM64', 'zip mock', 'windows', f'{base}/ucm-accept-windows-arm64.zip')} |")
    add(f"| Linux | amd64 | {badge('Linux amd64', 'tar.gz', 'linux', f'{base}/ucm-accept-linux-amd64.tar.gz')} "
        f"{badge('deb', 'amd64', 'linux', f'{base}/ucm-accept_{version}_amd64.deb')} "
        f"{badge('rpm', 'x86_64', 'linux', f'{base}/ucm-accept-{version}-1.x86_64.rpm')} |")
    add(f"| Linux | ARM64 | {badge('Linux ARM64', 'tar.gz', 'linux', f'{base}/ucm-accept-linux-arm64.tar.gz')} "
        f"{badge('deb', 'arm64', 'linux', f'{base}/ucm-accept_{version}_arm64.deb')} "
        f"{badge('rpm', 'aarch64', 'linux', f'{base}/ucm-accept-{version}-1.aarch64.rpm')} |")
    add("| Python | any | {} {} |".format(
        badge('Wheel', 'py3-none-any', 'python', f'{base}/ucm_accept-{version}-py3-none-any.whl'),
        badge('sdist', 'tar.gz', 'python', f'{base}/ucm_accept-{version}.tar.gz')))
    add("")
    add("> Windows ARM64 为 mock 预览版：pyarrow 不提供 win_arm64 轮子，EvalScope 引擎无法内置；"
        "真实验收请使用 Windows x64 或 Linux 版。")
    add("")

    add("### Docker 镜像（多架构，amd64 / arm64 自动匹配）")
    add("")
    add("```bash")
    add(f"docker pull {image}:{version}")
    add("")
    add("# 单架构 / 离线加载（release 附带 docker save 导出包；若带 .part-00 分卷，先 cat 合并再 load）")
    add(f"docker load -i ucm-accept-{version}-amd64.tar.gz")
    add(f"docker load -i ucm-accept-{version}-arm64.tar.gz")
    add("```")
    add("")

    add("### 离线资源包（UCM Accept 无感使用）")
    add("")
    add(f"{badge('Offline Asset Pack', f'{version} part-00+ 合并', 'assets', f'{base}/ucm-assets-{version}.tar.gz.part-00')} "
        f"{badge('SHA256', 'merged checksum', 'grey', f'{base}/ucm-assets-{version}.tar.gz.sha256')}")
    add("")
    add("包含 16 个 tokenizer、精度数据集、多轮场景与 AgentX traces（约 5GB）。"
        "超 2GiB 由 CI 自动分卷（GitHub Release 单文件上限），合并校验后解压，"
        "再把 `UCM_ASSETS_DIR` 指向解压目录即可离线运行全部验收项：")
    add("")
    add("```bash")
    add(f"cat ucm-assets-{version}.tar.gz.part-* > ucm-assets-{version}.tar.gz")
    add(f"sha256sum -c ucm-assets-{version}.tar.gz.sha256")
    add(f"tar -xzf ucm-assets-{version}.tar.gz -C ~/ucm-assets")
    add("UCM_ASSETS_DIR=~/ucm-assets ucm-accept --doctor --mock   # 校验 SHA256 与就绪状态")
    add("```")
    add("")

    add("### 离线工具链（现场无外网安装用）")
    add("")
    add(f"{badge('Wheelhouse', 'amd64', 'grey', f'{base}/ucm-accept-offline-tooling-{version}-amd64.tar.gz')} "
        f"{badge('Wheelhouse', 'arm64', 'grey', f'{base}/ucm-accept-offline-tooling-{version}-arm64.tar.gz')}")
    add("")
    add("全部产物 SHA256 见 `SHA256SUMS`。所有测试均由 EvalScope 原生引擎执行，"
        "本工具不做任何自研判定口径。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Release 徽标下载说明")
    parser.add_argument("--tag", required=True, help="tag 名，如 v1.2.0")
    parser.add_argument("--repo", required=True, help="仓库全名，如 Potterluo/ucm-accept")
    parser.add_argument("--image", required=True, help="镜像名，如 ghcr.io/potterluo/ucm-accept")
    parser.add_argument("--output", required=True, help="输出 markdown 文件")
    args = parser.parse_args()
    notes = build_notes(args.tag, args.repo, args.image)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(notes)
    print(f"release notes → {args.output}（{len(notes)} 字符）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
