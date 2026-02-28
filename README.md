# PaperTalker-CLI

一键「主题 → 学术视频」命令行工具。输入一个研究主题，自动通过 NotebookLM Deep Research 搜索资料、导入来源、生成视频并下载到本地。

## ✨ 特性

- 🚀 **一键安装**：自动检测/安装 Miniconda，配置清华镜像，安装所有依赖
- 🔍 **多种来源模式**：Deep Research 网络搜索 / 学术论文检索 / 手动上传 / 混合模式
- 🎨 **9种视频风格**：白板手绘、动漫、水彩、复古等多种风格可选
- 📚 **8个论文平台**：arXiv、PubMed、Semantic Scholar 等主流学术数据库
- ⚡ **超时恢复**：视频生成超时可随时恢复，无需重新开始
- 🌐 **中文优化**：默认简体中文，高信息密度，面向研究者

## 快速开始

```bash
# 1. 一键安装（自动处理 Conda 环境 + 依赖）
.\setup.ps1

# 2. 激活环境
conda activate papertalker

# 3. 首次登录 NotebookLM
notebooklm login

# 4. 生成视频
python quick_video.py "自定义主题
```

视频将保存到 `./output/`

## 📋 环境要求


| 依赖   | 版本               | 说明                   |
| ------ | ------------------ | ---------------------- |
| Python | ≥ 3.10            | 推荐 3.11              |
| 网络   | 需代理             | 访问 Google NotebookLM |
| 认证   | storage_state.json | NotebookLM 登录凭证    |

## 🔧 安装步骤

### 方式一：一键安装

#### Windows 用户

运行 `setup.ps1` 或 `setup.bat`：

```bash
# PowerShell
.\setup.ps1

# 或 CMD
.\setup.bat
```

#### macOS/Linux 用户

运行 `setup.sh`：

```bash
chmod +x setup.sh
./setup.sh
```

脚本会自动完成以下步骤：

**Step 1: 检测/安装 Conda**

- ✅ 已有 Conda → 直接使用
- 📦 无 Conda → 从清华镜像自动下载安装 Miniconda
  - Windows: Miniconda3-latest-Windows-x86_64.exe
  - macOS: Miniconda3-latest-MacOSX-arm64.sh
  - Linux: Miniconda3-latest-Linux-x86_64.sh

**Step 2: 创建独立环境**

- 创建 `papertalker` 环境（Python 3.11）
- 自动检测并清理无效环境

**Step 3: 安装依赖**

- notebooklm-py（NotebookLM 自动化）
- paper-search-mcp（学术论文搜索）
- playwright（浏览器自动化）
- 其他依赖包

**Step 4: 验证安装**

- 检查 NotebookLM 认证文件
- Windows: 自动打开新窗口并激活环境
- macOS/Linux: 提示手动激活环境

安装完成后：

```bash
# 激活环境
conda activate papertalker

# 首次登录
notebooklm login

# 开始使用
python quick_video.py "你的主题"
```

### 方式二：手动安装

如果自动安装失败，可以手动执行：

```bash
# 1. 创建环境
conda create -n papertalker python=3.11 -y
conda activate papertalker

# 2. 配置 pip 镜像（可选，加速下载）
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 安装依赖
pip install -e deps/notebooklm-py
pip install -e deps/paper-search-mcp
pip install python-dotenv httpx rich playwright

# 4. 安装浏览器
python -m playwright install chromium

# 5. 登录
notebooklm login
```

### 配置代理

编辑 `.env` 文件，设置代理地址（访问 Google 需要）：

```env
HTTPS_PROXY=http://127.0.0.1:7897
HTTP_PROXY=http://127.0.0.1:7897
```

### 登录 NotebookLM

首次使用需要登录 Google 账号：

```bash
notebooklm login
```

这会打开浏览器窗口：

1. 完成 Google 登录
2. 等待进入 NotebookLM 主页
3. 回到终端按 Enter 保存认证

认证信息保存在 `~/.notebooklm/storage_state.json`，下次使用无需重新登录。

**注意**：如果遇到超时错误，脚本会自动重试（最多3次，每次60秒超时）。

## 📖 使用方法

### 基本用法

