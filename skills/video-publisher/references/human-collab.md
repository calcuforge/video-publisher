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

## 环境与端口约定（对齐 hermes-hitl-environment）

**标准人机协作环境是 [hermes-hitl-environment](https://github.com/calcuforge/hermes-hitl-environment)**：
一个虚拟 Linux 桌面（Xvfb + Openbox + 共享 Chromium + VNC + noVNC），
人类与 agent 操作**同一个浏览器窗口**——agent 经 CDP(9222) 驱动，
人类经 VNC(5900) 或任意浏览器的 noVNC(6080/vnc.html) 观察与接管。

端口与环境变量约定（变量名与 hermes 的 `.env.example` 一致；**hermes 的
`.env` 只是 docker compose 部署时的配置源，容器内部没有 .env 文件**——
本 skill 脚本一律通过进程环境变量 `os.environ` 读取，本地运行需自行 export
相应变量。解析优先级：命令行参数 > 环境变量 > 平台配置 > 默认值）：

| 变量 | 默认 | 用途 |
|------|------|------|
| `PLAYWRIGHT_CDP_URL` | `http://127.0.0.1:9222` | Playwright 通过 CDP 驱动共享 Chromium |
| `CHROME_REMOTE_DEBUGGING_PORT` | `9222` | Chromium 调试端口 |
| `VNC_PORT` | `5900` | VNC 桌面端口 |
| `NOVNC_PORT` | `6080` | noVNC（浏览器访问 `http://<host>:6080/vnc.html`） |
| `VNC_VIEWER_URL` | — | VNC 接入地址（如 `vnc://host:port` 或 `http://host:port/vnc.html`）；设置后提示/推送消息中的 VNC 地址取此值，未设置回退 `{host}:{VNC_PORT}` |
| `CHROME_BIN` / `CHROME_PROFILE_DIR` / `CHROME_DOWNLOADS_DIR` | — | 浏览器可执行文件 / profile / 下载目录 |
| `SCREEN_WIDTH` / `SCREEN_HEIGHT` | `1920` / `1080` | Chromium 窗口尺寸 |
| `CHROME_EXTRA_FLAGS` | — | 附加启动参数 |

### 启动有头浏览器（发布前准备）

推荐方式：用本 skill 的 `launch_browser.py` 启动共享 Chromium（对齐 hermes
launch-chromium.sh：单一持久 profile、CDP 调试端口、下载目录、崩溃锁清理）：

```bash
# SKILL_DIR = 包含 SKILL.md 的目录（agent 已加载该文件，取其绝对路径）
SKILL_DIR="${SKILL_DIR:-${CLAUDE_SKILL_DIR}}"
python "${SKILL_DIR}/scripts/tool/launch_browser.py" \
    [--cdp-port 9222] [--profile-dir <持久profile>] [--downloads-dir <下载目录>]
# 输出 JSON envelope，含 CDP URL 与 VNC/noVNC 接入方式；浏览器前台长驻（后台运行）
```

或直接使用 hermes-hitl-environment（docker compose 一键起环境）：
`cd hermes-hitl-environment && cp .env.example .env && docker compose up -d --build`，
随后 `PLAYWRIGHT_CDP_URL=http://127.0.0.1:9222` 直接可用。

**多账号 = 共用浏览器实例（默认）**：所有账号连同一个 CDP 端点（平台实例，
默认 9222）——框架为每个账号创建**隔离 context**（载入该账号独立
storageState，cookie 互不串），无需为每账号启动浏览器。

- 只需启动一个共享实例（launch_browser.py 或 hermes 环境），发布/监控用
  `--account` 自动载入账号隔离 context（见 SKILL.md 账号解析链）；
- **VNC 人机协作注意**：每个账号的页面在**独立浏览器窗口**中打开，用户
  必须在"脚本打开的那个窗口"完成登录/验证（不要操作默认窗口），登录态
  才会保存到该账号；
- 首次登录（无 storageState）同样使用隔离 context，多个新账号不会串号；
- **可选完全隔离**：给 account_config.yaml 配独立 `cdp.port` +
  `profile_dir`，用 launch_browser.py 按该端口/profile 启动独立实例
  （独立指纹，降低风控关联；代价是每账号一个浏览器窗口与进程）；
- 无论共用或独立，同平台多账号发布建议**串行错峰**（防风控关联）。

Windows 本地调试也可手动启动（推荐固定 `--user-data-dir`，profile cookie 作
为兜底会话；**登录态持久化以 playwright storageState 为主**，见下节）：

```bash
# 系统 Chrome/Edge（Windows 上推荐，可直接看到窗口）
"C:\Program Files\Google\Chrome\Application\chrome.exe" \
  --remote-debugging-port=9222 --user-data-dir=C:\Users\<你>\video_publisher_browser_profile
```

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

## agent 的职责：转达提示 + channel 推送（不代替脚本）

**推送流程（四步）**：

```
脚本检测到需要登录/验证码 → 脚本输出 @ENV@ human_collab 提示（含 VNC 地址）
→ agent 推送 channel 消息（含 VNC 地址）→ agent 启动 watch_login.py 后台
监控页面（2h 超时）→ 检测到用户已处理 → 推送"已处理"通知并唤醒 agent 继续
```

**1. 脚本输出提示**。发布脚本遇到无法自动化的步骤（登录态过期、验证码、
风控等）时，输出一行 `@ENV@` JSON（消息自带 VNC/noVNC 接入地址）：

```json
@ENV@ {"env_status": "human_collab", "msg": "⚠ 需要用户通过 VNC 配合：页面未登录...。接入方式：浏览器 CDP: http://127.0.0.1:9222 | VNC: 127.0.0.1:5900 | noVNC: http://127.0.0.1:6080/vnc.html",
       "data": {"action": "vnc", "condition": "URL 包含 member.bilibili.com/..."}}
```

**2. agent 推送 channel 消息**。agent 看到 `@ENV@ human_collab` 提示后，
通过 **hermes agent 的 channel** 推送通知（消息**必须包含 VNC 接入地址**；
@ENV@ 提示自带，agent 手写消息时 CLI 会自动附加）：

```bash
python "${SKILL_DIR}/scripts/tool/notify.py" --message "⚠ 需要用户通过 VNC 配合：请完成登录，脚本正在等待。接入方式：VNC: 127.0.0.1:5900 | noVNC: http://127.0.0.1:6080/vnc.html"
python "${SKILL_DIR}/scripts/tool/notify.py" --message "..." --to telegram
```

- 机制：执行 `hermes send --to <目标> --subject video-publisher <消息>`
  CLI，复用 hermes gateway 已配置的频道凭据（Telegram / Discord / Slack /
  飞书 / 钉钉 / 企业微信 / 微信 等）推送到用户的消息 channel；
- 前置：hermes-agent 已安装、`hermes gateway start` 运行中（凭据在
  `hermes gateway setup` 时配置，本 skill 不重复配置）；
- 目标频道（**hermes v0.20+ 强制显式 `--to <平台[:频道[:thread]]>`**，
  "省略 --to 由 hermes 发往 home channel"是错误认知，hermes 并不支持）：
  在 `project_config.yaml` 的 `publish_defaults.hermes_send_targets` 配置
  **列表**（如 `[weixin, telegram:12345, feishu]`，支持多个目标）；
  **为空（默认）= 推送到所有已发现的 channel**（notify 通过
  `hermes send --list --json` 枚举，每个平台发 home channel 并附上已发现
  的频道）；CLI 可用 `--to` 单次覆盖；
- 推送失败（未设置目标 / hermes 未安装 / gateway 未运行 / 平台限流等）仅
  警告，**不影响发布流程**，agent 仍须在对话中提示用户。限流
  （rate limited，如微信 cooldown 30s）时 notify 会提示退避并自动重试一次。

**3. agent 启动监控脚本（唤醒机制）**。推送提醒后，agent **同时**用后台
方式启动 `watch_login.py` 监控页面，检测用户是否已处理，完成后自动唤醒
agent 继续后面的流程。

**完成判断逻辑由 agent 实现**：不同平台页面特征不同，watch_login.py 不内置
固定规则——agent 依据该平台实际页面编写 `{platform}_watch_check.py`
（模板 `scripts/publish_scripts/template_watch_check.py`，实现
`check(page) -> str | bool`，可判断 URL/元素/iframe 内容等任意只读特征），
放平台级 `{platform}/publish_scripts/` 复用，监控时用 `--check-script` 传入：

```bash
python "${SKILL_DIR}/scripts/tool/watch_login.py" \
    --platform-config <...>/platform_config.yaml \
    --project-config <...>/project_config.yaml \
    --check-script <...>/publish_scripts/{platform}_watch_check.py \
    [--timeout 7200]   # 最大等待 2 小时（默认）
```

- 判断函数每 3s 调用一次，返回真值/命中描述 = 用户已处理；异常被捕获
  输出 `watch_check_error` 并继续等待；
- 未提供 `--check-script` 时回退内置简单条件（`--wait-url-contains` /
  `--wait-selector` / platform_config 的 `login_indicator`）作兜底；
- 检测到用户已处理 → 输出 `@ENV@ watch_done` 并经 hermes channel 推送
  "用户已处理，发布流程继续"通知 → 退出码 0，**唤醒 agent 继续**；
- 超时（默认 2h）→ `@ENV@ watch_timeout` → 退出码 1，agent 需重新提醒
  用户或人工介入；
- 只读监控（轮询页面状态），与发布脚本共用同一有头浏览器互不干扰；
- agent 被唤醒后：若发布脚本仍在阻塞等待（`human_collab_done` 出现）则
  由脚本自行继续；若发布脚本已退出，则重新执行发布步骤继续流程。

**4. 用户处理**。用户按推送消息中的 VNC 地址接入有头浏览器完成操作
（扫码登录/输入验证码/点击滑块）；发布脚本每 30 秒输出一次
`human_collab_waiting` 心跳，完成时输出 `human_collab_done`；watch 脚本
同时检测到条件满足后唤醒 agent。

**agent 禁止**：
- 替用户处理验证码（自动打码/绕过）——所有验证一律走人工；
- 在未收到 `human_collab_done` / `watch_done` 或成功 envelope 前宣布发布成功；
- 等待期间做无关操作导致错过用户反馈。

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
