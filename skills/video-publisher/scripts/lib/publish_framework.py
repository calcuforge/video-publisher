#!/usr/bin/env python3
"""
通用发布框架（PlatformPublisher）— 平台自动化发布脚本的基类。

设计目标：平台发布脚本 = 一个继承本框架的子类，只覆写平台差异相关的 hook；
登录态管理（storageState + VNC 人机协作）、通用填表、视频/封面上传、提交、
结果等待等能力由框架与 lib/cdp 提供，开箱即用。

agent 扩展步骤（详见 references/publish-framework.md）：
1. 新建 {platform_dir}/publish_scripts/{platform}_publish.py
2. 定义子类继承 PlatformPublisher，覆写需要定制的 hook
   （不覆写 = 使用通用实现，通用实现依赖 material_structure 与类属性选择器）
3. 入口: if __name__ == "__main__": MyPublisher.run_cli()

调用约定（参数由 scripts/tool/publish_video.py 透传，勿改）：
    --platform-config <abs> --project-config <abs> --material <abs> --cdp-url <url>

输出约定：@ENV@ 进度行（含 human_collab 人机协作提示，自动经 agent channel
推送）+ 最终 JSON envelope。失败时 status=error、data.self_heal=
review_script_and_page、非零退出，触发自愈流程（references/self-healing.md）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib.cdp import (
    click_by_selector, click_by_text, connect_browser, ensure_login, env_out,
    fill_by_label, fill_by_placeholder, fill_text, human_wait_selector,
    human_wait_url, new_page, screenshot, select_by_text, upload_file,
)
from lib.net import ensure_utf8_stdio
from lib.yamlutil import load_yaml

ensure_utf8_stdio()


class PlatformPublisher:
    """平台发布基类：覆写 hook 扩展平台差异；通用能力开箱即用。"""

    # ============ 平台参数（子类覆写；依据 probe_page.py 探测结果填写）============
    PUBLISH_URL = ""            # 发布页 URL；空 = 平台配置 publish_page_url
    FORM_READY_SELECTOR = ""    # 发布表单出现的选择器（上传完成等待也用它）
    TITLE_SELECTOR = ""         # 标题输入框；空 = 按 label 文本匹配
    DESCRIPTION_SELECTOR = ""   # 简介文本域
    TAGS_SELECTOR = ""          # 标签输入框（多数平台需回车确认）
    PARTITION_SELECTOR = ""     # 分区 <select>；树形选择需覆写 fill_field
    VIDEO_UPLOAD_SELECTOR = ""  # 视频 file input；空 = 自动找第一个
    COVER_UPLOAD_SELECTOR = ""  # 封面 file input；与视频同 input 则留空
    SUBMIT_SELECTOR = ""        # 发布按钮；空 = 按"发布"文本点击
    SUBMIT_OK_URL_CONTAINS = "" # 发布成功 URL 特征（wait_result 用）
    SUBMIT_OK_SELECTOR = ""     # 发布成功元素特征（与 URL 特征二选一）
    LOGIN_TIMEOUT = 600
    FORM_READY_TIMEOUT = 600
    UPLOAD_TIMEOUT = 1800
    SUBMIT_TIMEOUT = 900
    MANUAL_CHECKPOINT = True    # manual 模式提交前暂停截图、等待用户审核

    def __init__(self, platform_config: dict, project_config: dict,
                 material: dict, cdp_url: str, material_yaml_path: str = ""):
        self.platform_config = platform_config
        self.project_config = project_config
        self.material = material
        self.cdp_url = cdp_url
        self.material_yaml_path = material_yaml_path
        self.mode = project_config.get("project", {}).get("creation_mode", "auto")
        self.structure = platform_config.get("material_structure", {}).get("fields", {})
        self.browser = None
        self.page = None

    # ============ 工具方法（子类可直接调用）============
    def env(self, status: str, msg: str, **data) -> None:
        env_out(status, msg, **data)

    def fields(self) -> dict:
        return self.material.get("fields", {})

    def field(self, name: str, default=""):
        return self.fields().get(name, default)

    def screenshot(self, name: str) -> str:
        path = str(Path(self.material_yaml_path).parent / name) if self.material_yaml_path else name
        if self.page:
            screenshot(self.page, path)
        return path

    # ============ 生命周期 ============
    def run(self) -> None:
        try:
            self.browser = connect_browser(self.cdp_url)
            self.page = self.open_publish_page()
            self.env("step", f"已打开发布页: {self.page.url}")

            self.wait_login()
            self.wait_form_ready()
            self.upload_video()
            self.fill_form()
            self.upload_cover()
            if self.mode == "manual" and self.MANUAL_CHECKPOINT:
                self.manual_checkpoint()
            self.submit()
            self.wait_result()

            url = self.page.url
            self.browser.close()
            print(json.dumps({"status": "ok", "msg": "发布执行完成",
                              "data": {"url": url}}, ensure_ascii=False, indent=2))
        except Exception as exc:
            print(json.dumps({"status": "error", "msg": f"发布失败: {exc}",
                              "data": {"self_heal": "review_script_and_page"}},
                             ensure_ascii=False, indent=2))
            sys.exit(1)

    @classmethod
    def run_cli(cls) -> None:
        parser = argparse.ArgumentParser(description="Platform publish script (framework subclass)")
        parser.add_argument("--platform-config", required=True)
        parser.add_argument("--project-config", required=True)
        parser.add_argument("--material", required=True)
        parser.add_argument("--cdp-url", required=True)
        args = parser.parse_args()
        cls(load_yaml(args.platform_config), load_yaml(args.project_config),
            load_yaml(args.material).get("material", {}), args.cdp_url, args.material).run()

    # ============ hooks：默认通用实现，子类按平台差异覆写 ============
    def open_publish_page(self):
        """打开发布页。子类可覆写：先处理登录跳转、打开特定 frame 等。"""
        url = self.PUBLISH_URL or self.platform_config.get("platform", {}).get("publish_page_url", "")
        return new_page(self.browser, url, platform_config=self.platform_config)

    def wait_login(self):
        """登录态管理：storageState 优先，缺失/过期则 VNC 人机协作登录并保存。
        子类可覆写追加额外等待（如登录后的短信/滑块二次校验）。"""
        ensure_login(self.page, self.platform_config, timeout=self.LOGIN_TIMEOUT)

    def wait_form_ready(self):
        """等待发布表单加载（登录后跳转或表单异步渲染）。"""
        if self.FORM_READY_SELECTOR:
            human_wait_selector(self.page, "等待发布表单加载", self.FORM_READY_SELECTOR,
                                timeout=self.FORM_READY_TIMEOUT)

    def upload_video(self):
        """上传视频文件。子类可覆写：先点上传按钮、处理多帧页面等。"""
        video = self.field("video") or self.material.get("video_file", "")
        if not video or not Path(video).exists():
            raise RuntimeError(f"物料中缺少视频文件: {video}")
        self.env("step", f"上传视频: {video}")
        upload_file(self.page, self.VIDEO_UPLOAD_SELECTOR, video)
        self.after_upload_video()

    def after_upload_video(self):
        """等待上传/转码完成：多数平台表单可用即视为就绪。"""
        human_wait_selector(
            self.page, "视频正在上传/转码，请通过 VNC 观察进度（大文件可能较慢）",
            self.FORM_READY_SELECTOR or "input, textarea",
            timeout=self.UPLOAD_TIMEOUT, condition_desc="上传完成、发布表单可用",
        )

    def fill_form(self):
        """按 material_structure 遍历物料字段并填写（video/image 由上传步骤处理）。"""
        for name, value in self.fields().items():
            fdef = self.structure.get(name, {})
            kind = fdef.get("kind", "text")
            if kind in ("video", "image"):
                continue
            if value in (None, "", [], False):
                continue
            self.fill_field(name, value, kind, fdef.get("label", name))

    def fill_field(self, name: str, value, kind: str, label: str):
        """单个字段填写分发。子类覆写处理特殊字段（树形分区、富文本等）。"""
        if kind in ("text", "textarea"):
            self._fill_text(name, value, label)
        elif kind == "tags":
            self._fill_tags(value, label)
        elif kind == "select":
            self._fill_select(value, label)
        elif kind == "checkbox":
            self._fill_checkbox(value, label)
        else:  # extra 等平台特有字段
            self.env("step", f"字段 [{name}]（kind={kind}）需在子类 fill_field 中覆写处理")

    def upload_cover(self):
        """上传封面。无封面文件则跳过。"""
        cover = self.field("cover")
        if not cover or not Path(cover).exists():
            self.env("step", "无封面文件，跳过封面上传")
            return
        self.env("step", f"上传封面: {cover}")
        upload_file(self.page, self.COVER_UPLOAD_SELECTOR, cover)

    def manual_checkpoint(self):
        """manual 模式提交前暂停：截图并等待用户审核确认。"""
        self.env("manual_checkpoint", "manual 模式：提交前暂停。agent 应向用户展示即将发布的内容并等待确认")
        self.screenshot("pre_submit.png")
        human_wait_selector(self.page, "等待用户确认后点击发布（manual 模式审核）",
                            self.FORM_READY_SELECTOR or "input, textarea", timeout=3600)

    def submit(self):
        """点击发布/提交按钮。"""
        self.before_submit()
        if self.SUBMIT_SELECTOR:
            if not click_by_selector(self.page, self.SUBMIT_SELECTOR):
                raise RuntimeError(f"未找到发布按钮: {self.SUBMIT_SELECTOR}")
        elif not click_by_text(self.page, "发布"):
            raise RuntimeError("未找到发布按钮（SUBMIT_SELECTOR 未配置且无'发布'文本按钮），"
                               "请根据探测结果补充 SUBMIT_SELECTOR")

    def before_submit(self):
        """提交前的平台特有步骤（勾选原创声明、二次确认弹窗等），子类按需覆写。"""

    def wait_result(self):
        """等待发布结果。未配置特征时提示 agent 人工确认。"""
        if self.SUBMIT_OK_URL_CONTAINS:
            human_wait_url(self.page, "已提交，等待发布结果（若出现验证码/风控校验，请通过 VNC 处理）",
                           self.SUBMIT_OK_URL_CONTAINS, timeout=self.SUBMIT_TIMEOUT)
        elif self.SUBMIT_OK_SELECTOR:
            human_wait_selector(self.page, "已提交，等待发布结果（若出现验证码/风控校验，请通过 VNC 处理）",
                                self.SUBMIT_OK_SELECTOR, timeout=self.SUBMIT_TIMEOUT)
        else:
            self.screenshot("post_submit.png")
            self.env("result", "已执行提交，请通过 VNC 确认页面状态（未配置 SUBMIT_OK_* 特征）")

    # ============ 通用字段填写实现（子类可复用/覆写）============
    def _fill_text(self, name: str, value: str, label: str) -> None:
        selector = ""
        if name == "title":
            selector = self.TITLE_SELECTOR
        elif name == "description":
            selector = self.DESCRIPTION_SELECTOR
        if selector:
            if not fill_text(self.page, selector, value):
                raise RuntimeError(f"字段 [{name}] 选择器未命中: {selector}")
            return
        if not fill_by_label(self.page, label, value) and not fill_by_placeholder(self.page, label, value):
            self.env("step", f"字段 [{name}] 未找到可见输入框，请检查选择器或人工处理")

    def _fill_tags(self, value: list, label: str) -> None:
        if self.TAGS_SELECTOR:
            tag_input = self.page.locator(self.TAGS_SELECTOR)
            for tag in value:
                tag_input.first.fill(tag)
                self.page.keyboard.press("Enter")
            return
        if not fill_by_label(self.page, label, " ".join(value)):
            self.env("step", f"标签字段未能自动填写（label={label}），请检查页面")

    def _fill_select(self, value: str, label: str) -> None:
        if self.PARTITION_SELECTOR:
            if not select_by_text(self.page, self.PARTITION_SELECTOR, value):
                raise RuntimeError(f"分区 [{value}] 在下拉中未找到（候选值需与 material_structure 一致）")
            return
        if not click_by_text(self.page, value):
            self.env("step", f"分区 [{value}] 未找到可选条目，可能为树形选择，请在子类覆写 fill_field 处理")

    def _fill_checkbox(self, value: bool, label: str) -> None:
        if not value:
            return
        try:
            loc = self.page.get_by_label(label, exact=False).first
            if loc.count() > 0:
                loc.click()
                return
        except Exception:
            pass
        self.env("step", f"checkbox [{label}] 未能自动勾选，请在子类覆写 fill_field")


if __name__ == "__main__":
    # 直接运行框架本身会因缺省实现而失败于发布页 URL 未配置 —— 平台脚本必须
    # 是继承本框架的子类（见 scripts/publish_scripts/template_publish.py）。
    print(json.dumps({"status": "error",
                      "msg": "publish_framework.py 是框架基类，请编写平台子类（参考 template_publish.py）",
                      "data": {}}, ensure_ascii=False, indent=2))
    sys.exit(1)
