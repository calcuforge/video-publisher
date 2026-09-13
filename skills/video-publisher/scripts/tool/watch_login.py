#!/usr/bin/env python3
"""
登录/验证码处理监控脚本 — 发布需要人工介入（登录/验证码/风控）时，agent
推送 channel 提醒后，用本脚本**后台运行**监控页面：检测到用户已处理则
推送"用户已处理"通知并退出码 0，**唤醒 agent 继续后面的发布流程**；
超时（默认 2 小时）退出码 1。

**完成判断逻辑由 agent 实现**（不同平台页面特征不同，脚本不内置固定规则）：
- 推荐：agent 依据该平台实际页面编写 `{platform}_watch_check.py`（模板见
  scripts/publish_scripts/template_watch_check.py），实现
  `check(page) -> str | bool`（返回真值/命中描述 = 已处理完成），
  用 `--check-script` 传入；判断模块放平台级
  `{platform}/publish_scripts/`，同平台所有项目复用；
- 未提供 --check-script 时回退内置简单条件（--wait-url-contains /
  --wait-selector / platform_config 的 login_indicator）作兜底。

用法:
    python watch_login.py --platform-config /abs/.../platform_config.yaml \
                          --check-script /abs/.../{platform}_watch_check.py \
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

注意：本脚本只读监控（轮询页面状态），不操作页面，与发布脚本共用
同一有头浏览器（CDP）互不干扰。
"""

from __future__ import annotations

import argparse
import importlib.util
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


def load_check_fn(script_path: str):
    """加载 agent 编写的完成判断模块（{platform}_watch_check.py）。

    约定：模块内必须有 `check(page) -> str | bool` 函数——返回真值或命中
    描述表示用户已处理完成；返回 False/None 表示继续等待。加载失败抛出
    RuntimeError（带明确提示）。
    """
    require_abs(script_path)
    spec = importlib.util.spec_from_file_location("platform_watch_check", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载判断模块: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "check"):
        raise RuntimeError(f"判断模块 {script_path} 缺少 check(page) 函数"
                           f"（模板见 scripts/publish_scripts/template_watch_check.py）")
    return module.check


def condition_met(page, args, platform_config: dict, check_fn=None) -> str:
    """返回命中的条件描述；未命中返回 ""。

    优先级：agent 自定义 check_fn（--check-script，平台特征由 agent 实现）
    > 内置简单条件（--wait-url-contains / --wait-selector / login_indicator）。
    """
    if check_fn is not None:
        try:
            result = check_fn(page)
        except Exception as exc:
            env_out("watch_check_error", f"完成判断函数异常（继续等待）: {exc}")
            return ""
        if result:
            return result if isinstance(result, str) else "自定义判断命中"
        return ""
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
    parser.add_argument("--platform-config", required=True, help="平台配置绝对路径（login_indicator，兜底用）")
    parser.add_argument("--project-config", default="", help="项目配置绝对路径（推送目标 hermes_send_targets，可选）")
    parser.add_argument("--cdp-url", default="", help="CDP 调试地址（默认按 lib/env 约定解析）")
    parser.add_argument("--account", default="",
                        help="目标账号唯一标识（多账号发布）：用该账号的合并配置监控"
                             "（storage_state/cdp 按账号隔离）；也可直接传账号合并视图的 platform-config 路径")
    parser.add_argument("--check-script", default="",
                        help="agent 编写的完成判断模块（{platform}_watch_check.py，含 check(page) 函数；"
                             "不同平台页面特征不同，由 agent 按实际页面实现；模板见 template_watch_check.py）")
    parser.add_argument("--wait-url-contains", default="", help="用户处理完成的 URL 特征（无 --check-script 时兜底）")
    parser.add_argument("--wait-selector", default="", help="用户处理完成的元素选择器（无 --check-script 时兜底）")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"最大等待秒数（默认 {DEFAULT_TIMEOUT}s = 2 小时）")
    parser.add_argument("--poll", type=int, default=3, help="轮询间隔秒数（默认 3）")
    args = parser.parse_args()

    require_abs(args.platform_config)
    platform_config = load_yaml(args.platform_config)

    # 多账号：合并账号配置（storage_state/cdp 按账号隔离），与发布脚本监控同一实例
    if args.account:
        from lib.account import resolve_account
        platform_dir = platform_config.get("platform", {}).get("data_dir", "")
        if platform_dir:
            platform_config, account_name = resolve_account(platform_dir, platform_config, account=args.account)
            if account_name:
                env_out("watch_account", f"监控目标账号: {account_name}")

    check_fn = None
    if args.check_script:
        try:
            check_fn = load_check_fn(args.check_script)
            env_out("watch_check", f"已加载 agent 自定义完成判断: {args.check_script}")
        except RuntimeError as exc:
            print(json.dumps({"status": "error", "msg": str(exc), "data": {}},
                             ensure_ascii=False, indent=2))
            sys.exit(1)

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
            hit = condition_met(page, args, platform_config, check_fn=check_fn)
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
