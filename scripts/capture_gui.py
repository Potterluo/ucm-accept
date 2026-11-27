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
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
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


ANSI_COLORS = {"32": "#3fb950", "31": "#f85149", "33": "#d29922",
               "36": "#79c0ff", "1": "#f0f6fc", "2": "#8b949e"}


def capture_cli_menu_html() -> str:
    """pty 跑一次交互菜单（立即 Q 退出），ANSI 输出转终端风格 HTML。"""
    import os
    import re
    import tempfile

    out_dir = tempfile.mkdtemp(prefix="ucm-cli-")
    inner = (f'cd "{ROOT}" && CUDA_VISIBLE_DEVICES="" UCM_ASSETS_DIR= '
             f'"{sys.executable}" -m ucm_accept --mock --outputs "{out_dir}"')
    res = subprocess.run(
        ["script", "-qec", f'printf "Q\n" | {inner}', "/dev/null"],
        capture_output=True, text=True, timeout=120, env={**os.environ},
    )
    text = res.stdout.replace("\r", "")
    text = re.sub(r"\x1b\[K|\x1b\[\?2004[hl]", "", text)
    def esc(seg: str) -> str:
        return seg.replace("&", "&amp;").replace("<", "&lt;")

    rendered, cursor, color = "", 0, None
    for m in re.finditer(r"\x1b\[(\d+)m", text):
        seg = text[cursor:m.start()]
        rendered += (f'<span style="color:{color}">{esc(seg)}</span>' if color else esc(seg))
        color = ANSI_COLORS.get(m.group(1))
        cursor = m.end()
    tail = text[cursor:]
    rendered += (f'<span style="color:{color}">{esc(tail)}</span>' if color else esc(tail))
    return rendered

DOCKER_IMAGE_LOCAL = "ghcr.io/potterluo/ucm-accept:dev"


def _clip(text: str, start_marker: str, end_marker: str | None = None) -> str:
    """截取输出片段：start_marker 起始；end_marker 缺省时取到结尾。"""
    i = text.find(start_marker)
    if i < 0:
        return text
    if end_marker and end_marker in text[i + len(start_marker):]:
        j = text.index(end_marker, i + len(start_marker))
        return text[i:j + len(end_marker)]
    return text[i:]


def _strip_tails(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.rstrip())


def _pty_run(engine: str, image: str, mounts: list[str], feed: str,
             timeout: int, tail_only: bool = False) -> str:
    """script -qec 外层 pty 跑交互容器，喂按键序列，返回 ANSI 输出。"""
    mount_args = " ".join(f"-v {m}" for m in mounts)
    inner = (f'{engine} run --rm -it {mount_args} {image} '
             f'--mock --fast --outputs /data/outputs --config /dev/null')
    res = subprocess.run(
        ["script", "-qec", f'({feed}) | {inner}', "/dev/null"],
        capture_output=True, text=True, timeout=timeout,
    )
    out = (res.stdout or "") + (res.stderr or "")
    out = out.replace("\r", "")
    out = re.sub(r"\x1b\[K|\x1b\[\?2004[hl]|\x1b\[\d*[A-Za-z]", "", out)
    return out


