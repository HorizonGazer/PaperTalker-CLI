"""Auto-login to NotebookLM: opens browser, waits for user to login, auto-saves."""
import sys, os, time
from pathlib import Path

if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")

def auto_login():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    home = Path.home() / ".notebooklm"
    home.mkdir(parents=True, exist_ok=True)
    storage_path = home / "storage_state.json"
    profile_dir = home / "browser_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1] Opening browser for Google login...")
    print(f"    Storage: {storage_path}")
    print(f"    Profile: {profile_dir}")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://notebooklm.google.com/", wait_until="domcontentloaded", timeout=60000)

        print("[2] Waiting for NotebookLM homepage to load...")
        print("    Please complete Google login if prompted.")
        print("    Script will auto-detect when you reach the NotebookLM page.\n")

        # Poll until we're on the NotebookLM page (not a login redirect)
        max_wait = 300  # 5 minutes
        start = time.time()
        while time.time() - start < max_wait:
            url = page.url
            if "notebooklm.google.com" in url and "accounts.google.com" not in url:
                # Check if the page has loaded (look for common elements)
                try:
                    # Wait a bit for page to stabilize
                    page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass
                # Verify we're really on NotebookLM
                if "notebooklm.google.com" in page.url:
                    print(f"[3] NotebookLM loaded! URL: {page.url}")
                    break
            elapsed = int(time.time() - start)
            print(f"    Waiting... ({elapsed}s) Current URL: {url[:80]}", end="\r")
            time.sleep(2)
        else:
            print("\nERROR: Timed out waiting for NotebookLM login (5 min)")
            browser.close()
            sys.exit(1)

        # Save storage state
        print("[4] Saving authentication...")
        browser.storage_state(path=str(storage_path))
        browser.close()

    size = storage_path.stat().st_size
    print(f"\n[OK] Authentication saved: {storage_path} ({size} bytes)")
    print("     You can now run quick_video.py!")

if __name__ == "__main__":
    auto_login()
