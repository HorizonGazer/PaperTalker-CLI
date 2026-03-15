#!/usr/bin/env python3
"""
subtitle.py - Standalone subtitle burning script
=================================================
Burns SRT subtitles into video with customizable styling.

Usage:
    python src/subtitle.py video.mp4 subtitles.srt           # Output: video_subtitled.mp4
    python src/subtitle.py video.mp4 subtitles.srt -o out.mp4  # Custom output
    python src/subtitle.py video.mp4 subtitles.srt --style bold  # Custom style

Requires:
    pip install imageio-ffmpeg
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Windows GBK fix
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; D = "\033[2m"; X = "\033[0m"


def get_ffmpeg():
    """Get FFmpeg path from imageio-ffmpeg."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        print(f"{R}ERROR:{X} imageio-ffmpeg not installed. Run: pip install imageio-ffmpeg")
        sys.exit(1)


def burn_subtitles(ffmpeg: str, video_path: Path, srt_path: Path, output_path: Path,
                   font_size: int = 20, style: str = "default") -> bool:
    """Burn SRT subtitles into video using FFmpeg.

    Args:
        ffmpeg: Path to FFmpeg binary
        video_path: Input video file
        srt_path: SRT subtitle file
        output_path: Output video file
        font_size: Font size (default 20)
        style: Subtitle style (default, bold, outline)

    Returns:
        True if successful, False otherwise
    """
    # Windows path fix for FFmpeg subtitle filter
    srt_path_fixed = str(srt_path).replace("\\", "/").replace(":", "\\:")

    # Style configurations
    styles = {
        "default": f"FontSize={font_size},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1",
        "bold": f"FontSize={font_size},Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1",
        "outline": f"FontSize={font_size},Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=2",
    }

    subtitle_style = styles.get(style, styles["default"])

    # FFmpeg command with subtitle filter
    cmd = [
        ffmpeg,
        "-i", str(video_path),
        "-vf", f"subtitles={srt_path_fixed}:force_style='{subtitle_style}'",
        "-c:a", "copy",  # Copy audio without re-encoding
        "-y",
        str(output_path)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Burn SRT subtitles into video")
    parser.add_argument("video", type=Path, help="Input video file")
    parser.add_argument("srt", type=Path, help="SRT subtitle file")
    parser.add_argument("-o", "--output", type=Path, help="Output video file (default: video_subtitled.mp4)")
    parser.add_argument("--font-size", type=int, default=20, help="Font size (default: 20)")
    parser.add_argument("--style", choices=["default", "bold", "outline"], default="default",
                        help="Subtitle style (default: default)")

    args = parser.parse_args()

    if not args.video.exists():
        print(f"{R}ERROR:{X} Video file not found: {args.video}")
        sys.exit(1)

    if not args.srt.exists():
        print(f"{R}ERROR:{X} SRT file not found: {args.srt}")
        sys.exit(1)

    output_video = args.output or args.video.with_stem(args.video.stem + "_subtitled")

    print(f"{C}Input video:{X} {args.video.name}")
    print(f"{C}Subtitles:{X} {args.srt.name}")
    print(f"{C}Output:{X} {output_video.name}")
    print(f"{C}Style:{X} {args.style} (font size: {args.font_size})")

    print(f"\nBurning subtitles...", end=" ", flush=True)
    ffmpeg = get_ffmpeg()

    if burn_subtitles(ffmpeg, args.video, args.srt, output_video, args.font_size, args.style):
        print(f"{G}ok{X}")
        print(f"\n{G}✓ Done!{X} Subtitled video saved to: {output_video}")
    else:
        print(f"{R}FAIL{X}")
        print(f"{R}ERROR:{X} Failed to burn subtitles")
        sys.exit(1)


if __name__ == "__main__":
    main()
