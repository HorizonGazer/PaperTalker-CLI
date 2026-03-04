# Downstream: Post-Production & Publishing

## Overview

Script: `publish.py` (project root; distributable copy at `skills/paper-talker/scripts/publish.py`)

After `quick_video.py` saves raw videos to `output/`, the downstream pipeline handles:
1. Audio extraction (FFmpeg via imageio-ffmpeg)
2. Cover extraction (first frame as JPEG)
3. Speech-to-text transcription (faster-whisper, local GPU)
4. SRT subtitle generation (smart chunking)
5. Hardcoded subtitle burn-in (FFmpeg)
6. Multi-platform upload with auto-generated metadata
7. Cleanup (delete originals, organize by date, save run history)

## One-Click Usage

```bash
conda activate papertalker
python publish.py
```

Or with direct path (Windows):
```bash
PYTHONIOENCODING=utf-8 "$(conda info --base)/envs/papertalker/python.exe" publish.py
```

Options:
```bash
--skip-upload              # Subtitle only, no upload
--platforms bilibili douyin # Choose platforms
--input output/            # Custom input dir
--output output_subtitled/ # Custom output dir
```

## Directory Convention

| Directory | Purpose |
|-----------|---------|
| `output/` | Raw input videos (source). **Cleared after processing.** |
| `output_subtitled/YYYY-MM-DD/` | Final subtitled videos + SRT files |

## Step-by-Step Implementation

### Step 1: Extract Audio

Use `imageio-ffmpeg` (pip package, bundles static FFmpeg binary):

```python
import imageio_ffmpeg, subprocess
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([ffmpeg, '-i', input_mp4, '-vn', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1', output_wav, '-y'])
```

**DO NOT** use `conda install ffmpeg` (GBK encoding errors on Windows).

### Step 2: Extract Cover

Extract first video frame as JPEG for B站 thumbnail:

```python
cover_path = date_dir / f"{topic}_cover.jpg"
subprocess.run([ffmpeg, '-i', str(video_path), '-vframes', '1', '-q:v', '2',
                '-y', str(cover_path)], capture_output=True, text=True)
```

Cover is uploaded with the video and deleted during cleanup.

### Step 3: Transcribe (faster-whisper, local GPU, subprocess)

Use `faster-whisper` with `large-v3` model and **word-level timestamps** for best Chinese accuracy and precise subtitle timing.

**IMPORTANT:** On Windows, `word_timestamps=True` crashes the Python process when called inside a function scope (CTranslate2/CUDA bug). The `publish.py` script works around this by running transcription in a **subprocess** where the code executes at module level:

```python
# publish.py transcribe() internally does:
# 1. Spawns subprocess with inline script (module-level code)
# 2. Subprocess runs whisper with word_timestamps=True
# 3. Serializes results via pickle to temp file
# 4. Parent process reads pickle and reconstructs segment objects
# 5. Falls back to in-process (no word timestamps) if subprocess fails
```

The subprocess script (runs at module level to avoid CUDA bug):
```python
from faster_whisper import WhisperModel
model = WhisperModel("large-v3", device="cuda", compute_type="float16")
segments, info = model.transcribe(wav_path, language="zh", beam_size=5,
    vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
    word_timestamps=True)
```

`word_timestamps=True` makes Whisper return per-word start/end times, enabling precise subtitle time alignment instead of proportional guessing.

First run downloads ~3GB model. Subsequent runs use cached model.

**Note:** Doubao ASR 2.0 API is an alternative but requires a publicly accessible audio URL and may have permission issues (error 45000030). See [doubao_asr.md](doubao_asr.md).

### Step 4: Generate SRT (Smart Chunking with jieba)

Convert whisper segments to SRT with word-boundary-aware text splitting:

