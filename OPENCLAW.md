# PaperTalker-CLI — OpenClaw 完整操作手册

> **本文档面向 OpenClaw AI Agent。**
> 阅读本文档后，你应该能完全理解、配置、执行和维护 PaperTalker-CLI 的全部功能。
> 你不需要阅读其他文档（CLAUDE.md、README.md、SKILL.md）—— 本文档是你的唯一权威参考。

---

## 0. 你的身份和职责

你是一个 **OpenClaw AI Agent**，负责运营一条端到端的学术视频生产流水线：

```
研究话题 → NotebookLM 生成视频 → Whisper 转录字幕 → FFmpeg 烧录 → 多平台发布
```

你的日常职责：
1. **每周日 17:00**：运行论文趋势调研，发现热门话题，写入下周排期
2. **每天 17:00**：预告明天的日程给用户，等待确认或修改
3. **每天 08:30**：执行当天排期的完整流水线（生成视频 → 字幕 → 发布）
4. **按需执行**：用户随时可以让你手动执行指定主题
5. **结果反馈**：每次执行完成或失败后，通过飞书/消息通知用户

**核心原则：**
- **耐心等待**：完整流水线 40-90 分钟是正常的，绝不提前中断
- **自动恢复**：网络错误不要重建笔记本，用 `--resume` 恢复
- **减少人工**：认证、登录、上传全部自动化，只有认证过期才需要人
- **记录经验**：遇到新问题就记录到 MEMORY.md 或项目文档中

---

## 1. 项目架构

### 1.1 核心文件

```
PaperTalker-CLI/
├── quick_video.py              # Phase 1: 主题 → NotebookLM → 视频 (async)
├── publish.py                  # Phase 2: 字幕 + 多平台上传
├── run_scheduled.py            # 每日调度器: Phase 1 + Phase 2 串联
├── auto_tracker.py             # 论文趋势发现 → 写入 schedule.txt
├── setup_cron.py               # OpenClaw cron 注册助手
├── schedule.txt                # 每日排期表 (TSV 格式，Tab 分隔)
├── video.md                    # 视频生成提示词 (学术风格，可自定义)
├── .env                        # 代理地址 + API 密钥 (从 .env.example 复制)
├── .env.example                # 环境配置模板
```

### 1.2 源代码模块

```
├── src/
│   ├── transcribe.py           # 音频→SRT (faster-whisper, 并行分块, 上下文纠错)
│   ├── subtitle.py             # SRT→烧录进视频 (FFmpeg)
│   ├── upload_bilibili.py      # B站上传 (biliup API)
│   ├── upload_weixin.py        # 微信视频号上传 (Playwright)
│   ├── workers/
│   │   └── weixin_upload_worker.py  # 视频号上传子进程 (async)
│   └── utils/
│       └── paper_search.py     # 论文搜索封装
```

### 1.3 Skills (可安装到 OpenClaw)

```
├── skills/
│   ├── paper-talker/           # 流水线 skill (SKILL.md + 参考文档)
│   │   ├── SKILL.md            # 完整技术参考
│   │   ├── scripts/            # 可分发的脚本副本
│   │   └── references/         # setup.md, upstream.md, downstream.md, known_issues.md
│   └── literature-review/      # 论文搜索 skill
│       ├── SKILL.md            # 文献检索方法论
│       └── scripts/
│           ├── paper_search.py     # Semantic Scholar + arXiv + CrossRef
│           └── deep_read.py        # PDF 精读
```

### 1.4 数据目录

```
├── cookies/
│   ├── bilibili/account.json   # B站认证 (gitignored)
│   └── weixin/                 # 微信视频号认证 (gitignored)
│       ├── storage_state.json
│       └── browser_profile/    # Playwright 持久化浏览器
├── vendor/
│   └── biliup.exe              # B站上传二进制 (Windows, gitignored)
├── deps/
│   └── notebooklm-py/          # NotebookLM Python 客户端 (本地可编辑安装)
├── tools/
│   ├── auto_login.py           # NotebookLM 自动登录 (浏览器弹出)
│   └── verify.py               # 依赖完整性验证
├── setup/
│   ├── setup.bat               # Windows 一键安装
│   ├── setup.sh                # macOS/Linux 一键安装
│   ├── setup_conda.bat         # Conda 安装 + 清华镜像
│   ├── setup_env.bat           # 创建 papertalker 环境
│   └── install_deps.bat        # pip 安装所有依赖
├── output/                     # 原始视频 (处理后自动清理)
├── output_subtitled/           # 最终成品，按日期归档
│   └── YYYY-MM-DD/             # {topic}.mp4 + {topic}.srt
├── run_history.json            # 完整运行历史 (JSON)
├── run_history.txt             # 简单文本日志
└── tracker_history.txt         # auto_tracker 运行历史
```

### 1.5 数据流全景

