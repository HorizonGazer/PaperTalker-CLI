#!/usr/bin/env python3
"""
transcribe.py - Standalone audio transcription script
=====================================================
Extracts audio from video, transcribes with faster-whisper, generates SRT.
Supports parallel transcription by splitting audio into chunks (--workers N).

Usage:
    python src/transcribe.py video.mp4                    # Output: video.srt
    python src/transcribe.py video.mp4 -o output.srt      # Custom output
    python src/transcribe.py video.mp4 --model large-v3   # Custom model
    python src/transcribe.py video.mp4 --device cuda       # Force GPU
    python src/transcribe.py video.mp4 --workers 3         # Parallel (3 chunks)

Requires:
    pip install imageio-ffmpeg faster-whisper
"""

# MKL env vars must be set before any CTranslate2/faster_whisper import
import os as _os
_os.environ.setdefault("MKL_THREADING_LAYER", "sequential")
_os.environ.setdefault("OMP_NUM_THREADS", "1")
_os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Windows GBK fix
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

# Subtitle display limits
MAX_CHARS_PER_LINE = 18  # Max Chinese chars per subtitle line
MAX_DURATION_PER_SUB = 6.0  # Max seconds a single subtitle can display
OVERLAP_SECONDS = 3.0  # Overlap between chunks to avoid cutting mid-sentence

G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; D = "\033[2m"; X = "\033[0m"


