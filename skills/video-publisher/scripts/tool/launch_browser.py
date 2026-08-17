#!/usr/bin/env python3
"""
启动共享有头 Chromium（人机协作用）— 对齐 hermes-hitl-environment 的
chrome/launch-chromium.sh 约定。

要点（与 hermes 一致）：
- 单一持久化 profile（--user-data-dir），登录态/cookie 跨重启保留；
- CDP 调试端口供 agent 驱动（默认 9222，--remote-debugging-address=127.0.0.1）；
- 下载目录固定（--download-default-directory）；
- 启动前清理陈旧 SingletonLock（崩溃残留导致新实例直接退出）；
- 人类通过 VNC(5900) / noVNC(6080) 观察操作同一浏览器。

环境变量（与 hermes .env.example 一致，命令行参数优先）：
  CHROME_BIN / CHROME_PROFILE_DIR / CHROME_DOWNLOADS_DIR /
  CHROME_REMOTE_DEBUGGING_PORT / SCREEN_WIDTH / SCREEN_HEIGHT /
  HERMES_WEBUI_LANG / CHROME_EXTRA_FLAGS / VNC_PORT / NOVNC_PORT

用法:
    python launch_browser.py [--cdp-port 9222] [--profile-dir PATH] \
                             [--downloads-dir PATH] [--chrome-bin PATH]

浏览器为前台长驻进程（agent 用后台方式运行；Ctrl+C 退出）。
输出: 启动信息 JSON envelope（含 CDP/VNC/noVNC 接入方式）。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.env import get_env, vnc_hint
from lib.net import ensure_utf8_stdio

ensure_utf8_stdio()

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")


def find_chrome_bin() -> str:
    """解析浏览器可执行文件：CHROME_BIN env > 系统常见路径 > playwright chromium。"""
    env_bin = get_env("CHROME_BIN")
    if env_bin and shutil.which(env_bin):
        return env_bin

    candidates = ["chromium", "chromium-browser", "google-chrome", "chrome", "msedge"]
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found

    if IS_WINDOWS:
        win_paths = [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        ]
        for p in win_paths:
            if p.exists():
                return str(p)

    # playwright chromium 兜底
    try:
        import playwright
        browsers = Path(playwright.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
        for p in (browsers / "chromium-*").glob("chrome.exe" if IS_WINDOWS else "chrome"):
            if p.exists():
                return str(p)
    except Exception:
        pass

    return get_env("CHROME_BIN", "chromium")


def clean_profile_locks(profile_dir: Path) -> None:
    """清理崩溃残留的 SingletonLock，避免新实例启动即退出（同 launch-chromium.sh）。"""
    try:
        for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            (profile_dir / name).unlink(missing_ok=True)
    except OSError:
        pass


def build_command(bin_path: str, profile_dir: Path, downloads_dir: Path,
                  cdp_port: int, width: int, height: int, lang: str) -> list[str]:
    """按平台组装启动参数；Linux 使用 hermes 完整参数集，Windows/macOS 裁剪。"""
    common = [
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={cdp_port}",
        "--remote-debugging-address=127.0.0.1",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-extensions",
        f"--window-size={width},{height}",
        "--window-position=0,0",
        f"--download-default-directory={downloads_dir}",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--disable-component-update",
        "--disable-session-crashed-bubble",
        f"--lang={lang}",
    ]
    if IS_LINUX:
        common += [
            "--disable-dev-shm-usage",
            "--password-store=basic",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-gpu-sandbox",
            "--disable-gpu",
            "--ozone-platform=x11",
        ]
    elif IS_WINDOWS:
        common += ["--disable-dev-shm-usage", "--disable-gpu"]

    extra = get_env("CHROME_EXTRA_FLAGS")
    if extra:
        common += extra.split()
    return [bin_path] + common


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the shared headed Chromium (hermes-aligned)")
    parser.add_argument("--cdp-port", type=int, default=0, help="CDP 调试端口（默认取 CHROME_REMOTE_DEBUGGING_PORT，再默认 9222）")
    parser.add_argument("--profile-dir", default="", help="浏览器 profile 目录（登录态持久化）")
    parser.add_argument("--downloads-dir", default="", help="下载目录")
    parser.add_argument("--chrome-bin", default="", help="浏览器可执行文件路径")
    args = parser.parse_args()

    cdp_port = args.cdp_port or int(get_env("CHROME_REMOTE_DEBUGGING_PORT", "9222"))
    profile_dir = Path(args.profile_dir or get_env("CHROME_PROFILE_DIR") or
                       str(Path.cwd() / "video_publiser_data" / "browser_profile"))
    downloads_dir = Path(args.downloads_dir or get_env("CHROME_DOWNLOADS_DIR") or
                         str(Path.cwd() / "video_publiser_data" / "downloads"))
    bin_path = args.chrome_bin or find_chrome_bin()
    width = int(get_env("SCREEN_WIDTH", "1920"))
    height = int(get_env("SCREEN_HEIGHT", "1080"))
    lang = get_env("HERMES_WEBUI_LANG", "zh-CN")

    profile_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)
    clean_profile_locks(profile_dir)

    cdp_url = f"http://127.0.0.1:{cdp_port}"
    print(json.dumps({
        "status": "ok",
        "msg": f"启动共享 Chromium: {bin_path}",
        "data": {
            "cdp_url": cdp_url,
            "profile_dir": str(profile_dir),
            "downloads_dir": str(downloads_dir),
            "hint": vnc_hint(cdp_url=cdp_url),
        },
    }, ensure_ascii=False, indent=2), flush=True)

    cmd = build_command(bin_path, profile_dir, downloads_dir, cdp_port, width, height, lang)
    try:
        subprocess.run(cmd)
    except FileNotFoundError:
        print(json.dumps({"status": "error", "msg": f"浏览器可执行文件不存在: {bin_path}",
                          "data": {"fix": "设置 CHROME_BIN 环境变量或安装 chromium"}},
                         ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