```
auto_tracker.py (每周论文发现)
    ↓ 写入
schedule.txt (TSV: 日期 | 主题 | 模式 | 平台 | 数量 | 状态)
    ↓ 读取
run_scheduled.py (每日 08:30 cron)
    ├── [可选] --pre-hook: auto_tracker.py --write-schedule
    ├── pick_topic(): 日期精确匹配 > queue FIFO
    │
    ├── Phase 1: quick_video.py (NotebookLM → output/*.mp4)
    │   ├── Step 1: 创建笔记本 (~2s)
    │   ├── Step 2: 启动 Deep Research
    │   ├── Step 3: 等待 Research 完成 (5-20 分钟, 发现 N 个来源)
    │   ├── Step 4: 导入来源 (批量15→5→逐个, 5-20 分钟)
    │   ├── Step 5: 等待来源处理 (30s-5min)
    │   ├── Step 6: 生成视频 (10-30+ 分钟, 轮询状态)
    │   └── Step 7: 下载 MP4 到 output/
    │
    ├── Phase 2: publish.py (subprocess)
    │   ├── Step 1: 提取音频 → 16kHz mono WAV
    │   ├── Step 2: 提取封面 → 原始视频首帧 JPEG
    │   ├── Step 3: Whisper 转录 (并行3workers, GPU优先/CPU备选)
    │   ├── Step 3b: 字幕验证+纠错 (T2S→去乱码→去重→上下文纠错)
    │   ├── Step 4: 生成 SRT (jieba 智能分句, ≤18字/行)
    │   ├── Step 5: 烧录字幕 (FFmpeg, 微软雅黑, 白字黑边)
    │   ├── Step 6: 上传 (B站+视频号并发, 先登先传)
    │   └── Step 7: 清理原始文件 + 记录历史
    │
    └── mark_completed() → 更新 schedule.txt 状态 + run_history.txt
```

---

## 2. 首次部署完整流程

**当你第一次接手这个项目时，严格按以下步骤操作。每一步都有验证方法。**

### 2.1 检查系统环境

```powershell
# 1. 确认 Conda 已安装
conda --version
# 预期: conda 24.x 或更高

# 2. 获取 Conda base 路径 (后续需要用)
conda info --base
# 预期: 类似 D:\ProgramData\anaconda3 或 C:\Users\xxx\miniconda3

# 3. 记录项目根目录
# 你需要知道 PaperTalker-CLI 项目的绝对路径
# 例如: D:\OneDrive\Desktop\UCAS\PaperTalker-CLI
```

**记录这两个关键路径：**
- `PROJECT_ROOT` = 项目根目录绝对路径
- `PYTHON_PATH` = `<conda_base>/envs/papertalker/python.exe` (Windows) 或 `<conda_base>/envs/papertalker/bin/python` (macOS/Linux)

### 2.2 安装依赖

```powershell
cd "<PROJECT_ROOT>"

# 方式 A: 一键安装 (推荐)
.\setup\setup.bat    # Windows
# ./setup/setup.sh   # macOS/Linux

# 方式 B: 手动安装 (如果一键失败)
conda create -n papertalker python=3.11 -y
conda activate papertalker
pip install -e deps/notebooklm-py
pip install python-dotenv httpx rich playwright
python -m playwright install chromium
pip install imageio-ffmpeg faster-whisper jieba "biliup>=1.1.29" qrcode
```

### 2.3 验证依赖

```powershell
$env:PYTHONIOENCODING='utf-8'
& "<PYTHON_PATH>" -u tools/verify.py
```

预期输出：每个依赖显示 `ok`。如果有 `MISS`，按提示安装。

### 2.4 配置代理

```powershell
# 复制模板
Copy-Item ".env.example" ".env"

# 编辑 .env，填入代理地址 (访问 Google 必须)
# HTTP_PROXY=http://127.0.0.1:7897
# HTTPS_PROXY=http://127.0.0.1:7897
```

### 2.5 首次认证测试

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUNBUFFERED='1'
& "<PYTHON_PATH>" -u quick_video.py "测试" --check
```

- 如果 NotebookLM 认证过期：脚本会自动弹出浏览器，用户完成 Google 登录
- 成功后显示 `✅ 预检通过，NotebookLM 已就绪`

### 2.6 安装 Skills

```powershell
# 找到你的 OpenClaw skills 目录
# 通常是: ~/.agents/skills/ 或 $env:USERPROFILE\.agents\skills\

# Windows:
xcopy "<PROJECT_ROOT>\skills\paper-talker" "$env:USERPROFILE\.agents\skills\paper-talker\" /E /I /Y
xcopy "<PROJECT_ROOT>\skills\literature-review" "$env:USERPROFILE\.agents\skills\literature-review\" /E /I /Y

# macOS/Linux:
# cp -r <PROJECT_ROOT>/skills/paper-talker ~/.agents/skills/
# cp -r <PROJECT_ROOT>/skills/literature-review ~/.agents/skills/
```

验证：技能应出现在你的 `<available_skills>` 列表中。

### 2.7 注册 Cron 定时任务

**这是最关键的步骤。** 注册以下 3 个 cron 任务。

**注意：下面命令中的 `<PROJECT_ROOT>` 和 `<PYTHON_PATH>` 需要替换为你的实际路径。**

#### Cron 1: 每周趋势调研 (周日 17:00)

```bash
openclaw cron add \
  --name "PaperTalker Weekly Tracker" \
  --cron "0 17 * * 0" \
  --session isolated \
  --message "Run weekly paper trend discovery for PaperTalker-CLI.

Execute the following steps:

1. cd <PROJECT_ROOT>
2. Run: \$env:PYTHONIOENCODING='utf-8'; \$env:PYTHONUNBUFFERED='1'; & '<PYTHON_PATH>' -u auto_tracker.py --write-schedule --force
   Timeout: 10 minutes. Be patient, it searches multiple academic databases.
3. After completion, read schedule.txt
4. Report to user via message:
   '📚 本周论文趋势调研完成，已安排以下主题：
   - [日期] [主题] (来源: [领域])
   - ...
   如需修改请回复。'

If auto_tracker fails, report the error to user."
```

#### Cron 2: 每天日程预告 (17:00)

```bash
openclaw cron add \
  --name "PaperTalker Daily Preview" \
  --cron "0 17 * * *" \
  --session isolated \
  --message "Check tomorrow's PaperTalker schedule and notify user.