def get_ffmpeg():
    """Get FFmpeg path from imageio-ffmpeg."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        print(f"{R}ERROR:{X} imageio-ffmpeg not installed. Run: pip install imageio-ffmpeg")
        sys.exit(1)


def get_audio_duration(ffmpeg: str, wav_path: Path) -> float:
    """Get audio duration in seconds using FFmpeg."""
    result = subprocess.run(
        [ffmpeg, "-i", str(wav_path), "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    # Parse duration from stderr (FFmpeg outputs info to stderr)
    for line in (result.stderr or "").splitlines():
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", line)
        if m:
            h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            return h * 3600 + mi * 60 + s + cs / 100.0
    return 0.0


def extract_audio(ffmpeg: str, video_path: Path, wav_path: Path) -> bool:
    """Extract audio from video to 16kHz mono WAV."""
    result = subprocess.run(
        [ffmpeg, "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", str(wav_path), "-y"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.returncode == 0


def split_audio(ffmpeg: str, wav_path: Path, num_chunks: int, tmpdir: str) -> list:
    """Split WAV into overlapping chunks for parallel transcription.

    Returns list of (chunk_path, start_time, end_time, clean_start, clean_end).
    - start_time/end_time: actual audio range of the chunk (includes overlap)
    - clean_start/clean_end: the "owned" range for this chunk (no overlap)
    """
    duration = get_audio_duration(ffmpeg, wav_path)
    if duration <= 0:
        raise RuntimeError("Could not determine audio duration")

    chunk_len = duration / num_chunks
    chunks = []

    for i in range(num_chunks):
        clean_start = i * chunk_len
        clean_end = min((i + 1) * chunk_len, duration)
        # Add overlap: extend start backward (except first chunk)
        actual_start = max(0, clean_start - OVERLAP_SECONDS) if i > 0 else 0
        # Add overlap: extend end forward (except last chunk)
        actual_end = min(duration, clean_end + OVERLAP_SECONDS) if i < num_chunks - 1 else duration

        chunk_path = Path(tmpdir) / f"chunk_{i:03d}.wav"
        result = subprocess.run(
            [ffmpeg, "-i", str(wav_path),
             "-ss", f"{actual_start:.3f}",
             "-to", f"{actual_end:.3f}",
             "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
             str(chunk_path), "-y"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to split chunk {i}: {result.stderr}")

        chunks.append((str(chunk_path), actual_start, actual_end, clean_start, clean_end))

    return chunks


def _transcribe_chunk(args):
    """Worker function to transcribe a single chunk in a subprocess.

    Args: tuple of (wav_path, model, device, chunk_index)
    Returns: (chunk_index, data_list, info_line) or raises
    """
    wav_path, model, device, chunk_idx = args
    import pickle
    import tempfile as _tf

    script_content = '''
import os, sys, pickle
os.environ["MKL_THREADING_LAYER"] = "sequential"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from faster_whisper import WhisperModel

try:
    import ctranslate2
    _has_cuda = "cuda" in ctranslate2.get_supported_compute_types("cuda")
except Exception:
    _has_cuda = False

_device = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "auto" else ("cuda" if _has_cuda else "cpu")
_model = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "auto" else ("large-v3" if _has_cuda else "small")
_ctype = "float16" if _device == "cuda" else "int8"

print(f"  whisper[{sys.argv[5]}]: {_model} on {_device} ({_ctype})", flush=True)

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
    with _tf.NamedTemporaryFile(suffix=".py", delete=False, mode="w",
                                encoding="utf-8") as sf:
        sf.write(script_content)
        script_path = sf.name

    with _tf.NamedTemporaryFile(suffix=".pkl", delete=False) as pf:
        pkl_path = pf.name

    try:
        device_arg = device if device else "auto"
        model_arg = model if model else "auto"

        result = subprocess.run(
            [sys.executable, script_path, str(wav_path), pkl_path,
             device_arg, model_arg, str(chunk_idx)],
            capture_output=True, text=True, timeout=1200,
            env={**_os.environ, "PYTHONIOENCODING": "utf-8",
                 "MKL_THREADING_LAYER": "sequential",
                 "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
        )

        info_line = ""
        for line in (result.stdout or "").strip().splitlines():
            if "whisper[" in line:
                info_line = line.strip()

        if Path(pkl_path).exists() and Path(pkl_path).stat().st_size > 0:
            with open(pkl_path, "rb") as f:
                data = pickle.load(f)
            return (chunk_idx, data, info_line)

        err = (result.stderr or "").strip().split("\n")[-10:]
        raise RuntimeError(f"Chunk {chunk_idx} failed:\n" + "\n".join(err))
    finally:
        try:
            Path(script_path).unlink()
            Path(pkl_path).unlink()
        except Exception:
            pass


def _offset_segments(data: list, offset: float) -> list:
    """Add time offset to all segments and their words."""
    for d in data:
        d["start"] += offset
        d["end"] += offset
        if "words" in d:
            for w in d["words"]:
                w["start"] += offset
                w["end"] += offset
    return data


def _merge_chunk_segments(chunks_data: list) -> list:
    """Merge segments from overlapping chunks, deduplicating the overlap regions.

    chunks_data: list of (chunk_index, data, actual_start, actual_end, clean_start, clean_end)
    """
    # Sort by chunk index
    chunks_data.sort(key=lambda x: x[0])

    merged = []
    for chunk_idx, data, actual_start, actual_end, clean_start, clean_end in chunks_data:
        # Offset all timestamps by actual_start (chunk audio starts at t=0 internally)
        data = _offset_segments(data, actual_start)

        for seg in data:
            seg_mid = (seg["start"] + seg["end"]) / 2.0
            # Only keep segments whose midpoint falls in the "clean" owned range
            if seg_mid >= clean_start and seg_mid < clean_end:
                merged.append(seg)
            # For the last chunk, also include segments at the very end
            elif chunk_idx == chunks_data[-1][0] and seg_mid >= clean_start:
                merged.append(seg)

    # Sort by start time
    merged.sort(key=lambda d: d["start"])

    # Deduplicate near-overlapping segments
    deduped = []
    for seg in merged:
        if not deduped:
            deduped.append(seg)
            continue
        prev = deduped[-1]
        # Skip if this segment overlaps significantly with the previous
        overlap = min(prev["end"], seg["end"]) - max(prev["start"], seg["start"])
        min_dur = min(prev["end"] - prev["start"], seg["end"] - seg["start"])
        if min_dur > 0 and overlap / min_dur > 0.5:
            # Keep the one with more text (likely more complete)
            if len(seg.get("text", "").strip()) > len(prev.get("text", "").strip()):
                deduped[-1] = seg
            continue
        deduped.append(seg)

    return deduped


def transcribe(wav_path: Path, model: str = None, device: str = None) -> list:
    """Transcribe audio using faster-whisper (single process, original behavior).

    Runs in a dedicated subprocess to isolate GPU/CPU memory.
    """
    return transcribe_parallel(wav_path, model=model, device=device, workers=1)


def transcribe_parallel(wav_path: Path, model: str = None, device: str = None,
                         workers: int = 3) -> list:
    """Transcribe audio using faster-whisper with parallel chunk processing.

    Splits audio into `workers` overlapping chunks, transcribes each in a
    separate subprocess, then merges results with correct timestamps.

    Args:
        wav_path: Path to 16kHz mono WAV file
        model: Model name or None for auto
        device: Device or None for auto-detect
        workers: Number of parallel workers (1 = no splitting)

    Returns:
        List of segment objects with .start, .end, .text, .words attributes
    """
    import pickle

    if workers <= 1:
        # Single-process: use original behavior (no splitting)
        result = _transcribe_chunk((str(wav_path), model, device, 0))
        _, data, info_line = result
        if info_line:
            print(f"\n{D}{info_line}{X}", flush=True)

        class Seg:
            def __init__(self, d):
                self.start = d["start"]
                self.end = d["end"]
                self.text = d["text"]
                self.words = None
                if "words" in d:
                    self.words = [type("W", (), w) for w in d["words"]]
        return [Seg(d) for d in data]

    # Multi-process: split audio into chunks
    ffmpeg = get_ffmpeg()
    with tempfile.TemporaryDirectory(prefix="transcribe_") as tmpdir:
        print(f"\n{D}  splitting audio into {workers} chunks...{X}", flush=True)
        chunks = split_audio(ffmpeg, wav_path, workers, tmpdir)

        # Launch parallel transcription
        print(f"{D}  launching {workers} parallel workers...{X}", flush=True)
        tasks = []
        for chunk_path, actual_start, actual_end, clean_start, clean_end in chunks:
            chunk_idx = len(tasks)
            tasks.append((chunk_path, model, device, chunk_idx))

        chunks_data = []
        info_printed = False
        # Use ProcessPoolExecutor for true parallelism
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_transcribe_chunk, t): t for t in tasks}
            for future in as_completed(futures):
                task_args = futures[future]
                chunk_idx = task_args[3]
                try:
                    idx, data, info_line = future.result()
                    # Find the matching chunk info
                    _, actual_start, actual_end, clean_start, clean_end = chunks[idx]
                    chunks_data.append((idx, data, actual_start, actual_end, clean_start, clean_end))
                    if info_line and not info_printed:
                        print(f"\n{D}{info_line}{X}", flush=True)
                        info_printed = True
                    print(f"{D}  chunk {idx+1}/{workers} done ({len(data)} segments){X}", flush=True)
                except Exception as e:
                    raise RuntimeError(f"Worker {chunk_idx} failed: {e}")

        # Merge all chunks
        print(f"{D}  merging {workers} chunks...{X}", flush=True)
        merged_data = _merge_chunk_segments(chunks_data)

    class Seg:
        def __init__(self, d):
            self.start = d["start"]
            self.end = d["end"]
            self.text = d["text"]
            self.words = None
            if "words" in d:
                self.words = [type("W", (), w) for w in d["words"]]
    return [Seg(d) for d in merged_data]


# ── Subtitle Verification ──────────────────────────────────────

# Traditional → Simplified Chinese mapping (common Whisper outputs)
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

# Regex for garbled/nonsense patterns
_GARBLED_RE = re.compile(
    r'[\u2500-\u257F]'           # Box-drawing chars
    r'|[\u2580-\u259F]'          # Block elements
    r'|(.)\1{4,}'               # Same char repeated 5+ times
    r'|[a-zA-Z]{20,}'           # Latin chars 20+ in a row (likely garbled)
)


def verify_segments(segments: list) -> tuple:
    """Second-pass verification of transcription segments.

    Checks and fixes:
    1. Traditional → Simplified Chinese conversion
    2. Remove garbled/nonsense text
    3. Remove exact/near duplicate consecutive segments
    4. Fix timing issues (negative duration, huge gaps, overlaps)
    5. Remove suspiciously short segments (< 0.1s with single char)

    Returns:
        (verified_segments, fixes_log) where fixes_log is a list of fix descriptions
    """
    fixes = []

    # Pass 1: T2S conversion + garbled removal
    cleaned = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue

        # Check for garbled text
        if _GARBLED_RE.search(text):
            # If more than half is garbled, drop the segment
            clean_text = _GARBLED_RE.sub("", text)
            if len(clean_text) < len(text) * 0.5:
                fixes.append(f"removed garbled: '{text[:30]}...'")
                continue
            seg.text = clean_text
            fixes.append(f"cleaned garbled chars in: '{text[:30]}...'")

        # T2S conversion
        converted = seg.text.translate(_T2S_TABLE)
        if converted != seg.text:
            fixes.append(f"T2S: '{seg.text[:20]}' -> '{converted[:20]}'")
            seg.text = converted
            # Also convert words if present
            if seg.words:
                for w in seg.words:
                    w.word = w.word.translate(_T2S_TABLE)

        cleaned.append(seg)

    # Pass 2: Deduplicate consecutive identical/near-duplicate
    deduped = []
    dup_count = 0
    for seg in cleaned:
        if not deduped:
            deduped.append(seg)
            continue

        prev = deduped[-1]
        cur_text = seg.text.strip()
        prev_text = prev.text.strip()

        # Exact duplicate
        if cur_text == prev_text:
            prev.end = max(prev.end, seg.end)
            dup_count += 1
            continue

        # Near-duplicate: one is substring of other
        if len(cur_text) > 4 and len(prev_text) > 4:
            if cur_text in prev_text or prev_text in cur_text:
                if len(cur_text) > len(prev_text):
                    prev.text = seg.text
                    if seg.words:
                        prev.words = seg.words
                prev.end = max(prev.end, seg.end)
                dup_count += 1
                continue

        deduped.append(seg)

    if dup_count > 0:
        fixes.append(f"removed {dup_count} duplicate segments")

    # Pass 3: Timing fixes
    timing_fixes = 0
    for i, seg in enumerate(deduped):
        # Fix negative duration
        if seg.end <= seg.start:
            seg.end = seg.start + 0.5
            timing_fixes += 1

        # Fix overlapping with next segment
        if i < len(deduped) - 1:
            next_seg = deduped[i + 1]
            if seg.end > next_seg.start:
                seg.end = next_seg.start
                timing_fixes += 1

    if timing_fixes > 0:
        fixes.append(f"fixed {timing_fixes} timing issues")

    # Pass 4: Remove suspiciously short segments
    short_removed = 0
    final = []
    for seg in deduped:
        dur = seg.end - seg.start
        text = seg.text.strip()
        # Remove very short segments with minimal content
        if dur < 0.1 and len(text) <= 1:
            short_removed += 1
            continue
        final.append(seg)

    if short_removed > 0:
        fixes.append(f"removed {short_removed} too-short segments")

    # Pass 5: Context-aware error correction
    final, ctx_fixes = _context_aware_correction(final)
    fixes.extend(ctx_fixes)

    return final, fixes


# ══════════════════════════════════════════════════════════════
#  Context-aware subtitle error correction
# ══════════════════════════════════════════════════════════════

# Common Whisper homophone / misheard corrections for academic Chinese
# Format: wrong → correct (only apply when context supports it)
_HOMOPHONE_CORRECTIONS = {
    # 学术常见错误
    '基因组学': None,  # correct term, skip
    '积因': '基因',
    '及因': '基因',
    '基阴': '基因',
    '击因': '基因',
    '寄因': '基因',
    '蛋白治': '蛋白质',
    '蛋白置': '蛋白质',
    '单白质': '蛋白质',
    '旦白质': '蛋白质',
    '细包': '细胞',
    '细泡': '细胞',
    '戏胞': '细胞',
    '系胞': '细胞',
    '溪胞': '细胞',
    '生物芯息学': '生物信息学',
    '生物新息学': '生物信息学',
    '深度血习': '深度学习',
    '深度雪习': '深度学习',
    '机器血习': '机器学习',
    '机器雪习': '机器学习',
    '神经往络': '神经网络',
    '神经忘络': '神经网络',
    '人工只能': '人工智能',
    '人工只能': '人工智能',
    '算发': '算法',
    '算罚': '算法',
    '数据及': '数据集',
    '数据急': '数据集',
    '注意利机制': '注意力机制',
    '置信去间': '置信区间',
    '准确律': '准确率',
    '准确绿': '准确率',
    '显著差意': '显著差异',
    '统计显著': None,  # correct
    '模形': '模型',
    '模行': '模型',
    '莫型': '模型',
    '磨型': '模型',
    '训连': '训练',
    '训炼': '训练',
    '迅练': '训练',
    '参数优话': '参数优化',
    '参数有化': '参数优化',
    '梯渡下降': '梯度下降',
    '梯度夏降': '梯度下降',
    '卷击': '卷积',
    '卷及': '卷积',
    '预训连': '预训练',
    '微条': '微调',
    '围调': '微调',
    '分只': '分支',
    '特正': '特征',
    '特整': '特征',
    '聚类分洗': '聚类分析',
    '居类': '聚类',
    '距类': '聚类',
    '回鬼': '回归',
    '回贵': '回归',
    '分类器': None,  # correct
    '分雷器': '分类器',
    '分类其': '分类器',
    '变一器': '变异器',
    '变移器': '变异器',
    '转录租': '转录组',
    '转录阻': '转录组',
    '空间转入组': '空间转录组',
    '空间专录组': '空间转录组',
    '单细包': '单细胞',
    '表大量': '表达量',
    '表打量': '表达量',
    '差一表达': '差异表达',
    '差移表达': '差异表达',
    '马尔科夫': None,  # correct
    '马可夫': '马尔可夫',
    '布朗云动': '布朗运动',
    '布朗远动': '布朗运动',
    '随即过程': '随机过程',
    '随即变量': '随机变量',
    '概律': '概率',
    '概绿': '概率',
    '盖率': '概率',
    '期忘值': '期望值',
    '期旺值': '期望值',
    '方差': None,  # correct
    '放差': '方差',
    '协方差': None,  # correct
    '携方差': '协方差',
    '正太分布': '正态分布',
    '正台分布': '正态分布',
    '泊松分部': '泊松分布',
    '薄松分布': '泊松分布',
    '边路': '遍历',
    '遍利': '遍历',
}

# Context keywords that boost confidence for corrections
_ACADEMIC_CONTEXT_KEYWORDS = {
    '研究', '论文', '方法', '实验', '结果', '分析', '数据', '模型',
    '算法', '学习', '训练', '网络', '计算', '优化', '参数', '特征',
    '预测', '分类', '回归', '聚类', '基因', '蛋白', '细胞', '组学',
    '转录', '表达', '生物', '医学', '临床', '样本', '统计', '显著',
    '概率', '分布', '随机', '过程', '变量', '函数', '矩阵', '向量',
    '空间', '维度', '降维', '嵌入', '编码', '解码', '注意力',
    '卷积', '循环', '变换', '扩散', '生成', '对抗', '判别',
}

# Filler / hallucination patterns that Whisper repeats
_FILLER_PATTERNS = re.compile(
    r'^(嗯+|啊+|呃+|哦+|唔+|呢+|吧+|嘛+|哈+|嗨+|噢+)$'  # Pure filler
    r'|^(谢谢观看|感谢收看|感谢观看|谢谢大家|谢谢收看|字幕制作|字幕校对).*'  # Hallucinated end cards
    r'|^(请订阅|别忘了|点赞|关注|subscribe|like|share).*'  # Hallucinated CTAs
    r'|^\.+$'    # Only dots
    r'|^\*+$'    # Only asterisks
    r'|^-+$'     # Only dashes
, re.IGNORECASE)


def _context_aware_correction(segments: list) -> tuple:
    """Apply context-aware corrections to subtitle segments.
    
    Uses a sliding window of 3 segments (prev, current, next) to:
    1. Fix common Whisper homophones in academic Chinese
    2. Remove filler words / hallucinated end cards
    3. Merge orphan fragments into neighbors
    
    Returns:
        (corrected_segments, fixes_log)
    """
    if not segments:
        return segments, []
    
    fixes = []
    
    # --- Phase A: Homophone correction with context ---
    for i, seg in enumerate(segments):
        text = seg.text.strip()
        if not text:
            continue
        
        # Build context window (prev + next segment text)
        context_parts = []
        if i > 0:
            context_parts.append(segments[i-1].text.strip())
        context_parts.append(text)
        if i < len(segments) - 1:
            context_parts.append(segments[i+1].text.strip())
        context = ''.join(context_parts)
        
        # Check if we're in academic context
        in_academic_ctx = any(kw in context for kw in _ACADEMIC_CONTEXT_KEYWORDS)
        
        corrected = text
        for wrong, right in _HOMOPHONE_CORRECTIONS.items():
            if right is None:
                continue  # Skip entries that are correct terms
            if wrong in corrected:
                # Apply correction; in academic context, always apply;
                # otherwise require the correct term to appear nearby
                if in_academic_ctx or right in context:
                    corrected = corrected.replace(wrong, right)
                    fixes.append(f"纠错: '{wrong}' → '{right}' (上下文: ...{context[:30]}...)")
        
        if corrected != text:
            seg.text = corrected
            if seg.words:
                # Rebuild word text (approximate — word boundaries may shift)
                for w in seg.words:
                    for wrong, right in _HOMOPHONE_CORRECTIONS.items():
                        if right is None:
                            continue
                        if wrong in w.word:
                            w.word = w.word.replace(wrong, right)
    
    # --- Phase B: Remove filler / hallucinated segments ---
    cleaned = []
    filler_count = 0
    for seg in segments:
        text = seg.text.strip()
        if _FILLER_PATTERNS.match(text):
            filler_count += 1
            continue
        cleaned.append(seg)
    
    if filler_count > 0:
        fixes.append(f"removed {filler_count} filler/hallucinated segments")
    
    # --- Phase C: Merge orphan fragments ---
    # Segments with ≤ 2 chars and < 0.5s that look like split-off pieces
    merged = []
    skip_next = False
    for i, seg in enumerate(cleaned):
        if skip_next:
            skip_next = False
            continue
        
        text = seg.text.strip()
        dur = seg.end - seg.start
        
        # Check if this is an orphan fragment
        if len(text) <= 2 and dur < 0.5 and text not in ('的', '了', '是', '在', '和', '与', '或'):
            # Try merging into previous segment
            if merged:
                prev = merged[-1]
                gap = seg.start - prev.end
                if gap < 0.3:
                    prev.text = prev.text.strip() + text
                    prev.end = seg.end
                    fixes.append(f"merged orphan '{text}' into previous")
                    continue
            # Try merging into next segment
            if i < len(cleaned) - 1:
                nxt = cleaned[i + 1]
                gap = nxt.start - seg.end
                if gap < 0.3:
                    nxt.text = text + nxt.text.strip()
                    nxt.start = seg.start
                    fixes.append(f"merged orphan '{text}' into next")
                    continue
        
        merged.append(seg)
    
    return merged, fixes


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
    parser.add_argument("--workers", type=int, default=3, help="Parallel workers (default: 3, 1=no split)")
    parser.add_argument("--keep-wav", action="store_true", help="Keep extracted WAV file")

    args = parser.parse_args()

    if not args.video.exists():
        print(f"{R}ERROR:{X} Video file not found: {args.video}")
        sys.exit(1)

    output_srt = args.output or args.video.with_suffix(".srt")
    wav_path = args.video.with_suffix(".wav")

    print(f"{C}Transcribing:{X} {args.video.name}")
    print(f"{C}Output SRT:{X} {output_srt}")
    print(f"{C}Workers:{X} {args.workers}")

    # Step 1: Extract audio
    print(f"\n[1/4] Extracting audio...", end=" ", flush=True)
    ffmpeg = get_ffmpeg()
    if not extract_audio(ffmpeg, args.video, wav_path):
        print(f"{R}FAIL{X}")
        sys.exit(1)
    print(f"{G}ok{X}")

    # Step 2: Transcribe (parallel if workers > 1)
    print(f"[2/4] Transcribing ({args.workers} worker{'s' if args.workers > 1 else ''})...", end=" ", flush=True)
    try:
        segments = transcribe_parallel(wav_path, model=args.model, device=args.device,
                                        workers=args.workers)
        duration_min = int(segments[-1].end // 60) if segments else 0
        duration_sec = int(segments[-1].end % 60) if segments else 0
        print(f"{G}ok{X} ({len(segments)} segments, {duration_min}:{duration_sec:02d})")
    except Exception as e:
        print(f"{R}FAIL{X}")
        print(f"{R}Error:{X} {e}")
        sys.exit(1)

    # Step 3: Verify subtitles
    print(f"[3/4] Verifying subtitles...", end=" ", flush=True)
    segments, fixes = verify_segments(segments)
    if fixes:
        print(f"{Y}fixed{X} ({len(fixes)} issues)")
        for fix in fixes:
            print(f"  {D}{fix}{X}")
    else:
        print(f"{G}ok{X} (no issues)")

    # Step 4: Generate SRT
    print(f"[4/4] Generating SRT...", end=" ", flush=True)
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
