# VectCutAPI Reference

## Overview

VectCutAPI generates JianYing/CapCut draft projects with subtitle tracks. It does **not** directly burn subtitles into video pixels. The user must open the draft in JianYing/CapCut and export to get the final video.

Location: `VectCutAPI/` in project root.

## Start Server

```bash
cd VectCutAPI
pip install -r requirements.txt
cp config.json.example config.json  # edit is_capcut_env: false for JianYing
python capcut_server.py             # HTTP API on port 9001
```

## Add Subtitle API

**`POST http://localhost:9001/add_subtitle`**

### Required Parameter

| Parameter | Type | Description |
|-----------|------|-------------|
| `srt` | string | SRT content string, URL to .srt file, or local file path |

### Key Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `draft_id` | null | Existing draft ID (null = create new) |
| `font` | `"思源粗宋"` | Font name |
| `font_size` | `5.0` | Font size |
| `bold` | `false` | Bold text |
| `font_color` | `"#FFFFFF"` | Hex color |
| `border_color` | `"#000000"` | Border hex color |
| `border_width` | `0.0` | Border width (0 = none) |
| `background_alpha` | `0.0` | Background opacity (0 = none) |
| `transform_y` | `-0.8` | Vertical position (-0.8 = near bottom) |
| `width` | `1080` | Canvas width |
| `height` | `1920` | Canvas height |

### Example

```python
import requests

srt_content = "1\n00:00:00,000 --> 00:00:04,433\nHello world.\n\n2\n00:00:04,433 --> 00:00:11,360\nThis is a test.\n"

resp = requests.post("http://localhost:9001/add_subtitle", json={
    "srt": srt_content,
    "font_size": 8.0,
    "bold": True,
    "font_color": "#FFFFFF",
    "border_color": "#000000",
    "border_width": 1.0,
    "transform_y": -0.8,
    "width": 1920,
    "height": 1080
})
print(resp.json())
# {"success": true, "output": {"draft_id": "dfd_...", "draft_url": "..."}, "error": ""}
```

## Save Draft

**`POST http://localhost:9001/save_draft`**

```python
resp = requests.post("http://localhost:9001/save_draft", json={
    "draft_id": "<draft_id from add_subtitle response>"
})
```

## Workflow

1. Start server (`python capcut_server.py`)
2. Add video to draft (`POST /add_video`)
3. Add subtitle (`POST /add_subtitle` with SRT)
4. Save draft (`POST /save_draft`)
5. Open draft folder in JianYing/CapCut
6. Export final video from JianYing/CapCut
