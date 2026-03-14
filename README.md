# PaperTalker-CLI

研究主题 → 学术科普视频 → 字幕 → 多平台发布，全程 AI Agent 自动完成。

| 主题                            | 时长 | 字幕 | B站                                                      |
| ------------------------------- | ---- | ---- | -------------------------------------------------------- |
| 随机过程                        | 8:36 | 226  | [BV1bZw4zLEJf](https://www.bilibili.com/video/BV1bZw4zLEJf) |
| Agent多智能体编排               | 9:35 | 290  | [BV1teNgzBEMH](https://www.bilibili.com/video/BV1teNgzBEMH) |
| 虚拟细胞                        | 9:39 | 295  | [BV1wjAfztECV](https://www.bilibili.com/video/BV1wjAfztECV) |
| BiOmics：AI生物侦探二人组       | 8:50 | 248  | [BV1fMPwz8EqU](https://www.bilibili.com/video/BV1fMPwz8EqU) |
| SpatialData：空间组学的通用框架 | 7:42 | 231  | [BV1mgPczuEN9](https://www.bilibili.com/video/BV1mgPczuEN9) |
| 多组学整合                      | 9:13 | 254  | [BV19KPTzKEdo](https://www.bilibili.com/video/BV19KPTzKEdo) |

## 前提条件

| 必需 | 说明 |
|------|------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 或 [OpenClaw](https://docs.openclaw.ai) | AI Agent 交互入口（二选一） |
| 代理 | HTTP 代理地址（访问 Google 必须） |
| Google 账号 | 登录 NotebookLM |

| 可选 | 说明 |
|------|------|
| B站账号 | 上传B站需要 |
| 微信视频号 | 上传视频号需要 |
| NVIDIA GPU + CUDA | Whisper 转录加速（无 GPU 用 CPU 也行） |
| NCBI / Semantic Scholar API Key | 论文搜索提速（[获取方式见 .env.example](.env.example)） |

## 快速开始

三种方式任选其一。

### 方式 A：对话 Claude Code

在终端打开 Claude Code，**整段粘贴**发送：

> 帮我克隆并安装 PaperTalker-CLI 项目：
> 1. git clone https://github.com/HorizonGazer/PaperTalker-CLI.git
> 2. 运行一键安装脚本
> 3. 把 .env.example 复制为 .env，代理地址填 `你的代理地址`
> 4. 帮我登录 NotebookLM
> 5. 安装 skill 到 ~/.claude/skills/paper-talker

之后所有操作都只需对话：

| 你想做什么 | 对 Claude 说 |
|------------|-------------|
| 生成视频 | `帮我做一个关于「量子计算」的学术科普视频` |
| 生成 + 上传 | `帮我生成元胞自动机视频，添加字幕发表在B站和视频号` |
| 指定风格 | `做一个蛋白质折叠的视频，用动漫风格` |
| 本地文件 | `帮我解读这篇论文 paper.pdf，生成视频` |
| 论文检索 | `用论文检索模式，主题 AlphaFold3，只搜 arxiv 和 pubmed` |
| 混合模式 | `混合模式：先 Deep Research 再补充论文，主题 LLM 药物发现` |
| 只配字幕 | `帮我把 output 里的视频加字幕，不上传` |
| 重新上传 | `上传失败了，帮我重新上传` |
| 定时任务 | `帮我设置每天自动生成视频` |
| 自定义提示词 | `帮我修改视频生成提示词，改成英文` |

### 方式 B：OpenClaw 全自动部署（推荐长期使用）

如果你使用 [OpenClaw](https://docs.openclaw.ai)，可以实现**全自动每日视频生产**。只需让你的 Agent 阅读 [OPENCLAW.md](OPENCLAW.md)：

```
你 → "帮我克隆并安装 PaperTalker-CLI 项目：git clone https://github.com/HorizonGazer/PaperTalker-CLI.git到我指定的路径（更改路径），阅读 OPENCLAW.md，按照文档设置好定时任务并执行一次测试"
Agent → 自动完成：环境检测 → 安装依赖 → 注册 3 个 cron → 运行测试流水线 → 汇报结果
```

**OPENCLAW.md** 是一份 1000+ 行的完整操作手册，覆盖：

| 章节 | 内容 |
|------|------|
| 首次部署 | 9 步从零搭建，每步有验证方法 |
| 跨平台 | Windows / macOS / Linux 适配指南 |
| API 配置 | 每个 API 的获取链接和步骤 |
| 定时任务 | 3 个 cron 注册命令（可直接复制） |
| 日常操作 | 执行模板 + 耐心等待规则 + 错误恢复 |
| 字幕纠错 | 87 条同音字修正 + 幻觉检测 |
| 发布可控 | 断点续传 + `--retry` 重新上传 |
| Agent 自学 | 经验积累格式 + 知识传承 |

**OpenClaw 定时任务（自动注册）：**

| 时间 | 任务 | 说明 |
|------|------|------|
| 每周日 17:00 | 论文趋势调研 | 搜索热门论文，写入下周排期 |
| 每天 17:00 | 日程预告 | 预告明天主题，等待用户确认 |
| 每天 08:30 | 执行流水线 | 生成视频 → 字幕 → 上传 → 通知 |

### 方式 C：纯命令行

```bash
# ── 安装 ──
git clone https://github.com/HorizonGazer/PaperTalker-CLI.git
cd PaperTalker-CLI
setup/setup.bat                    # Windows（macOS/Linux: ./setup/setup.sh）
cp .env.example .env               # 编辑 .env 填入代理地址和 API Keys

# ── 认证 ──
conda activate papertalker
python quick_video.py "测试" --check   # NotebookLM 登录
vendor/biliup.exe -u cookies/bilibili/account.json login  # B站（可选）

# ── 生成视频 ──
python quick_video.py "量子计算"                                      # Deep Research
python quick_video.py "AlphaFold3" --source search --year 2025       # 论文检索
python quick_video.py "蛋白质折叠" --style anime --no-confirm         # 指定风格
python quick_video.py "Transformer" --source file --files paper.pdf   # 本地文件

# ── 字幕 + 上传 ──
python publish.py --platforms bilibili weixin_channels   # 全流程
python publish.py --skip-upload                          # 只配字幕
python publish.py --retry                                # 重新上传失败的视频

# ── 定时任务 ──
python run_scheduled.py                # 运行今日排期
python auto_tracker.py --write-schedule  # 论文趋势调研
python setup_cron.py --execute         # 注册 OpenClaw 定时任务
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
│  ├ 论文检索 (8平台)     │              │ 3. 语音转录 (Whisper)     │
│  ├ 本地文件上传        │              │ 4. 字幕纠错 (上下文)      │
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
├── publish.py                  # Phase 2: 字幕 + 上传 (含 --retry 断点续传)
├── run_scheduled.py            # 每日调度入口 (Phase 1 + Phase 2)
├── auto_tracker.py             # 论文趋势发现 → 写入排期
├── setup_cron.py               # OpenClaw 定时任务注册
├── schedule.txt                # 每日排期表 (Tab 分隔)
├── video.md                    # 视频生成提示词（可自定义）
├── .env.example                # 环境配置模板（含 API 获取说明）
├── CLAUDE.md                   # Claude Code 项目指引
├── OPENCLAW.md                 # OpenClaw Agent 完整操作手册 (1000+ 行)
├── src/                        # 源代码模块
│   ├── transcribe.py           # 音频转录 + SRT + 上下文纠错
│   ├── subtitle.py             # 字幕烧录
│   ├── upload_bilibili.py      # B站上传
│   ├── upload_weixin.py        # 微信视频号上传
│   └── utils/paper_search.py   # 论文搜索封装 (8 平台)
├── skills/
│   ├── paper-talker/           # 流水线 Skill 定义
│   └── literature-review/      # 论文搜索 Skill
├── setup/                      # 一键安装 (Windows + macOS/Linux)
├── tools/                      # auto_login.py, verify.py
├── deps/                       # notebooklm-py (本地可编辑)
├── vendor/                     # biliup 二进制 (gitignored)
├── cookies/                    # 平台认证 (gitignored)
├── output/                     # 原始视频 (自动清理)
└── output_subtitled/           # 最终成品 (按日期归档)
```

## API 配置

所有 API Key 均为**可选**。没有 Key 也能运行，有 Key 可提高搜索质量和速率。

| API | 用途 | 获取方式 |
|-----|------|---------|
| 代理 (HTTP_PROXY) | 访问 Google | 你的 VPN/代理 |
| NCBI API Key | PubMed 搜索提速 | [NCBI Settings](https://www.ncbi.nlm.nih.gov/account/settings/) → API Key Management |
| Semantic Scholar | 学术论文搜索提速 | [S2 API](https://www.semanticscholar.org/product/api#api-key) → Request Key (1-3天审批) |
| CrossRef | DOI 查询提速 | 填邮箱即进入 Polite Pool |
| arXiv | 预印本搜索 | 无需 Key |
| 微信公众号 | 发布图文 | [公众号后台](https://mp.weixin.qq.com/) → 开发 → 基本配置 |

详细步骤见 [.env.example](.env.example) 中的注释。

## 字幕纠错

转录流水线包含 **8 层纠错**：

| 层 | 功能 | 示例 |
|----|------|------|
| 1 | 繁体→简体 | 學習 → 学习 |
| 2 | 乱码移除 | ████ → (删除) |
| 3 | 重复段合并 | 相同文本连续出现 → 保留一个 |
| 4 | 时间戳修复 | 负时长、重叠 → 自动修正 |
| 5 | 短段移除 | <0.1s 单字 → 删除 |
| 6 | **上下文同音纠错** | 积因→基因, 深度血习→深度学习, 概律→概率 |
| 7 | **幻觉检测** | "谢谢观看", "嗯嗯嗯" → 删除 |
| 8 | **碎片合并** | 孤立 1-2 字 → 合并到前/后段 |

87 条学术中文同音字修正规则，覆盖生物信息学、AI、统计学等领域。

## 跨平台支持

| 组件 | Windows | macOS | Linux |
|------|---------|-------|-------|
| 安装 | `setup\setup.bat` | `./setup/setup.sh` | 同 macOS |
| biliup | `vendor/biliup.exe` | `vendor/biliup-macos` | `vendor/biliup` |
| FFmpeg | `pip install imageio-ffmpeg` | 同左 / `brew install ffmpeg` | 同左 / `apt install ffmpeg` |

macOS 首次使用 biliup 需要：
```bash
chmod +x vendor/biliup-macos
xattr -d com.apple.quarantine vendor/biliup-macos  # 解除签名限制
```

## 常见问题

| 问题 | 解决 |
|------|------|
| 视频生成网络中断 | `--resume NID TID` 恢复，**不要重建 notebook** |
| NotebookLM 登录超时 | 确认代理，或 `python quick_video.py "test" --check` |
| 视频生成超时 | 通常 10-30 分钟，用 `--resume` 恢复 |
| 上传失败 | `python publish.py --retry` 重新上传 |
| B站 Cookie 过期 | `vendor/biliup.exe login` 重新扫码 |
| 视频号过期 | `publish.py` 自动弹出浏览器扫码 |
| Windows GBK 错误 | 不要用 `conda run`，直接 `python ...` |
| macOS biliup 被拒 | `xattr -d com.apple.quarantine vendor/biliup-macos` |
| 自定义视频内容 | 编辑 `video.md` |

## 致谢

[notebooklm-py](https://github.com/srijitcoder/notebooklm-py) · [paper-search-mcp](https://github.com/paper-search/paper-search-mcp) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [biliup](https://github.com/biliup/biliup) · [Playwright](https://playwright.dev/) · [OpenClaw](https://github.com/openclaw/openclaw)

## 许可证

MIT
