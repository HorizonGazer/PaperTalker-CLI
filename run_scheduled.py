#!/usr/bin/env python3
"""
run_scheduled.py - Daily scheduled pipeline entry point
========================================================
Reads schedule.txt (tab-separated), picks today's topic, runs Phase 1 (quick_video)
and Phase 2 (publish.py) sequentially.

Usage:
    python run_scheduled.py                  # Run today's scheduled topic
    python run_scheduled.py --dry-run        # Show what would run without executing
    python run_scheduled.py --force "topic"  # Override with a specific topic

Designed for OpenClaw cron integration (see setup_cron.py).
"""

import argparse
import asyncio
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Windows GBK fix
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent
SCHEDULE_FILE = PROJECT_ROOT / "schedule.txt"
HISTORY_FILE = PROJECT_ROOT / "run_history.txt"

# ── Colors ──────────────────────────────────────────────────
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; B = "\033[1m"; D = "\033[2m"; X = "\033[0m"


def load_schedule() -> list[dict]:
    """Load schedule.txt, return empty list if missing.

    Returns list of dicts with keys: date, topic, source_mode, platforms, max_results, status, completed_at, notes, line_num
    """
    if not SCHEDULE_FILE.exists():
        print(f"  {Y}schedule.txt not found, creating template...{X}")
        template = """# PaperTalker Schedule (Tab-Separated Format)
# Columns: date	topic	source_mode	platforms	max_results	status	completed_at	notes
#
# Legal Values:
#   date: YYYY-MM-DD or "queue"
#   source_mode: research, search, file, paper
#   platforms: bilibili, douyin, weixin_channels, weixin_article, xiaohongshu, kuaishou (comma-separated)
#   max_results: positive integer (1-50)
#   status: pending, completed, failed
#
# ────────────────────────────────────────────────────────────────────────────

queue	示例主题	research	bilibili,weixin_channels	5	pending
"""
        SCHEDULE_FILE.write_text(template, encoding="utf-8")
        return []

    lines = SCHEDULE_FILE.read_text(encoding="utf-8").splitlines()
    entries = []

    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) < 6:
            continue  # Skip malformed lines

        entry = {
            "date": parts[0],
            "topic": parts[1],
            "source_mode": parts[2] if len(parts) > 2 else "research",
            "platforms": parts[3] if len(parts) > 3 else "bilibili",
            "max_results": int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 5,
            "status": parts[5] if len(parts) > 5 else "pending",
            "completed_at": parts[6] if len(parts) > 6 else "",
            "notes": parts[7] if len(parts) > 7 else "",
            "line_num": i,
        }
        entries.append(entry)

    return entries


def save_schedule(entries: list[dict]):
    """Persist schedule.txt."""
    lines = SCHEDULE_FILE.read_text(encoding="utf-8").splitlines()

    # Preserve header comments
    header_lines = []
    for line in lines:
        if line.strip().startswith("#") or not line.strip():
            header_lines.append(line)
        else:
            break

    # Rebuild data lines
    data_lines = []
    for entry in entries:
        parts = [
            entry["date"],
            entry["topic"],
            entry.get("source_mode", "research"),
            entry.get("platforms", "bilibili"),
            str(entry.get("max_results", 5)),
            entry.get("status", "pending"),
            entry.get("completed_at", ""),
            entry.get("notes", ""),
        ]
        data_lines.append("\t".join(parts))

    content = "\n".join(header_lines + data_lines) + "\n"
    SCHEDULE_FILE.write_text(content, encoding="utf-8")