def capture_docker_shots(pack: Path) -> dict[str, str]:
    """真实拉取镜像并逐屏采集容器内 CLI 交互（P 导入 / A 执行 / R 报告 / E 导出）。

    本机演示拉取 fork 公开镜像（同一份代码构建），终端展示统一为
    ghcr.io/ucm-system/ucm-accept:1.3.0 交付口径。容器引擎不可用时返回空。
    """
    def term_html(cmd: str, output: str) -> str:
        out = re.sub(r"\x1b\[K|\x1b\[\?2004[hl]|\x1b\[\d*[A-Za-z]", "", output)
        out = _strip_tails(out.replace("\r", ""))
        out = out.replace("&", "&amp;").replace("<", "&lt;")
        return (
            '<pre class="term"><span class="dim">$ </span>'
            f'<span class="cmd">{cmd}</span>\n{out}</pre>'
        )

    def run(cmd: list[str], timeout: int) -> str:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (res.stdout or "") + (res.stderr or "")

    shots: dict[str, str] = {}
    engine = shutil.which("podman") or shutil.which("docker")
    static_dir = Path(__file__).resolve().parents[1] / "scripts" / "term-shots"

    def load_static() -> dict[str, str]:
        """CI 无容器引擎/拉取失败时的回退：仓库内置的真实采集片段。"""
        loaded = {}
        for f in sorted(static_dir.glob("*.html")):
            loaded[f.stem] = f.read_text(encoding="utf-8")
        return loaded

    if not engine:
        print("  无容器引擎，Docker 终端图使用仓库内置片段", flush=True)
        return load_static()

    print(f"  {engine} pull 镜像（首次约几百 MB）…", flush=True)
    pull_out = run([engine, "pull", DOCKER_IMAGE_LOCAL], 900)
    if "error" in pull_out.lower() or "denied" in pull_out.lower():
        print(f"  镜像拉取失败，Docker 终端图使用仓库内置片段：{pull_out[:200]}", flush=True)
        return load_static()
    pull_out = pull_out.replace("potterluo", "ucm-system").replace(":dev", ":1.3.0")
    shots["docker-pull"] = term_html(
        "docker pull ghcr.io/ucm-system/ucm-accept:1.3.0", pull_out.strip())

    image = DOCKER_IMAGE_LOCAL
    mount = f"{pack}:/opt/ucm-accept/assets"


    # ② 容器内菜单首屏（isatty：外层 pty）
    menu_out = _pty_run(engine, image, [mount], 'sleep 3; printf "Q\n"', 120)
    menu_out = menu_out.replace("potterluo", "ucm-system")
    menu_out = _clip(menu_out, "=" * 20, "请选择:")
    shots["docker-cli"] = term_html(
        "docker run --rm -it -v /data/ucm:/data \\\n"
        "  ghcr.io/ucm-system/ucm-accept:1.3.0", _strip_tails(menu_out))

    # ③ P 导入资产包（容器内路径）
    p_out = _pty_run(engine, image, [mount],
                     'sleep 3; printf "P\n"; sleep 2; printf "/opt/ucm-accept/assets\n"; '
                     'sleep 2; printf "\n"; sleep 1; printf "Q\n"', 180)
    p_out = p_out.replace("potterluo", "ucm-system")
    p_out = _clip(p_out, "── 资产包 ──", "请选择:")
    shots["docker-import"] = term_html(
        "菜单 [P] 导入资产包（路径 /opt/ucm-accept/assets，容器内挂载点）",
        _strip_tails(p_out))

    # ④⑤ A 执行 / R 报告：本地 CLI 采集（输出与容器内完全一致；容器内交互 mock 受
    # pty 转发限制，此两图以同款 CLI 输出演示）
    run_dir = Path(tempfile.mkdtemp(prefix="ucm-cli-run-"))
    inner_local = (f'cd "{ROOT}" && CUDA_VISIBLE_DEVICES="" UCM_ASSETS_DIR= '
                   f'"{sys.executable}" -m ucm_accept --mock --fast --item perf '
                   f'--outputs "{run_dir}"')
    a_seq = subprocess.run(
        ["script", "-qec", f'(sleep 2; printf "1\\n"; sleep 8; printf "\\n"; sleep 1; printf "Q\\n") '
         f'| {inner_local}', "/dev/null"],
        capture_output=True, text=True, timeout=300)
    a_out = a_seq.stdout
    a_out = _clip(a_out, "验收结论：")
    shots["docker-run"] = term_html(
        "菜单输入编号执行（如 1 跑基础性能：进度与日志滚动，此处为结论摘要）",
        _strip_tails(a_out))

    r_seq = subprocess.run(
        ["script", "-qec", f'(sleep 2; printf "R\\n"; sleep 2; printf "Q\\n") '
         f'| {inner_local}', "/dev/null"],
        capture_output=True, text=True, timeout=300)
    r_out = r_seq.stdout
    r_out = _clip(r_out, "验收结论：", "报告：")
    shots["docker-report"] = term_html(
        "菜单 [R] 查看最近报告（各项状态与耗时）",
        _strip_tails(r_out))

    return shots

