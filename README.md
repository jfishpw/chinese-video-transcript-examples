# chinese-video-transcript-examples

用 [Apify](https://apify.com) 把 **抖音 / B站视频**变成**带时间戳的中文文字稿**，喂给 LLM、RAG、向量库或全文检索。

底层 Actor：[`jfishpw/chinese-video-transcript`](https://apify.com/jfishpw/chinese-video-transcript) — 抖音/B站视频转文字，无需 API key，$0.008/条 + $0.01/分钟。

---

## 30 秒上手

```python
from apify_client import ApifyClient

client = ApifyClient("<YOUR_API_TOKEN>")
run = client.actor("jfishpw/chinese-video-transcript").call(
    run_input={"videoUrls": ["https://www.bilibili.com/video/BV1MzWU65Ewn"]},
)
for item in client.dataset(run["defaultDatasetId"]).iterate_items():
    print(item["text"])
```

## 它解决什么问题

视频内容没法直接喂给 LLM——模型的输入是文本，不是视频。常见做法是：下载视频 → 抽音轨 → 跑 ASR → 拼时间戳。这套流程要自己处理登录态、代理、音频格式、模型加载、中文优化，每一步都能卡住。

这个 Actor 把整条链路封装成一个 HTTP 调用：

```
视频链接 → 解析直链 → 抽音频 → Whisper 转写 → 带时间戳的 JSON
```

## 支持的输入

| 输入类型 | 示例 | 说明 |
|---|---|---|
| 抖音视频 | `https://www.douyin.com/video/7534679152504376595` | 服务端直出转写，秒级返回 |
| 抖音分享短链 | `https://v.douyin.com/xxxxx/` | 自动跟随跳转 |
| B站视频 | `https://www.bilibili.com/video/BV1MzWU65Ewn` | 自动解析音频 |
| B站 BV / av 号 | `BV1MzWU65Ewn` / `av170001` | |
| 直链媒体 | `https://.../video.mp4` `.m4a` `.mp3` `.wav` `.m3u8` | 直接转写 |

批量最多 50 条（`maxItems`），单条失败不影响其他条目。

## 输出结构

每条视频一行 JSON：

```json
{
  "url": "https://www.bilibili.com/video/BV1MzWU65Ewn",
  "platform": "bilibili",
  "videoId": "BV1MzWU65Ewn",
  "title": "普通话水平测试网站（免费）",
  "author": "...",
  "durationSec": 23.8,
  "source": "asr",
  "modelSize": "base",
  "language": "zh",
  "text": "烤普通话,别再下毒了...",
  "segments": [{"start": 0.0, "end": 4.4, "text": "..."}],
  "segmentCount": 2,
  "charCount": 118,
  "billableMinutes": 1,
  "hasTranscript": true,
  "qualityCheck": true,
  "errorCode": null,
  "hint": null,
  "fetchedAt": "2026-11-18T07:15:00+00:00"
}
```

`segments` 带秒级时间戳，可以做片段级引用；`qualityCheck` 是结果自证字段（`hasTranscript` 且最后时间戳 ≤ 音频时长 × 1.25）。

## 常用配置

| 字段 | 默认值 | 说明 |
|---|---|---|
| `videoUrls` | `[]` | 视频链接数组，必填 |
| `modelSize` | `base` | `tiny` 最快最便宜 / `base` 均衡 / `small` 最准 |
| `language` | `zh` | `zh` / `auto` / `en` |
| `withTimestamps` | `true` | 是否返回带时间戳的分段 |
| `includeMetadata` | `true` | 是否附带标题、作者、播放量等元数据 |
| `maxItems` | `10` | 单次最多处理多少条 |
| `maxDurationSec` | `300` | 超过则跳过并返回 `MEDIA_TOO_LONG`（不计费） |

## 实战场景

### 1. 视频进 RAG 知识库

```python
from apify_client import ApifyClient

client = ApifyClient("<YOUR_API_TOKEN>")
urls = [
    "https://www.bilibili.com/video/BV1MzWU65Ewn",
    "https://www.douyin.com/video/7534679152504376595",
]

run = client.actor("jfishpw/chinese-video-transcript").call(
    run_input={"videoUrls": urls, "modelSize": "base", "withTimestamps": True},
)

docs = []
for item in client.dataset(run["defaultDatasetId"]).iterate_items():
    if not item.get("hasTranscript"):
        continue
    for seg in item.get("segments") or []:
        docs.append({
            "content": seg["text"],
            "metadata": {
                "source": item["url"],
                "title": item["title"],
                "start": seg["start"],
                "end": seg["end"],
            },
        })

print(f"{len(docs)} 个片段可以入库")
```

### 2. 扒竞品的口播文案

```python
import csv

run = client.actor("jfishpw/chinese-video-transcript").call(
    run_input={"videoUrls": competitor_urls, "modelSize": "base"},
)

with open("scripts.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["title", "url", "duration", "text"])
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        w.writerow([item["title"], item["url"], item["durationSec"], item["text"]])
```

### 3. 无字幕视频补字幕

B站匿名接口的 CC/AI 字幕恒返回空（需要登录态 SESSDATA），所以这个 Actor 统一走本地 ASR——**任何视频都有稿**：

```python
run = client.actor("jfishpw/chinese-video-transcript").call(
    run_input={"videoUrls": [url], "modelSize": "base", "withTimestamps": True},
)

for item in client.dataset(run["defaultDatasetId"]).iterate_items():
    srt = ""
    for i, seg in enumerate(item["segments"], 1):
        srt += f"{i}\n{_ts(seg['start'])} --> {_ts(seg['end'])}\n{seg['text']}\n\n"
    open("subtitle.srt", "w", encoding="utf-8").write(srt)


def _ts(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
```

### 4. 命令行一行调用

```bash
curl "https://api.apify.com/v2/acts/jfishpw/chinese-video-transcript/runs?token=$APIFY_TOKEN" \
  -X POST -H "Content-Type: application/json" \
  -d '{"videoUrls":["https://www.bilibili.com/video/BV1MzWU65Ewn"],"modelSize":"base"}'
```

## 接入 AI agent

通过 Apify MCP server 可以让 Claude、Cursor 等直接调用：

```bash
claude mcp add --transport http apify "https://mcp.apify.com?tools=jfishpw/chinese-video-transcript"
```

```json
{
  "mcpServers": {
    "apify": {
      "url": "https://mcp.apify.com?tools=jfishpw/chinese-video-transcript"
    }
  }
}
```

然后直接对 agent 说「把这个 B站视频转成文字稿」。

## 价格

| 事件 | 价格 |
|---|---|
| `transcriptResult` | $0.008 / 条 |
| `transcriptMinute` | $0.01 / 分钟（按音频时长向上取整） |

一条 1 分钟视频 ≈ **$0.018**。失败项、超长视频、不支持的平台**不计费**。

## 已知限制

| 情况 | 行为 |
|---|---|
| 小红书链接 | 返回 `UNSUPPORTED_SOURCE`，不计费 |
| 纯音乐 / 无人声 | 返回 `EMPTY_TRANSCRIPT`，不计费 |
| 超过 `maxDurationSec` | 返回 `MEDIA_TOO_LONG`，下载前拦截，不计费 |

## 相关链接

- Actor 主页：https://apify.com/jfishpw/chinese-video-transcript
- 在线体验（B站示例，链接已预填）：https://apify.com/jfishpw/chinese-video-transcript/examples/bilibili-video-to-text
- 在线体验（RAG 场景）：https://apify.com/jfishpw/chinese-video-transcript/examples/video-transcript-for-rag
- 另一个 Actor：A股主力资金流向 https://apify.com/jfishpw/china-a-share-fund-flow

## License

MIT
