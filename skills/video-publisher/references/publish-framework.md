# 发布脚本框架扩展指南（Publish Framework）

> **何时加载：** 首次发布流程的「首次发布执行」步骤（编写/补充平台发布
> 脚本），或现有平台脚本需要适配页面改版/新增步骤。本指南说明如何基于
> 通用发布框架（`scripts/lib/publish_framework.py` 的 `PlatformPublisher`）
> 扩展自动化发布流程。

## 框架思想

平台发布脚本 = 一个继承 `PlatformPublisher` 的子类：

- **开箱即用**：登录态管理（storageState + VNC 人机协作）、通用填表
  （基于 `material_structure` + label 文本匹配）、视频/封面上传、提交、
  结果等待、错误 envelope 与自愈提示，全部由框架实现。
- **只写差异**：agent 依据 `probe_page.py` 的 DOM 探测结果，填写类属性
  （选择器）并覆写平台差异相关的 hook。
- **可复用**：同一平台所有项目/所有视频共用一份子类，业务数据只来自
  yaml（materials.yaml 与配置），禁止硬编码。

## 发布生命周期与 hooks

**默认时序（表单先行型，多数平台）**：

```
open_publish_page → wait_login → wait_form_ready → upload_video →
fill_form(逐字段 → fill_field) → upload_cover → [manual_checkpoint]
→ submit(before_submit) → wait_result
```

**视频先行型（如 B站：先上传视频、转码完成后标题表单才出现）**——配置
两个类属性即可，无需覆写任何方法（框架自动调整时序）：

```python
class BilibiliPublisher(PlatformPublisher):
    UPLOAD_FIRST = True                    # 视频先行模式
    UPLOAD_ENTRY_SELECTOR = "text=点击上传" # 上传入口出现的选择器（按探测填写）
    FORM_READY_SELECTOR = "input[placeholder*='标题']"  # 转码完成后表单出现
```

```
open_publish_page → wait_login → upload_video（先等 UPLOAD_ENTRY_SELECTOR
上传入口）→ wait_form_ready（转码完成、标题表单出现）→ fill_form → ...
```

| Hook/属性 | 默认实现 | 何时覆写 |
|------|---------|---------|
| `UPLOAD_FIRST` | `False`（表单先行） | **B站等先传视频后出表单的平台设 True**，框架自动调整 wait_form_ready/upload_video 顺序 |
| `UPLOAD_ENTRY_SELECTOR` | 空 | 视频先行模式下等待上传入口出现的选择器（如"点击上传"按钮/拖拽区）；留空直接尝试 file input |
| `open_publish_page` | 新开标签页打开发布页 | 页面含多 frame、需先跳登录再回跳 |
| `wait_login` | `ensure_login`：storageState 优先，缺失/过期 → VNC 登录并保存 | 登录后还有短信/滑块二次校验 |
| `wait_form_ready` | 等待 `FORM_READY_SELECTOR` 出现 | 表单异步渲染、需点击"开始创作"才出现；视频先行模式下它等的是转码完成后的表单 |
| `upload_video` | 找 file input set 文件（视频先行模式先等上传入口），随后 `after_upload_video` 等待转码 | 走系统文件选择（改人工）等特殊交互 |
| `after_upload_video` | 等待表单可用（超时 UPLOAD_TIMEOUT） | 平台有显式"转码完成"状态可精确等待 |
| `fill_form` | 遍历物料字段按 kind 分发 | 表单顺序/组合特殊（先选分区才解锁标题等） |
| `fill_field` | 按 kind 分发：text/textarea→选择器或 label；tags→输入+回车；select→下拉；checkbox→label 点击 | **树形分区、富文本、extra 字段** |
| `upload_cover` | 封面 file input 上传 | 封面需先裁剪（B站式） |
| `manual_checkpoint` | manual 模式提交前截图 + 阻塞等确认 | 手动审核时需展示额外信息 |
| `before_submit` | 空 | 提交前勾选原创声明/协议、二次确认弹窗 |
| `submit` | 按 `SUBMIT_SELECTOR` 或"发布"文本点击 | 分步发布（保存草稿→再发布） |
| `wait_result` | 等待 `SUBMIT_OK_URL_CONTAINS` / `SUBMIT_OK_SELECTOR` | 成功提示是 toast/弹窗/跳转混合 |

