#!/usr/bin/env python3
"""
setup_cron.py - OpenClaw cron registration helper
==================================================
Generates the openclaw cron command to register daily PaperTalker pipeline.

Usage:
    python setup_cron.py                    # Show command (default: 9 AM daily)
    python setup_cron.py --time "14:30"     # Custom time (24h format)
    python setup_cron.py --execute          # Auto-execute the command

Example output:
    openclaw cron add --name "Daily PaperTalker" --cron "0 9 * * *" \\
      --session isolated --message "Run today's scheduled paper reading from schedule.txt"
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


def generate_command(cron_expr: str, name: str = "Daily PaperTalker") -> str:
    """Generate openclaw cron add command."""
    run_script = PROJECT_ROOT / "run_scheduled.py"

    # OpenClaw message (what the agent sees)
    message = (
        "Run today's scheduled paper reading from schedule.txt. "
        "Execute: python run_scheduled.py"
    )

    cmd = (
        f'openclaw cron add --name "{name}" --cron "{cron_expr}" '
        f'--session isolated --message "{message}"'
    )

    return cmd


def main():
    parser = argparse.ArgumentParser(description="Setup OpenClaw cron for PaperTalker")
    parser.add_argument("--time", default="09:00", help="Daily run time (HH:MM, 24h format)")
    parser.add_argument("--name", default="Daily PaperTalker", help="Cron job name")
    parser.add_argument("--execute", action="store_true", help="Execute the command automatically")
    args = parser.parse_args()

    cron_expr = time_to_cron(args.time)
    cmd = generate_command(cron_expr, args.name)

    print(f"\n{B}OpenClaw Cron Setup{X}")
    print(f"{'='*60}")
    print(f"  Job name: {C}{args.name}{X}")
    print(f"  Schedule: {args.time} daily ({cron_expr})")
    print(f"  Script:   {PROJECT_ROOT / 'run_scheduled.py'}")
    print(f"{'='*60}\n")

    print(f"{B}Command to register:{X}")
    print(f"  {D}{cmd}{X}\n")

    if args.execute:
        print(f"  {Y}Executing command...{X}")
        try:
            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            print(f"  {G}Success!{X}")
            if result.stdout:
                print(f"\n{result.stdout}")
        except subprocess.CalledProcessError as e:
            print(f"  {R}Failed: {e}{X}")
            if e.stderr:
                print(f"\n{e.stderr}")
            sys.exit(1)
    else:
        print(f"  {D}To register, run:{X}")
        print(f"    python setup_cron.py --execute")
        print(f"  {D}Or copy the command above and run it manually.{X}\n")


if __name__ == "__main__":
    main()
