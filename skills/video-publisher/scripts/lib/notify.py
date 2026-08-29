"""
Channel 通知推送 — 通过 hermes agent gateway 的 channel 消息推送提醒用户。

推送流程（推送动作由 agent 执行，脚本不自动推送）：
1. 脚本检测到需要登录/验证码 → 输出 @ENV@ human_collab 提示（含 VNC 地址）；
2. agent 看到提示后，调用本模块（或 scripts/tool/notify.py CLI）把**含 VNC
   地址**的提示消息推送到 hermes agent 的 messaging channel（Telegram /
   Discord / Slack / 飞书 / 钉钉 / 企业微信 / 微信 等，复用 hermes gateway
   已配置的频道凭据）。

目标频道（hermes v0.20+ 强制显式 `--to <平台[:频道[:thread]]>`）由调用方
传入 targets 列表；**列表为空 = 推送到所有已发现的 channel**（通过
`hermes send --list --json` 枚举）。实际配置位置：project_config.yaml 的
`publish_defaults.hermes_send_targets`（如 `[weixin, telegram:12345]`），
CLI 可用 `--to` 单次覆盖。

- 前置：hermes-agent 已安装且 `hermes gateway start` 运行中（凭据在
  `hermes gateway setup` 时配置，本 skill 不重复配置）
- 失败时透传 stderr（截断 300 字符）到 WARNING；微信等平台限流
  （rate limited）时给出约 30s 退避提示并自动重试一次。
- 推送失败只输出警告，绝不阻断主流程。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time

# hermes send 输出中的限流信息，如 "iLink sendmessage rate limited; cooldown active for 30.0s"
_RATE_LIMIT_RE = re.compile(r"rate limited.*cooldown active for ([\d.]+)s", re.IGNORECASE)


def _warn(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def _run_hermes_send(target: str, message: str, title: str) -> tuple[bool, str]:
    """执行一次 hermes send。返回 (ok, 失败原因摘要)。"""
    cmd = ["hermes", "send", "--to", target, "--subject", title, message]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return False, "hermes CLI 未安装或不在 PATH 上（请安装 hermes-agent 并配置 gateway）"
    except subprocess.TimeoutExpired:
        return False, "hermes send 超时（60s）"
    except Exception as exc:
        return False, f"hermes send 执行异常: {exc}"

    if proc.returncode == 0:
        return True, ""
    err = (proc.stderr or proc.stdout or "").strip()[:300]
    return False, f"hermes send 失败（退出码 {proc.returncode}）: {err}"


def _list_all_targets() -> tuple[list[str], str]:
    """通过 `hermes send --list --json` 枚举所有可用目标。

    返回 (targets, 失败原因)。输出形如 {"platforms": {"telegram": [...]}}；
    每个平台取裸平台名（home channel）并附上列表中的具体频道。
    无已发现频道时返回空列表（由调用方报错）。
    """
    cmd = ["hermes", "send", "--list", "--json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return [], "hermes CLI 未安装或不在 PATH 上（请安装 hermes-agent 并配置 gateway）"
    except Exception as exc:
        return [], f"hermes send --list 执行异常: {exc}"

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:300]
        return [], f"hermes send --list 失败（退出码 {proc.returncode}）: {err}"

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return [], f"hermes send --list 输出非 JSON: {(proc.stdout or '')[:200]}"

    targets: list[str] = []
    for platform, value in (data.get("platforms") or {}).items():
        targets.append(platform)  # 平台 home channel
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    targets.append(f"{platform}:{item.strip()}")
    # 去重并保持顺序
    seen: set[str] = set()
    unique = [t for t in targets if not (t in seen or seen.add(t))]
    return unique, ""


def _send_with_retry(target: str, message: str, title: str) -> tuple[bool, str]:
    """推送到单个目标，限流时退避重试一次。"""
    ok, reason = _run_hermes_send(target, message, title)
    if ok:
        return True, ""
    match = _RATE_LIMIT_RE.search(reason)
    if match:
        cooldown = float(match.group(1))
        _warn(f"目标 {target} 限流（rate limited，cooldown {cooldown:.0f}s），"
              f"等待退避后重试一次...（不影响发布流程）")
        time.sleep(min(cooldown, 30))
        ok, retry_reason = _run_hermes_send(target, message, title)
        if ok:
            return True, ""
        reason = f"限流重试后仍失败: {retry_reason}"
    return False, reason


def notify_human_collab(message: str, title: str = "video-publisher",
                        targets: list[str] | None = None) -> tuple[bool, str, list[str]]:
    """通过 hermes agent channel 推送人机协作通知。

    targets：目标列表（hermes send --to 格式）；None 或空列表 = 推送到
    所有已发现的 channel（hermes send --list 枚举）。

    返回 (是否全部成功, 失败原因摘要, 实际推送的目标列表)。失败原因与
    实际目标供调用方（tool/notify.py）向用户展示真实情况；调用方仅警告、
    绝不阻断发布主流程。
    """
    if not targets:
        targets, reason = _list_all_targets()
        if reason:
            _warn(f"无法枚举推送目标（不影响发布流程）: {reason}")
            return False, reason, []
        if not targets:
            reason = "hermes send --list 未发现任何可用 channel（gateway 未配置平台凭据），无法推送"
            _warn(reason)
            return False, reason, []

    used_targets = list(targets)
    failed: list[str] = []
    for target in used_targets:
        ok, reason = _send_with_retry(target, message, title)
        if not ok:
            failed.append(f"{target}: {reason}")
            _warn(f"目标 {target} 推送失败（不影响发布流程）: {reason}")

    if not failed:
        return True, "", used_targets
    return False, f"成功 {len(used_targets) - len(failed)}/{len(used_targets)}，失败: {'; '.join(failed)}", used_targets
