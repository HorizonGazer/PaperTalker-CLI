#!/usr/bin/env python3
"""
publish.py - One-click downstream pipeline: subtitle + upload
=============================================================
Scans output/ for videos, transcribes, burns subtitles, uploads to platforms.

Usage:
    python publish.py                         # Process all videos in output/
    python publish.py --input output/         # Specify input dir
    python publish.py --skip-upload           # Subtitle only, no upload
    python publish.py --platforms bilibili weixin_channels  # Choose platforms

Requires:
    pip install imageio-ffmpeg faster-whisper "biliup>=1.1.29" playwright python-dotenv requests

Environment:
    Python: conda activate papertalker && python publish.py
    PYTHONIOENCODING=utf-8
"""

# MKL env vars must be set before any CTranslate2/faster_whisper import
import os as _os
_os.environ.setdefault("MKL_THREADING_LAYER", "sequential")
_os.environ.setdefault("OMP_NUM_THREADS", "1")
_os.environ.setdefault("MKL_NUM_THREADS", "1")

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
PLATFORMS = ["bilibili", "douyin", "weixin", "weixin_channels", "weixin_article", "xiaohongshu", "kuaishou"]
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = PROJECT_ROOT / "output"
DEFAULT_OUTPUT = PROJECT_ROOT / "output_subtitled"
COOKIE_FILE = PROJECT_ROOT / "cookies" / "bilibili" / "account.json"
WEIXIN_STORAGE_STATE = PROJECT_ROOT / "cookies" / "weixin" / "storage_state.json"
WEIXIN_MP_PROFILE_DIR = PROJECT_ROOT / "cookies" / "weixin_mp" / "browser_profile"
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
    """Generate self-adaptive B站 tags based on topic content.

    - Detects domain keywords to add relevant field tags
    - Splits compound topics (与/和/及, spaces, +)
    - Keeps base tags for discoverability
    - Max 12 tags, each tag max 20 chars
    """
    # Domain keyword -> extra tags mapping
    DOMAIN_TAGS = {
        # AI / CS
        "AI": ["人工智能", "AI技术"],
        "LLM": ["大语言模型", "AI技术"],
        "GPT": ["大语言模型", "ChatGPT"],
        "Claude": ["Anthropic", "AI工具"],
        "Copilot": ["AI编程", "代码助手"],
        "Cursor": ["AI编程", "代码助手"],
        "Code": ["编程", "开发工具"],
        "Agent": ["AI Agent", "智能体"],
        "机器学习": ["深度学习", "AI技术"],
        "深度学习": ["神经网络", "AI技术"],
        "强化学习": ["AI技术"],
        "计算机视觉": ["CV", "图像识别"],
        "自然语言": ["NLP"],
        "大模型": ["大语言模型", "AI技术"],
        "Transformer": ["深度学习", "注意力机制"],
        # Bio / Med
        "蛋白质": ["生物信息学", "结构生物学"],
        "基因": ["基因组学", "生物技术"],
        "药物": ["药物发现", "制药"],
        "细胞": ["细胞生物学"],
        "神经": ["神经科学"],
        "医学": ["医疗AI"],
        "临床": ["医学研究"],
        # Physics / Math
        "量子": ["量子计算", "物理学"],
        "材料": ["材料科学"],
        "能源": ["新能源"],
        # General science
        "机器人": ["自动化", "智能制造"],
        "自动驾驶": ["无人驾驶", "智能交通"],
    }

    # Truncate topic if too long (B站 tag max 20 chars)
    topic_short = topic[:20] if len(topic) > 20 else topic
    topic_tags = [topic_short]

    # Split compound topics
    for sep in ["与", "和", "及", "+", "&"]:
        if sep in topic:
            parts = [p.strip()[:20] for p in topic.split(sep) if p.strip()]
            topic_tags.extend(parts)

    # For English/mixed topics: don't add full phrase again if already added
    # (avoid duplicate long tags)

    # Match domain keywords
    domain_extra = []
    topic_upper = topic.upper()
    for kw, tags in DOMAIN_TAGS.items():
        if kw.upper() in topic_upper or kw in topic:
            domain_extra.extend(tags)

    # Base discoverability tags
    base_tags = ["AI科研", "学术科普", "论文解读", "前沿研究", "深度解读"]

    # Combine: topic tags -> domain tags -> base tags
    all_tags = topic_tags + domain_extra + base_tags

    # Deduplicate preserving order, max 12, each tag max 20 chars
    seen = set()
    unique = []
    for t in all_tags:
        t = t.strip()[:20]  # Enforce 20-char limit
        if t and t not in seen and len(unique) < 12:
            seen.add(t)
            unique.append(t)
    return ",".join(unique)


# ── Cover extraction ────────────────────────────────────────

