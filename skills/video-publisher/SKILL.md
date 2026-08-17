---
name: video-publisher
description: >
  Use when the user wants to publish/upload a video to a video website such as
  Bilibili (B站), Douyin (抖音), WeChat Channels (微信视频号), YouTube, or any
  other video platform. Trigger keywords: "发布这个视频到...", "上传视频到...",
  "发布到B站/抖音/视频号/youtube", "publish this video to ...", "post to ...".
  Automates the whole flow: environment check, platform/project init, cover
  image generation (comfyui-scheduler text-to-image), material assembly, and
  browser form-filling via CDP + headed Chromium with human-in-the-loop (VNC)
  support for login/captcha. Auto (default) and manual modes; multi-platform,
  multi-project; self-healing on failure. Do NOT trigger for video editing,
  encoding, trimming, or downloading.
argument-hint: "[视频文件或目录] [平台] [项目(可选)]"
effort: high
category: Content Creation
version: 1.0.0
created: 2026-08-13
permissions:
  - env
  - file_read
  - file_write
  - network
  - shell
dependencies:
  - comfyui-scheduler
metadata:
  requires:
    bins: [python3, ffmpeg, ffprobe, comfyui-scheduler]
    # python packages: see requirements.txt (install with pip install -r)
---

# Video Publisher（自动发布视频到视频网站）

通用化的视频网站自动发布 skill：**agent + 脚本配合**。能自动化的部分
（环境检查、目录/配置初始化、封面文生图、物料组装、浏览器表单自动化）
用 Python 脚本完成；无法自动化的部分（登录、验证码、风控校验、平台页面
改版适配）由文档指引 agent 转达用户，通过 VNC 人机协作完成。

## 触发方式

关键词触发，例如：
- "**发布这个视频到B站**"
- "把 D:\videos\xxx.mp4 上传到抖音"
- "发布到微信视频号，分类是科技"
- "publish this video to youtube"

首次使用某平台时自动执行「首次发布流程」——agent 直接走完整个发布流程，
**首次发布成功即完成平台接入**（过程中补充发布脚本与物料数据结构，下次
复用）；之后同平台发布走「非首次发布流程」。

## 依赖（Dependencies）