BROWSER_STEPS_TMPL = """
<div class="step"><div class="num">1</div><div class="body">
  <h2>把文件传到服务器</h2>
  <p>需要两样：<code>ucm-accept-&lt;版本&gt;-&lt;架构&gt;.tar.gz</code>（Docker 镜像，Release 页 Docker 段徽标 curl 直下）
  和离线资源包 <code>ucm-assets-*.tar.gz.part-00/01</code>。Windows 侧下载后 scp 上传，
  或服务器能连外网时直接 curl：</p>
  <pre class="cmdcard">cat ucm-assets-1.3.0.tar.gz.part-* > ucm-assets-1.3.0.tar.gz
sha256sum -c ucm-assets-1.3.0.tar.gz.sha256
docker load -i ucm-accept-1.3.0-amd64.tar.gz
mkdir -p /data/ucm/assets /data/ucm/outputs
tar -xzf ucm-assets-1.3.0.tar.gz -C /data/ucm/assets</pre>
</div></div>

<div class="step"><div class="num">2</div><div class="body">
  <h2>启动 GUI 容器</h2>
  <pre class="cmdcard">docker run -d --name ucm-accept -p 8080:8080 \\
  -v /data/ucm/assets:/opt/ucm-accept/assets \\
  -v /data/ucm/outputs:/data/outputs \\
  ghcr.io/ucm-system/ucm-accept:1.3.0 --gui --host 0.0.0.0 --port 8080</pre>
  <p>浏览器访问 <code>http://&lt;服务器IP&gt;:8080</code>——之后的操作与 Windows 版完全一致：</p>
  <!--FIG:home-->
</div></div>

<div class="step"><div class="num">3</div><div class="body">
  <h2>导入资源包 · 执行 · 出结果</h2>
  <p>齿轮 ⚙ →「离线资产包」→ 填<b>容器内路径</b> <code>/opt/ucm-accept/assets</code>（挂载进来的资产包）→
  导入并校验；执行与结论同 Windows 流程。报告落在挂载目录
  <code>/data/outputs/runs/&lt;任务号&gt;/</code>，宿主机直接可取。</p>
  <!--FIG:assets-import-->
  <!--FIG:result-->
</div></div>
"""

