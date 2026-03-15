# PaperTalker-CLI

End-to-end academic video production: Research Topic -> NotebookLM Video -> Subtitles -> Multi-Platform Publishing.

## Quick Reference

### Full Pipeline

| Command | Description |
|---------|-------------|
| `python quick_video.py "主题" --check` | Step 0: Verify NotebookLM connectivity (MUST run first) |
| `python quick_video.py "主题" --no-confirm` | Phase 1: Generate video from topic (NotebookLM Research) |
| `python quick_video.py "主题" --source search --no-confirm` | Phase 1: Generate from literature search (Semantic Scholar + arXiv + CrossRef) |
| `python quick_video.py "主题" --source file --files paper.pdf` | Phase 1: Generate from local PDF |
| `python quick_video.py "主题" --source paper` | Phase 1: Search by paper title, pick from list |
| `python publish.py` | Phase 2: Subtitle + upload all videos in output/ |
| `python publish.py --platforms bilibili weixin_channels` | Phase 2: Upload to specific platforms |
| `python publish.py --skip-upload` | Subtitle only, no upload |
| `python publish.py --retry` | Re-upload previously failed videos from output_subtitled/ |
| `python run_scheduled.py` | Run today's scheduled topic (from schedule.txt) |
| `python run_scheduled.py --pre-hook "auto_tracker.py --write-schedule"` | Run with auto paper discovery |
| `python auto_tracker.py` | Discover trending papers (report only) |
| `python auto_tracker.py --write-schedule` | Discover papers + write to schedule.txt |
| `python setup_cron.py --execute` | Register OpenClaw daily cron job (10 AM) |
| `python setup_cron.py --with-tracker --execute` | Register dual cron (8:30 tracker + 10:00 pipeline) |

### Modular Scripts (按需调用)

| Script | Description | Example |
|--------|-------------|---------|
| `src/transcribe.py` | Audio transcription (extract + Whisper + SRT, parallel) | `python src/transcribe.py video.mp4 --workers 3` |
| `src/subtitle.py` | Burn SRT subtitles into video | `python src/subtitle.py video.mp4 subs.srt` |
| `src/upload_bilibili.py` | Upload to Bilibili with metadata | `python src/upload_bilibili.py video.mp4 --title "标题" --tags "tag1,tag2"` |
| `src/upload_weixin.py` | Upload to WeChat Channels | `python src/upload_weixin.py video.mp4 --title "标题" --desc "描述"` |

## Running Python (Windows)

**Always use direct Python path + UTF-8 encoding + unbuffered output.** Never use `conda run` (GBK crash). Always set `PYTHONUNBUFFERED=1` to prevent silent output buffering in subprocess/pipe.

```bash
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$(conda info --base)/envs/papertalker/python.exe" -u script.py
```

Or activate first: `conda activate papertalker && PYTHONUNBUFFERED=1 python -u script.py`

## Project Layout

```
quick_video.py              # Phase 1: topic -> NotebookLM video (async)
publish.py                  # Phase 2: subtitle + upload (orchestrator)
run_scheduled.py            # Cron entry point: pick topic -> Phase 1 -> Phase 2 (supports --pre-hook/--post-hook)
auto_tracker.py             # Auto paper discovery: literature search -> schedule.txt
setup_cron.py               # OpenClaw cron registration helper (10 AM default)
OPENCLAW.md                 # OpenClaw handoff document (architecture + usage + TODO)
video.md                    # Video generation prompt (strict academic rigor)
schedule.txt                # Daily schedule: date-bound topics + FIFO queue
src/                        # Source modules
  transcribe.py             # Standalone: audio extraction + Whisper transcription + SRT generation
  subtitle.py               # Standalone: burn SRT subtitles into video
  upload_bilibili.py        # Standalone: Bilibili upload with metadata
  upload_weixin.py          # Standalone: WeChat Channels upload
  workers/
    weixin_upload_worker.py # WeChat Channels upload subprocess (async Playwright, legacy)
  utils/
    paper_search.py         # Literature search wrapper (uses skills/literature-review)
setup/                      # One-click installers (setup.bat, setup.sh, etc.)
tools/                      # Utility scripts (auto_login.py, verify.py)
cookies/bilibili/           # Bilibili auth (account.json)
cookies/weixin/             # WeChat 视频号 auth (storage_state.json, browser_profile/)
vendor/                     # Binary tools (biliup.exe)
deps/                       # Local editable packages (notebooklm-py)
output/                     # Raw videos (transient, cleared after processing)
output_subtitled/           # Final subtitled videos organized by date
skills/paper-talker/        # Skill definition (distributable)
skills/literature-review/   # Literature search skill (Semantic Scholar, arXiv, CrossRef)
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
| WeChat 视频号 login detection | Direct navigate to `post/create`. Poll every 0.2s for URL change. 3-level re-verify (0.3s+0.5s) |
| WeChat 视频号 file upload | Use `set_input_files()` instead of `expect_file_chooser()` |
| WeChat 视频号 publish button | Try 3 click methods. Wait for URL redirect to `post/list`. Keep browser open 35s after publish |
| WeChat 视频号 short title < 6 chars | Auto-pad with "—视频解读" to meet minimum |
| Deep Research rate limit | Auto-fallback to Fast Research (`--mode fast`) or use `--source search` for literature search |
| Bilibili tag length limit | Each tag max 20 chars, max 12 tags total |
| Bilibili tag format | `data.tag` must be comma-separated string, NOT list |
| BiliBili() init | Pass `Data` object, then `bili.login_by_cookies(account)` separately |
| paper_search uses literature-review skill | `src/utils/paper_search.py` wraps `skills/literature-review/scripts/paper_search.py` |

## Environment

| Item | Value |
|------|-------|
| Conda env | `papertalker` (Python 3.11) |
| Proxy | Set in `.env` (required for Google) |
| NotebookLM auth | `~/.notebooklm/storage_state.json` |
| Bilibili cookies | `cookies/bilibili/account.json` |
| WeChat 视频号 auth | `cookies/weixin/storage_state.json` |
| WeChat 公众号 API | `.env` (WECHAT_APPID, WECHAT_APPSECRET) |
