---
name: paper-talker
description: "End-to-end academic video production pipeline: research topic to subtitled video on streaming platforms. Use when the user wants to: (1) set up PaperTalker environment, (2) generate academic videos from a topic via NotebookLM, (3) add subtitles and burn into video, (4) upload videos to Bilibili/Douyin/WeChat/Xiaohongshu/Kuaishou, (5) run full pipeline topic-to-published-video, (6) troubleshoot deps or auth issues, (7) search academic papers. Triggers: paper talker, academic video, topic to video, generate video, notebooklm, video pipeline, subtitle, upload bilibili, batch publish, setup papertalker."
---

# Paper Talker

End-to-end academic video production: **Research Topic** -> **NotebookLM Video** -> **Subtitles** -> **Multi-Platform Publishing**.

## Automation Principles

**This pipeline is designed for maximum automation. Claude MUST follow these rules:**

1. **ALWAYS run connectivity check first as a SEPARATE command.** Before Phase 1, run `quick_video.py "topic" --check` in its own Bash call with `timeout=120000`. Check the exit code. Only proceed to Phase 1 if exit code is 0. If it fails, notify the user with the error output and do NOT run the full pipeline.
2. **ALWAYS use `PYTHONUNBUFFERED=1`** in addition to `PYTHONIOENCODING=utf-8` for ALL Python invocations. Without this, output is fully buffered in non-TTY environments and the script appears to hang silently with 0 bytes output.
3. **Never ask for confirmation before running scripts.** Run `quick_video.py` and `publish.py` directly. These are non-destructive (they only create files in `output/` and `output_subtitled/`).
4. **Always use `--no-confirm`** when running `quick_video.py` to skip all interactive prompts.
5. **Auth expired? Auto-handled.** `quick_video.py --check` and `quick_video.py` automatically call `tools/auto_login.py` when NotebookLM auth expires — the user just needs to complete Google login in the popup browser.
6. **Be patient with long operations.** Deep Research takes 10-20 min; video generation takes 10-30+ min. Total pipeline can exceed 30 minutes. Use `timeout=600000` for Bash calls (use `run_in_background=true` for very long waits). Do NOT interrupt or retry prematurely.
7. **Network errors are transient — NEVER retry by creating a new notebook.** When `quick_video.py` fails due to network errors mid-pipeline, Claude MUST:
   - Record the notebook ID (NID) and video task ID (TID) from the script output (printed early in the run)
   - Use `--resume NID TID` to continue polling the SAME task in the SAME notebook
   - Do NOT rerun `quick_video.py "TOPIC" --no-confirm` — this creates a duplicate notebook and wastes resources
   - Wait 2-3 minutes before resuming — the task continues running on Google's servers regardless of client disconnection
   - Can retry `--resume` multiple times if network keeps dropping — the task ID stays valid for 30 min
8. **Run Phase 1 then Phase 2 sequentially** without asking. After `quick_video.py` produces a video, immediately run `publish.py` to subtitle and upload.
9. **Only confirm for truly destructive actions**: deleting user files, modifying account credentials, or force-pushing git. Everything else: just do it.

## Claude Execution Workflow (MANDATORY)

**Claude MUST execute the pipeline in these exact steps. Do NOT skip or combine steps.**

### Step 0: Connectivity Check (SEPARATE Bash call, short timeout)

```bash
cd "<PROJECT_ROOT>" && PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$(conda info --base)/envs/papertalker/python.exe" -u quick_video.py "TOPIC" --check
```
- **timeout: 120000** (2 minutes max)
- If exit code != 0: STOP. Show the error output to the user. Do NOT proceed.
- If exit code == 0: proceed to Step 1.
- If auto-login is triggered (browser popup), wait for user to complete Google login.

### Step 1: Generate Video (long-running, background recommended)

