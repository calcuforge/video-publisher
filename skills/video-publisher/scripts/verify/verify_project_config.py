#!/usr/bin/env python3
"""
校验项目配置 project_config.yaml 的完整性。

设计约定（避免 init→verify 矛盾）：
- REQUIRED：项目骨架字段（init_project.py 初始化即具备），缺失 = 初始化出错；
- WARN：agent 按发布请求填写/发布前复验的字段（partition、cover 等），
  刚初始化时为空属预期。

用法:
    python verify_project_config.py --project-config /abs/path/project_config.yaml

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
    ("project", ["name", "project_root_path", "creation_mode"]),
    ("publish_defaults", ["title_format", "tags", "auto_cover"]),
]

MODE_VALUES = ("auto", "manual")

# agent 填写/发布前复验的字段：刚 init 时为空属预期（WARN）
WARN_KEYS = [
    ("publish_defaults", ["partition"], "agent 按发布请求填写（需在平台 material_structure 候选值内）"),
    ("publish_defaults", ["description_format"], "可选，留空则简介为空"),
    ("material", ["video_source_dir"], "agent 填写待发布视频所在目录"),
    ("cover", ["comfyui_workflow"], "封面文生图 workflow（按本机 comfyui-scheduler 工作流库填写）"),
    ("cover", ["prompt"], "封面提示词模板，支持 {title} 占位符"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify project_config.yaml")
    parser.add_argument("--project-config", required=True)
    args = parser.parse_args()
    require_abs(args.project_config)

    config = load_yaml(args.project_config)
    errors: list[str] = []
    warnings: list[str] = []

    for section, keys in REQUIRED_KEYS:
        sec = config.get(section, {})
        for key in keys:
            if key not in sec or sec[key] in (None, ""):
                errors.append(f"缺少必需配置: {section}.{key}")

    mode = config.get("project", {}).get("creation_mode", "")
    if mode and mode not in MODE_VALUES:
        errors.append(f"project.creation_mode 取值无效: {mode}（应为 auto 或 manual）")

    root = config.get("project", {}).get("project_root_path", "")
    if root:
        if "{" in root:
            # 示例/模板配置常见：{workspace}/... 占位符未替换
            warnings.append(f"project.project_root_path 含占位符，未做目录存在性检查: {root}"
                            f"（示例配置属预期；实际配置应为绝对路径）")
        elif not Path(root).exists():
            errors.append(f"项目目录不存在: {root}")

    for section, keys, hint in WARN_KEYS:
        sec = config.get(section, {})
        for key in keys:
            if key not in sec or sec[key] in (None, "", [], {}):
                warnings.append(f"建议补充: {section}.{key}（{hint}）")

    if errors:
        print(json.dumps({"status": "error", "msg": f"{len(errors)} 项配置缺失",
                          "data": {"errors": errors, "warnings": warnings}},
                         ensure_ascii=False, indent=2))
        sys.exit(1)
    print(json.dumps({"status": "ok", "msg": "项目配置完整",
                      "data": {"warnings": warnings}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
