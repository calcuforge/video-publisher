# 首次发布流程（Workflow — First Publish）

> **何时加载：** 目标平台在 `video_publiser_data` 下没有 `platform_config.yaml`，
> 或没有可用的平台发布脚本 `publish_scripts/{platform}_publish.py`。
> 本流程完成平台接入 + 首次发布，之后同平台发布走
> [workflow-publish.md](workflow-publish.md)（非首次流程）。

## 流程总览

```
1. 收到用户发布视频指令
2. 运行环境检查
3. 平台检测与目录、配置初始化
4. 发布物料数据结构整理、编写该平台自动化发布脚本 ←（失败时回到这里）
5. 项目检测与目录、配置初始化
6. 物料数据生成
7. 执行发布脚本
8. 成功 → 汇报结果；失败 → 自愈（回到步骤 4）
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
- 本步骤只初始化骨架；物料数据结构（`material_structure`）在步骤 4 中完善。

## 步骤 4 — 发布物料数据结构整理、编写该平台自动化发布脚本 ★核心步骤

这是首次流程的核心，产物有两个：

### 4a. 探测发布页 DOM 结构（支持人机协作）

```bash
python "${SKILL_DIR}/scripts/tool/probe_page.py" \
    --cdp-url http://127.0.0.1:9222 \
    --url <平台发布页URL> \
    --output {platform_dir}/tmp/publish_page_dump.md \
    [--wait-url-contains <登录后跳转URL特征>]
```

- 脚本通过 CDP 调用**有头浏览器**打开发布页，输出页面所有可见控件
  （输入框/文本域/下拉/按钮/上传控件）及其属性到 markdown。
- **人机协作**：若打开发布页后被重定向到登录页，先指定
  `--wait-url-contains` 为**登录后发布页的 URL 特征**（如
  `member.bilibili.com/platform/upload`），脚本阻塞等待，agent 必须提示用户：
  > ⚠ 需要通过 VNC 在有头浏览器中登录 <平台>，脚本正在等待...

  用户登录完成后跳回发布页，探测自动继续。
- 探测完成后，把登录指示（`login_indicator.url_contains` = 登录后 URL 特征、
  `login_indicator.selector` = 已登录元素特征）写入 platform_config.yaml；
  发布脚本随后会用 storageState 保存登录态，后续发布不再需要人工登录
  （见 human-collab.md「登录态管理」）。
- 探测结果包含 iframe 内控件（很多平台的发布页是 iframe），分析时注意主 frame。

### 4b. 整理物料数据结构 → 写入平台配置

阅读 dump 文件，梳理发布表单的**字段、候选值、控件定位方式**，完善
`platform_config.yaml`：

```yaml
material_structure:
  fields:
    title:        { label: 标题, kind: text, required: true, max_length: 80 }
    description:  { label: 简介, kind: textarea }
    tags:         { label: 标签, kind: tags, required: true, max_count: 3 }
    partition:    { label: 分区, kind: select, required: true,
                    candidates: [科技, 游戏, 生活] }   # 探测到的分区选项
    cover:        { label: 封面, kind: image, required: true }
    video:        { label: 视频文件, kind: video, required: true }
```

同时生成/完善自动模式默认配置模板（`default_config`）：
标题模板、简介模板、默认标签、默认分区、`auto_cover`。
**规则：物料数据结构与默认模板保存在平台级配置中，供 agent 和脚本共同调用。**

回填平台信息：`publish_page_url`、`login_indicator.url_contains`（登录页特征）、
`login_indicator.selector`（已登录特征，如"投稿"按钮）。

### 4c. 编写平台自动化发布脚本

```bash
cp "${SKILL_DIR}/scripts/publish_scripts/template_publish.py" \
   {platform_dir}/publish_scripts/{platform}_publish.py