```bash
cd "<PROJECT_ROOT>" && PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$(conda info --base)/envs/papertalker/python.exe" -u quick_video.py "TOPIC" --no-confirm
```
- **timeout: 600000**. For longer waits, use `run_in_background=true` and check with `TaskOutput`.
- **CRITICAL: Record NID and TID from output.** The script prints notebook ID (after "笔记本:") and video task ID (after "视频任务:") early in the run. Save these — you need them for `--resume` if the script fails.
- If exit code is non-zero due to **network errors**: proceed to Step 1b (Resume). Do NOT rerun this command.
- If exit code is non-zero for **other reasons** (auth, dependency): show output and stop.

### Step 1b: Resume Failed Generation (if Step 1 failed due to network)

If Step 1 failed due to consecutive network errors but the notebook and video task were already submitted:

```bash
cd "<PROJECT_ROOT>" && PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$(conda info --base)/envs/papertalker/python.exe" -u quick_video.py "TOPIC" --resume NID TID
```
- Replace `NID` with the notebook ID and `TID` with the video task ID from Step 1 output.
- **Wait at least 2-3 minutes** before resuming — the task continues on Google's servers regardless of client disconnection.
- Can retry `--resume` multiple times if network keeps dropping — the task ID stays valid for 30 min.
- Video generation typically takes 10-30+ minutes total; be patient.

### Step 2: Subtitle + Upload (long-running, separate Bash call)

```bash
cd "<PROJECT_ROOT>" && PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$(conda info --base)/envs/papertalker/python.exe" -u publish.py
```
- **timeout: 600000**
- Check exit code. Report results (BV number, etc.) to user.

## Pipeline Overview

```
 PREFLIGHT (Step 0: quick_video.py --check)
 ┌──────────────────────────┐
 │  Verify NotebookLM conn  │
 │  ├─ Auth file exists?    │
 │  ├─ Token valid?         │
 │  ├─ API reachable?       │
 │  └─ Auto-login if needed │
 └──────────┬───────────────┘
            │ exit 0 = ok
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
| Transcription | `faster-whisper` GPU preferred (large-v3 float16), CPU fallback (small int8), isolated subprocess | Doubao ASR (permission issues) |
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

**Both Phase 1 and Phase 2 MUST use the `papertalker` conda environment.** Never use `conda run` (GBK crash).

**CRITICAL: Always set `PYTHONUNBUFFERED=1`** (or use `-u` flag) to prevent silent output buffering in non-TTY environments (subprocess, pipe). Without this, scripts appear to hang with 0 bytes output.

```bash
# Preferred: direct Python path + UTF-8 + unbuffered
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$(conda info --base)/envs/papertalker/python.exe" -u script.py

# Alternative: activate first
conda activate papertalker && PYTHONUNBUFFERED=1 python -u script.py
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

**NotebookLM** (auto-handled by `quick_video.py`):
When auth expires, the script automatically launches `tools/auto_login.py` which opens a browser. The user completes Google login; the script auto-detects completion and saves credentials. No terminal interaction needed.

Manual fallback if auto-login fails:
```bash
conda activate papertalker
python tools/auto_login.py
# Or: notebooklm login
```

**Bilibili** (auto-handled by `publish.py`):
When cookies are missing, `publish.py` automatically pops up a new terminal window running `biliup login`.
The user just scans the QR code with the Bilibili app; the script auto-detects cookie creation and continues.

Manual fallback if auto-login fails:
```bash
cd vendor
./biliup.exe -u ../cookies/bilibili/account.json login
# Select "扫码登录" -> scan QR with Bilibili app
```

For full setup (Conda install, Tsinghua mirrors, env creation), see [references/setup.md](references/setup.md).

## Phase 1: Video Generation (Upstream)

**Script:** `quick_video.py` — async pipeline using Google NotebookLM.

```bash
# Step 0: Connectivity check (MUST run first, separate call)
conda activate papertalker
PYTHONUNBUFFERED=1 python -u quick_video.py "虚拟细胞" --check

# Step 1: Generate video (only if Step 0 exits 0)
PYTHONUNBUFFERED=1 python -u quick_video.py "虚拟细胞" --no-confirm
```

### Upstream Pipeline

