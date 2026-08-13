#!/usr/bin/env python3
"""
平台检测与初始化：创建 {workspace}/video_publiser_data/{platform}/ 目录及
platform_config.yaml（从 templates/platform_config_tpl.yaml 复制，回填
platform.data_dir，并将 templates/default_config_tpl.yaml 合并为 default_config）。

内置平台别名映射（--platform 支持别名输入）：
- bilibili:      [B站, 哔哩哔哩, bilibili]
- douyin:        [抖音, douyin]
- wechat_channels: [微信视频号, 视频号, wechat_channels]
- youtube:       [youtube, 油管, youtu]

不认识的平台名直接作为新平台标识创建（agent 随后按 references/platform-integration.md
补充平台配置与发布脚本）。已存在的平台目录视为初始化完成，不会覆盖现有配置。

用法:
    python init_platform.py --workspace /abs/path --platform bilibili

输出（JSON envelope）: data.platform_dir / data.platform_config 路径。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
SKILL_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.net import ensure_utf8_stdio, require_abs
from lib.yamlutil import load_yaml, save_yaml

ensure_utf8_stdio()

TEMPLATE_PATH = SKILL_ROOT / "templates" / "platform_config_tpl.yaml"
DEFAULT_CONFIG_TEMPLATE = SKILL_ROOT / "templates" / "default_config_tpl.yaml"

PLATFORM_ALIASES: dict[str, list[str]] = {
    "bilibili": ["B站", "哔哩哔哩", "bilibili", "b站"],
    "douyin": ["抖音", "douyin", "抖"],
    "wechat_channels": ["微信视频号", "视频号", "wechat_channels", "wechat"],
    "youtube": ["youtube", "油管", "you"],
}


def normalize_platform(raw: str) -> str:
    """将用户输入的平台名归一化为平台标识（小写字母下划线）。"""
    for canonical, aliases in PLATFORM_ALIASES.items():
        if raw.strip().lower() in [a.lower() for a in aliases]:
            return canonical
    normalized = raw.strip().lower().replace(" ", "_")
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize a platform directory and config")
    parser.add_argument("--workspace", default="", help="工作区根目录（含 video_publiser_data/）")
    parser.add_argument("--platform", required=True, help="平台名或别名，如 bilibili / B站 / 抖音")
    args = parser.parse_args()

    from init_workspace import resolve_workspace
    workspace = resolve_workspace(args.workspace)
    data_root = workspace / "video_publiser_data"
    data_root.mkdir(parents=True, exist_ok=True)

    platform_id = normalize_platform(args.platform)
    platform_dir = data_root / platform_id
    config_path = platform_dir / "platform_config.yaml"

    created = False
    if not config_path.exists():
        config = load_yaml(TEMPLATE_PATH)
        config.setdefault("platform", {})["name"] = platform_id
        config["platform"]["data_dir"] = str(platform_dir)
        default_seed = load_yaml(DEFAULT_CONFIG_TEMPLATE)
        config["default_config"] = {**default_seed, **(config.get("default_config") or {})}
        platform_dir.mkdir(parents=True, exist_ok=True)
        save_yaml(config, config_path)
        created = True

    scripts_dir = platform_dir / "publish_scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    print(json.dumps({
        "status": "ok",
        "msg": f"平台 {'初始化' if created else '已存在'}: {platform_id}",
        "data": {
            "platform": platform_id,
            "platform_dir": str(platform_dir),
            "platform_config": str(config_path),
            "publish_scripts_dir": str(scripts_dir),
            "created": created,
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
