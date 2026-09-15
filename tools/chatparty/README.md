# ChatParty 顾问通道工具链

把 [ChatParty](https://www.chatparty.cn)（多模型聚合桌面应用）里的网页 AI 站点变成脚本可调用的顾问通道。本目录包含三个纯标准库 Python 脚本 + 一份自改教程。

> **⚠️ 合规声明**：本目录**不包含、也不分发** ChatParty 程序本体或其任何修改版。
> 所有补丁都需要你对自己合法安装的副本自行操作，修改仅供个人本地使用，请勿分发修改后的程序包。

## 脚本

### `cp_login_guard.py` — 登录看门狗

- 每 45 秒巡检 ChatParty（CDP 9222）各站点登录态：CDP cookie（含 HttpOnly）+ localStorage 双通道检测
- 已登录时持续备份 cookie + localStorage 到 `guard-backups/`（只在确认登录态时备份，防止坏状态覆盖好备份）
- 掉登录自动恢复：注入 cookie + LS → 只刷新该 webview → 复核（每站每小时最多 3 次，防风控）
- 自定义站配置丢失：强制回写（含 `custom-providers` 被初始化成 `"[]"` 的情况）→ 刷新主窗口（10 分钟冷却）
- 心跳锁单实例（`guard.lock`，2 分钟无心跳自动让位）；日志 `guard.log`

站点检测指标在脚本顶部 `SITES` / `CUSTOM_HOST_MAP` 里按你的站点清单维护。

### `trial_send.py` — 通道试跑

对指定站点做一次「发送 → 收回复」闭环，验证顾问通道可用：

```bash
python trial_send.py kimi "https://www.kimi.com" "通道测试：请只回复两个字——收到"
```

原理：CDP 按 URL 前缀匹配 webview target → 编辑器 `scrollIntoView`（多站应用的 webview 常小窗渲染，元素在视口外）→ 视口内可信点击 / 视口外 JS focus → `Input.insertText` → 原生 `dispatchKeyEvent` Enter → 读 `document.body.innerText` 尾部收回复。

### `cdp_inspect.py` — 巡检三合一

接入新站点前的侦察工具（列 target / 探 DOM / 截图）：

```bash
python cdp_inspect.py list                      # 列出全部 target
python cdp_inspect.py probe kimi.com            # 探该页输入框选择器、cookie/LS 键名
python cdp_inspect.py shot kimi.com out.png     # 截图看 webview 实际渲染
```

用 `probe` 摸清编辑器选择器与登录态存放位置（cookie 名单 or localStorage 键），再据此校准 `cp_login_guard.py` 的 `SITES` / `CUSTOM_HOST_MAP` 检测指标。

## 依赖

**无第三方依赖**——两个脚本都是纯 Python 标准库（WebSocket 手写实现，无 Origin 头以绕过 CDP 403）。Python 3.10+ 即可。

## 自改教程（供个人本地使用）

社区常见的个人化改造点（风险自担，改前备份 `resources/app.asar`）：

1. **删减预置站点 / 修改站点 URL**：解包 `resources/app.asar`，在渲染进程 bundle 里按站点 id 增删，重打包（注意 Electron asar 是 4 字节对齐）。
2. **退出时可靠存盘 + 定时自动保存**：主进程 `before-quit` 里 flush 各 webview 会话 + `setInterval` 定期存盘（原版常见 bug：quit 时异步存盘来不及落盘）。
3. **userData 迁移**：若程序以低完整性级别运行（Windows Low IL, S-1-16-4096），对 `%APPDATA%` 全拒写（EPERM）——要么把数据目录迁到打了 `icacls /setintegritylevel (OI)(CI)L` 低完整性标签的目录，要么以普通完整性运行。
4. **挂 CDP**：启动参数加 `--remote-debugging-port=9222`，看门狗与试跑脚本才有入口。
5. **登录保活**：`cp_login_guard.py` 常驻 + 开机自启（VBS 静默拉起）。

> 注意：修改第三方应用可能违反其服务条款；验证码/风控组件改动易触发崩溃（软件渲染下尤其明显），改动后务必逐站回归。
