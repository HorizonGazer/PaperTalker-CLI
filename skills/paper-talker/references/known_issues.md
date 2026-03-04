# Known Issues & Workarounds

## Subtitle Segmentation Issues

### Subtitles split mid-word (e.g. "活" / "生生的细胞")

**Symptom:** Hard character-count splits break Chinese words unnaturally.

**Cause:** Old `chunk_subtitle_text` split at fixed 18-char boundary without word awareness.

**Fix (2026-03-04):** Added `jieba` Chinese word segmentation. Split priority:
1. Punctuation boundaries (，。、；！？：)
2. Word boundaries via `jieba.cut()` — never breaks mid-word
3. Single-word overflow: take the whole word even if > max_chars

```bash
pip install jieba
```

### Subtitle timing imprecise after splitting long segments

**Symptom:** Split subtitle lines have proportionally guessed timestamps, causing lip-sync drift.

**Fix (2026-03-04):** Enabled `word_timestamps=True` in faster-whisper transcribe call. `generate_srt()` now uses per-word start/end times to compute each subtitle line's exact time range.

### CUDA crash with word_timestamps=True inside function scope (Windows)

**Symptom:** Python process hard-crashes (exit code 127, no traceback) when calling `faster-whisper` with `word_timestamps=True` from inside a function on Windows. Module-level calls work fine.

**Cause:** CTranslate2/CUDA bug on Windows — word-level decoding in function scope causes segfault.

**Fix (2026-03-04):** `transcribe()` in publish.py now runs whisper in a subprocess where the code executes at module level. Results are serialized via pickle. Falls back to in-process transcription without word timestamps if subprocess fails.

## Windows Encoding Issues

### `conda run` crashes with GBK encoding on Chinese output

**Symptom:** `UnicodeEncodeError: 'gbk' codec can't encode character`

**Workaround:** Use Python absolute path directly with UTF-8 encoding:
```bash
PYTHONIOENCODING=utf-8 "$(conda info --base)/envs/papertalker/python.exe" script.py
```

Or activate env first: `conda activate papertalker && python script.py`

Never use `conda run` for scripts that produce Chinese output on Windows.

### `conda run` fails with multiline arguments

**Symptom:** `AssertionError: Support for scripts where arguments contain newlines not implemented`

**Workaround:** Write Python code to script files instead of inline `-c` arguments with newlines.

### `conda install ffmpeg` fails on Windows

**Symptom:** UnicodeDecodeError during package resolution or rollback.

**Workaround:** Use `pip install imageio-ffmpeg` instead. Access FFmpeg via:
```python
import imageio_ffmpeg
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
```

### PYTHONIOENCODING for skill packaging

**Symptom:** `UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f4e6'` when running `package_skill.py`

**Workaround:** Always prefix with `PYTHONIOENCODING=utf-8`:
```bash
PYTHONIOENCODING=utf-8 "$(conda info --base)/envs/papertalker/python.exe" package_skill.py
```

## Playwright Issues

### Chromium version mismatch

**Symptom:** `Executable doesn't exist at .../chromium-XXXX/chrome-win/chrome.exe`

**Cause:** Playwright Python package and installed browser binary are different versions. Happens when playwright is upgraded/downgraded but browser isn't reinstalled.

**Fix options (choose faster one):**

1. **Reinstall browser to match package:**
   ```bash
   python -m playwright install chromium
   ```

2. **Upgrade package to match existing browser (often faster):**
   ```bash
   pip install --upgrade playwright
   ```
   Check which chromium versions exist in `~/AppData/Local/ms-playwright/` and upgrade playwright to match.

**Real example:** Playwright 1.52 expected chromium-1169, but chromium-1200/1208 were installed. Upgrading playwright 1.52->1.58 matched chromium-1208 without downloading anything.

## FFmpeg Issues

### Subtitle filter fails with Windows paths

**Symptom:** FFmpeg errors on paths like `C:\Users\...\file.srt`

