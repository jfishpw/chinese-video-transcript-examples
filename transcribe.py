#!/usr/bin/env python3
"""把 B站 / 抖音视频转成带时间戳的中文文字稿。

用法：
    export APIFY_TOKEN=your_token
    python transcribe.py "https://www.bilibili.com/video/BV1MzWU65Ewn"

    # 批量
    python transcribe.py url1 url2 url3

    # 输出 SRT 字幕
    python transcribe.py --srt output.srt "https://www.bilibili.com/video/BV1MzWU65Ewn"
"""
from __future__ import annotations

import os
import sys

from apify_client import ApifyClient

ACTOR = "jfishpw/chinese-video-transcript"


def to_srt(segments: list[dict]) -> str:
    def ts(seconds: float) -> str:
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    out = ""
    for i, seg in enumerate(segments, 1):
        out += f"{i}\n{ts(seg['start'])} --> {ts(seg['end'])}\n{seg['text']}\n\n"
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    srt_path = None
    if "--srt" in sys.argv:
        idx = sys.argv.index("--srt")
        srt_path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "output.srt"
        args = [a for a in args if a != srt_path]

    if not args:
        print(__doc__)
        return 1

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("缺少 APIFY_TOKEN 环境变量")
        return 1

    client = ApifyClient(token)
    run = client.actor(ACTOR).call(
        run_input={"videoUrls": args, "modelSize": "base", "withTimestamps": True},
    )

    segments: list[dict] = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        title = item.get("title") or item.get("url")
        if not item.get("hasTranscript"):
            print(f"[跳过] {title}  code={item.get('errorCode')}  hint={item.get('hint')}")
            continue
        print(f"\n=== {title} ({item.get('durationSec')}s, {item.get('charCount')} 字) ===")
        print(item["text"][:300])
        segments.extend(item.get("segments") or [])

    if srt_path:
        with open(srt_path, "w", encoding="utf-8") as fh:
            fh.write(to_srt(segments))
        print(f"\nSRT 已写入 {srt_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
