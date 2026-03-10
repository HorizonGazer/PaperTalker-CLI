#!/usr/bin/env python3
"""
WeChat Channels upload worker - runs in isolated subprocess.

Uses Playwright ASYNC API to avoid sync_playwright()'s event loop conflicts.
Called by publish.py via subprocess with JSON args.

Usage:
    python _weixin_upload_worker.py '<json_args>' '<result_file>'
"""
import asyncio
import json
import sys
import time
from pathlib import Path

# Patch asyncio to allow nested event loops (Windows Playwright compat)
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent
WEIXIN_STORAGE_STATE = PROJECT_ROOT / "cookies" / "weixin" / "storage_state.json"

G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; X = "\033[0m"


async def upload_weixin_channels_async(video_path: str, title: str, desc: str, tags: str, cover_path: str = None) -> dict:
    """Upload video to WeChat Channels using async Playwright API."""
    from playwright.async_api import async_playwright

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
        print(f"  {Y}正在打开发布页面 https://channels.weixin.qq.com/platform/post/create{X}", flush=True)
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

        # Wait for file input - try multiple strategies
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

        if not file_input_found:
            # Debug: list all frames and their URLs
            print(f"    [DEBUG] 页面frames ({len(page.frames)}):", flush=True)
            for i, frame in enumerate(page.frames):
                print(f"      [{i}] {frame.url[:100]}", flush=True)
            # Try clicking the upload area/button to trigger file input
            print(f"    尝试点击上传区域...", flush=True)
            upload_area_selectors = [
                'div.upload-content',
                'div[class*="upload"]',
                'div.post-cover-uploader',
                'button:has-text("上传视频")',
                'span:has-text("上传视频")',
                'div:has-text("点击上传")',
            ]
            for sel in upload_area_selectors:
                try:
                    elem = upload_frame.locator(sel)
                    if await elem.count() > 0 and await elem.first.is_visible():
                        print(f"    找到上传区域: {sel}", flush=True)
                        await elem.first.click()
                        await asyncio.sleep(2)
                        break
                except Exception:
                    pass
            # Re-check for file input after click
            try:
                await upload_frame.wait_for_selector('input[type="file"]', timeout=10000, state="attached")
                file_input_found = True
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
                    # Fallback: try clicking any upload button/area
                    for sel in ['div.upload-content', 'div[class*="upload-btn"]', 'button:has-text("上传")']:
                        try:
                            elem = page.locator(sel)
                            if await elem.count() > 0:
                                await elem.first.click()
                                clicked = True
                                break
                        except Exception:
                            continue
                if not clicked:
                    await context.close()
                    await p.stop()
                    return {"ok": False, "error": "Cannot find file input or upload button"}
        except Exception as e:
            await context.close()
            await p.stop()
            return {"ok": False, "error": f"File chooser failed: {e}"}

        file_chooser = await fc_info.value
        await file_chooser.set_files(video_path)
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
                    # Try saving as draft
                    draft_btn = upload_frame.locator('button:has-text("保存草稿")')
                    if await draft_btn.count() > 0:
                        draft_cls = await draft_btn.first.get_attribute("class") or ""
                        if "disabled" not in draft_cls:
                            await draft_btn.first.click()
                            print(f"    ✓ 已保存为草稿", flush=True)
                            await asyncio.sleep(3)
                            await context.close()
                            await p.stop()
                            return {"ok": True, "note": "saved as draft"}
                    await context.close()
                    await p.stop()
                    return {"ok": False, "error": "Publish button disabled (timeout)"}

                # Click publish — try multiple methods to ensure it works
                print(f"    点击发表...", flush=True)

                # Method 1: Direct click
                try:
                    await publish_btn.first.click()
                    print(f"    ✓ 方法1: 直接点击", flush=True)
                except Exception as e:
                    print(f"    ✗ 方法1失败: {e}", flush=True)

                await asyncio.sleep(2)

                # Method 2: JavaScript click (more reliable)
                try:
                    await upload_frame.evaluate('document.querySelector("button:has-text(\\"发表\\")").click()')
                    print(f"    ✓ 方法2: JS点击", flush=True)
                except Exception as e:
                    print(f"    ✗ 方法2失败: {e}", flush=True)

                await asyncio.sleep(2)

                # Method 3: Force click
                try:
                    await publish_btn.first.click(force=True)
                    print(f"    ✓ 方法3: 强制点击", flush=True)
                except Exception as e:
                    print(f"    ✗ 方法3失败: {e}", flush=True)

                publish_clicked = True
                await asyncio.sleep(3)

                # Debug: List all visible buttons after clicking publish
                print(f"    [DEBUG] 检查页面上所有按钮...", flush=True)
                try:
                    all_buttons = upload_frame.locator('button')
                    btn_count = await all_buttons.count()
                    print(f"    [DEBUG] 找到 {btn_count} 个按钮", flush=True)
                    for i in range(min(btn_count, 10)):  # Check first 10 buttons
                        try:
                            btn_text = await all_buttons.nth(i).inner_text()
                            is_visible = await all_buttons.nth(i).is_visible()
                            if is_visible and btn_text.strip():
                                print(f"    [DEBUG] 按钮 {i+1}: '{btn_text.strip()}'", flush=True)
                        except Exception:
                            pass
                except Exception as e:
                    print(f"    [DEBUG] 按钮检查异常: {e}", flush=True)

                # Check for confirmation dialog after clicking publish
                print(f"    检查确认弹窗...", flush=True)
                await asyncio.sleep(2)
                try:
                    # Common confirmation dialog selectors
                    confirm_selectors = [
                        'button:has-text("确定")',
                        'button:has-text("确认")',
                        'button:has-text("发布")',
                        'div.dialog button',
                        'div.modal button',
                        'button.btn-primary',
                        'button.primary',
                    ]
                    found_confirm = False
                    for sel in confirm_selectors:
                        confirm_btn = upload_frame.locator(sel)
                        count = await confirm_btn.count()
                        if count > 0:
                            for i in range(count):
                                try:
                                    btn = confirm_btn.nth(i)
                                    if await btn.is_visible():
                                        btn_text = await btn.inner_text()
                                        # Skip if it's the original publish button
                                        if "发表" in btn_text and "确" not in btn_text:
                                            continue
                                        print(f"    检测到确认按钮: '{btn_text}' (选择器: {sel})，点击...", flush=True)
                                        await btn.click()
                                        await asyncio.sleep(1)
                                        found_confirm = True
                                        break
                                except Exception as e:
                                    print(f"    确认按钮点击异常: {e}", flush=True)
                            if found_confirm:
                                break
                    if not found_confirm:
                        print(f"    未检测到确认弹窗，可能已直接发表", flush=True)
                except Exception as e:
                    print(f"    确认弹窗检测异常: {e}", flush=True)
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
            # publish was clicked — continue to cleanup even if error occurred
            print(f"    ⚠ 发表后异常 (已点击发表): {e}", flush=True)

        await asyncio.sleep(3)

        # Step 6: Handle post-publish dialogs (best-effort)
        print(f"    检查发表后弹窗...", flush=True)

        # Check for various post-publish dialogs
        try:
            # Success message dialog
            success_selectors = [
                'div:has-text("发表成功")',
                'div:has-text("发布成功")',
                'button:has-text("我知道了")',
                'button:has-text("确定")',
            ]
            for sel in success_selectors:
                elem = upload_frame.locator(sel)
                if await elem.count() > 0:
                    try:
                        if await elem.first.is_visible():
                            print(f"    检测到成功提示: {sel}", flush=True)
                            # Try to click if it's a button
                            if 'button' in sel:
                                await elem.first.click()
                                await asyncio.sleep(1)
                            break
                    except Exception:
                        pass
        except Exception as e:
            print(f"    成功提示检测异常: {e}", flush=True)

        try:
            verify_dialog = upload_frame.locator('div.mobile-guide-qr-code')
            if await verify_dialog.count() > 0 and await verify_dialog.is_visible():
                print(f"\n  {'='*50}")
                print(f"  需要管理员扫码验证，请用微信扫描弹窗中的二维码")
                print(f"  等待验证... (最多2分钟)")
                print(f"  {'='*50}\n", flush=True)
                v_start = time.time()
                while time.time() - v_start < 120:
                    if await verify_dialog.count() == 0 or not await verify_dialog.is_visible():
                        print(f"    ✓ 验证完成", flush=True)
                        break
                    await asyncio.sleep(2)
        except Exception:
            pass

        try:
            notice_btn = upload_frame.locator('div.post-check-dialog button:has-text("我知道了")')
            if await notice_btn.count() > 0 and await notice_btn.first.is_visible():
                print(f"    点击'我知道了'按钮", flush=True)
                await notice_btn.first.click()
                await asyncio.sleep(2)
        except Exception:
            pass

        # Check current URL to see if we're redirected to success page or list page
        await asyncio.sleep(3)
        final_url = page.url
        print(f"    发表后URL: {final_url}", flush=True)

        # Wait longer to ensure publish request completes
        print(f"    等待发表请求完成...", flush=True)
        await asyncio.sleep(10)

        # Check if redirected to post list (indicates success)
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
        # If publish was already clicked, treat as success despite cleanup errors
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
    if len(sys.argv) < 3:
        print("Usage: python _weixin_upload_worker.py '<json_args>' '<result_file>'")
        sys.exit(1)

    args = json.loads(sys.argv[1])
    result_file = Path(sys.argv[2])

    result = asyncio.run(upload_weixin_channels_async(
        args["video_path"],
        args["title"],
        args["desc"],
        args["tags"],
        args.get("cover_path"),
    ))

    result_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
