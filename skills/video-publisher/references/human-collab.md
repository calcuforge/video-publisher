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

## agent 的职责：转达提示，不代替脚本

发布脚本遇到无法自动化的步骤时，会输出一行 `@ENV@` JSON：

```json
@ENV@ {"env_status": "human_collab", "msg": "⚠ 需要用户通过 VNC 配合：页面未登录...",
       "data": {"action": "vnc", "condition": "URL 包含 member.bilibili.com/..."}}
```

**agent 必须**：把这条消息原样转达给用户，说明需要做什么（扫码登录/输入验证码/
点击滑块），并告知脚本正在阻塞等待。脚本每 30 秒输出一次
`human_collab_waiting` 心跳，完成时输出 `human_collab_done`。

**agent channel 推送通知**：脚本输出人机协作提示时会**自动**通过配置的
agent channel 推送通知（登录态/验证码等场景均经 `human_hint()` 触发）。
若 channel 未配置或推送失败，agent 仍须在对话中提示用户；agent 也可用
CLI 手动补推：

```bash
python "${SKILL_DIR}/scripts/tool/notify.py" --message "需要用户通过 VNC 完成登录"
```

channel 配置（可选，不配置则不推送）：
- 配置文件 `{workspace}/video_publiser_data/agent_channel.yaml`（示例见
  templates/example_configs/agent_channel.yaml），支持 `command`（命令模板，
  如 `claude notify`）与 `webhook`（HTTP POST JSON）两种类型；
- 或环境变量 `AGENT_CHANNEL`（http(s) 开头 = webhook URL，否则 = 命令模板）；
- 推送失败仅警告，不影响发布流程。

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