| 依赖 | 用途 | 安装 |
|------|------|------|
| Python >= 3.10 | 脚本运行时 | 系统安装 |
| requests / pyyaml / playwright | 网络、配置、浏览器自动化 | `pip install -r "${SKILL_DIR}/requirements.txt"` |
| ffmpeg / ffprobe | 视频元数据探测 | 系统安装并加入 PATH |
| comfyui-scheduler | 封面文生图 | `pip install -e <repo>`（https://github.com/calcuforge/comfyui-scheduler.git） |
| ComfyUI 服务 | 文生图后端 | 本地运行，默认 http://127.0.0.1:8188 |
| 有头浏览器 + VNC | 人机协作（登录/验证码） | 标准环境为 [hermes-hitl-environment](https://github.com/calcuforge/hermes-hitl-environment)（VNC:5900 / noVNC:6080 / CDP:9222），或 `launch_browser.py` 启动共享 Chromium；见 references/human-collab.md |

**脚本路径约定**：本 skill 所有脚本以 `${SKILL_DIR}/scripts/...` 引用，
`SKILL_DIR` = **包含本 SKILL.md 的目录**（agent 已加载本文件，取其绝对路径；
已设置 `CLAUDE_SKILL_DIR` 环境变量时直接使用）：

```bash
SKILL_DIR="${SKILL_DIR:-${CLAUDE_SKILL_DIR}}"
```

前置检查（每次发布的第一步，必须执行）：

```bash
SKILL_DIR="${SKILL_DIR:-${CLAUDE_SKILL_DIR}}"
python "${SKILL_DIR}/scripts/tool/check_prereqs.py" [--workspace <工作区>]
```

## 工作目录（输出约束）

**所有发布相关文件必须位于工作区 `video_publiser_data` 目录下，禁止写到
系统临时目录或工作区之外。** `video_publiser_data` 是**单独一层目录**（数据
根，不存在则新建），平台、项目目录在其下逐层展开，**目录名不带
`video_publiser_data` 前缀**：

```text
{workspace}/video_publiser_data/     # 数据根（单独一层目录，无前缀命名）
├── {platform}/                      # 平台目录，如 bilibili
│   ├── platform_config.yaml         # 平台级配置：物料数据结构 + 默认模板 + CDP/登录信息
│   ├── publish_scripts/             # 该平台自动化发布脚本（首次流程编写，可复用）
│   │   └── {platform}_publish.py
│   └── projects/
│       └── {project}/               # 项目目录，如 tech
│           ├── project_config.yaml  # 项目级配置：模式/发布默认值/封面生成配置
│           ├── materials/           # 每次发布的物料目录 {date}_{video_name}/
│           │   └── .../materials.yaml  # 物料数据（标题/简介/标签/分区/封面/视频）
│           └── tmp/                 # 临时文件（截图、探测 dump、自愈日志）
```

- **平台** = 视频网站（每个平台一个目录 + 平台级 yaml 配置，可任意扩展）。
- **项目** = 要发布视频的关键属性，如视频分类（每个项目一个目录 + 项目级
  yaml 配置，可任意扩展）。
- workspace 解析顺序：`--workspace` 参数 > 环境变量 `VIDEO_PUBLISHER_WORKSPACE`
  > 当前工作目录。
- 配置文件的完整填写示例见 `templates/example_configs/`（含 B站平台配置、
  tech 项目配置、一次发布的物料数据），agent 编写配置时可参考其格式。


## 执行模式

| 模式 | 行为 |
|------|------|
| **Auto（默认）** | 使用平台 `default_config` 默认模板自动完成，无人为暂停 |
| **Manual（手动）** | 关键步骤暂停，用户审核后继续 |

模式写入 `project_config.yaml` 的 `project.creation_mode`。**每次步骤边界
都从配置文件重读该字段，不要依赖对话记忆。** 用户明确要求"手动/一步步来/
我要确认"时初始化 manual 模式。

Manual 模式确认点：
1. 初始化项目前 —— 确认项目参数与默认发布值；
2. 物料生成后 —— 确认标题/封面/标签/分区（修改 materials.yaml）；
3. 提交发布前 —— 脚本暂停并截图，用户确认后才提交。

## 发布流程

### 首次发布流程（平台无配置或无发布脚本时）

**核心思想：不做独立探测步骤——agent 直接走完整个发布流程，首次发布成功
即完成平台接入**（执行中补充发布脚本与物料数据结构，下次复用）：

```
1. 收到用户发布视频指令（解析：视频文件、平台、项目）
2. 运行环境检查（check_prereqs.py）
3. 平台检测与目录、配置初始化（init_workspace.py → init_platform.py → verify）
4. 项目检测与目录、配置初始化（init_project.py → verify）
5. 物料数据生成（generate_material.py：ffprobe + comfyui-scheduler 封面文生图）
6. 首次发布执行 ★（走完整发布流程，边发布边沉淀资产）
7. 发布成功 → 资产已落盘，汇报结果
```

**步骤 6 详解（「首次发布执行」）：**

1. **编写最小发布脚本**：基于通用发布框架 `scripts/lib/publish_framework.py`
   的 `PlatformPublisher` 写最小子类（登录态管理 storageState + VNC 人机协作、
   通用填表、上传、提交、错误 envelope 开箱即用），先填已知选择器，其余
   留空走框架通用实现，参考 `scripts/publish_scripts/template_publish.py` 与
   `references/publish-framework.md`。
2. **执行发布**：`publish_video.py` 运行脚本，逐步完成 登录 → 上传视频 →
   填表 → 封面上传 → 提交。登录/验证码/风控时脚本阻塞等待，agent 实时转达
   用户（自动经 agent channel 推送），绝不绕过验证。
3. **执行中沉淀资产（不做单独探测步骤）**：定位失败或需确认页面结构时，
   用 `probe_page.py` 抓取 DOM 或查看截图，然后修复脚本（补选择器/覆写
   hook）重试；把确认的表单字段、候选值（分区选项）、控件定位写入
   `platform_config.yaml` 的 `material_structure.fields` 并完善
   `default_config` 与 `login_indicator`。
4. **成功即落盘**：发布成功后固化脚本选择器，回填 `publish_script` 字段，
   运行 `verify_platform_config.py` 校验（WARN 应已消失）。此后该平台所有
   发布走非首次流程。
   **脚本规范**：必须继承框架（禁止脱离框架另写）；同平台所有项目共用一份
   （禁止复制改写）；业务数据只来自 yaml；每步输出 `@ENV@` 进度；失败抛错
   退出非零（触发自愈循环，见 references/self-healing.md）。

### 非首次发布流程（平台已有配置与发布脚本）

```
1. 收到用户发布视频指令
2. 平台检测（配置与脚本存在性）
3. 项目检测（存在则复用，否则 init_project.py）
4. 物料数据生成
5. 执行发布脚本
6. 成功 → 汇报；失败 → 回到"首次发布执行"的沉淀环节（修复脚本/物料结构后重试）
```

详细步骤与命令见 references/workflow-first-publish.md 与
references/workflow-publish.md。

## 人机协作要点

- **环境端口约定对齐 hermes-hitl-environment**：agent 经 CDP(9222) 驱动共享
  有头 Chromium，用户经 VNC(5900) / noVNC(6080/vnc.html) 观察与介入。
  解析优先级：命令行参数 > 环境变量（`PLAYWRIGHT_CDP_URL` /
  `CHROME_REMOTE_DEBUGGING_PORT` / `VNC_PORT` / `NOVNC_PORT`）> 平台配置
  （`platform.cdp`）> 默认值。启动共享浏览器用 `scripts/tool/launch_browser.py`
  （对齐 hermes 的 launch-chromium.sh），或直接运行 hermes-hitl-environment。
- 发布过程通过 **CDP 调用有头浏览器**，用户可经 **VNC** 观察与介入。
- **登录态管理（storageState 优先）**：编写 playwright 自动化脚本时，登录态
  必须用 storageState 保存（平台级 `storage_state.json`，路径可由
  `platform_config.yaml` 的 `platform.login.storage_state_path` 覆盖）。
  每次发布优先复用登录态；**缺失或过期**（打开页面后未命中
  `login_indicator`）时启用 VNC 人机协作登录，成功后自动保存登录态。
  实现位于 `lib/cdp.ensure_login()`，发布框架 `PlatformPublisher.wait_login`
  默认调用（子类可覆写追加短信/滑块二次校验等待）。
- 脚本遇到登录/验证码/风控等会输出 `@ENV@ {"env_status": "human_collab", ...}`
  并**阻塞等待**。agent 必须原样转达用户：
  > ⚠ 需要用户通过 VNC 配合：<操作说明>，脚本正在等待（每 30s 心跳）。

  直到出现 `human_collab_done` 或失败才继续/重试。
- **agent channel 推送**：脚本输出人机协作提示时自动通过配置的 channel 推送
  通知（登录态/验证码场景）；若配置了 `agent_channel`（`{workspace}/video_
  publiser_data/agent_channel.yaml` 或环境变量 `AGENT_CHANNEL`，支持
  command/webhook 两种类型）则推送，失败仅警告不影响流程。agent 也可用
  `scripts/tool/notify.py --message "..."` 手动补推。详见 human-collab.md。
- 具体协议、浏览器启动方式、等待条件写法见 references/human-collab.md。

## 自愈机制

发布失败（脚本非零退出）→ 回到「首次发布执行」的沉淀环节：记录失败 →
按需 probe 页面（可能已改版）→ 修复脚本/物料结构 → 校验 → 幂等重试。
连续两次失败仍无法定位则停止并携带证据（截图/日志/dump）向用户报告。
详见 references/self-healing.md。

## 新平台接入

平台即目录，支持任意视频网站：B站、抖音、微信视频号、youtube 内置别名，
其他平台（小红书、快手等）按 references/platform-integration.md 接入：
`init_platform.py --platform <标识>` → 探测页面 → 完善配置 → 编写发布脚本。

## 硬性规则（Hard Rules）

1. **输出约束**：所有文件写入 `video_publiser_data` 下，禁止系统临时目录。
2. **模式来源**：每次从 `project_config.yaml` 读取 `creation_mode`。
3. **物料契约**：发布脚本只消费 materials.yaml 与配置，禁止硬编码业务数据。
4. **框架复用**：平台发布脚本必须继承 `PlatformPublisher` 框架；同平台一份
   子类，新项目/新视频不得复制改写成另一份。
5. **不绕过验证**：登录/验证码一律人工（VNC），脚本只等待、不破解。
6. **失败必自愈**：失败先诊断（probe + 审查），禁止盲目重试。
7. **转达提示**：`@ENV@ human_collab` 消息必须转达用户，不得静默等待。

## References

- [workflow-first-publish.md](references/workflow-first-publish.md) — 首次发布流程（含首次发布执行详解）
- [publish-framework.md](references/publish-framework.md) — 发布脚本框架扩展指南（hooks + 平台类型模式）
- [workflow-publish.md](references/workflow-publish.md) — 非首次发布流程
- [human-collab.md](references/human-collab.md) — VNC + CDP 人机协作协议
- [self-healing.md](references/self-healing.md) — 自愈机制
- [platform-integration.md](references/platform-integration.md) — 新平台接入指南
