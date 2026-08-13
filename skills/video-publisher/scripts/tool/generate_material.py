#!/usr/bin/env python3
"""
物料数据生成：为一次发布准备封面图片与标题/简介/标签/分区等文本物料。

流程:
1. ffprobe 探测视频文件（时长、分辨率、大小）写入物料元数据
2. 若启用 auto_cover 且配置了 comfyui_workflow，通过 comfyui-scheduler
   文生图生成封面（提示词来自 project_config.yaml cover.prompt，支持
   {title} {topic} 占位符）
3. 依据平台 material_structure.fields + 项目 publish_defaults + 平台
   default_config，组装 materials.yaml（agent 随后按需编辑文本字段；
   手动模式下必须先经用户审核）
4. 自动模式直接使用组装结果；manual 模式下 agent 必须暂停等待用户审核

物料目录: {project_dir}/materials/{YYYYMMDD}_{video_name}/

用法:
    python generate_material.py --project-config /abs/.../project_config.yaml \
                                --platform-config /abs/.../platform_config.yaml \
                                --video-file /abs/path/video.mp4 \
                                [--output-dir /abs/...] [--no-cover]

输出（JSON envelope）: data.material_dir / data.materials_yaml / data.cover_file
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.net import ensure_utf8_stdio, require_abs
from lib.yamlutil import load_yaml, save_yaml

ensure_utf8_stdio()


def ffprobe_metadata(video_file: Path) -> dict:
    """探测视频时长(秒)/分辨率/大小。ffprobe 缺失或探测失败时返回空 dict（不致命）。"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,duration",
             "-show_entries", "format=duration",
             "-of", "json", str(video_file)],
            capture_output=True, text=True, timeout=120,
        )
        data = json.loads(result.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        duration = stream.get("duration") or fmt.get("duration")
        return {
            "duration_sec": round(float(duration), 1) if duration else None,
            "width": stream.get("width"),
            "height": stream.get("height"),
            "size_bytes": video_file.stat().st_size,
        }
    except Exception:
        return {}


def run_comfyui_t2i(workflow_code: str, payload: dict, output_path: str, timeout: int = 900) -> str:
    """通过 comfyui-scheduler CLI 执行文生图任务，下载产物到 output_path。"""
    inputs_json = json.dumps(payload, ensure_ascii=False)
    cmd = ["comfyui-scheduler", "run", "-w", workflow_code, "-i", inputs_json]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"comfyui-scheduler 任务超时（{timeout}s）: {workflow_code}")
    except FileNotFoundError:
        raise RuntimeError("comfyui-scheduler 不在 PATH 上，请先安装（见 SKILL.md 依赖章节）")

    if result.returncode != 0:
        raise RuntimeError(f"comfyui-scheduler 失败: {result.stderr or result.stdout[:300]}")

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"comfyui-scheduler 输出非 JSON: {result.stdout[:200]}")

    if output.get("status") != "ok":
        raise RuntimeError(f"工作流执行错误: {output.get('msg', 'unknown')}")

    files = output.get("data", {}).get("files", [])
    if not files:
        raise RuntimeError("工作流未返回输出文件")

    from lib.net import download_file
    download_file(files[0].get("url", ""), output_path)
    return output_path


def render_template(template: str, **ctx) -> str:
    """替换 {name} 占位符；未提供的占位符原样保留。"""
    def repl(m: re.Match) -> str:
        return str(ctx.get(m.group(1), m.group(0)))
    return re.sub(r"\{(\w+)\}", repl, template)


