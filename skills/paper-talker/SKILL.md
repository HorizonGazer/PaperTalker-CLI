---
name: paper-talker
description: "End-to-end academic video production pipeline: research topic to subtitled video on streaming platforms. Use when the user wants to: (1) set up PaperTalker environment, (2) generate academic videos from a topic via NotebookLM, (3) add subtitles and burn into video, (4) upload videos to Bilibili/Douyin/WeChat/Xiaohongshu/Kuaishou, (5) run full pipeline topic-to-published-video, (6) troubleshoot deps or auth issues, (7) search academic papers. Triggers: paper talker, academic video, topic to video, generate video, notebooklm, video pipeline, subtitle, upload bilibili, batch publish, setup papertalker."
---

# Paper Talker

End-to-end academic video production: **Research Topic** -> **NotebookLM Video** -> **Subtitles** -> **Multi-Platform Publishing**.

## Pipeline Overview

```
 UPSTREAM (Phase 1: quick_video.py)        DOWNSTREAM (Phase 2: publish.py)
 ┌──────────────────────────┐              ┌──────────────────────────────┐
 │  Research Topic           │              │  output/*.mp4                │
 │       │                   │              │       │                      │
 │  NotebookLM               │              │  1. Extract Audio (FFmpeg)   │
 │   ├─ Deep Research        │              │  2. Extract Cover (1st frame)│
 │   ├─ Paper Search (8 DBs) │              │  3. Transcribe (whisper GPU) │
 │   ├─ Manual Upload        │              │  4. Generate SRT (chunked)   │
 │   └─ Mixed                │              │  5. Burn Subtitles (FFmpeg)  │
 │       │                   │              │  6. Upload (Bilibili, ...)   │
 │  Generate & Download MP4  │  ────────>   │  7. Cleanup + Save History   │
 └──────────────────────────┘   output/    └──────────────────────────────┘
                                            output_subtitled/YYYY-MM-DD/
```

## Project Structure

```
PaperTalker-CLI/
├── CLAUDE.md                  # Project-level instructions for Claude Code
├── quick_video.py             # Phase 1: topic -> NotebookLM video (async)
├── publish.py                 # Phase 2: subtitle + upload (canonical copy)
├── paper_search.py            # Multi-platform paper search wrapper
├── video.md                   # Video generation prompt (strict academic rigor)
├── .env / .env.example        # Proxy + API keys (HTTPS_PROXY, NCBI_API_KEY, SS_API_KEY)
├── setup/                     # One-click installers
│   ├── setup.bat / setup.ps1  #   Windows (calls sub-scripts below)
│   ├── setup.sh               #   macOS/Linux
│   ├── setup_conda.bat        #   Step 1: detect/install Conda + Tsinghua mirrors
│   ├── setup_env.bat          #   Step 2: create papertalker env (Python 3.11)
│   └── install_deps.bat       #   Step 3: install pip deps + Playwright chromium
├── tools/                     # Utility scripts
│   ├── auto_login.py          #   Non-interactive NotebookLM login helper
│   └── verify.py              #   Dependency verification checker
├── cookies/                   # Authentication credentials (gitignored)
│   └── bilibili/account.json  #   Bilibili auth
├── vendor/                    # Binary tools (gitignored)
│   └── biliup.exe             #   Bilibili login/upload tool
├── output/                    # Raw videos (cleared after downstream)
├── output_subtitled/          # Subtitled videos organized by date
│   └── YYYY-MM-DD/           #   {topic}.mp4, {topic}.srt
├── deps/
│   ├── notebooklm-py/        # NotebookLM Python client (v0.3.2, local editable)
│   │   └── src/notebooklm/   #   Client API: notebooks, sources, artifacts, research, chat
│   └── paper-search-mcp/     # Academic paper search (v0.1.3, MCP server)
│       └── paper_search_mcp/ #   8 platforms: arxiv, pubmed, biorxiv, medrxiv, etc.
└── skills/paper-talker/       # Skill definition (distributable)
    ├── SKILL.md
    ├── scripts/publish.py    # Phase 2 copy (for skill distribution)
    └── references/           # Setup, upstream, downstream, known issues, etc.
```

### Key Implementation Choices