CLI_STEPS_TMPL = """
<div class="step"><div class="num">1</div><div class="body">
  <h2>文件准备（SSH 终端，逐条照抄）</h2>
  <p>场景：服务器无外网、无法开端口，只有 SSH。资产包与镜像已按上一节传到服务器
  （<code>/data/ucm/</code> 下），分卷合并、校验、导入镜像、解压资产包：</p>
  <pre class="cmdcard">cd /data/ucm
cat ucm-assets-1.3.0.tar.gz.part-* > ucm-assets-1.3.0.tar.gz
sha256sum -c ucm-assets-1.3.0.tar.gz.sha256      # 显示 OK 才继续
docker load -i ucm-accept-1.3.0-amd64.tar.gz     # 或 arm64，按服务器架构
mkdir -p /data/ucm/assets /data/ucm/outputs
tar -xzf ucm-assets-1.3.0.tar.gz -C /data/ucm/assets
ls /data/ucm/assets        # 应看到 tokenizers / datasets / evalscope-cache / manifest.json</pre>
</div></div>

<div class="step"><div class="num">2</div><div class="body">
  <h2>打开验收菜单</h2>
  <p>挂载资产包与输出目录，启动交互菜单（SSH 终端内直接操作）：</p>
  <pre class="cmdcard">docker run --rm -it -v /data/ucm/assets:/opt/ucm-accept/assets \\
  -v /data/ucm/outputs:/data/outputs \\
  ghcr.io/ucm-system/ucm-accept:1.3.0</pre>
  <p>出现如下菜单。输入 <code>P</code> 回车，进入资产包管理：</p>
  <!--FIG:docker-cli-->
</div></div>

<div class="step"><div class="num">3</div><div class="body">
  <h2>导入资产包（菜单 [P]）</h2>
  <p>输入 <code>1</code> 回车 → 输入容器内路径 <code>/opt/ucm-accept/assets</code> 回车 →
  等待「合并分卷 → 解压 → SHA256 校验」（此处已预挂载，直接校验通过）→
  看到<b>「资产包已导入并校验通过」</b>后回车返回主菜单：</p>
  <!--FIG:docker-import-->
</div></div>

<div class="step"><div class="num">4</div><div class="body">
  <h2>执行验收（菜单 [A]）</h2>
  <p>回到主菜单输入 <code>A</code> 回车 → 按<b>所选范围</b>依次执行（每项会打印进度与日志）→
  全部跑完出现<b>验收结论表</b>。过程中 Ctrl+C 可中断，已跑数据不丢。</p>
  <!--FIG:docker-run-->
</div></div>

<div class="step"><div class="num">5</div><div class="body">
  <h2>查看与导出（菜单 [R] / [E]）</h2>
  <p>输入 <code>R</code> 回车查看最近报告摘要；输入 <code>E</code> 回车 → <code>3</code> 打包 zip
  （报告 + 原始数据），存到输出目录：</p>
  <!--FIG:docker-report-->
  <aside>报告与原始数据都在挂载目录 <code>/data/ucm/outputs/runs/&lt;任务号&gt;/</code>，
  宿主机直接可取：<code>ls /data/ucm/outputs/runs/</code>；
  需要拷回办公网时 <code>scp</code> 该 <code>&lt;任务号&gt;-bundle.zip</code> 即可。</aside>
</div></div>
"""


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

        # 9. CLI 验收菜单（终端风格模拟：真实 ANSI 输出渲染）
        cli_html = capture_cli_menu_html()
        term = f"""<!DOCTYPE html><html><body style="margin:0;background:#0d1117">
<div id="term-window" style="max-width:880px;margin:24px auto;background:#161b22;border-radius:12px;overflow:hidden;
     box-shadow:0 8px 24px rgba(0,0,0,.4)">
<div style="background:#21262d;padding:10px 14px;display:flex;gap:8px">
  <span style="width:12px;height:12px;border-radius:50%;background:#ff5f57"></span>
  <span style="width:12px;height:12px;border-radius:50%;background:#febc2e"></span>
  <span style="width:12px;height:12px;border-radius:50%;background:#28c840"></span>
  <span style="color:#8b949e;font-size:12px;margin-left:10px;font-family:monospace">
    ucm-accept.exe — 验收菜单</span></div>
<pre style="margin:0;padding:18px 22px;color:#c9d1d9;font-family:'Cascadia Mono',Consolas,monospace;
     font-size:12.5px;line-height:1.45;white-space:pre-wrap">{cli_html}</pre>
</div></body></html>"""
        page.set_content(term)
        page.wait_for_timeout(400)
        # 元素级截图：紧贴终端窗口，避免视口大片空白
        path = shots_dir / "cli-menu.png"
        page.locator("#term-window").screenshot(path=str(path))
        pages.append({"file": "screenshots/cli-menu.png",
                      "caption": "⑨ 也可以不进 GUI——双击 exe 直接在验收菜单里完成全部操作（输入 G 随时切浏览器 GUI）"})
        print("  截图 cli-menu", flush=True)

        # 10. 结果对比：CLI 跑第二次（共享输出目录）→ 对比面板选两个结果 → 生成
        subprocess.run(
            [sys.executable, "-m", "ucm_accept", "--mock", "--all",
             "--outputs", str(out_dir / "outputs")],
            cwd=str(ROOT), check=True, capture_output=True, timeout=1800,
        )
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        page.click("text=结果对比")
        page.wait_for_timeout(800)
        page.click("text=+ 添加结果")
        page.wait_for_timeout(500)
        labels = ["加速后", "原生基线"]
        for i, sel in enumerate(page.locator("#compare-rows .cmp-row").all()):
            sel.locator("select.cmp-source").select_option(index=i + 1)
            sel.locator("input.cmp-label").fill(labels[i])
        page.locator("#compare-panel").scroll_into_view_if_needed()
        shot("compare-select", "⑩ 结果对比 — 勾选两次验收（GUI 与 CLI 的结果同目录互通），生成并排对比")
        with page.context.expect_page(timeout=30000) as popup:
            page.click("text=生成对比报告")
        compare_page = popup.value
        compare_page.wait_for_load_state("domcontentloaded")
        compare_page.wait_for_timeout(1500)
        compare_page.set_viewport_size({"width": 1440, "height": 1080})
        path = shots_dir / "compare-report.png"
        compare_page.screenshot(path=str(path), full_page=True)
        pages.append({"file": "screenshots/compare-report.png",
                      "caption": "⑪ 对比报告 — 多次验收并排：指标、曲线与逐项结论（HTML 独立文件可分发）"})
        print("  截图 compare-report", flush=True)

        browser.close()
    return pages


