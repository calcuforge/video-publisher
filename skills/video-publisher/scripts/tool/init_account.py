#!/usr/bin/env python3
"""
账号初始化：创建 {platform_dir}/accounts/{name}/ 账号目录及 account_config.yaml
（从 templates/account_config_tpl.yaml 复制，回填 name/account_dir/
storage_state_path/cdp.port/profile_dir）。

- 账号唯一标识 = 目录名（小写英文数字下划线），重名报错并列出已有账号
- CDP 端口自动递增：扫描已有账号端口，取 max+1（首个账号 9223，避开平台
  默认的 9222）；实现每账号独立浏览器实例（登录态隔离、可并行发布）
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
BASE_PORT = 9223  # 首个账号端口（9222 留给平台默认浏览器实例）


def next_cdp_port(platform_dir: Path) -> int:
    """扫描已有账号端口取 max+1；无账号时从 BASE_PORT 开始。"""
    ports = [BASE_PORT - 1]
    for acct in list_accounts(platform_dir):
        cfg_path = Path(acct["config_path"])
        if cfg_path.exists():
            cfg = load_yaml(cfg_path) or {}
            port = (cfg.get("account", {}) or {}).get("cdp", {}) or {}
            ports.append(int(port.get("port", BASE_PORT - 1) or BASE_PORT - 1))
    return max(ports) + 1


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
        port = next_cdp_port(platform_dir)
        config = load_yaml(TEMPLATE_PATH)
        account = config.setdefault("account", {})
        account["name"] = name
        account["account_dir"] = str(account_dir)
        if args.display_name:
            account["display_name"] = args.display_name
        if args.aliases:
            account["aliases"] = [a.strip() for a in args.aliases.split(",") if a.strip()]
        account.setdefault("login", {})["storage_state_path"] = str(account_dir / "storage_state.json")
        account.setdefault("cdp", {})["port"] = port
        account["cdp"]["profile_dir"] = str(account_dir / "browser_profile")
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
