# PaperTalker-CLI

研究主题 → 学术科普视频 → 字幕 → 多平台发布，全程对话 Claude 完成。

| 主题                            | 时长 | 字幕 | B站                                                      |
| ------------------------------- | ---- | ---- | -------------------------------------------------------- |
| Agent多智能体编排               | 9:35 | 290  | [BV1teNgzBEMH](https://www.bilibili.com/video/BV1teNgzBEMH) |
| 虚拟细胞                        | 9:39 | 295  | [BV1wjAfztECV](https://www.bilibili.com/video/BV1wjAfztECV) |
| BiOmics：AI生物侦探二人组       | 8:50 | 248  | [BV1fMPwz8EqU](https://www.bilibili.com/video/BV1fMPwz8EqU) |
| SpatialData：空间组学的通用框架 | 7:42 | 231  | [BV1mgPczuEN9](https://www.bilibili.com/video/BV1mgPczuEN9) |
| 多组学整合                      | 9:13 | 254  | [BV19KPTzKEdo](https://www.bilibili.com/video/BV19KPTzKEdo) |

## 前提条件

| 必需                                                       | 说明                                                            |
| ---------------------------------------------------------- | --------------------------------------------------------------- |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | Anthropic 官方 CLI，本项目的交互入口                            |
| 代理                                                       | HTTP 代理地址（如 `http://127.0.0.1:7897`），访问 Google 必须 |
| Google 账号                                                | 登录 NotebookLM，Pro可用次数更多                                |

| 可选              | 说明                                        |
| ----------------- | ------------------------------------------- |
| B站账号           | 上传B站需要，不上传可跳过                   |
| 微信视频号        | 上传视频号需要，首次扫码登录                |
| 微信公众号        | 发布图文需要 APPID/APPSECRET（`.env`）    |
| NVIDIA GPU + CUDA | faster-whisper 转录加速，无 GPU 用 CPU 也行 |

## 快速开始

两种方式任选其一。

### 方式 A：对话 Claude（推荐）

在任意终端打开 Claude Code，把下面这段话**整段粘贴**发送：

> 帮我克隆并安装 PaperTalker-CLI 项目：
>
> 1. git clone https://github.com/HorizonGazer/PaperTalker-CLI.git
> 2. 运行一键安装脚本
> 3. 把 .env.example 复制为 .env，代理地址填 `你的代理地址`
> 4. 帮我登录 NotebookLM
> 5. 安装 skill 到 ~/.claude/skills/paper-talker

Claude 会依次执行。**之后所有操作都只需对话：**

| 你想做什么     | 对 Claude 说                                                                            |
| -------------- | --------------------------------------------------------------------------------------- |
| 生成视频       | `帮我做一个关于「量子计算」的学术科普视频`                                            |
| 生成 + 上传B站 | `帮我生成元胞自动机视频，最后添加字幕发表在B站`                                       |
| 生成 + 多平台  | `帮我生成元胞自动机视频，自动登录notebooklm并进行搜索，最后添加字幕发表在B站和视频号` |
| 指定风格       | `做一个蛋白质折叠的视频，用动漫风格`                                                  |
| 本地文件解读   | `帮我解读这篇论文 paper.pdf，生成视频，`                                              |
| 论文标题搜索   | `搜索 Attention is All You Need 这篇论文，生成解读视频`                               |
| 论文检索模式   | `用论文检索模式，主题 AlphaFold3，只搜 arxiv 和 pubmed，限 2025 年以后`               |
| 手动上传来源   | `我想手动上传几篇 PDF 作为来源，路径在your path，主题是脑机接口`                      |
| 混合模式       | `混合模式：先 Deep Research 再补充论文，主题是 LLM 药物发现`                          |
| 只配字幕       | `帮我把 output 里的视频加字幕，不上传`                                                |
| 字幕 + 上传    | `output 文件夹里有视频了，帮我配字幕上传B站`                                          |
| 定时任务       | `帮我设置每天9点自动生成视频` / `看看 schedule.txt 里排了什么`                      |
| 检查环境       | `帮我检查依赖是否安装完整`                                                            |
| 认证过期       | `NotebookLM 认证过期了，帮我自动认证`                                                 |
| 视频超时       | `视频生成超时了，帮我恢复`                                                            |
| 上传失败       | `上传B站失败了，帮我看看什么原因`                                                     |
| 登录B站        | `帮我登录B站`                                                                         |
| 自定义提示词   | `帮我修改视频生成提示词，改成英文输出，面向本科生`                                    |

视频内容由 `video.md` 控制，默认：简体中文、严格引用数据、高信息密度、面向研究者。

### 方式 B：纯命令行

```bash
# ── 安装 ──
git clone https://github.com/HorizonGazer/PaperTalker-CLI.git
cd PaperTalker-CLI
setup\setup.bat                    # Windows（macOS/Linux: ./setup/setup.sh）
cp .env.example .env               # 编辑 .env 填入代理地址

# ── 认证 ──
conda activate papertalker
notebooklm login                   # 浏览器登录 Google → 回终端按 Enter
cd vendor && ./biliup.exe -u ../cookies/bilibili/account.json login  # B站扫码（可选）

# ── 生成视频 ──
python quick_video.py "量子计算"                                      # Deep Research 默认
python quick_video.py "AlphaFold3" --source search --platforms arxiv pubmed --year 2025
python quick_video.py "蛋白质折叠" --style anime --no-confirm
python quick_video.py "Transformer" --source file --files paper.pdf   # 本地文件
python quick_video.py "Attention" --source paper                      # 按论文标题搜索

# ── 字幕 + 上传 ──
python publish.py                                          # B站（默认）
python publish.py --platforms bilibili weixin_channels     # B站 + 视频号
python publish.py --platforms bilibili weixin_channels weixin_article  # 全平台
python publish.py --skip-upload                            # 只配字幕

# ── 模块化脚本（按需调用）──
python src/transcribe.py video.mp4                         # 仅转录
python src/subtitle.py video.mp4 subtitles.srt             # 仅烧录字幕
python src/upload_bilibili.py video.mp4 --title "标题" --tags "tag1,tag2"  # 仅上传B站
python src/upload_weixin.py video.mp4 --title "标题" --desc "描述"         # 仅上传视频号

# ── 定时任务 ──
python run_scheduled.py                # 运行今日排期
python run_scheduled.py --dry-run      # 预览不执行
python run_scheduled.py --force "量子计算"  # 立即执行指定主题
python setup_cron.py --execute         # 注册 OpenClaw 每日定时任务
```

---

## 工作原理

```
Phase 1: quick_video.py                  Phase 2: publish.py
┌────────────────────────┐              ┌──────────────────────────┐
│ 研究主题                │              │ output/*.mp4             │
│    ↓                   │              │    ↓                     │
│ NotebookLM             │              │ 1. 提取音频 (FFmpeg)      │
│  ├ Deep Research       │              │ 2. 提取封面 (首帧)        │
│  ├ 论文检索 (8个平台)   │              │ 3. 语音转录 (whisper)     │
│  ├ 本地文件上传        │              │ 4. 智能分句 (jieba)       │
│  ├ 论文标题搜索        │              │ 5. 烧录字幕 (FFmpeg)      │
│  ├ 手动上传            │              │ 6. 上传平台               │
│  └ 混合模式            │              │   ├ B站 (biliup API)      │
│    ↓                   │              │   ├ 微信视频号 (Playwright)│
│ 生成 + 下载 MP4        │── output/ ──→│   └ 微信公众号 (API)      │
└────────────────────────┘              │ 7. 清理 + 记录历史        │
                                        └──────────────────────────┘
         认证检查点:                       → output_subtitled/日期/主题.mp4
         ① NotebookLM (Google 登录)
         ② B站 (终端扫码 / biliup)
         ③ 微信视频号 (浏览器扫码)
```

## 仓库结构

```
PaperTalker-CLI/
├── quick_video.py              # Phase 1: 主题 → NotebookLM 视频
├── publish.py                  # Phase 2: 字幕 + 上传
├── run_scheduled.py            # 定时任务入口（Phase 1 + Phase 2）
├── setup_cron.py               # OpenClaw 定时任务注册
├── video.md                    # 视频生成提示词（可自定义）
├── schedule.txt                # 每日排期表（Tab 分隔）
├── .env.example                # 环境配置模板
├── src/                        # 源代码模块
│   ├── transcribe.py           # 独立脚本：音频转录 + SRT 生成
│   ├── subtitle.py             # 独立脚本：字幕烧录
│   ├── upload_bilibili.py      # 独立脚本：B站上传
│   ├── upload_weixin.py        # 独立脚本：微信视频号上传
│   ├── README.md               # 模块化脚本使用文档
│   ├── workers/
│   │   └── weixin_upload_worker.py  # 微信视频号上传子进程（async Playwright，legacy）
│   └── utils/
│       └── paper_search.py          # 论文搜索封装（8个学术平台）
├── setup/                      # 一键安装脚本
├── tools/                      # auto_login.py（自动认证）、verify.py（依赖检查）
├── deps/                       # 本地依赖：notebooklm-py、paper-search-mcp
├── cookies/bilibili/           # B站登录凭证 (gitignored)
├── cookies/weixin/             # 微信视频号认证 (gitignored)
├── vendor/                     # biliup.exe 等二进制工具 (gitignored)
├── output/                     # 原始视频（处理后自动清理）
├── output_subtitled/           # 最终成品，按日期归档：主题.mp4 + 主题.srt
├── skills/paper-talker/        # Claude Code Skill 定义 + 技术参考文档
└── CLAUDE.md                   # Claude Code 项目指引
```

## 命令参考

对话 Claude 是推荐用法。以下是底层命令，供手动调用或调试。

### quick_video.py — 生成视频

```bash
conda activate papertalker
python quick_video.py "主题"
```

| 参数                 | 默认值                     | 说明                                                                                                                 |
| -------------------- | -------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `topic`            | (必填)                     | 视频主题                                                                                                             |
| `--source`         | `research`               | `research` `search` `upload` `mixed` `file` `paper`                                                      |
| `--files`          | —                         | 本地文件/目录路径（配合 `--source file`）                                                                          |
| `--style`          | `whiteboard`             | `whiteboard` `classic` `anime` `kawaii` `watercolor` `retro_print` `heritage` `paper_craft` `auto` |
| `--platforms`      | `arxiv semantic_scholar` | 论文搜索平台（search/mixed 模式），可选：`pubmed` `biorxiv` `medrxiv` `google_scholar` `crossref` `iacr` |
| `--year`           | 无                         | 论文年份筛选                                                                                                         |
| `--max-results`    | `10`                     | 每平台最大结果数                                                                                                     |
| `--mode`           | `deep`                   | Deep Research 深度：`fast` / `deep`                                                                              |
| `--lang`           | `zh-CN`                  | 语言代码                                                                                                             |
| `--timeout`        | `1800`                   | 生成超时秒数                                                                                                         |
| `--no-confirm`     | false                      | 跳过阶段确认                                                                                                         |
| `--resume NID TID` | —                         | 恢复超时的视频任务                                                                                                   |
| `--instructions`   | `video.md`               | 自定义视频生成提示词                                                                                                 |

**来源模式说明：**

| 模式         | 说明                                               |
| ------------ | -------------------------------------------------- |
| `research` | NotebookLM Deep Research 自动搜索网络资料（默认）  |
| `search`   | 论文检索（arxiv 等 8 个学术平台）                  |
| `file`     | 本地文件（PDF/txt/md/docx），配合 `--files` 使用 |
| `paper`    | 按论文标题搜索，列出候选让用户选择                 |
| `upload`   | 打开浏览器手动上传                                 |
| `mixed`    | Deep Research + 论文检索                           |

### publish.py — 字幕 + 上传

```bash
python publish.py
```

| 参数              | 默认值                | 说明                                                                                        |
| ----------------- | --------------------- | ------------------------------------------------------------------------------------------- |
| `--skip-upload` | false                 | 只配字幕，不上传                                                                            |
| `--platforms`   | `bilibili`          | `bilibili` `weixin_channels` `weixin_article` `douyin` `xiaohongshu` `kuaishou` |
| `--input`       | `output/`           | 输入目录                                                                                    |
| `--output`      | `output_subtitled/` | 输出目录                                                                                    |

### 模块化脚本 — 按需调用

`publish.py` 是一个编排器，内部调用这些独立脚本。当你需要更细粒度的控制时，可以直接使用：

#### 1. transcribe.py - 音频转录

```bash
# 基本用法（自动检测 GPU/CPU）
python src/transcribe.py video.mp4

# 指定模型和设备
python src/transcribe.py video.mp4 --model large-v3 --device cuda

# 自定义输出
python src/transcribe.py video.mp4 -o custom.srt --keep-wav
```

#### 2. subtitle.py - 字幕烧录

```bash
# 基本用法
python src/subtitle.py video.mp4 subtitles.srt

# 自定义样式
python src/subtitle.py video.mp4 subtitles.srt --font-size 24 --style bold
```

#### 3. upload_bilibili.py - B站上传

```bash
# 基本用法
python src/upload_bilibili.py video.mp4 \
  --title "【AI科研科普】主题：前沿研究深度解读" \
  --tags "AI科研,学术科普,论文解读" \
  --cover cover.jpg

# 自动登录
python src/upload_bilibili.py video.mp4 --title "标题" --tags "tag1,tag2" --auto-login
```

#### 4. upload_weixin.py - 微信视频号上传

```bash
# 基本用法
python src/upload_weixin.py video.mp4 \
  --title "视频标题" \
  --desc "视频描述" \
  --tags "AI,科研,学术"
```

**使用场景：**
- 重新转录（使用不同模型）：`python src/transcribe.py video.mp4 --model large-v3`
- 重新上传（修改元数据）：`python src/upload_bilibili.py video.mp4 --title "新标题"`
- 仅字幕工作流：`python src/transcribe.py video.mp4 && python src/subtitle.py video.mp4 video.srt`
- 批量处理：`for video in output/*.mp4; do python src/transcribe.py "$video"; done`

详细文档：[src/README.md](src/README.md)

### 定时任务

编辑 `schedule.txt`（Tab 分隔），配置每日自动生成：

```
# 日期       主题         模式      平台                       数量  状态
2026-03-10   蛋白质折叠   search    bilibili                   5     pending
queue        单细胞测序   research  bilibili,weixin_channels   5     pending
```

- **日期行**：到期自动执行（精确匹配当天日期）
- **queue 行**：FIFO 队列，无日期匹配时顺序消费
- 执行完成后自动标记 `completed` 并记录时间戳

```bash
python run_scheduled.py                  # 运行今日排期
python run_scheduled.py --force "主题"   # 立即执行指定主题
python setup_cron.py --execute           # 注册 OpenClaw 每日定时任务
```

## 认证管理

三个独立的认证检查点，均支持缓存（首次认证后自动复用）：

| 服务       | 认证方式               | 凭证位置                             | 首次需要     |
| ---------- | ---------------------- | ------------------------------------ | ------------ |
| NotebookLM | Google 浏览器登录      | `~/.notebooklm/storage_state.json` | 手动登录     |
| B站        | 终端扫码 / biliup 弹窗 | `cookies/bilibili/account.json`    | 扫码         |
| 微信视频号 | Playwright 浏览器弹窗  | `cookies/weixin/browser_profile/`  | 微信扫码     |
| 微信公众号 | API 密钥               | `.env` (APPID/APPSECRET)           | 填写配置即可 |

## 常见问题

| 问题                 | 解决                                                                                |
| -------------------- | ----------------------------------------------------------------------------------- |
| 视频生成网络中断     | 不要重新创建 notebook，用 `--resume NID TID` 恢复轮询，任务在服务端继续运行       |
| NotebookLM 登录超时  | 确认代理开启且 `.env` 正确；或告诉 Claude `帮我自动认证`                        |
| 视频生成超时         | 通常 10-30 分钟。超时后用 `--resume` 恢复，或告诉 Claude `视频超时了，帮我恢复` |
| 上传B站失败          | 重新扫码登录 `vendor/biliup.exe login`；确认 biliup >= 1.1.29                     |
| 视频号登录检测慢     | 直接打开发布页面，微信自动跳转登录，扫码后自动跳回，0.5s 轮询检测 URL 变化          |
| 视频号上传失败       | `python -m playwright install chromium` 更新浏览器                                |
| Windows GBK 编码错误 | 不要用 `conda run`，直接 `conda activate papertalker && python ...`             |
| macOS 权限错误       | `chmod +x setup/setup.sh`                                                         |
| 自定义视频内容       | 编辑 `video.md`（默认：中文、引用数据、高信息密度、面向研究者）                   |

## 致谢

[notebooklm-py](https://github.com/srijitcoder/notebooklm-py) · [paper-search-mcp](https://github.com/paper-search/paper-search-mcp) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [biliup](https://github.com/biliup/biliup) · [Playwright](https://playwright.dev/)

## 许可证

MIT