def pick_topic(entries: list[dict]) -> dict | None:
    """Select today's topic from schedule.

    Priority:
    1. Date-matched pending topic (exact match on today's date)
    2. First pending item from queue (FIFO)

    Returns:
        dict with topic entry or None if nothing scheduled
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Check date-specific topics
    for entry in entries:
        if entry["date"] == today and entry["status"] == "pending":
            return entry

    # Fall back to queue
    for entry in entries:
        if entry["date"] == "queue" and entry["status"] == "pending":
            return entry

    return None


def mark_completed(entries: list[dict], topic_entry: dict, success: bool = True):
    """Mark topic as completed/failed in schedule and save."""
    for entry in entries:
        if entry is topic_entry:
            entry["status"] = "completed" if success else "failed"
            entry["completed_at"] = datetime.now().isoformat(timespec="seconds")
            break

    save_schedule(entries)

    # Append to run_history.txt
    status = "completed" if success else "failed"
    history_line = (
        f"{datetime.now().isoformat(timespec='seconds')}\t"
        f"{topic_entry['topic']}\t"
        f"{topic_entry['source_mode']}\t"
        f"{topic_entry.get('platforms', '')}\t"
        f"{status}\n"
    )
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(history_line)


def print_schedule_overview(entries: list[dict]):
    """Print schedule overview before picking topic."""
    today = datetime.now().strftime("%Y-%m-%d")
    pending = [e for e in entries if e["status"] == "pending"]
    completed = [e for e in entries if e["status"] == "completed"]
    failed = [e for e in entries if e["status"] == "failed"]

    print(f"  {B}日程概览:{X} {len(pending)} 待执行 | {len(completed)} 已完成 | {len(failed)} 失败")

    # Check for stale date-specific entries (past dates still pending)
    stale = [e for e in pending if e["date"] != "queue" and e["date"] < today]
    if stale:
        print(f"  {Y}提醒: {len(stale)} 个过期未执行的主题{X}")
        for e in stale:
            print(f"    {D}{e['date']}  {e['topic'][:40]}{X}")
    print()


def get_python() -> str:
    """Get the Python interpreter path (prefer conda env)."""
    return sys.executable


async def run_phase1(topic: str, source_mode: str, defaults: dict) -> bool:
    """Run Phase 1: quick_video.py (in-process async)."""
    print(f"\n{'='*60}")
    print(f"  {B}Phase 1: Generate Video{X}")
    print(f"  Topic: {C}{topic}{X}")
    print(f"  Source: {source_mode}")
    print(f"{'='*60}\n")

    try:
        # Import and run in-process (same async loop)
        sys.path.insert(0, str(PROJECT_ROOT))
        from quick_video import run

        result = await run(
            topic=topic,
            source_mode=source_mode,
            no_confirm=True,  # Automated mode
            platforms=defaults.get("search_platforms"),
            max_results=defaults.get("max_results", 5),
        )

        if result:
            print(f"\n  {G}Phase 1 completed: {result}{X}")
            return True
        else:
            print(f"\n  {R}Phase 1 failed (no output){X}")
            return False

    except Exception as e:
        print(f"\n  {R}Phase 1 error: {e}{X}")
        return False


def run_phase2(defaults: dict) -> bool:
    """Run Phase 2: publish.py (subprocess for GPU memory isolation)."""
    print(f"\n{'='*60}")
    print(f"  {B}Phase 2: Subtitle + Upload{X}")
    print(f"{'='*60}\n")

    python = get_python()
    publish_script = str(PROJECT_ROOT / "publish.py")
    platforms = defaults.get("platforms", ["bilibili", "weixin_channels"])

    cmd = [python, "-u", publish_script, "--platforms"] + platforms

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            timeout=3600,  # 60 min timeout
        )

        if result.returncode == 0:
            print(f"\n  {G}Phase 2 completed successfully{X}")
            return True
        else:
            print(f"\n  {R}Phase 2 failed (exit code {result.returncode}){X}")
            return False

    except subprocess.TimeoutExpired:
        print(f"\n  {R}Phase 2 timed out (60 min){X}")
        return False
    except Exception as e:
        print(f"\n  {R}Phase 2 error: {e}{X}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Run scheduled PaperTalker pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    parser.add_argument("--force", type=str, help="Override with a specific topic")
    parser.add_argument("--skip-phase2", action="store_true", help="Only run Phase 1 (video generation)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result (for OpenClaw)")
    parser.add_argument("--source-args", type=str, help="Extra args for quick_video.py source (JSON string)")
    parser.add_argument("--publish-platforms", nargs="+", help="Override publish platforms (default from schedule)")
    parser.add_argument("--pre-hook", type=str, help="Script to run before topic selection (e.g., 'auto_tracker.py --write-schedule')")
    parser.add_argument("--post-hook", type=str, help="Script to run after pipeline completion")
    args = parser.parse_args()

    print(f"\n{B}PaperTalker Scheduled Run{X}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # ── Pre-hook (e.g., auto_tracker.py --write-schedule) ──
    if args.pre_hook:
        print(f"  {C}Running pre-hook:{X} {args.pre_hook}")
        hook_env = os.environ.copy()
        hook_env["PYTHONIOENCODING"] = "utf-8"
        hook_env["PYTHONUNBUFFERED"] = "1"
        try:
            hook_result = subprocess.run(
                [get_python(), "-u"] + shlex.split(args.pre_hook),
                cwd=str(PROJECT_ROOT),
                env=hook_env,
                timeout=300,
            )
            if hook_result.returncode != 0:
                print(f"  {Y}Pre-hook exited with code {hook_result.returncode}, continuing...{X}")
        except subprocess.TimeoutExpired:
            print(f"  {Y}Pre-hook timed out (300s), continuing...{X}")
        except Exception as e:
            print(f"  {Y}Pre-hook error: {e}, continuing...{X}")
        print()

    entries = load_schedule()

    # ── Schedule overview (pre-run check) ──
    if entries:
        print_schedule_overview(entries)

    # Determine topic
    if args.force:
        topic_entry = {
            "date": "force",
            "topic": args.force,
            "source_mode": "research",
            "platforms": "bilibili,weixin_channels",
            "max_results": 5,
            "status": "pending",
            "completed_at": "",
            "notes": "",
        }
        print(f"  {Y}Forced topic: {args.force}{X}")
    else:
        topic_entry = pick_topic(entries)
        if not topic_entry:
            print(f"  {Y}No pending topics scheduled for today.{X}")
            print(f"  {D}Add topics to schedule.txt or use --force \"topic\"{X}")
            return

    platforms_str = topic_entry.get("platforms", "bilibili")
    platforms_list = args.publish_platforms or [p.strip() for p in platforms_str.split(",")]

    print(f"  Topic: {C}{topic_entry['topic']}{X}")
    print(f"  Source mode: {topic_entry['source_mode']}")
    print(f"  Platforms: {platforms_list}")
    print()

    if args.dry_run:
        print(f"  {Y}[DRY RUN] Would run the above pipeline. Exiting.{X}")
        return

    defaults = {
        "source_mode": topic_entry["source_mode"],
        "platforms": platforms_list,
        "max_results": topic_entry.get("max_results", 5),
    }

    # Phase 1: Generate video
    phase1_ok = await run_phase1(topic_entry["topic"], topic_entry["source_mode"], defaults)

    if not phase1_ok:
        print(f"\n{R}Pipeline aborted after Phase 1 failure.{X}")
        if topic_entry["date"] != "force":
            mark_completed(entries, topic_entry, success=False)
        return

    # Phase 2: Subtitle + Upload (subprocess)
    if not args.skip_phase2:
        phase2_ok = run_phase2(defaults)
    else:
        print(f"  {Y}Phase 2 skipped (--skip-phase2){X}")
        phase2_ok = True

    # Mark completed
    if phase1_ok and topic_entry["date"] != "force":
        mark_completed(entries, topic_entry, success=True)
        print(f"\n  {G}Topic marked as completed in schedule.txt{X}")

    # Summary
    summary = {
        "topic": topic_entry["topic"],
        "source_mode": topic_entry["source_mode"],
        "platforms": platforms_list,
        "phase1": "ok" if phase1_ok else "fail",
        "phase2": "ok" if phase2_ok else ("skip" if args.skip_phase2 else "fail"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }

    if args.json:
        import json
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"\n{'='*60}")
        print(f"  {B}Pipeline Summary{X}")
        print(f"  Topic:   {topic_entry['topic']}")
        print(f"  Phase 1: {'OK' if phase1_ok else 'FAIL'}")
        print(f"  Phase 2: {'OK' if phase2_ok else 'FAIL'}")
        print(f"{'='*60}\n")

    # ── Post-hook ──
    if args.post_hook:
        print(f"  {C}Running post-hook:{X} {args.post_hook}")
        hook_env = os.environ.copy()
        hook_env["PYTHONIOENCODING"] = "utf-8"
        hook_env["PYTHONUNBUFFERED"] = "1"
        try:
            subprocess.run(
                [get_python(), "-u"] + shlex.split(args.post_hook),
                cwd=str(PROJECT_ROOT),
                env=hook_env,
                timeout=300,
            )
        except Exception as e:
            print(f"  {Y}Post-hook error: {e}{X}")

    # Exit code: 0 if both phases ok, 1 otherwise (for cron/OpenClaw)
    if not phase1_ok or (not args.skip_phase2 and not phase2_ok):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
