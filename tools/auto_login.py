"""
auto_login.py — NotebookLM authentication manager.

Three modes:
  --refresh   Try to refresh auth silently (headless, no user interaction needed)
  --check     Just check if current auth is valid (exit 0=ok, 1=expired)
  (default)   Open browser for manual Google login

Usage:
  python tools/auto_login.py              # Manual login (opens browser)
  python tools/auto_login.py --refresh    # Silent refresh (try headless first)
  python tools/auto_login.py --check      # Check auth validity
"""
import sys, os, time, argparse, json
from pathlib import Path

if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")

HOME_DIR = Path.home() / ".notebooklm"
STORAGE_PATH = HOME_DIR / "storage_state.json"
PROFILE_DIR = HOME_DIR / "browser_profile"
NOTEBOOKLM_URL = "https://notebooklm.google.com/"

G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; D = "\033[2m"; X = "\033[0m"


def _ensure_dirs():
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)


def check_auth() -> bool:
    """Check if current NotebookLM auth is valid (headless)."""
    if not STORAGE_PATH.exists():
        print(f"{R}✗{X} 认证文件不存在: {STORAGE_PATH}")
        return False

    # Check file age (>7 days is suspicious)
    age_hours = (time.time() - STORAGE_PATH.stat().st_mtime) / 3600
    if age_hours > 168:  # 7 days
        print(f"{Y}⚠{X} 认证文件已 {int(age_hours)}小时 未更新，可能过期")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"{Y}⚠{X} playwright 未安装，无法验证")
        return STORAGE_PATH.exists()

    print(f"{D}正在验证认证状态...{X}", flush=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.pages[0] if browser.pages else browser.new_page()

            try:
                page.goto(NOTEBOOKLM_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)
                url = page.url
            except Exception as e:
                print(f"{R}✗{X} 无法访问 NotebookLM: {e}")
                browser.close()
                return False

            # If redirected to Google login, auth is expired
            if "accounts.google.com" in url:
                print(f"{R}✗{X} 认证已过期 (重定向到 Google 登录)")
                browser.close()
                return False

            if "notebooklm.google.com" in url:
                print(f"{G}✓{X} 认证有效")
                browser.close()
                return True

            print(f"{Y}⚠{X} 未知状态，URL: {url[:80]}")
            browser.close()
            return False
    except Exception as e:
        print(f"{Y}⚠{X} 验证失败: {e}")
        return False


def refresh_auth() -> bool:
    """Try to refresh auth silently using existing browser profile.
    
    If the persistent browser profile has valid Google cookies, we can
    navigate to NotebookLM headlessly and re-save the storage state.
    No user interaction needed.
    """
    _ensure_dirs()

    if not PROFILE_DIR.exists() or not any(PROFILE_DIR.iterdir()):
        print(f"{Y}⚠{X} 无浏览器 profile，需要手动登录")
        return False

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"{R}✗{X} playwright 未安装")
        return False

    print(f"[1] 尝试无头刷新认证...", flush=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.pages[0] if browser.pages else browser.new_page()

            try:
                page.goto(NOTEBOOKLM_URL, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"  {R}访问失败: {e}{X}")
                browser.close()
                return False

            # Wait for page to settle
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            url = page.url

            if "accounts.google.com" in url:
                print(f"  {Y}Google cookie 已过期，需要手动登录{X}")
                browser.close()
                return False

            if "notebooklm.google.com" in url:
                # Success — save fresh storage state
                browser.storage_state(path=str(STORAGE_PATH))
                browser.close()
                size = STORAGE_PATH.stat().st_size
                print(f"  {G}✓ 认证刷新成功!{X} ({size} bytes)")
                return True

            print(f"  {Y}未知页面: {url[:80]}{X}")
            browser.close()
            return False

    except Exception as e:
        print(f"  {R}刷新失败: {e}{X}")
        return False


def manual_login() -> bool:
    """Open browser for manual Google login."""
    _ensure_dirs()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"{R}ERROR:{X} playwright 未安装")
        print(f"  运行: pip install playwright && python -m playwright install chromium")
        return False

    print(f"[1] 打开浏览器进行 Google 登录...")
    print(f"    Storage: {STORAGE_PATH}")
    print(f"    Profile: {PROFILE_DIR}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto(NOTEBOOKLM_URL, wait_until="domcontentloaded", timeout=120000)

            print("[2] 等待 NotebookLM 页面加载...")
            print("    如果弹出 Google 登录页面，请完成登录。")
            print("    脚本会自动检测登录完成。\n")

            # Poll until on NotebookLM (not Google login)
            max_wait = 600  # 10 minutes
            start = time.time()
            while time.time() - start < max_wait:
                url = page.url
                if "notebooklm.google.com" in url and "accounts.google.com" not in url:
                    try:
                        page.wait_for_load_state("networkidle", timeout=20000)
                    except Exception:
                        pass
                    if "notebooklm.google.com" in page.url:
                        print(f"\n[3] NotebookLM 加载完成! URL: {page.url}")
                        break
                elapsed = int(time.time() - start)
                print(f"    等待登录中... ({elapsed}s)", end="\r", flush=True)
                time.sleep(2)
            else:
                print(f"\n{R}ERROR:{X} 登录超时 (10分钟)")
                browser.close()
                return False

            # Save
            print("[4] 保存认证信息...")
            browser.storage_state(path=str(STORAGE_PATH))
            browser.close()

        size = STORAGE_PATH.stat().st_size
        print(f"\n{G}✓ 认证保存成功!{X} {STORAGE_PATH} ({size} bytes)")
        return True

    except Exception as e:
        print(f"\n{R}ERROR:{X} {e}")
        return False


def auto_login() -> bool:
    """Smart login: try refresh first, fallback to manual.
    
    1. Try headless refresh (no user interaction)
    2. If that fails, open browser for manual login
    """
    _ensure_dirs()
    print(f"{'='*50}")
    print(f"  NotebookLM 认证管理")
    print(f"{'='*50}\n")

    # Step 1: Try silent refresh
    if refresh_auth():
        return True

    print(f"\n[自动刷新失败，切换到手动登录]\n")

    # Step 2: Manual login
    return manual_login()


def main():
    parser = argparse.ArgumentParser(description="NotebookLM authentication manager")
    parser.add_argument("--check", action="store_true",
                        help="Check if auth is valid (exit 0=ok, 1=expired)")
    parser.add_argument("--refresh", action="store_true",
                        help="Try to refresh auth silently (headless)")
    parser.add_argument("--manual", action="store_true",
                        help="Force manual browser login")
    args = parser.parse_args()

    if args.check:
        ok = check_auth()
        sys.exit(0 if ok else 1)
    elif args.refresh:
        ok = refresh_auth()
        if not ok:
            print(f"\n{Y}无头刷新失败。请运行不带参数的命令进行手动登录:{X}")
            print(f"  python tools/auto_login.py")
        sys.exit(0 if ok else 1)
    elif args.manual:
        ok = manual_login()
        sys.exit(0 if ok else 1)
    else:
        ok = auto_login()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
