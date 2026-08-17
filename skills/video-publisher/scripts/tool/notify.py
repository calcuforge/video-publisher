#!/usr/bin/env python3
"""
agent channel 通知推送 CLI — agent 在转达人机协作提示时，可用本脚本通过
配置的 channel 推送通知（如"请通过 VNC 完成登录"）。

用法:
    python notify.py --message "需要用户通过 VNC 完成登录"
    python notify.py --message "..." --title "video-publisher"

channel 配置解析（与 lib/notify.py 一致）：
- 环境变量 AGENT_CHANNEL_CONFIG → yaml 文件
- 默认 {workspace}/video_publiser_data/agent_channel.yaml
- 环境变量 AGENT_CHANNEL → webhook URL 或命令模板

输出: JSON envelope。未配置 channel 时 status=ok 且 data.sent=false。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.net import ensure_utf8_stdio

ensure_utf8_stdio()


def main() -> None:
    parser = argparse.ArgumentParser(description="Push a notification through the agent channel")
    parser.add_argument("--message", required=True, help="通知消息内容")
    parser.add_argument("--title", default="video-publisher", help="通知标题")
    args = parser.parse_args()

    from lib.notify import load_channel_config, notify_human_collab

    config = load_channel_config()
    if not config:
        print(json.dumps({
            "status": "ok",
            "msg": "未配置 agent channel，跳过推送（配置方法见 lib/notify.py 与 references/human-collab.md）",
            "data": {"sent": False},
        }, ensure_ascii=False, indent=2))
        return

    sent = notify_human_collab(args.message, title=args.title)
    print(json.dumps({
        "status": "ok" if sent else "warning",
        "msg": f"agent channel 推送{'成功' if sent else '失败（详见 stderr）'}",
        "data": {"sent": sent, "type": config.get("type"), "target": config.get("target", "")},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
