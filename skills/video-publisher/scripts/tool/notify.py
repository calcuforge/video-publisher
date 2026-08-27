#!/usr/bin/env python3
"""
agent channel 通知推送 CLI — agent 在转达人机协作提示时，可用本脚本通过
hermes agent gateway 的 channel 推送通知（如"请通过 VNC 完成登录"）。

用法:
    python notify.py --message "需要用户通过 VNC 完成登录"
    python notify.py --message "..." --title "video-publisher" --to telegram

推送机制（lib/notify.py）：
- 执行 `hermes send [--to <目标频道>] --subject <标题> <消息>`，复用
  hermes gateway 已配置的频道凭据（Telegram/Discord/飞书/钉钉/企业微信等）；
- 目标频道：--to 参数 > 环境变量 HERMES_SEND_TARGET > hermes 默认（home channel）；
- hermes CLI 缺失或推送失败仅警告，不影响发布流程。

输出: JSON envelope。data.sent 表示是否成功推送。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.env import get_env
from lib.net import ensure_utf8_stdio

ensure_utf8_stdio()


def main() -> None:
    parser = argparse.ArgumentParser(description="Push a notification through the hermes agent channel")
    parser.add_argument("--message", required=True, help="通知消息内容")
    parser.add_argument("--title", default="video-publisher", help="通知标题（--subject）")
    parser.add_argument("--to", default="", help="目标频道（如 telegram / telegram:12345 / wecom），默认取 HERMES_SEND_TARGET")
    args = parser.parse_args()

    from lib.notify import notify_human_collab

    if args.to:
        import os
        os.environ["HERMES_SEND_TARGET"] = args.to

    target = get_env("HERMES_SEND_TARGET", "")
    sent = notify_human_collab(args.message, title=args.title)
    print(json.dumps({
        "status": "ok" if sent else "warning",
        "msg": f"hermes channel 推送{'成功' if sent else '失败（详见 stderr；未安装 hermes 或 gateway 未运行）'}",
        "data": {"sent": sent, "target": target or "hermes 默认(home channel)"},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