```
Step 0: Connectivity check (quick_video.py --check)
Step 1: Create NotebookLM notebook (title = topic)
Step 2: Gather sources (based on --source mode)
Step 3: Auto-confirm and proceed (--no-confirm skips interactive prompts)
Step 4: Import sources into notebook (batch 15, URL fallback)
Step 5: Wait for source processing (30s + 5s/source, max 180s)
Step 6: Generate video (submit task + poll status, up to 30 min)
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
| `--check` | false | Only test NotebookLM connectivity, do not generate video |
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

Videos saved as `output/{sanitized_topic}_{YYYYMMDD_HHMMSS}.mp4`. Deep Research takes 10-20 min; video generation takes 10-30+ min. If timeout or network failure, use `--resume NID TID` to continue polling.

## Phase 2: Post-Production & Publishing (Downstream)

**Script:** `publish.py` (project root) — scans `output/`, processes all videos.

```bash
conda activate papertalker
PYTHONUNBUFFERED=1 python -u publish.py
```

Or with direct path (Windows):
```bash
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "$(conda info --base)/envs/papertalker/python.exe" -u publish.py
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
| 2 | Extract Cover | First frame of **original** (un-subtitled) video as JPEG; dual FFmpeg approach for robustness |
| 3 | Transcribe | faster-whisper in isolated subprocess; GPU (large-v3 float16) preferred, CPU (small int8) fallback; MKL env vars auto-set |
| 4 | Generate SRT | Smart chunking: jieba word-aware split, max 18 chars/line, word-level time alignment |
| 5 | Burn Subtitles | FFmpeg subtitles filter (Microsoft YaHei, white + black outline, MarginV=30) |
| 6 | Upload | Auto-generated title/desc/tags, cover image, per platform |
| 7 | Cleanup | Delete original + WAV + cover temp, save run history JSON |

### Smart Metadata Generation

The script auto-generates B站-optimized metadata from the filename:

- **Topic extraction**: `虚拟细胞_20260303_223817.mp4` -> `虚拟细胞` (strip `_YYYYMMDD_HHMMSS`)
- **Title**: `【AI科研科普】{topic}：前沿研究深度解读` (max 80 chars)
- **Description**: Topic + duration + subtitle count + hashtags (max 250 chars)
- **Tags**: Self-adaptive based on topic content. Domain keyword detection (AI/Bio/Physics/etc.) adds relevant field tags. Splits compound topics (与/和/及/+/&). Max 12 tags.
  - Example: `Claude Code` -> `Claude Code,Anthropic,AI工具,编程,开发工具,AI科研,...`
  - Example: `蛋白质折叠与药物发现` -> `蛋白质折叠与药物发现,蛋白质折叠,药物发现,生物信息学,...`
- **Cover**: First frame of **original** (un-subtitled) video as JPEG; dual FFmpeg approach for robustness
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
| Python output buffering (0 bytes in subprocess) | `PYTHONUNBUFFERED=1` + `-u` flag for all invocations |
| `conda run` GBK crash | Direct Python path + `PYTHONIOENCODING=utf-8` |
| `conda install ffmpeg` fails | `pip install imageio-ffmpeg` |
| FFmpeg subtitle Windows paths | `path.replace('\\','/').replace(':','\\:')` |
| CUDA crash with `word_timestamps=True` in function scope | Subprocess transcribe (auto in publish.py) |
| MKL `mkl_malloc` memory failure on CPU | Set `MKL_THREADING_LAYER=sequential`, `OMP_NUM_THREADS=1` before import; use `small` model on CPU |
| biliup login interactive | Auto-handled: `publish.py` pops up login terminal when cookies missing |
| Playwright chromium version mismatch | `python -m playwright install chromium` (or upgrade playwright to match existing browser) |
| Network errors during video generation | Do NOT create a new notebook. Record NID+TID from output, wait 2-3 min, then `--resume NID TID` |
| NotebookLM auth expired | Auto-handled: `quick_video.py` calls `tools/auto_login.py` automatically |
| Doubao ASR 45000030 permission | Use `faster-whisper` local GPU instead |
| biliup < 1.0 blocked (21590) | `pip install "biliup>=1.1.29"` |
| `login_by_cookies` KeyError | Pass full `account` dict, NOT `account['cookie_info']` |

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
