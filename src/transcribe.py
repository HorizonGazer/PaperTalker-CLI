#!/usr/bin/env python3
"""
transcribe.py - Standalone audio transcription script
=====================================================
Extracts audio from video, transcribes with faster-whisper, generates SRT.

Usage:
    python src/transcribe.py video.mp4                    # Output: video.srt
    python src/transcribe.py video.mp4 -o output.srt      # Custom output
    python src/transcribe.py video.mp4 --model large-v3   # Custom model
    python src/transcribe.py video.mp4 --device cuda      # Force GPU

Requires:
    pip install imageio-ffmpeg faster-whisper
"""

# MKL env vars must be set before any CTranslate2/faster_whisper import
import os as _os
_os.environ.setdefault("MKL_THREADING_LAYER", "sequential")
_os.environ.setdefault("OMP_NUM_THREADS", "1")
_os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

# Windows GBK fix
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

# Subtitle display limits
MAX_CHARS_PER_LINE = 18  # Max Chinese chars per subtitle line
MAX_DURATION_PER_SUB = 6.0  # Max seconds a single subtitle can display

G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; D = "\033[2m"; X = "\033[0m"


def get_ffmpeg():
    """Get FFmpeg path from imageio-ffmpeg."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        print(f"{R}ERROR:{X} imageio-ffmpeg not installed. Run: pip install imageio-ffmpeg")
        sys.exit(1)


def extract_audio(ffmpeg: str, video_path: Path, wav_path: Path) -> bool:
    """Extract audio from video to 16kHz mono WAV."""
    result = subprocess.run(
        [ffmpeg, "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", str(wav_path), "-y"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.returncode == 0


def transcribe(wav_path: Path, model: str = None, device: str = None) -> list:
    """Transcribe audio using faster-whisper with word-level timestamps.

    Runs in a dedicated subprocess to isolate GPU/CPU memory.
    Auto-detects GPU availability if device not specified.

    Args:
        wav_path: Path to 16kHz mono WAV file
        model: Model name (large-v3, medium, small, etc.) or None for auto
        device: Device (cuda, cpu) or None for auto-detect

    Returns:
        List of segment objects with .start, .end, .text, .words attributes
    """
    import pickle, tempfile

    # Write a standalone transcription script to a temp file
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

# Use provided args or auto-detect
_device = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "auto" else ("cuda" if _has_cuda else "cpu")
_model = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "auto" else ("large-v3" if _has_cuda else "small")
_ctype = "float16" if _device == "cuda" else "int8"

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
        device_arg = device if device else "auto"
        model_arg = model if model else "auto"

        result = subprocess.run(
            [sys.executable, script_path, str(wav_path), pkl_path, device_arg, model_arg],
            capture_output=True, text=True, timeout=600,
            env={**_os.environ, "PYTHONIOENCODING": "utf-8",
                 "MKL_THREADING_LAYER": "sequential",
                 "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
        )
        # Print subprocess info line (model/device)
        for line in (result.stdout or "").strip().splitlines():
            if line.strip().startswith("whisper:"):
                print(f"\n{D}{line.strip()}{X}", flush=True)

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
        err = (result.stderr or "").strip().split("\n")[-10:]  # Last 10 lines
        raise RuntimeError(f"Transcription failed:\n" + "\n".join(err))

    finally:
        try:
            Path(script_path).unlink()
            Path(pkl_path).unlink()
        except Exception:
            pass


def format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def split_long_text(text: str, max_chars: int = MAX_CHARS_PER_LINE) -> list[str]:
    """Split long text into multiple lines, respecting punctuation."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    # Try to split at punctuation
    for sep in ["，", "。", "；", "、", "！", "？", ",", ".", ";", " "]:
        if sep in text:
            parts = text.split(sep)
            lines = []
            current = ""
            for i, part in enumerate(parts):
                part_with_sep = part + (sep if i < len(parts) - 1 else "")
                if len(current) + len(part_with_sep) <= max_chars:
                    current += part_with_sep
                else:
                    if current:
                        lines.append(current)
                    current = part_with_sep
            if current:
                lines.append(current)
            if all(len(line) <= max_chars for line in lines):
                return lines

    # Fallback: hard split
    return [text[i:i+max_chars] for i in range(0, len(text), max_chars)]


