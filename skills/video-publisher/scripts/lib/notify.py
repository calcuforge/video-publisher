"""
Agent channel 通知推送 — 人机协作时需要用户介入（登录态、验证码、风控等）时，
除脚本 stdout 的 @ENV@ 提示外，可额外通过配置的 channel 推送通知提醒用户。

配置解析优先级：
1. 环境变量 AGENT_CHANNEL_CONFIG → 指向 channel 配置 yaml 文件
2. 默认 {workspace}/video_publiser_data/agent_channel.yaml
3. 环境变量 AGENT_CHANNEL → 简化写法：
   - http(s):// 开头 → 视为 webhook URL（type=webhook）
   - 其他 → 视为命令模板（type=command）

配置格式（yaml）：

    # agent_channel.yaml — 人机协作通知推送配置（可选，不配置则不推送）
    enabled: true              # false = 关闭推送
    type: command              # command（执行命令）| webhook（HTTP POST JSON）
    target: 'claude notify "{message}"'   # command: 命令模板，{message} 占位符
                                 # webhook: 目标 URL，POST {"text": message}
    message_template: "⚠ 需要人工配合：{message}"   # 可选，默认原样
    timeout: 10                # 秒

推送失败只输出警告（env_status: notify_warning），绝不阻断主流程。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from lib.env import get_env

DEFAULT_CONFIG_NAME = "agent_channel.yaml"


def _workspace() -> Path:
    ws = get_env("VIDEO_PUBLISHER_WORKSPACE")
    return Path(ws) if ws else Path.cwd()


def load_channel_config() -> Optional[dict]:
    """解析 channel 配置；未配置或未启用返回 None。"""
    # 1. 环境变量指定配置文件
    config_path = get_env("AGENT_CHANNEL_CONFIG")
    if config_path and Path(config_path).exists():
        from lib.yamlutil import load_yaml
        config = load_yaml(config_path)
    else:
        # 2. 默认位置
        default_path = _workspace() / "video_publiser_data" / DEFAULT_CONFIG_NAME
        if default_path.exists():
            from lib.yamlutil import load_yaml
            config = load_yaml(default_path)
        else:
            # 3. AGENT_CHANNEL 简化写法
            shorthand = get_env("AGENT_CHANNEL")
            if not shorthand:
                return None
            if shorthand.startswith("http://") or shorthand.startswith("https://"):
                config = {"type": "webhook", "target": shorthand}
            else:
                config = {"type": "command", "target": shorthand}

    if not isinstance(config, dict):
        return None
    if not config.get("enabled", True):
        return None
    if not config.get("target"):
        return None
    return config


def _format(message: str, config: dict) -> str:
    template = config.get("message_template") or "{message}"
    return template.replace("{message}", message)


def _send_webhook(url: str, text: str, timeout: int) -> bool:
    import requests
    resp = requests.post(url, json={"text": text}, timeout=timeout)
    resp.raise_for_status()
    return True


def _send_command(template: str, text: str, timeout: int) -> bool:
    cmd = template.replace("{message}", text)
    subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout)
    return True


def notify_human_collab(message: str, title: str = "video-publisher") -> bool:
    """推送人机协作通知（非阻塞）。返回是否成功推送（未配置返回 False）。

    发送在线程中执行，避免阻塞脚本的阻塞等待主流程。
    """
    config = load_channel_config()
    if not config:
        return False

    # command 类型不加标题前缀（消息将作为命令参数，方括号等字符可能被
    # shell 误解）；webhook 的 JSON 文本可以带标题
    if config.get("type") == "webhook":
        text = f"[{title}] {_format(message, config)}"
    else:
        text = _format(message, config)
    timeout = int(config.get("timeout", 10))
    result: dict = {}

    def _do() -> None:
        try:
            if config.get("type") == "webhook":
                _send_webhook(config["target"], text, timeout)
                result["ok"] = True
            else:
                _send_command(config["target"], text, timeout)
                result["ok"] = True
        except Exception as exc:  # 推送失败仅警告
            result["ok"] = False
            result["err"] = str(exc)

    thread = threading.Thread(target=_do, daemon=True)
    thread.start()
    thread.join(timeout=timeout + 5)

    ok = result.get("ok")
    if not ok:
        err = result.get("err", "未知错误（可能超时）")
        print(f"WARNING: agent channel 推送失败（不影响发布流程）: {err}", file=sys.stderr)
    return bool(ok)
