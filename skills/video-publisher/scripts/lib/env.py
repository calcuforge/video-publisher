"""
环境变量约定 — 与 hermes-hitl-environment（https://github.com/.../hermes-hitl-environment）
对齐。该环境提供标准的人机协作桌面：人类通过 VNC(5900)/noVNC(6080) 观察操作，
agent 通过 CDP(9222) 驱动同一个共享 Chromium。

重要：本模块只读取进程环境变量（os.environ），**不读取任何 .env 文件**。
hermes 的 .env/.env.example 只是 docker compose 部署时的配置源（env_file），
部署时变量被注入容器进程环境；容器内部与本地运行环境中都没有 .env 文件。

约定的环境变量（变量名与 hermes 的 .env.example 一致）：

  PLAYWRIGHT_CDP_URL=http://127.0.0.1:9222   Playwright 通过 CDP 驱动共享 Chromium
  CHROME_REMOTE_DEBUGGING_PORT=9222          共享 Chromium 调试端口
  VNC_PORT=5900                              VNC 端口
  NOVNC_PORT=6080                            noVNC 端口（浏览器访问 /vnc.html）
  DISPLAY=:99                                X display
  SCREEN_WIDTH=1920 / SCREEN_HEIGHT=1080     Chromium 窗口尺寸
  CHROME_BIN=chromium                        浏览器可执行文件
  CHROME_PROFILE_DIR=/data/chromium          持久化 profile（登录态/cookie）
  CHROME_DOWNLOADS_DIR=/downloads            下载目录
  CHROME_EXTRA_FLAGS="..."                   附加启动参数（空格分隔）
  HERMES_WEBUI_LANG=zh-CN                    浏览器界面语言

解析优先级统一为：命令行参数 > 环境变量 > 配置文件 > 默认值。
"""

from __future__ import annotations

import os
from urllib.parse import urlparse


def get_env(name: str, default: str = "") -> str:
    """读取环境变量，未设置或为空时返回默认值。"""
    value = os.environ.get(name, "")
    return value if value else default


def resolve_cdp_url(configured: str = "", port: int = 9222) -> str:
    """解析 CDP 地址。

    优先级：显式传入 > 环境变量 PLAYWRIGHT_CDP_URL > http://127.0.0.1:{port}。
    """
    if configured:
        return configured
    env_url = get_env("PLAYWRIGHT_CDP_URL")
    if env_url:
        return env_url
    return f"http://127.0.0.1:{port}"


def cdp_port(cdp_url: str) -> int:
    """从 CDP URL 提取端口号。"""
    try:
        return urlparse(cdp_url).port or 9222
    except ValueError:
        return 9222


def vnc_hint(host: str = "127.0.0.1", cdp_url: str = "") -> str:
    """生成人机协作入口提示（对齐 hermes 端口约定）。

    cdp_url 显式传入时以其为准；否则按 resolve_cdp_url 约定解析。
    """
    vnc_port = get_env("VNC_PORT", "5900")
    novnc_port = get_env("NOVNC_PORT", "6080")
    resolved = cdp_url if cdp_url else resolve_cdp_url()
    return (
        f"浏览器 CDP: {resolved} | "
        f"VNC: {host}:{vnc_port} | "
        f"noVNC: http://{host}:{novnc_port}/vnc.html"
    )
