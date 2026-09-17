# ChatParty 顾问通道工具链

把 [ChatParty](https://www.chatparty.cn)（多模型聚合桌面应用）里的网页 AI 站点变成脚本可调用的顾问通道。本目录包含纯标准库 Python 脚本 + 一份自改教程。

> **⚠️ 合规声明**：本目录**不包含、也不分发** ChatParty 程序本体或其任何修改版。
> 所有补丁都需要你对自己合法安装的副本自行操作，修改仅供个人本地使用，请勿分发修改后的程序包。

## 前置：启动器（CDP 开关）

官方 exe **不内置 CDP**——必须用 `--remote-debugging-port=9222` 启动，本目录所有脚本才有遥控入口。`start_chatparty.bat` 是幂等启动模板（先改开头的 exe 路径）：

- ChatParty 没跑 → 带 CDP 拉起；在跑且 CDP 在听 → 直接退出（幂等）
- 在跑但无 CDP（直接双击过 exe）→ 提示关闭后用启动器重开（`netstat` 探测）

建议把启动器放桌面并配置开机自启（任务计划/VBS 静默拉起），常驻后台。

## 脚本

### `orchestra_bridge.py` — 组长遥控桥（ai-orchestra 专用入口）

四件套（纯标准库，无第三方依赖）：

```bash
python orchestra_bridge.py status            # 各站 target/标题/登录线索（组长选站用）
python orchestra_bridge.py ensure            # 幂等拉起 ChatParty（CDP 9222 在线即返回）
python orchestra_bridge.py send metaso "通道测试：请只回复两个字——收到"
python orchestra_bridge.py read metaso 60    # 读回复（seconds>0 时轮询等文本稳定）
```

- 12 站按 URL 片段匹配（SITES 表按你的站点清单维护），worker/静态资源 target 自动过滤
- 发送 = 可见 textarea 用 native setter + input 事件 / contenteditable 用 execCommand，先按钮后 Enter（React 受控组件不认直赋值）；回复读 `body.innerText` 尾部，由组长（LLM）自行解析
- 程序路径走环境变量 `ORCHESTRA_CHATPARTY_EXE`（ensure 用）；日志 `orchestra_bridge.log`
- 典型闭环：`send` → `read <key> 60`（轮询文本稳定）→ 组长解析出回复

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

`orchestra_bridge.py` / `cp_login_guard.py` / `trial_send.py` / `cdp_inspect.py` 全部**纯 Python 标准库**（WebSocket 手写实现，无 Origin 头以绕过 CDP 403）。Python 3.10+ 即可。
`patch_main_customsend46.py` / `patch_main_customsend47.py` / `patch_main_customsend48.py` 需要 node（语法校验）；`replace_v4.py` 纯标准库。

## 自改教程（供个人本地使用）

社区常见的个人化改造点（风险自担，改前备份 `resources/app.asar`）：

1. **删减预置站点 / 修改站点 URL**：解包 `resources/app.asar`，在渲染进程 bundle 里按站点 id 增删，重打包（注意 Electron asar 是 4 字节对齐）。
2. **退出时可靠存盘 + 定时自动保存**：主进程 `before-quit` 里 flush 各 webview 会话 + `setInterval` 定期存盘（原版常见 bug：quit 时异步存盘来不及落盘）。
3. **userData 迁移**：若程序以低完整性级别运行（Windows Low IL, S-1-16-4096），对 `%APPDATA%` 全拒写（EPERM）——要么把数据目录迁到打了 `icacls /setintegritylevel (OI)(CI)L` 低完整性标签的目录，要么以普通完整性运行。
4. **挂 CDP**：用 `start_chatparty.bat` 启动器（或启动参数加 `--remote-debugging-port=9222`），看门狗与桥脚本才有入口。
5. **登录保活**：`cp_login_guard.py` 常驻 + 开机自启（VBS 静默拉起）。
6. **主进程 trusted 三重门发送补丁**（`patch_main_customsend46.py`（v4.6）/ `patch_main_customsend47.py`（v4.7）/ `patch_main_customsend48.py`（v4.8）+ `replace_v4.py`，实测版本）：
   - 病根：群发/讨论发送走 IPC → 主进程 → 部分站点（MUI 富文本包装、Draft.js 等框架 state 与 DOM 脱节型）JS 注入发不出去。解法 = 主进程 `webContents.debugger` 走 **CDP trusted 输入**（`Input.dispatchMouseEvent` / `Input.insertText` / `Input.dispatchKeyEvent`），hidden webview 下同样有效。
   - **三重门**（详见 patch 脚本 docstring）：probe 门（elementFromPoint 验证落点，布局未稳坐标会偏）→ focus 门（activeElement 在输入框内）→ value 门（insertText 后 trim 非空）→ 才 Enter。全链日志到 `cp_trusted.log`，`after-url` 验证跳转。
   - **asar 重打包三坑**：①保留原文件条目的 `integrity`（丢了 Electron 启动即崩），被替换文件重算 SHA256（整包 + 4MB 分块）；②树形 walk 递归重排所有文件 offset；③header size-offset 反写（4 字节对齐）。
   - 用法：设 `ORCHESTRA_CHATPARTY_ASAR` → `python patch_main_customsend48.py`（产出 `.v48new`，不覆盖原文件；47/48 防重入锚点分别是 `__cpBcRescue` / `__cpIsDoubao`，基线锚点递查前置版本）→ `python replace_v4.py`（等 ChatParty 退出 → 自动备份 → 替换 → 读回校验）。**锚点按你副本实际 main.js 调整**，锚点不匹配会安全退出不写盘。
   - 版本演进（我们本地实测链）：v4.4 定位布局偏移 → v4.5 三重门 → v4.6 纳米 Slate 直填（fiber 找 editor 实例 + React props 直调）+ Kimi value 门 trim → **v4.7 RESCUE 群发漏站补扫** → **v4.8 豆包改版适配**。十二站群发入卡 E2E 全通。
   - **v4.7 RESCUE 补扫**（锚点 B1 = 单站 IPC handler）：群发循环在**渲染进程**（50ms 内连发），漏站 = 渲染进程没发 IPC，主进程侧无从拦截——补扫挂在 `ipcMain.handle("send-message-to-webview")` wrapper：每条 IPC 记账（60s 滑窗）→ 窗内 ≥3 条且各站消息**完全一致**（群发语义；单发/2 站对比不触发）→ 3.5s 静默（群发 50ms 打完，无中途误补风险）→ 主窗口 DOM 枚举 `webview[id]` → 对缺失站直调原 handler 补发（自动复用 custom script + trusted 全套）；防重 = 同消息 90s 时间桶。实测：两次群发分别救回 kimi 单站、kimi+知乎直达双站。
   - **v4.8 豆包改版适配**（五锚点 D1~D5）：豆包前端改版后 guidance textarea 形态消失（编辑器变 tiptap ProseMirror contenteditable、发送按钮 class 更换），custom script 填字成功但按旧 class 找按钮 10 次重试全空静默放弃。解法 = 把 `__cpIsDoubao` 并入 metaso/kimi 的 attach + 三重门 trusted 分支（contenteditable 版 probe/focus/value 表达式自动适用），custom 填字在前、trusted Enter 兜底，两条路径并行无冲突。实测发送后跳会话页。已知无害竞态：custom 残留填字与 trusted 填字出现「1+11+1」拼接（不影响发送）；想消除 = 清掉 doubao 键 custom script 后 reload 主窗口 store。
7. **提取/状态脚本注入（进阶）**：往 `chatallai_custom_scripts` localStorage 注入各站 `getLLMLastMessage`/状态检测脚本（文本稳定检测），让「收集回答」覆盖自定义站。注意主窗口 reload 会重载全部 webview 丢会话，注入后需 reload 主窗口 store 才生效。

> 注意：修改第三方应用可能违反其服务条款；验证码/风控组件改动易触发崩溃（软件渲染下尤其明显），改动后务必逐站回归。
