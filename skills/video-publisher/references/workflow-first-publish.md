# 首次发布流程（Workflow — First Publish）

> **何时加载：** 目标平台在 `video_publiser_data` 下没有 `platform_config.yaml`，
> 或没有可用的平台发布脚本 `publish_scripts/{platform}_publish.py`
> （`publish_script` 字段为空）。
>
> **核心思想：不去预先探测页面再写脚本，而是让 agent 直接走完整个发布流程
> ——首次发布本身就是一次真实的发布执行**。发布过程中逐步补充平台发布脚本
> 与物料数据结构（表单字段、候选值、控件定位），首次发布成功即完成资产
> 落盘，此后同平台发布走 [workflow-publish.md](workflow-publish.md)（非首次
> 流程）复用。

## 流程总览

```
1. 收到用户发布视频指令
2. 运行环境检查
3. 平台检测与目录、配置初始化
4. 项目检测与目录、配置初始化
5. 物料数据生成（按通用物料结构 + 项目/平台默认值）
6. 首次发布执行 ★（agent 走完整发布流程，边发布边补充脚本与物料结构）
7. 发布成功 → 资产已落盘，汇报结果；后续同平台发布走非首次流程
```

---

## 步骤 1 — 收到用户发布视频指令

从用户消息中解析三要素：

| 要素 | 说明 | 示例 |
|------|------|------|
| 视频 | 待发布的视频文件或目录 | `发布这个视频到B站` |
| 平台 | 目标平台（支持别名） | B站 / 抖音 / 微信视频号 / youtube |
| 项目 | 视频分类（可选，默认询问或按视频内容推断） | 科技 / 游戏 |

若用户只给了平台没给视频文件，先在工作区或常见视频目录下查找最新视频，
找不到则询问用户。平台别名映射见 `init_platform.py` 的 `PLATFORM_ALIASES`。

## 步骤 2 — 运行环境检查

```bash
# SKILL_DIR = 包含 SKILL.md 的目录（agent 已加载该文件，取其绝对路径）
SKILL_DIR="${SKILL_DIR:-${CLAUDE_SKILL_DIR}}"
python "${SKILL_DIR}/scripts/tool/check_prereqs.py" [--workspace <工作区>]
```

- 检查项：Python、requests/pyyaml/playwright、ffmpeg/ffprobe、comfyui-scheduler
  CLI、playwright chromium、`video_publiser_data` 工作区。
- 缺失即报错并给出修复命令。CDP 端口不可达仅警告（发布前需先启动有头浏览器）。
- 有头浏览器 + VNC 的启动方式见 [human-collab.md](human-collab.md)。

## 步骤 3 — 平台检测与目录、配置初始化

```bash
python "${SKILL_DIR}/scripts/tool/init_workspace.py" --workspace <工作区>
python "${SKILL_DIR}/scripts/tool/init_platform.py" --workspace <工作区> --platform <平台或别名>
python "${SKILL_DIR}/scripts/verify/verify_platform_config.py" --platform-config <...>/platform_config.yaml
```

- 平台目录结构：`{workspace}/video_publiser_data/{platform}/`，内含
  `platform_config.yaml` 与 `publish_scripts/`。
- 内置平台（bilibili/douyin/wechat_channels/youtube）别名自动归一；
  新平台按 [platform-integration.md](platform-integration.md) 接入。
- `platform_config.yaml` 此时是**骨架**：`material_structure.fields` 只有
  通用字段（title/description/tags/partition/cover/video），`publish_page_url`
  等为空属预期（verify 通过但带 WARN）——这些都在步骤 6 首次发布过程中补充。

## 步骤 4 — 项目检测与目录、配置初始化

**先识别视频来源**：若视频文件同目录存在 `video_config.yaml`
（explainer-video-maker 产物），按
[explainer-video-maker-integration.md](explainer-video-maker-integration.md)
用其 `topic` 与项目名归类（推断分类 → 同名项目复用/创建），并记下
`video_config.yaml` 路径供步骤 5 使用。

```bash
python "${SKILL_DIR}/scripts/tool/init_project.py" \
    --platform-dir {platform_dir} --project-dir-name <分类名>
python "${SKILL_DIR}/scripts/verify/verify_project_config.py" --project-config <...>/project_config.yaml
```

- 项目名 = 视频分类（如 tech / game / food），同名自动加数字后缀；
  来自 explainer-video-maker 的视频按其中信息归类。
- 编辑 `project_config.yaml`：`creation_mode`（默认 auto）、
  `publish_defaults`（标题/简介模板、默认标签、分区、auto_cover）、
  `material.video_source_dir`、`cover`（comfyui workflow、提示词、尺寸——
  workflow 名须为本机 comfyui-scheduler 已导入的实际工作流）。
