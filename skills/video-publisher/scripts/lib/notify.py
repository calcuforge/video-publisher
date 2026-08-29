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
- 目标频道：环境变量 HERMES_SEND_TARGET（如 `weixin`、`telegram:12345`、
  `discord:#ops`）。**hermes v0.20+ 强制要求显式 `--to <平台[:频道[:thread]]>`**，
  省略 --to 时 hermes send 报 "--to PLATFORM[:channel[:thread]] is required"
  并退出码 2——因此 HERMES_SEND_TARGET 未设置时直接返回失败，绝不假装成功。
- 失败时透传 stderr（截断 300 字符）到 WARNING；微信等平台限流
  （rate limited）时给出约 30s 退避提示并自动重试一次。
- 推送失败只输出警告，绝不阻断主流程。
"""

from __future__ import annotations

import re
import subprocess
import sys
import time

from lib.env import get_env

# hermes send 输出中的限流信息，如 "iLink sendmessage rate limited; cooldown active for 30.0s"
_RATE_LIMIT_RE = re.compile(r"rate limited.*cooldown active for ([\d.]+)s", re.IGNORECASE)


def _warn(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def _run_hermes_send(target: str, message: str, title: str) -> tuple[bool, str]:
    """执行一次 hermes send。返回 (ok, 失败原因摘要)。"""
    cmd = ["hermes", "send", "--to", target, "--subject", title, message]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return False, "hermes CLI 未安装或不在 PATH 上（请安装 hermes-agent 并配置 gateway）"
    except subprocess.TimeoutExpired:
        return False, "hermes send 超时（60s）"
    except Exception as exc:
        return False, f"hermes send 执行异常: {exc}"

    if proc.returncode == 0:
        return True, ""
    err = (proc.stderr or proc.stdout or "").strip()[:300]
    return False, f"hermes send 失败（退出码 {proc.returncode}）: {err}"


def notify_human_collab(message: str, title: str = "video-publisher") -> tuple[bool, str]:
    """通过 hermes agent channel 推送人机协作通知。

    返回 (是否成功, 失败原因摘要)。失败原因供调用方（tool/notify.py）向用户
    展示真实情况；调用方仅警告、绝不阻断发布主流程。
    """
    target = get_env("HERMES_SEND_TARGET")
    if not target:
        reason = ("未设置 HERMES_SEND_TARGET；hermes send 强制要求显式 "
                  "--to <平台[:频道]>（如 HERMES_SEND_TARGET=weixin），无法推送")
        _warn(reason)
        return False, reason

    ok, reason = _run_hermes_send(target, message, title)
    if ok:
        return True, ""

    # 限流退避：解析 cooldown 秒数（默认 30s），提示后自动重试一次
    match = _RATE_LIMIT_RE.search(reason)
    if match:
        cooldown = float(match.group(1))
        _warn(f"hermes send 目标平台限流（rate limited，cooldown {cooldown:.0f}s），"
              f"等待退避后重试一次...（不影响发布流程）")
        time.sleep(min(cooldown, 30))
        ok, retry_reason = _run_hermes_send(target, message, title)
        if ok:
            return True, ""
        reason = f"限流重试后仍失败: {retry_reason}"

    _warn(f"hermes send 推送失败（不影响发布流程）: {reason}")
    return False, reason
