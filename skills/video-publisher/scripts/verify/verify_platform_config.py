#!/usr/bin/env python3
"""
校验平台配置 platform_config.yaml 的完整性。

用法:
    python verify_platform_config.py --platform-config /abs/path/platform_config.yaml

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
    ("platform", ["name", "aliases", "publish_page_url", "data_dir"]),
    ("material_structure", ["fields"]),
    ("default_config", ["title_format", "auto_cover"]),
]

WARN_KEYS = [
    ("platform", ["cdp"]),
    ("platform", ["login_indicator"]),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify platform_config.yaml")
    parser.add_argument("--platform-config", required=True)
    args = parser.parse_args()
    require_abs(args.platform_config)

    config = load_yaml(args.platform_config)
    errors: list[str] = []
    warnings: list[str] = []

    for section, keys in REQUIRED_KEYS:
        sec = config.get(section, {})
        for key in keys:
            if key not in sec or sec[key] in (None, "", []):
                errors.append(f"缺少必需配置: {section}.{key}")

    fields = config.get("material_structure", {}).get("fields", {})
    if not errors:
        for name, fdef in fields.items():
            if "label" not in fdef:
                errors.append(f"material_structure.fields.{name} 缺少 label")

    for section, keys in WARN_KEYS:
        sec = config.get(section, {})
        for key in keys:
            if key not in sec or sec[key] in (None, "", {}):
                warnings.append(f"建议补充: {section}.{key}（首次流程探测后填写）")

    if errors:
        print(json.dumps({"status": "error", "msg": f"{len(errors)} 项配置缺失", "data": {"errors": errors, "warnings": warnings}},
                         ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps({"status": "ok", "msg": "平台配置完整", "data": {"warnings": warnings}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