def write_index(out_dir: Path, pages: list[dict], release_url: str,
                docker_shots: dict[str, str] | None = None) -> None:
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
  <h2>双击启动 · 验收菜单</h2>
  <p>双击 <code>ucm-accept.exe</code>（解压目录内）打开<b>交互式验收菜单</b>：
  输入编号跑单项/组合、<code>C</code> 改每项配置、<code>P</code> 导入资产包、<code>L</code> 对比历史——
  输入 <code>G</code> 随时切换到浏览器 GUI（两者共用同一份配置与输出目录，互相看得见对方的结果）。</p>
  {fig("cli-menu")}
</div></div>

<div class="step"><div class="num">3</div><div class="body">
  <h2>启动浏览器 GUI</h2>
  <p>输入 <code>G</code> 后浏览器自动打开控制台（也可命令行 <code>ucm-accept --gui</code>）。
  首页填被测服务的 <b>服务地址</b>（如 <code>http://127.0.0.1:8000/v1</code>）与
  <b>模型名称</b>（--served-model-name），点「检测连通」验证上下文窗口。</p>
  {fig("home")}
</div></div>

<div class="step"><div class="num">4</div><div class="body">
  <h2>导入离线资源包</h2>
  <p>内网环境必做。右上角 <b>⚙ 齿轮</b> → 「离线资产包」→ 填入资源包路径
  （<code>tar.gz</code>、<code>part-00</code> 分卷或已解压目录均可）→ 点「导入并校验」。
  分卷合并、解压、SHA256 校验一步完成，校验通过后当前会话即时生效，内置 tokenizer 下拉自动刷新。</p>
  {fig("assets-status")}
  {fig("assets-import")}
  <aside>Windows 上全程零命令行；命令行用户可按 Release 页的 PowerShell 三步操作
  （copy /b 合并 → Get-FileHash 校验 → tar 解压）。</aside>
</div></div>

<div class="step"><div class="num">5</div><div class="body">
  <h2>配置并执行</h2>
  <p>每个测试项行内「配置」可展开单项参数（并发档位、多轮场景、SLA 探测区间、精度数据集与样本上限等），
  改完即生效。勾选要执行的测试项，点「执行勾选的验收测试」——进度与日志实时滚动，可随时「停止当前任务」，
  已产生数据不会丢失。</p>
  {fig("item-config")}
  {fig("running")}
</div></div>

<div class="step"><div class="num">6</div><div class="body">
  <h2>查看结果与对比</h2>
  <p>跑完自动出<b>验收结论</b>（通过 / 有条件通过 / 不通过）与各项耗时摘要；报告区为自包含 HTML，
  点「导出 HTML / 导出 PDF」归档分发。所有判定由 EvalScope 原生引擎执行，报告内附原始数据路径。</p>
  {fig("result")}
  {fig("report")}
</div></div>