def extract_cover(ffmpeg: str, video_path: Path, cover_path: Path) -> bool:
    """Extract first frame from original video as cover image (JPEG).

    Always uses the original (un-subtitled) video to get a clean first frame.
    Tries multiple FFmpeg approaches for robustness.
    """
    # Approach 1: seek to 0 and grab 1 frame
    result = subprocess.run(
        [ffmpeg, "-ss", "0", "-i", str(video_path), "-vframes", "1",
         "-q:v", "2", "-y", str(cover_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode == 0 and cover_path.exists() and cover_path.stat().st_size > 0:
        return True

    # Approach 2: without -ss, raw first frame
    result = subprocess.run(
        [ffmpeg, "-i", str(video_path), "-vframes", "1", "-q:v", "2",
         "-y", str(cover_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.returncode == 0 and cover_path.exists() and cover_path.stat().st_size > 0


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
        biliup_exe = PROJECT_ROOT / "vendor" / "biliup.exe"
        if biliup_exe.exists():
            print(f"  {Y}MISS{X} bilibili cookies (will auto-login before upload)")
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
    """Transcribe audio using faster-whisper with word-level timestamps.

    Runs in a dedicated subprocess to isolate GPU/CPU memory.
    GPU (large-v3 float16) preferred; falls back to CPU (small int8).
    """
    import pickle, tempfile

    # Write a standalone transcription script to a temp file
    # (avoids f-string escaping issues and ensures clean process)
    script_content = '''
import os, sys, pickle
os.environ["MKL_THREADING_LAYER"] = "sequential"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from faster_whisper import WhisperModel

# Detect GPU availability
try:
    import ctranslate2
    _has_cuda = "cuda" in ctranslate2.get_supported_compute_types("cuda")
except Exception:
    _has_cuda = False

_device = "cuda" if _has_cuda else "cpu"
_ctype = "float16" if _has_cuda else "int8"
_model = "large-v3" if _has_cuda else "small"
print(f"  whisper: {_model} on {_device} ({_ctype})", flush=True)

model = WhisperModel(_model, device=_device, compute_type=_ctype)
segments, info = model.transcribe(
    sys.argv[1], language="zh", beam_size=5,
    vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
    word_timestamps=True,
    initial_prompt="以下是普通话的句子，使用简体中文。",
)
seg_list = list(segments)

data = []
for s in seg_list:
    d = {"start": s.start, "end": s.end, "text": s.text}
    if hasattr(s, "words") and s.words:
        d["words"] = [{"start": w.start, "end": w.end, "word": w.word} for w in s.words]
    data.append(d)

with open(sys.argv[2], "wb") as f:
    pickle.dump(data, f)
'''
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w",
                                     encoding="utf-8") as script_f:
        script_f.write(script_content)
        script_path = script_f.name

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
        pkl_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, script_path, str(wav_path), pkl_path],
            capture_output=True, text=True, timeout=600,
            env={**os.environ, "PYTHONIOENCODING": "utf-8",
                 "MKL_THREADING_LAYER": "sequential",
                 "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
        )
        # Print subprocess info line (model/device)
        for line in (result.stdout or "").strip().splitlines():
            if line.strip().startswith("whisper:"):
                print(f"\n  {D}  {line.strip()}{X}", end="", flush=True)

        if Path(pkl_path).exists() and Path(pkl_path).stat().st_size > 0:
            with open(pkl_path, "rb") as f:
                data = pickle.load(f)

            class Seg:
                def __init__(self, d):
                    self.start = d["start"]
                    self.end = d["end"]
                    self.text = d["text"]
                    self.words = None
                    if "words" in d:
                        self.words = [type("W", (), w) for w in d["words"]]
            return [Seg(d) for d in data]

        # Subprocess failed — raise with stderr
        err = (result.stderr or "").strip().split("\n")
        raise RuntimeError(err[-1] if err else "transcription subprocess failed")
    finally:
        Path(script_path).unlink(missing_ok=True)
        Path(pkl_path).unlink(missing_ok=True)


def seconds_to_srt(s: float) -> str:
    """Convert seconds to SRT time format."""
    h, m = int(s) // 3600, int(s) % 3600 // 60
    sec, ms = int(s) % 60, int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


# ── Traditional → Simplified Chinese ─────────────────────────────
# Embedded mapping for common Traditional Chinese chars Whisper outputs.
# No external dependency needed.
_T2S_DICT = {
    '並':'并','來':'来','個':'个','們':'们','價':'价','優':'优',
    '內':'内','兩':'两','創':'创','別':'别','動':'动','區':'区',
    '單':'单','嗎':'吗','問':'问','國':'国','圖':'图','圓':'圆',
    '壓':'压','報':'报','場':'场','處':'处','備':'备','複':'复',
    '夠':'够','學':'学','實':'实','寫':'写','對':'对','導':'导',
    '層':'层','嚴':'严','幹':'干','幾':'几','廠':'厂','廣':'广',
    '從':'从','後':'后','徵':'征','應':'应','態':'态','慣':'惯',
    '戰':'战','據':'据','採':'采','換':'换','斷':'断','時':'时',
    '書':'书','會':'会','構':'构','業':'业','機':'机','條':'条',
    '東':'东','標':'标','檢':'检','歷':'历','歸':'归','決':'决',
    '減':'减','測':'测','準':'准','滿':'满','潛':'潜','為':'为',
    '無':'无','現':'现','環':'环','產':'产','異':'异','當':'当',
    '發':'发','療':'疗','確':'确','種':'种','穩':'稳','節':'节',
    '範':'范','簡':'简','組':'组','結':'结','絕':'绝','統':'统',
    '經':'经','維':'维','線':'线','總':'总','編':'编','練':'练',
    '網':'网','繫':'系','聯':'联','職':'职','與':'与','興':'兴',
    '舉':'举','號':'号','術':'术','規':'规','視':'视','覺':'觉',
    '觀':'观','計':'计','討':'讨','記':'记','設':'设','訴':'诉',
    '診':'诊','評':'评','試':'试','話':'话','該':'该','誌':'志',
    '說':'说','調':'调','談':'谈','論':'论','講':'讲','謹':'谨',
    '證':'证','譜':'谱','議':'议','變':'变','讓':'让','質':'质',
    '軍':'军','軟':'软','較':'较','輪':'轮','輯':'辑','轉':'转',
    '這':'这','過':'过','達':'达','還':'还','進':'进','運':'运',
    '邊':'边','邏':'逻','關':'关','開':'开','間':'间','際':'际',
    '險':'险','難':'难','電':'电','靜':'静','響':'响','頂':'顶',
    '項':'项','預':'预','頭':'头','題':'题','顛':'颠','顧':'顾',
    '顯':'显','風':'风','驗':'验','驚':'惊','體':'体','點':'点',
    '麼':'么','齊':'齐','龍':'龙','傳':'传','億':'亿','佈':'布',
    '勢':'势','獨':'独','獻':'献','礎':'础','籤':'签','級':'级',
    '細':'细','給':'给','腦':'脑','腫':'肿','臨':'临','藥':'药',
    '蓋':'盖','萬':'万','裡':'里','陣':'阵','陰':'阴','雜':'杂',
    '離':'离','雲':'云','須':'须','頻':'频','願':'愿','飛':'飞',
    '驟':'骤','鏈':'链','鍵':'键','長':'长','闢':'辟','極':'极',
    '誤':'误','認':'认','資':'资','訊':'讯','審':'审','屬':'属',
    '幣':'币','帶':'带','彈':'弹','慮':'虑','擇':'择','敵':'敌',
    '曆':'历','棄':'弃','歐':'欧','殘':'残','滯':'滞','獎':'奖',
    '監':'监','競':'竞','紋':'纹','終':'终','績':'绩',
}
_T2S_TABLE = str.maketrans(_T2S_DICT)

def t2s(text: str) -> str:
    """Convert Traditional Chinese text to Simplified Chinese."""
    return text.translate(_T2S_TABLE)


def deduplicate_segments(segments: list) -> list:
    """Remove consecutive duplicate segments from whisper output.

    Whisper (especially with VAD) can produce overlapping segments with
    identical or near-identical text.  This merges them by extending the
    previous segment's end time and dropping the duplicate.

    Returns (deduped_segments, removed_count).
    """
    if not segments:
        return segments, 0

    deduped = [segments[0]]
    removed = 0

    for seg in segments[1:]:
        prev = deduped[-1]
        cur_text = seg.text.strip()
        prev_text = prev.text.strip()

        # Skip empty
        if not cur_text:
            removed += 1
            continue

        # Exact duplicate
        if cur_text == prev_text:
            prev.end = max(prev.end, seg.end)
            # Merge words if both have them
            if hasattr(seg, 'words') and seg.words and hasattr(prev, 'words') and prev.words:
                prev.words.extend(seg.words)
            removed += 1
            continue

        # Near-duplicate: one is a substring of the other (common whisper artifact)
        if len(cur_text) > 4 and len(prev_text) > 4:
            if cur_text in prev_text or prev_text in cur_text:
                # Keep the longer one
                if len(cur_text) > len(prev_text):
                    prev.text = seg.text
                    if hasattr(seg, 'words') and seg.words:
                        prev.words = seg.words
                prev.end = max(prev.end, seg.end)
                removed += 1
                continue

        deduped.append(seg)

    return deduped, removed


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


def ensure_bilibili_login() -> bool:
    """Auto-login to Bilibili if cookies are missing.

    Two strategies (auto-fallback):
    1. Python API: call Bilibili TV QR login directly, display QR in terminal.
       Zero interactive menus — user just scans with Bilibili App.
    2. Bat fallback: write a temp .bat launching biliup.exe login in a new window.
    """
    if COOKIE_FILE.exists():
        print(f"  {G}✓ B站Cookie已缓存，跳过登录{X}", flush=True)
        return True

    print(f"  {Y}! B站Cookie不存在，需要扫码登录{X}", flush=True)
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Strategy 1: Python API QR login (fully non-interactive)
    try:
        return _qr_login_api()
    except Exception as e:
        print(f"  {Y}API登录失败 ({e})，尝试备用方式...{X}")

    # Strategy 2: biliup.exe via .bat (needs user to select menu item)
    return _qr_login_bat()


def _qr_login_api() -> bool:
    """Bilibili TV QR login via Python API — no interactive menu."""
    import hashlib, time, urllib.parse
    import requests as _req

    _APP_KEY = "4409e2ce8ffd12b8"
    _APP_SEC = "59b43e04ad6965f34319062b478f83dd"

    def _sign(params: dict) -> dict:
        qs = urllib.parse.urlencode(params)
        params["sign"] = hashlib.md5(f"{qs}{_APP_SEC}".encode()).hexdigest()
        return params

    session = _req.Session()
    session.trust_env = False  # Bypass proxy for Chinese Bilibili API

    # Step 1 — request QR code (retry up to 3 times)
    r = None
    for attempt in range(3):
        try:
            params = _sign({"appkey": _APP_KEY, "local_id": "0", "ts": int(time.time())})
            resp = session.post(
                "http://passport.bilibili.com/x/passport-tv-login/qrcode/auth_code",
                data=params, timeout=10,
            )
            r = resp.json()
            if r and r.get("code") == 0:
                break
        except Exception as e:
            if attempt < 2:
                print(f"  {D}QR请求失败 (retry {attempt+1}/3): {e}{X}")
                time.sleep(2)
            else:
                raise RuntimeError(f"QR request failed after 3 retries: {e}")
    if not r or r.get("code") != 0:
        raise RuntimeError(f"QR request failed: {r}")

    url = r["data"]["url"]
    auth_code = r["data"]["auth_code"]

    # Step 2 — display QR in terminal
    print(f"\n  {Y}请用B站App扫描下方二维码登录:{X}\n")
    try:
        import qrcode as _qr
        qr = _qr.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except Exception:
        print(f"  {D}（qrcode库不可用，请手动打开链接）{X}")
        print(f"  {D}{url}{X}")

    print(f"\n  {D}等待扫码... (最多120秒){X}", flush=True)

    # Step 3 — poll until scanned or timeout (120 s)
    # B站 TV QR poll response codes:
    #   0     = login success
    #   86038 = QR not scanned yet
    #   86039 = QR scanned, waiting for confirm on phone
    #   86090 = QR scanned (another code variant)
    poll_params = _sign({
        "appkey": _APP_KEY, "auth_code": auth_code,
        "local_id": "0", "ts": int(time.time()),
    })
    scanned_notified = False
    for i in range(120):
        time.sleep(0.5)  # Poll faster for responsive detection
        try:
            resp = session.post(
                "http://passport.bilibili.com/x/passport-tv-login/qrcode/poll",
                data=poll_params, timeout=5,
            ).json()
            code = resp.get("code", -1) if resp else -1

            if code == 0:
                # Login success — save immediately
                COOKIE_FILE.write_text(
                    json.dumps(resp["data"], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"\n  {G}✓ B站登录成功! Cookie已保存{X}", flush=True)
                return True

            if code in (86039, 86090) and not scanned_notified:
                # Scanned but not confirmed yet
                print(f"  {Y}✓ 已扫码! 请在手机上点击「确认登录」...{X}", flush=True)
                scanned_notified = True

        except Exception:
            pass
        # Progress: every 5 seconds (polling at 0.5s, so every 10 iterations)
        if i % 10 == 9 and not scanned_notified:
            print(f"  {D}等待扫码... ({(i+1)//2}s){X}", flush=True)

    print(f"  {R}登录超时 (120s){X}", flush=True)
    return False


# ── WeChat Publishing ───────────────────────────────────────

def ensure_weixin_login() -> bool:
    """Ensure WeChat 视频号 login via Playwright persistent browser context.

    Uses browser_profile directory to persist login across sessions.
    If not logged in, opens browser to channels.weixin.qq.com login page
    and waits for user to scan QR code + confirm on phone.

    Returns:
        True if logged in (or login succeeded), False otherwise.
    """
    profile_dir = WEIXIN_STORAGE_STATE.parent / "browser_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"  {R}ERROR{X} playwright not installed. Run: pip install playwright && playwright install chromium")
        return False

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-proxy-server",
                ],
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                ignore_https_errors=True,
            )
            page = context.pages[0] if context.pages else context.new_page()

            # Navigate to post/create page (will auto-redirect to login if not authenticated)
            create_url = "https://channels.weixin.qq.com/platform/post/create"
            print(f"  {Y}正在打开发布页面...{X}", flush=True)
            try:
                page.goto(create_url, timeout=30000)
            except Exception as e:
                print(f"  {Y}导航异常: {e}，继续...{X}", flush=True)

            import time
            time.sleep(3)
            current_url = page.url
            print(f"  当前URL: {current_url}", flush=True)

            if "post/create" in current_url:
                print(f"  {G}✓ 微信视频号已缓存登录，无需扫码{X}", flush=True)
            elif "login" in current_url.lower():
                print(f"\n  {'='*50}")
                print(f"  {Y}请用微信扫描浏览器中的二维码登录{X}")
                print(f"  扫码后在手机上点击「确认登录」")
                print(f"  登录后会自动跳转到发布页面")
                print(f"  等待登录中... (最多5分钟)")
                print(f"  {'='*50}\n", flush=True)

                max_wait = 300
                start = time.time()
                logged_in = False
                last_print = 0
                while time.time() - start < max_wait:
                    url = page.url
                    # Check if redirected to post/create (indicates successful login)
                    if "post/create" in url:
                        # 3-second re-verify to avoid false positives
                        print(f"  {Y}✓ 检测到页面跳转，验证登录状态...{X}", flush=True)
                        time.sleep(1)
                        url2 = page.url
                        if "post/create" in url2:
                            time.sleep(2)
                            url3 = page.url
                            if "post/create" in url3:
                                logged_in = True
                                print(f"  {G}✓✓ 扫码成功！已自动跳转到发布页面{X}", flush=True)
                                print(f"  {G}当前URL: {url3}{X}", flush=True)
                                break
                            else:
                                print(f"  {D}URL短暂变化后回退，继续等待...{X}", flush=True)
                        else:
                            print(f"  {D}URL短暂变化后回退，继续等待...{X}", flush=True)
                    elapsed = int(time.time() - start)
                    if elapsed >= last_print + 10:
                        print(f"  {D}等待扫码... ({elapsed}s){X}", flush=True)
                        last_print = elapsed
                    time.sleep(0.5)  # Poll every 0.5s for auto-redirect detection

                if not logged_in:
                    print(f"  {R}登录超时 (5分钟){X}", flush=True)
                    context.close()
                    return False

                print(f"  {G}✓ 微信视频号登录成功! 状态已保存{X}", flush=True)
                # Save storage state as backup
                WEIXIN_STORAGE_STATE.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(WEIXIN_STORAGE_STATE))

            context.close()

        return True

    except Exception as e:
        print(f"  {R}登录失败: {e}{X}")
        return False


def ensure_weixin_mp_login() -> bool:
    """Ensure WeChat Official Account (mp.weixin.qq.com) login via Playwright.

    Uses browser_profile directory to persist login across sessions.
    If not logged in, opens browser for QR scan and waits.

    Returns:
        True if logged in (or login succeeded), False otherwise.
    """
    WEIXIN_MP_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"  {R}ERROR{X} playwright not installed")
        return False

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(WEIXIN_MP_PROFILE_DIR),
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-proxy-server",
                ],
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                ignore_https_errors=True,
            )
            page = context.pages[0] if context.pages else context.new_page()

            try:
                page.goto("https://mp.weixin.qq.com/", timeout=30000)
            except Exception:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            import time
            time.sleep(2)

            # mp.weixin.qq.com: logged in → redirects to /cgi-bin/home
            # not logged in → stays on root URL with QR code
            current_url = page.url
            if "cgi-bin" in current_url:
                print(f"  {G}✓ 微信公众号已缓存登录，无需扫码{X}", flush=True)
            else:
                print(f"\n  {'='*50}")
                print(f"  {Y}请用微信扫描浏览器中的二维码登录公众号{X}")
                print(f"  扫码后在手机上点击「确认登录」")
                print(f"  等待登录中... (最多5分钟)")
                print(f"  {'='*50}\n", flush=True)

                max_wait = 300
                start = time.time()
                logged_in = False
                last_print = 0
                while time.time() - start < max_wait:
                    url = page.url
                    if "cgi-bin" in url:
                        # 3-second re-verify to avoid false positives
                        print(f"  {Y}✓ 检测到页面跳转，验证登录状态...{X}", flush=True)
                        time.sleep(1)
                        url2 = page.url
                        if "cgi-bin" in url2:
                            time.sleep(2)
                            url3 = page.url
                            if "cgi-bin" in url3:
                                logged_in = True
                                break
                            else:
                                print(f"  {D}URL短暂变化后回退，继续等待...{X}", flush=True)
                        else:
                            print(f"  {D}URL短暂变化后回退，继续等待...{X}", flush=True)
                    elapsed = int(time.time() - start)
                    if elapsed >= last_print + 10:
                        print(f"  {D}等待扫码... ({elapsed}s){X}", flush=True)
                        last_print = elapsed
                    time.sleep(0.3)

                if not logged_in:
                    print(f"  {R}公众号登录超时 (5分钟){X}", flush=True)
                    context.close()
                    return False

                print(f"  {G}✓ 微信公众号登录成功!{X}", flush=True)

            context.close()

        return True

    except Exception as e:
        print(f"  {R}公众号登录失败: {e}{X}")
        return False


