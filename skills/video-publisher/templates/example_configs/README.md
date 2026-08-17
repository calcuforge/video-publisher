# 配置示例参考目录（example_configs）

本目录演示 skill 运行过程中三类配置文件的**完整填写示例**，供 agent 在
「发布物料数据结构整理、编写该平台自动化发布脚本」和「物料数据生成」步骤
中参考格式与取值。示例场景：向 B 站发布科技分类视频《GPU架构详解》。

目录结构同时演示工作区命名约定 `video_publiser_data-[平台]-[项目]`：

```text
example_configs/
└── video_publiser_data-bilibili-tech/
    ├── platform_config.yaml          # 平台级配置（B站，含物料数据结构与默认模板）
    └── projects/tech/
        ├── project_config.yaml       # 项目级配置（tech 科技类）
        └── materials/20260813_gpu_architecture/
            └── materials.yaml        # 单次发布的物料数据
```

文件中的路径均为示例占位（`{workspace}` = 实际工作区绝对路径）。实际运行时：

- `platform_config.yaml` 由 `init_platform.py` 生成骨架，agent 在首次发布流程
  探测发布页后完善（本示例即为完善后的形态）；
- `project_config.yaml` 由 `init_project.py` 生成骨架，agent 按请求填写；
- `materials.yaml` 由 `generate_material.py` 自动生成，agent/用户审核修改。

**注意**：示例仅为参考，平台真实表单结构可能变化，必须以 `probe_page.py`
对实际发布页的探测结果为准。
