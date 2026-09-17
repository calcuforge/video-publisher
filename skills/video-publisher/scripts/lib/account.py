"""
多账号支持 — 账号配置解析/合并/列表。

账号唯一标识 = 账号目录名（{platform_dir}/accounts/{name}/），同时写入
account_config.yaml 的 account.name（两者强制一致）。account_config.yaml
可配 display_name（展示名）与 aliases（指令匹配别名，非唯一标识）。

agent 确定目标账号的四级解析链（resolve_account）：
    1. 显式指定（用户指令匹配 / --account 参数）
    2. 项目默认 project_config.yaml → publish_defaults.default_account
    3. 平台默认 platform_config.yaml → default_account
    4. 兜底 default 账号（accounts/default）
无 accounts/ 目录 = 单账号形态，返回原 platform_config（完全兼容现状）。

合并视图（merge_account）：账号配置的 login / cdp 段覆盖平台配置对应段
（storage_state_path / port / profile_dir 按账号隔离），其余字段保持平台级
共享——框架与平台发布脚本读到的仍是 platform_config 形状，账号透明。
"""

from __future__ import annotations

import copy
from pathlib import Path

from lib.yamlutil import load_yaml

ACCOUNTS_DIR = "accounts"
DEFAULT_ACCOUNT = "default"


def normalize_account(raw: str) -> str:
    """账号名归一化：小写、空格转下划线（与平台标识同规则）。"""
    return raw.strip().lower().replace(" ", "_")


def accounts_dir(platform_dir: Path | str) -> Path:
    return Path(platform_dir) / ACCOUNTS_DIR


def list_accounts(platform_dir: Path | str) -> list[dict]:
    """列出平台下所有已配置账号。返回 [{name, display_name, aliases, config_path}]。"""
    base = accounts_dir(platform_dir)
    result = []
    if not base.exists():
        return result
    for entry in sorted(base.iterdir()):
        cfg_path = entry / "account_config.yaml"
        if not entry.is_dir() or not cfg_path.exists():
            continue
        cfg = load_yaml(cfg_path) or {}
        acct = cfg.get("account", {}) if isinstance(cfg, dict) else {}
        result.append({
            "name": acct.get("name") or entry.name,
            "display_name": acct.get("display_name", ""),
            "aliases": acct.get("aliases", []) or [],
            "config_path": str(cfg_path),
        })
    return result


def load_account_config(platform_dir: Path | str, account: str) -> dict | None:
    """读取指定账号配置；不存在返回 None。"""
    path = accounts_dir(platform_dir) / account / "account_config.yaml"
    if not path.exists():
        return None
    cfg = load_yaml(path)
    return cfg if isinstance(cfg, dict) else None


def match_account(platform_dir: Path | str, query: str) -> str | None:
    """按用户输入匹配账号：name / display_name / aliases（不区分大小写）。

    返回账号唯一标识（目录名）；未匹配返回 None。
    """
    query = (query or "").strip().lower()
    if not query:
        return None
    for acct in list_accounts(platform_dir):
        candidates = {acct["name"].lower(), str(acct.get("display_name", "")).lower()}
        candidates |= {str(a).lower() for a in acct.get("aliases", [])}
        if query in candidates:
            return acct["name"]
    return None


def resolve_account(platform_dir: Path | str, platform_config: dict,
                    account: str = "", project_config: dict | None = None
                    ) -> tuple[dict, str]:
    """四级解析链确定目标账号并返回合并视图。

    优先级：显式 account（用户指令匹配/--account）> 项目 default_account
    > 平台 default_account > default 兜底。

    返回 (effective_platform_config, account_name)。无 accounts/ 目录或账号
    不存在时按原 platform_config 返回（account_name 为空 = 单账号形态）；
    显式指定但账号不存在时抛 RuntimeError（附可用账号列表，供 agent 自纠错）。
    """
    base = accounts_dir(platform_dir)
    if not base.exists():
        return platform_config, ""

    available = [a["name"] for a in list_accounts(platform_dir)]

    resolved = ""
    if account:
        account_n = normalize_account(account)
        if account_n not in available:
            # 非 ID 输入（用户口语）：按 display_name/aliases 匹配
            matched = match_account(platform_dir, account)
            if not matched:
                raise RuntimeError(
                    f"账号不存在: {account}（平台可用账号: {', '.join(available) or '无'}）。"
                    f"可先用 init_account.py 创建")
            account_n = matched
        resolved = account_n
    else:
        proj_default = (project_config or {}).get("publish_defaults", {}).get("default_account", "")
        plat_default = platform_config.get("default_account", "")
        for candidate in (proj_default, plat_default):
            if candidate and normalize_account(candidate) in available:
                resolved = normalize_account(candidate)
                break
        if not resolved and DEFAULT_ACCOUNT in available:
            resolved = DEFAULT_ACCOUNT
    if not resolved:
        return platform_config, ""

    acct_cfg = load_account_config(platform_dir, resolved)
    if not acct_cfg:
        return platform_config, ""
    return merge_account(platform_config, acct_cfg), resolved


def merge_account(platform_config: dict, account_config: dict) -> dict:
    """合并平台配置与账号配置为有效视图（login/cdp 段被账号覆盖）。

    账号配置中的空值不覆盖平台配置——共用模式（默认）下账号 cdp 段的
    profile_dir 留空 = 沿用平台实例，不应清除平台级设置。
    """
    effective = copy.deepcopy(platform_config)
    acct = account_config.get("account", {}) if isinstance(account_config, dict) else {}
    platform = effective.setdefault("platform", {})

    def non_empty(d: dict) -> dict:
        return {k: v for k, v in d.items() if v not in (None, "", [], {})}

    # login 段覆盖（storage_state_path 按账号隔离）
    acct_login = non_empty(acct.get("login") or {})
    if acct_login:
        platform["login"] = {**(platform.get("login") or {}), **acct_login}
    # cdp 段覆盖（独立实例时为账号专属 port/profile_dir；共用模式仅端口与平台一致）
    acct_cdp = non_empty(acct.get("cdp") or {})
    if acct_cdp:
        platform["cdp"] = {**(platform.get("cdp") or {}), **acct_cdp}

    platform["account"] = acct.get("name", "")
    return effective
