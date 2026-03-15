#!/usr/bin/env python3
"""
auto_tracker.py - Weekly Hot Topic Paper Tracker
==================================================
Discovers high-citation papers in biomedical+AI cross-domains using the
literature-review skill (Semantic Scholar + arXiv). Runs weekly, picks the
best paper from each domain, and distributes them as date-specific entries
in schedule.txt (one topic per day).

Usage:
    python auto_tracker.py                          # Report only (dry run)
    python auto_tracker.py --write-schedule         # Write topics to schedule.txt with dates
    python auto_tracker.py --days 90 --top 5        # Custom lookback & top N for report
    python auto_tracker.py --json                   # Machine-readable output

Designed as a weekly pre-hook for run_scheduled.py:
    python run_scheduled.py --pre-hook "auto_tracker.py --write-schedule"
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Windows GBK fix
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent
SCHEDULE_FILE = PROJECT_ROOT / "schedule.txt"
TRACKER_HISTORY = PROJECT_ROOT / "tracker_history.txt"

# ── Import literature-review skill searchers ─────────────────
_SKILL_SCRIPTS = PROJECT_ROOT / "skills" / "literature-review" / "scripts"
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))

from paper_search import SemanticScholarSearcher, ArxivSearcher, Paper, deduplicate

# ── Colors ──────────────────────────────────────────────────
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"
B = "\033[1m"; D = "\033[2m"; X = "\033[0m"

# ── Domain Definitions ──────────────────────────────────────
DOMAINS = [
    {
        "name_zh": "肿瘤+AI",
        "query": "tumor cancer AI deep learning",
    },
    {
        "name_zh": "肠道+AI",
        "query": "gut microbiome AI machine learning",
    },
    {
        "name_zh": "单细胞+AI",
        "query": "single-cell RNA-seq AI deep learning",
    },
    {
        "name_zh": "空间转录组+AI",
        "query": "spatial transcriptomics AI machine learning",
    },
]


def search_domain(domain: dict, max_results: int = 20, year: str = None) -> list:
    """Search a single domain across Semantic Scholar + arXiv.

    Returns list of Paper objects.
    """
    query = domain["query"]
    all_papers = []

    # Semantic Scholar (primary - has citations + year filter)
    try:
        ss = SemanticScholarSearcher()
        kwargs = {"query": query, "max_results": max_results}
        if year:
            kwargs["year"] = year
        papers = ss.search(**kwargs)
        all_papers.extend(papers)
        print(f"    Semantic Scholar: {len(papers)} results", flush=True)
    except Exception as e:
        print(f"    {Y}Semantic Scholar failed: {e}{X}", flush=True)

    # arXiv (supplementary - no citations, no year filter)
    try:
        ax = ArxivSearcher()
        papers = ax.search(query=query, max_results=max_results)
        all_papers.extend(papers)
        print(f"    arXiv: {len(papers)} results", flush=True)
    except Exception as e:
        print(f"    {Y}arXiv failed: {e}{X}", flush=True)

    return all_papers


def filter_recent(papers: list, days: int = 90) -> list:
    """Filter papers published within the last N days."""
    cutoff = datetime.now() - timedelta(days=days)
    recent = []

    for paper in papers:
        if not paper.published_date:
            continue
        try:
            date_str = paper.published_date.strip()
            dt = None
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(date_str[:19], fmt)
                    break
                except ValueError:
                    continue
            if dt and dt >= cutoff:
                recent.append(paper)
        except Exception:
            continue

    return recent


def rank_papers(papers: list) -> list:
    """Rank papers by citations (desc), then by date (desc).

    High-citation papers are prioritized — this is the key metric
    for trending/impactful papers.
    """
    papers = deduplicate(papers)

    def sort_key(p):
        citations = p.citations or 0
        try:
            date_str = p.published_date or "1970-01-01"
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            date_val = dt.timestamp()
        except (ValueError, AttributeError):
            date_val = 0
        return (-citations, -date_val)

    papers.sort(key=sort_key)
    return papers


def generate_report(domain_results: dict, days: int, top_n: int) -> str:
    """Generate a Chinese summary report of discovered papers."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = []
    lines.append(f"\n{'═'*56}")
    lines.append(f"  PaperTalker 热点追踪报告 · {today}")
    lines.append(f"{'═'*56}\n")

    recommended_topics = []

    for domain_name, papers in domain_results.items():
        lines.append(f"── {domain_name} (过去{days}天, 按引用排序) {'─'*(30 - len(domain_name)*2)}")

        if not papers:
            lines.append(f"  {D}未发现相关论文{X}\n")
            continue

        lines.append(f"  发现 {len(papers)} 篇论文，Top {min(top_n, len(papers))}:\n")

        for i, paper in enumerate(papers[:top_n]):
            title = paper.title or "Untitled"
            date = paper.published_date or "Unknown"
            citations = paper.citations or 0
            authors = ", ".join(paper.authors[:3]) if paper.authors else "Unknown"
            if len(paper.authors) > 3:
                authors += " et al."

            lines.append(f"  {i+1}. {B}{title}{X}")
            lines.append(f"     {D}{date} | 引用: {citations} | {authors}{X}")
            if paper.doi:
                lines.append(f"     DOI: {paper.doi}")
            if paper.abstract:
                abstract_preview = paper.abstract[:150].replace("\n", " ")
                lines.append(f"     {D}{abstract_preview}...{X}")
            lines.append("")

        if papers:
            best = papers[0]
            topic_title = best.title[:60] if best.title else domain_name
            recommended_topics.append((domain_name, topic_title, best.citations or 0))

    if recommended_topics:
        lines.append(f"── 推荐主题 (按引用数排序) {'─'*32}")
        for i, (domain, title, cites) in enumerate(recommended_topics):
            lines.append(f"  {i+1}. {C}{domain}{X}: {title} (引用:{cites})")
        lines.append("")

    return "\n".join(lines)