def upload_weixin_channels(video_path: Path, title: str, desc: str, tags: str, cover_path: Path = None) -> dict:
    """Upload video to WeChat 视频号 via Playwright automation.

    Uses persistent browser context with wujie micro-frontend iframe handling.
    Handles login (QR scan) inline to avoid asyncio event loop conflicts from
    multiple sync_playwright() contexts.

    Args:
        video_path: Path to video file
        title: Video title (short title limited to 16 chars for 视频号)
        desc: Video description
        tags: Comma-separated tags (appended as #tag to description)
        cover_path: Optional cover image (not used - 视频号 auto-generates cover)

    Returns:
        {"ok": bool, "error": str}
    """
    import time

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "error": "playwright not installed"}

    profile_dir = WEIXIN_STORAGE_STATE.parent / "browser_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Short title: 6-16 chars (视频号 requires minimum 6)
    title_short = title[:16] if len(title) > 16 else title
    if len(title_short) < 6:
        title_short = title_short + "—视频解读"
        title_short = title_short[:16]

    # Build description with tags
    tag_suffix = ""
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        tag_suffix = " " + " ".join(f"#{t}" for t in tag_list[:5])
    full_desc = desc + tag_suffix

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-proxy-server",
                ],
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                ignore_https_errors=True,
            )
            page = context.pages[0] if context.pages else context.new_page()

            # Navigate to upload page (will redirect to login if not authenticated)
            try:
                page.goto("https://channels.weixin.qq.com/platform/post/create", timeout=30000)
            except Exception:
                pass

            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(2)

            # Inline login check: if redirected to login page, wait for QR scan
            if "login" not in page.url.lower():
                print(f"  {G}✓ 微信视频号已缓存登录，直接上传{X}", flush=True)
            else:
                print(f"\n  {'='*50}")
                print(f"  {Y}请用微信扫描浏览器中的二维码登录{X}")
                print(f"  扫码后在手机上点击「确认登录」")
                print(f"  等待登录中... (最多5分钟)")
                print(f"  {'='*50}\n", flush=True)

                max_wait = 300
                start = time.time()
                logged_in = False
                last_print = 0
                while time.time() - start < max_wait:
                    url = page.url
                    if "login" not in url.lower():
                        # 3-second re-verify to avoid false positives
                        print(f"  {Y}✓ 检测到页面跳转，验证登录状态...{X}", flush=True)
                        time.sleep(1)
                        url2 = page.url
                        if "login" not in url2.lower():
                            time.sleep(2)
                            url3 = page.url
                            if "login" not in url3.lower():
                                logged_in = True
                                print(f"  {G}✓✓ 扫码成功！登录状态已确认{X}", flush=True)
                                print(f"  {G}登录后URL: {url3}{X}", flush=True)
                                break
                            else:
                                print(f"  {D}URL短暂变化后回退，继续等待...{X}", flush=True)
                        else:
                            print(f"  {D}URL短暂变化后回退，继续等待...{X}", flush=True)
                    elapsed = int(time.time() - start)
                    if elapsed >= last_print + 10:
                        print(f"  {D}等待扫码... ({elapsed}s){X}", flush=True)
                        last_print = elapsed
                    time.sleep(0.3)  # Fast polling for responsive detection

                if not logged_in:
                    print(f"  {R}登录超时 (5分钟){X}", flush=True)
                    context.close()
                    return {"ok": False, "error": "Login timeout"}

                print(f"  {G}✓ 微信视频号登录成功! 立即继续上传...{X}", flush=True)
                WEIXIN_STORAGE_STATE.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(WEIXIN_STORAGE_STATE))

                # Navigate to upload page after login
                try:
                    page.goto("https://channels.weixin.qq.com/platform/post/create", timeout=30000)
                except Exception:
                    pass
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                time.sleep(2)

            # Find the wujie iframe (form is rendered inside it)
            # The wujie micro-frontend renders the upload form in an iframe
            # Wait up to 30s for the iframe to appear and load
            upload_frame = None
            for attempt in range(15):
                for frame in page.frames:
                    if "/micro/" in frame.url:
                        upload_frame = frame
                        break
                if upload_frame:
                    break
                time.sleep(2)

            # Wujie may expose elements to main page instead of iframe
            if not upload_frame:
                print(f"    未找到iframe，使用主页面")
                upload_frame = page

            # Wait for file input to appear inside iframe
            try:
                upload_frame.wait_for_selector('input[type="file"]', timeout=30000, state="attached")
            except Exception:
                pass
            time.sleep(2)

            # Step 1: Upload video via file chooser
            # The file input is hidden, so we trigger it and intercept the file chooser
            # File chooser listener must be on page, not frame

            with page.expect_file_chooser(timeout=10000) as fc_info:
                # Trigger the file input click via JavaScript in the iframe
                upload_frame.evaluate('document.querySelector("input[type=\\"file\\"]").click()')

            file_chooser = fc_info.value
            file_chooser.set_files(str(video_path))
            print(f"    视频已选择，等待上传...")

            # Step 2: Wait for upload to complete
            # Check if video preview appears (indicates upload finished)
            max_upload_wait = 300  # 5 min max for upload (large videos need more time)
            start = time.time()
            upload_done = False
            while time.time() - start < max_upload_wait:
                try:
                    # Multiple indicators of upload completion:
                    # 1. Video element appears
                    # 2. Delete button appears (删除)
                    # 3. Short title input becomes enabled
                    # 4. Progress bar disappears or reaches 100%
                    video_elem = upload_frame.locator('video')
                    delete_btn = upload_frame.locator('button:has-text("删除")')
                    short_title_input = upload_frame.locator('input[placeholder*="概括视频主要内容"]')

                    # Also check main page if iframe is empty
                    video_elem_main = page.locator('video')
                    delete_btn_main = page.locator('button:has-text("删除")')

                    if video_elem.count() > 0 or delete_btn.count() > 0:
                        upload_done = True
                        print(f"    检测到上传完成标志 (iframe)")
                        break
                    if video_elem_main.count() > 0 or delete_btn_main.count() > 0:
                        upload_done = True
                        print(f"    检测到上传完成标志 (主页面)")
                        break
                    short_title_input = upload_frame.locator('input[placeholder*="概括视频主要内容"]')

                    if video_elem.count() > 0 or delete_btn.count() > 0:
                        upload_done = True
                        print(f"    检测到上传完成标志")
                        break

                    # Also check if short title input is enabled (not disabled)
                    if short_title_input.count() > 0:
                        is_disabled = short_title_input.first.is_disabled()
                        if not is_disabled:
                            upload_done = True
                            print(f"    短标题输入框已启用，上传完成")
                            break

                except Exception:
                    pass
                elapsed = int(time.time() - start)
                if elapsed % 10 == 0 and elapsed > 0:
                    print(f"    上传中... ({elapsed}s)")
                time.sleep(2)

            if not upload_done:
                print(f"    {Y}未检测到视频预览，但继续尝试填写表单...{X}")

            print(f"    上传完成，填写信息...")
            time.sleep(3)

            # Wujie iframe may be empty after upload, check and fallback to main page
            short_title_test = upload_frame.locator('input[placeholder*="概括"]')
            if short_title_test.count() == 0 and hasattr(upload_frame, 'url'):
                upload_frame = page

            # Step 3: Fill in short title (右侧表单，必填)
            try:
                # 短标题在右侧，placeholder包含"概括视频主要内容"
                short_title_input = upload_frame.locator('input[placeholder*="概括视频主要内容"]')
                count = short_title_input.count()
                print(f"    短标题输入框: 找到 {count} 个")
                if count > 0:
                    short_title_input.first.click()
                    time.sleep(0.3)
                    short_title_input.first.fill(title_short)
                    print(f"    ✓ 短标题: {title_short}")
                else:
                    print(f"    ✗ 短标题输入框未找到")
            except Exception as e:
                print(f"    ✗ 短标题填写失败: {e}")

            # Step 4: Fill in description (左侧视频下方，可选)
            # Description is a contenteditable div with data-placeholder="添加描述"
            desc_filled = False
            try:
                # The description field is: <div contenteditable="" data-placeholder="添加描述" class="input-editor"></div>
                desc_elem = upload_frame.locator('div.input-editor[contenteditable][data-placeholder="添加描述"]')
                count = desc_elem.count()
                print(f"    描述字段: 找到 {count} 个")

                if count > 0 and desc_elem.first.is_visible():
                    desc_elem.first.click()
                    time.sleep(0.3)
                    # For contenteditable, use type() instead of fill()
                    desc_elem.first.evaluate(f'el => el.innerText = {repr(full_desc)}')
                    desc_filled = True
                    print(f"    ✓ 描述已填写")
                else:
                    print(f"    ⚠ 描述字段不可见或未找到")

            except Exception as e:
                print(f"    ⚠ 描述填写异常: {e}")

            time.sleep(2)

            # Step 5: Wait for publish button to become enabled (video processing)
            print(f"    检查发表按钮状态...")
            try:
                publish_btn = upload_frame.locator('button:has-text("发表")')
                btn_count = publish_btn.count()
                print(f"    发表按钮: 找到 {btn_count} 个")

                if btn_count > 0:
                    # Debug: print button details
                    btn_cls = publish_btn.first.get_attribute("class") or ""
                    btn_disabled = publish_btn.first.get_attribute("disabled")
                    print(f"    [DEBUG] 按钮class: {btn_cls}")
                    print(f"    [DEBUG] 按钮disabled属性: {btn_disabled}")

                    # Check for error/warning messages that might explain why button is disabled
                    error_msgs = upload_frame.locator('.weui-desktop-form__tips--error, .tips-error, .error-tip')
                    if error_msgs.count() > 0:
                        for ei in range(error_msgs.count()):
                            print(f"    [DEBUG] 错误提示: {error_msgs.nth(ei).text_content()}")

                    # Poll until publish button is enabled (video may still be processing)
                    max_wait_publish = 180  # wait up to 3 minutes for video processing
                    is_disabled = True
                    for wait_i in range(max_wait_publish // 5):
                        cls = publish_btn.first.get_attribute("class") or ""
                        html_disabled = publish_btn.first.get_attribute("disabled")
                        is_disabled = "disabled" in cls or html_disabled is not None
                        if not is_disabled:
                            break
                        if wait_i == 0:
                            print(f"    {Y}发表按钮暂时禁用，等待视频处理...{X}")
                        print(f"\r    等待发表按钮可用... ({(wait_i+1)*5}s/{max_wait_publish}s)", end="", flush=True)
                        time.sleep(5)
                    if not is_disabled:
                        print(f"\n    发表按钮状态: enabled")
                    else:
                        print(f"\n    发表按钮状态: disabled (超时)")
                        # Debug: take screenshot for diagnosis
                        try:
                            ss_path = str(Path("output_subtitled") / "debug_weixin_disabled.png")
                            page.screenshot(path=ss_path, full_page=True)
                            print(f"    [DEBUG] 截图已保存: {ss_path}")
                        except Exception as e:
                            print(f"    [DEBUG] 截图失败: {e}")
                        # Debug: check for processing progress
                        try:
                            progress = page.locator('.progress, .upload-progress, [class*="progress"]')
                            if progress.count() > 0:
                                for pi in range(min(progress.count(), 3)):
                                    print(f"    [DEBUG] 进度元素: {progress.nth(pi).get_attribute('class')} = {progress.nth(pi).text_content()[:100]}")
                            # Check video element
                            videos = page.locator('video')
                            print(f"    [DEBUG] 页面video元素: {videos.count()} 个")
                            # Check if there are any error/warning messages on the whole page
                            warns = page.locator('.weui-desktop-form__tips--warn, .weui-desktop-dialog__bd')
                            if warns.count() > 0:
                                for wi in range(min(warns.count(), 3)):
                                    txt = warns.nth(wi).text_content()[:100] if warns.nth(wi).is_visible() else "(hidden)"
                                    print(f"    [DEBUG] 警告/对话: {txt}")
                        except Exception:
                            pass

                    if is_disabled:
                        # 按钮仍被禁用，尝试保存草稿
                        print(f"    {Y}发表按钮仍被禁用，尝试保存草稿...{X}")
                        draft_btn = upload_frame.locator('button:has-text("保存草稿")')
                        if draft_btn.count() > 0:
                            draft_cls = draft_btn.first.get_attribute("class") or ""
                            if "disabled" not in draft_cls:
                                draft_btn.first.click()
                                print(f"    ✓ 已保存为草稿")
                                time.sleep(3)
                                print(f"    浏览器保持打开 10 秒...")
                                time.sleep(10)
                                context.close()
                                return {"ok": True, "note": "saved as draft (publish button disabled, may need more required fields)"}
                        print(f"    {R}草稿按钮也不可用{X}")
                        time.sleep(10)
                        context.close()
                        return {"ok": False, "error": "Both publish and draft buttons disabled"}

                    # 按钮可用，点击发表
                    print(f"    点击发表...")
                    publish_btn.first.click()
                    time.sleep(3)

                else:
                    context.close()
                    return {"ok": False, "error": "Publish button not found"}

            except Exception as e:
                context.close()
                return {"ok": False, "error": f"Failed to interact with publish button: {e}"}
            time.sleep(3)

            # Step 7: Handle post-publish dialogs
            # May show "管理员本人验证" QR code or "以下事项需注意" dialog
            try:
                # Check for verification dialog
                verify_dialog = upload_frame.locator('div.mobile-guide-qr-code')
                if verify_dialog.count() > 0 and verify_dialog.is_visible():
                    print(f"\n  {'='*50}")
                    print(f"  需要管理员扫码验证，请用微信扫描弹窗中的二维码")
                    print(f"  等待验证... (最多2分钟)")
                    print(f"  {'='*50}\n")
                    # Wait for dialog to disappear
                    max_verify = 120
                    v_start = time.time()
                    while time.time() - v_start < max_verify:
                        if verify_dialog.count() == 0 or not verify_dialog.is_visible():
                            break
                        time.sleep(2)
            except Exception:
                pass

            try:
                # Check for "以下事项需注意" dialog - click 我知道了
                notice_btn = upload_frame.locator('div.post-check-dialog button:has-text("我知道了")')
                if notice_btn.count() > 0 and notice_btn.first.is_visible():
                    notice_btn.first.click()
                    time.sleep(2)
            except Exception:
                pass

            # Wait for success indication
            time.sleep(5)

            print(f"    浏览器保持打开 10 秒...")
            time.sleep(10)

            context.close()
            return {"ok": True}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def upload_weixin_article(video_path: Path, title: str, desc: str, tags: str, cover_path: Path, srt_path: Path, bilibili_result: str) -> dict:
    """Publish article to WeChat Official Account.

    Strategy:
    1. Try WeChat API (if WECHAT_APPID/WECHAT_APPSECRET configured in .env)
    2. Fall back to Playwright browser automation (QR scan login)
    """
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    appid = os.getenv("WECHAT_APPID", "")
    appsecret = os.getenv("WECHAT_APPSECRET", "")
    has_api_creds = appid and appsecret and "your_" not in appid and "your_" not in appsecret

    # Generate article HTML content
    html_content = generate_article_html(title, desc, srt_path, bilibili_result)

    if has_api_creds:
        # Strategy 1: WeChat API
        ret = _upload_weixin_article_api(title, desc, html_content, cover_path, appid, appsecret)
        if ret["ok"]:
            return ret
        print(f"      {Y}API方式失败 ({ret['error']})，尝试浏览器方式...{X}", flush=True)

    # Strategy 2: Playwright subprocess
    return _run_weixin_mp_subprocess(title, html_content, str(cover_path) if cover_path else None)


def generate_article_html(title: str, desc: str, srt_path: Path, bilibili_result: str) -> str:
    """Generate HTML content for WeChat article from SRT transcript.

    Args:
        title: Article title
        desc: Description
        srt_path: Path to SRT file
        bilibili_result: Bilibili result (e.g., "ok:BV1xx...")

    Returns:
        HTML string for article content
    """
    # Extract BV number if available
    bv_link = ""
    if bilibili_result.startswith("ok:BV"):
        bvid = bilibili_result.split(":", 1)[1]
        bv_link = f'<p><strong>B站视频:</strong> <a href="https://www.bilibili.com/video/{bvid}">https://www.bilibili.com/video/{bvid}</a></p>'

    # Read SRT and convert to plain text
    transcript = ""
    if srt_path.exists():
        srt_text = srt_path.read_text(encoding="utf-8")
        # Remove SRT formatting (index, timestamps)
        lines = []
        for line in srt_text.split("\n"):
            line = line.strip()
            # Skip index lines (pure numbers) and timestamp lines (contains -->)
            if line and not line.isdigit() and "-->" not in line:
                lines.append(line)
        transcript = "\n".join(lines)

    html = f"""
<h2>{title}</h2>
<p>{desc}</p>
{bv_link}
<h3>视频文字稿</h3>
<p style="white-space: pre-wrap;">{transcript}</p>
"""
    return html


def _upload_weixin_article_api(title: str, desc: str, html_content: str, cover_path: Path, appid: str, appsecret: str) -> dict:
    """Upload article via WeChat Official Account API (needs APPID/APPSECRET)."""
    try:
        import requests

        token_resp = requests.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={"grant_type": "client_credential", "appid": appid, "secret": appsecret},
            timeout=10,
        ).json()

        if "access_token" not in token_resp:
            return {"ok": False, "error": f"Token failed: {token_resp.get('errmsg', 'unknown')}"}

        access_token = token_resp["access_token"]

        thumb_media_id = None
        if cover_path and Path(cover_path).exists():
            with open(cover_path, "rb") as f:
                files = {"media": (Path(cover_path).name, f, "image/jpeg")}
                upload_resp = requests.post(
                    f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image",
                    files=files, timeout=30,
                ).json()
                thumb_media_id = upload_resp.get("media_id")

        draft_data = {
            "articles": [{
                "title": title,
                "author": "AI科研助手",
                "digest": desc[:120],
                "content": html_content,
                "content_source_url": "",
                "thumb_media_id": thumb_media_id or "",
                "need_open_comment": 0,
                "only_fans_can_comment": 0,
            }]
        }

        draft_resp = requests.post(
            f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}",
            json=draft_data, timeout=30,
        ).json()

        if "media_id" not in draft_resp:
            return {"ok": False, "error": f"Draft failed: {draft_resp.get('errmsg', 'unknown')}"}

        media_id = draft_resp["media_id"]

        publish_resp = requests.post(
            f"https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token={access_token}",
            json={"media_id": media_id}, timeout=30,
        ).json()

        if publish_resp.get("errcode") != 0:
            return {"ok": False, "error": f"Publish failed: {publish_resp.get('errmsg', 'unknown')}"}

        return {"ok": True, "publish_id": publish_resp.get("publish_id", "")}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def _run_weixin_mp_subprocess(title: str, content_html: str, cover_path: str = None) -> dict:
    """Run WeChat Official Account article upload in subprocess via Playwright."""
    import tempfile

    result_file = Path(tempfile.mktemp(suffix=".json", prefix="weixin_mp_result_"))
    worker_script = PROJECT_ROOT / "_weixin_mp_upload_worker.py"

    args_json = json.dumps({
        "title": title,
        "content_html": content_html,
        "cover_path": cover_path,
    }, ensure_ascii=False)

    try:
        proc = subprocess.run(
            [sys.executable, "-u", str(worker_script), args_json, str(result_file)],
            timeout=600,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        )
        if result_file.exists():
            ret = json.loads(result_file.read_text(encoding="utf-8"))
            result_file.unlink(missing_ok=True)
            return ret
        elif proc.returncode != 0:
            return {"ok": False, "error": f"Subprocess exit code {proc.returncode}"}
        else:
            return {"ok": False, "error": "No result from subprocess"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Upload timeout (10min)"}
    except Exception as e:
        return {"ok": False, "error": f"Subprocess error: {e}"}
    finally:
        result_file.unlink(missing_ok=True)


def _qr_login_bat() -> bool:
    """Fallback: launch biliup.exe login via temp .bat (user selects menu)."""
    import time

    biliup_exe = PROJECT_ROOT / "vendor" / "biliup.exe"
    if not biliup_exe.exists():
        print(f"  {R}MISS{X} vendor/biliup.exe")
        return False

    print(f"  {Y}正在弹出登录窗口...{X}")
    print(f"  {D}请在弹出的终端中选择「扫码登录」并用B站App扫码{X}")

    bat_content = (
        f'@echo off\n'
        f'echo ========================================\n'
        f'echo    B站登录 - 请选择「扫码登录」\n'
        f'echo ========================================\n'
        f'echo.\n'
        f'"{biliup_exe}" -u "{COOKIE_FILE}" login\n'
        f'echo.\n'
        f'echo 登录完成，此窗口可关闭。\n'
        f'pause\n'
    )
    bat_path = PROJECT_ROOT / "vendor" / "_bilibili_login.bat"
    bat_path.write_text(bat_content, encoding="utf-8")

    try:
        if sys.platform == "win32":
            subprocess.Popen(
                f'start "B站登录" cmd /c "{bat_path}"',
                shell=True, cwd=str(PROJECT_ROOT / "vendor"),
            )
        else:
            login_cmd = f'"{biliup_exe}" -u "{COOKIE_FILE}" login'
            for term_cmd in [
                ["gnome-terminal", "--", "bash", "-c", login_cmd],
                ["xterm", "-e", login_cmd],
            ]:
                try:
                    subprocess.Popen(term_cmd, cwd=str(PROJECT_ROOT / "vendor"))
                    break
                except FileNotFoundError:
                    continue

        for i in range(120):
            if COOKIE_FILE.exists() and COOKIE_FILE.stat().st_size > 10:
                print(f"  {G}B站登录成功!{X}")
                return True
            time.sleep(1)
            if i % 10 == 9:
                print(f"  {D}等待扫码... ({i+1}s){X}")

        print(f"  {R}登录超时 (120s){X}")
        return False
    finally:
        bat_path.unlink(missing_ok=True)


def upload_bilibili(video_path, title: str, desc: str, tags: str,
                    cover_path=None) -> dict:
    """Upload video to Bilibili with title, desc, tags, and optional cover."""
    video_path = Path(video_path) if not isinstance(video_path, Path) else video_path
    if cover_path:
        cover_path = Path(cover_path) if not isinstance(cover_path, Path) else cover_path
    if not COOKIE_FILE.exists():
        if not ensure_bilibili_login():
            return {"ok": False, "bvid": "", "error": "B站未登录"}

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


def _run_weixin_channels_subprocess(video_path: Path, title: str, desc: str, tags: str, cover_path: Path = None) -> dict:
    """Run WeChat Channels upload in a subprocess using async Playwright API.

    The main process's event loop state conflicts with Playwright's sync API.
    This launches _weixin_upload_worker.py which uses the async API with asyncio.run()
    in a clean subprocess, avoiding all event loop conflicts.
    """
    import tempfile

    result_file = Path(tempfile.mktemp(suffix=".json", prefix="weixin_result_"))
    worker_script = PROJECT_ROOT / "src/workers/weixin_upload_worker.py"

    args_json = json.dumps({
        "video_path": str(video_path),
        "title": title,
        "desc": desc,
        "tags": tags,
        "cover_path": str(cover_path) if cover_path else None,
    }, ensure_ascii=False)

    try:
        proc = subprocess.run(
            [sys.executable, "-u", str(worker_script), args_json, str(result_file)],
            timeout=600,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        )
        if result_file.exists():
            ret = json.loads(result_file.read_text(encoding="utf-8"))
            result_file.unlink(missing_ok=True)
            return ret
        elif proc.returncode != 0:
            return {"ok": False, "error": f"Subprocess exit code {proc.returncode}"}
        else:
            return {"ok": False, "error": "No result from subprocess"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Upload timeout (10min)"}
    except Exception as e:
        return {"ok": False, "error": f"Subprocess error: {e}"}
    finally:
        result_file.unlink(missing_ok=True)


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
        # Deduplicate consecutive identical/near-identical segments
        segments, dup_count = deduplicate_segments(segments)
        # Convert Traditional Chinese to Simplified Chinese
        for seg in segments:
            seg.text = t2s(seg.text)
            if seg.words:
                for w in seg.words:
                    w.word = t2s(w.word)
        dup_info = f", {dup_count} duplicates removed" if dup_count else ""
        ok(f"({len(segments)} segments, {duration_str}{dup_info})")
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
            elif plat == "weixin_channels":
                # Run in subprocess to avoid asyncio event loop conflicts
                # (Playwright sync_api uses asyncio internally, conflicts with
                # the event loop left by faster-whisper/other imports)
                ret = _run_weixin_channels_subprocess(output_mp4, title, desc, tags, cover_path)
                if ret["ok"]:
                    print(f"      WeChat视频号  {G}ok{X}")
                    result["uploads"]["weixin_channels"] = "ok"
                else:
                    print(f"      WeChat视频号  {R}FAIL{X}  {ret['error']}")
                    result["uploads"]["weixin_channels"] = f"FAIL:{ret['error']}"
            elif plat == "weixin_article":
                ret = upload_weixin_article(output_mp4, title, desc, tags, cover_path, srt_path, result.get("uploads", {}).get("bilibili", ""))
                if ret["ok"]:
                    print(f"      WeChat公众号  {G}ok{X}  {ret['publish_id']}")
                    result["uploads"]["weixin_article"] = f"ok:{ret['publish_id']}"
                else:
                    print(f"      WeChat公众号  {R}FAIL{X}  {ret['error']}")
                    result["uploads"]["weixin_article"] = f"FAIL:{ret['error']}"
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


def ensure_all_logins(platforms: list[str]) -> dict:
    """Pre-authenticate all platforms concurrently before uploading.

    Phase 1: Quick cache/credential check for all platforms
    Phase 2: Start all needed QR logins at once (B站 terminal + WeChat browsers)
    Phase 3: Wait for all to complete and report results

    Returns:
        dict mapping platform -> bool (True=ready, False=failed)
    """
    import threading

    results = {}
    need_login = []

    # ── Phase 1: Cache check ──
    print(f"\n  {B}[登录预检]{X} 检查各平台认证状态")

    if "bilibili" in platforms:
        if COOKIE_FILE.exists():
            print(f"    B站:       {G}✓ Cookie已缓存{X}")
            results["bilibili"] = True
        else:
            print(f"    B站:       {Y}! 需要扫码登录{X}")
            need_login.append("bilibili")

    if "weixin_channels" in platforms:
        profile_dir = WEIXIN_STORAGE_STATE.parent / "browser_profile"
        has_profile = profile_dir.exists() and any(profile_dir.iterdir()) if profile_dir.exists() else False
        if has_profile:
            print(f"    微信视频号: {D}有缓存，需浏览器验证{X}")
        else:
            print(f"    微信视频号: {Y}! 需要扫码登录{X}")
        need_login.append("weixin_channels")

    if "weixin_article" in platforms:
        has_profile = WEIXIN_MP_PROFILE_DIR.exists() and any(WEIXIN_MP_PROFILE_DIR.iterdir()) if WEIXIN_MP_PROFILE_DIR.exists() else False
        if has_profile:
            print(f"    微信公众号: {D}有缓存，需浏览器验证{X}")
        else:
            print(f"    微信公众号: {Y}! 需要扫码登录{X}")
        need_login.append("weixin_article")

    if not need_login:
        print(f"\n  {G}✓ 所有平台已就绪!{X}\n")
        return results

    # ── Phase 2: Concurrent login ──
    has_bilibili = "bilibili" in need_login
    weixin_logins = [p for p in need_login if p != "bilibili"]

    if len(need_login) > 1:
        print(f"\n  {Y}▶ 同时启动 {len(need_login)} 个平台登录 — 请依次完成扫码{X}")
        if has_bilibili:
            print(f"    B站:   用B站App扫描终端二维码")
        if "weixin_channels" in need_login:
            print(f"    视频号: 用微信扫描浏览器二维码")
        if "weixin_article" in need_login:
            print(f"    公众号: 用微信扫描浏览器二维码")
        print()

    threads = []

    # Start WeChat logins in background threads (open browser windows)
    if "weixin_channels" in need_login:
        def _login_weixin_channels():
            results["weixin_channels"] = ensure_weixin_login()
        t = threading.Thread(target=_login_weixin_channels, daemon=True)
        threads.append(t)
        t.start()

    if "weixin_article" in need_login:
        def _login_weixin_mp():
            results["weixin_article"] = ensure_weixin_mp_login()
        t = threading.Thread(target=_login_weixin_mp, daemon=True)
        threads.append(t)
        t.start()

    # B站 login in main thread (terminal QR code — no thread conflicts)
    if has_bilibili:
        results["bilibili"] = ensure_bilibili_login()

    # Wait for all background threads
    for t in threads:
        t.join(timeout=360)

    # ── Phase 3: Summary ──
    print(f"\n  {B}[登录结果]{X}")
    failed = []
    for plat in platforms:
        status = results.get(plat)
        if status is True:
            print(f"    {plat:18} {G}✓ 就绪{X}")
        elif status is False:
            print(f"    {plat:18} {R}✗ 失败{X}")
            failed.append(plat)
        else:
            print(f"    {plat:18} {Y}? 超时{X}")
            failed.append(plat)

    if not failed:
        print(f"\n  {G}✓ 所有平台登录完成! 自动开始处理...{X}\n")
    else:
        print(f"\n  {Y}! 以下平台将跳过: {', '.join(failed)}{X}\n")

    return results


def main():
    parser = argparse.ArgumentParser(description="Video post-production: subtitle + upload")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input video directory")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output base directory")
    parser.add_argument("--platforms", nargs="+", default=["bilibili", "weixin_channels"],
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

    # Pre-authenticate all platforms (parallel QR scan)
    if not args.skip_upload:
        login_results = ensure_all_logins(args.platforms)
        # Filter out platforms that failed login
        active_platforms = [p for p in args.platforms if login_results.get(p) is not False]
        if not active_platforms:
            print(f"{R}所有平台登录失败，无法上传。{X}")
            return
        args.platforms = active_platforms

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