```

按探测结果填写模板顶部的常量（选择器、登录特征、成功特征），实现以下步骤：

1. 连接有头浏览器（CDP），打开发布页
2. `wait_login` — 未登录则 `human_wait_url` 阻塞等待，输出 VNC 提示
3. 上传视频 → `human_wait_selector` 等待上传/转码完成
4. 填写标题/简介/标签/分区（`fill_by_label` / `fill_by_placeholder` /
   `select_by_text`，探测结果里没有 label 关联时用 CSS 选择器）
5. 上传封面
6. 提交发布 → 成功特征出现或 `human_wait` 等待人工处理风控
7. 输出最终 envelope

**脚本规范（可复用原则）**：
- 同一平台的所有项目/所有视频共用一份脚本，业务数据只来自 yaml 配置；
- 每一步用 `env_out()` 输出进度；失败抛 `RuntimeError`（非零退出触发自愈）；
- 登录/验证码/风控一律用 `human_wait_*` 阻塞 + `@ENV@` 提示，不尝试绕过验证。

最后回填 `platform_config.yaml` 的 `publish_script` 字段，并运行
`verify_platform_config.py` 校验。

## 步骤 5 — 项目检测与目录、配置初始化

```bash
python "${SKILL_DIR}/scripts/tool/init_project.py" \
    --platform-dir {platform_dir} --project-dir-name <分类名>
python "${SKILL_DIR}/scripts/verify/verify_project_config.py" --project-config <...>/project_config.yaml
```

- 项目名 = 视频分类（如 tech / game / food），同名自动加数字后缀。
- 编辑 `project_config.yaml`：`creation_mode`（默认 auto）、
  `publish_defaults`（标题/简介模板、默认标签、分区、auto_cover）、
  `material.video_source_dir`、`cover`（comfyui workflow、提示词、尺寸）。
- 封面规格参考平台要求（如 B 站封面 3:2，1600x1000），写入 `cover.width/height`。
- **手动模式确认点 #1**：manual 模式下，初始化前向用户确认项目参数与默认值。

## 步骤 6 — 物料数据生成

```bash
python "${SKILL_DIR}/scripts/tool/generate_material.py" \
    --project-config <...>/project_config.yaml \
    --platform-config <...>/platform_config.yaml \
    --video-file <待发布视频>
```

- ffprobe 探测视频元数据；按 `cover` 配置通过 **comfyui-scheduler 文生图**
  生成封面（提示词模板支持 `{title}` 占位符，文生图实现参考 explainer-video-maker
  的 run_aigc.py 模式）；组装 `materials.yaml`（标题/简介/标签/分区/封面/视频路径）。
- 产物在 `{project}/materials/{date}_{video_name}/`。
- **手动模式确认点 #2**：manual 模式下，agent 展示物料数据（标题/封面/标签/
  分区）等待用户审核，修改 `materials.yaml` 后继续。
- 封面生成失败不阻断流程（警告并继续），agent 可让用户手动提供封面。

## 步骤 7 — 执行发布脚本

```bash
python "${SKILL_DIR}/scripts/tool/publish_video.py" \
    --platform-config <...>/platform_config.yaml \
    --project-config <...>/project_config.yaml \
    --material <...>/materials.yaml
```

- 发布过程中 `@ENV@` 提示需要人工介入时（登录/验证码/风控），agent 必须
  实时转达用户：**"请通过 VNC 在浏览器中完成 <操作>，脚本正在等待"**，
  直到脚本输出 `human_collab_done`。
- **手动模式确认点 #3**：manual 模式下脚本会在提交前暂停并截图，agent
  将截图与内容摘要展示给用户，确认后才继续发布。

## 步骤 8 — 成功汇报 / 失败自愈

- 成功：向用户汇报发布结果（页面 URL/状态），并可记录到项目 `tmp/` 的
  发布历史。
- 失败（脚本退出非零，`data.self_heal` 为 `review_script_and_page`）：
  回到步骤 4，按 [self-healing.md](self-healing.md) 执行自愈：
  重新探测页面（页面结构可能已变化）→ 审查并修复脚本 → 重试。
