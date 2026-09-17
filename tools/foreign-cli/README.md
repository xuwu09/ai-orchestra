# Foreign CLI — 国外顾问组通道工具

把五个国外网页 AI（ChatGPT / Grok / Copilot / Perplexity / Gemini）变成脚本可调用的顾问通道。五站共用**同一个独立浏览器 profile**（与日常浏览器隔离）+ 同一条本地代理出网，在技能里构成「国外顾问组」（双轨规则见 `references/capabilities.example.md`）。

> **合规声明**：本工具只通过浏览器调试协议（CDP）驱动你自己已登录的网页会话；不破解、不绕过任何站点的风控。请遵守各站点服务条款与当地法律法规，外网成员调度仅限合法合规内容（技能内置硬红线）。

## 架构要点

- **独立 profile + 幂等启动 bat**：专门的浏览器 profile 挂 `--remote-debugging-port=9227` + `--proxy-server=<本地代理>` 启动，五站各开一个标签页常驻（或以「全提问」分屏 iframe 形态常开）。
- **登录态边界**：cookie 绑定 profile 加密存储，在该窗口里**人工登录一次即持久有效**；与主浏览器 profile 之间无法迁移，新站点必须在该窗口登录。
- **iframe 双形态**：站点可以是独立标签页，也可以是分屏 iframe（OOPIF）——CDP 对 iframe target 的 trusted 输入（click / insertText / dispatchKeyEvent）与页面**完全等价**，两种形态同等支持。
- **host 级 target 匹配**：按 `urlparse(url).netloc` 匹配站点 hint（copilot 用宽匹配兼容 `copilot.microsoft.com` / `copilot.com` 双域名），防止第三方 iframe（URL 查询参数里恰好含站点名，如 stripe 的 `url=...grok.com...`）被误匹配。

## 命令

```bash
python foreign_cli.py status                       # 代理/CDP 状态 + 各站 target 列表
python foreign_cli.py ensure                       # CDP 不在线则跑启动 bat 并等待（尽力而为）
python foreign_cli.py new chatgpt                  # 导航到站点首页开新会话
python foreign_cli.py send gemini "你的问题"        # 三重门管线发送
python foreign_cli.py send perplexity @task.txt    # @文件 = 发送整个文件内容
python foreign_cli.py extract chatgpt --tail 2000  # 读页面文本尾部（收回复）
```

典型闭环：`send` → 轮询 `extract` 直到出现回复。五站共用一套命令，`site` 取值：`chatgpt / grok / copilot / perplexity / gemini`。

## 三重门发送管线（send 的核心）

从 ChatParty 工具链的三门管线移植到普通网页，解决「弹层抢焦点」「点了没聚焦」「字没进去就回车」三类失败：

1. **扫描门**：选中视口内最大的可见编辑器并打临时标记，在编辑器矩形内做 **15 点多点扫描**（elementFromPoint），命中标记元素才算通过；不通过则自动关 `[role=dialog]` 弹层（找 close 按钮 / X 按钮）+ trusted Escape 后重扫（最多 4 轮）。
2. **焦点门**：trusted click 后校验 `document.activeElement` 在编辑器内；不在则补点一次再验，仍失败即 ABORT——防止弹层吞掉后续输入。
3. **值门**：`Input.insertText` 后读回编辑器值，trim 非空才算写入成功（失败自动补插一次），然后才发 trusted Enter。

任一门失败都会以 `aborted: <门名>` 结束并输出分段日志，不盲发。全程只走 CDP trusted 输入（`Input.dispatchMouseEvent` / `Input.insertText` / `Input.dispatchKeyEvent`），不用 JS 合成事件——多数现代编辑器（React 受控组件、tiptap/ProseMirror 等）不认 JS 合成输入。

## 启动 bat 要点

幂等启动 bat（先探测 CDP 端口再决定是否拉起）核心参数：

```bat
start "" "<浏览器 exe>" ^
  --remote-debugging-port=9227 ^
  --proxy-server=http://127.0.0.1:<本地代理端口> ^
  --user-data-dir=<独立 profile 目录> ^
  <五个站点 URL 空格分隔>
```

> 注意：浏览器主窗口最小化/关闭可能连带回收 CDP；分屏形态下 iframe target 随分屏开合变化。发送报 `no page target` 时，先在该窗口确认目标站点可见。

## 依赖

Python 3.10+，唯一第三方依赖：

```bash
pip install websocket-client
```

（`websocket-client` 连 CDP 时需 `suppress_origin=True` 绕过 403，脚本已处理。）

## E2E 状态（2026-09-18 五站实测）

| 站点 | 发送 | 回复 | 备注 |
|---|---|---|---|
| chatgpt | ✅ | ✅ | codex-dialog 类弹层抢焦点由扫描门自动清障 |
| grok | ✅ | ⚠️ | 输入管线通；回复流可能被代理 WebSocket 阻断（间歇性，页内 Try again/刷新可恢复） |
| copilot | ✅ | ✅ | 双域名宽匹配 |
| perplexity | ✅ | ✅ | |
| gemini | ✅ | ✅ | |