## 扩展步骤（首次发布执行中）

```bash
# 1. 新建平台发布脚本（不要复制模板，按需参考）
#    {platform_dir}/publish_scripts/{platform}_publish.py

# 2. 编写子类（骨架）：
```

```python
from lib.publish_framework import PlatformPublisher

class BilibiliPublisher(PlatformPublisher):
    PUBLISH_URL = "https://member.bilibili.com/platform/upload/video/frame"
    FORM_READY_SELECTOR = "input[placeholder*='标题']"
    TAGS_SELECTOR = "input[placeholder*='标签']"
    SUBMIT_SELECTOR = "button:has-text('发布')"
    SUBMIT_OK_URL_CONTAINS = "/manage/create"
    # 需要时才覆写 hook...

if __name__ == "__main__":
    BilibiliPublisher.run_cli()
```

```bash
# 3. 回填 platform_config.yaml 的 publish_script 字段（绝对路径）
# 4. verify_platform_config.py 校验；publish_video.py 执行发布
```

`publish_video.py` 会把 skill 的 `scripts/` 注入子进程 PYTHONPATH，平台脚本
无论位于何处都能 `from lib.publish_framework import PlatformPublisher`。

## 按平台类型的扩展模式

### A. 标准表单型（多数平台）
文本标题 + 文本域简介 + 标签 + 下拉分区 + 文件上传。只需填写类属性，
不需要覆写任何 hook。

### B. 树形/级联分区型（如 B站、西瓜）
`PARTITION_SELECTOR` 无法覆盖 → 覆写 `fill_field`：

```python
def fill_field(self, name, value, kind, label):
    if name == "partition":
        click_by_text(self.page, value)  # 一级分区，然后点二级（探测后写）
        # 若多级：value 用 "一级 / 二级" 分隔，依次点击
        return
    super().fill_field(name, value, kind, label)
```

### C. 强验证型（抖音、视频号等）
登录/提交后常有滑块、短信、风控 → 覆写 `wait_login` 与 `submit` 后的等待：

```python
def wait_login(self):
    super().wait_login()  # 框架登录（含 storageState 保存）
    human_wait_selector(self.page, "请通过 VNC 完成安全校验（滑块/短信）",
                        "text=校验通过", timeout=self.LOGIN_TIMEOUT)
```

### D. 视频先行型（B站等：先传视频、转码完成才出表单）
**首选：配置 `UPLOAD_FIRST = True` + `UPLOAD_ENTRY_SELECTOR`**，框架自动
调整时序（先等上传入口 → 上传 → 等表单出现），无需覆写方法（见上文
"视频先行型"示例）。

仅当上传入口需要额外点击交互（如先点按钮再出现 file input）时再覆写：

```python
def upload_video(self):
    click_by_text(self.page, "点击上传")   # 特殊入口交互
    super().upload_video()                # 框架的 file input 上传 + 等待
```

上传完成后需点"继续"的平台可覆写 `after_upload_video` 追加。注意：**若平台
属于先传视频后出表单，请优先用 UPLOAD_FIRST，不要通过覆写方法改变顺序**——
时序是平台级属性，配置表达比方法覆写更清晰、更可复用。

### E. 提交前确认型
需勾选协议/原创声明或确认弹窗：

```python
def before_submit(self):
    super().before_submit()
    if self.field("original_declaration"):
        click_by_text(self.page, "未经作者授权，禁止转载")
    click_by_text(self.page, "确认")   # 弹窗确认
```

## 调试与自愈

- 每个 hook 中可用 `self.env("step", ...)` 输出进度；`self.screenshot(name)`
  保存截图到物料目录（agent 用 Read 查看）。
- 失败时框架自动输出 `status=error` + `self_heal=review_script_and_page`，
  agent 按 [self-healing.md](self-healing.md) 重新 probe → 修子类 → 重试。
- 页面改版只需改类属性/覆写对应 hook，**禁止**复制整个子类另起一份。

## 硬性规则

1. 平台脚本必须继承 `PlatformPublisher`，禁止脱离框架另写。
2. 同平台一份子类；新项目/新视频不复制改写。
3. 业务数据（标题/标签/分区/文件路径）只来自 yaml，禁止硬编码。
4. 登录/验证码/风控一律 `human_wait_*` + VNC 人机协作，禁止绕过验证。
