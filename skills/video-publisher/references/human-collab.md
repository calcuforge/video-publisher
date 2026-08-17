# 人机协作协议（Human-in-the-Loop via VNC + CDP）

> **何时加载：** 任何需要启动有头浏览器、处理登录/验证码/风控、或解释
> `@ENV@ human_collab` 提示的场景。发布脚本编写时也必须遵守本协议。

## 核心机制

自动化发布通过 **CDP（Chrome DevTools Protocol）调试端口** 调用**有头
（headed）Chromium** 浏览器完成。浏览器窗口始终可见，用户可通过 **VNC**
实时观察并手动介入。人机协作组件 = Playwright(CDP) + 有头浏览器 + VNC +
脚本内的阻塞等待机制。

```
用户 ←(VNC 观察/操作)→ 有头浏览器 ←(CDP:9222)← 发布脚本 ←(@ENV@提示)← agent
```

## 启动有头浏览器（发布前准备）

任选一种方式，浏览器必须**有头**且开启调试端口：

```bash
# 方式 1：playwright chromium（若浏览器无界面环境，请配合 VNC/远程桌面使用）
python -m playwright open --browser chromium --save-storage=auth.json &
# 或者直接启动并保持窗口:
chromium --remote-debugging-port=9222 --user-data-dir={workspace}/video_publiser_data/tmp/browser-profile

# 方式 2：系统 Chrome/Edge（Windows 上推荐，可直接看到窗口）
"C:\Program Files\Google\Chrome\Application\chrome.exe" \
  --remote-debugging-port=9222 --user-data-dir=C:\Users\<你>\video_publisher_browser_profile

# 方式 3：无界面服务器（Linux），先起 VNC:
x11vnc -forever -display :0 &   # 之后 DISPLAY=:0 启动 chromium
```

- 建议使用固定的 `--user-data-dir`（浏览器 profile 的 cookie 作为兜底会话），
  但**登录态的持久化以 playwright storageState 为主**（见下节）。
- 检查端口：`curl http://127.0.0.1:9222/json/version` 返回 JSON 即就绪。

## 登录态管理（storageState 优先，VNC 兜底）

**agent 编写/维护 playwright 自动化脚本时，登录态必须用 storageState 保存
与复用**，规则如下（已在 `lib/cdp.ensure_login()` 中实现，发布脚本模板默认
调用）：

```
每次发布：
1. 读取平台 storageState（默认 {platform.data_dir}/storage_state.json，
   可用 platform_config.yaml 的 platform.login.storage_state_path 覆盖）
2. 存在 → 载入登录态打开发布页 → 校验 login_indicator（URL 特征/元素特征）
   ├─ 命中 → 已登录，直接继续发布
   └─ 未命中 → 登录态已过期/失效 → 步骤 3
   不存在 → 首次发布，无登录态 → 步骤 3
3. VNC 人机协作登录：脚本输出 @ENV@ 提示（"storageState 缺失或已过期，
   请通过 VNC 在有头浏览器中完成登录"）并阻塞等待，用户登录完成后
   自动保存新的 storageState，后续发布无需再登录
```

要点：
- **storageState 保存位置在平台级**（`{platform_dir}/storage_state.json`），
  该平台所有项目/所有视频共用一份登录态。
- 判断"已登录"的依据是 `platform_config.yaml` 的 `login_indicator`
  （`url_contains` 登录后 URL 特征 / `selector` 已登录元素特征），首次流程
  中用 probe_page.py 探测后填写，缺失时 `ensure_login()` 会报错提醒补齐。
- 登录态过期是常态（平台强制下线、token 失效），脚本必须能自动降级到
  VNC 登录，**不要假设"上次登录过就永远有效"**。
- 首次流程的 probe_page.py 探测页面时，若浏览器会话已登录（profile cookie），
  探测结果即为登录后的发布页结构；登录态随后由发布脚本保存为 storageState。

## agent 的职责：转达提示，不代替脚本

发布脚本遇到无法自动化的步骤时，会输出一行 `@ENV@` JSON：

```json
@ENV@ {"env_status": "human_collab", "msg": "⚠ 需要用户通过 VNC 配合：页面未登录...",
       "data": {"action": "vnc", "condition": "URL 包含 member.bilibili.com/..."}}
```

**agent 必须**：把这条消息原样转达给用户，说明需要做什么（扫码登录/输入验证码/
点击滑块），并告知脚本正在阻塞等待。脚本每 30 秒输出一次
`human_collab_waiting` 心跳，完成时输出 `human_collab_done`。

**agent 禁止**：
- 替用户处理验证码（自动打码/绕过）——所有验证一律走人工；
- 在未收到 `human_collab_done` 或成功 envelope 前宣布发布成功；
- 阻塞等待期间做无关操作导致错过用户反馈。

## 常见人机协作场景与条件

| 场景 | 等待条件（脚本写法） | 提示给用户的内容 |
|------|---------------------|-----------------|
| 登录 | `human_wait_url(page, desc, 登录后URL特征)` | 请通过 VNC 扫码/输账号登录 |
| 短信验证 | `human_wait_selector(page, desc, 验证成功特征)` | 请查收短信并输入验证码 |
| 滑块/图形验证 | `human_wait_url` 或自定义 condition | 请在浏览器里完成滑块验证 |
| 上传转码慢 | `human_wait_selector(表单可用特征)` | 视频上传中，可观察进度 |
| 风控拦截 | 提交后 `human_wait_url(成功特征)` | 若出现校验请人工处理 |
| manual 审核 | agent 侧暂停 + 截图展示 | 内容确认后告知 agent 继续 |

自定义等待条件示例（脚本内）：

```python
from lib.cdp import human_wait
human_wait(page, "等待视频转码完成",
           lambda p: p.locator("text=转码完成").count() > 0,
           timeout=1800, condition_desc="页面出现'转码完成'")
```

## 超时与失败

- 等待超时（默认 600s，上传可设 1800s+）→ 脚本抛 `RuntimeError` 退出非零，
  触发自愈流程（[self-healing.md](self-healing.md)）。
- 用户无法及时配合时，agent 可以重跑脚本——脚本设计为幂等：
  已登录的 cookie 复用、上传可重试，失败步骤之前的产物不重建。

## 截图辅助

- 发布脚本可在关键节点调用 `screenshot(page, path)`（如 manual 模式提交前），
  agent 用 Read 工具查看截图，向用户展示审核，或用于失败排查。
- 截图写入项目 `tmp/` 目录，禁止写系统临时目录。