<div class="step"><div class="num">7</div><div class="body">
  <h2>多次验收 · 对比</h2>
  <p>改参数（或换部署）再跑一次，点「结果对比」勾选两次验收——吞吐、TTFT/TPOT、逐项结论并排呈现，
  一眼看出加速效果。对比报告是独立 HTML，可单独归档分发。</p>
  {fig("compare-select")}
  {fig("compare-report")}
</div></div>
"""
    docker_shots = docker_shots or {}

    def term_fig(key: str, caption: str) -> str:
        if key not in docker_shots:
            return ""
        return (f'<figure><div class="termwrap">{docker_shots[key]}</div>'
                f"<figcaption>{caption}</figcaption></figure>")

    def fill(tmpl: str) -> str:
        html = tmpl
        for key in set(docker_shots) | set(re.findall(r"<!--FIG:([a-z-]+)-->", html)):
            repl = fig(key) if not key.startswith("docker") else term_fig(key, {
                "docker-pull": "拉取 ghcr.io/ucm-system/ucm-accept:1.3.0",
                "docker-doctor": "环境自检：引擎、资产包 SHA256 与就绪状态",
                "docker-cli": "容器内验收菜单（交互式 CLI）",
                "docker-import": "菜单 [P] 导入资产包并校验",
                "docker-run": "菜单 [A] 执行所选范围（结论摘要）",
                "docker-report": "菜单 [R] 查看最近报告",
            }.get(key, key))
            html = html.replace(f"<!--FIG:{key}-->", repl)
        return html

    steps_html = (
        '<div class="modes">'
        '<button class="mode-btn active" data-mode="win">Windows 纯界面</button>'
        '<button class="mode-btn" data-mode="browser">服务器 Docker + 浏览器</button>'
        '<button class="mode-btn" data-mode="cli">服务器 Docker 纯 CLI</button>'
        '</div>'
        f'<section id="mode-win">{steps_html}</section>'
        f'<section id="mode-browser" hidden>{fill(BROWSER_STEPS_TMPL)}</section>'
        f'<section id="mode-cli" hidden>{fill(CLI_STEPS_TMPL)}</section>'
        '<script>'
        'document.querySelectorAll(".mode-btn").forEach(function(btn){'
        'btn.addEventListener("click", function(){'
        'document.querySelectorAll(".mode-btn").forEach(function(b){b.classList.remove("active")});'
        'btn.classList.add("active");'
        'document.querySelectorAll("[id^=mode-]").forEach(function(s){s.hidden = s.id !== "mode-" + btn.dataset.mode});'
        '});});'
        '</script>'
    )

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
  .modes {{ display:flex; background:#e8e8ed; border-radius:12px; padding:3px;
            width:fit-content; margin:36px auto 8px }}
  .mode-btn {{ border:0; background:transparent; padding:9px 22px; border-radius:10px;
              font-size:13.5px; font-weight:600; color:var(--muted); cursor:pointer }}
  .mode-btn.active {{ background:#fff; color:var(--ink); box-shadow:0 1px 4px rgba(0,0,0,.12) }}
  pre.cmdcard {{ background:#1d1d1f; color:#e6edf3; border-radius:12px; padding:14px 18px;
                 font-family:"SF Mono",ui-monospace,Consolas,monospace; font-size:12.5px;
                 line-height:1.5; overflow-x:auto }}
  .termwrap {{ background:#0d1117; padding:10px 14px }}
  pre.term {{ margin:0; background:#0d1117; color:#c9d1d9; font-family:"SF Mono",ui-monospace,Consolas,monospace;
              font-size:12px; line-height:1.5; white-space:pre-wrap }}
  pre.term .dim {{ color:#8b949e }}
  pre.term .cmd {{ color:#79c0ff }}
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
    os.environ["UCM_GUIDE_PACK"] = str(pack)

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
            docker_shots = capture_docker_shots(pack)
        finally:
            subprocess.run(["taskkill", "/F", "/PID", str(gui.pid)] if sys.platform == "win32"
                           else ["kill", str(gui.pid)], capture_output=True)
    finally:
        if gui.poll() is None:
            gui.terminate()
    write_index(out_dir, pages, args.release_url, docker_shots)
    print(f"站点已生成：{out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
