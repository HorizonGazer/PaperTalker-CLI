#!/usr/bin/env python3
"""
PaperTalker-CLI · quick_video.py — 一键主题→视频 (独立版)
=========================================================
用法:
    python quick_video.py "生物智能体"
    python quick_video.py "蛋白质折叠" --source search --platforms arxiv pubmed --year 2024
    python quick_video.py "量子计算" --source upload
    python quick_video.py "LLM药物发现" --source search --style anime --no-confirm
    python quick_video.py "Attention机制" --source file --files paper.pdf
    python quick_video.py "Transformer" --source paper

来源模式 (--source):
    research   NotebookLM Deep/Fast Research 自动搜索网络资料（默认）
    search     自主文献检索 (Semantic Scholar + arXiv + CrossRef)，支持 --platforms / --year / --max-results
    upload     打开 NotebookLM 笔记本页面，用户手动上传文件后继续
    mixed      先 NotebookLM Research，再补充自主文献检索
    file       导入本地文件（PDF/txt/md/docx），需配合 --files 参数
    paper      按标题搜索论文，列出候选让用户选择后导入

流程:
    1. 创建笔记本
    2. 获取来源（research / search / upload / mixed / file / paper）
    3. 阶段性确认：展示来源列表，用户确认后继续
    4. 等待来源处理
    5. 生成视频
    6. 等待完成 + 下载
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# Windows GBK 兼容: 强制 UTF-8 输出
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

# ── 路径设置（独立可移植）─────────────────────────────────
CLI_DIR = Path(__file__).resolve().parent

# 加载 .env
from dotenv import load_dotenv
load_dotenv(CLI_DIR / ".env")

# 代理
for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    val = os.environ.get(key) or os.environ.get(key.upper())
    if val:
        os.environ[key] = val
        os.environ[key.lower()] = val

from notebooklm import NotebookLMClient, VideoStyle, ArtifactNotReadyError
from notebooklm.exceptions import ArtifactParseError

# ── 颜色 / 日志 ──────────────────────────────────────────
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; B = "\033[1m"; D = "\033[2m"; X = "\033[0m"

# 可导入 NotebookLM 的文件类型
IMPORTABLE_EXTS = {".pdf", ".txt", ".md", ".docx"}

def step(i, n, msg):   print(f"  {C}[{i}/{n}]{X} {msg}", flush=True)
def ok(msg):            print(f"  {G}  ✓ {msg}{X}", flush=True)
def warn(msg):          print(f"  {Y}  ⚠ {msg}{X}", flush=True)
def err(msg):           print(f"  {R}  ✗ {msg}{X}", flush=True)
def info(msg):          print(f"  {D}    {msg}{X}", flush=True)

async def preflight_check() -> bool:
    """快速连通性预检: 连接 NotebookLM 并列出笔记本，验证认证有效。"""
    storage = os.environ.get(
        "NOTEBOOKLM_STORAGE_PATH",
        str(Path.home() / ".notebooklm" / "storage_state.json"),
    )

    print(f"\n{B}{'═'*60}{X}")
    print(f"{B}  PaperTalker-CLI · NotebookLM 连通性检查{X}")
    print(f"{'═'*60}\n", flush=True)

    # 检查 storage_state.json 是否存在
    if not Path(storage).exists():
        err(f"认证文件不存在: {storage}")
        info("请先运行: python tools/auto_login.py")
        return False

    # 尝试连接（含自动登录重试）
    for _login_attempt in range(2):
        try:
            client_ctx = await NotebookLMClient.from_storage(storage)
            break
        except (ValueError, Exception) as e:
            if _login_attempt == 0 and ("expired" in str(e).lower() or "authentication" in str(e).lower() or "redirect" in str(e).lower()):
                warn(f"认证过期，自动重新登录...")
                import subprocess
                login_script = str(CLI_DIR / "tools" / "auto_login.py")
                login_result = subprocess.run(
                    [sys.executable, login_script],
                    timeout=720,
                )
                if login_result.returncode != 0:
                    err("自动登录失败，请手动运行: python tools/auto_login.py")
                    return False
                ok("自动登录成功，重试连接...")
                continue
            err(f"连接失败: {e}")
            return False
    else:
        err("认证重试耗尽")
        return False

    # 列出笔记本验证 API 可用
    try:
        async with client_ctx as client:
            notebooks = await client.notebooks.list()
            ok(f"NotebookLM 连接成功!")
            info(f"当前有 {len(notebooks)} 个笔记本")
            if notebooks:
                for nb in notebooks[:5]:
                    title = getattr(nb, "title", "无标题")
                    info(f"  · {title}")
                if len(notebooks) > 5:
                    info(f"  ... 还有 {len(notebooks)-5} 个")
    except Exception as e:
        err(f"API 调用失败: {e}")
        return False

    print(f"\n{G}  ✅ 预检通过，NotebookLM 已就绪{X}\n")
    return True


def banner(topic, source_mode, style, lang, output):
    print(f"\n{B}{'═'*60}{X}")
    print(f"{B}  PaperTalker-CLI · 一键视频生成{X}")
    print(f"{B}{'═'*60}{X}")
    print(f"  主题:   {C}{topic}{X}")
    print(f"  来源:   {source_mode}")
    print(f"  风格:   {style}")
    print(f"  语言:   {lang}")
    print(f"  输出:   {output}")
    print(f"{'═'*60}\n", flush=True)

# ── 视频风格 ──────────────────────────────────────────────
STYLE_MAP = {
    "classic": VideoStyle.CLASSIC, "whiteboard": VideoStyle.WHITEBOARD,
    "kawaii": VideoStyle.KAWAII, "anime": VideoStyle.ANIME,
    "watercolor": VideoStyle.WATERCOLOR, "retro_print": VideoStyle.RETRO_PRINT,
    "heritage": VideoStyle.HERITAGE, "paper_craft": VideoStyle.PAPER_CRAFT,
    "auto": VideoStyle.AUTO_SELECT,
}

# ── video.md 提示词 ──────────────────────────────────────
def load_prompt() -> str:
    p = CLI_DIR / "video.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""

# ── 阶段确认 ──────────────────────────────────────────────
def confirm(msg: str, auto: bool = False) -> bool:
    if auto:
        print(f"  {G}  → 自动确认: {msg}{X}", flush=True)
        return True
    try:
        ans = input(f"  {Y}  ? {msg} [Y/n]: {X}").strip().lower()
        return ans in ("", "y", "yes", "是")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def print_sources_table(sources: list[dict], label: str = "来源"):
    if not sources:
        warn(f"没有找到{label}")
        return
    print(f"\n  {B}  {label} ({len(sources)} 条):{X}")
    for i, s in enumerate(sources, 1):
        title = s.get("title", "")[:60]
        plat = s.get("source", s.get("platform", ""))
        year = s.get("published_date", "")[:4]
        cites = s.get("citations", 0)
        url = s.get("url", "")
        line = f"    {D}{i:>3}.{X} {title}"
        if plat:
            line += f"  {D}[{plat}]{X}"
        if year and year != "None":
            line += f"  {D}({year}){X}"
        if cites:
            line += f"  {Y}引用:{cites}{X}"
        print(line)
        if url:
            print(f"         {D}{url}{X}")
    print(flush=True)


# ══════════════════════════════════════════════════════════
#  来源获取策略
# ══════════════════════════════════════════════════════════

async def source_deep_research(client, notebook_id: str, topic: str, mode: str = "deep") -> list[dict]:
    """Deep Research: 启动 → 轮询 → 返回发现的来源。

    如果 Deep Research 失败（速率限制等），提示用户切换账号或自动降级到 Fast Research。
    """
    step(2, 7, f"启动 Deep Research ({mode})...")
    t0 = time.time()

    try:
        task = await client.research.start(notebook_id, query=topic, source="web", mode=mode)
    except Exception as e:
        error_msg = str(e).lower()
        # 检测速率限制错误
        if "rate" in error_msg or "limit" in error_msg or "quota" in error_msg or "429" in error_msg:
            if mode == "deep":
                warn(f"Deep Research 被限流: {e}")
                print()
                print(f"  {'='*60}")
                print(f"  {Y}检测到 Deep Research 速率限制{X}")
                print(f"  ")
                print(f"  可选方案:")
                print(f"    1. 切换 Google 账号（重新登录 NotebookLM）")
                print(f"    2. 自动降级到 Fast Research（速度更快，质量略低）")
                print(f"    3. 使用论文搜索模式（--source search）")
                print(f"  {'='*60}")
                print()

                # 询问用户
                response = input(f"  是否切换账号？(y/N): ").strip().lower()
                if response in ['y', 'yes', '是']:
                    print(f"\n  {Y}正在重新登录 NotebookLM...{X}")
                    # 删除旧的认证文件
                    auth_file = Path.home() / ".notebooklm" / "storage_state.json"
                    if auth_file.exists():
                        auth_file.unlink()
                        print(f"  {G}✓ 已清除旧账号缓存{X}")

                    # 调用自动登录
                    import subprocess
                    auto_login_script = CLI_DIR / "tools" / "auto_login.py"
                    if auto_login_script.exists():
                        result = subprocess.run(
                            [sys.executable, str(auto_login_script)],
                            capture_output=False
                        )
                        if result.returncode == 0:
                            print(f"  {G}✓ 账号切换成功，请重新运行脚本{X}")
                            sys.exit(0)
                        else:
                            err("账号切换失败")
                            return []
                    else:
                        err(f"找不到自动登录脚本: {auto_login_script}")
                        return []
                else:
                    warn("自动降级到 Fast Research...")
                    return await source_deep_research(client, notebook_id, topic, mode="fast")
            else:
                err(f"Fast Research 也被限流: {e}")
                print(f"\n  {Y}建议切换 Google 账号后重试{X}")
                print(f"  运行: python tools/auto_login.py")
                return []
        else:
            err(f"Deep Research 启动失败: {e}")
            return []

    if not task:
        if mode == "deep":
            warn("Deep Research 启动失败，尝试降级到 Fast Research...")
            return await source_deep_research(client, notebook_id, topic, mode="fast")
        else:
            err("Fast Research 启动失败")
            return []

    task_id = task.get("task_id")
    ok(f"Research 已启动: task_id={task_id}")

    step(3, 7, "等待 Deep Research 完成 (最长 40 分钟)...")
    consecutive_errors = 0
    for i in range(480):
        await asyncio.sleep(5)
        try:
            result = await client.research.poll(notebook_id)
            consecutive_errors = 0  # 重置错误计数
        except Exception as e:
            consecutive_errors += 1
            sys.stdout.write(f"\r    轮询 #{i+1}: 网络波动 ({consecutive_errors}/10)，重试中...   ")
            sys.stdout.flush()
            if consecutive_errors >= 10:
                print()
                err(f"连续 {consecutive_errors} 次网络错误，放弃: {e}")
                return []
            continue
        status = result.get("status", "")
        n = len(result.get("sources", []))
        sys.stdout.write(f"\r    轮询 #{i+1}: status={status}, sources={n}   ")
        sys.stdout.flush()
        if status == "completed":
            sources = result.get("sources", [])
            print()
            ok(f"Research 完成! 发现 {len(sources)} 个来源  ({time.time()-t0:.1f}s)")
            summary = result.get("summary", "")
            if summary:
                info(f"摘要: {summary[:200]}...")
            return sources
        elif status in ("failed", "error"):
            print()
            err(f"Research 失败: {result}")
            return []
    print()
    warn("Research 超时")
    return []


async def source_paper_search(topic: str, platforms: list[str], max_results: int, year: int | None) -> list[dict]:
    """自主文献检索 (literature-review skill: Semantic Scholar + arXiv + CrossRef)。"""
    from src.utils.paper_search import search_papers
    step(2, 7, f"搜索论文: platforms={platforms}, max={max_results}, year={year or 'any'}...")
    t0 = time.time()
    papers = await search_papers(topic, platforms=platforms, max_results=max_results, year=year)
    ok(f"搜索完成: {len(papers)} 篇论文  ({time.time()-t0:.1f}s)")
    return papers


async def source_upload(client, notebook_id: str) -> list[dict]:
    """打开 NotebookLM 笔记本页面，让用户手动上传文件。"""
    nb_url = f"https://notebooklm.google.com/notebook/{notebook_id}"
    step(2, 7, "打开 NotebookLM 笔记本，请手动上传文件...")
    print(f"\n  {B}  笔记本链接:{X} {C}{nb_url}{X}")
    print(f"  {Y}  请在浏览器中上传文件，完成后回到终端按 Enter 继续{X}\n")
    try:
        webbrowser.open(nb_url)
    except Exception:
        pass
    try:
        input(f"  {Y}  ↵ 上传完成后按 Enter 继续...{X}")
    except (EOFError, KeyboardInterrupt):
        print()
    sources = await client.sources.list(notebook_id)
    result = []
    for s in sources:
        result.append({
            "title": getattr(s, "title", "") or getattr(s, "name", ""),
            "url": "",
            "source": "upload",
            "id": getattr(s, "id", ""),
        })
    ok(f"笔记本中有 {len(result)} 个来源")
    return result


async def source_local_files(client, notebook_id: str, paths: list[str]) -> list[dict]:
    """导入本地文件（PDF/txt/md/docx）到 NotebookLM。

    paths 可以是文件路径或目录路径（自动递归扫描）。
    直接调用 client.sources.add_file()，无需再经过 import_sources()。
    """
    # 收集所有待导入文件
    files = []
    for p_str in paths:
        p = Path(p_str).resolve()
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in IMPORTABLE_EXTS:
                    files.append(f)
        elif p.is_file():
            if p.suffix.lower() in IMPORTABLE_EXTS:
                files.append(p)
            else:
                warn(f"不支持的文件类型: {p.name} (支持: {', '.join(IMPORTABLE_EXTS)})")
        else:
            warn(f"路径不存在: {p_str}")

    if not files:
        err("没有找到可导入的文件")
        return []

    # 去重
    files = list(dict.fromkeys(files))

    step(2, 7, f"准备导入 {len(files)} 个本地文件...")
    for i, f in enumerate(files, 1):
        size_kb = f.stat().st_size / 1024
        info(f"{i:>3}. {f.name} ({size_kb:.0f} KB)")

    step(3, 7, f"上传文件到 NotebookLM...")
    imported = []
    for i, f in enumerate(files, 1):
        try:
            src = await client.sources.add_file(notebook_id, str(f))
            imported.append({
                "title": f.stem,
                "url": "",
                "source": "file",
                "id": getattr(src, "id", ""),
            })
            sys.stdout.write(f"\r    已上传 {i}/{len(files)}: {f.name}")
            sys.stdout.flush()
        except Exception as e:
            print()
            warn(f"上传失败 [{f.name}]: {e}")
    if imported:
        print()
    ok(f"成功导入 {len(imported)}/{len(files)} 个文件")
    return imported


async def source_paper_title(
    client, notebook_id: str, topic: str,
    platforms: list[str], max_results: int, no_confirm: bool = False,
) -> list[dict]:
    """按论文标题搜索，列出候选让用户选择后导入。"""
    from src.utils.paper_search import search_papers
    step(2, 7, f"搜索论文: '{topic}' on {platforms}...")
    t0 = time.time()
    papers = await search_papers(topic, platforms=platforms, max_results=max_results)
    ok(f"搜索完成: {len(papers)} 篇论文  ({time.time()-t0:.1f}s)")

    if not papers:
        warn("没有找到相关论文")
        return []

    print_sources_table(papers, "搜索结果")

    # 让用户选择
    if no_confirm:
        info("自动全选 (--no-confirm)")
        selected_indices = list(range(len(papers)))
    else:
        try:
            ans = input(f"  {Y}  选择论文编号 (逗号分隔, 'all' 全选, Enter 跳过): {X}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return []

        if not ans:
            info("已跳过")
            return []
        elif ans.lower() == "all":
            selected_indices = list(range(len(papers)))
        else:
            selected_indices = []
            for part in ans.split(","):
                part = part.strip()
                if part.isdigit():
                    idx = int(part) - 1  # 从 1 开始
                    if 0 <= idx < len(papers):
                        selected_indices.append(idx)

    if not selected_indices:
        warn("没有选择任何论文")
        return []

    selected = [papers[i] for i in selected_indices]
    ok(f"已选择 {len(selected)} 篇论文")
    return selected


# ══════════════════════════════════════════════════════════
#  导入来源到笔记本
# ══════════════════════════════════════════════════════════

async def import_sources(client, notebook_id: str, sources: list[dict], task_id: str | None = None, source_mode: str = "research"):
    """将来源导入到 NotebookLM 笔记本。"""
    if not sources:
        return 0

    if source_mode in ("research", "mixed") and task_id:
        batch_size = 15
        total_imported = 0
        for i in range(0, len(sources), batch_size):
            batch = sources[i:i + batch_size]
            try:
                imported = await client.research.import_sources(notebook_id, task_id, batch)
                total_imported += len(imported)
                info(f"批次 {i//batch_size+1}: 导入 {len(imported)} 个")
            except Exception as e:
                warn(f"批次 {i//batch_size+1} 导入失败 (已导入 {total_imported}): {e}")
                break
        if total_imported > 0:
            return total_imported

    count = 0
    for s in sources:
        url = s.get("pdf_url") or s.get("url")
        if not url:
            continue
        try:
            await client.sources.add_url(notebook_id, url=url)
            count += 1
            sys.stdout.write(f"\r    已添加 {count}/{len(sources)}...")
            sys.stdout.flush()
        except Exception as e:
            warn(f"添加失败 [{s.get('title', '')[:30]}]: {e}")
    if count:
        print()
    return count


# ══════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════

async def run(
    topic: str,
    source_mode: str = "research",
    style: str = "whiteboard",
    language: str = "zh-CN",
    research_mode: str = "deep",
    platforms: list[str] | None = None,
    max_results: int = 10,
    year: int | None = None,
    output_dir: str = "./output",
    timeout: float = 3600.0,
    instructions: str | None = None,
    no_confirm: bool = False,
    file_paths: list[str] | None = None,
):
    total = 7
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    prompt = instructions or load_prompt()
    vstyle = STYLE_MAP.get(style, VideoStyle.WHITEBOARD)

    banner(topic, source_mode, style, language, out)

    storage = os.environ.get(
        "NOTEBOOKLM_STORAGE_PATH",
        str(Path.home() / ".notebooklm" / "storage_state.json"),
    )

    # 自动登录重试: 认证过期时自动调用 auto_login.py 刷新后重试
    for _login_attempt in range(2):
        try:
            client_ctx = await NotebookLMClient.from_storage(storage)
            break
        except (ValueError, Exception) as e:
            if _login_attempt == 0 and ("expired" in str(e).lower() or "authentication" in str(e).lower() or "redirect" in str(e).lower()):
                warn(f"认证过期，自动重新登录...")
                import subprocess
                login_script = str(CLI_DIR / "tools" / "auto_login.py")
                login_result = subprocess.run(
                    [sys.executable, login_script],
                    timeout=720,
                )
                if login_result.returncode != 0:
                    err("自动登录失败，请手动运行: python tools/auto_login.py")
                    return None
                ok("自动登录成功，继续执行...")
                continue
            raise

    async with client_ctx as client:

        # ── Step 1: 创建笔记本 ────────────────────────────
        step(1, total, "创建 NotebookLM 笔记本...")
        t0 = time.time()
        notebook = await client.notebooks.create(title=topic)
        nid = notebook.id
        ok(f"笔记本: {nid}  ({time.time()-t0:.1f}s)")
        info(f"链接: https://notebooklm.google.com/notebook/{nid}")

        # ── Step 2-3: 获取来源 ────────────────────────────
        discovered = []
        research_task_id = None

        if source_mode in ("research", "mixed"):
            discovered = await source_deep_research(client, nid, topic, research_mode)
            try:
                task_info = await client.research.poll(nid)
                research_task_id = task_info.get("task_id")
            except Exception:
                pass

        if source_mode in ("search", "mixed"):
            papers = await source_paper_search(topic, platforms or ["arxiv", "semantic_scholar"], max_results, year)
            discovered.extend(papers)

        if source_mode == "upload":
            discovered = await source_upload(client, nid)

        if source_mode == "file":
            if not file_paths:
                err("--source file 需要 --files 参数指定文件路径")
                return None
            discovered = await source_local_files(client, nid, file_paths)

        if source_mode == "paper":
            discovered = await source_paper_title(
                client, nid, topic,
                platforms or ["arxiv", "semantic_scholar"],
                max_results, no_confirm,
            )

        # ── 阶段确认 ─────────────────────────────────────
        print_sources_table(discovered, "发现的来源")

        if source_mode in ("upload", "file"):
            # upload/file 模式下文件已导入，无需再调用 import_sources
            if not confirm(f"笔记本中有 {len(discovered)} 个来源，继续生成视频?", no_confirm):
                print(f"\n  {Y}已取消{X}\n")
                return None
            imported_count = len(discovered)
        else:
            if not discovered:
                warn("没有找到任何来源")
                if not confirm("继续使用空笔记本生成视频?", no_confirm):
                    print(f"\n  {Y}已取消{X}\n")
                    return None
                imported_count = 0
            else:
                if not confirm(f"将 {len(discovered)} 个来源导入笔记本并生成视频?", no_confirm):
                    print(f"\n  {Y}已取消{X}\n")
                    return None

                step(4, total, "导入来源到笔记本...")
                t0 = time.time()
                imported_count = await import_sources(
                    client, nid, discovered,
                    task_id=research_task_id,
                    source_mode=source_mode,
                )
                ok(f"已导入 {imported_count} 个来源  ({time.time()-t0:.1f}s)")

        # ── Step 5: 等待来源处理 ──────────────────────────
        step(5, total, "等待来源处理...")
        if imported_count > 0:
            wait_s = min(30 + imported_count * 5, 360)
            for i in range(wait_s):
                sys.stdout.write(f"\r    等待中... {i+1}/{wait_s}s")
                sys.stdout.flush()
                await asyncio.sleep(1)
            print()
            ok("来源处理完成")
        else:
            ok("无需等待")

        # ── Step 6: 生成视频 ──────────────────────────────
        step(6, total, "提交视频生成...")
        t0 = time.time()
        gen = await client.artifacts.generate_video(
            notebook_id=nid,
            instructions=prompt or None,
            video_style=vstyle,
            language=language,
        )
        tid = gen.task_id
        ok(f"视频任务: {tid}")

        safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in topic)[:50]
        ts = time.strftime("%Y%m%d_%H%M%S")
        fpath = str(out / f"{safe}_{ts}.mp4")

        info(f"等待视频完成 (最长 {int(timeout)}s，完成即尝试下载)...")
        t1 = time.time()
        final = None
        result_path = None
        poll_count = 0
        rapid_mode = False  # 接近完成时切换快速模式
        while time.time() - t1 < timeout:
            await asyncio.sleep(2.0 if rapid_mode else 3.0)
            poll_count += 1
            try:
                status_obj = await client.artifacts.poll_status(nid, tid)
                elapsed = time.time() - t0
                tag = " ⚡" if rapid_mode else ""
                sys.stdout.write(f"\r    #{poll_count} 状态: {status_obj.status}  ({elapsed:.0f}s){tag}   ")
                sys.stdout.flush()

                if status_obj.status in ("failed", "error"):
                    print()
                    final = status_obj
                    break

                if status_obj.status in ("completed", "done"):
                    try:
                        result_path = await client.artifacts.download_video(nid, fpath, artifact_id=tid)
                        print()
                        ok(f"视频生成完成并已下载!  ({time.time()-t0:.1f}s)")
                        ok(f"已保存: {result_path}")
                        break
                    except ArtifactNotReadyError:
                        rapid_mode = True
                    except ArtifactParseError:
                        rapid_mode = True
                    except Exception as e:
                        warn(f"下载异常: {e}，继续重试")
                        rapid_mode = True
                else:
                    # 主动探测下载: 快速模式每次都试, 普通模式每3次试一次
                    should_try = rapid_mode or (poll_count % 3 == 0 and poll_count >= 2)
                    if should_try:
                        try:
                            result_path = await client.artifacts.download_video(nid, fpath, artifact_id=tid)
                            print()
                            ok(f"视频已可下载!  ({time.time()-t0:.1f}s)")
                            ok(f"已保存: {result_path}")
                            break
                        except ArtifactNotReadyError:
                            pass
                        except ArtifactParseError:
                            if not rapid_mode:
                                rapid_mode = True
                                info("检测到视频接近完成，切换快速轮询...")
                        except Exception:
                            pass
            except Exception:
                pass
        else:
            if final is None:
                print()
                err(f"视频生成超时 ({int(timeout)}s)，但任务仍在后台运行")
                print(f"\n  {Y}恢复命令:{X}")
                print(f'  python quick_video.py "{topic}" --resume {nid} {tid}\n')
                return None

        if final is not None and final.status in ("failed", "error"):
            err(f"视频状态异常: {final.status}")
            if getattr(final, "error", None):
                err(f"错误: {final.error}")
            return None

        if final is not None and final.status not in ("completed", "done"):
            return None

        if result_path is None:
            step(7, total, "下载视频...")
            t0 = time.time()
            try:
                result_path = await client.artifacts.download_video(nid, fpath, artifact_id=tid)
                ok(f"已保存: {result_path}  ({time.time()-t0:.1f}s)")
            except Exception as e:
                err(f"下载失败: {e}")
                return None

    # ── 完成 ──────────────────────────────────────────────
    print(f"\n{G}{'═'*60}{X}")
    print(f"{G}{B}  ✅ 全部完成!{X}")
    print(f"{G}  视频: {result_path}{X}")
    print(f"{G}  笔记本: {nid}{X}")
    print(f"{G}  链接: https://notebooklm.google.com/notebook/{nid}{X}")
    print(f"{G}{'═'*60}{X}\n")
    return result_path


# ══════════════════════════════════════════════════════════
#  恢复超时的视频生成
# ══════════════════════════════════════════════════════════

async def resume_video(
    notebook_id: str, task_id: str, topic: str = "resume",
    output_dir: str = "./output", timeout: float = 3600.0,
):
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    print(f"\n{B}{'═'*60}{X}")
    print(f"{B}  PaperTalker-CLI · 恢复视频下载{X}")
    print(f"  笔记本: {notebook_id}")
    print(f"  任务:   {task_id}")
    print(f"{'═'*60}\n", flush=True)

    storage = os.environ.get(
        "NOTEBOOKLM_STORAGE_PATH",
        str(Path.home() / ".notebooklm" / "storage_state.json"),
    )

    # 自动登录重试
    for _login_attempt in range(2):
        try:
            client_ctx = await NotebookLMClient.from_storage(storage)
            break
        except (ValueError, Exception) as e:
            if _login_attempt == 0 and ("expired" in str(e).lower() or "authentication" in str(e).lower() or "redirect" in str(e).lower()):
                warn(f"认证过期，自动重新登录...")
                import subprocess
                login_script = str(CLI_DIR / "tools" / "auto_login.py")
                login_result = subprocess.run(
                    [sys.executable, login_script],
                    timeout=720,
                )
                if login_result.returncode != 0:
                    err("自动登录失败，请手动运行: python tools/auto_login.py")
                    return None
                ok("自动登录成功，继续执行...")
                continue
            raise

    async with client_ctx as client:
        step(1, 2, "检查视频状态 (完成即尝试下载)...")
        t0 = time.time()
        safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in topic)[:50]
        ts = time.strftime("%Y%m%d_%H%M%S")
        fpath = str(out / f"{safe}_{ts}.mp4")
        result_path = None
        poll_count = 0
        rapid_mode = False
        while time.time() - t0 < timeout:
            await asyncio.sleep(2.0 if rapid_mode else 3.0)
            poll_count += 1
            try:
                status_obj = await client.artifacts.poll_status(notebook_id, task_id)
                elapsed = time.time() - t0
                tag = " ⚡" if rapid_mode else ""
                sys.stdout.write(f"\r    #{poll_count} 状态: {status_obj.status}  ({elapsed:.0f}s){tag}   ")
                sys.stdout.flush()

                if status_obj.status in ("failed", "error"):
                    print()
                    err(f"视频失败: {status_obj.error or status_obj.status}")
                    return None

                if status_obj.status in ("completed", "done"):
                    try:
                        result_path = await client.artifacts.download_video(
                            notebook_id, fpath, artifact_id=task_id
                        )
                        print()
                        ok(f"视频已完成并已下载!  ({time.time()-t0:.1f}s)")
                        ok(f"已保存: {result_path}")
                        break
                    except ArtifactNotReadyError:
                        rapid_mode = True
                    except ArtifactParseError:
                        rapid_mode = True
                    except Exception as e:
                        warn(f"下载异常: {e}，继续重试")
                        rapid_mode = True
                else:
                    should_try = rapid_mode or (poll_count % 3 == 0 and poll_count >= 2)
                    if should_try:
                        try:
                            result_path = await client.artifacts.download_video(
                                notebook_id, fpath, artifact_id=task_id
                            )
                            print()
                            ok(f"视频已可下载!  ({time.time()-t0:.1f}s)")
                            ok(f"已保存: {result_path}")
                            break
                        except ArtifactNotReadyError:
                            pass
                        except ArtifactParseError:
                            if not rapid_mode:
                                rapid_mode = True
                                info("检测到视频接近完成，切换快速轮询...")
                        except Exception:
                            pass
            except Exception as e:
                sys.stdout.write(f"\r    轮询出错: {e}   ")
                sys.stdout.flush()
        else:
            if result_path is None:
                print()
                err(f"仍然超时 ({timeout}s)")
                info(f"稍后再试: python quick_video.py \"{topic}\" --resume {notebook_id} {task_id}")
                return None

        if result_path is None:
            step(2, 2, "下载视频...")
            t0 = time.time()
            result_path = await client.artifacts.download_video(
                notebook_id, fpath, artifact_id=task_id
            )
            ok(f"已保存: {result_path}  ({time.time()-t0:.1f}s)")

    print(f"\n{G}{'═'*60}{X}")
    print(f"{G}{B}  ✅ 下载完成!{X}")
    print(f"{G}  视频: {result_path}{X}")
    print(f"{G}{'═'*60}{X}\n")
    return result_path


# ══════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="PaperTalker-CLI · 一键主题→视频",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python quick_video.py "生物智能体"
  python quick_video.py "蛋白质折叠" --source search --platforms arxiv pubmed --year 2024
  python quick_video.py "量子计算" --source upload
  python quick_video.py "LLM" --source mixed --style anime --no-confirm
  python quick_video.py "Attention" --source file --files paper.pdf ./more_papers/
  python quick_video.py "Transformer" --source paper --platforms arxiv
        """,
    )
    p.add_argument("topic", help="视频主题")
    p.add_argument("--source", default="research",
                   choices=["research", "search", "upload", "mixed", "file", "paper"],
                   help="来源模式: research=NotebookLM检索, search=自主文献检索, file=本地文件 (默认: research)")
    p.add_argument("--files", nargs="+", default=None,
                   help="本地文件或目录路径 (用于 --source file)")
    p.add_argument("--style", default="whiteboard", choices=list(STYLE_MAP.keys()),
                   help="视频风格 (默认: whiteboard)")
    p.add_argument("--lang", default="zh-CN", help="语言 (默认: zh-CN)")
    p.add_argument("--mode", default="deep", choices=["fast", "deep"],
                   help="Deep Research 模式 (默认: deep)")
    p.add_argument("--platforms", nargs="+", default=None,
                   help="文献检索平台 (默认: arxiv semantic_scholar; 可选: crossref)")
    p.add_argument("--max-results", type=int, default=10,
                   help="每平台最大结果数 (默认: 10)")
    p.add_argument("--year", type=int, default=None,
                   help="论文年份筛选")
    p.add_argument("--output", default="./output", help="输出目录 (默认: ./output)")
    p.add_argument("--timeout", type=float, default=3600.0,
                   help="视频生成超时秒数 (默认: 3600 = 60分钟)")
    p.add_argument("--instructions", default=None,
                   help="自定义视频指令 (覆盖 video.md)")
    p.add_argument("--no-confirm", action="store_true",
                   help="跳过阶段确认")
    p.add_argument("--check", action="store_true",
                   help="仅检查 NotebookLM 连通性，不生成视频")
    p.add_argument("--resume", nargs=2, metavar=("NOTEBOOK_ID", "TASK_ID"),
                   help="恢复超时的视频生成")
    p.add_argument("--publish", nargs="*", default=None,
                   metavar="PLATFORM",
                   help="生成后自动发布 (可指定平台: bilibili weixin_channels, 默认: bilibili weixin_channels)")

    a = p.parse_args()

    if a.check:
        success = asyncio.run(preflight_check())
        sys.exit(0 if success else 1)

    if a.resume:
        nid, tid = a.resume
        result = asyncio.run(resume_video(
            notebook_id=nid, task_id=tid, topic=a.topic,
            output_dir=a.output, timeout=a.timeout,
        ))
        sys.exit(0 if result else 1)

    result = asyncio.run(run(
        topic=a.topic, source_mode=a.source, style=a.style,
        language=a.lang, research_mode=a.mode, platforms=a.platforms,
        max_results=a.max_results, year=a.year, output_dir=a.output,
        timeout=a.timeout, instructions=a.instructions, no_confirm=a.no_confirm,
        file_paths=a.files,
    ))

    if not result:
        sys.exit(1)

    # Auto-publish if --publish specified
    if a.publish is not None:
        publish_platforms = a.publish if a.publish else ["bilibili", "weixin_channels"]
        print(f"\n{'='*60}")
        print(f"  Phase 2: Auto-publishing to {', '.join(publish_platforms)}")
        print(f"{'='*60}\n")

        publish_cmd = [
            sys.executable, "-u",
            str(Path(__file__).resolve().parent / "publish.py"),
            "--platforms", *publish_platforms,
        ]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        try:
            ret = subprocess.run(publish_cmd, env=env, timeout=3600,
                                 cwd=str(Path(__file__).resolve().parent))
            if ret.returncode != 0:
                print(f"\n  Auto-publish failed (exit code {ret.returncode})")
                sys.exit(1)
        except subprocess.TimeoutExpired:
            print(f"\n  Auto-publish timed out (60 min)")
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
