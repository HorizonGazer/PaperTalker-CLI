#!/usr/bin/env python3
"""
setup_cron.py - OpenClaw cron registration helper
==================================================
Generates the openclaw cron command to register daily PaperTalker pipeline.

Usage:
    python setup_cron.py                          # Show command (default: 10 AM daily)
    python setup_cron.py --time "14:30"           # Custom time (24h format)
    python setup_cron.py --with-tracker           # Also register 8:30 AM auto_tracker
    python setup_cron.py --execute                # Auto-execute the command

Example output:
    openclaw cron add --name "Daily PaperTalker" --cron "0 10 * * *" \\
      --session isolated --message "Run today's scheduled paper reading..."
"""

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# ── Colors ──────────────────────────────────────────────────
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; B = "\033[1m"; D = "\033[2m"; X = "\033[0m"


def time_to_cron(time_str: str) -> str:
    """Convert HH:MM to cron expression (minute hour * * *)."""
    try:
        hour, minute = map(int, time_str.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
        return f"{minute} {hour} * * *"
    except Exception:
        print(f"  {R}Invalid time format: {time_str}. Use HH:MM (24h).{X}")
        sys.exit(1)


def generate_command(cron_expr: str, name: str, message: str) -> str:
    """Generate openclaw cron add command."""
    cmd = (
        f'openclaw cron add --name "{name}" --cron "{cron_expr}" '
        f'--session isolated --message "{message}"'
    )
    return cmd


def execute_command(cmd: str, name: str):
    """Execute a single openclaw cron command."""
    print(f"  {Y}Registering: {name}...{X}")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"  {G}Success!{X}")
        if result.stdout:
            print(f"  {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"  {R}Failed: {e}{X}")
        if e.stderr:
            print(f"  {e.stderr.strip()}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Setup OpenClaw cron for PaperTalker")
    parser.add_argument("--time", default="10:00", help="Daily pipeline run time (HH:MM, default: 10:00)")
    parser.add_argument("--name", default="Daily PaperTalker", help="Cron job name")
    parser.add_argument("--with-tracker", action="store_true",
                        help="Also register auto_tracker.py cron (default: 08:30)")
    parser.add_argument("--tracker-time", default="08:30",
                        help="Auto tracker run time (HH:MM, default: 08:30)")
    parser.add_argument("--execute", action="store_true", help="Execute the command(s) automatically")
    args = parser.parse_args()

    commands = []

    # ── Tracker cron (optional) ──
    if args.with_tracker:
        tracker_cron = time_to_cron(args.tracker_time)
        tracker_msg = (
            "Run auto_tracker.py --write-schedule to discover trending papers "
            "in biomedical+AI domains and write to schedule.txt. "
            f"Execute: cd {PROJECT_ROOT} && python auto_tracker.py --write-schedule"
        )
        tracker_cmd = generate_command(tracker_cron, "PaperTalker Auto Tracker", tracker_msg)
        commands.append(("PaperTalker Auto Tracker", args.tracker_time, tracker_cron, tracker_cmd))

    # ── Pipeline cron ──
    pipeline_cron = time_to_cron(args.time)
    pipeline_msg = (
        "Run today's scheduled paper reading from schedule.txt. "
        f"Execute: cd {PROJECT_ROOT} && python run_scheduled.py"
    )
    if not args.with_tracker:
        # Single-cron mode: embed auto_tracker as pre-hook
        pipeline_msg = (
            "Run auto_tracker then today's scheduled paper reading. "
            f"Execute: cd {PROJECT_ROOT} && python run_scheduled.py "
            "--pre-hook 'auto_tracker.py --write-schedule'"
        )
    pipeline_cmd = generate_command(pipeline_cron, args.name, pipeline_msg)
    commands.append((args.name, args.time, pipeline_cron, pipeline_cmd))

    # ── Display ──
    print(f"\n{B}OpenClaw Cron Setup{X}")
    print(f"{'='*60}")
    for name, time_str, cron_expr, _ in commands:
        print(f"  {C}{name}{X}: {time_str} daily ({cron_expr})")
    print(f"  Script: {PROJECT_ROOT / 'run_scheduled.py'}")
    if args.with_tracker:
        print(f"  Tracker: {PROJECT_ROOT / 'auto_tracker.py'}")
    print(f"{'='*60}\n")

    for name, _, _, cmd in commands:
        print(f"{B}[{name}] Command:{X}")
        print(f"  {D}{cmd}{X}\n")

    if args.execute:
        all_ok = True
        for name, _, _, cmd in commands:
            if not execute_command(cmd, name):
                all_ok = False
        if not all_ok:
            sys.exit(1)
        print(f"\n  {G}All cron jobs registered!{X}\n")
    else:
        print(f"  {D}To register, run:{X}")
        print(f"    python setup_cron.py --execute")
        if not args.with_tracker:
            print(f"    python setup_cron.py --with-tracker --execute  # with auto tracker")
        print(f"  {D}Or copy the commands above and run them manually.{X}\n")


if __name__ == "__main__":
    main()