Steps:
1. Read <PROJECT_ROOT>/schedule.txt
2. Calculate tomorrow's date (YYYY-MM-DD)
3. Search for: a) exact date match with status=pending, OR b) first 'queue' entry with status=pending
4. Send message to user:
   If found: '📋 明天的 PaperTalker 日程：[topic]，来源模式：[source_mode]，将于明早 8:30 自动执行。如需修改请回复。'
   If not found: '📋 明天没有待处理的 PaperTalker 主题。需要我运行趋势调研发现新主题吗？'

IMPORTANT: This is a notification task. Do NOT execute the pipeline."
```

#### Cron 3: 每天执行流水线 (08:30)

```bash
openclaw cron add \
  --name "PaperTalker Daily Pipeline" \
  --cron "30 8 * * *" \
  --session isolated \
  --message "Run today's PaperTalker scheduled pipeline. This is a LONG-RUNNING task (40-90 minutes total). Be EXTREMELY patient.

PROJECT_ROOT=<PROJECT_ROOT>
PYTHON=<PYTHON_PATH>

--- STEP 0: Read Schedule ---
Read PROJECT_ROOT/schedule.txt
Find today's pending topic (date match > queue FIFO)
If no pending topic: notify user '今天没有待处理的 PaperTalker 主题' and stop.
Set TOPIC = the topic text

--- STEP 1: Connectivity Check (max 4 minutes) ---
cd PROJECT_ROOT
\$env:PYTHONIOENCODING='utf-8'; \$env:PYTHONUNBUFFERED='1'
& PYTHON -u quick_video.py TOPIC --check
If exit code != 0: STOP. Notify user of error. Do NOT proceed.
If auto-login triggered (browser popup): wait for user to complete Google login.

