# 配置示例参考目录（example_configs）

本目录演示 skill 运行过程中三类配置文件的**完整填写示例**，供 agent 在
「发布物料数据结构整理、编写该平台自动化发布脚本」和「物料数据生成」步骤
中参考格式与取值。示例场景：向 B 站发布科技分类视频《GPU架构详解》。

目录结构演示实际工作区布局：`video_publiser_data` 为**单独一层目录**（数据
根），平台/项目目录在其下逐层展开，目录名不带 `video_publiser_data` 前缀：

```text
example_configs/
└── video_publiser_data/             # 数据根（= {workspace}/video_publiser_data）
    ├── agent_channel.yaml            # 工作区级人机协作通知推送配置（可选）
    └── bilibili/                     # 平台目录
        ├── platform_config.yaml      # 平台级配置（B站，含物料数据结构与默认模板）
        └── projects/tech/            # 项目目录
            ├── project_config.yaml   # 项目级配置（tech 科技类）
            └── materials/20260813_gpu_architecture/
                └── materials.yaml    # 单次发布的物料数据
```

文件中的路径均为示例占位（`{workspace}` = 实际工作区绝对路径）。实际运行时：

- `platform_config.yaml` 由 `init_platform.py` 生成骨架，agent 在首次发布流程
  探测发布页后完善（本示例即为完善后的形态）；
- `project_config.yaml` 由 `init_project.py` 生成骨架，agent 按请求填写；
- `materials.yaml` 由 `generate_material.py` 自动生成，agent/用户审核修改。

**注意**：示例仅为参考，平台真实表单结构可能变化，必须以 `probe_page.py`
对实际发布页的探测结果为准。
