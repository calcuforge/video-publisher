#!/usr/bin/env python3
"""
校验平台配置 platform_config.yaml 的完整性。

设计约定（避免 init→verify 矛盾）：
- REQUIRED：平台骨架字段（init_platform.py 初始化即具备），缺失 = 初始化出错；
- WARN：首次流程探测/填写后才有值的字段（publish_page_url、login_indicator、
  publish_script 等），刚初始化时为空属预期，发布前应复验。

用法:
    python verify_platform_config.py --platform-config /abs/path/platform_config.yaml

输出（JSON envelope）: status ok/error + data.errors + data.warnings。
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
    ("platform", ["name", "aliases", "data_dir"]),
    ("material_structure", ["fields"]),
    ("default_config", ["title_format", "auto_cover"]),
]

# 首次流程探测/填写后才有值的字段：刚 init 时为空属预期（WARN），
# 发布前复验应无警告。
WARN_KEYS = [
    ("platform", ["publish_page_url"], "首次流程步骤 4a 用 probe_page.py 探测后填写"),
    ("platform", ["login_indicator"], "首次流程步骤 4a 探测登录特征后填写"),
    ("platform", ["cdp"], "通常无需修改，可保留默认"),
    ("platform", ["login"], "storageState 路径，留空用默认 {data_dir}/storage_state.json"),
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

    for section, keys, hint in WARN_KEYS:
        sec = config.get(section, {})
        for key in keys:
            if key not in sec or sec[key] in (None, "", {}, []):
                warnings.append(f"建议补充: {section}.{key}（{hint}）")

    if errors:
        print(json.dumps({"status": "error", "msg": f"{len(errors)} 项配置缺失",
                          "data": {"errors": errors, "warnings": warnings}},
                         ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps({"status": "ok", "msg": "平台配置完整",
                      "data": {"warnings": warnings}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
