# PaperTalker-CLI

End-to-end academic video production: Research Topic -> NotebookLM Video -> Subtitles -> Multi-Platform Publishing.

## Quick Reference

| Command | Description |
|---------|-------------|
| `python quick_video.py "主题" --check` | Step 0: Verify NotebookLM connectivity (MUST run first) |
| `python quick_video.py "主题" --no-confirm` | Phase 1: Generate video from topic |
| `python quick_video.py "主题" --source file --files paper.pdf` | Phase 1: Generate from local PDF |
| `python quick_video.py "主题" --source paper` | Phase 1: Search by paper title, pick from list |
| `python publish.py` | Phase 2: Subtitle + upload all videos in output/ |
| `python publish.py --platforms bilibili weixin_channels` | Phase 2: Upload to specific platforms |
| `python publish.py --skip-upload` | Subtitle only, no upload |
| `python run_scheduled.py` | Run today's scheduled topic (from schedule.txt) |
| `python setup_cron.py --execute` | Register OpenClaw daily cron job |

## Running Python (Windows)

**Always use direct Python path + UTF-8 encoding + unbuffered output.** Never use `conda run` (GBK crash). Always set `PYTHONUNBUFFERED=1` to prevent silent output buffering in subprocess/pipe.

```bash
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$(conda info --base)/envs/papertalker/python.exe" -u script.py
```

Or activate first: `conda activate papertalker && PYTHONUNBUFFERED=1 python -u script.py`

## Project Layout

```
quick_video.py              # Phase 1: topic -> NotebookLM video (async)
publish.py                  # Phase 2: subtitle + upload (canonical copy)
_weixin_upload_worker.py    # WeChat Channels upload subprocess (async Playwright)
paper_search.py             # Multi-platform paper search wrapper
video.md                    # Video generation prompt (strict academic rigor)
schedule.txt                # Daily schedule: date-bound topics + FIFO queue
run_scheduled.py            # Cron entry point: pick topic -> Phase 1 -> Phase 2
setup_cron.py               # OpenClaw cron registration helper
setup/                      # One-click installers (setup.bat, setup.sh, etc.)
tools/                      # Utility scripts (auto_login.py, verify.py)
cookies/bilibili/           # Bilibili auth (account.json)
cookies/weixin/             # WeChat 视频号 auth (storage_state.json, browser_profile/)
vendor/                     # Binary tools (biliup.exe)
deps/                       # Local editable packages (notebooklm-py, paper-search-mcp)
output/                     # Raw videos (transient, cleared after processing)
output_subtitled/           # Final subtitled videos organized by date
skills/paper-talker/        # Skill definition (distributable)
```

## Skill

Full pipeline documentation is in `skills/paper-talker/SKILL.md`. This is the authoritative reference for all parameters, known issues, and implementation details.

## Key Known Issues

| Issue | Fix |
|-------|-----|
| Python output buffering (0 bytes in subprocess) | `PYTHONUNBUFFERED=1` + `-u` flag |
| `conda run` GBK crash | Direct Python path + `PYTHONIOENCODING=utf-8` |
| CUDA crash with `word_timestamps=True` in function scope | Subprocess transcribe (already handled in publish.py) |
| FFmpeg subtitle Windows paths | `path.replace('\\','/').replace(':','\\:')` |
| `conda install ffmpeg` fails | Use `pip install imageio-ffmpeg` |
| Playwright sync_api event loop conflict | Use async API in subprocess (`_weixin_upload_worker.py`) + `nest_asyncio` |
| WeChat 视频号 login false positive | URL stability check (3s re-verify after URL change) |
| WeChat 视频号 short title < 6 chars | Auto-pad with "—视频解读" to meet minimum |

## Environment

| Item | Value |
|------|-------|
| Conda env | `papertalker` (Python 3.11) |
| Proxy | Set in `.env` (required for Google) |
| NotebookLM auth | `~/.notebooklm/storage_state.json` |
| Bilibili cookies | `cookies/bilibili/account.json` |
| WeChat 视频号 auth | `cookies/weixin/storage_state.json` |
| WeChat 公众号 API | `.env` (WECHAT_APPID, WECHAT_APPSECRET) |