def generate_srt(segments: list, output_path: Path) -> int:
    """Generate SRT subtitle file from transcription segments.

    Returns:
        Number of subtitle entries generated
    """
    srt_lines = []
    sub_index = 1

    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue

        # Split long segments by duration
        seg_duration = seg.end - seg.start
        if seg_duration > MAX_DURATION_PER_SUB and seg.words and len(seg.words) > 1:
            # Split by words to respect duration limit
            chunk_words = []
            chunk_start = seg.words[0].start

            for i, word in enumerate(seg.words):
                chunk_words.append(word.word)
                is_last = i == len(seg.words) - 1
                chunk_duration = word.end - chunk_start

                if chunk_duration >= MAX_DURATION_PER_SUB or is_last:
                    chunk_text = "".join(chunk_words).strip()
                    if chunk_text:
                        lines = split_long_text(chunk_text)
                        srt_lines.append(f"{sub_index}")
                        srt_lines.append(f"{format_timestamp(chunk_start)} --> {format_timestamp(word.end)}")
                        srt_lines.append("\n".join(lines))
                        srt_lines.append("")
                        sub_index += 1

                    chunk_words = []
                    if not is_last:
                        chunk_start = seg.words[i + 1].start
        else:
            # Normal segment
            lines = split_long_text(text)
            srt_lines.append(f"{sub_index}")
            srt_lines.append(f"{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}")
            srt_lines.append("\n".join(lines))
            srt_lines.append("")
            sub_index += 1

    output_path.write_text("\n".join(srt_lines), encoding="utf-8")
    return sub_index - 1


def main():
    parser = argparse.ArgumentParser(description="Transcribe video to SRT subtitles")
    parser.add_argument("video", type=Path, help="Input video file")
    parser.add_argument("-o", "--output", type=Path, help="Output SRT file (default: video.srt)")
    parser.add_argument("--model", help="Whisper model (large-v3, medium, small, etc.)")
    parser.add_argument("--device", choices=["cuda", "cpu"], help="Device (auto-detect if not specified)")
    parser.add_argument("--keep-wav", action="store_true", help="Keep extracted WAV file")

    args = parser.parse_args()

    if not args.video.exists():
        print(f"{R}ERROR:{X} Video file not found: {args.video}")
        sys.exit(1)

    output_srt = args.output or args.video.with_suffix(".srt")
    wav_path = args.video.with_suffix(".wav")

    print(f"{C}Transcribing:{X} {args.video.name}")
    print(f"{C}Output SRT:{X} {output_srt}")

    # Step 1: Extract audio
    print(f"\n[1/3] Extracting audio...", end=" ", flush=True)
    ffmpeg = get_ffmpeg()
    if not extract_audio(ffmpeg, args.video, wav_path):
        print(f"{R}FAIL{X}")
        sys.exit(1)
    print(f"{G}ok{X}")

    # Step 2: Transcribe
    print(f"[2/3] Transcribing...", end=" ", flush=True)
    try:
        segments = transcribe(wav_path, model=args.model, device=args.device)
        duration_min = int(segments[-1].end // 60) if segments else 0
        duration_sec = int(segments[-1].end % 60) if segments else 0
        print(f"{G}ok{X} ({len(segments)} segments, {duration_min}:{duration_sec:02d})")
    except Exception as e:
        print(f"{R}FAIL{X}")
        print(f"{R}Error:{X} {e}")
        sys.exit(1)

    # Step 3: Generate SRT
    print(f"[3/3] Generating SRT...", end=" ", flush=True)
    try:
        sub_count = generate_srt(segments, output_srt)
        print(f"{G}ok{X} ({sub_count} subtitles)")
    except Exception as e:
        print(f"{R}FAIL{X}")
        print(f"{R}Error:{X} {e}")
        sys.exit(1)

    # Cleanup
    if not args.keep_wav:
        try:
            wav_path.unlink()
        except Exception:
            pass

    print(f"\n{G}✓ Done!{X} SRT saved to: {output_srt}")


if __name__ == "__main__":
    main()

