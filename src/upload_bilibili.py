#!/usr/bin/env python3
"""
upload_bilibili.py - Standalone Bilibili upload script
=======================================================
Uploads video to Bilibili with metadata (title, tags, description, cover).

Usage:
    python src/upload_bilibili.py video.mp4 --title "标题" --tags "tag1,tag2"
    python src/upload_bilibili.py video.mp4 --cover cover.jpg --desc "描述"
    python src/upload_bilibili.py video.mp4 --auto-login  # Auto-login if no cookies

Requires:
    pip install "biliup>=1.1.29"
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Windows GBK fix
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COOKIE_FILE = PROJECT_ROOT / "cookies" / "bilibili" / "account.json"
BILIUP_EXE = PROJECT_ROOT / "vendor" / "biliup.exe"

G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; D = "\033[2m"; X = "\033[0m"


def ensure_bilibili_login() -> bool:
    """Ensure Bilibili login via biliup CLI QR code scan.

    Returns:
        True if logged in (or login succeeded), False otherwise
    """
    if COOKIE_FILE.exists():
        print(f"{G}✓ Bilibili cookies found{X}")
        return True

    if not BILIUP_EXE.exists():
        print(f"{R}ERROR:{X} biliup.exe not found at {BILIUP_EXE}")
        print(f"Download from: https://github.com/biliup/biliup-rs/releases")
        return False

    print(f"\n{'='*50}")
    print(f"{Y}请用B站App扫描终端二维码登录{X}")
    print(f"{'='*50}\n")

    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [str(BILIUP_EXE), "login"],
        cwd=str(COOKIE_FILE.parent),
        capture_output=False,  # Show QR code in terminal
    )

    if result.returncode == 0 and COOKIE_FILE.exists():
        print(f"\n{G}✓ Bilibili login successful!{X}")
        return True
    else:
        print(f"\n{R}✗ Bilibili login failed{X}")
        return False


def upload_bilibili(video_path: Path, title: str, tags: str, desc: str, cover_path: Path = None) -> dict:
    """Upload video to Bilibili using biliup library.

    Args:
        video_path: Path to video file
        title: Video title
        tags: Comma-separated tags
        desc: Video description
        cover_path: Optional cover image path

    Returns:
        dict with {"ok": bool, "bvid": str} or {"ok": bool, "error": str}
    """
    try:
        from biliup.plugins.bili_webup import BiliBili, Data
    except ImportError:
        return {"ok": False, "error": "biliup not installed. Run: pip install 'biliup>=1.1.29'"}

    if not COOKIE_FILE.exists():
        return {"ok": False, "error": "No Bilibili cookies. Run with --auto-login first."}

    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie_data = json.load(f)
    except Exception as e:
        return {"ok": False, "error": f"Failed to load cookies: {e}"}

    # Prepare metadata
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    meta = Data()
    meta.title = title
    meta.desc = desc
    meta.tag = tag_list
    meta.copyright = 1  # Original content

    # Convert Path to str for biliup compatibility
    video_str = str(video_path)
    cover_str = str(cover_path) if cover_path else None

    try:
        print(f"使用cookies上传")
        bili = BiliBili(cookie_data)
        ret = bili.upload_file(video_str, lines="AUTO", tasks=3)

        if ret:
            video_id = bili.submit(cover=cover_str)
            if video_id:
                return {"ok": True, "bvid": video_id}
            else:
                return {"ok": False, "error": "Submit failed (no video ID returned)"}
        else:
            return {"ok": False, "error": "Upload failed"}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Upload video to Bilibili")
    parser.add_argument("video", type=Path, help="Video file to upload")
    parser.add_argument("--title", required=True, help="Video title")
    parser.add_argument("--tags", required=True, help="Comma-separated tags (max 12, each max 20 chars)")
    parser.add_argument("--desc", default="", help="Video description")
    parser.add_argument("--cover", type=Path, help="Cover image (optional)")
    parser.add_argument("--auto-login", action="store_true", help="Auto-login if no cookies")

    args = parser.parse_args()

    if not args.video.exists():
        print(f"{R}ERROR:{X} Video file not found: {args.video}")
        sys.exit(1)

    if args.cover and not args.cover.exists():
        print(f"{R}ERROR:{X} Cover file not found: {args.cover}")
        sys.exit(1)

    # Check/ensure login
    if args.auto_login and not COOKIE_FILE.exists():
        if not ensure_bilibili_login():
            print(f"{R}ERROR:{X} Login failed")
            sys.exit(1)

    print(f"{C}Uploading to Bilibili:{X}")
    print(f"  Video: {args.video.name}")
    print(f"  Title: {args.title}")
    print(f"  Tags:  {args.tags}")
    if args.cover:
        print(f"  Cover: {args.cover.name}")

    print(f"\nUploading...", flush=True)
    result = upload_bilibili(args.video, args.title, args.tags, args.desc, args.cover)

    if result["ok"]:
        bvid = result.get("bvid", "")
        print(f"\n{G}✓ Upload successful!{X}")
        print(f"BV号: {bvid}")
        print(f"链接: https://www.bilibili.com/video/{bvid}")
    else:
        error = result.get("error", "Unknown error")
        print(f"\n{R}✗ Upload failed:{X} {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
