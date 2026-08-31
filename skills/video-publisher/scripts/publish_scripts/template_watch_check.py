#!/usr/bin/env python3
"""
登录/验证码完成判断模块模板 — watch_login.py 通过 --check-script 加载。

**不同平台页面特征不同，完成判断逻辑由 agent 按实际页面实现**（依据
probe_page.py 的探测结果与发布脚本 human_wait 的等待特征）。agent 在首次
发布执行中新建 {platform}/publish_scripts/{platform}_watch_check.py，
实现 `check(page)` 函数，同平台所有项目复用；随后监控命令改为：

    python watch_login.py --platform-config <...> \
        --check-script <...>/publish_scripts/{platform}_watch_check.py \
        --project-config <...>

约定：
- `check(page) -> str | bool`：
    返回 True 或非空字符串（命中描述，会出现在推送/日志中）= 用户已处理完成；
    返回 False / None / "" = 继续等待。
- 函数内可自由使用 page（playwright Page 对象）做任何只读判断：
  URL 特征、元素可见、iframe 内元素、文本出现、按钮状态等。
- 判断要**幂等**：每 3s 调用一次，不得有副作用（不要点击/刷新页面）。
- 异常会被捕获并输出 watch_check_error 继续等待（避免一次异常导致监控中断）。
"""

from __future__ import annotations


def check(page) -> str | bool:
    """返回 True/命中描述表示用户已处理完成；False/None 继续等待。

    下方是不同平台页面特征的示例实现，agent 按实际探测结果替换：
    """
    # 示例 1：登录完成 = URL 回到发布页（登录跳转特征）
    if "member.bilibili.com/platform/upload" in (page.url or ""):
        return "已登录（URL 回到发布页）"

    # 示例 2：验证码/短信通过 = 页面出现特定元素
    # if page.locator("text=验证通过").count() > 0:
    #     return "验证码已通过（页面出现'验证通过'）"

    # 示例 3：iframe 内元素（部分平台发布页在 iframe 中）
    # for frame in page.frames:
    #     if frame.locator("input[placeholder*='标题']").count() > 0:
    #         return "iframe 内发布表单已出现"

    # 示例 4：登录按钮消失（未登录提示消失）
    # if page.locator("text=登录").count() == 0:
    #     return "页面登录入口消失"

    return False
