# Upstream: Video Generation (quick_video.py)

## Overview

`quick_video.py` automates the full pipeline from a research topic to a downloaded MP4 video via Google NotebookLM. It handles notebook creation, source gathering (4 modes), source importing, video generation, polling, and downloading.

## CLI Usage

```bash
# Activate conda env first
conda activate papertalker

# Basic (Deep Research, default)
python quick_video.py "生物智能体"

# Paper search with platform/year filters
python quick_video.py "蛋白质折叠" --source search --platforms arxiv pubmed --year 2024

# Manual upload
python quick_video.py "量子计算" --source upload

# Mixed mode (Deep Research + paper search)
python quick_video.py "LLM药物发现" --source mixed --platforms semantic_scholar --year 2026

# Custom style
python quick_video.py "蛋白质折叠" --style anime

# Resume a timed-out video
python quick_video.py "脑机接口" --resume <notebook_id> <task_id>
```

## All CLI Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `topic` | (required) | Video topic |
| `--source` | `research` | Source mode: research / search / upload / mixed |
| `--style` | `whiteboard` | Video style (see table below) |
| `--lang` | `zh-CN` | Language code |
| `--mode` | `deep` | Deep Research depth: fast / deep |
| `--platforms` | arxiv semantic_scholar | Paper search platforms (space-separated) |
| `--max-results` | `10` | Max results per platform |
| `--year` | none | Paper year filter |
| `--output` | `./output` | Video output directory |
| `--timeout` | `1800` | Video generation timeout (seconds) |
| `--instructions` | video.md | Custom video instruction text |
| `--no-confirm` | false | Skip stage confirmations |
| `--resume NID TID` | — | Resume a timed-out video task |

## Source Modes

| Mode | Behavior | Best For |
|------|----------|----------|
| `research` | NotebookLM Deep Research auto-searches the web | General topics, current tech |
| `search` | paper-search-mcp searches academic databases | Specific academic domains |
| `upload` | Opens notebook URL for manual file upload | Existing documents |
| `mixed` | Deep Research + paper search combined | Comprehensive coverage |

## Video Styles

| Style | Enum | Description |
|-------|------|-------------|
| `whiteboard` | WHITEBOARD | Whiteboard hand-drawn (default) |
| `classic` | CLASSIC | Classic style |
| `anime` | ANIME | Anime style |
| `kawaii` | KAWAII | Cute style |
| `watercolor` | WATERCOLOR | Watercolor painting |
| `retro_print` | RETRO_PRINT | Retro print |
| `heritage` | HERITAGE | Traditional style |
| `paper_craft` | PAPER_CRAFT | Paper craft |
| `auto` | AUTO_SELECT | AI auto-selects |

## Paper Search Platforms

| Platform | ID | Domain |
|----------|----|--------|
| arXiv | `arxiv` | Physics, math, CS |
| PubMed | `pubmed` | Biomedical |
| bioRxiv | `biorxiv` | Biology preprints |
| medRxiv | `medrxiv` | Medical preprints |
| Semantic Scholar | `semantic_scholar` | Cross-discipline |
| Google Scholar | `google_scholar` | General academic |
| CrossRef | `crossref` | Publication metadata |
| IACR | `iacr` | Cryptography |

## 7-Step Pipeline

```
Step 1: Create NotebookLM notebook (title = topic)
Step 2: Gather sources (based on --source mode)
Step 3: Stage confirmation (show source list, wait for user)
Step 4: Import sources into notebook (batch 15, URL fallback)
Step 5: Wait for source processing (30s + 3s per source, max 90s)
Step 6: Generate video (submit + poll + download)
Step 7: Download MP4 to output/{topic}_{timestamp}.mp4
```

## Output Convention

Video files saved to `output/` with naming pattern:
```
{sanitized_topic}_{YYYYMMDD_HHMMSS}.mp4
```

Characters not in `[a-zA-Z0-9._- ]` are replaced with `_`, truncated to 50 chars.

## Authentication

- NotebookLM auth: `~/.notebooklm/storage_state.json` (Playwright browser state)
- First-time login: `notebooklm login` (opens browser, complete Google login)
- Override path: `NOTEBOOKLM_STORAGE_PATH` env var

## Video Generation Prompt (video.md)

Default prompt enforces:
- Simplified Chinese output
- Strict academic rigor with specific numbers (p-values, accuracy, AUC, etc.)
- Original figures and formulas from source papers
- High information density for researchers/graduate students
- No vague language ("显著提升" forbidden, must give exact values)

## Timeout Recovery

Video generation typically takes 10-20 minutes. If timeout occurs:
```bash
# Script prints recovery command:
python quick_video.py "topic" --resume <notebook_id> <task_id>
```

Resume mode polls status and downloads when ready, no re-generation needed.
