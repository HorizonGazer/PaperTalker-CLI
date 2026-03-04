# PaperTalker-CLI

End-to-end academic video production: Research Topic -> NotebookLM Video -> Subtitles -> Multi-Platform Publishing.

## Quick Reference

| Command | Description |
|---------|-------------|
| `python quick_video.py "主题"` | Phase 1: Generate video from topic |
| `python publish.py` | Phase 2: Subtitle + upload all videos in output/ |
| `python publish.py --skip-upload` | Subtitle only, no upload |

## Running Python (Windows)

**Always use direct Python path + UTF-8 encoding.** Never use `conda run` (GBK crash).

```bash
PYTHONIOENCODING=utf-8 "$(conda info --base)/envs/papertalker/python.exe" script.py
```

Or activate first: `conda activate papertalker && python script.py`

## Project Layout

```
quick_video.py          # Phase 1: topic -> NotebookLM video (async)
publish.py              # Phase 2: subtitle + upload (canonical copy)
paper_search.py         # Multi-platform paper search wrapper
video.md                # Video generation prompt (strict academic rigor)
setup/                  # One-click installers (setup.bat, setup.sh, etc.)
tools/                  # Utility scripts (auto_login.py, verify.py)
cookies/bilibili/       # Bilibili auth (account.json)
vendor/                 # Binary tools (biliup.exe)
deps/                   # Local editable packages (notebooklm-py, paper-search-mcp)
output/                 # Raw videos (transient, cleared after processing)
output_subtitled/       # Final subtitled videos organized by date
skills/paper-talker/    # Skill definition (distributable)
```

## Skill

Full pipeline documentation is in `skills/paper-talker/SKILL.md`. This is the authoritative reference for all parameters, known issues, and implementation details.

## Key Known Issues

| Issue | Fix |
|-------|-----|
| `conda run` GBK crash | Direct Python path + `PYTHONIOENCODING=utf-8` |
| CUDA crash with `word_timestamps=True` in function scope | Subprocess transcribe (already handled in publish.py) |
| FFmpeg subtitle Windows paths | `path.replace('\\','/').replace(':','\\:')` |
| `conda install ffmpeg` fails | Use `pip install imageio-ffmpeg` |

## Environment

| Item | Value |
|------|-------|
| Conda env | `papertalker` (Python 3.11) |
| Proxy | Set in `.env` (required for Google) |
| NotebookLM auth | `~/.notebooklm/storage_state.json` |
| Bilibili cookies | `cookies/bilibili/account.json` |
