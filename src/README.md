# Modular Scripts

独立的模块化脚本，可按需单独调用。

## 脚本列表

### 1. transcribe.py - 音频转录

从视频提取音频，使用 faster-whisper 转录，生成 SRT 字幕文件。

```bash
# 基本用法（自动检测 GPU/CPU，自动选择模型）
python src/transcribe.py video.mp4

# 指定输出文件
python src/transcribe.py video.mp4 -o output.srt

# 指定模型和设备
python src/transcribe.py video.mp4 --model large-v3 --device cuda

# 保留提取的 WAV 文件
python src/transcribe.py video.mp4 --keep-wav
```

**输出：**
- `video.srt` - SRT 字幕文件
- `video.wav` - 提取的音频（默认删除，使用 `--keep-wav` 保留）

---

### 2. subtitle.py - 字幕烧录

将 SRT 字幕烧录到视频中。

```bash
# 基本用法
python src/subtitle.py video.mp4 subtitles.srt

# 指定输出文件
python src/subtitle.py video.mp4 subtitles.srt -o output.mp4

# 自定义字体大小和样式
python src/subtitle.py video.mp4 subtitles.srt --font-size 24 --style bold
```

**样式选项：**
- `default` - 默认样式
- `bold` - 粗体
- `outline` - 加粗轮廓

**输出：**
- `video_subtitled.mp4` - 带字幕的视频

---

### 3. upload_bilibili.py - B站上传

上传视频到 Bilibili，支持标题、标签、描述、封面。

```bash
# 基本用法
python src/upload_bilibili.py video.mp4 \
  --title "【AI科研科普】主题：前沿研究深度解读" \
  --tags "AI科研,学术科普,论文解读" \
  --desc "视频描述"

# 带封面
python src/upload_bilibili.py video.mp4 \
  --title "标题" \
  --tags "tag1,tag2,tag3" \
  --cover cover.jpg

# 自动登录（如果没有 cookies）
python src/upload_bilibili.py video.mp4 \
  --title "标题" \
  --tags "tag1,tag2" \
  --auto-login
```

**注意事项：**
- 标签最多 12 个，每个最多 20 字符
- 首次使用需要扫码登录（使用 `--auto-login`）
- Cookies 保存在 `cookies/bilibili/account.json`

**输出：**
- 成功后返回 BV 号和视频链接

---

### 4. upload_weixin.py - 微信视频号上传

上传视频到微信视频号。

```bash
# 基本用法
python src/upload_weixin.py video.mp4 \
  --title "视频标题" \
  --desc "视频描述"

# 带标签
python src/upload_weixin.py video.mp4 \
  --title "视频标题" \
  --desc "视频描述" \
  --tags "AI,科研,学术"
```

**注意事项：**
- 标题长度：6-16 字符（少于 6 字符会自动补齐）
- 首次使用需要微信扫码登录
- 登录状态保存在 `cookies/weixin/browser_profile/`
- 标签最多 5 个

**输出：**
- 成功后视频发布到微信视频号

---

## 使用场景

### 场景 1：重新转录（使用不同模型）

```bash
# 使用 GPU 和 large-v3 模型重新转录
python src/transcribe.py video.mp4 --model large-v3 --device cuda -o new_subtitles.srt

# 烧录新字幕
python src/subtitle.py video.mp4 new_subtitles.srt -o video_new_subs.mp4
```

### 场景 2：重新上传（修改元数据）

```bash
# 重新上传到 B站，使用新的标题和标签
python src/upload_bilibili.py video_subtitled.mp4 \
  --title "新标题" \
  --tags "新标签1,新标签2,新标签3" \
  --cover new_cover.jpg
```

### 场景 3：仅字幕工作流

```bash
# 1. 转录
python src/transcribe.py video.mp4

# 2. 烧录字幕
python src/subtitle.py video.mp4 video.srt

# 完成！不上传
```

### 场景 4：仅上传工作流

```bash
# 假设已经有带字幕的视频，直接上传
python src/upload_bilibili.py video_subtitled.mp4 \
  --title "标题" \
  --tags "tag1,tag2" \
  --auto-login

python src/upload_weixin.py video_subtitled.mp4 \
  --title "标题" \
  --desc "描述"
```

### 场景 5：批量处理

```bash
# 批量转录多个视频
for video in output/*.mp4; do
  python src/transcribe.py "$video"
done

# 批量烧录字幕
for video in output/*.mp4; do
  srt="${video%.mp4}.srt"
  python src/subtitle.py "$video" "$srt"
done
```

---

## 与 publish.py 的关系

`publish.py` 是一个编排器（orchestrator），内部调用这些模块化脚本的功能。

**何时使用 publish.py：**
- 完整的端到端流程（转录 + 字幕 + 上传）
- 批量处理 `output/` 目录中的所有视频
- 自动生成元数据（标题、标签、描述）

**何时使用模块化脚本：**
- 只需要某个特定步骤
- 需要自定义参数（模型、样式、元数据等）
- 需要重试某个失败的步骤
- 需要批量处理但使用自定义逻辑

---

## 依赖

所有脚本共享相同的依赖：

```bash
# 转录
pip install imageio-ffmpeg faster-whisper

# 字幕烧录
pip install imageio-ffmpeg

# B站上传
pip install "biliup>=1.1.29"

# 微信视频号上传
pip install playwright nest-asyncio
playwright install chromium
```

或使用一键安装：

```bash
# Windows
setup\setup.bat

# macOS/Linux
./setup/setup.sh
```
