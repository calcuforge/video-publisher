#!/usr/bin/env python3
"""
发布页 DOM 结构探测：通过 CDP 调用有头浏览器打开发布页，输出页面结构
（URL、标题、iframe、所有可见的输入/文本域/下拉/按钮/上传控件及其属性），
供 agent 分析表单结构、编写平台自动化发布脚本、整理物料数据结构。

人机协作：若 --wait-url-contains 或 --wait-selector 给定，脚本打开页面后
阻塞等待该条件出现（如登录成功后跳转到发布页），并输出 VNC 提示，等待
用户通过 VNC 在有头浏览器中完成登录/验证码等操作。

用法:
    python probe_page.py --cdp-url http://127.0.0.1:9222 \
                         --url https://member.bilibili.com/platform/upload/video/frame \
                         --output /abs/path/dump.md \
                         [--wait-url-contains member.bilibili.com/platform/upload] \
                         [--timeout 600]

输出: 探测结果 markdown 写入 --output；JSON envelope 摘要打印到 stdout。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.net import ensure_utf8_stdio, require_abs

ensure_utf8_stdio()


def format_dump(dump: dict) -> str:
    lines = [
        f"# 页面结构探测",
        f"- URL: {dump['url']}",
        f"- 标题: {dump['title']}",
        f"- frame 数量: {len(dump['frames'])}",
        "",
    ]
    for fi, frame in enumerate(dump["frames"]):
        lines.append(f"## Frame {fi}: name={frame['name'] or '(主)'} url={frame['url']}")
        lines.append("")
        if not frame["elements"]:
            lines.append("（无可视元素）")
            lines.append("")
            continue
        lines.append("| 标签 | 属性 |")
        lines.append("|------|------|")
        for el in frame["elements"]:
            if el["tag"] == "a":
                attr = f"text={el['text']!r} href={el['href']}"
            else:
                parts = []
                for key in ("name", "id", "type", "placeholder", "class"):
                    if el.get(key):
                        parts.append(f"{key}={el[key]!r}")
                if el.get("label"):
                    parts.append(f"label={el['label']!r}")
                attr = ", ".join(parts)
            lines.append(f"| `{el['tag']}` | {attr} |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe a publish page DOM via CDP")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="CDP 调试地址")
    parser.add_argument("--url", required=True, help="要打开的发布页 URL")
    parser.add_argument("--output", required=True, help="探测结果输出文件（绝对路径，markdown）")
    parser.add_argument("--wait-url-contains", default="", help="打开页面后阻塞等待 URL 包含该字符串（登录跳转）")
    parser.add_argument("--wait-selector", default="", help="打开页面后阻塞等待该选择器出现")
    parser.add_argument("--timeout", type=int, default=600, help="人机协作等待超时（秒）")
    args = parser.parse_args()

    require_abs(args.output)
    from lib.cdp import (
        connect_browser, dump_page, env_out, human_wait_selector, human_wait_url, new_page,
    )

    if args.wait_url_contains and args.wait_selector:
        print(json.dumps({"status": "error", "msg": "--wait-url-contains 与 --wait-selector 只能指定其一", "data": {}},
                         ensure_ascii=False))
        sys.exit(1)

    try:
        browser = connect_browser(args.cdp_url)
        page = new_page(browser, args.url)
        env_out("probe", f"已打开页面: {args.url}")

        if args.wait_url_contains:
            human_wait_url(page, "请在浏览器中完成登录/验证，等待跳转到发布页", args.wait_url_contains, timeout=args.timeout)
        elif args.wait_selector:
            human_wait_selector(page, "请在浏览器中完成登录/验证，等待发布表单出现", args.wait_selector, timeout=args.timeout)

        dump = dump_page(page)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(format_dump(dump), encoding="utf-8")

        browser.close()
        print(json.dumps({
            "status": "ok",
            "msg": f"页面结构探测完成，共 {sum(len(f['elements']) for f in dump['frames'])} 个元素",
            "data": {"output": args.output, "url": dump["url"], "title": dump["title"]},
        }, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "error", "msg": f"探测失败: {exc}", "data": {}},
                         ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
