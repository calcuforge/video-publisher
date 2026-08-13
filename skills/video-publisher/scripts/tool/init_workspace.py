#!/usr/bin/env python3
"""
确保工作区数据目录 video_publiser_data 存在。

所有发布相关文件（平台配置、项目配置、物料数据、发布脚本）必须位于
{workspace}/video_publiser_data 下，禁止写到系统临时目录或工作区之外。

workspace 解析顺序：--workspace 参数 > 环境变量 VIDEO_PUBLISHER_WORKSPACE
> 当前工作目录。

用法:
    python init_workspace.py --workspace /abs/path

输出（JSON envelope）: data.data_dir 为视频发布数据根目录绝对路径。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.net import ensure_utf8_stdio, require_abs

ensure_utf8_stdio()

DATA_DIR_NAME = "video_publiser_data"


def resolve_workspace(cli_workspace: str) -> Path:
    workspace = cli_workspace or os.environ.get("VIDEO_PUBLISHER_WORKSPACE", "")
    if workspace:
        require_abs(workspace)
        return Path(workspace)
    return Path.cwd()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ensure video_publiser_data workspace exists")
    parser.add_argument("--workspace", default="", help="工作区根目录（含 video_publiser_data/）")
    args = parser.parse_args()

    workspace = resolve_workspace(args.workspace)
    data_dir = workspace / DATA_DIR_NAME
    data_dir.mkdir(parents=True, exist_ok=True)

    print(json.dumps({
        "status": "ok",
        "msg": f"发布数据根目录就绪: {data_dir}",
        "data": {"workspace": str(workspace), "data_dir": str(data_dir)},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