```python
import jieba

MAX_CHARS_PER_LINE = 18  # Max Chinese chars per subtitle line
MAX_DURATION_PER_SUB = 6.0  # Max seconds per subtitle display

def chunk_subtitle_text(text, max_chars=18):
    """Split long text at punctuation or word boundaries (jieba), never mid-word."""
    if len(text) <= max_chars:
        return [text]
    lines = []
    remaining = text
    punct = set("，。、；！？：,.;!?:")
    while remaining:
        if len(remaining) <= max_chars:
            lines.append(remaining)
            break
        # Priority 1: split at punctuation
        best = -1
        for i in range(min(max_chars, len(remaining)) - 1, -1, -1):
            if remaining[i] in punct:
                best = i + 1
                break
        if best > 0:
            lines.append(remaining[:best])
            remaining = remaining[best:]
            continue
        # Priority 2: split at word boundary using jieba
        words = list(jieba.cut(remaining))
        line = ""
        split_found = False
        consumed = 0
        for w in words:
            if len(line) + len(w) > max_chars:
                if line:
                    lines.append(line)
                    remaining = remaining[consumed:]
                    split_found = True
                    break
                else:
                    lines.append(w)
                    remaining = remaining[len(w):]
                    split_found = True
                    break
            line += w
            consumed += len(w)
        if not split_found:
            lines.append(remaining)
            break
    return lines

def generate_srt(segments, srt_path):
    """Uses word-level timestamps for precise time alignment per subtitle line."""
    entries = []
    idx = 0
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        duration = seg.end - seg.start
        lines = chunk_subtitle_text(text)
        n = len(lines)
        if n == 1 and duration <= MAX_DURATION_PER_SUB:
            idx += 1
            entries.append((idx, seg.start, seg.end, text))
        elif hasattr(seg, 'words') and seg.words:
            # Word-level timestamp alignment
            words = list(seg.words)
            word_idx = 0
            for line in lines:
                chars_remaining = len(line)
                line_start = line_end = None
                while word_idx < len(words) and chars_remaining > 0:
                    w = words[word_idx]
                    w_text = w.word.strip()
                    if not w_text:
                        word_idx += 1
                        continue
                    if line_start is None:
                        line_start = w.start
                    line_end = w.end
                    chars_remaining -= len(w_text)
                    word_idx += 1
                idx += 1
                entries.append((idx, line_start or seg.start, line_end or seg.end, line))
        else:
            # Fallback: proportional time distribution
            time_per_line = duration / n
            for j, line in enumerate(lines):
                idx += 1
                t_start = seg.start + j * time_per_line
                t_end = seg.start + (j + 1) * time_per_line
                entries.append((idx, t_start, t_end, line))
    # Write SRT
    srt_lines = []
    for num, start, end, text in entries:
        srt_lines.append(str(num))
        srt_lines.append(f"{seconds_to_srt(start)} --> {seconds_to_srt(end)}")
        srt_lines.append(text)
        srt_lines.append("")
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    return len(entries)
```

**Key improvement:** Before jieba, hard char-splits produced unnatural breaks like "复刻一个活" / "生生的细胞". Now splits at word boundaries: "复刻一个" / "活生生的细胞".

**Dependency:** `pip install jieba` (pure Python, ~19MB dictionary)

### Step 5: Burn Hardcoded Subtitles

**FFmpeg via imageio-ffmpeg (primary method):**

```python
srt_escaped = str(srt_path).replace('\\', '/').replace(':', '\\:')
vf = (f"subtitles='{srt_escaped}':force_style='"
      f"FontSize=20,FontName=Microsoft YaHei,"
      f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
      f"Outline=2,MarginV=30'")
subprocess.run([ffmpeg, '-i', str(input_mp4), '-vf', vf,
                '-c:a', 'copy', '-y', str(output_mp4)])
```

**Critical:** On Windows, FFmpeg subtitle filter path needs forward slashes and escaped colons.

**Alternative - VectCutAPI:** Generates JianYing draft project (NOT rendered video). User must open in JianYing to export. Only use when editable subtitles needed. See [vectcut_api.md](vectcut_api.md).

### Step 6: Upload with Smart Metadata

Auto-generated metadata from filename:

