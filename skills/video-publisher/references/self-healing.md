# 自愈机制（Self-Healing）

> **何时加载：** 发布脚本执行失败（退出非零，envelope 中
> `data.self_heal` 为 `review_script_and_page`），或页面结构与配置不符。

## 触发条件

发布失败 → 回到首次发布流程的**「首次发布执行」沉淀环节**
（workflow-first-publish.md 步骤 6，边发布边补充/修复脚本与物料结构），
执行下述诊断循环。**禁止**不做诊断就盲目重试或硬改脚本绕过错
（如 `--no-verify` 式绕过）。

## 失败分类与处理

| 失败特征 | 根因 | 处理 |
|---------|------|------|
| 连接 CDP 失败 | 有头浏览器未启动/端口错误 | 按 human-collab.md 启动浏览器，重试 |
| 找不到控件/选择器 | 页面改版或探测不完整 | 重新 probe → 更新选择器/物料结构 |
| 登录后未跳转 | 登录失败或验证码 | VNC 人工处理，重试等待 |
| storageState 失效/过期 | token 过期、平台强制下线 | 属正常流程：ensure_login 自动降级为 VNC 登录并重新保存 storageState，无需修脚本 |
| 上传控件找不到 | 上传入口是按钮非 file input | 改用 human_wait_selector 等人工点击 |
| 表单填了没生效 | 字段定位到隐藏/错误元素 | 重新 probe，改用 label/placeholder 定位 |
| 提交后无反应 | 提交按钮选择器错/风控 | 重新 probe + 人工介入 |
| 封面生成失败 | workflow 未配置/ComfyUI 未运行 | 补配置或手动提供封面（警告不阻断） |

## 诊断循环（自愈流程）

```
1. 记录失败: 收集脚本 stdout（@ENV@ 行）、截图、material 与配置
2. 重新探测: probe_page.py 再次获取页面 DOM（页面可能已改版）
   → 对比新旧 dump，定位失效的选择器/新增步骤
3. 审查修复:
   - 脚本错误 → 修复 {platform}_publish.py（只改定位逻辑，不动业务数据）
   - 结构错误 → 更新 platform_config.yaml 的 material_structure/default_config
   - 页面变化 → 更新 login_indicator / 选择器，必要时新增步骤
4. 校验: verify_platform_config.py / verify_project_config.py
5. 重试: 重新执行发布（幂等设计，无需重建物料）
6. 连续失败 ≥2 次仍无法定位 → 停止并报告，向用户展示失败证据
   （截图 + 日志 + 探测结果），请求人工协助或确认平台页面是否改版
```

## 幂等与重试安全

- 发布脚本按幂等设计：重复执行不会重复上传物料、不会创建新项目目录。
- 已登录 cookie 复用（固定 user-data-dir），重试不会强制重新登录。
- 封面已生成则 `generate_material.py` 默认重建目录 —— 重试发布时不要重新
  生成物料，直接复用 `materials/{date}_{name}/materials.yaml`；若封面失败
  可手动放置 cover 文件后更新 yaml 的 fields.cover。

## 自愈记录

每次自愈的根因与修复写入 `{project}/tmp/heal_log.md`（追加），供后续
发布参考，避免同一平台重复踩坑。
