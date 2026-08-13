#!/usr/bin/env python3
"""
校验项目配置 project_config.yaml 的完整性。

用法:
    python verify_project_config.py --project-config /abs/path/project_config.yaml

输出（JSON envelope）: status ok/error + data.errors。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.net import ensure_utf8_stdio, require_abs
from lib.yamlutil import load_yaml

ensure_utf8_stdio()

REQUIRED_KEYS = [
    ("project", ["name", "project_root_path", "creation_mode"]),
    ("publish_defaults", ["title_format", "tags", "partition", "auto_cover"]),
]

MODE_VALUES = ("auto", "manual")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify project_config.yaml")
    parser.add_argument("--project-config", required=True)
    args = parser.parse_args()
    require_abs(args.project_config)

    config = load_yaml(args.project_config)
    errors: list[str] = []

    for section, keys in REQUIRED_KEYS:
        sec = config.get(section, {})
        for key in keys:
            if key not in sec or sec[key] in (None, ""):
                errors.append(f"缺少必需配置: {section}.{key}")

    mode = config.get("project", {}).get("creation_mode", "")
    if mode and mode not in MODE_VALUES:
        errors.append(f"project.creation_mode 取值无效: {mode}（应为 auto 或 manual）")

    root = Path(config.get("project", {}).get("project_root_path", ""))
    if str(root) and not root.exists():
        errors.append(f"项目目录不存在: {root}")

    if errors:
        print(json.dumps({"status": "error", "msg": f"{len(errors)} 项配置缺失", "data": {"errors": errors}},
                         ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps({"status": "ok", "msg": "项目配置完整", "data": {}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