- 封面规格参考平台要求（如 B 站封面 3:2，1600x1000），写入 `cover.width/height`。
- **手动模式确认点 #1**：manual 模式下，初始化前向用户确认项目参数与默认值。

## 步骤 5 — 物料数据生成

```bash
python "${SKILL_DIR}/scripts/tool/generate_material.py" \
    --project-config <...>/project_config.yaml \
    --platform-config <...>/platform_config.yaml \
    --video-file <待发布视频> \
    [--video-config <...>/video_config.yaml]   # 来自 explainer-video-maker 时必传
```

- **explainer-video-maker 联动**（步骤 4 识别到 `video_config.yaml` 时）：
  传 `--video-config`，标题直接用 `topic`（或模板引用 `{topic}`）、简介用
  `summary`、封面提示词可引用 `{topic}`/`{summary}`，详见
  [explainer-video-maker-integration.md](explainer-video-maker-integration.md)。
- ffprobe 探测视频元数据；按 `cover` 配置通过 **comfyui-scheduler 文生图**
  生成封面（提示词支持 `{title}` 占位符，按标题模板解析后注入）；组装
  `materials.yaml`（标题/简介/标签/分区/封面/视频路径）。
- 产物在 `{project}/materials/{date}_{video_name}/`。
- **手动模式确认点 #2**：manual 模式下，agent 展示物料数据（标题/封面/标签/
  分区）等待用户审核，修改 `materials.yaml` 后继续。

## 步骤 6 — 首次发布执行 ★（走完整发布流程，边发布边沉淀资产）

**这是首次发布的核心：agent 直接执行一次真实发布，而非先探测页面。**
发布成功本身 = 平台接入完成；过程中把实际观察到的页面结构沉淀为
`material_structure` 与发布脚本，供后续复用。

### 6a. 编写最小发布脚本

基于通用发布框架写一个最小子类（参考
`scripts/publish_scripts/template_publish.py` 与
[publish-framework.md](publish-framework.md)），先只填已知信息：

```python
# {platform_dir}/publish_scripts/{platform}_publish.py
from lib.publish_framework import PlatformPublisher

class BilibiliPublisher(PlatformPublisher):
    PUBLISH_URL = "https://member.bilibili.com/platform/upload/video/frame"
    # 其余选择器先用空值（走框架通用 label 匹配），执行失败时再补充
    # FORM_READY_SELECTOR / TITLE_SELECTOR / SUBMIT_SELECTOR 等

if __name__ == "__main__":
    BilibiliPublisher.run_cli()
```

- 登录态无需配置：框架 `wait_login` 自动处理（storageState 优先，缺失/过期
  时阻塞等待用户 VNC 登录并保存）。
- 登录指示 `login_indicator`（登录后 URL 特征/已登录元素特征）可在执行前
  从已知信息填写，或等首次登录后在执行中补充。

### 6b. 执行发布

```bash
python "${SKILL_DIR}/scripts/tool/publish_video.py" \
    --platform-config <...>/platform_config.yaml \
    --project-config <...>/project_config.yaml \
    --material <...>/materials.yaml
```

- 发布过程输出 `@ENV@` 进度行；遇到登录/验证码/风控时脚本阻塞等待，
  agent 必须实时转达用户（自动经 agent channel 推送），直到
  `human_collab_done` 或失败。
- **手动模式确认点 #3**：manual 模式下脚本在提交前暂停并截图，agent 将
  截图与内容摘要展示给用户，确认后才继续发布。

### 6c. 执行中补充物料结构与脚本（资产沉淀）

**不要单独安排"探测步骤"——页面结构信息在发布执行中按需获取**：

- **执行失败/定位不中时**：用 `probe_page.py` 抓取当前页面 DOM 结构
  （或查看框架保存的截图），确认真实控件后**修复脚本**（补选择器、覆写
  hook）并重试——这与自愈循环是同一件事，内嵌在首次发布中。
- **表单字段确认后**：把实际字段、候选值（如分区选项）、控件定位方式
  写入 `platform_config.yaml` 的 `material_structure.fields`；同步完善
  `default_config`（标题/简介模板、默认标签、默认分区、auto_cover）。
- **登录特征确认后**：回填 `login_indicator.url_contains`（登录后 URL 特征）
  与 `login_indicator.selector`（已登录元素特征）。

### 6d. 成功即落盘

发布成功后，把执行中实际生效的选择器/步骤固化进发布脚本（若 6a 用的是
空值则回填），运行 `verify_platform_config.py` 校验（WARN 应已消失），
确认 `publish_script` 字段已回填。**此后该平台所有发布走非首次流程。**

## 步骤 7 — 汇报

向用户汇报发布结果（页面 URL/状态），并可记录到项目 `tmp/` 的发布历史。
若步骤 6 连续失败两次仍无法定位（页面异常/需求不明），停止并携带证据
（截图/日志/probe dump）向用户报告，按 [self-healing.md](self-healing.md)
处理。
