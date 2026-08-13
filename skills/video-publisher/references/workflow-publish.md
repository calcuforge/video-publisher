# 非首次发布流程（Workflow — Publish）

> **何时加载：** 目标平台已有 `platform_config.yaml` 且发布脚本
> `publish_scripts/{platform}_publish.py` 可用（`publish_script` 字段已回填）。
> 大部分发布走本流程，简洁高效。

## 流程总览

```
1. 收到用户发布视频指令
2. 平台检测
3. 项目检测
4. 物料数据生成
5. 执行发布脚本
6. 成功 → 汇报；失败 → 回到"发布物料数据结构整理、编写该平台自动化发布脚本"
   （首次流程步骤 4，见 workflow-first-publish.md）
```

## 步骤 1 — 收到用户发布视频指令

解析三要素（视频、平台、项目），平台别名与首次流程一致。

## 步骤 2 — 平台检测

- 检查 `{workspace}/video_publiser_data/{platform}/platform_config.yaml` 是否存在。
- 不存在 → 转入首次发布流程；存在 → 校验 `publish_script` 指向的脚本是否存在，
  不存在 → 转入首次流程步骤 4。

## 步骤 3 — 项目检测

- 按视频内容推断分类，查找 `{platform}/projects/{name}/project_config.yaml`。
- 不存在 → `init_project.py` 初始化新项目（沿用已有项目的 `cover`/`publish_defaults`
  作为参考，向用户确认或按默认值生成）。
- 存在 → 读取 `project.creation_mode` 决定模式，读取 `publish_defaults` 作为取值来源。
- **模式必须从配置文件读取，不要依赖对话记忆。** 每次发布前重新读一遍。

## 步骤 4 — 物料数据生成

同首次流程步骤 6（generate_material.py + 手动模式审核点）。

## 步骤 5 — 执行发布脚本

同首次流程步骤 7（publish_video.py + 人机协作 + 手动模式提交前确认点）。

## 步骤 6 — 成功汇报 / 失败自愈

- 成功：汇报结果。
- 失败：回到"发布物料数据结构整理、编写该平台自动化发布脚本"步骤
  （首次流程步骤 4），按 [self-healing.md](self-healing.md) 处理：
  重新 probe → 修复脚本/物料结构 → 重试。