```python
def extract_topic(filename):
    """虚拟细胞_20260303_223817 -> 虚拟细胞"""
    name = Path(filename).stem
    return re.sub(r"_\d{8}_\d{6}$", "", name)

def make_title(topic):
    return f"【AI科研科普】{topic}：前沿研究深度解读"

def make_desc(topic, seg_count, duration_str):
    return (f"本视频由 AI 自动生成，基于 {topic} 领域最新研究文献，"
            f"通过 NotebookLM 深度分析后制作。\n"
            f"内容涵盖 {topic} 的研究背景、核心方法与关键发现。\n"
            f"时长：{duration_str} | 字幕：{seg_count} 句\n\n"
            f"#AI科研 #{topic} #学术科普 #论文解读")

def make_tags(topic):
    base = ["AI科研", "学术科普", "论文解读", "前沿研究", "深度解读"]
    topic_tags = [topic]
    for sep in ["与", "和", "及"]:
        if sep in topic:
            topic_tags.extend(topic.split(sep))
    all_tags = topic_tags + base
    # Deduplicate, max 12
    seen = set()
    unique = [t.strip() for t in all_tags if t.strip() and t.strip() not in seen and not seen.add(t.strip())]
    return ",".join(unique[:12])
```

#### Bilibili Upload (tested, working)

```python
import json
from biliup.plugins.bili_webup import BiliBili, Data

with open(cookie_file, 'r') as f:
    account = json.load(f)  # pass FULL dict, NOT account['cookie_info']

data = Data()
data.copyright = 1
data.title = title[:80]       # B站 title limit
data.desc = desc[:250]        # B站 desc limit
data.tid = 201                # 科学科普 category
data.tag = tags               # comma-separated, max 12
data.dtime = 0                # publish immediately
if cover_path and cover_path.exists():
    data.cover = str(cover_path)

with BiliBili(data) as bili:
    bili.login_by_cookies(account)
    bili.access_token = account.get('token_info', {}).get('access_token', '')
    video_part = bili.upload_file(str(video_path), lines='AUTO', tasks=3)
    video_part['title'] = title[:80]
    data.append(video_part)
    ret = bili.submit()  # ret['data']['bvid'] = BV number
```

Requires `biliup>=1.1.29` (older versions blocked by Bilibili error 21590).

Cookie file: `cookies/bilibili/account.json`

First-time login (interactive, **cannot run from Claude CLI**):
```bash
cd vendor
./biliup.exe -u ../cookies/bilibili/account.json login
```
Select "扫码登录", scan QR with Bilibili app.

### Step 7: Cleanup + Run History

After all uploads:
- **Delete** original video from `output/`
- **Delete** WAV audio temp file
- **Delete** cover JPEG temp file
- **Keep** subtitled video + SRT in `output_subtitled/YYYY-MM-DD/`
- **Save** run record to `references/run_history.json` (last 50 records)

Run history record format:
```json
{
    "date": "2026-03-03T23:22:47.266137",
    "topic": "虚拟细胞",
    "file": "虚拟细胞_20260303_223817",
    "subtitles": 295,
    "duration": "9:39",
    "title": "【AI科研科普】虚拟细胞：前沿研究深度解读",
    "tags": "虚拟细胞,AI科研,学术科普,论文解读,前沿研究,深度解读",
    "uploads": {"bilibili": "ok:BV1wjAfztECV"}
}
```

## Output Naming

```
output_subtitled/YYYY-MM-DD/{topic}.mp4   # subtitled video (clean name)
output_subtitled/YYYY-MM-DD/{topic}.srt   # subtitle file
```

Topic is extracted from filename by stripping `_YYYYMMDD_HHMMSS` suffix.

## Progress Display

```
Pre-flight check:
  ok   imageio-ffmpeg / faster-whisper / biliup / ffmpeg / cookies
Last run: 2026-03-03 | 虚拟细胞 | bilibili: ok:BV1wjAfztECV

Scanning output/... found 1 videos.
Date folder: output_subtitled/2026-03-03/

--- [1/1] 虚拟细胞_20260303_223817.mp4 ---
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

## Summary Report

```
======================================================================
                              Summary
======================================================================
| Topic                | Subtitle |   Bilibili  |
|----------------------|----------|-------------|
| 虚拟细胞              | ok       | ok:BVxxxxx  |
```
