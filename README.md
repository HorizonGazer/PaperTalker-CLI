# PaperTalker-CLI

研究主题 → 学术科普视频 → 字幕 → B站发布，全程对话 Claude 完成。

| 主题                            | 时长 | 字幕 | B站 |
| ------------------------------- | ---- | ---- | --- |
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
| Google 账号                                                | 登录 NotebookLM                                                 |

| 可选              | 说明                                        |
| ----------------- | ------------------------------------------- |
| B站账号           | 上传视频需要，不上传可跳过                  |
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

| 你想做什么     | 对 Claude 说                                                              |
| -------------- | ------------------------------------------------------------------------- |
| 生成视频       | `帮我做一个关于「量子计算」的学术科普视频`                              |
| 生成 + 上传B站 | `生成视频，主题是多组学整合，完成后上传B站`                             |
| 指定风格       | `做一个蛋白质折叠的视频，用动漫风格`                                    |
| 论文检索模式   | `用论文检索模式，主题 AlphaFold3，只搜 arxiv 和 pubmed，限 2025 年以后` |
| 手动上传来源   | `我想手动上传几篇 PDF 作为来源，主题是脑机接口`                         |
| 混合模式       | `混合模式：先 Deep Research 再补充论文，主题是 LLM 药物发现`            |
| 只配字幕       | `帮我把 output 里的视频加字幕，不上传`                                  |
| 字幕 + 上传    | `output 文件夹里有视频了，帮我配字幕上传B站`                            |
| 检查环境       | `帮我检查依赖是否安装完整`                                              |
| 认证过期       | `NotebookLM 认证过期了，帮我自动认证`                                   |
| 视频超时       | `视频生成超时了，帮我恢复`                                              |
| 上传失败       | `上传B站失败了，帮我看看什么原因`                                       |
| 登录B站        | `帮我登录B站`                                                           |
| 自定义提示词   | `帮我修改视频生成提示词，改成英文输出，面向本科生`                      |

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

# ── 字幕 + 上传 ──
python publish.py                  # 处理 output/ 全部视频，配字幕上传B站
python publish.py --skip-upload    # 只配字幕
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
│  ├ 论文检索 (8个平台)   │              │ 3. 语音转录 (whisper GPU) │
│  ├ 手动上传            │              │ 4. 智能分句 (jieba)       │
│  └ 混合模式            │              │ 5. 烧录字幕 (FFmpeg)      │
│    ↓                   │              │ 6. 上传平台 (biliup)      │
│ 生成 + 下载 MP4        │── output/ ──→│ 7. 清理 + 记录历史        │
└────────────────────────┘              └──────────────────────────┘
                                          → output_subtitled/日期/主题.mp4
```

## 仓库结构

```
PaperTalker-CLI/
├── quick_video.py          # Phase 1: 主题 → NotebookLM 视频
├── publish.py              # Phase 2: 字幕 + 上传
├── paper_search.py         # 论文搜索封装
├── video.md                # 视频生成提示词（可自定义）
├── .env.example            # 环境配置模板
├── setup/                  # 一键安装脚本
├── tools/                  # auto_login.py（自动认证）、verify.py（依赖检查）
├── deps/                   # 本地依赖：notebooklm-py、paper-search-mcp
├── cookies/bilibili/       # B站登录凭证 (gitignored)
├── vendor/                 # biliup.exe 等二进制工具 (gitignored)
├── output/                 # 原始视频（处理后自动清理）
├── output_subtitled/       # 最终成品，按日期归档：主题.mp4 + 主题.srt
├── skills/paper-talker/    # Claude Code Skill 定义 + 技术参考文档
└── CLAUDE.md               # Claude Code 项目指引
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
| `--source`         | `research`               | `research` / `search` / `upload` / `mixed`                                                                   |
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

### publish.py — 字幕 + 上传

```bash
python publish.py
```

| 参数              | 默认值                | 说明                                                            |
| ----------------- | --------------------- | --------------------------------------------------------------- |
| `--skip-upload` | false                 | 只配字幕，不上传                                                |
| `--platforms`   | `bilibili`          | `bilibili` `douyin` `weixin` `xiaohongshu` `kuaishou` |
| `--input`       | `output/`           | 输入目录                                                        |
| `--output`      | `output_subtitled/` | 输出目录                                                        |

## 常见问题

| 问题                 | 解决                                                                                |
| -------------------- | ----------------------------------------------------------------------------------- |
| 视频生成网络中断     | 不要重新创建 notebook，用 `--resume NID TID` 恢复轮询，任务在服务端继续运行         |
| NotebookLM 登录超时  | 确认代理开启且 `.env` 正确；或告诉 Claude `帮我自动认证`                        |
| 视频生成超时         | 通常 10-30 分钟。超时后用 `--resume` 恢复，或告诉 Claude `视频超时了，帮我恢复` |
| 上传B站失败          | 重新扫码登录 `vendor/biliup.exe login`；确认 biliup >= 1.1.29                     |
| Windows GBK 编码错误 | 不要用 `conda run`，直接 `conda activate papertalker && python ...`             |
| macOS 权限错误       | `chmod +x setup/setup.sh`                                                         |
| 自定义视频内容       | 编辑 `video.md`（默认：中文、引用数据、高信息密度、面向研究者）                   |

## 致谢

[notebooklm-py](https://github.com/srijitcoder/notebooklm-py) · [paper-search-mcp](https://github.com/paper-search/paper-search-mcp) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [biliup](https://github.com/biliup/biliup) · [Playwright](https://playwright.dev/)

## 许可证

MIT
