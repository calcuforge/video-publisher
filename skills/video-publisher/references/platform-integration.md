# 新平台接入指南（Platform Integration）

> **何时加载：** 用户要求发布到不在内置列表（bilibili / douyin /
> wechat_channels / youtube）的平台，或内置平台配置缺失。
> 每个平台对应 `video_publiser_data` 下的一个目录，不存在则新建。

## 接入步骤

### 1. 目录与配置初始化

```bash
# SKILL_DIR = 包含 SKILL.md 的目录（agent 已加载该文件，取其绝对路径）
SKILL_DIR="${SKILL_DIR:-${CLAUDE_SKILL_DIR}}"
python "${SKILL_DIR}/scripts/tool/init_workspace.py" --workspace <工作区>
python "${SKILL_DIR}/scripts/tool/init_platform.py" --workspace <工作区> --platform <平台标识>
```

- 平台标识用英文小写（如 `xiaohongshu`、`kuaishou`）。内置别名表见
  `init_platform.py` 的 `PLATFORM_ALIASES` —— 新平台接入后把常用别名加进去，
  并在 `platform_config.yaml` 的 `platform.aliases` 中登记。

### 2. 完善平台配置（首次发布执行过程中沉淀）

不预先探测页面：`init_platform.py` 先建骨架，**在首次发布执行过程中**根据
实际页面确认的信息完善 `platform_config.yaml`：

```yaml
platform:
  name: xiaohongshu
  aliases: [小红书, xiaohongshu]
  publish_page_url: https://creator.xiaohongshu.com/publish/publish
  login_indicator:
    url_contains: ""      # 登录后 URL 特征（任一命中即视为已登录）
    selector: ""          # 已登录元素特征选择器
  login:
    storage_state_path: ""  # 留空默认 {data_dir}/storage_state.json（storageState 登录态）
  # 端口对齐 hermes-hitl-environment：人类 VNC(5900)/noVNC(6080)，agent CDP(9222)
  # 解析优先级：环境变量（PLAYWRIGHT_CDP_URL/CHROME_REMOTE_DEBUGGING_PORT/
  # VNC_PORT/NOVNC_PORT）> 以下配置 > 默认值
  cdp:
    host: 127.0.0.1
    port: 9222
    vnc_port: 5900
    novnc_port: 6080
    browser_path: "" # 留空 = playwright chromium；可指向系统 Chrome/Edge
    profile_dir: "" # 浏览器持久 profile（登录态兜底），留空用默认
    downloads_dir: ""
material_structure:
  fields: {...}           # 首次发布执行过程中按实际表单补充（字段/候选值，见下）
default_config: {...}     # 自动模式默认模板（执行中完善）
publish_script: ""        # 首次发布成功后回填
```

### 3. 物料数据结构约定

`material_structure.fields` 是 agent 与脚本之间唯一的物料契约，
字段 `kind` 取值：

| kind | 含义 | 物料值 |
|------|------|--------|
| text | 单行文本（标题等） | 字符串 |
| textarea | 多行文本（简介） | 字符串 |
| tags | 标签列表 | 字符串数组 |
| select | 下拉/单选（分区） | 选项字符串，`candidates` 给出候选值 |
| image | 封面图片 | 本地图片绝对路径 |
| video | 视频文件 | 本地视频绝对路径 |
| checkbox | 开关（如"声明原创"） | bool |
| extra | 平台特有字段（如合集、定时发布） | 字符串，由 agent 在物料阶段填写 |

新平台请完整梳理表单的每个字段并登记候选值，**缺字段会导致发布脚本
无法完成表单**。

### 4. 编写平台发布脚本（基于通用发布框架，首次发布执行中完成）

平台脚本**继承通用发布框架** `lib/publish_framework.py` 的
`PlatformPublisher`：框架提供登录态管理（storageState + VNC 人机协作）、
通用填表、上传、提交、结果等待；子类填写选择器类属性并覆写平台差异 hook。
**首次发布执行中**先写最小子类 → 执行发布 → 失败时按需 probe 页面并修复
脚本/补充选择器 → 成功后固化并回填 `publish_script` 字段。扩展指南见
[publish-framework.md](publish-framework.md)（可参考
`scripts/publish_scripts/template_publish.py` 示例）。同一平台只维护一份
子类（框架可复用原则）。

### 5. 平台特有提示词库（可选）

若平台对封面规格有特殊要求（尺寸/比例/文字安全区），在
`platform_config.yaml` 增加 `cover_spec` 段：

```yaml
cover_spec:
  width: 1242
  height: 1660
  ratio: "3:4"
  note: 小红书封面竖版 3:4，注意底部留白
```

agent 生成封面（generate_material.py）时以此为准写入项目 `cover` 配置。

## 平台列表维护

接入完成后建议在本文件中登记：

| 平台标识 | 别名 | 发布页 | 封面规格 | 备注 |
|---------|------|--------|---------|------|
| bilibili | B站/哔哩哔哩 | member.bilibili.com/... | 3:2 (1600x1000) | 内置 |
| douyin | 抖音 | creator.douyin.com/... | 竖版 3:4 | 内置 |
| wechat_channels | 微信视频号 | channels.weixin.qq.com/... | 9:16 | 内置 |
| youtube | 油管 | studio.youtube.com/... | 16:9 (1280x720) | 内置 |
| (新平台) | | | | |