**Workaround:** Escape backslashes and colons:
```python
srt_escaped = str(srt_path).replace('\\', '/').replace(':', '\\:')
```

## ASR / Transcription Issues

### Doubao ASR API returns 45000030 permission error

**Symptom:** `[resource_id=volc.bigasr.auc] requested resource not granted`

**Cause:** API permission not granted for the account, or public audio URL required.

**Workaround:** Use `faster-whisper` local GPU transcription instead:
```python
from faster_whisper import WhisperModel
model = WhisperModel("large-v3", device="cuda", compute_type="float16")
segments, info = model.transcribe(wav_path, language="zh", beam_size=5,
    vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500))
```

## NotebookLM Issues

### Authentication expired

**Symptom:** `ValueError: Authentication expired or invalid. Redirected to accounts.google.com`

**Fix (interactive):**
```bash
conda activate papertalker
notebooklm login
```
If playwright chromium is also missing, run `python -m playwright install chromium` first.

**Fix (non-interactive, when login exists in browser):**
Use `tools/auto_login.py` with persistent browser profile to auto-save storage_state from existing session:
```bash
python tools/auto_login.py
```

### `notebooklm login` requires interactive terminal

**Symptom:** `Aborted!` when running from Claude CLI (script calls `input()` which requires interactive terminal)

**Workaround:** The `notebooklm login` command must be run in a real terminal. Use `tools/auto_login.py` as a non-interactive alternative that uses persistent browser profiles.

### `notebooklm login` timeout

**Cause:** Network slow or proxy unstable.

**Workaround:**
1. Ensure proxy is running and `.env` has correct address
2. Script auto-retries 3 times with 60s timeout each
3. Verify proxy can access `https://notebooklm.google.com`

### Deep Research returns no sources

**Cause:** Network instability.

**Workaround:**
1. Check proxy
2. Try `--mode fast`
3. Or use `--source search` for direct paper search

### Video generation timeout

**Cause:** Generation takes 10-20 min, longer with many sources.

**Workaround:**
1. `--timeout 3600` for longer timeout
2. `--resume <nid> <tid>` to continue polling
3. `--max-results 5` to reduce sources

### Video status cycles between pending/in_progress

**Symptom:** Status shows `in_progress` -> `pending` -> `in_progress` during generation

**This is normal.** NotebookLM video generation status cycles. The script handles this correctly by continuing to poll. Generation typically completes in 10-25 minutes.

## Bilibili Upload Issues

### biliup < 1.0 blocked by Bilibili (error 21590)

**Symptom:** `投稿工具已停用`

**Fix:** `pip install "biliup>=1.1.29"`

### `login_by_cookies` KeyError on `cookie_info`

**Symptom:** `KeyError: 'cookie_info'`

**Cause:** biliup >= 1.1 expects the full `account.json` dict.

**Fix:** Pass full account dict:
```python
with open(cookie_file, 'r') as f:
    account = json.load(f)
bili.login_by_cookies(account)  # NOT account['cookie_info']
```

### biliup.exe login is interactive

**Symptom:** Cannot complete login from Claude CLI (arrow key menu).

**Fix:** Run in a separate terminal:
```bash
cd vendor
./biliup.exe -u ../cookies/bilibili/account.json login
```

### biliup version requirement

**Symptom:** Bilibili returns error 21590 with older biliup versions.

**Fix:** `pip install "biliup>=1.1.29"` in the papertalker env.

## publish.py Path Conventions

### Root vs distributable copy

- **Canonical:** `publish.py` at project root. Uses `PROJECT_ROOT = Path(__file__).resolve().parent`.
- **Distributable:** `skills/paper-talker/scripts/publish.py`. Uses 4-level parent traversal. Only works when nested inside the project tree.

## SKILL.md Validation Issues

### YAML multiline `>-` breaks validation

**Fix:** Use single-line quoted string for description in YAML frontmatter.

### `quick_validate.py` GBK UnicodeDecodeError

**Fix:** Already patched — `encoding='utf-8'` added to `skill_md.read_text()`.
