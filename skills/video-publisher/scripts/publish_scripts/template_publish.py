#!/usr/bin/env python3
"""
平台发布脚本模板 — agent 在"首次发布流程"中将其复制为
{platform_dir}/publish_scripts/{platform}_publish.py（如 bilibili_publish.py），
并根据 probe_page.py 的 DOM 探测结果填充以下各步骤。

设计原则（可复用）:
- 同一平台的所有项目/所有视频共用本脚本，参数全部来自 materials.yaml
  与 platform_config.yaml / project_config.yaml，禁止硬编码标题、标签等业务数据。
- 通过 CDP 连接有头浏览器（用户可经 VNC 观察）；遇到登录、验证码、风险校验
  等无法自动化的场景，使用 human_wait_* 阻塞等待并输出 @ENV@ 提示。
- 每一步用 env_out() 输出进度，失败抛出 RuntimeError（进程以非零码退出，
  触发 agent 的自愈流程）。

通用步骤（按平台实际页面调整顺序与选择器）:
1. 连接浏览器，打开发布页
2. 检测登录状态（login_indicator）；未登录则 human_wait 等待用户 VNC 登录
3. 等待发布表单出现（human_wait_selector）
4. 上传视频文件（upload_file）并等待转码/上传完成（human_wait 或进度检测）
5. 填写标题/简介/标签/分区（fill_by_label / fill_by_placeholder / select_by_text）
6. 上传封面（upload_file）
7. 发布前检查（manual 模式下由 agent 暂停让用户审核，见 SKILL.md）
8. 点击提交/发布按钮；遇到风控校验则 human_wait 等待人工处理
9. 等待发布结果（URL 跳转或成功提示），输出最终结果

命令行参数（由 publish_video.py 传入，请勿修改）:
    --platform-config <abs>  --project-config <abs>  --material <abs>  --cdp-url <url>

JSON envelope 输出: @ENV@ {"env_status": "...", ...} 行 + 最终 JSON（stdout）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.cdp import (
    connect_browser, click_by_selector, click_by_text, env_out, fill_by_label,
    fill_by_placeholder, fill_text, human_wait_selector, human_wait_url, new_page,
    screenshot, select_by_text, upload_file,
)
from lib.net import ensure_utf8_stdio
from lib.yamlutil import load_yaml

ensure_utf8_stdio()

# ============ agent 在此填写平台参数 ============
# 依据 probe_page.py 探测结果：
# - 发布页 URL 与登录指示（通常与 platform_config.yaml 一致，此处为兜底默认）
# - 关键控件的选择器（CSS）或标签文本
PUBLISH_URL = ""  # 例: https://member.bilibili.com/platform/upload/video/frame
LOGIN_URL_CONTAINS = ""  # 例: passport.bilibili.com — 出现即需要人工登录
LOGIN_OK_URL_CONTAINS = ""  # 例: /platform/upload/video/frame — 出现即视为已登录
FORM_READY_SELECTOR = ""  # 发布表单出现的选择器，例: "input[placeholder*='标题']"
TITLE_SELECTOR = ""  # 例: "input[placeholder*='标题']"；留空则用 fill_by_label('标题')
DESCRIPTION_SELECTOR = ""
TAGS_SELECTOR = ""  # 标签输入框（部分平台标签需回车确认）
PARTITION_SELECTOR = ""  # 分区下拉 <select> 或可点击的树形选择（平台差异大）
VIDEO_UPLOAD_SELECTOR = ""  # 例: "input[type=file]"；留空自动找第一个文件输入
COVER_UPLOAD_SELECTOR = ""  # 封面文件输入；若与视频为同一 input 则留空
SUBMIT_SELECTOR = ""  # 例: "button:has-text('发布')"
SUBMIT_OK_URL_CONTAINS = ""  # 发布成功后的 URL 特征，例: /manage/create
# ================================================


def read_material(material_path: Path) -> dict:
    material = load_yaml(material_path)
    return material.get("material", {})


def wait_login(page, platform_config: dict) -> None:
    """检测登录状态；未登录则阻塞等待用户通过 VNC 完成登录。"""
    indicator = platform_config.get("platform", {}).get("login_indicator", {})
    url_ok = indicator.get("url_contains") or LOGIN_OK_URL_CONTAINS
    selector_ok = indicator.get("selector") or ""
    logged_in = False
    if url_ok and url_ok in (page.url or ""):
        logged_in = True
    if selector_ok and page.locator(selector_ok).count() > 0:
        logged_in = True
    if logged_in:
        env_out("login", "已检测到登录状态")
        return
    human_wait_url(
        page,
        "页面未登录。请通过 VNC 观察有头浏览器，手动完成登录（扫码/账号密码/验证码）",
        url_ok,
    )


def step_upload_video(page, material: dict) -> None:
    video = material.get("fields", {}).get("video") or material.get("video_file", "")
    if not video or not Path(video).exists():
        raise RuntimeError(f"物料中缺少视频文件: {video}")
    env_out("step", f"上传视频: {video}")
    upload_file(page, VIDEO_UPLOAD_SELECTOR, video)
    # 等待上传/转码完成：多数平台出现可填写标题的表单即说明视频已就绪
    human_wait_selector(
        page,
        "视频正在上传/转码，请通过 VNC 观察进度（大文件可能较慢）",
        TITLE_SELECTOR or "input, textarea",
        timeout=1800,
        condition_desc="上传完成、发布表单可用",
    )


def step_fill_form(page, material: dict, platform_config: dict) -> None:
    fields = material.get("fields", {})
    structure = platform_config.get("material_structure", {}).get("fields", {})
    for name, value in fields.items():
        if value in (None, "", [], False):
            continue
        kind = structure.get(name, {}).get("kind", "text")
        label = structure.get(name, {}).get("label", name)
        if kind in ("text", "textarea"):
            if kind == "text" and TITLE_SELECTOR and name == "title":
                fill_text(page, TITLE_SELECTOR, value)
            elif kind == "textarea" and DESCRIPTION_SELECTOR:
                fill_text(page, DESCRIPTION_SELECTOR, value)
            else:
                if not fill_by_label(page, label, value):
                    env_out("step", f"字段 [{name}] 未找到可见输入框，尝试其他方式或人工处理")
        elif kind == "tags":
            if TAGS_SELECTOR:
                tag_input = page.locator(TAGS_SELECTOR)
                for tag in value:
                    tag_input.first.fill(tag)
                    page.keyboard.press("Enter")
            elif not fill_by_label(page, label, " ".join(value)):
                env_out("step", f"标签字段 [{name}] 未能自动填写，请检查页面")
        elif kind == "select":
            if PARTITION_SELECTOR:
                select_by_text(page, PARTITION_SELECTOR, value)
            elif not click_by_text(page, value):
                env_out("step", f"分区 [{value}] 未找到可选条目，请人工选择")
        elif kind == "image" and value:
            env_out("step", f"上传封面: {value}")
            if COVER_UPLOAD_SELECTOR:
                upload_file(page, COVER_UPLOAD_SELECTOR, value)
        # video 字段在 step_upload_video 处理；checkbox/extra 按平台补充
    env_out("step", "表单字段填写完成")


def step_submit(page) -> None:
    if not SUBMIT_SELECTOR:
        raise RuntimeError("SUBMIT_SELECTOR 未配置，请根据探测结果补充发布按钮选择器")
    if not click_by_selector(page, SUBMIT_SELECTOR):
        if not click_by_text(page, "发布"):
            raise RuntimeError(f"未找到发布按钮: {SUBMIT_SELECTOR}")
    # 风控/二次校验：阻塞等待人工确认或结果页出现
    if SUBMIT_OK_URL_CONTAINS:
        human_wait_url(
            page,
            "已提交，等待发布结果（若出现验证码/风控校验，请通过 VNC 处理）",
            SUBMIT_OK_URL_CONTAINS,
            timeout=900,
        )
    env_out("result", "发布流程已执行完成，请确认页面状态")


def main() -> None:
    parser = argparse.ArgumentParser(description="Platform publish script (agent-filled)")
    parser.add_argument("--platform-config", required=True)
    parser.add_argument("--project-config", required=True)
    parser.add_argument("--material", required=True)
    parser.add_argument("--cdp-url", required=True)
    args = parser.parse_args()

    platform_config = load_yaml(args.platform_config)
    material = read_material(Path(args.material))
    project_config = load_yaml(args.project_config)

    mode = project_config.get("project", {}).get("creation_mode", "auto")

    try:
        browser = connect_browser(args.cdp_url)
        page = new_page(browser, PUBLISH_URL or platform_config.get("platform", {}).get("publish_page_url", ""))
        env_out("step", f"已打开发布页: {page.url}")

        wait_login(page, platform_config)
        if FORM_READY_SELECTOR:
            human_wait_selector(page, "等待发布表单加载", FORM_READY_SELECTOR)
        step_upload_video(page, material)
        step_fill_form(page, material, platform_config)

        if mode == "manual":
            # agent 侧：manual 模式在提交前暂停，等待用户审核
            env_out("manual_checkpoint", "manual 模式：提交前暂停。agent 应向用户展示即将发布的内容并等待确认")
            screenshot(page, str(Path(args.material).parent / "pre_submit.png"))
            human_wait_selector(page, "等待用户确认后点击发布（manual 模式审核）", "input, textarea", timeout=3600)

        step_submit(page)
        browser.close()
        print(json.dumps({"status": "ok", "msg": "发布执行完成", "data": {"url": page.url}},
                         ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "error", "msg": f"发布失败: {exc}",
                          "data": {"self_heal": "review_script_and_page"}},
                         ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
