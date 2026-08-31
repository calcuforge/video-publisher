#!/usr/bin/env python3
"""
登录/验证码处理监控脚本 — 发布需要人工介入（登录/验证码/风控）时，agent
推送 channel 提醒后，用本脚本**后台运行**监控页面：检测到用户已处理则
推送"用户已处理"通知并退出码 0，**唤醒 agent 继续后面的发布流程**；
超时（默认 2 小时）退出码 1。

监控条件优先级：
1. --wait-url-contains / --wait-selector（验证码等处理完成的**具体特征**，
   与发布脚本 human_wait 用的同一条件，任一命中即视为已处理）；
2. 未指定时用 platform_config 的 login_indicator（登录后 URL 特征/已登录
   元素特征）。

用法:
    python watch_login.py --platform-config /abs/.../platform_config.yaml \
                          [--project-config /abs/.../project_config.yaml] \
                          [--cdp-url http://127.0.0.1:9222] \
                          [--wait-url-contains <URL特征>] [--wait-selector <选择器>] \
                          [--timeout 7200] [--poll 3]

行为（@ENV@ 输出，供 agent 解析）:
- 检测到用户已处理 → @ENV@ watch_done（含完成条件与页面 URL），经 hermes
  channel 推送"用户已处理，发布流程继续"通知（目标：--project-config 的
  publish_defaults.hermes_send_targets，空 = 全部已发现 channel）→ 退出码 0；
- 超时 → @ENV@ watch_timeout → 退出码 1（agent 需重新提醒用户或人工介入）；
- 每 60s 输出 @ENV@ watch_waiting 心跳。

注意：本脚本只读监控（轮询 URL/元素存在性），不操作页面，与发布脚本共用
同一有头浏览器（CDP）互不干扰。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.cdp import check_logged_in, connect_browser, env_out, new_page
from lib.net import ensure_utf8_stdio, require_abs
from lib.yamlutil import load_yaml

ensure_utf8_stdio()

DEFAULT_TIMEOUT = 7200  # 2 小时


def condition_met(page, args, platform_config: dict) -> str:
    """返回命中的条件描述；未命中返回 ""。"""
    if args.wait_url_contains and args.wait_url_contains in (page.url or ""):
        return f"URL 包含 {args.wait_url_contains}"
    if args.wait_selector:
        try:
            if page.locator(args.wait_selector).count() > 0:
                return f"选择器可见 {args.wait_selector}"
        except Exception:
            pass
    if not args.wait_url_contains and not args.wait_selector:
        if check_logged_in(page, platform_config):
            return "login_indicator 命中（已登录）"
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch the publish page until the user handles login/captcha")
    parser.add_argument("--platform-config", required=True, help="平台配置绝对路径（login_indicator）")
    parser.add_argument("--project-config", default="", help="项目配置绝对路径（推送目标 hermes_send_targets，可选）")
    parser.add_argument("--cdp-url", default="", help="CDP 调试地址（默认按 lib/env 约定解析）")
    parser.add_argument("--wait-url-contains", default="", help="用户处理完成的 URL 特征（可选）")
    parser.add_argument("--wait-selector", default="", help="用户处理完成的元素选择器（可选）")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"最大等待秒数（默认 {DEFAULT_TIMEOUT}s = 2 小时）")
    parser.add_argument("--poll", type=int, default=3, help="轮询间隔秒数（默认 3）")
    args = parser.parse_args()

    require_abs(args.platform_config)
    platform_config = load_yaml(args.platform_config)

    targets = []
    if args.project_config:
        require_abs(args.project_config)
        targets = load_yaml(args.project_config).get("publish_defaults", {}).get("hermes_send_targets", []) or []

    try:
        browser = connect_browser(args.cdp_url)
        url = platform_config.get("platform", {}).get("publish_page_url", "")
        page = new_page(browser, url, platform_config=platform_config)
        env_out("watch_start", f"开始监控页面: {page.url}（超时 {args.timeout}s）")

        deadline = time.monotonic() + args.timeout
        last_heartbeat = time.monotonic()
        while time.monotonic() < deadline:
            hit = condition_met(page, args, platform_config)
            if hit:
                env_out("watch_done", f"用户已完成处理（{hit}），唤醒 agent 继续发布流程", page_url=page.url, hit=hit)
                from lib.notify import notify_human_collab
                notify_human_collab(f"用户已完成{hit}，发布流程继续（无需再操作）", targets=targets)
                browser.close()
                sys.exit(0)
            if time.monotonic() - last_heartbeat > 60:
                last_heartbeat = time.monotonic()
                env_out("watch_waiting", f"仍在等待用户处理（已等待 {int(time.monotonic() + args.timeout - deadline)}s）")
            time.sleep(args.poll)

        env_out("watch_timeout", f"等待用户处理超时（{args.timeout}s）。请 agent 重新提醒用户或人工介入", page_url=page.url)
        browser.close()
        sys.exit(1)
    except Exception as exc:
        print(json.dumps({"status": "error", "msg": f"监控失败: {exc}", "data": {}},
                         ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