# ── Schedule Integration ─────────────────────────────────────

def load_schedule() -> list:
    """Load schedule.txt entries."""
    if not SCHEDULE_FILE.exists():
        return []

    lines = SCHEDULE_FILE.read_text(encoding="utf-8").splitlines()
    entries = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        entries.append({
            "date": parts[0],
            "topic": parts[1],
            "source_mode": parts[2] if len(parts) > 2 else "research",
            "platforms": parts[3] if len(parts) > 3 else "bilibili,weixin_channels",
            "max_results": int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 5,
            "status": parts[5] if len(parts) > 5 else "pending",
            "completed_at": parts[6] if len(parts) > 6 else "",
            "notes": parts[7] if len(parts) > 7 else "",
            "line_num": i,
        })
    return entries


def save_schedule(entries: list):
    """Persist schedule.txt with header + data."""
    header = """# PaperTalker Schedule (Tab-Separated Format)
# Columns: date\ttopic\tsource_mode\tplatforms\tmax_results\tstatus\tcompleted_at\tnotes
#
# source_mode: research (NotebookLM, 默认) | search (literature-review) | file (本地PDF) | paper (按标题搜索)
# platforms:   bilibili,weixin_channels (逗号分隔)
# status:      pending | completed | failed
# notes:       auto_tracker = 自动追踪生成 | 用户手动添加留空
#
# ────────────────────────────────────────────────────────────────────────────
"""
    data_lines = []
    for entry in entries:
        parts = [
            entry["date"],
            entry["topic"],
            entry.get("source_mode", "research"),
            entry.get("platforms", "bilibili,weixin_channels"),
            str(entry.get("max_results", 5)),
            entry.get("status", "pending"),
            entry.get("completed_at", ""),
            entry.get("notes", ""),
        ]
        data_lines.append("\t".join(parts))

    content = header + "\n".join(data_lines) + "\n"
    SCHEDULE_FILE.write_text(content, encoding="utf-8")


def should_run_weekly() -> bool:
    """Check if tracker should run (once per week).

    Returns True if no tracker run was recorded in the past 6 days.
    """
    if not TRACKER_HISTORY.exists():
        return True

    lines = TRACKER_HISTORY.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return True

    # Check last run date
    last_line = lines[-1].strip()
    try:
        last_date = datetime.fromisoformat(last_line.split("\t")[0])
        days_since = (datetime.now() - last_date).days
        if days_since < 6:
            print(f"  {D}上次追踪: {last_date.strftime('%Y-%m-%d')} ({days_since}天前)，本周已运行{X}")
            return False
    except (ValueError, IndexError):
        pass

    return True


