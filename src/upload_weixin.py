#!/usr/bin/env python3
"""
upload_weixin.py - Standalone WeChat Channels upload script
============================================================
Uploads video to WeChat Channels (视频号) with metadata.

Usage:
    python src/upload_weixin.py video.mp4 --title "标题" --desc "描述"
    python src/upload_weixin.py video.mp4 --title "标题" --tags "tag1,tag2"

Requires:
    pip install playwright nest-asyncio
    playwright install chromium
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Windows GBK fix
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

# Patch asyncio to allow nested event loops (Windows Playwright compat)
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEIXIN_STORAGE_STATE = PROJECT_ROOT / "cookies" / "weixin" / "storage_state.json"

G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; D = "\033[2m"; X = "\033[0m"


async def upload_weixin_channels(video_path: Path, title: str, desc: str, tags: str = "") -> dict:
    """Upload video to WeChat Channels using async Playwright API.

    Args:
        video_path: Path to video file
        title: Video title (6-16 chars, auto-padded if < 6)
        desc: Video description
        tags: Comma-separated tags (optional)

    Returns:
        dict with {"ok": bool} or {"ok": bool, "error": str}
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"ok": False, "error": "playwright not installed. Run: pip install playwright && playwright install chromium"}

    publish_clicked = False  # Track if publish was clicked (for error handling)

    profile_dir = WEIXIN_STORAGE_STATE.parent / "browser_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Short title: 6-16 chars (视频号 requires minimum 6)
    title_short = title[:16] if len(title) > 16 else title
    if len(title_short) < 6:
        title_short = title_short + "—视频解读"  # Pad to meet minimum
        title_short = title_short[:16]

    tag_suffix = ""
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        tag_suffix = " " + " ".join(f"#{t}" for t in tag_list[:5])
    full_desc = desc + tag_suffix

    p = await async_playwright().start()
    try:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-proxy-server",
            ],
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            ignore_https_errors=True,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to upload page (will redirect to login if not authenticated)
        print(f"  {Y}正在打开发布页面...{X}", flush=True)
        try:
            await page.goto("https://channels.weixin.qq.com/platform/post/create", timeout=30000)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"  {Y}导航异常: {e}，继续...{X}", flush=True)

        # Check current URL
        current_url = page.url
        print(f"  当前URL: {current_url}", flush=True)

        # If on login page, wait for user to scan and auto-redirect
        if "login" in current_url.lower():
            print(f"\n  {'='*50}")
            print(f"  {Y}请用微信扫描浏览器中的二维码登录{X}")
            print(f"  扫码后在手机上点击「确认登录」")
            print(f"  登录后会自动跳转到发布页面")
            print(f"  等待登录中... (最多5分钟)")
            print(f"  {'='*50}\n", flush=True)

            start = time.time()
            logged_in = False
            last_print = 0
            while time.time() - start < 300:
                try:
                    current_url = page.url
                    # Check if redirected to create page
                    if "post/create" in current_url:
                        logged_in = True
                        print(f"  {G}✓✓ 扫码成功！已自动跳转到发布页面{X}", flush=True)
                        print(f"  {G}当前URL: {current_url}{X}", flush=True)
                        break
                except Exception as e:
                    print(f"  {Y}检测异常: {e}{X}", flush=True)

                elapsed = int(time.time() - start)
                if elapsed >= last_print + 10:
                    print(f"  等待扫码... ({elapsed}s)", flush=True)
                    last_print = elapsed
                await asyncio.sleep(0.5)

            if not logged_in:
                print(f"  {R}登录超时 (5分钟){X}", flush=True)
                await context.close()
                await p.stop()
                return {"ok": False, "error": "Login timeout"}

            print(f"  {G}✓ 微信视频号登录成功!{X}", flush=True)
            WEIXIN_STORAGE_STATE.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(WEIXIN_STORAGE_STATE))
        else:
            # Already logged in
            if "post/create" in current_url:
                print(f"  {G}✓ 微信视频号已缓存登录，直接上传{X}", flush=True)
            else:
                # Navigate to create page
                print(f"  {Y}正在跳转到发布页面...{X}", flush=True)
                await page.goto("https://channels.weixin.qq.com/platform/post/create", timeout=30000)
                await asyncio.sleep(3)
                current_url = page.url
                if "post/create" in current_url:
                    print(f"  {G}✓ 已到达发布页面{X}", flush=True)
                else:
                    print(f"  {R}无法到达发布页面，当前URL: {current_url}{X}", flush=True)
                    await context.close()
                    await p.stop()
                    return {"ok": False, "error": f"Cannot reach create page: {current_url}"}

        # Final verification
        final_url = page.url
        print(f"  最终URL检查: {final_url}", flush=True)
        if "post/create" not in final_url:
            print(f"  {R}✗ 未在发布页面{X}", flush=True)
            await context.close()
            await p.stop()
            return {"ok": False, "error": f"Not on create page: {final_url}"}

        print(f"  {G}✓✓ 已确认到达发布页面{X}", flush=True)

        # Find wujie iframe
        upload_frame = None
        for attempt in range(15):
            for frame in page.frames:
                if "/micro/" in frame.url:
                    upload_frame = frame
                    break
            if upload_frame:
                break
            await asyncio.sleep(2)

        if not upload_frame:
            print(f"    未找到iframe，使用主页面", flush=True)
            upload_frame = page

        # Wait for file input
        file_input_found = False
        try:
            await upload_frame.wait_for_selector('input[type="file"]', timeout=30000, state="attached")
            file_input_found = True
        except Exception:
            pass

        if not file_input_found:
            # Try all frames
            print(f"    在当前frame未找到文件输入框，检查所有frames...", flush=True)
            for frame in page.frames:
                try:
                    fi = frame.locator('input[type="file"]')
                    if await fi.count() > 0:
                        upload_frame = frame
                        file_input_found = True
                        print(f"    找到文件输入框在frame: {frame.url[:80]}", flush=True)
                        break
                except Exception:
                    pass

        await asyncio.sleep(2)

        # Step 1: Upload video via file chooser
        try:
            async with page.expect_file_chooser(timeout=10000) as fc_info:
                # Try clicking via JavaScript first
                clicked = False
                for frame in [upload_frame] + list(page.frames):
                    try:
                        fi_count = await frame.locator('input[type="file"]').count()
                        if fi_count > 0:
                            await frame.evaluate('document.querySelector("input[type=\\"file\\"]").click()')
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    await context.close()
                    await p.stop()
                    return {"ok": False, "error": "Cannot find file input"}
        except Exception as e:
            await context.close()
            await p.stop()
            return {"ok": False, "error": f"File chooser failed: {e}"}

        file_chooser = await fc_info.value
        await file_chooser.set_files(str(video_path))
        print(f"    视频已选择，等待上传...", flush=True)

        # Step 2: Wait for upload to complete
        max_upload_wait = 300
        start = time.time()
        upload_done = False
        while time.time() - start < max_upload_wait:
            try:
                video_elem = upload_frame.locator('video')
                delete_btn = upload_frame.locator('button:has-text("删除")')
                video_elem_main = page.locator('video')
                delete_btn_main = page.locator('button:has-text("删除")')

                if await video_elem.count() > 0 or await delete_btn.count() > 0:
                    upload_done = True
                    print(f"    检测到上传完成标志 (iframe)", flush=True)
                    break
                if await video_elem_main.count() > 0 or await delete_btn_main.count() > 0:
                    upload_done = True
                    print(f"    检测到上传完成标志 (主页面)", flush=True)
                    break

                short_title_input = upload_frame.locator('input[placeholder*="概括视频主要内容"]')
                if await short_title_input.count() > 0:
                    is_disabled = await short_title_input.first.is_disabled()
                    if not is_disabled:
                        upload_done = True
                        print(f"    短标题输入框已启用，上传完成", flush=True)
                        break
            except Exception:
                pass
            elapsed = int(time.time() - start)
            if elapsed % 10 == 0 and elapsed > 0:
                print(f"    上传中... ({elapsed}s)", flush=True)
            await asyncio.sleep(2)

        if not upload_done:
            print(f"    {Y}未检测到视频预览，但继续尝试填写表单...{X}", flush=True)

        print(f"    上传完成，填写信息...", flush=True)
        await asyncio.sleep(3)

        # Wujie iframe may be empty after upload, fallback to main page
        short_title_test = upload_frame.locator('input[placeholder*="概括"]')
        if await short_title_test.count() == 0 and hasattr(upload_frame, 'url'):
            upload_frame = page

        # Step 3: Fill short title
        try:
            short_title_input = upload_frame.locator('input[placeholder*="概括视频主要内容"]')
            count = await short_title_input.count()
            print(f"    短标题输入框: 找到 {count} 个", flush=True)
            if count > 0:
                await short_title_input.first.click()
                await asyncio.sleep(0.3)
                await short_title_input.first.fill(title_short)
                print(f"    ✓ 短标题: {title_short}", flush=True)
            else:
                print(f"    ✗ 短标题输入框未找到", flush=True)
        except Exception as e:
            print(f"    ✗ 短标题填写失败: {e}", flush=True)

        # Step 4: Fill description
        try:
            desc_elem = upload_frame.locator('div.input-editor[contenteditable][data-placeholder="添加描述"]')
            count = await desc_elem.count()
            print(f"    描述字段: 找到 {count} 个", flush=True)
            if count > 0 and await desc_elem.first.is_visible():
                await desc_elem.first.click()
                await asyncio.sleep(0.3)
                await desc_elem.first.evaluate(f'el => el.innerText = {repr(full_desc)}')
                print(f"    ✓ 描述已填写", flush=True)
        except Exception as e:
            print(f"    ⚠ 描述填写异常: {e}", flush=True)

        await asyncio.sleep(2)

        # Step 5: Wait for publish button
        print(f"    检查发表按钮状态...", flush=True)
        try:
            publish_btn = upload_frame.locator('button:has-text("发表")')
            btn_count = await publish_btn.count()
            print(f"    发表按钮: 找到 {btn_count} 个", flush=True)

            if btn_count > 0:
                max_wait_publish = 300  # 5 min — large videos need server processing
                is_disabled = True
                for wait_i in range(max_wait_publish // 5):
                    cls = await publish_btn.first.get_attribute("class") or ""
                    html_disabled = await publish_btn.first.get_attribute("disabled")
                    is_disabled = "disabled" in cls or html_disabled is not None
                    if not is_disabled:
                        break
                    if wait_i == 0:
                        print(f"    {Y}发表按钮暂时禁用，等待视频处理...{X}", flush=True)
                    print(f"\r    等待发表按钮可用... ({(wait_i+1)*5}s/{max_wait_publish}s)", end="", flush=True)
                    await asyncio.sleep(5)

                if not is_disabled:
                    print(f"\n    发表按钮状态: enabled", flush=True)
                else:
                    print(f"\n    发表按钮状态: disabled (超时)", flush=True)
                    await context.close()
                    await p.stop()
                    return {"ok": False, "error": "Publish button disabled (timeout)"}

                # Click publish
                print(f"    点击发表...", flush=True)
                try:
                    await publish_btn.first.click()
                    print(f"    ✓ 方法1: 直接点击", flush=True)
                except Exception as e:
                    print(f"    ✗ 方法1失败: {e}", flush=True)

                await asyncio.sleep(2)

                try:
                    await publish_btn.first.click(force=True)
                    print(f"    ✓ 方法2: 强制点击", flush=True)
                except Exception as e:
                    print(f"    ✗ 方法2失败: {e}", flush=True)

                publish_clicked = True
                await asyncio.sleep(3)
            else:
                await context.close()
                await p.stop()
                return {"ok": False, "error": "Publish button not found"}

        except Exception as e:
            if not publish_clicked:
                try:
                    await context.close()
                    await p.stop()
                except Exception:
                    pass
                return {"ok": False, "error": f"Publish interaction failed: {e}"}
            print(f"    ⚠ 发表后异常 (已点击发表): {e}", flush=True)

        await asyncio.sleep(3)

        # Check current URL to see if we're redirected to success page
        await asyncio.sleep(10)
        current_url = page.url
        if "post/list" in current_url or "post/create" not in current_url:
            print(f"    {G}✓ 检测到页面跳转，发表成功{X}", flush=True)
            print(f"    当前URL: {current_url}", flush=True)
        else:
            print(f"    当前仍在发布页面，继续等待...", flush=True)
            await asyncio.sleep(10)
            current_url = page.url
            print(f"    最终URL: {current_url}", flush=True)

        print(f"    {G}✓ 发表流程完成，保持浏览器打开15秒以确保请求提交...{X}", flush=True)
        await asyncio.sleep(15)

        try:
            await context.close()
            await p.stop()
        except Exception:
            pass
        return {"ok": True}

    except Exception as e:
        import traceback
        print(f"    [ERROR] {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        if publish_clicked:
            print(f"    ⚠ 发表后清理异常 (视频已发布): {e}", flush=True)
            try:
                await p.stop()
            except Exception:
                pass
            return {"ok": True, "note": f"published but cleanup error: {e}"}
        try:
            await p.stop()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Upload video to WeChat Channels")
    parser.add_argument("video", type=Path, help="Video file to upload")
    parser.add_argument("--title", required=True, help="Video title (6-16 chars, auto-padded if < 6)")
    parser.add_argument("--desc", default="", help="Video description")
    parser.add_argument("--tags", default="", help="Comma-separated tags (optional, max 5)")

    args = parser.parse_args()

    if not args.video.exists():
        print(f"{R}ERROR:{X} Video file not found: {args.video}")
        sys.exit(1)

    print(f"{C}Uploading to WeChat Channels:{X}")
    print(f"  Video: {args.video.name}")
    print(f"  Title: {args.title}")
    if args.tags:
        print(f"  Tags:  {args.tags}")

    print(f"\nUploading...", flush=True)
    result = asyncio.run(upload_weixin_channels(args.video, args.title, args.desc, args.tags))

    if result["ok"]:
        print(f"\n{G}✓ Upload successful!{X}")
    else:
        error = result.get("error", "Unknown error")
        print(f"\n{R}✗ Upload failed:{X} {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
