#!/usr/bin/env python3
"""生成 GitHub Pages 完整操作指南站点（Windows 视角，Apple 风格）。

流程全部真实走通（mock 模式，不产生真实外呼）：
    1. Release 页下载徽标表（可选，--release-url 提供时截取）
    2. 资产包准备：prepare_assets 生成真实资产包并打 tar.gz
    3. GUI 首页 → 齿轮「离线资产包」→ 填路径导入并校验
    4. 展开项内配置 → 执行验收（运行态截图）→ 结论与结果页
    5. 报告 HTML

产物（--out 目录）：
    index.html            完整操作指南
    screenshots/*.png     各步骤截图
    guide-pack/           演示用资产包（不入站点）
"""

from __future__ import annotations

import argparse
import http.client
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8321
BASE_URL = f"http://127.0.0.1:{PORT}"


def wait_ready(seconds: int = 60) -> bool:
    for _ in range(seconds // 2):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=3)
            conn.request("GET", "/")
            conn.getresponse().read()
            conn.close()
            return True
        except OSError:
            time.sleep(2)
    return False


def prepare_guide_pack(out_dir: Path) -> tuple[Path, Path]:
    """生成演示用真实资产包（含 manifest）及其 tar.gz，返回 (pack_root, tar_path)。"""
    pack = out_dir / "guide-pack"
    pack.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "scripts/prepare_assets.py", "--assets-dir", str(pack),
         "--init", "--seed-bundled"],
        cwd=str(ROOT), check=True, capture_output=True,
    )
    subprocess.run(
        [sys.executable, "scripts/prepare_assets.py", "--assets-dir", str(pack),
         "--output", str(pack / "manifest.json")],
        cwd=str(ROOT), check=True, capture_output=True,
    )
    tar_path = out_dir / "ucm-assets-guide.tar.gz"
    if tar_path.exists():
        tar_path.unlink()
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(pack, arcname=".")
    return pack, tar_path


def capture(out_dir: Path, tar_path: Path, release_url: str) -> list[dict]:
    from playwright.sync_api import sync_playwright

    shots_dir = out_dir / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    pages: list[dict] = []

    def shot(name: str, caption: str, full: bool = False) -> None:
        path = shots_dir / f"{name}.png"
        page.screenshot(path=str(path), full_page=full)
        pages.append({"file": f"screenshots/{name}.png", "caption": caption})
        print(f"  截图 {name}", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1080}, device_scale_factor=1.5)

        # 1. Release 下载页（真实 GitHub 页面，失败则跳过不阻塞）
        if release_url:
            try:
                page.goto(release_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)
                shot("release", "① Release 页下载 — 按 OS 徽标点击即下载（Windows 选 zip）")
            except Exception as exc:  # noqa: BLE001
                print(f"  release 截图跳过：{exc}", flush=True)

        # 2. GUI 首页
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_selector(".hero", timeout=30000)
        page.wait_for_timeout(2500)
        shot("home", "② 双击 ucm-accept.exe 打开验收菜单，输入 G 启动浏览器 GUI，填服务地址与模型")

        # 3. 齿轮 → 离线资产包（初始状态）
        page.click("button.gear")
        page.wait_for_timeout(1200)
        page.locator("#assets-status").scroll_into_view_if_needed()
        page.wait_for_timeout(600)
        shot("assets-status", "③ 资产包状态 — 齿轮面板查看校验结果与内置 tokenizer")

        # 4. 导入并校验（填 tar.gz 路径，真实走导入流程）
        page.fill("#assets-path", str(tar_path))
        page.click("text=导入并校验")
        page.wait_for_timeout(4000)
        page.locator("#assets-result").scroll_into_view_if_needed()
        shot("assets-import", "④ 导入资源包 — 填 tar.gz / part-00 分卷路径，一键合并·解压·SHA256 校验")

        # 5. 展开项内配置
        page.locator("#item-multiturn button.link").first.click()
        page.wait_for_timeout(900)
        page.locator("#item-multiturn").scroll_into_view_if_needed()
        shot("item-config", "⑤ 每项配置 — 行内「配置」展开，改完即生效")

        # 6. 执行验收：运行态
        page.click("text=执行勾选的验收测试")
        page.wait_for_timeout(2500)
        shot("running", "⑥ 执行验收 — 运行中：进度、日志实时滚动（mock 演示模式）")

        # 7. 结论卡（等待 verdict 出现结论文本）
        for _ in range(300):
            verdict = page.locator(".verdict").inner_text()
            if ("通过" in verdict or "未完成" in verdict) and "执行" not in verdict[:6]:
                break
            page.wait_for_timeout(1000)
        page.wait_for_timeout(1500)
        page.locator(".verdict").scroll_into_view_if_needed()
        shot("result", "⑦ 验收结论 — 结论、各项状态与耗时一览")

        # 8. 报告 HTML
        page.wait_for_timeout(800)
        shot("report", "⑧ 完整报告 — 自包含 HTML，支持导出 PDF，离线归档分发", full=True)

        browser.close()
    return pages


