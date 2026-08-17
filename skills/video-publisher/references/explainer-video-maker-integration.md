# 联动 explainer-video-maker（视频来源识别与物料生成）

> **何时加载：** 用户要发布的视频疑似由 explainer-video-maker skill 制作，
> 或视频文件所在目录存在 `video_config.yaml`。

## 识别方法

explainer-video-maker 的产物结构为
`projects/{项目}/{视频名}/video_config.yaml` + `result.mp4`（同目录）。
**判定特征：视频文件同目录存在 `video_config.yaml`** —— 是即视为
explainer-video-maker 制作，按本指引归类和生成物料。

`video_config.yaml` 可用字段：

| 字段 | 含义 | 用途 |
|------|------|------|
| `topic` | 视频主题（标题核心） | 项目归类、标题、封面提示词 |
| `summary` | 视频摘要 | 简介、封面提示词 |
| `chapter_summaries` | 各章节摘要（dict） | 可选：更细的简介/标签参考 |

## 项目归类（项目检测步骤）

1. 读取 `topic`，推断内容分类（科技/游戏/知识/生活/美食...）；
2. 若 explainer 项目目录名为分类化命名（`content_structure_params`，
   如 `air_crash_documentary_1080p_horizontal`），取**内容分类部分**
   （如 `air_crash`）作为候选项目名；
3. 在 `{平台}/projects/` 下查找同名项目，不存在则用
   `init_project.py` 创建（候选名作为 `--project-dir-name`）。

## 物料生成（物料数据生成步骤）

`generate_material.py` 传入 `--video-config`：

```bash
python "${SKILL_DIR}/scripts/tool/generate_material.py" \
    --project-config <...>/project_config.yaml \
    --platform-config <...>/platform_config.yaml \
    --video-file <...>/result.mp4 \
    --video-config <...>/video_config.yaml
```

自动生效的行为：

- **标题**：未配置 `title_format` 时直接用 `topic` 作为标题；配置了模板
  则模板可引用 `{topic}`（如 `"{topic} | 科技前沿"`）；
- **简介**：未配置 `description_format` 时用 `summary`（按平台字段
  `max_length` 截断）；配置了模板可引用 `{summary}`；
- **封面**：`cover.prompt` 可引用 `{topic}` / `{summary}` 生成与内容贴合的
  封面（如 `"主题：{topic}，纪录片风格封面"`）；
- 输出 envelope 会提示已读取的 topic，agent 可据此确认归类与标题合理。

## 示例

```bash
# 假设 explainer 产物:
#   projects/air_crash_documentary_1080p_horizontal/ai_air_crash/video_config.yaml
#   projects/air_crash_documentary_1080p_horizontal/ai_air_crash/result.mp4

# 1. 归类: topic → 航空/空难类 → 项目名 candidate: air_crash
python init_project.py --platform-dir <...>/bilibili --project-dir-name air_crash

# 2. 物料生成（标题=topic，简介=summary，封面提示词可引用 {topic}）
python generate_material.py --project-config <...>/project_config.yaml \
    --platform-config <...>/platform_config.yaml \
    --video-file <...>/result.mp4 \
    --video-config <...>/video_config.yaml
```

## 注意事项

- 若视频目录内没有 `video_config.yaml`（如手动导出的 mp4），按普通视频处理
  （标题用 `{video_name}`，无 topic/summary 占位符）。
- `chapter_summaries` 为可选增强：agent 可挑选关键章节关键词补充标签
  （`publish_defaults.tags`）。
- 项目归类结果如与用户预期不符（如用户指定了分类），以用户指定为准。
