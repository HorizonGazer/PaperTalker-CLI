#!/usr/bin/env python3
"""
publish.py - One-click downstream pipeline: subtitle + upload
=============================================================
Scans output/ for videos, transcribes, burns subtitles, uploads to Bilibili.

Usage:
    python publish.py                         # Process all videos in output/
    python publish.py --input output/         # Specify input dir
    python publish.py --skip-upload           # Subtitle only, no upload
    python publish.py --platforms bilibili douyin  # Choose platforms

Requires:
    pip install imageio-ffmpeg faster-whisper "biliup>=1.1.29"

Environment:
    Python: conda activate papertalker && python publish.py
    PYTHONIOENCODING=utf-8
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Windows GBK fix
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

# ── Config ──────────────────────────────────────────────────
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov"}
PLATFORMS = ["bilibili", "douyin", "weixin", "xiaohongshu", "kuaishou"]

def _find_project_root() -> Path:
    """Walk up from this file to find the project root (contains quick_video.py)."""
    d = Path(__file__).resolve().parent
    for _ in range(6):
        if (d / "quick_video.py").exists():
            return d
        d = d.parent
    return Path(__file__).resolve().parent  # fallback

PROJECT_ROOT = _find_project_root()
DEFAULT_INPUT = PROJECT_ROOT / "output"
DEFAULT_OUTPUT = PROJECT_ROOT / "output_subtitled"
COOKIE_FILE = PROJECT_ROOT / "cookies" / "bilibili" / "account.json"
RUN_HISTORY_FILE = PROJECT_ROOT / "skills" / "paper-talker" / "references" / "run_history.json"

# Subtitle display limits
MAX_CHARS_PER_LINE = 18  # Max Chinese chars per subtitle line (screen width)
MAX_DURATION_PER_SUB = 6.0  # Max seconds a single subtitle can display

# ── Colors ──────────────────────────────────────────────────
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; B = "\033[1m"; D = "\033[2m"; X = "\033[0m"

def ok(msg):   print(f"  {G}  ok{X} {msg}", flush=True)
def fail(msg): print(f"  {R}  FAIL{X} {msg}", flush=True)
def info(msg): print(f"  {D}    {msg}{X}", flush=True)


# ── Title / Tag / Desc helpers ──────────────────────────────

def extract_topic(filename: str) -> str:
    """Extract clean topic from filename like '虚拟细胞_20260303_223817'."""
    name = Path(filename).stem
    # Remove trailing _YYYYMMDD_HHMMSS pattern
    name = re.sub(r"_\d{8}_\d{6}$", "", name)
    return name


def make_title(topic: str) -> str:
    """Generate a descriptive B站 video title from topic."""
    return f"【AI科研科普】{topic}：前沿研究深度解读"


def make_desc(topic: str, seg_count: int, duration_str: str) -> str:
    """Generate video description."""
    return (
        f"本视频由 AI 自动生成，基于 {topic} 领域最新研究文献，"
        f"通过 NotebookLM 深度分析后制作。\n"
        f"内容涵盖 {topic} 的研究背景、核心方法与关键发现。\n"
        f"时长：{duration_str} | 字幕：{seg_count} 句\n\n"
        f"#AI科研 #{topic} #学术科普 #论文解读"
    )


def make_tags(topic: str) -> str:
    """Generate relevant B站 tags (comma-separated, max 12 tags)."""
    base_tags = ["AI科研", "学术科普", "论文解读", "前沿研究", "深度解读"]
    # Add topic-specific tags
    topic_tags = [topic]
    # Split topic if it contains common delimiters
    for sep in ["与", "和", "及"]:
        if sep in topic:
            topic_tags.extend(topic.split(sep))
    all_tags = topic_tags + base_tags
    # Deduplicate while preserving order, max 12
    seen = set()
    unique = []
    for t in all_tags:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    return ",".join(unique[:12])


# ── Cover extraction ────────────────────────────────────────

def extract_cover(ffmpeg: str, video_path: Path, cover_path: Path) -> bool:
    """Extract first frame as cover image (JPEG)."""
    result = subprocess.run(
        [ffmpeg, "-i", str(video_path), "-vframes", "1", "-q:v", "2",
         "-y", str(cover_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.returncode == 0 and cover_path.exists()


# ── Pre-flight ──────────────────────────────────────────────

def preflight_check() -> bool:
    """Verify all required dependencies are available. Returns True if all ok."""
    import importlib
    all_ok = True
    deps = [
        ("imageio_ffmpeg", "imageio-ffmpeg", "pip install imageio-ffmpeg"),
        ("faster_whisper", "faster-whisper", "pip install faster-whisper"),
        ("biliup", "biliup", 'pip install "biliup>=1.1.29"'),
    ]
    print("Pre-flight check:")
    for mod, name, fix in deps:
        try:
            importlib.import_module(mod)
            print(f"  {G}ok{X}   {name}")
        except ImportError:
            print(f"  {R}MISS{X} {name}  ->  {fix}")
            all_ok = False

    # Check FFmpeg binary
    try:
        import imageio_ffmpeg
        imageio_ffmpeg.get_ffmpeg_exe()
        print(f"  {G}ok{X}   ffmpeg binary")
    except Exception:
        print(f"  {R}MISS{X} ffmpeg binary  ->  pip install imageio-ffmpeg")
        all_ok = False

    # Check Bilibili cookies
    if COOKIE_FILE.exists():
        print(f"  {G}ok{X}   bilibili cookies")
    else:
        print(f"  {Y}MISS{X} bilibili cookies (upload will fail)")

    print()
    return all_ok


def scan_videos(input_dir: Path) -> list[Path]:
    """Scan for video files in input directory."""
    videos = sorted(
        [f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXTS],
        key=lambda f: f.name,
    )
    return videos


def get_ffmpeg():
    """Get FFmpeg path from imageio-ffmpeg."""
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def extract_audio(ffmpeg: str, video_path: Path, wav_path: Path) -> bool:
    """Extract audio from video to 16kHz mono WAV."""
    result = subprocess.run(
        [ffmpeg, "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", str(wav_path), "-y"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.returncode == 0


def transcribe(wav_path: Path) -> list:
    """Transcribe audio using faster-whisper large-v3 with word-level timestamps.

    Runs in a subprocess to avoid CUDA crash when word_timestamps=True
    is used inside a function scope on Windows (CTranslate2 bug).
    Falls back to in-process without word timestamps if subprocess fails.
    """
    import pickle, tempfile

    # Subprocess script: runs transcription at module level to avoid CUDA bug
    script = f'''
import pickle, sys
from pathlib import Path
from faster_whisper import WhisperModel

model = WhisperModel("large-v3", device="cuda", compute_type="float16")
segments, info = model.transcribe(
    {str(wav_path)!r}, language="zh", beam_size=5,
    vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
    word_timestamps=True,
)
seg_list = list(segments)

# Serialize segments as dicts (can't pickle CTranslate2 objects)
data = []
for s in seg_list:
    d = {{"start": s.start, "end": s.end, "text": s.text}}
    if hasattr(s, "words") and s.words:
        d["words"] = [{{"start": w.start, "end": w.end, "word": w.word}} for w in s.words]
    data.append(d)

with open(sys.argv[1], "wb") as f:
    pickle.dump(data, f)
'''
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
        pkl_path = tmp.name

    result = subprocess.run(
        [sys.executable, "-c", script, pkl_path],
        capture_output=True, text=True, timeout=600,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    if Path(pkl_path).exists() and Path(pkl_path).stat().st_size > 0:
        with open(pkl_path, "rb") as f:
            data = pickle.load(f)
        Path(pkl_path).unlink(missing_ok=True)

        # Convert dicts back to named-tuple-like objects
        class Seg:
            def __init__(self, d):
                self.start = d["start"]
                self.end = d["end"]
                self.text = d["text"]
                self.words = None
                if "words" in d:
                    self.words = [type("W", (), w) for w in d["words"]]
        return [Seg(d) for d in data]

    # Fallback: in-process without word timestamps
    Path(pkl_path).unlink(missing_ok=True)
    from faster_whisper import WhisperModel
    model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    segments, seg_info = model.transcribe(
        str(wav_path), language="zh", beam_size=5,
        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
    )
    return list(segments)


def seconds_to_srt(s: float) -> str:
    """Convert seconds to SRT time format."""
    h, m = int(s) // 3600, int(s) % 3600 // 60
    sec, ms = int(s) % 60, int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def chunk_subtitle_text(text: str, max_chars: int = MAX_CHARS_PER_LINE) -> list[str]:
    """Split long text into multiple display lines for subtitle readability.

    Rules:
    - Each line <= max_chars characters
    - Prefer splitting at punctuation: ，。、；！？：
    - Otherwise split at word boundaries using jieba
    - Never break in the middle of a word
    """
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import jieba
    jieba.setLogLevel(jieba.logging.WARNING)
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    lines = []
    remaining = text
    punct = set("，。、；！？：,.;!?:")

    while remaining:
        if len(remaining) <= max_chars:
            lines.append(remaining)
            break

        # Priority 1: split at punctuation within max_chars
        best_split = -1
        for i in range(min(max_chars, len(remaining)) - 1, -1, -1):
            if remaining[i] in punct:
                best_split = i + 1  # Include the punctuation
                break

        if best_split > 0:
            lines.append(remaining[:best_split])
            remaining = remaining[best_split:]
            continue

        # Priority 2: split at word boundary using jieba
        words = list(jieba.cut(remaining))
        line = ""
        split_found = False
        consumed = 0
        for w in words:
            if len(line) + len(w) > max_chars:
                if line:  # Have accumulated words, split here
                    lines.append(line)
                    remaining = remaining[consumed:]
                    split_found = True
                    break
                else:  # Single word exceeds max_chars, take it whole
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


def generate_srt(segments: list, srt_path: Path) -> int:
    """Generate SRT file from whisper segments with smart chunking.

    - Uses word-level timestamps for precise time alignment
    - Splits at natural word boundaries via jieba
    - Limits display duration per subtitle
    - Returns total subtitle entry count
    """
    entries = []
    idx = 0

    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue

        duration = seg.end - seg.start
        lines = chunk_subtitle_text(text)
        n_lines = len(lines)

        if n_lines == 1 and duration <= MAX_DURATION_PER_SUB:
            idx += 1
            entries.append((idx, seg.start, seg.end, text))
        elif hasattr(seg, 'words') and seg.words:
            # Use word-level timestamps for precise alignment
            words = list(seg.words)
            word_idx = 0
            for line in lines:
                # Find how many words belong to this line
                chars_remaining = len(line)
                line_start = None
                line_end = None
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

                if line_start is None:
                    line_start = seg.start
                if line_end is None:
                    line_end = seg.end
                idx += 1
                entries.append((idx, line_start, line_end, line))
        else:
            # Fallback: proportional time distribution
            time_per_line = duration / n_lines
            for j, line in enumerate(lines):
                idx += 1
                t_start = seg.start + j * time_per_line
                t_end = seg.start + (j + 1) * time_per_line
                entries.append((idx, t_start, t_end, line))

    srt_lines = []
    for num, start, end, text in entries:
        srt_lines.append(str(num))
        srt_lines.append(f"{seconds_to_srt(start)} --> {seconds_to_srt(end)}")
        srt_lines.append(text)
        srt_lines.append("")

    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    return len(entries)


def burn_subtitles(ffmpeg: str, input_mp4: Path, srt_path: Path, output_mp4: Path) -> bool:
    """Burn hardcoded subtitles into video using FFmpeg (lossless quality)."""
    srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
    vf = (
        f"subtitles='{srt_escaped}':force_style='"
        f"FontSize=20,FontName=Microsoft YaHei,"
        f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        f"Outline=2,MarginV=30'"
    )
    # -crf 0: mathematically lossless H.264
    # -preset fast: balance encode speed vs file size (lossless ignores most preset effects)
    # -c:a copy: audio stream untouched
    result = subprocess.run(
        [ffmpeg, "-i", str(input_mp4), "-vf", vf,
         "-c:v", "libx264", "-crf", "0", "-preset", "fast",
         "-c:a", "copy", "-y", str(output_mp4)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.returncode == 0


def upload_bilibili(video_path: Path, title: str, desc: str, tags: str,
                    cover_path: Path = None) -> dict:
    """Upload video to Bilibili with title, desc, tags, and optional cover."""
    if not COOKIE_FILE.exists():
        return {"ok": False, "bvid": "", "error": f"Cookie not found: {COOKIE_FILE}"}

    try:
        from biliup.plugins.bili_webup import BiliBili, Data

        with open(COOKIE_FILE, "r") as f:
            account = json.load(f)

        data = Data()
        data.copyright = 1
        data.title = title[:80]  # B站 title limit
        data.desc = desc[:250]   # B站 desc limit
        data.tid = 201  # 科学科普
        data.tag = tags
        data.dtime = 0

        with BiliBili(data) as bili:
            bili.login_by_cookies(account)
            bili.access_token = account.get("token_info", {}).get("access_token", "")

            # Upload cover image first to get URL (B站 requires uploaded URL, not local path)
            if cover_path and cover_path.exists():
                try:
                    cover_url = bili.cover_up(str(cover_path))
                    data.cover = cover_url
                except Exception as e:
                    info(f"Cover upload failed ({e}), using auto-generated cover")

            video_part = bili.upload_file(str(video_path), lines="AUTO", tasks=3)
            video_part["title"] = title[:80]
            data.append(video_part)
            ret = bili.submit()
            bvid = ret.get("data", {}).get("bvid", "")
            return {"ok": True, "bvid": bvid, "error": ""}

    except Exception as e:
        return {"ok": False, "bvid": "", "error": str(e)}


# ── Run history ─────────────────────────────────────────────

def load_run_history() -> list:
    """Load previous successful run records."""
    if RUN_HISTORY_FILE.exists():
        try:
            return json.loads(RUN_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_run_record(record: dict):
    """Append a successful run record to history."""
    history = load_run_history()
    history.append(record)
    # Keep last 50 records
    history = history[-50:]
    RUN_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    RUN_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Main pipeline ───────────────────────────────────────────

def process_video(
    video_path: Path,
    date_dir: Path,
    index: int,
    total: int,
    ffmpeg: str,
    platforms: list[str],
    skip_upload: bool,
) -> dict:
    """Process a single video through the full downstream pipeline."""
    raw_name = video_path.stem
    topic = extract_topic(raw_name)
    result = {"video": raw_name, "topic": topic, "subtitle": "FAIL", "uploads": {}}

    print(f"\n--- [{index}/{total}] {video_path.name} ---")
    print(f"  Topic: {C}{topic}{X}")

    # Step 1: Extract audio
    wav_path = date_dir / f"{topic}.wav"
    print(f"[1/7] Extract audio......... ", end="", flush=True)
    if extract_audio(ffmpeg, video_path, wav_path):
        ok("")
    else:
        fail("FFmpeg audio extraction failed")
        return result

    # Step 2: Extract cover (first frame)
    cover_path = date_dir / f"{topic}_cover.jpg"
    print(f"[2/7] Extract cover......... ", end="", flush=True)
    if extract_cover(ffmpeg, video_path, cover_path):
        ok(f"-> {cover_path.name}")
    else:
        info("(failed, will use default)")
        cover_path = None

    # Step 3: Transcribe
    print(f"[3/7] Transcribe............ ", end="", flush=True)
    try:
        segments = transcribe(wav_path)
        total_dur = segments[-1].end if segments else 0
        mins, secs = int(total_dur) // 60, int(total_dur) % 60
        duration_str = f"{mins}:{secs:02d}"
        ok(f"({len(segments)} segments, {duration_str})")
    except Exception as e:
        fail(str(e))
        return result

    # Step 4: Generate SRT (with smart chunking)
    srt_path = date_dir / f"{topic}.srt"
    print(f"[4/7] Generate SRT.......... ", end="", flush=True)
    count = generate_srt(segments, srt_path)
    ok(f"({count} subtitles) -> {date_dir.name}/{topic}.srt")
    result["subtitle"] = "ok"
    result["sub_count"] = count

    # Step 5: Burn subtitles
    output_mp4 = date_dir / f"{topic}.mp4"
    print(f"[5/7] Burn subtitles........ ", end="", flush=True)
    if burn_subtitles(ffmpeg, video_path, srt_path, output_mp4):
        ok(f"-> {date_dir.name}/{topic}.mp4")
    else:
        fail("FFmpeg subtitle burn failed")
        return result

    # Step 6: Upload with smart title/desc/tags
    title = make_title(topic)
    desc = make_desc(topic, count, duration_str)
    tags = make_tags(topic)

    print(f"[6/7] Upload:")
    info(f"Title: {title}")
    info(f"Tags:  {tags}")

    if skip_upload:
        info("(skipped)")
    else:
        for plat in platforms:
            if plat == "bilibili":
                ret = upload_bilibili(output_mp4, title, desc, tags, cover_path)
                if ret["ok"]:
                    print(f"      Bilibili  {G}ok{X}  {ret['bvid']}")
                    result["uploads"]["bilibili"] = f"ok:{ret['bvid']}"
                else:
                    print(f"      Bilibili  {R}FAIL{X}  {ret['error']}")
                    result["uploads"]["bilibili"] = f"FAIL:{ret['error']}"
            else:
                print(f"      {plat.capitalize()}  {Y}-{X}  (not implemented)")
                result["uploads"][plat] = "-"

    # Step 7: Cleanup
    print(f"[7/7] Cleanup............... ", end="", flush=True)
    try:
        wav_path.unlink(missing_ok=True)
        if cover_path:
            cover_path.unlink(missing_ok=True)
        # Only delete original if upload succeeded (or was skipped)
        upload_ok = skip_upload or all(
            v.startswith("ok") for v in result["uploads"].values() if v != "-"
        )
        if upload_ok:
            video_path.unlink(missing_ok=True)
            ok("(original + temp deleted)")
        else:
            ok("(temp deleted, original kept — upload failed)")
    except Exception as e:
        fail(str(e))

    # Save run history
    record = {
        "date": datetime.now().isoformat(),
        "topic": topic,
        "file": raw_name,
        "subtitles": count,
        "duration": duration_str,
        "title": title,
        "tags": tags,
        "uploads": result["uploads"],
    }
    save_run_record(record)

    return result


def main():
    parser = argparse.ArgumentParser(description="Video post-production: subtitle + upload")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input video directory")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output base directory")
    parser.add_argument("--platforms", nargs="+", default=["bilibili"],
                        choices=PLATFORMS, help="Upload platforms")
    parser.add_argument("--skip-upload", action="store_true", help="Skip upload step")
    args = parser.parse_args()

    input_dir = Path(args.input).resolve()
    output_base = Path(args.output).resolve()

    # Pre-flight dependency check
    if not preflight_check():
        print(f"{R}Missing dependencies. Install them and retry.{X}")
        sys.exit(1)

    # Show run history summary
    history = load_run_history()
    if history:
        last = history[-1]
        print(f"Last run: {D}{last.get('date','?')[:10]} | {last.get('topic','?')} | {last.get('uploads',{})}{X}")
        print()

    # Scan
    print(f"Scanning {input_dir}...", end=" ", flush=True)
    videos = scan_videos(input_dir)
    print(f"found {len(videos)} videos.")

    if not videos:
        print("No videos to process.")
        return

    for v in videos:
        size_mb = v.stat().st_size / (1024 * 1024)
        info(f"{v.name} ({size_mb:.1f} MB)")

    # Create date folder
    today = datetime.now().strftime("%Y-%m-%d")
    date_dir = output_base / today
    date_dir.mkdir(parents=True, exist_ok=True)
    print(f"Date folder: {date_dir}")

    # Get FFmpeg
    ffmpeg = get_ffmpeg()

    # Process each video
    results = []
    for i, video in enumerate(videos, 1):
        r = process_video(video, date_dir, i, len(videos), ffmpeg,
                          args.platforms, args.skip_upload)
        results.append(r)

    # Summary report
    print(f"\n{'='*70}")
    print(f"{'Summary':^70}")
    print(f"{'='*70}")
    header = "| Topic | Subtitle |"
    sep = "|-------|----------|"
    for plat in args.platforms:
        header += f" {plat.capitalize():^11} |"
        sep += f"{'-'*13}|"
    print(header)
    print(sep)
    for r in results:
        topic = r.get("topic", r["video"])[:20]
        row = f"| {topic:20} | {r['subtitle']:8} |"
        for plat in args.platforms:
            val = r["uploads"].get(plat, "-")
            row += f" {val[:11]:11} |"
        print(row)
    print()


if __name__ == "__main__":
    main()