```bash
# Deep Research（默认）— 自动搜索网络资料
python quick_video.py "生物智能体"

# 指定视频风格
python quick_video.py "蛋白质折叠" --style anime

# 指定输出目录
python quick_video.py "量子计算" --output ./videos
```

### 来源模式


| 模式       | 说明                                              | 适用场景                   |
| ---------- | ------------------------------------------------- | -------------------------- |
| `research` | （默认）NotebookLM Deep Research 自动搜索网络资料 | 综合性主题、前沿技术       |
| `search`   | paper-search-mcp 论文检索，支持平台/年份/数量筛选 | 学术研究、特定领域深度分析 |
| `upload`   | 打开笔记本页面，手动上传文件后继续                | 已有资料、特定文档         |
| `mixed`    | 先 Deep Research，再补充论文检索                  | 需要网络资料+学术论文      |

```bash
# 论文检索 — 指定平台和年份
python quick_video.py "蛋白质折叠" --source search --platforms arxiv pubmed --year 2026

# 手动上传 — 打开笔记本，上传后按 Enter
python quick_video.py "量子计算" --source upload

# 混合模式 — Deep Research + 论文检索
python quick_video.py "LLM药物发现" --source mixed --platforms semantic_scholar --year 2026
```

### 全部参数


| 参数               | 默认值                 | 说明                                         |
| ------------------ | ---------------------- | -------------------------------------------- |
| `topic`            | （必填）               | 视频主题                                     |
| `--source`         | `research`             | 来源模式: research / search / upload / mixed |
| `--style`          | `whiteboard`           | 视频风格（见下表）                           |
| `--lang`           | `zh-CN`                | 语言代码                                     |
| `--mode`           | `deep`                 | Deep Research 深度: fast / deep              |
| `--platforms`      | arxiv semantic_scholar | 论文搜索平台（空格分隔）                     |
| `--max-results`    | `10`                   | 每平台最大结果数                             |
| `--year`           | 无                     | 论文年份筛选                                 |
| `--output`         | `./output`             | 视频输出目录                                 |
| `--timeout`        | `1800`                 | 视频生成超时（秒）                           |
| `--instructions`   | video.md               | 自定义视频指令文本                           |
| `--no-confirm`     | false                  | 跳过阶段确认                                 |
| `--resume NID TID` | —                     | 恢复超时的视频任务                           |

### 视频风格


| 风格          | 说明               | 适用场景       |
| ------------- | ------------------ | -------------- |
| `whiteboard`  | 白板手绘风（默认） | 教学、讲解     |
| `classic`     | 经典风格           | 正式、学术     |
| `anime`       | 动漫风             | 科普、趣味     |
| `kawaii`      | 可爱风             | 轻松、有趣     |
| `watercolor`  | 水彩风             | 艺术、柔和     |
| `retro_print` | 复古印刷           | 怀旧、经典     |
| `heritage`    | 传统风             | 文化、历史     |
| `paper_craft` | 纸艺风             | 创意、手工     |
| `auto`        | 自动选择           | 让 AI 自动决定 |

### 论文搜索平台


| 平台             | ID                 | 说明                   |
| ---------------- | ------------------ | ---------------------- |
| arXiv            | `arxiv`            | 物理、数学、计算机科学 |
| PubMed           | `pubmed`           | 生物医学               |
| bioRxiv          | `biorxiv`          | 生物学预印本           |
| medRxiv          | `medrxiv`          | 医学预印本             |
| Semantic Scholar | `semantic_scholar` | 跨学科学术搜索         |
| Google Scholar   | `google_scholar`   | 综合学术搜索           |
| CrossRef         | `crossref`         | 学术出版物元数据       |
| IACR             | `iacr`             | 密码学                 |

## 🔄 工作流程

```
输入主题
  │
  ├─ research ──→ Deep Research 搜索 ──→ 轮询完成 ──→ 导入来源
  ├─ search ────→ 论文检索 ──────────────────────────→ 添加 URL
  ├─ upload ────→ 打开笔记本 → 用户上传 → Enter ────→ 已在笔记本中
  └─ mixed ─────→ Deep Research + 论文检索 ──────────→ 导入 + 添加
  │
  ▼
  [阶段确认] 展示来源列表，确认后继续
  │
  ▼
  等待来源处理 → 生成视频 → 轮询状态 → 下载 MP4
  │
  ▼
  ./output/主题_时间戳.mp4
```

