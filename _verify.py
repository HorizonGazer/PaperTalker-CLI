"""Verify all dependencies for PaperTalker-CLI."""
import sys, os
from pathlib import Path

os.chdir(Path(__file__).parent)
from dotenv import load_dotenv
load_dotenv(".env")

checks = []

# 1
try:
    from notebooklm import NotebookLMClient, VideoStyle
    checks.append("[OK] notebooklm-py")
except Exception as e:
    checks.append(f"[FAIL] notebooklm-py: {e}")

# 2
try:
    from paper_search import search_papers, AVAILABLE_PLATFORMS
    checks.append(f"[OK] paper_search ({len(AVAILABLE_PLATFORMS)} platforms)")
except Exception as e:
    checks.append(f"[FAIL] paper_search: {e}")

# 3
import httpx
checks.append("[OK] httpx")

# 4
proxy = os.environ.get("HTTPS_PROXY", "NOT SET")
checks.append(f"[OK] proxy: {proxy}")

# 5
auth = Path.home() / ".notebooklm" / "storage_state.json"
if auth.exists():
    checks.append(f"[OK] auth: {auth.stat().st_size} bytes")
else:
    checks.append(f"[FAIL] auth: {auth} not found")

# 6
vm = Path("video.md")
if vm.exists():
    checks.append(f"[OK] video.md: {vm.stat().st_size} bytes")
else:
    checks.append(f"[FAIL] video.md not found")

for c in checks:
    print(f"  {c}")

failed = [c for c in checks if "[FAIL]" in c]
if failed:
    print(f"\n  {len(failed)} check(s) failed!")
    sys.exit(1)
else:
    print("\n  All checks passed!")
