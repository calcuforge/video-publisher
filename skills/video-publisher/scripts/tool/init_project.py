#!/usr/bin/env python3
"""
项目检测与初始化：创建 {platform_dir}/projects/{name}/ 目录及 project_config.yaml
（从 templates/project_config_tpl.yaml 复制，回填 project.project_root_path）。

项目的概念 = 要发布视频的关键属性（如视频分类），名称用分类化命名（如 tech /
game / food / tutorial），不是具体视频标题。若同名项目已存在，追加数字后缀
（tech、tech2、tech3...）。平台目录不存在时先运行 init_platform.py。

用法:
    python init_project.py --platform-dir /abs/path/video_publiser_data/bilibili \
                           --project-dir-name tech

输出（JSON envelope）: data.project_dir / data.project_config 路径。
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

TEMPLATE_PATH = SKILL_ROOT / "templates" / "project_config_tpl.yaml"


def resolve_project_dir(projects_dir: Path, name: str) -> tuple[Path, str]:
    """Return (project_dir, final_name), appending a numeric suffix if needed."""
    candidate = projects_dir / name
    if not candidate.exists():
        return candidate, name
    n = 2
    while True:
        suffixed = f"{name}{n}"
        candidate = projects_dir / suffixed
        if not candidate.exists():
            return candidate, suffixed
        n += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize a project directory and config")
    parser.add_argument("--platform-dir", required=True, help="平台目录绝对路径（含 platform_config.yaml）")
    parser.add_argument("--project-dir-name", required=True, help="项目目录名（分类化，如 tech）")
    args = parser.parse_args()

    require_abs(args.platform_dir)
    platform_dir = Path(args.platform_dir)
    if not (platform_dir / "platform_config.yaml").exists():
        print(json.dumps({
            "status": "error",
            "msg": f"平台目录无效或未初始化: {platform_dir}（先运行 init_platform.py）",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    projects_dir = platform_dir / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    project_dir, final_name = resolve_project_dir(projects_dir, args.project_dir_name)
    project_dir.mkdir(parents=True, exist_ok=False)

    config = load_yaml(TEMPLATE_PATH)
    config["project"]["name"] = final_name
    config["project"]["project_root_path"] = str(project_dir)

    for sub in ("materials", "tmp"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

    save_yaml(config, project_dir / "project_config.yaml")

    print(json.dumps({
        "status": "ok",
        "msg": f"项目初始化完成: {final_name}",
        "data": {
            "project": final_name,
            "project_dir": str(project_dir),
            "project_config": str(project_dir / "project_config.yaml"),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
