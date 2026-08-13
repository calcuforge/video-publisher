# 新平台接入指南（Platform Integration）

> **何时加载：** 用户要求发布到不在内置列表（bilibili / douyin /
> wechat_channels / youtube）的平台，或内置平台配置缺失。
> 每个平台对应 `video_publiser_data` 下的一个目录，不存在则新建。

## 接入步骤

### 1. 目录与配置初始化

```bash
python "${SKILL_DIR}/scripts/tool/init_workspace.py" --workspace <工作区>
python "${SKILL_DIR}/scripts/tool/init_platform.py" --workspace <工作区> --platform <平台标识>
```

- 平台标识用英文小写（如 `xiaohongshu`、`kuaishou`）。内置别名表见
  `init_platform.py` 的 `PLATFORM_ALIASES` —— 新平台接入后把常用别名加进去，
  并在 `platform_config.yaml` 的 `platform.aliases` 中登记。

### 2. 完善平台配置（首次发布流程步骤 4 的产物）

在 `platform_config.yaml` 中填写：

```yaml
platform:
  name: xiaohongshu
  aliases: [小红书, xiaohongshu]
  publish_page_url: https://creator.xiaohongshu.com/publish/publish
  login_indicator:
    url_contains: ""      # 登录页 URL 特征（用于判断需要人工登录）
    selector: ""          # 已登录特征选择器
  cdp: {host: 127.0.0.1, port: 9222, browser_path: ""}
material_structure:
  fields: {...}           # 探测发布页后填写（字段/候选值，见下）
default_config: {...}     # 自动模式默认模板
publish_script: ""        # 编写发布脚本后回填
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

### 4. 编写平台发布脚本

按 `scripts/publish_scripts/template_publish.py` 的说明编写
`publish_scripts/{platform}_publish.py`，回填 `publish_script` 字段。
同一平台只维护一份脚本（可复用原则）。

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
