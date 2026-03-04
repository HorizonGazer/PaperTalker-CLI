# Environment Setup Guide

## One-Click Setup

### Windows

```bash
setup\setup.ps1     # PowerShell wrapper
# OR
setup\setup.bat     # CMD (calls sub-scripts below)
```

Sub-scripts (can be run individually if one-click fails):
```bash
setup\setup_conda.bat    # Step 1: Detect/install Conda + configure mirrors
setup\setup_env.bat      # Step 2: Create papertalker env (Python 3.11)
setup\install_deps.bat   # Step 3: Install all dependencies + Playwright chromium
```

### macOS / Linux

```bash
chmod +x setup/setup.sh
./setup/setup.sh
```

## Setup Steps Explained

### Step 1: Conda Detection & Installation

**Auto-detection priority:**
1. `conda` on PATH
2. Common install locations: `~/miniconda3`, `~/.local/miniconda3`, `C:\ProgramData\miniconda3`
3. Auto-install from Tsinghua mirror if not found

**Miniconda download URLs (Tsinghua mirror):**
- Windows: `https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Windows-x86_64.exe`
- macOS: `https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-MacOSX-arm64.sh`
- Linux: `https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh`

**Mirror configuration (auto-applied):**

Conda channels (`~/.condarc`):
```yaml
channels:
  - defaults
default_channels:
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/msys2
custom_channels:
  conda-forge: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
  pytorch: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
```

Pip mirror (`~/pip/pip.ini` on Windows, `~/.pip/pip.conf` on Unix):
```ini
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
[install]
trusted-host = pypi.tuna.tsinghua.edu.cn
```

### Step 2: Create Environment

```bash
conda create -n papertalker python=3.11 -y
```

If environment exists but is invalid (missing python.exe), auto-removes and recreates.

### Step 3: Install Dependencies

**Upstream (required for video generation):**
```bash
pip install -e deps/notebooklm-py       # NotebookLM automation
pip install -e deps/paper-search-mcp    # Academic paper search (8 platforms)
pip install python-dotenv httpx rich playwright
python -m playwright install chromium    # Browser for NotebookLM auth
```

**Downstream (required for subtitles + upload):**
```bash
pip install imageio-ffmpeg              # FFmpeg binary (avoids conda ffmpeg GBK issue)
pip install faster-whisper              # Local GPU speech-to-text (large-v3 model, ~3GB first run)
pip install jieba                       # Chinese word segmentation for subtitle splitting
pip install "biliup>=1.1.29"            # Bilibili upload (older versions blocked)
```

### Step 4: Authentication

**NotebookLM login:**
```bash
conda activate papertalker
notebooklm login
```
Opens browser for Google login. Auth saved to `~/.notebooklm/storage_state.json`. Re-run if expired.

**Bilibili login (interactive, separate terminal):**
```bash
cd vendor
./biliup.exe -u ../cookies/bilibili/account.json login
```
Select "扫码登录", scan QR with Bilibili app.

### Step 5: Proxy Configuration

Edit `.env` in project root:
```env
HTTPS_PROXY=http://your-proxy:port
HTTP_PROXY=http://your-proxy:port
```

Required for all Google NotebookLM access.

## Environment Verification

### Quick Check

```bash
conda activate papertalker
python -c "
import notebooklm, playwright, imageio_ffmpeg, faster_whisper, biliup, jieba
print('All imports OK')
print('FFmpeg:', imageio_ffmpeg.get_ffmpeg_exe())
"
```

### Full Check

```bash
python -c "
import importlib, os
from pathlib import Path
checks = [
    ('notebooklm', 'notebooklm-py'),
    ('paper_search_mcp', 'paper-search-mcp'),
    ('playwright', 'playwright'),
    ('dotenv', 'python-dotenv'),
    ('httpx', 'httpx'),
    ('rich', 'rich'),
    ('imageio_ffmpeg', 'imageio-ffmpeg'),
    ('faster_whisper', 'faster-whisper'),
    ('jieba', 'jieba'),
    ('biliup', 'biliup'),
]
for mod, pkg in checks:
    try:
        m = importlib.import_module(mod)
        v = getattr(m, '__version__', '?')
        print(f'  ok   {pkg:25s} {v}')
    except ImportError:
        print(f'  MISS {pkg}')

auth = Path.home() / '.notebooklm' / 'storage_state.json'
print(f'  {\"ok\" if auth.exists() else \"MISS\":4s} notebooklm-auth')

bili = Path('cookies/bilibili/account.json')
print(f'  {\"ok\" if bili.exists() else \"MISS\":4s} bilibili-cookies')
"
```

## Troubleshooting

### Playwright chromium version mismatch

**Symptom:** `Executable doesn't exist at .../chromium-XXXX/chrome.exe`

**Cause:** Playwright Python package updated but browser binary outdated (or vice versa).

**Fix:**
```bash
python -m playwright install chromium
```

### `conda run` UnicodeEncodeError

**Symptom:** `'gbk' codec can't encode character` on any Chinese output.

**Fix:** Never use `conda run`. Use direct path:
```bash
PYTHONIOENCODING=utf-8 "$(conda info --base)/envs/papertalker/python.exe" script.py
```

Or activate environment first:
```bash
conda activate papertalker
python script.py
```

### `conda install ffmpeg` fails

**Symptom:** UnicodeDecodeError during conda solve/rollback.

**Fix:** Use pip package instead:
```bash
pip install imageio-ffmpeg
```

### NotebookLM auth expired

**Symptom:** `ValueError: Authentication expired or invalid. Redirected to accounts.google.com`

**Fix:**
```bash
conda activate papertalker
notebooklm login
```

If `playwright install chromium` is also needed, run that first.

### macOS: `conda` command not found after install

**Fix:**
```bash
source ~/.bash_profile   # bash
source ~/.zshrc          # zsh
# Or restart terminal
```
