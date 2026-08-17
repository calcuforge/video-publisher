#!/usr/bin/env python3
"""
运行环境检查：验证 video-publisher skill 的全部前置条件。

检查项：
- Python >= 3.10
- Python 包: requests / pyyaml / playwright
- ffmpeg / ffprobe 在 PATH 上
- comfyui-scheduler CLI 已安装
- playwright chromium 浏览器已安装（有头模式基础）
- 工作区 video_publiser_data 目录存在（--workspace 提供时）
- CDP 调试端口可达（--cdp-url 提供时，仅警告不报错）

用法:
    python check_prereqs.py
    python check_prereqs.py --workspace /abs/path
    python check_prereqs.py --cdp-url http://127.0.0.1:9222
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

from lib.net import ensure_utf8_stdio

ensure_utf8_stdio()

PLAYWRIGHT_BROWSER_DIRS = [
    # Windows
    Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright",
    # Linux / macOS
    Path.home() / ".cache" / "ms-playwright",
    Path.home() / "Library" / "Caches" / "ms-playwright",
]


def check_python() -> list[str]:
    v = sys.version_info
    if v < (3, 10):
        return [f"Python >= 3.10 required, found {v.major}.{v.minor}.{v.micro}"]
    return []


def check_python_packages() -> list[str]:
    errors = []
    for pkg, pip_name in (("requests", "requests"), ("yaml", "pyyaml"), ("playwright", "playwright")):
        try:
            __import__(pkg)
        except ImportError:
            errors.append(f"Python 包 '{pip_name}' 未安装。运行: pip install -r requirements.txt")
    return errors


def check_binaries() -> list[str]:
    errors = []
    for name in ("ffmpeg", "ffprobe", "comfyui-scheduler"):
        if shutil.which(name) is None:
            errors.append(f"'{name}' 不在 PATH 上")
    return errors


def check_playwright_browser() -> list[str]:
    """Check for an installed chromium via playwright's ms-playwright dirs."""
    found = False
    for base in PLAYWRIGHT_BROWSER_DIRS:
        if not base or not base.exists():
            continue
        for entry in base.iterdir():
            if entry.is_dir() and ("chromium" in entry.name.lower() or "chrome" in entry.name.lower()):
                found = True
                break
    if not found:
        return ["playwright chromium 浏览器未安装。运行: playwright install chromium"]
    return []


def check_workspace(workspace: str) -> list[str]:
    if not workspace:
        return []
    data_dir = Path(workspace) / "video_publiser_data"
    if not data_dir.exists():
        return [f"工作区数据目录不存在: {data_dir}。运行: python init_workspace.py --workspace {workspace}"]
    return []


def check_cdp(cdp_url: str) -> list[str]:
    if not cdp_url:
        cdp_url = os.environ.get("PLAYWRIGHT_CDP_URL", "")
    if not cdp_url:
        return []
    from lib.cdp import check_cdp_port
    try:
        from urllib.parse import urlparse
        parsed = urlparse(cdp_url)
        host, port = parsed.hostname or "127.0.0.1", parsed.port or 9222
        if not check_cdp_port(host, port):
            return [f"CDP 调试端口不可达: {cdp_url}（不影响本检查通过，发布前需启动有头浏览器，见 references/human-collab.md）"]
    except Exception:
        pass
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Check video-publisher prerequisites")
    parser.add_argument("--workspace", default="", help="工作区根目录（含 video_publiser_data/）")
    parser.add_argument("--cdp-url", default="", help="CDP 调试地址，如 http://127.0.0.1:9222")
    args = parser.parse_args()

    from lib.net import require_abs
    if args.workspace:
        require_abs(args.workspace)

    all_errors: list[str] = []
    all_errors.extend(check_python())
    all_errors.extend(check_python_packages())
    all_errors.extend(check_binaries())
    all_errors.extend(check_playwright_browser())
    all_errors.extend(check_workspace(args.workspace))
    all_errors.extend(check_cdp(args.cdp_url))

    # CDP 不可达仅是警告
    warnings = [e for e in all_errors if "CDP" in e]
    errors = [e for e in all_errors if "CDP" not in e]

    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"{len(errors)} 项前置条件未满足",
            "data": {"errors": errors, "warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    print(json.dumps({
        "status": "ok",
        "msg": "所有前置条件满足",
        "data": {"warnings": warnings},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