def record_tracker_run(n_topics: int):
    """Record tracker run to history file."""
    line = f"{datetime.now().isoformat(timespec='seconds')}\t{n_topics} topics\n"
    with open(TRACKER_HISTORY, "a", encoding="utf-8") as f:
        f.write(line)


def update_schedule(recommended_topics: list) -> int:
    """Write recommended topics to schedule.txt with date-specific entries.

    Distributes topics across the next 7 days (one per day), skipping dates
    that already have a pending entry. Uses source_mode=research (NotebookLM)
    by default.

    Args:
        recommended_topics: List of (domain_name_zh, topic_title, citations) tuples

    Returns:
        Number of topics actually written
    """
    entries = load_schedule()
    today = datetime.now().date()

    # Collect dates that already have pending entries
    occupied_dates = set()
    existing_topics_lower = set()
    for entry in entries:
        if entry["status"] == "pending":
            existing_topics_lower.add(entry["topic"].lower().strip())
            if entry["date"] != "queue":
                try:
                    occupied_dates.add(datetime.strptime(entry["date"], "%Y-%m-%d").date())
                except ValueError:
                    pass

    # Find available dates in the next 7 days
    available_dates = []
    for offset in range(7):
        d = today + timedelta(days=offset)
        if d not in occupied_dates:
            available_dates.append(d)

    if not available_dates:
        print(f"  {Y}未来7天已全部排满，跳过自动写入{X}")
        return 0

    written = 0
    new_entries = list(entries)  # copy

    for (domain_name, topic_title, citations) in recommended_topics:
        if not available_dates:
            break  # No more slots

        full_topic = f"{domain_name}: {topic_title}"
        if full_topic.lower().strip() in existing_topics_lower:
            print(f"  {D}跳过重复: {full_topic[:50]}...{X}")
            continue

        target_date = available_dates.pop(0)
        date_str = target_date.strftime("%Y-%m-%d")

        new_entries.append({
            "date": date_str,
            "topic": full_topic,
            "source_mode": "research",  # NotebookLM优先
            "platforms": "bilibili,weixin_channels",
            "max_results": 5,
            "status": "pending",
            "completed_at": "",
            "notes": f"auto_tracker|citations:{citations}",
        })
        print(f"  {G}✓ {date_str}{X}: {full_topic[:50]}...")
        written += 1

    if written > 0:
        # Sort: date-specific entries by date, then queue entries at the end
        def entry_sort_key(e):
            if e["date"] == "queue":
                return ("9999-99-99", e.get("line_num", 999))
            return (e["date"], e.get("line_num", 999))

        new_entries.sort(key=entry_sort_key)
        save_schedule(new_entries)
        print(f"\n  {G}写入 {written} 个主题到 schedule.txt (按日期分配){X}")

    return written


def print_schedule_status():
    """Print current schedule status overview."""
    entries = load_schedule()
    if not entries:
        print(f"  {D}schedule.txt 为空{X}")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    pending = [e for e in entries if e["status"] == "pending"]
    completed = [e for e in entries if e["status"] == "completed"]
    failed = [e for e in entries if e["status"] == "failed"]

    print(f"  {B}日程状态:{X} {len(pending)} 待执行 | {len(completed)} 已完成 | {len(failed)} 失败")

    # Show today's topic if any
    today_entry = next((e for e in entries if e["date"] == today and e["status"] == "pending"), None)
    if today_entry:
        print(f"  {G}今日主题:{X} {today_entry['topic'][:50]}")
    else:
        queue_entry = next((e for e in entries if e["date"] == "queue" and e["status"] == "pending"), None)
        if queue_entry:
            print(f"  {Y}今日无指定, 队列下一个:{X} {queue_entry['topic'][:50]}")
        else:
            print(f"  {Y}无待执行主题{X}")

    # Show upcoming schedule
    upcoming = [e for e in pending if e["date"] != "queue" and e["date"] >= today]
    if upcoming:
        print(f"\n  {B}近期计划:{X}")
        for e in upcoming[:7]:
            src = f" [{e['source_mode']}]" if e['source_mode'] != 'research' else ''
            note = f" {D}({e['notes']}){X}" if e.get('notes') else ''
            print(f"    {e['date']}  {e['topic'][:45]}{src}{note}")