def write_index(out_dir: Path, pages: list[dict], release_url: str) -> None:
    by_file = {p["file"]: p["caption"] for p in pages}

    def has(name: str) -> bool:
        return any(k.endswith(f"/{name}.png") for k in by_file)

    def fig(name: str, extra: str = "") -> str:
        key = next((k for k in by_file if k.endswith(f"/{name}.png")), "")
        if not key:
            return ""
        cap = by_file[key]
        return (f'<figure {extra}><img src="{key}" alt="{cap}" loading="lazy">'
                f"<figcaption>{cap}</figcaption></figure>")

    release_href = release_url or "#"
    steps_html = f"""
<div class="step"><div class="num">1</div><div class="body">
  <h2>下载</h2>
  <p>打开 <a href="{release_href}">Releases · v1.3.0</a>，按操作系统点徽标下载。Windows 64 位选
  <code>ucm-accept-windows-x64.zip</code>，解压到任意目录（免安装）。</p>
  {fig("release")}
  <aside>Linux 用户另有 tar.gz / deb / rpm；内网环境请同时下载「离线资产包」分卷
  <code>ucm-assets-*.tar.gz.part-00/01</code> 与 <code>SHA256SUMS</code>。</aside>
</div></div>

<div class="step"><div class="num">2</div><div class="body">
  <h2>启动 GUI</h2>
  <p>双击 <code>ucm-accept.exe</code> 打开<b>验收菜单</b>（交互式 CLI），输入 <code>G</code> 即可启动浏览器 GUI（菜单内所有配置与 GUI 实时互通）。首页填被测服务的
  <b>服务地址</b>（如 <code>http://127.0.0.1:8000/v1</code>）与 <b>模型名称</b>（--served-model-name），
  点「检测连通」验证上下文窗口。</p>
  {fig("home")}
</div></div>

<div class="step"><div class="num">3</div><div class="body">
  <h2>导入离线资源包</h2>
  <p>内网环境必做。右上角 <b>⚙ 齿轮</b> → 「离线资产包」→ 填入资源包路径
  （<code>tar.gz</code>、<code>part-00</code> 分卷或已解压目录均可）→ 点「导入并校验」。
  分卷合并、解压、SHA256 校验一步完成，校验通过后当前会话即时生效，内置 tokenizer 下拉自动刷新。</p>
  {fig("assets-status")}
  {fig("assets-import")}
  <aside>Windows 上全程零命令行；命令行用户可按 Release 页的 PowerShell 三步操作
  （copy /b 合并 → Get-FileHash 校验 → tar 解压）。</aside>
</div></div>

<div class="step"><div class="num">4</div><div class="body">
  <h2>配置并执行</h2>
  <p>每个测试项行内「配置」可展开单项参数（并发档位、多轮场景、SLA 探测区间、精度数据集与样本上限等），
  改完即生效。勾选要执行的测试项，点「执行勾选的验收测试」——进度与日志实时滚动，可随时「停止当前任务」，
  已产生数据不会丢失。</p>
  {fig("item-config")}
  {fig("running")}
</div></div>

<div class="step"><div class="num">5</div><div class="body">
  <h2>查看结果</h2>
  <p>跑完自动出<b>验收结论</b>（通过 / 有条件通过 / 不通过）与各项耗时摘要；报告区为自包含 HTML，
  点「导出 HTML / 导出 PDF」归档分发。所有判定由 EvalScope 原生引擎执行，报告内附原始数据路径。</p>
  {fig("result")}
  {fig("report")}
</div></div>
"""
    steps_html = f'<section id="steps">{steps_html}</section>' if has("home") else ""

    (out_dir / "index.html").write_text(
        f"""<!DOCTYPE html>
<html lang="zh_CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UCM 验收工具 · 操作指南（Windows）</title>
<style>
  :root {{ --blue:#0071e3; --ink:#1d1d1f; --muted:#86868b; --line:#e8e8ed; }}
  body {{ margin:0; background:#f5f5f7; color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
         -webkit-font-smoothing:antialiased; }}
  nav {{ position:sticky; top:0; background:rgba(255,255,255,.85); backdrop-filter:blur(14px);
        border-bottom:1px solid var(--line); z-index:10; }}
  nav div {{ max-width:1080px; margin:0 auto; padding:14px 16px; display:flex; gap:22px;
             font-size:13px; font-weight:600; }}
  nav a {{ color:var(--ink); text-decoration:none; opacity:.85 }}
  nav a:hover {{ color:var(--blue); opacity:1 }}
  header {{ max-width:1080px; margin:0 auto; padding:64px 16px 8px; }}
  header .eyebrow {{ font-size:12px; letter-spacing:.18em; color:var(--muted); font-weight:600;
                     text-transform:uppercase; }}
  header h1 {{ margin:10px 0 6px; font-size:44px; font-weight:700; letter-spacing:-.02em; }}
  header p {{ margin:0; color:var(--muted); font-size:16px; line-height:1.6 }}
  header .cta {{ display:inline-block; margin-top:18px; background:var(--blue); color:#fff;
                 padding:12px 26px; border-radius:999px; text-decoration:none; font-size:15px }}
  main {{ max-width:1080px; margin:12px auto 0; padding:0 16px 40px }}
  .step {{ display:flex; gap:22px; margin:56px 0; }}
  .num {{ flex:0 0 44px; height:44px; border-radius:50%; background:var(--blue); color:#fff;
          display:flex; align-items:center; justify-content:center; font-size:19px; font-weight:700;
          box-shadow:0 6px 16px rgba(0,113,227,.25) }}
  .body {{ flex:1; min-width:0 }}
  .body h2 {{ margin:6px 0 10px; font-size:24px; letter-spacing:-.01em }}
  .body p {{ margin:0 0 14px; color:#424245; font-size:15px; line-height:1.7 }}
  .body code {{ background:rgba(0,113,227,.08); color:#003a8c; border-radius:6px; padding:2px 7px;
                font-family:"SF Mono",ui-monospace,Consolas,monospace; font-size:12.5px }}
  .body aside {{ background:#fff; border:1px solid var(--line); border-left:3px solid var(--blue);
                 border-radius:12px; padding:12px 16px; font-size:13px; color:var(--muted); margin-top:12px }}
  figure {{ margin:18px 0 0; background:#fff; border-radius:20px; overflow:hidden;
            box-shadow:0 4px 12px rgba(0,0,0,.05) }}
  figure img {{ width:100%; display:block }}
  figcaption {{ padding:11px 18px; font-size:12.5px; color:var(--muted); border-top:1px solid var(--line) }}
  footer {{ text-align:center; color:var(--muted); font-size:12px; padding:26px 16px 40px }}
</style>
</head>
<body>
<nav><div>
  <a href="#top">UCM 验收工具</a><a href="#steps">操作步骤</a>
  <a href="{release_href}">Releases</a><a href="https://github.com/ucm-system/ucm-accept">GitHub</a>
</div></nav>
<header id="top">
  <div class="eyebrow">UCM Inference Acceleration · Acceptance Guide</div>
  <h1>五分钟完成推理加速验收</h1>
  <p>以下步骤以 Windows 为例，全部截图来自真实操作（mock 演示模式，不产生真实请求）。
  下载、导入资源包、执行测试、查看结果——每一步都可照抄。</p>
  <a class="cta" href="{release_href}">前往 Releases 下载</a>
</header>
<main>
{steps_html}
{("" if has("home") else "<p style='color:#86868b'>截图生成中，稍后刷新本页。</p>")}
</main>
<footer>ucm-accept v1.3.0 · GitHub Pages 自动发布 · 所有测试由 EvalScope 原生引擎执行</footer>
</body>
</html>
""",
        encoding="utf-8",
    )
    print(f"index.html 已生成（{len(pages)} 张截图）", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 GitHub Pages 操作指南站点")
    parser.add_argument("--out", default="site", help="站点输出目录")
    parser.add_argument("--release-url", default="",
                        help="Releases 页地址（提供时截取下载页截图）")
    args = parser.parse_args()
    out_dir = Path(args.out).resolve()

    print("准备演示资产包…", flush=True)
    pack, tar_path = prepare_guide_pack(out_dir)

    gui = subprocess.Popen(
        [sys.executable, "-m", "ucm_accept", "--gui", "--mock", "--no-browser",
         "--port", str(PORT), "--outputs", str(out_dir / "outputs")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(ROOT),
        env={**dict(__import__("os").environ), "UCM_ASSETS_DIR": str(pack)},
    )
    try:
        if not wait_ready():
            print(f"GUI 未在 {BASE_URL} 就绪", file=sys.stderr)
            return 1
        try:
            pages = capture(out_dir, tar_path, args.release_url)
        finally:
            subprocess.run(["taskkill", "/F", "/PID", str(gui.pid)] if sys.platform == "win32"
                           else ["kill", str(gui.pid)], capture_output=True)
    finally:
        if gui.poll() is None:
            gui.terminate()
    write_index(out_dir, pages, args.release_url)
    print(f"站点已生成：{out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
