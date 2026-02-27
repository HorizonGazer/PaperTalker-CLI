#!/usr/bin/env python3
"""
PaperTalker-CLI · quick_video.py — 一键主题→视频 (独立版)
=========================================================
用法:
    python quick_video.py "生物智能体"
    python quick_video.py "蛋白质折叠" --source search --platforms arxiv pubmed --year 2024
    python quick_video.py "量子计算" --source upload
    python quick_video.py "LLM药物发现" --source search --style anime --no-confirm

来源模式 (--source):
    research   Deep Research 自动搜索网络资料（默认）
    search     paper-search-mcp 论文检索，支持 --platforms / --year / --max-results
    upload     打开 NotebookLM 笔记本页面，用户手动上传文件后继续
    mixed      先 Deep Research，再补充论文检索

流程:
    1. 创建笔记本
    2. 获取来源（research / search / upload / mixed）
    3. 阶段性确认：展示来源列表，用户确认后继续
    4. 等待来源处理
    5. 生成视频
    6. 等待完成 + 下载
"""

import argparse
import asyncio
import os
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

def step(i, n, msg):   print(f"  {C}[{i}/{n}]{X} {msg}", flush=True)
def ok(msg):            print(f"  {G}  ✓ {msg}{X}", flush=True)
def warn(msg):          print(f"  {Y}  ⚠ {msg}{X}", flush=True)
def err(msg):           print(f"  {R}  ✗ {msg}{X}", flush=True)
def info(msg):          print(f"  {D}    {msg}{X}", flush=True)

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
    """Deep Research: 启动 → 轮询 → 返回发现的来源。"""
    step(2, 7, f"启动 Deep Research ({mode})...")
    t0 = time.time()
    task = await client.research.start(notebook_id, query=topic, source="web", mode=mode)
    if not task:
        err("Deep Research 启动失败")
        return []
    task_id = task.get("task_id")
    ok(f"Research 已启动: task_id={task_id}")

    step(3, 7, "等待 Deep Research 完成...")
    for i in range(120):
        await asyncio.sleep(5)
        result = await client.research.poll(notebook_id)
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
    """paper-search-mcp 论文检索。"""
    from paper_search import search_papers
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
    timeout: float = 1800.0,
    instructions: str | None = None,
    no_confirm: bool = False,
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

    async with await NotebookLMClient.from_storage(storage) as client:

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

        # ── 阶段确认 ─────────────────────────────────────
        print_sources_table(discovered, "发现的来源")

        if source_mode == "upload":
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
            wait_s = min(30 + imported_count * 3, 90)
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
    output_dir: str = "./output", timeout: float = 1800.0,
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

    async with await NotebookLMClient.from_storage(storage) as client:
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
        """,
    )
    p.add_argument("topic", help="视频主题")
    p.add_argument("--source", default="research",
                   choices=["research", "search", "upload", "mixed"],
                   help="来源模式 (默认: research)")
    p.add_argument("--style", default="whiteboard", choices=list(STYLE_MAP.keys()),
                   help="视频风格 (默认: whiteboard)")
    p.add_argument("--lang", default="zh-CN", help="语言 (默认: zh-CN)")
    p.add_argument("--mode", default="deep", choices=["fast", "deep"],
                   help="Deep Research 模式 (默认: deep)")
    p.add_argument("--platforms", nargs="+", default=None,
                   help="论文搜索平台 (默认: arxiv semantic_scholar)")
    p.add_argument("--max-results", type=int, default=10,
                   help="每平台最大结果数 (默认: 10)")
    p.add_argument("--year", type=int, default=None,
                   help="论文年份筛选")
    p.add_argument("--output", default="./output", help="输出目录 (默认: ./output)")
    p.add_argument("--timeout", type=float, default=1800.0,
                   help="视频生成超时秒数 (默认: 1800 = 30分钟)")
    p.add_argument("--instructions", default=None,
                   help="自定义视频指令 (覆盖 video.md)")
    p.add_argument("--no-confirm", action="store_true",
                   help="跳过阶段确认")
    p.add_argument("--resume", nargs=2, metavar=("NOTEBOOK_ID", "TASK_ID"),
                   help="恢复超时的视频生成")

    a = p.parse_args()

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
    ))
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