| Component | **Used (Tested)** | Alternative (Not in Pipeline) |
|-----------|-------------------|-------------------------------|
| Transcription | `faster-whisper` local GPU (large-v3, word timestamps, subprocess) | Doubao ASR (permission issues) |
| Subtitle burn | FFmpeg `subtitles` filter | VectCutAPI (needs manual JianYing export) |
| Upload | `biliup` library direct import (`vendor/biliup.exe` for login) | — |
| FFmpeg binary | `imageio-ffmpeg` pip package | `conda install ffmpeg` (GBK crash) |

## Environment

| Item | Value |
|------|-------|
| Conda env | `papertalker` (Python 3.11) |
| Project root | (auto-detected from script location) |
| Proxy | Set in `.env` (required for Google) |
| NotebookLM auth | `~/.notebooklm/storage_state.json` |
| Bilibili cookies | `cookies/bilibili/account.json` |

### Running Python

**On Windows, always use direct Python path + UTF-8 encoding.** Never use `conda run` (GBK crash).

```bash
PYTHONIOENCODING=utf-8 "$(conda info --base)/envs/papertalker/python.exe" script.py
```

Or in an activated conda shell:
```bash
conda activate papertalker && python script.py
```

### Directory Convention

| Directory | Purpose |
|-----------|---------|
| `output/` | Raw videos from upstream. **Cleared after downstream processing.** |
| `output_subtitled/YYYY-MM-DD/` | Final subtitled videos + SRT files |

## Pre-flight Check

Before running either phase, verify dependencies:

```python
import importlib, os, sys
from pathlib import Path

checks = []
for mod, pkg in [
    ('notebooklm', 'notebooklm-py'), ('playwright', 'playwright'),
    ('dotenv', 'python-dotenv'), ('imageio_ffmpeg', 'imageio-ffmpeg'),
    ('faster_whisper', 'faster-whisper'), ('biliup', 'biliup'),
    ('jieba', 'jieba'),
]:
    try:
        importlib.import_module(mod)
        checks.append(('ok', pkg))
    except ImportError:
        checks.append(('MISS', pkg))

try:
    import imageio_ffmpeg
    imageio_ffmpeg.get_ffmpeg_exe()
    checks.append(('ok', 'ffmpeg-binary'))
except Exception:
    checks.append(('MISS', 'ffmpeg-binary'))

auth = Path.home() / '.notebooklm' / 'storage_state.json'
checks.append(('ok' if auth.exists() else 'MISS', 'notebooklm-auth'))

for status, name in checks:
    print(f"  {'ok' if status == 'ok' else 'MISS':6s} {name}")
```

### Fix Missing Dependencies

```bash
# One-click setup
setup\setup.bat    # Windows
./setup/setup.sh   # macOS/Linux

# Or manually (in papertalker env):
# Upstream:
pip install -e deps/notebooklm-py
pip install -e deps/paper-search-mcp
pip install python-dotenv httpx rich playwright
python -m playwright install chromium

# Downstream:
pip install imageio-ffmpeg faster-whisper jieba "biliup>=1.1.29"
```

### Authentication

**NotebookLM** (Google login, interactive):
```bash
conda activate papertalker
notebooklm login
# Opens browser -> complete Google login -> press Enter
# Saved to ~/.notebooklm/storage_state.json
```

**Bilibili** (QR scan, interactive, **run in separate terminal**):
```bash
cd vendor
./biliup.exe -u ../cookies/bilibili/account.json login
# Select "扫码登录" -> scan QR with Bilibili app
```

For full setup (Conda install, Tsinghua mirrors, env creation), see [references/setup.md](references/setup.md).

## Phase 1: Video Generation (Upstream)

**Script:** `quick_video.py` — async pipeline using Google NotebookLM.

```bash
conda activate papertalker
python quick_video.py "虚拟细胞"
```

### Upstream 7-Step Pipeline

```
Step 1: Create NotebookLM notebook (title = topic)
Step 2: Gather sources (based on --source mode)
Step 3: Stage confirmation (show source list, wait for user)
Step 4: Import sources into notebook (batch 15, URL fallback)
Step 5: Wait for source processing (30s + 3s/source, max 90s)
Step 6: Generate video (submit task + poll status)
Step 7: Download MP4 to output/{topic}_{timestamp}.mp4
```

### Source Modes

| Mode | Behavior | Command Example |
|------|----------|-----------------|
| `research` (default) | NotebookLM Deep Research auto-searches web | `python quick_video.py "生物智能体"` |
| `search` | paper-search-mcp across 8 academic databases | `python quick_video.py "蛋白质折叠" --source search --platforms arxiv pubmed --year 2024` |
| `upload` | Opens notebook URL for manual file upload | `python quick_video.py "量子计算" --source upload` |
| `mixed` | Deep Research + paper search combined | `python quick_video.py "LLM药物发现" --source mixed --platforms semantic_scholar` |

### Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `topic` | (required) | Video topic |
| `--source` | `research` | Source mode: research/search/upload/mixed |
| `--style` | `whiteboard` | 9 styles: whiteboard, classic, anime, kawaii, watercolor, retro_print, heritage, paper_craft, auto |
| `--lang` | `zh-CN` | Language code |
| `--mode` | `deep` | Deep Research depth: fast/deep |
| `--platforms` | arxiv semantic_scholar | Paper search: arxiv, pubmed, biorxiv, medrxiv, semantic_scholar, google_scholar, crossref, iacr |
| `--max-results` | `10` | Per-platform result limit |
| `--year` | none | Paper year filter |
| `--output` | `./output` | Video output directory |
| `--timeout` | `1800` | Generation timeout (seconds) |
| `--instructions` | video.md | Custom video prompt (override video.md) |
| `--no-confirm` | false | Skip stage confirmations |
| `--resume NID TID` | — | Resume timed-out video task |

For full parameter reference, see [references/upstream.md](references/upstream.md).

### Video Generation Prompt (video.md)

Default prompt enforces strict academic rigor:
- Simplified Chinese output
- Must cite specific values (p-values, accuracy, AUC, confidence intervals)
- Include original figures, formulas from source papers
- High information density for researchers/graduate students
- Forbids vague language ("显著提升" forbidden — must give exact numbers)

### Output

Videos saved as `output/{sanitized_topic}_{YYYYMMDD_HHMMSS}.mp4`. Generation takes 10-20 min. If timeout, script prints `--resume` command.

## Phase 2: Post-Production & Publishing (Downstream)

**Script:** `publish.py` (project root) — scans `output/`, processes all videos.

```bash
conda activate papertalker
python publish.py
```

Or with direct path (Windows):
```bash
PYTHONIOENCODING=utf-8 "$(conda info --base)/envs/papertalker/python.exe" publish.py
```

Script options:
```bash
--skip-upload              # Subtitle only, no upload
--platforms bilibili douyin # Choose platforms (bilibili, douyin, weixin, xiaohongshu, kuaishou)
--input output/            # Custom input dir
--output output_subtitled/ # Custom output dir
```

### Downstream 7-Step Pipeline

| Step | Action | Details |
|------|--------|---------|
| 1 | Extract Audio | FFmpeg -> 16kHz mono WAV |
| 2 | Extract Cover | First video frame as JPEG (B站 thumbnail) |
| 3 | Transcribe | faster-whisper large-v3, CUDA GPU, Chinese, VAD filter, word timestamps (subprocess) |
| 4 | Generate SRT | Smart chunking: jieba word-aware split, max 18 chars/line, word-level time alignment |
| 5 | Burn Subtitles | FFmpeg subtitles filter (Microsoft YaHei, white + black outline, MarginV=30) |
| 6 | Upload | Auto-generated title/desc/tags, cover image, per platform |
| 7 | Cleanup | Delete original + WAV + cover temp, save run history JSON |

### Smart Metadata Generation

The script auto-generates B站-optimized metadata from the filename:

- **Topic extraction**: `虚拟细胞_20260303_223817.mp4` -> `虚拟细胞` (strip `_YYYYMMDD_HHMMSS`)
- **Title**: `【AI科研科普】{topic}：前沿研究深度解读` (max 80 chars)
- **Description**: Topic + duration + subtitle count + hashtags (max 250 chars)
- **Tags**: `{topic},AI科研,学术科普,论文解读,前沿研究,深度解读` (max 12, topic split at 与/和/及)
- **Cover**: First frame of video as JPEG
- **Category**: tid=201 (科学科普)

### Subtitle Smart Chunking

Long whisper segments are split for screen readability:
1. **Punctuation split** (highest priority): ，。、；！？：,.;!?:
2. **Word-boundary split** (via `jieba`): never breaks mid-word (e.g. "活生生" stays intact)
3. Max 18 Chinese characters per subtitle line
4. Max 6 seconds display per subtitle entry
5. **Word-level time alignment**: each subtitle's start/end derived from Whisper word timestamps (not proportional guessing)
6. Fallback: proportional time distribution when word timestamps unavailable
- Example: 210 raw segments -> 295 display-ready subtitles

