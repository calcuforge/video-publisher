#!/usr/bin/env python3
"""
执行发布脚本：加载物料数据与平台配置，调用平台专属发布脚本
（{platform_dir}/publish_scripts/{platform}_publish.py）完成浏览器自动化发布。

平台发布脚本由 agent 在"首次发布流程"中基于 probe_page.py 的探测结果编写
（模板见 scripts/publish_scripts/template_publish.py），遵循可复用原则：
同一平台的所有项目共用一份脚本，发布参数全部来自 materials.yaml 与配置。

发布脚本通过 CDP 连接有头浏览器（用户可经 VNC 观察/介入）。遇到登录、验证码
等情况时脚本会阻塞等待并输出 @ENV@ 人机协作提示，agent 必须将其转达给用户。

用法:
    python publish_video.py --platform-config /abs/.../platform_config.yaml \
                            --project-config /abs/.../project_config.yaml \
                            --material /abs/.../materials.yaml \
                            [--script /abs/.../{platform}_publish.py] \
                            [--cdp-url http://127.0.0.1:9222]

输出: 透传平台发布脚本的 JSON envelope 输出。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.env import get_env
from lib.net import ensure_utf8_stdio, require_abs
from lib.yamlutil import load_yaml

ensure_utf8_stdio()


def resolve_script(platform_config_path: Path, cli_script: str) -> Path:
    if cli_script:
        require_abs(cli_script)
        return Path(cli_script)

    platform_config = load_yaml(platform_config_path)
    configured = platform_config.get("publish_script", "")
    if configured and Path(configured).exists():
        return Path(configured)

    platform_dir = Path(platform_config.get("platform", {}).get("data_dir", ""))
    name = platform_config.get("platform", {}).get("name", "")
    candidate = platform_dir / "publish_scripts" / f"{name}_publish.py"
    if candidate.exists():
        return candidate
    raise RuntimeError(
        f"未找到平台发布脚本 {candidate}（platform_config.yaml 的 publish_script 也为空）。\n"
        f"首次发布需要先完成'发布物料数据结构整理、编写该平台自动化发布脚本'步骤：\n"
        f"1. python probe_page.py --url <发布页> --output <dump.md> 探测 DOM 结构\n"
        f"2. 参考 scripts/publish_scripts/template_publish.py 编写 {name}_publish.py\n"
        f"3. 回填 platform_config.yaml 的 publish_script 字段"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute the platform publish script")
    parser.add_argument("--platform-config", required=True, help="平台配置绝对路径")
    parser.add_argument("--project-config", required=True, help="项目配置绝对路径")
    parser.add_argument("--material", required=True, help="物料数据 materials.yaml 绝对路径")
    parser.add_argument("--script", default="", help="平台发布脚本绝对路径（默认按配置解析）")
    parser.add_argument("--cdp-url", default="", help="CDP 调试地址（默认取平台配置）")
    args = parser.parse_args()

    require_abs(args.platform_config, args.project_config, args.material)
    if not Path(args.material).exists():
        print(json.dumps({"status": "error", "msg": f"物料数据不存在: {args.material}", "data": {}},
                         ensure_ascii=False, indent=2))
        sys.exit(1)

    platform_config = load_yaml(args.platform_config)
    cdp = platform_config.get("platform", {}).get("cdp", {})
    # 解析优先级：--cdp-url 参数 > 环境变量 PLAYWRIGHT_CDP_URL（hermes 约定）> 平台配置 > 默认
    cdp_url = args.cdp_url or get_env("PLAYWRIGHT_CDP_URL") or \
        f"http://{cdp.get('host', '127.0.0.1')}:{cdp.get('port', 9222)}"

    try:
        script = resolve_script(Path(args.platform_config), args.script)
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "msg": str(exc), "data": {"self_heal": "publish_script_missing"}},
                         ensure_ascii=False, indent=2))
        sys.exit(1)

    cmd = [
        sys.executable, str(script),
        "--platform-config", args.platform_config,
        "--project-config", args.project_config,
        "--material", args.material,
        "--cdp-url", cdp_url,
    ]
    # 透传子进程输出（含 @ENV@ 人机协作行），退出码一致
    result = subprocess.run(cmd, timeout=3600)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
