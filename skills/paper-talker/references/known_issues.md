# Known Issues & Workarounds

## Subtitle Segmentation Issues

### Whisper produces duplicate consecutive segments

**Symptom:** Subtitles contain repeated text — the same sentence appears twice in a row, causing visual duplication in the burned video.

**Cause:** Whisper (especially with VAD filter) can produce overlapping segments with identical or near-identical text. This is a known upstream artifact.

**Fix (2026-03-09):** Added `deduplicate_segments()` in publish.py (after transcription, before SRT generation):
- Exact duplicates: merges timing, keeps one copy
- Near-duplicates (one text is a substring of the other): keeps the longer text, merges timing
- Logs how many duplicates were removed (e.g., `210 segments, 9:39, 5 duplicates removed`)

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

**Fix (2026-03-09):** `publish.py` now uses Bilibili's TV QR login API directly via Python — no interactive menu needed. The QR code is rendered in the terminal via `qrcode` library. User just scans with Bilibili App.

If the Python API fails, falls back to launching `biliup.exe login` via a temp `.bat` file in a new terminal window.

Manual fallback if both fail:
```bash
cd vendor
./biliup.exe -u ../cookies/bilibili/account.json login
```

### biliup.exe login not triggered on Windows (nested-quote bug)

**Symptom:** `publish.py` opens a terminal window for Bilibili login, but `biliup.exe` does not actually execute. The window opens blank or closes immediately. Cookies are never created, so upload fails.

**Cause:** The original `start "title" cmd /k "..."` command contained nested double quotes that Windows cmd cannot parse:
```
start "B站登录" cmd /k ""C:\...\biliup.exe" -u "C:\...\account.json" login"
```
The inner quotes confuse cmd, causing the command to silently fail.

**Fix (2026-03-09):** `ensure_bilibili_login()` now writes a temporary `.bat` file (`vendor/_bilibili_login.bat`) containing the login command, then launches it with `start "B站登录" cmd /c "path\to\_bilibili_login.bat"`. The `.bat` file is cleaned up after login completes or times out. This eliminates all nested-quote issues.

The `.bat` also shows clear instructions to the user:
```
========================================
   B站登录 - 请选择「扫码登录」
========================================
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

## WeChat Channels (视频号) Upload Issues

### Wujie iframe becomes empty after video upload

**Symptom:** After uploading video via file chooser, the wujie iframe (`/micro/content/post/create`) exists but contains no form elements. All locators return 0 results.

**Cause:** Wujie micro-frontend framework may clear iframe content after upload completes, exposing elements to the main page instead.

**Fix (2026-03-10):** `upload_weixin_channels()` checks if iframe has elements after upload. If `input[placeholder*="概括"]` count is 0, automatically switches to main page for form filling.

```python
short_title_test = upload_frame.locator('input[placeholder*="概括"]')
if short_title_test.count() == 0 and hasattr(upload_frame, 'url'):
    upload_frame = page  # Use main page instead
```

### Upload completion detection

**Symptom:** Script waits 180s for upload to complete but doesn't detect when video is ready.

**Fix (2026-03-10):** Check multiple indicators:
1. `video` element appears
2. "删除" button appears
3. Short title input becomes enabled (not disabled)

### Description field is contenteditable div, not textarea

**Symptom:** Standard `textarea` or `input` selectors don't find the description field.

**Fix (2026-03-10):** Description is `<div contenteditable="" data-placeholder="添加描述" class="input-editor"></div>`. Use:
```python
desc_elem = upload_frame.locator('div.input-editor[contenteditable][data-placeholder="添加描述"]')
desc_elem.evaluate(f'el => el.innerText = {repr(text)}')
```

### Short title max length

**Symptom:** WeChat Channels rejects titles longer than 30 characters.

**Fix:** `upload_weixin_channels()` automatically truncates to 16 characters (safe limit for Chinese).

### Proxy causes HTTP errors on Chinese sites

**Symptom:** `net::ERR_HTTP_RESPONSE_CODE_FAILURE` when accessing `channels.weixin.qq.com`.

**Fix (2026-03-10):** Add `--no-proxy-server` to browser launch args:
```python
context = p.chromium.launch_persistent_context(
    args=["--disable-blink-features=AutomationControlled", "--no-proxy-server"],
    ...
)
```

### Publish button stays disabled after upload

**Symptom:** Video uploads to WeChat Channels but the publish button remains disabled (`weui-desktop-btn_disabled` class). Both publish and draft buttons are unusable.

**Cause:** Two issues:
1. Upload completion detection only checked iframe, but after Wujie micro-frontend switch, elements move to main page
2. Video server-side processing takes time after upload completes. Previous code only waited 2 seconds before checking

**Fix (2026-03-10):**
1. Upload detection now checks both iframe AND main page for `<video>` element / `删除` button
2. Upload timeout increased from 180s to 300s (5 min) for large videos
3. Publish button polling: waits up to 180s (3 min) with 5s intervals for button to become enabled
4. Added debug screenshot + detailed logging when button stays disabled

### Bilibili TV QR API returns empty response

**Symptom:** `Expecting value: line 1 column 1 (char 0)` when calling Bilibili TV QR login API.

**Cause:** Proxy may intercept/block the passport.bilibili.com API, or API endpoint changed.

**Fix (2026-03-10):** Added 3-retry loop with 10s timeout. Falls back to biliup.exe `.bat` launcher which requires user to scan QR code in a terminal window.

## ASR / Transcription Issues

### Whisper outputs Traditional Chinese characters

**Symptom:** Subtitles contain Traditional Chinese (繁体字) instead of Simplified Chinese.

**Fix (2026-03-10):** Two-layer approach:
1. Added `initial_prompt="以下是普通话的句子，使用简体中文。"` to Whisper transcribe call to guide the model
2. Post-transcription Traditional-to-Simplified conversion via embedded `str.maketrans()` table (~200+ character mappings). Applied to both segment text and word text. No external dependencies (avoids `opencc` installation issues behind proxy).

### Playwright sync_api event loop conflict

**Symptom:** `RuntimeError: This event loop is already running` when calling `sync_playwright()` after other async-capable libraries (faster-whisper, etc.) have been imported.

**Cause:** Playwright's sync API wraps async calls with `loop.run_until_complete()`. If the process's asyncio event loop is in an inconsistent state (from prior imports or subprocess mechanisms), this fails.

**Fix (2026-03-10):** WeChat Channels upload runs in a separate subprocess (`_weixin_upload_worker.py`) using Playwright's **async API** directly with `asyncio.run()`. This gives a completely clean event loop. The main process communicates results via a temp JSON file.

### WeChat login false positive from transient URL change

**Symptom:** Login detected as successful but page redirects back to `login.html`. All subsequent navigation to create page fails, file input not found.

**Cause:** During QR scan authentication, the URL may briefly change (triggering `"login" not in url` check) then redirect back to `login.html` if the session wasn't fully established.

**Fix (2026-03-10):** Two-layer login verification:
1. After URL changes away from "login", wait 3s and re-check to confirm URL is stable
2. After all navigation attempts, verify final URL is NOT on login page — abort with clear error if stuck
3. Body text check removed (login page HTML contains dashboard keywords)