def build_material(
    project_config: dict,
    platform_config: dict,
    video_file: Path,
    cover_file: str,
    metadata: dict,
    ctx: dict,
) -> dict:
    """按 项目 publish_defaults > 平台 default_config > 字段定义 组装物料数据。"""
    pub = project_config.get("publish_defaults", {})
    plat_default = platform_config.get("default_config", {})
    fields = platform_config.get("material_structure", {}).get("fields", {})

    def pick(keys: list[str], fallback=None):
        for src in (pub, plat_default):
            for k in keys:
                if k in src and src[k] not in (None, ""):
                    return src[k]
        return fallback

    title = render_template(str(pick(["title_format"], "{video_name}")), **ctx)
    description = render_template(str(pick(["description_format"], "")), **ctx)

    material: dict = {
        "material": {
            "video_file": str(video_file),
            "video_metadata": metadata,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "fields": {},
        }
    }
    for field_name, field_def in fields.items():
        kind = field_def.get("kind", "text")
        value = ""
        if kind == "title" or (kind == "text" and field_name == "title"):
            value = title
        elif kind == "textarea" or (kind == "text" and field_name == "description"):
            value = description
        elif kind == "tags":
            value = pick(["tags"], [])
        elif kind == "select":
            value = pick(["partition"], "")
        elif kind == "image":
            value = cover_file
        elif kind == "video":
            value = str(video_file)
        elif kind == "checkbox":
            value = False
        elif kind == "extra":
            value = pick([field_name], "")
        material["material"]["fields"][field_name] = value

    material["material"]["mode"] = project_config.get("project", {}).get("creation_mode", "auto")
    return material


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate publish materials (cover + text) for a video")
    parser.add_argument("--project-config", required=True, help="项目配置绝对路径")
    parser.add_argument("--platform-config", required=True, help="平台配置绝对路径")
    parser.add_argument("--video-file", required=True, help="待发布视频文件绝对路径")
    parser.add_argument("--output-dir", default="", help="物料输出目录（默认 {project}/materials/{date}_{video_name}）")
    parser.add_argument("--no-cover", action="store_true", help="跳过封面生成")
    args = parser.parse_args()

    require_abs(args.project_config, args.platform_config, args.video_file)
    project_config = load_yaml(args.project_config)
    platform_config = load_yaml(args.platform_config)

    video_file = Path(args.video_file)
    if not video_file.exists():
        print(json.dumps({"status": "error", "msg": f"视频文件不存在: {video_file}", "data": {}},
                         ensure_ascii=False, indent=2))
        sys.exit(1)

    project_dir = Path(project_config.get("project", {}).get("project_root_path", ""))
    video_name = video_file.stem
    date_str = datetime.now().strftime("%Y%m%d")
    output_dir = Path(args.output_dir) if args.output_dir else project_dir / "materials" / f"{date_str}_{video_name}"
    output_dir.mkdir(parents=True, exist_ok=True)

    ctx = {
        "video_name": video_name,
        "date": date_str,
        "project": project_config.get("project", {}).get("name", ""),
    }

    metadata = ffprobe_metadata(video_file)

    # ---- 封面生成（comfyui-scheduler 文生图）----
    cover_file = ""
    auto_cover = project_config.get("publish_defaults", {}).get("auto_cover",
                 platform_config.get("default_config", {}).get("auto_cover", True))
    cover_cfg = project_config.get("cover", {})
    if auto_cover and not args.no_cover and cover_cfg.get("comfyui_workflow"):
        prompt = render_template(str(cover_cfg.get("prompt", "")), **ctx)
        payload = {
            "prompt": prompt,
            "negative_prompt": cover_cfg.get("negative_prompt", ""),
            "width": cover_cfg.get("width", 1920),
            "height": cover_cfg.get("height", 1080),
            "seed": cover_cfg.get("seed", 0),
        }
        cover_file = str(output_dir / "cover.png")
        print(json.dumps({"status": "info", "msg": "正在通过 comfyui-scheduler 生成封面...",
                          "data": {"workflow": cover_cfg["comfyui_workflow"], "prompt": prompt}},
                         ensure_ascii=False), flush=True)
        try:
            run_comfyui_t2i(cover_cfg["comfyui_workflow"], payload, cover_file)
        except RuntimeError as exc:
            print(json.dumps({"status": "warning", "msg": f"封面生成失败（继续执行）: {exc}", "data": {}},
                             ensure_ascii=False), flush=True)
            cover_file = ""
    elif auto_cover and not cover_cfg.get("comfyui_workflow"):
        print(json.dumps({"status": "warning",
                          "msg": "auto_cover 已启用但 cover.comfyui_workflow 未配置，跳过封面生成。"
                                 "agent 应参考 references/platform-integration.md 补充配置或手动准备封面。",
                          "data": {}}, ensure_ascii=False), flush=True)

    material = build_material(project_config, platform_config, video_file, cover_file, metadata, ctx)
    materials_yaml = output_dir / "materials.yaml"
    save_yaml(material, materials_yaml)

    print(json.dumps({
        "status": "ok",
        "msg": "物料数据生成完成",
        "data": {
            "material_dir": str(output_dir),
            "materials_yaml": str(materials_yaml),
            "cover_file": cover_file,
            "video_metadata": metadata,
            "mode": material["material"]["mode"],
            "note": "manual 模式下 agent 必须先让用户审核 materials.yaml 再继续",
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
