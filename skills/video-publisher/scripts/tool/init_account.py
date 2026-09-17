#!/usr/bin/env python3
"""
账号初始化：创建 {platform_dir}/accounts/{name}/ 账号目录及 account_config.yaml
（从 templates/account_config_tpl.yaml 复制，回填 name/account_dir/
storage_state_path）。

- 账号唯一标识 = 目录名（小写英文数字下划线），重名报错并列出已有账号
- **默认共用模式**：所有账号连同一个浏览器实例（平台 CDP 端口），靠独立
  storageState 隔离 cookie（框架自动为账号创建隔离 context）——回填的
  cdp.port 即平台端口，profile_dir 留空
- 如需完全隔离（独立指纹防风控关联），手改 account_config.yaml 的
  cdp.port（不同端口）与 cdp.profile_dir，并用 launch_browser.py 按该
  端口/profile 启动独立实例
- 已存在的账号视为初始化完成（不覆盖现有配置）

用法:
    python init_account.py --platform-dir /abs/.../video_publiser_data/bilibili \
                           --account account_b [--display-name 小号B] [--aliases 小号B,b号]

输出（JSON envelope）: data.account_dir / data.account_config / data.cdp_port。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
SKILL_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.account import accounts_dir, list_accounts, normalize_account
from lib.net import ensure_utf8_stdio, require_abs
from lib.yamlutil import load_yaml, save_yaml

ensure_utf8_stdio()

TEMPLATE_PATH = SKILL_ROOT / "templates" / "account_config_tpl.yaml"
DEFAULT_CDP_PORT = 9222  # 平台默认浏览器实例端口（共用模式）


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize an account directory and config")
    parser.add_argument("--platform-dir", required=True, help="平台目录绝对路径（含 platform_config.yaml）")
    parser.add_argument("--account", required=True, help="账号唯一标识（小写英文数字下划线）")
    parser.add_argument("--display-name", default="", help="展示名（如 小号B）")
    parser.add_argument("--aliases", default="", help="逗号分隔的指令匹配别名（如 小号B,b号）")
    args = parser.parse_args()

    require_abs(args.platform_dir)
    platform_dir = Path(args.platform_dir)
    if not (platform_dir / "platform_config.yaml").exists():
        print(json.dumps({"status": "error",
                          "msg": f"平台目录无效或未初始化: {platform_dir}（先运行 init_platform.py）",
                          "data": {}}, ensure_ascii=False, indent=2))
        sys.exit(1)

    if not TEMPLATE_PATH.exists():
        print(json.dumps({"status": "error", "msg": f"模板不存在: {TEMPLATE_PATH}", "data": {}},
                         ensure_ascii=False, indent=2))
        sys.exit(1)

    name = normalize_account(args.account)
    if not name:
        print(json.dumps({"status": "error", "msg": "账号名不能为空", "data": {}}, ensure_ascii=False))
        sys.exit(1)

    existing = [a["name"] for a in list_accounts(platform_dir)]
    account_dir = accounts_dir(platform_dir) / name
    config_path = account_dir / "account_config.yaml"

    created = False
    if not config_path.exists():
        if name in existing:
            print(json.dumps({"status": "error",
                              "msg": f"账号已存在: {name}（可用账号: {', '.join(existing)}）",
                              "data": {"available": existing}},
                             ensure_ascii=False, indent=2))
            sys.exit(1)
        # 共用模式：账号连平台同一浏览器实例（CDP 端口取平台配置，默认 9222）
        platform_cfg = load_yaml(platform_dir / "platform_config.yaml") or {}
        port = (platform_cfg.get("platform", {}).get("cdp", {}) or {}).get("port", DEFAULT_CDP_PORT)

        config = load_yaml(TEMPLATE_PATH)
        account = config.setdefault("account", {})
        account["name"] = name
        account["account_dir"] = str(account_dir)
        if args.display_name:
            account["display_name"] = args.display_name
        if args.aliases:
            account["aliases"] = [a.strip() for a in args.aliases.split(",") if a.strip()]
        account.setdefault("login", {})["storage_state_path"] = str(account_dir / "storage_state.json")
        account.setdefault("cdp", {})["port"] = port  # 共用平台实例端口
        account["cdp"]["profile_dir"] = ""  # 留空 = 共用平台浏览器实例（独立实例时手改端口与 profile）
        account_dir.mkdir(parents=True, exist_ok=True)
        save_yaml(config, config_path)
        created = True

    print(json.dumps({
        "status": "ok",
        "msg": f"账号 {'初始化' if created else '已存在'}: {name}",
        "data": {
            "account": name,
            "account_dir": str(account_dir),
            "account_config": str(config_path),
            "storage_state_path": str(account_dir / "storage_state.json"),
            "cdp_port": (load_yaml(config_path).get("account", {}).get("cdp", {}) or {}).get("port"),
            "created": created,
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
