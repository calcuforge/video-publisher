#!/usr/bin/env python3
"""
agent channel 通知推送 CLI — agent 在转达人机协作提示时，可用本脚本通过
hermes agent gateway 的 channel 推送通知（如"请通过 VNC 完成登录"）。

用法:
    python notify.py --project-config <...>/project_config.yaml \
                     --message "需要用户通过 VNC 完成登录"
    python notify.py --message "..." --to weixin      # 单次覆盖目标
    python notify.py --message "..."                  # 无任何目标配置 = 推全部

目标解析优先级（hermes v0.20+ 强制显式 --to）：
1. --to 参数（单次覆盖，可多次传）；
2. project_config.yaml 的 publish_defaults.hermes_send_targets（列表，
   支持多个目标，如 [weixin, telegram:12345]）；
3. 两者均未设置（空）→ 推送到所有已发现的 channel（hermes send --list 枚举）。
   注意：hermes send 不支持省略 --to 发默认频道，未设置目标时必须枚举。

推送机制（lib/notify.py）：
- 执行 `hermes send --to <目标频道> --subject <标题> <消息>`，复用
  hermes gateway 已配置的频道凭据（Telegram/Discord/飞书/钉钉/企业微信等）；
- **消息自动包含 VNC 接入地址**（优先取环境变量 `VNC_VIEWER_URL`，未设置
  回退 hermes 环境约定的 `{host}:{VNC_PORT}`），用户收到推送即可按地址
  接入浏览器处理；
- 失败时 msg/data.reason 输出真实原因（无目标 / CLI 缺失 / 退出码 /
  限流 rate limited 等），仅警告，不影响发布流程。

输出: JSON envelope。data.sent 是否全部成功，data.targets 实际目标列表。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.env import vnc_hint
from lib.net import ensure_utf8_stdio, require_abs
from lib.yamlutil import load_yaml

ensure_utf8_stdio()


def resolve_targets(args) -> tuple[list[str], str]:
    """按 优先级：--to > project_config.publish_defaults.hermes_send_targets > 全部。

    返回 (targets, 来源说明)。"""
    if args.to:
        return args.to, "--to 参数"
    if args.project_config:
        require_abs(args.project_config)
        config = load_yaml(args.project_config)
        targets = config.get("publish_defaults", {}).get("hermes_send_targets", []) or []
        if targets:
            return targets, "project_config.yaml 的 publish_defaults.hermes_send_targets"
    return [], "未配置目标（推送到所有已发现 channel）"


def main() -> None:
    parser = argparse.ArgumentParser(description="Push a notification through the hermes agent channel")
    parser.add_argument("--message", required=True, help="通知消息内容")
    parser.add_argument("--title", default="video-publisher", help="通知标题（--subject）")
    parser.add_argument("--to", action="append", default=[],
                        help="目标频道（如 weixin / telegram:12345），可多次传；默认读取 project_config 配置")
    parser.add_argument("--project-config", default="", help="项目配置绝对路径（读取 publish_defaults.hermes_send_targets）")
    args = parser.parse_args()

    from lib.notify import notify_human_collab

    # 推送消息必须包含 VNC 接入地址：@ENV@ 提示自带（noVNC/接入方式 字样）
    # 则原样推送，否则自动附加（agent 手动写消息时兜底；注意消息里提到
    # "VNC" 单词不等于包含地址，须按地址特征判断）
    message = args.message
    has_address = ("noVNC" in message) or ("noVnc" in message) or ("接入方式" in message)
    if not has_address:
        message = f"{message}。接入方式：{vnc_hint()}"

    targets, source = resolve_targets(args)
    sent, reason, used_targets = notify_human_collab(message, title=args.title, targets=targets)
    print(json.dumps({
        "status": "ok" if sent else "warning",
        "msg": "hermes channel 推送成功" if sent else f"hermes channel 推送失败：{reason}",
        "data": {"sent": sent, "targets": used_targets, "target_source": source, "reason": reason},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