**Dependency:** `pip install jieba` (Chinese word segmentation, pure Python, no C deps)

### Run History

Each run is recorded in `references/run_history.json` (last 50 records):
```json
{
  "date": "2026-03-03T23:22:47",
  "topic": "虚拟细胞",
  "file": "虚拟细胞_20260303_223817",
  "subtitles": 295,
  "duration": "9:39",
  "title": "【AI科研科普】虚拟细胞：前沿研究深度解读",
  "tags": "虚拟细胞,AI科研,学术科普,论文解读,前沿研究,深度解读",
  "uploads": {"bilibili": "ok:BV1wjAfztECV"}
}
```
On startup, shows last successful run for reference.

### Output Naming

Output files use clean topic names (timestamps stripped):
```
output_subtitled/YYYY-MM-DD/{topic}.mp4   # subtitled video
output_subtitled/YYYY-MM-DD/{topic}.srt   # subtitle file
```

### Manual Step-by-Step

For debugging or custom workflows, see [references/downstream.md](references/downstream.md).
For VectCutAPI (JianYing editable subtitles), see [references/vectcut_api.md](references/vectcut_api.md).
For Doubao ASR (cloud alternative to whisper), see [references/doubao_asr.md](references/doubao_asr.md).

## Known Issues

See [references/known_issues.md](references/known_issues.md) for full list. Critical:

| Issue | Fix |
|-------|-----|
| `conda run` GBK crash | Direct Python path + `PYTHONIOENCODING=utf-8` |
| `conda install ffmpeg` fails | `pip install imageio-ffmpeg` |
| FFmpeg subtitle Windows paths | `path.replace('\\','/').replace(':','\\:')` |
| CUDA crash with `word_timestamps=True` in function scope | Subprocess transcribe (auto in publish.py) |
| Playwright chromium version mismatch | `python -m playwright install chromium` (or upgrade playwright to match existing browser) |
| NotebookLM auth expired | `notebooklm login` (interactive, needs browser + proxy) |
| Doubao ASR 45000030 permission | Use `faster-whisper` local GPU instead |
| biliup < 1.0 blocked (21590) | `pip install "biliup>=1.1.29"` |
| `login_by_cookies` KeyError | Pass full `account` dict, NOT `account['cookie_info']` |
| biliup login interactive | Run `biliup.exe login` in separate terminal |

## Progress Display

```
Pre-flight check:
  ok   imageio-ffmpeg / faster-whisper / biliup / ffmpeg / cookies
Last run: 2026-03-03 | 虚拟细胞 | bilibili: ok:BV1wjAfztECV

Scanning output/... found N videos.
Date folder: output_subtitled/2026-03-03/

--- [1/N] 虚拟细胞_20260303_223817.mp4 ---
  Topic: 虚拟细胞
[1/7] Extract audio......... ok
[2/7] Extract cover......... ok -> 虚拟细胞_cover.jpg
[3/7] Transcribe............ ok (210 segments, 9:39)
[4/7] Generate SRT.......... ok (295 subtitles) -> 2026-03-03/虚拟细胞.srt
[5/7] Burn subtitles........ ok -> 2026-03-03/虚拟细胞.mp4
[6/7] Upload:
      Title: 【AI科研科普】虚拟细胞：前沿研究深度解读
      Tags:  虚拟细胞,AI科研,学术科普,论文解读,前沿研究,深度解读
      Bilibili  ok  BV1wjAfztECV
[7/7] Cleanup............... ok (original + temp deleted)
```

## Resources

| File | Purpose |
|------|---------|
| [references/setup.md](references/setup.md) | Full environment setup (Conda, mirrors, deps, auth, proxy) |
| [references/upstream.md](references/upstream.md) | quick_video.py CLI parameters, styles, platforms, pipeline |
| [references/downstream.md](references/downstream.md) | Detailed code for each downstream step |
| [references/known_issues.md](references/known_issues.md) | All known issues with workarounds and code fixes |
| [references/doubao_asr.md](references/doubao_asr.md) | Doubao ASR 2.0 API (alternative to faster-whisper) |
| [references/vectcut_api.md](references/vectcut_api.md) | VectCutAPI for JianYing/CapCut draft subtitles |
| [scripts/publish.py](scripts/publish.py) | Downstream pipeline script (distributable copy) |