--- STEP 2: Generate Video (max 60 minutes!) ---
& PYTHON -u quick_video.py TOPIC --no-confirm
Run in BACKGROUND. Poll every 2 minutes for output.
⚠️ CRITICAL:
- Record NID (笔记本 ID, printed after '笔记本:') and TID (视频任务 ID, printed after '视频任务:')
- Deep Research: 5-20 min — DO NOT INTERRUPT
- Source import: 5-20 min — DO NOT INTERRUPT (may seem stuck, it's adding URLs one by one)
- Source processing wait: 1-5 min
- Video generation: 10-30+ min — status will show 'in_progress' or 'pending', both are normal
- Total Phase 1: 30-60+ minutes. THIS IS NORMAL.
If network error mid-generation:
  1. Wait 2-3 minutes
  2. Resume: & PYTHON -u quick_video.py TOPIC --resume NID TID
  3. NEVER create a new notebook — the task continues on Google's servers

--- STEP 3: Subtitle + Upload (max 30 minutes) ---
& PYTHON -u publish.py --platforms bilibili weixin_channels
Run in BACKGROUND. Poll every 1 minute.
- Transcription: 5-15 min (GPU faster, CPU slower)
- Subtitle burn: 1-3 min
- Upload: 3-10 min per platform
If B站 QR needed: terminal displays QR, user scans with B站 App
If 视频号 QR needed: browser popup, user scans with WeChat

--- STEP 4: Report Results ---
Notify user with results:
  '✅ PaperTalker 今日任务完成！
  主题：[topic]
  时长：[duration]
  字幕：[count] 条
  B站：[BV号 or 失败原因]
  视频号：[成功/失败]
  文件：output_subtitled/[date]/[topic].mp4'

Update schedule.txt: change status to 'completed' with timestamp, or 'failed' with notes.

--- ERROR RECOVERY ---
Phase 1 network fail → --resume NID TID (NEVER recreate notebook)
Phase 1 auth fail → notify user to re-login, mark failed
Phase 2 upload fail → can retry: & PYTHON -u publish.py
Phase 2 transcribe fail → can retry: & PYTHON -u src/transcribe.py <video_path>"
```

### 2.8 验证 Cron 注册

```bash
openclaw cron list
```

应看到 3 个 PaperTalker 相关的 cron 任务，状态为 `idle` 或 `ok`。

### 2.9 首次测试运行

建议首次部署后立即做一次手动测试：

```powershell
# 小规模测试 (用 search 模式，更快)
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUNBUFFERED='1'
& "<PYTHON_PATH>" -u quick_video.py "基因编辑" --no-confirm --source search --max-results 3

# 然后测试 publish
& "<PYTHON_PATH>" -u publish.py --platforms bilibili
```

成功后，记录经验到你的 MEMORY.md：
- 环境路径
- 遇到的问题和解决方法
- 认证状态
- 首次测试的 BV 号

---

## 3. 跨平台适配 (Windows / macOS / Linux)

### 3.1 平台差异总览

| 组件 | Windows | macOS | Linux |
|------|---------|-------|-------|
| Python 路径 | `<conda_base>\envs\papertalker\python.exe` | `<conda_base>/envs/papertalker/bin/python` | 同 macOS |
| Shell | PowerShell (`;` 分隔命令) | bash/zsh (`&&` 或 `;`) | bash |
| 安装脚本 | `setup\setup.bat` | `./setup/setup.sh` | 同 macOS |
| biliup 二进制 | `vendor/biliup.exe` | `vendor/biliup-macos` | `vendor/biliup` |
| 编码修复 | 需要 `PYTHONIOENCODING=utf-8` | 通常不需要 | 通常不需要 |
| Conda 激活 | `conda activate papertalker` | `conda activate papertalker` | 同 macOS |
| FFmpeg | `pip install imageio-ffmpeg` | 同左，或 `brew install ffmpeg` | 同左，或 `apt install ffmpeg` |

### 3.2 macOS 特殊说明

**biliup 配置：**
```bash
# 检查 vendor/ 下是否有 biliup-macos
ls vendor/biliup-macos

# 如果不存在，从压缩包解压
cd vendor
tar -xf biliupR-v1.1.29-x86_64-macos.tar.xz
mv biliupR-v1.1.29-x86_64-macos/biliup biliup-macos
chmod +x biliup-macos

# 如果 macOS 阻止运行 (未签名)
xattr -d com.apple.quarantine biliup-macos
# 或在 系统偏好设置 → 安全性与隐私 → 允许运行
```

**Playwright 浏览器：**
```bash
# macOS 上 Chromium 可能需要额外权限
python -m playwright install chromium
# 如果报权限错误
xattr -cr ~/Library/Caches/ms-playwright/
```

**ffmpeg：**
```bash
# 方式 A: pip (推荐，跨平台一致)
pip install imageio-ffmpeg

# 方式 B: Homebrew
brew install ffmpeg
```

### 3.3 Linux 特殊说明

```bash
# biliup
cd vendor
tar -xf biliupR-v1.1.29-x86_64-linux.tar.xz
mv biliupR-v1.1.29-x86_64-linux/biliup biliup
chmod +x biliup

# Playwright 需要系统依赖
python -m playwright install-deps
python -m playwright install chromium
```

### 3.4 平台自检

**你（Agent）在首次接手时，应自动检测并记录：**

```python
import sys, platform
print(f"OS: {platform.system()} {platform.release()}")
print(f"Python: {sys.executable}")
print(f"Platform: {'Windows' if sys.platform == 'win32' else 'macOS' if platform.system() == 'Darwin' else 'Linux'}")
```

然后根据检测结果，选择正确的命令格式（PowerShell vs bash）、biliup 路径等。

---

## 4. API 获取指南

### 4.1 API 总览

| API | 必要性 | 用途 | 获取方式 |
|-----|-------|------|---------|
| 代理 (HTTP_PROXY) | **必须** (中国大陆) | 访问 Google NotebookLM | 你的 VPN/代理服务 |
| Google 账号 | **必须** | NotebookLM 登录 | 浏览器自动认证 |
| NCBI API Key | 可选 (推荐) | PubMed 搜索提速 | 免费注册即得 |
| Semantic Scholar Key | 可选 (推荐) | 学术论文搜索提速 | 免费申请，1-3 天审批 |
| CrossRef Email | 可选 | DOI 查询进入 Polite Pool | 填邮箱即可 |
| arXiv API | 无需 Key | 预印本搜索 | 完全开放 |
| Google Scholar | 无需 Key | 综合搜索 | 通过 scholarly 库 |
| 微信公众号 API | 可选 | 发布图文 | 公众号后台获取 |

### 4.2 快速配置流程 (OpenClaw 对话式)

当用户让你配置 API 时，按以下流程引导：

**Step 1: 编辑 .env**
```bash
# 检查是否已有 .env
if [ ! -f .env ]; then cp .env.example .env; fi
```

**Step 2: 代理 (必须)**
```
用户的代理地址是什么？填入 .env 的 HTTP_PROXY 和 HTTPS_PROXY
```

**Step 3: NCBI API Key (推荐)**
```
引导用户:
1. 打开 https://www.ncbi.nlm.nih.gov/account/settings/
2. 登录/注册 NCBI 账号 (可用 Google 账号)
3. 点击 "API Key Management" → "Create an API Key"
4. 复制 Key
5. 填入 .env: NCBI_API_KEY=xxx 和 NCBI_EMAIL=用户邮箱
```

**Step 4: Semantic Scholar Key (推荐)**
```
引导用户:
1. 打开 https://www.semanticscholar.org/product/api#api-key
2. 登录 Semantic Scholar
3. 点击 "Request API Key"
4. 填写用途: "Academic video production pipeline for literature search"
5. 等待审批 (1-3天)，审批后填入 .env: SS_API_KEY=xxx
```

**Step 5: CrossRef (可选)**
```
只需在 .env 填入: CROSSREF_EMAIL=用户邮箱
无需注册，自动进入 Polite Pool
```

### 4.3 验证 API 配置

```powershell
# 验证所有配置
& "<PYTHON_PATH>" -u tools/verify.py

# 单独测试论文搜索
& "<PYTHON_PATH>" -c "
from dotenv import load_dotenv; load_dotenv('.env')
import sys; sys.path.insert(0, 'src/utils')
import asyncio
from paper_search import search_papers
results = asyncio.run(search_papers('CRISPR', platforms=['semantic_scholar'], max_results=3))
print(f'Found {len(results)} papers')
for p in results: print(f'  - {p[\"title\"][:60]}')
"
```

---

## 5. 发布可控性 (断点续传)

### 5.1 问题场景

视频已生成并加好字幕，但上传阶段失败（平台认证过期、网络问题等）。此时：
- 视频文件保存在 `output_subtitled/日期/主题.mp4` ✅
- SRT 字幕保存在 `output_subtitled/日期/主题.srt` ✅
- 上传状态记录在 `run_history.json` 中标记为 `FAIL` ❌

### 5.2 自动行为

`publish.py` 已内置保护机制：
- 上传失败时，**不会删除原始视频** (保留在 output/)
- 上传状态准确记录到 `run_history.json`
- 每次启动时显示上次运行结果供参考

### 5.3 重新上传命令

```powershell
# 重新上传所有之前失败的视频
& "<PYTHON_PATH>" -u publish.py --retry

# 重新上传到指定平台
& "<PYTHON_PATH>" -u publish.py --retry --platforms bilibili

# 单独上传特定视频
& "<PYTHON_PATH>" -u src/upload_bilibili.py output_subtitled/2026-03-14/随机过程.mp4 --title "标题" --tags "tag1,tag2"
```

### 5.4 Agent 发布流程 (带断点控制)

当你执行流水线的 Phase 2 时：

```
1. 执行 publish.py --platforms bilibili weixin_channels
2. 检查输出的 Summary 表格
3. 如果某个平台显示 FAIL:
   a. 通知用户: "视频已生成并加好字幕，但 [平台] 上传失败: [原因]。
      文件: output_subtitled/[date]/[topic].mp4
      需要登录 [平台] 后重新上传吗？"
   b. 等待用户回复
   c. 用户确认后: publish.py --retry --platforms [失败平台]
4. 如果所有平台成功: 正常汇报
```

### 5.5 Cron 中的发布失败处理

每日 08:30 cron 执行时，如果上传失败：

```
1. 不要重试整个流水线 (视频已生成!)
2. 通知用户:
   "⚠️ 今日视频已生成但部分平台上传失败
   主题: [topic]
   字幕: [count] 条
   B站: [状态]
   视频号: [状态]
   文件: output_subtitled/[date]/[topic].mp4
   
   请完成平台登录后回复"重新上传"，我会立即上传。"
3. 等用户回复后执行: publish.py --retry
```

---

## 6. Windows Python 执行规则 (极其重要!)

### 3.1 标准执行模板

**所有 Python 调用必须这样写：**

```powershell
# PowerShell (OpenClaw 默认 shell)
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUNBUFFERED='1'
& "<PYTHON_PATH>" -u <script.py> [args...]
```

```bash
# Bash (Git Bash / WSL / macOS / Linux)
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 "<PYTHON_PATH>" -u <script.py> [args...]
```

### 3.2 绝对禁止

| ❌ 禁止 | 原因 | ✅ 正确做法 |
|---------|------|-----------|
| `conda run -n papertalker python script.py` | GBK 编码崩溃 (Windows) | 直接使用 Python 绝对路径 |
| 不设置 `PYTHONUNBUFFERED=1` | 输出全缓冲，看起来像卡死 (0 bytes) | 始终设置 |
| 不设置 `PYTHONIOENCODING=utf-8` | 中文输出乱码 | 始终设置 |
| PowerShell 中用 `&&` 连接命令 | PowerShell 不支持 (ParseError) | 用 `;` 分隔 |

### 3.3 长时间脚本执行

对于超过 1 分钟的脚本，使用后台执行 + 轮询：

```
1. 用 exec(background=true, timeout=3600000) 启动
2. 用 process(action=poll, timeout=120000) 定期检查
3. 不要频繁轮询 — 每次 poll 等 60-120 秒
4. 看到 "Process exited with code 0" 才是真正完成
```

---

## 7. 日常操作详解

### 4.1 耐心等待规则 (最重要的规则!)

**你必须对以下步骤保持足够的耐心。绝不能提前中断或超时。**

| 阶段 | 预计耗时 | 你应设的超时 | 说明 |
|------|---------|-------------|------|
| Deep Research | 5-20 分钟 | 40 分钟 | 轮询状态 `in_progress`，sources 从 0 慢慢增长 |
| 来源导入 | 5-20 分钟 | 30 分钟 | 逐个添加 URL，失败的自动跳过（每个最多 45s） |
| 来源处理 | 1-5 分钟 | 5 分钟 | 固定等待，显示 "等待中... N/Xs" |
| 视频生成 | 10-30+ 分钟 | 60 分钟 | 状态交替 `in_progress`/`pending`，这是正常的 |
| Whisper 转录 | 5-15 分钟 | 20 分钟 | GPU 快 (~5min)，CPU 慢 (~15min) |
| 字幕烧录 | 1-3 分钟 | 5 分钟 | FFmpeg 处理 |
| 平台上传 | 3-10 分钟 | 15 分钟 | B站+视频号并发 |

**总计一次完整流水线：40-90 分钟。这是正常的。**

### 4.2 完整流水线执行模板

当你需要执行完整流水线时（无论是 cron 触发还是用户手动要求），严格按以下步骤：

```
=== Phase 0: 连通性检查 ===
命令: & PYTHON -u quick_video.py "TOPIC" --check
超时: 4 分钟
成功: exit code 0, 显示 "预检通过"
失败: 停止，通知用户

=== Phase 1: 视频生成 ===
命令: & PYTHON -u quick_video.py "TOPIC" --no-confirm
超时: 60 分钟 (后台运行)
关键: 从输出中记录 NID 和 TID
  - NID 在 "笔记本: XXXXXXXX" 后面
  - TID 在 "视频任务: XXXXXXXX" 后面
成功: 显示 "全部完成" + 视频路径
失败恢复:
  - 网络错误 → 等 2-3 分钟 → --resume NID TID
  - 认证错误 → 通知用户重新登录
  - 来源过多导致 failed → 重试用 --max-results 5

=== Phase 2: 字幕 + 上传 ===
命令: & PYTHON -u publish.py --platforms bilibili weixin_channels
超时: 30 分钟 (后台运行)
成功: Summary 表格显示 ok
失败恢复:
  - 上传失败 → 单独重试 publish.py
  - 转录失败 → 单独重试 src/transcribe.py

=== Phase 3: 汇报结果 ===
通知用户: 主题、时长、字幕数、BV号、视频号状态、文件路径
更新 schedule.txt: completed/failed + 时间戳
```

### 4.3 错误恢复手册

| 错误场景 | 恢复方法 | 注意事项 |
|---------|---------|---------|
| 网络中断 (Phase 1) | `--resume NID TID` | **绝不重建笔记本**。等 2-3 分钟再恢复 |
| NotebookLM 认证过期 | `quick_video.py --check` 自动触发重新登录 | 用户需在浏览器完成 Google 登录 |
| Deep Research 被限流 | 自动降级到 Fast Research | 或换 Google 账号 |
| B站 cookies 过期 | `publish.py` 自动展示终端 QR | 用户用 B站 App 扫码 |
| 微信视频号过期 | `publish.py` 自动弹浏览器 | 用户微信扫码 |
| 视频生成 `failed` | 来源过多，用 `--max-results 5` 重试 | 减少来源数量 |
| Whisper GPU 崩溃 | 自动 fallback 到 CPU small 模型 | publish.py 已处理 |
| biliup 版本过低 | `pip install "biliup>=1.1.29"` | 低版本被 B站 封禁 |
| Playwright chromium 过旧 | `python -m playwright install chromium` | 版本不匹配会报错 |

### 4.4 schedule.txt 格式详解

Tab 分隔 (TSV)，每行一个主题：

```
# Columns: date	topic	source_mode	platforms	max_results	status	completed_at	notes
2026-03-15	空间转录组+AI	research	bilibili,weixin_channels	5	pending		auto_tracker
queue	单细胞测序	research	bilibili,weixin_channels	5	pending
queue	LLM Agent	research	bilibili,weixin_channels	5	pending
```

| 字段 | 合法值 | 说明 |
|------|-------|------|
| date | `YYYY-MM-DD` 或 `queue` | 日期条目优先于 queue |
| topic | 任意文本 | 视频主题（中英文均可） |
| source_mode | `research` / `search` / `file` / `paper` / `upload` / `mixed` | 来源获取方式 |
| platforms | 逗号分隔: `bilibili,weixin_channels,weixin_article` | 发布平台 |
| max_results | 1-50 | 论文搜索每平台结果数 |
| status | `pending` / `completed` / `failed` | 执行完自动更新 |
| completed_at | ISO 时间戳 | 自动填写 |
| notes | 自由文本 | `auto_tracker` = 自动发现的主题 |

**选题优先级：** 日期精确匹配 > queue 中第一个 pending

### 4.5 auto_tracker.py 论文趋势调研

```powershell
# 只报告 (不写入)
& "<PYTHON_PATH>" -u auto_tracker.py

# 写入 schedule.txt (分配到未来 7 天的日期)
& "<PYTHON_PATH>" -u auto_tracker.py --write-schedule

# 强制运行 (忽略 6 天冷却期)
& "<PYTHON_PATH>" -u auto_tracker.py --write-schedule --force

# 查看排期状态
& "<PYTHON_PATH>" -u auto_tracker.py --status

# 指定搜索领域 (0=肿瘤+AI, 1=肠道+AI, 2=单细胞+AI, 3=空间转录组+AI)
& "<PYTHON_PATH>" -u auto_tracker.py --domains 0,2
```

跟踪领域 (生物医学 + AI 交叉):
- 0: 肿瘤+AI (tumor cancer AI deep learning)
- 1: 肠道+AI (gut microbiome AI machine learning)
- 2: 单细胞+AI (single-cell RNA-seq AI deep learning)
- 3: 空间转录组+AI (spatial transcriptomics AI machine learning)

行为规则:
- 6 天冷却期 (`--force` 跳过)
- 搜索高引用论文，按引用数排序
- 将发现的主题分配为日期条目 (每天一个)
- 跳过已有用户指定主题的日期 (用户优先)
- source_mode 固定为 `research` (NotebookLM Deep Research)
- 运行记录保存在 `tracker_history.txt`

---

## 8. 字幕纠错系统

字幕流水线包含**多层纠错**，从底层到高层依次处理：

### 5.1 纠错流水线

```
Whisper 原始输出 (139 segments)
    ↓ Pass 1: 繁体→简体转换 (T2S)
    ↓ Pass 2: 去除乱码 (box-drawing, 重复字符, 长拉丁序列)
    ↓ Pass 3: 去除重复段 (完全相同 + 包含关系)
    ↓ Pass 4: 修复时间戳 (负时长, 重叠, 间隙)
    ↓ Pass 5: 去除过短段 (<0.1s 且 ≤1字)
    ↓ Pass 6: 上下文纠错 (同音字/学术术语纠正)  ← 新增
    ↓ Pass 7: 去除填充词/幻觉 (嗯、谢谢观看...)  ← 新增
    ↓ Pass 8: 合并孤立碎片 (≤2字, <0.5s)          ← 新增
    ↓
验证后字幕 → jieba 智能分句 → SRT 文件
```

### 5.2 上下文纠错原理

Whisper 在转录学术中文时，常产生**同音错字**（phonetically correct but semantically wrong）。例如：

| Whisper 输出 | 正确 | 原因 |
|-------------|------|------|
| 积因组学 | 基因组学 | 同音 jī yīn |
| 深度血习 | 深度学习 | 同音 xué xí |
| 单白质 | 蛋白质 | 近音 dàn/dān |
| 神经往络 | 神经网络 | 同音 wǎng luò |
| 随即过程 | 随机过程 | 同音 jī/jí |
| 概律 | 概率 | 同音 lǜ/lǜ |
| 正太分布 | 正态分布 | 同音 tài/tài |

纠错策略：
1. **维护同音错字词典** (100+ 条学术术语映射)
2. **上下文窗口** = 前一段 + 当前段 + 后一段
3. **学术环境检测** = 上下文中是否包含学术关键词（研究、论文、算法...）
4. **保守策略** = 在学术上下文中直接修正；非学术上下文中，只在正确词也出现在上下文时才修正

代码位置：`src/transcribe.py` → `_context_aware_correction()` 函数

### 5.3 幻觉检测

Whisper 有时会在音频静默处幻觉出不存在的内容：
- 填充词：嗯嗯嗯、啊啊啊
- 结尾卡片：谢谢观看、请订阅
- 纯符号：.....、*****

这些会被 `_FILLER_PATTERNS` 正则匹配并自动移除。

### 5.4 碎片合并

短碎片（≤2字, <0.5s）通常是 Whisper 断句错误。系统会根据时间间隙（<0.3s）将碎片合并到相邻的前一段或后一段。

---

## 9. 命令参考

### 6.1 quick_video.py — Phase 1

```powershell
# 默认 Deep Research
& "<PYTHON_PATH>" -u quick_video.py "主题" --no-confirm

# 连通性检查
& "<PYTHON_PATH>" -u quick_video.py "主题" --check

# 论文检索
& "<PYTHON_PATH>" -u quick_video.py "主题" --source search --platforms arxiv semantic_scholar --year 2025

# 本地文件
& "<PYTHON_PATH>" -u quick_video.py "主题" --source file --files paper.pdf

# 混合模式
& "<PYTHON_PATH>" -u quick_video.py "主题" --source mixed

# 恢复超时
& "<PYTHON_PATH>" -u quick_video.py "主题" --resume NID TID

# 生成+自动发布
& "<PYTHON_PATH>" -u quick_video.py "主题" --no-confirm --publish bilibili weixin_channels
```

| 参数 | 默认 | 说明 |
|------|-----|------|
| `topic` | (必填) | 视频主题 |
| `--check` | false | 仅检查连通性 |
| `--source` | `research` | research/search/upload/mixed/file/paper |
| `--style` | `whiteboard` | 9种视频风格 |
| `--mode` | `deep` | Research 深度: fast/deep |
| `--platforms` | `arxiv semantic_scholar` | 搜索平台 |
| `--max-results` | `10` | 每平台结果数 |
| `--year` | 无 | 论文年份筛选 |
| `--no-confirm` | false | 跳过确认 (**cron必须加**) |
| `--resume NID TID` | 无 | 恢复中断任务 |
| `--publish` | 无 | 生成后自动发布 |
| `--timeout` | `3600` | 超时秒数 |

### 6.2 publish.py — Phase 2

```powershell
& "<PYTHON_PATH>" -u publish.py
& "<PYTHON_PATH>" -u publish.py --platforms bilibili weixin_channels
& "<PYTHON_PATH>" -u publish.py --skip-upload
& "<PYTHON_PATH>" -u publish.py --workers 3
```

### 6.3 独立模块

```powershell
& "<PYTHON_PATH>" -u src/transcribe.py video.mp4              # 仅转录
& "<PYTHON_PATH>" -u src/subtitle.py video.mp4 subtitles.srt  # 仅烧录
& "<PYTHON_PATH>" -u src/upload_bilibili.py video.mp4 --title "标题" --tags "t1,t2"
& "<PYTHON_PATH>" -u src/upload_weixin.py video.mp4 --title "标题"
```

---

## 10. 已知问题速查

| 问题 | 解决 |
|------|------|
| Python 输出空 (0 bytes) | `PYTHONUNBUFFERED=1` + `-u` |
| `conda run` GBK 崩溃 | 直接 Python 路径 + `PYTHONIOENCODING=utf-8` |
| PowerShell `&&` 报错 | 用 `;` 分隔命令 |
| FFmpeg Windows 路径 | 脚本内部自动转义 |
| CUDA 崩溃 | publish.py 已用子进程隔离 |
| MKL 内存错误 | 自动设 `MKL_THREADING_LAYER=sequential` |
| 批量导入失败 | 自动降级: 15批→5批→逐个(45s超时) |
| 网络中断 | `--resume NID TID`，**不要重建笔记本** |
| B站 tag 格式 | 脚本内部已处理为逗号字符串 |
| 视频号标题<6字 | 自动补 "—视频解读" |
| Playwright 版本 | `python -m playwright install chromium` |
| 中文搜索0结果 | 自动翻译英文 (~60术语映射) |
| biliup<1.0 被封 | `pip install "biliup>=1.1.29"` |

---

## 11. 反馈和通知

### 8.1 执行结果通知

每次流水线执行完成后，你应该通过你的消息渠道（飞书、Telegram、Discord 等）通知用户。

**成功模板：**
```
✅ PaperTalker 今日任务完成！
📹 主题：随机过程
⏱ 时长：8:36
📝 字幕：226 条 (纠错: 3 处同音修正, 1 处碎片合并)
🅱️ B站：BV1bZw4zLEJf
📱 视频号：已发布
📁 文件：output_subtitled/2026-03-14/随机过程.mp4
```

**失败模板：**
```
❌ PaperTalker 今日任务失败
📹 主题：随机过程
💥 失败阶段：Phase 1 视频生成
📋 错误：网络连续断开 10 次
🔧 建议：检查代理是否正常，稍后用 --resume 恢复
📎 NID: d345c7e4-...  TID: 9832932f-...
```

### 8.2 日程预告通知

每天 17:00 发送：
```
📋 明天的 PaperTalker 日程
主题：空间转录组+AI
模式：research (Deep Research)
平台：B站 + 视频号
执行时间：明早 08:30
如需修改请回复。
```

### 8.3 趋势调研通知

每周日 17:00 发送：
```
📚 本周论文趋势调研完成
已安排以下主题：
- 3/16(周一): 单细胞+AI: xxx论文标题 [citations: 42]
- 3/17(周二): 空间转录组+AI: yyy论文标题 [citations: 35]
- 3/18(周三): 肿瘤+AI: zzz论文标题 [citations: 28]
...
如需修改请回复。
```

---

## 12. Agent 自学和经验积累

### 9.1 首次接手时

1. 阅读本文档 (OPENCLAW.md)
2. 执行 §2 首次部署流程
3. 记录你的环境特定信息到 MEMORY.md:
   - 项目路径、Python 路径
   - 遇到的安装问题和解决方法
   - 首次测试结果

### 9.2 日常积累

每次遇到新问题时：
1. **诊断问题** (看错误输出)
2. **尝试解决** (查看 §7 已知问题)
3. **记录到 MEMORY.md** (问题 + 解决方案)
4. **如果是通用问题**：更新本文档的 §7 已知问题表

### 9.3 经验传承格式

在你的 MEMORY.md 中记录：
```markdown
## PaperTalker-CLI 经验

### 环境
- PROJECT_ROOT: /path/to/PaperTalker-CLI
- PYTHON_PATH: /path/to/envs/papertalker/python
- OS: Windows 11 / macOS 14 / Ubuntu 24.04
- GPU: NVIDIA RTX 4090 / 无GPU

### 遇到的问题
- [日期] 问题描述 → 解决方案
- [日期] ...

### 运行统计
- 首次测试: [日期], 主题 [xxx], BV号 [BVxxx]
- 成功率: xx/xx
```

---

## 13. 扩展和自定义

### 10.1 修改视频内容风格

编辑 `video.md`（提示词）。默认：简体中文、严格引用数据、高信息密度、面向研究生。

### 10.2 添加跟踪领域

编辑 `auto_tracker.py` 中的 `DOMAINS` 列表。

### 10.3 修改 Cron 时间

```bash
openclaw cron list              # 查看所有 cron
openclaw cron rm <ID>           # 删除旧的
openclaw cron add ...           # 重新注册新时间
```

### 10.4 添加新平台

1. 创建 `src/upload_<platform>.py`
2. 在 `publish.py` 中添加逻辑
3. 在 `schedule.txt` platforms 列中使用

---

## 14. 快速诊断

```powershell
# 1. 检查依赖
& "<PYTHON_PATH>" -u tools/verify.py

# 2. 检查 NotebookLM
& "<PYTHON_PATH>" -u quick_video.py "test" --check

# 3. 检查排期
Get-Content "<PROJECT_ROOT>/schedule.txt"

# 4. 检查历史
Get-Content "<PROJECT_ROOT>/run_history.txt"

# 5. 检查 tracker
Get-Content "<PROJECT_ROOT>/tracker_history.txt"

# 6. 测试 tracker (干跑)
& "<PYTHON_PATH>" -u auto_tracker.py --days 7 --top 3

# 7. 测试流水线 (干跑)
& "<PYTHON_PATH>" -u run_scheduled.py --dry-run
```

---

## 15. 完整端到端示例

```
[用户] 帮我生成一个关于"随机过程"的视频，发到B站和视频号

[Agent 操作流程]

1. 进入项目目录
   cd D:/OneDrive/Desktop/UCAS/PaperTalker-CLI

2. Step 0: 连通性检查 (后台, 4分钟超时)
   → ✓ NotebookLM 连接成功

3. Step 1: 生成视频 (后台, 60分钟超时)
   → [1/7] 创建笔记本: d345c7e4-...
   → [2/7] Deep Research 启动
   → [3/7] 等待完成 (~5min)... 72 个来源
   → [4/7] 导入来源 (~15min)... 66 个成功
   → [5/7] 来源处理 (~3min)
   → [6/7] 视频生成 (~16min)
   → [7/7] 下载: output/随机过程_20260314_225610.mp4

4. Step 2: 字幕+上传 (后台, 30分钟超时)
   → [1/7] 提取音频
   → [2/7] 提取封面
   → [3/7] 转录 (139段, 8:36)
   → [3b] 纠错: 2处同音修正, 1处碎片合并
   → [4/7] SRT (226字幕)
   → [5/7] 烧录字幕
   → [6/7] B站 BV1bZw4zLEJf ✓ | 视频号 ✓
   → [7/7] 清理

5. 通知用户:
   ✅ "随机过程"视频完成！
   时长8:36, 226字幕, B站BV1bZw4zLEJf, 视频号已发布
```

---

## 16. TODO

### 高优先级
- [ ] PubMed/bioRxiv 搜索源
- [ ] 引用趋势检测 (本周 vs 上周)
- [ ] 失败自动重试 (第二天)

### 中优先级
- [ ] AI 封面图
- [ ] NotebookLM 多账号轮换
- [ ] 抖音/小红书上传器
- [ ] 排期 Web UI

### 低优先级
- [ ] GPU 内存管理
- [ ] 批量模式
- [ ] 标题 A/B 测试

---

*本文档由 OpenClaw Agent 生成和维护。最后更新: 2026-03-14*