def main():
    parser = argparse.ArgumentParser(
        description="Weekly hot topic paper tracker for biomedical+AI domains"
    )
    parser.add_argument("--days", type=int, default=90,
                        help="Lookback window in days (default: 90, focus on high-citation)")
    parser.add_argument("--top", type=int, default=3,
                        help="Top N papers per domain to report (default: 3)")
    parser.add_argument("--max-results", type=int, default=20,
                        help="Max results per platform per domain (default: 20)")
    parser.add_argument("--write-schedule", action="store_true",
                        help="Write top topics to schedule.txt with per-day dates")
    parser.add_argument("--force", action="store_true",
                        help="Skip weekly check, force run even if ran recently")
    parser.add_argument("--domains", type=str, default=None,
                        help="Comma-separated domain indices (0-based, default: all)")
    parser.add_argument("--json", action="store_true",
                        help="Output machine-readable JSON")
    parser.add_argument("--status", action="store_true",
                        help="Show schedule status only (no search)")
    args = parser.parse_args()

    # Status-only mode
    if args.status:
        print(f"\n{B}PaperTalker 日程状态{X}")
        print_schedule_status()
        return

    # Weekly gate (skip if ran within 6 days, unless --force)
    if args.write_schedule and not args.force:
        if not should_run_weekly():
            print(f"  {D}使用 --force 可强制运行{X}")
            print_schedule_status()
            return

    # Select domains
    domains = DOMAINS
    if args.domains:
        indices = [int(x.strip()) for x in args.domains.split(",")]
        domains = [DOMAINS[i] for i in indices if 0 <= i < len(DOMAINS)]

    # Year filter: search within current and previous year for citation accumulation
    current_year = datetime.now().year
    year_filter = f"{current_year - 1}-{current_year}"

    print(f"\n{B}PaperTalker 热点追踪{X}")
    print(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"搜索范围: 过去{args.days}天 | 按引用数排序 | 每域Top {args.top}")
    print(f"搜索域: {', '.join(d['name_zh'] for d in domains)}\n")

    domain_results = {}
    all_recommended = []

    for domain in domains:
        name = domain["name_zh"]
        print(f"  {C}搜索: {name}{X} ...", flush=True)

        papers = search_domain(domain, max_results=args.max_results, year=year_filter)
        recent = filter_recent(papers, days=args.days)
        print(f"    过去{args.days}天: {len(recent)} 篇", flush=True)

        ranked = rank_papers(recent)
        domain_results[name] = ranked

        # Best paper (highest citations) -> recommendation
        if ranked:
            best = ranked[0]
            topic_title = best.title[:60] if best.title else name
            all_recommended.append((name, topic_title, best.citations or 0))

    # Sort recommendations by citations (highest first)
    all_recommended.sort(key=lambda x: -x[2])

    # Output
    if args.json:
        output = {
            "date": datetime.now().isoformat(timespec="seconds"),
            "days": args.days,
            "domains": {},
        }
        for name, papers in domain_results.items():
            output["domains"][name] = [
                {
                    "title": p.title,
                    "authors": p.authors[:5],
                    "date": p.published_date,
                    "citations": p.citations,
                    "doi": p.doi,
                    "url": p.url,
                    "abstract": p.abstract[:200] if p.abstract else "",
                }
                for p in papers[:args.top]
            ]
        output["recommended"] = [
            {"domain": d, "topic": t, "citations": c} for d, t, c in all_recommended
        ]
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        report = generate_report(domain_results, args.days, args.top)
        print(report)

    # Write to schedule (with dates)
    if args.write_schedule:
        if all_recommended:
            written = update_schedule(all_recommended)
            if written > 0:
                record_tracker_run(written)
            elif not args.json:
                print(f"  {D}无新主题需要写入{X}")
        else:
            print(f"  {Y}未发现推荐主题，跳过写入{X}")

    # Summary
    total_papers = sum(len(v) for v in domain_results.values())
    if total_papers == 0:
        print(f"\n  {Y}未发现任何论文{X}")
        sys.exit(1)
    else:
        print(f"\n  {G}追踪完成: {total_papers} 篇论文, {len(all_recommended)} 个推荐主题{X}")

    # Show schedule status after writing
    if args.write_schedule:
        print()
        print_schedule_status()


if __name__ == "__main__":
    main()