## ⏱️ 超时恢复

视频生成通常需要 10-20 分钟。如果超时，脚本会打印恢复命令：

```bash
# 超时后会显示类似：
#   恢复命令:
#   python quick_video.py "主题" --resume <notebook_id> <task_id>

# 直接运行恢复命令即可继续等待 + 下载
python quick_video.py "脑机接口" --resume abc123 def456
```

## 📁 文件结构

```
PaperTalker-CLI/
├── quick_video.py          # 主脚本
├── paper_search.py         # 论文搜索封装
├── video.md                # 视频生成提示词
├── .env                    # 环境配置（代理、API Keys）
├── .env.example            # 配置模板
├── setup.sh                # macOS/Linux 一键安装脚本
├── setup.bat               # Windows 主安装脚本（调用子脚本）
├── setup.ps1               # Windows PowerShell 包装器
├── setup_conda.bat         # Windows Step 1: 检测/安装 Conda
├── setup_env.bat           # Windows Step 2: 创建环境
├── install_deps.bat        # Windows Step 3: 安装依赖
├── output/                 # 视频输出目录
├── deps/                   # 本地依赖包
│   ├── notebooklm-py/      # NotebookLM 自动化库
│   └── paper-search-mcp/   # 学术论文搜索库
└── README.md               # 本文件
```

## ❓ 常见问题

### Q: `notebooklm login` 超时？

**原因**：网络连接慢或代理不稳定

**解决**：

1. 确保代理已开启，且 `.env` 中的代理地址正确
2. 脚本会自动重试3次，每次60秒超时
3. 如果仍然失败，检查代理是否能访问 `https://notebooklm.google.com`

### Q: Deep Research 没有返回来源？

**原因**：NotebookLM 的 Deep Research 需要稳定的网络连接

**解决**：

1. 检查代理是否正常工作
2. 尝试使用 `--mode fast` 快速模式
3. 或使用 `--source search` 直接搜索论文

### Q: 视频生成一直超时？

**原因**：NotebookLM 视频生成通常需要 10-20 分钟，来源多时更久

**解决**：

1. 使用 `--timeout 3600` 增加超时时间（秒）
2. 超时后使用 `--resume` 恢复，无需重新开始
3. 减少来源数量（`--max-results 5`）

### Q: macOS 上运行 setup.sh 提示权限错误？

**原因**：脚本没有执行权限

**解决**：

```bash
chmod +x setup.sh
./setup.sh
```

### Q: macOS 上 Conda 初始化后仍然找不到 conda 命令？

**原因**：需要重启终端或重新加载配置文件

**解决**：

```bash
# 重新加载配置
source ~/.bash_profile  # 如果使用 bash
source ~/.zshrc         # 如果使用 zsh

# 或者直接重启终端
```

### Q: 安装脚本在某一步停止？

**原因**：网络问题或环境冲突

**解决**：

1. 检查网络连接和代理设置
2. **Windows 用户**手动运行各个子脚本：
   ```bash
   .\setup_conda.bat    # 安装 Conda
   .\setup_env.bat      # 创建环境
   .\install_deps.bat   # 安装依赖
   ```
3. **macOS/Linux 用户**查看脚本输出的错误信息，通常是网络问题
4. 或使用手动安装方式

### Q: 如何在其他电脑使用？

**步骤**：

1. 复制整个 `PaperTalker-CLI/` 文件夹
2. 运行 `setup.ps1` 或 `setup.bat` 安装依赖
3. 运行 `notebooklm login` 登录
4. 配置 `.env` 中的代理
5. 开始使用

### Q: 如何自定义视频内容？

编辑 `video.md` 文件，修改视频生成提示词。默认提示词要求：

- 简体中文
- 严格忠实原文，引用具体数值
- 高信息密度，面向研究者

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

- [notebooklm-py](https://github.com/yourusername/notebooklm-py) - NotebookLM 自动化库
- [paper-search-mcp](https://github.com/yourusername/paper-search-mcp) - 学术论文搜索库
- [Playwright](https://playwright.dev/) - 浏览器自动化框架
