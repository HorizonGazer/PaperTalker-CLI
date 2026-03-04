# Doubao ASR 2.0 API Reference

## Overview

Volcengine Doubao BigModel ASR. Submits audio via URL, polls for results.

**Important:** The API requires a **publicly accessible audio URL** (not local file). May return permission error 45000030 — use faster-whisper as alternative.

## Endpoints

| Action | URL |
|--------|-----|
| Submit | `https://openspeech-direct.zijieapi.com/api/v3/auc/bigmodel/submit` |
| Query  | `https://openspeech-direct.zijieapi.com/api/v3/auc/bigmodel/query` |

## Authentication Headers

```python
headers = {
    "X-Api-App-Key": appid,
    "X-Api-Access-Key": token,
    "X-Api-Resource-Id": "volc.bigasr.auc",
    "X-Api-Request-Id": task_id,           # uuid4
    "X-Api-Sequence": "-1"                 # submit only
}
```

## Submit Request Body

```python
{
    "user": {"uid": "papertalker"},
    "audio": {"url": "<publicly_accessible_audio_url>"},
    "request": {
        "model_name": "bigmodel",
        "enable_channel_split": True,
        "enable_ddc": True,
        "enable_speaker_info": True,
        "enable_punc": True,
        "enable_itn": True,
        "corpus": {"correct_table_name": "", "context": ""}
    }
}
```

## Query Loop

Poll `query` endpoint every 1s with same `X-Api-Request-Id` and `X-Tt-Logid` from submit response.

| Status Code | Meaning |
|-------------|---------|
| `20000000`  | Finished |
| `20000001`  | Processing |
| `20000002`  | Processing |
| Other       | Failed |

## Response → SRT Conversion

```python
def ms_to_srt_time(ms):
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms_rem = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"

def utterances_to_srt(utterances):
    lines = []
    for i, u in enumerate(utterances, 1):
        start = ms_to_srt_time(u["start_time"])
        end = ms_to_srt_time(u["end_time"])
        lines.append(f"{i}\n{start} --> {end}\n{u['text']}\n")
    return "\n".join(lines)
```

## Hosting Local Audio

Since the API needs a URL:

**Python temp server + cloudflared:**
```bash
python -m http.server 8899 --directory output_subtitled/
cloudflared tunnel --url http://localhost:8899
```

## SDK Location

Project file: `auc_python/auc_websocket_demo.py`
