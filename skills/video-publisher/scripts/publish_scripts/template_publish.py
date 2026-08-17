#!/usr/bin/env python3
"""
平台发布脚本模板 — 展示如何基于通用发布框架（lib/publish_framework.py 的
PlatformPublisher）编写平台自动化发布脚本。

agent 在"首次发布流程"步骤 4 中，新建
{platform_dir}/publish_scripts/{platform}_publish.py，参照本文件编写
子类：依据 probe_page.py 的 DOM 探测结果填写类属性（选择器/登录特征/成功
特征），并按平台差异覆写需要的 hook。不覆写的 hook 使用框架通用实现
（基于 material_structure + label 文本匹配的通用填表）。

框架提供的 hooks（按发布生命周期顺序）：
    open_publish_page → wait_login → wait_form_ready → upload_video →
    fill_form(fill_field) → upload_cover → [manual_checkpoint] → submit
    (before_submit) → wait_result

常见覆写场景与示例见 references/publish-framework.md：
- 树形分区/富文本等特殊字段 → 覆写 fill_field
- 登录后的短信/滑块二次校验 → 覆写 wait_login 追加 human_wait_*
- 先点按钮再出现文件输入 → 覆写 upload_video
- 提交前的勾选（原创声明等）→ 覆写 before_submit

命令行参数（由 publish_video.py 传入，请勿修改）:
    --platform-config <abs>  --project-config <abs>  --material <abs>  --cdp-url <url>
"""

from __future__ import annotations

from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

sys.path.insert(0, str(SCRIPTS_DIR))

from lib.cdp import human_wait_selector  # noqa: E402
from lib.publish_framework import PlatformPublisher  # noqa: E402


class TemplatePublisher(PlatformPublisher):
    """示例子类：把类名换成 {平台名}Publisher（如 BilibiliPublisher）。
    下面每个属性/hook 都标注了"依据探测结果填写/覆写"。"""

    # ---- 平台参数（依据 probe_page.py 探测结果填写）----
    PUBLISH_URL = ""  # 发布页 URL，如 https://member.bilibili.com/platform/upload/video/frame
    # 登录指示（url_contains / selector）配置在 platform_config.yaml；
    # 登录态由框架 wait_login → ensure_login 管理：storageState 优先，
    # 缺失/过期时阻塞等待用户 VNC 登录并自动保存。
    FORM_READY_SELECTOR = ""  # 发布表单出现的选择器，如 "input[placeholder*='标题']"
    TITLE_SELECTOR = ""  # 标题输入框；留空则按 label"标题"匹配
    DESCRIPTION_SELECTOR = ""  # 简介文本域；留空则按 label"简介"匹配
    TAGS_SELECTOR = ""  # 标签输入框（部分平台输入后需回车确认）
    PARTITION_SELECTOR = ""  # 分区 <select>；若是树形选择，覆写 fill_field
    VIDEO_UPLOAD_SELECTOR = ""  # 视频 file input；留空自动找第一个
    COVER_UPLOAD_SELECTOR = ""  # 封面 file input；与视频同 input 则留空
    SUBMIT_SELECTOR = ""  # 发布按钮，如 "button:has-text('发布')"；留空按"发布"文本点击
    SUBMIT_OK_URL_CONTAINS = ""  # 发布成功 URL 特征，如 "/manage/create"
    SUBMIT_OK_SELECTOR = ""  # 或成功元素特征，二选一

    # ---- hook 覆写示例（按需取消注释）----

    # 场景 1：登录后还有短信/滑块二次校验 —— 覆写 wait_login 追加等待
    # def wait_login(self):
    #     super().wait_login()
    #     human_wait_selector(self.page, "请通过 VNC 完成登录后的安全校验（滑块/短信）",
    #                         "text=安全校验通过", timeout=self.LOGIN_TIMEOUT)

    # 场景 2：分区是树形/级联选择 —— 覆写 fill_field 处理 partition
    # def fill_field(self, name, value, kind, label):
    #     if name == "partition":
    #         # 示例：点击一级分区再选二级（选择器以实际探测为准）
    #         if not click_by_text(self.page, value.split(" / ")[0]):
    #             self.env("step", f"分区 [{value}] 未找到，请人工选择")
    #         return
    #     super().fill_field(name, value, kind, label)

    # 场景 3：提交前需勾选"原创声明" —— 覆写 before_submit
    # def before_submit(self):
    #     super().before_submit()
    #     if self.field("original_declaration"):
    #         click_by_text(self.page, "未经作者授权，禁止转载")

    # 场景 4：先点"上传视频"按钮才出现文件输入框 —— 覆写 upload_video
    # def upload_video(self):
    #     click_by_text(self.page, "点击上传")
    #     super().upload_video()


if __name__ == "__main__":
    TemplatePublisher.run_cli()
