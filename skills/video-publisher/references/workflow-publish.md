# 非首次发布流程（Workflow — Publish）

> **何时加载：** 目标平台已有 `platform_config.yaml` 且发布脚本
> `publish_scripts/{platform}_publish.py` 可用（`publish_script` 字段已回填，
> 首次发布已成功落盘）。大部分发布走本流程，简洁高效。

## 流程总览

```
1. 收到用户发布视频指令
2. 平台检测
3. 项目检测
4. 物料数据生成
5. 执行发布脚本
6. 成功 → 汇报；失败 → 回到"首次发布执行"的沉淀环节
   （修复脚本/物料结构后重试，见 workflow-first-publish.md 步骤 6）
```

## 步骤 1 — 收到用户发布视频指令

解析三要素（视频、平台、项目），平台别名与首次流程一致。

## 步骤 2 — 平台检测

- 检查 `{workspace}/video_publiser_data/{platform}/platform_config.yaml` 是否存在。
- 不存在 → 转入首次发布流程；存在 → 校验 `publish_script` 指向的脚本是否存在，
  不存在 → 转入首次发布流程的「首次发布执行」步骤。

## 步骤 3 — 项目检测

- **先识别视频来源**：若视频文件同目录存在 `video_config.yaml`
  （explainer-video-maker 产物），按
  [explainer-video-maker-integration.md](explainer-video-maker-integration.md)
  用其 `topic` 归类并复用/创建项目；记下 `video_config.yaml` 路径供步骤 4 使用。
- 否则按视频内容推断分类，查找 `{platform}/projects/{name}/project_config.yaml`。
- 不存在 → `init_project.py` 初始化新项目（沿用已有项目的 `cover`/`publish_defaults`
  作为参考，向用户确认或按默认值生成）。
- 存在 → 读取 `project.creation_mode` 决定模式，读取 `publish_defaults` 作为取值来源。
- **模式必须从配置文件读取，不要依赖对话记忆。** 每次发布前重新读一遍。

## 步骤 4 — 物料数据生成

同首次流程步骤 5（generate_material.py + `--video-config` 联动 + 手动模式审核点）。
**标题必须套用吸引力手法**（悬念/数字/承诺/情绪/对比，见
[title-guide.md](title-guide.md)）：`title_format` 引用 `{topic}` 配置
或编辑 `materials.yaml` 的 title 字段；默认 `{video_name}`/裸 topic 不作为
最终标题。

## 步骤 5 — 执行发布脚本

同首次流程步骤 6b（publish_video.py + 人机协作 + 手动模式提交前确认点）。

**非首次发布的登录态/验证码场景（重点）**：非首次发布 ≠ 免登录——storageState
可能过期（token 失效、平台强制下线、cookie 被清），发布过程也可能遇到
验证码/风控校验。处理链路由脚本自动执行，agent 负责转达与跟进：

1. 脚本打开发布页后按 `login_indicator` 校验登录态；storageState **缺失或
   过期** → 输出 `@ENV@ {"env_status": "human_collab", ...}` 并**阻塞等待**；
2. 提交后出现验证码/风控 → `human_wait_*` 同样输出提示并阻塞等待；
3. 脚本输出提示后，**agent 经 hermes agent 的 channel 推送通知**（用
   `scripts/tool/notify.py --project-config <...>` 把含 VNC 地址的提示消息
   推送出去；`hermes send` 复用 gateway 频道凭据，**目标取项目配置
   `publish_defaults.hermes_send_targets`**（hermes v0.20+ 强制 --to；
   空 = 推送到所有已发现 channel），见
   [human-collab.md](human-collab.md)）；
4. agent 必须把 `@ENV@` 消息**原样转达**用户（说明需通过 VNC 完成什么操作），
   hermes 未安装/gateway 未运行推送失败时更要在对话中明确提示；
5. **agent 同时后台启动监控**：`scripts/tool/watch_login.py`（**完成判断由
   agent 编写 `{platform}_watch_check.py` 经 `--check-script` 提供**——平台
   页面特征各异；默认 2h 超时）——用户处理完成后输出 `@ENV@ watch_done`
   并推送"已处理"通知，**唤醒 agent 继续**；超时输出 `watch_timeout`；
6. 用户处理完成后脚本检测到条件满足（`human_collab_done`）自动继续；登录
   成功会自动重新保存 storageState，后续发布再次复用。

**agent 必须**：未收到 `human_collab_done`/`watch_done` 或成功 envelope 前
不得宣布成功、不得盲目重试；等待期间不得做无关操作错过用户反馈。

## 步骤 6 — 成功汇报 / 失败自愈

- 成功：汇报结果。
- 失败：回到「首次发布执行」的沉淀环节（workflow-first-publish.md 步骤 6），
  按 [self-healing.md](self-healing.md) 处理：按需 probe 页面 → 修复脚本/
  物料结构 → 重试。
