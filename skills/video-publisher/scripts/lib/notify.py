"""
Channel 通知推送 — 通过 hermes agent gateway 的 channel 消息推送提醒用户。

推送流程（推送动作由 agent 执行，脚本不自动推送）：
1. 脚本检测到需要登录/验证码 → 输出 @ENV@ human_collab 提示（含 VNC 地址）；
2. agent 看到提示后，调用本模块（或 scripts/tool/notify.py CLI）把**含 VNC
   地址**的提示消息推送到 hermes agent 的 messaging channel（Telegram /
   Discord / Slack / 飞书 / 钉钉 / 企业微信 / 微信 等，复用 hermes gateway
   已配置的频道凭据）。

- 前置：hermes-agent 已安装且 `hermes gateway start` 运行中（凭据在
  `hermes gateway setup` 时配置，本 skill 不重复配置）
- 目标频道：环境变量 HERMES_SEND_TARGET（如 `telegram`、`telegram:12345`、
  `wecom`、`feishu`、`discord:#ops`）；未设置时不带 --to，由 hermes 自行
  决定（home channel）
- 推送失败只输出警告，绝不阻断主流程
"""

from __future__ import annotations

import subprocess
import sys

from lib.env import get_env


def notify_human_collab(message: str, title: str = "video-publisher") -> bool:
    """通过 hermes agent channel 推送人机协作通知。

    返回是否成功推送；hermes CLI 缺失/失败时返回 False（调用方仅警告）。
    """
    cmd = ["hermes", "send"]
    target = get_env("HERMES_SEND_TARGET")
    if target:
        cmd += ["--to", target]
    cmd += ["--subject", title]
    cmd.append(message)

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return True
    except FileNotFoundError:
        print("WARNING: hermes CLI 未安装或不在 PATH 上，无法通过 channel 推送通知"
              "（请安装 hermes-agent 并配置 gateway；不影响发布流程）", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"WARNING: hermes send 推送失败（不影响发布流程）: {exc}", file=sys.stderr)
        return False
