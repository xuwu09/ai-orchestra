# AI Orchestra 详细教程（从零到第一次派单）

> 目标读者：**没玩过多 AI 协作的新手**。跟着做完约 15 分钟，你会得到一个「组长 + 顾问团 + 干活组」的多 AI 协作系统。
>
> 核心思想一句话：**先定角色，再填成员**——让每个 AI 干它最擅长的活，从源头减少 token 浪费。

---

## 0. 这套系统长什么样（2 分钟）

```
┌─────────────── 组长层（你的 agent，如 WorkBuddy / Claude Code）───────────────┐
│   接单 → 拆解 → 派单 → 监控 → 实测验收 → 交付                                  │
└──────┬──────────────────────────────┬────────────────────────────────┘
       │ 派方案任务包                   │ 派实现/修复任务包
       ▼                              ▼
┌── 顾问组（对话出方案）─────────┐  ┌── 干活组（能改本地文件）──────┐
│ ChatParty 12 站（豆包/Kimi/…）│  │ CLI agent（DS/Codex/…）      │
│ 国外 5 站（GPT/Grok/…）       │  │ 只制作与修复，不写方案        │
└──────────────────────────────┘  └──────────────────────────────┘
```

- **方案与实现分离**：顾问组多轮互审出「可照做的最详细版方案」，干活组照做即可，不用再做设计决策。
- **五级降级路由**：官方 CLI → CDP 客户端 → OpenCLI 网页 → 剪贴板 → 用户中转。某成员离线 ≠ 不可用（可拉起）。
- **额度分层**：免费/无限额站点干资料搜集等粗活，付费/限额成员只干方案定稿等核心活。

---

## 1. 一键安装（30 秒）

**Windows（PowerShell）**：

```powershell
irm https://raw.githubusercontent.com/xuwu09/ai-orchestra/main/install.ps1 | iex
```

**macOS / Linux**：

```bash
curl -fsSL https://raw.githubusercontent.com/xuwu09/ai-orchestra/main/install.sh | bash
```

装完自动完成：

1. 技能整体装到 `~\.workbuddy\skills\ai-orchestra`（Claude Code 用户可加参数 `-Target "$env:USERPROFILE\.claude\skills\ai-orchestra"`）
2. **自动生成** `capabilities.md` 和 `routes.yaml`（从 example 模板复制，旧文件自动备份）
3. 提示下一步动作

> 已有旧安装？重跑一次安装脚本即可更新——旧目录自动备份成 `ai-orchestra.bak-时间戳`。

---

## 2. 首次配置（5 分钟，三条路线任选）

### 路线 A：最小可用（只有组长，无外部成员）

什么都不用配。组长自带干活能力，`capabilities.md`/`routes.yaml` 保持模板态也能跑纯文字任务。**适合先体验流程。**

### 路线 B：接入 ChatParty 顾问团（推荐，国内 12 站）

前提：已安装 [ChatParty](https://www.chatparty.cn)（多模型聚合桌面应用）。

1. **改启动器**：打开 `tools\chatparty\start_chatparty.bat`，把里面的 exe 路径改成你的 ChatParty 安装路径（这是「一键使用」的开关——官方 exe 不内置 CDP，必须用它启动）。
2. **拉起**：双击这个 bat。已登录的站点会以卡片形式常开。
3. **验证通道**：
   ```bash
   cd tools\chatparty
   python orchestra_bridge.py status          # 应列出各开着的站点
   python orchestra_bridge.py send metaso "通道测试：请只回复两个字——收到"
   python orchestra_bridge.py read metaso 60  # 等到「收到」即闭环
   ```
4. **（可选但强烈建议）登录看门狗**：`python cp_login_guard.py` 常驻，掉登录自动恢复 + 配置丢失自动回写。
5. 把 12 站的强项/限额情况填进 `capabilities.md` 的成员表（照抄 example 的格式即可）。

### 路线 C：接入国外顾问组（GPT / Grok / Copilot / Perplexity / Gemini）

前提：本机有可用的国际网络代理。

1. 复制 `tools\foreign-cli` 的思路：用一个**独立浏览器 profile** 挂 `--remote-debugging-port=9227 --proxy-server=http://127.0.0.1:<代理端口>` 启动，五站各开一个标签页（或「全提问」分屏）。
2. 在该窗口里**人工登录一次**五个站点（登录态绑定 profile，持久有效；主浏览器登录态无法迁移过来）。
3. 设环境变量后验证：
   ```bash
   set ORCHESTRA_FOREIGN_PROXY_PORT=<你的代理端口>
   set ORCHESTRA_FOREIGN_LAUNCHER=<你的启动 bat 路径>
   python foreign_cli.py status
   python foreign_cli.py send gemini "通道测试：请只回复两个字——收到"
   python foreign_cli.py extract gemini --tail 500
   ```
4. `capabilities.md` 国外顾问组节照 example 填；**硬红线**：外网成员仅限合法合规内容。

### 最后一步：扫描生成路由表

编辑 `references\scan_routes.py` 顶部 CONFIG 区（每项都有注释，按你本机路径/端口填；也可用 `ORCHESTRA_*` 环境变量），然后：

```bash
python scan_routes.py        # 生成 references/routes.yaml
python scan_routes.py --print  # 只看不写
```

---

## 3. 第一次派单（实战）

对组长（已安装本技能的 agent）说人话即可：

- **纯文字出品（快车道，跳过干活组）**：
  > 「调度多个 AI：让顾问组讨论『给上班族的三条减脂饮食原则』，互审后给我最终版」
- **编码任务（顾问出方案 → 干活落盘）**：
  > 「调度多个 AI 给我的小工具加一个导出 CSV 功能：先出方案再实现，最后实测验收」
- **资料搜集（额度分层）**：
  > 「用无限额站点搜集 XX 产品的公开评测要点，汇总成一页」

组长会自动：选站 → 生成「人话化」任务包（防平台 AI 检测）→ 派发 → 收回答 → 互审 → 验收。你只管看结果。

---

## 4. 工具链速查

### ChatParty 通道（tools/chatparty/）

| 工具 | 一句话 | 常用命令 |
|---|---|---|
| `start_chatparty.bat` | 幂等启动（带 CDP 9222） | 双击 / 开机自启 |
| `orchestra_bridge.py` | 组长遥控桥 status/send/read/ensure | `python orchestra_bridge.py status` |
| `cp_login_guard.py` | 登录看门狗（常驻） | `python cp_login_guard.py` |
| `trial_send.py` | 单站收发闭环试跑 | `python trial_send.py kimi "https://www.kimi.com" "hi"` |
| `cdp_inspect.py` | 巡检三合一 list/probe/shot | `python cdp_inspect.py probe metaso.cn` |

全部纯标准库，无第三方依赖。

### 国外顾问组通道（tools/foreign-cli/）

`status / new / send / extract / ensure` 五件套，三重门发送管线（扫描门 → 焦点门 → 值门 → trusted Enter），页面与分屏 iframe 双形态。唯一第三方依赖 `pip install websocket-client`。详见该目录 README（含五站实测状态表）。

---

## 5. ChatParty 自改进阶（可选）

`tools\chatparty\README.md` 自改教程覆盖：删站重构建、可靠存盘、userData 迁移、主进程 trusted 三重门补丁（v4.6 示例工具 + asar 重打包三坑）、提取脚本注入。核心原则：

- **改前必备份** `resources/app.asar`
- 补丁脚本**锚点不匹配就安全退出**，绝不写盘
- 改完逐站回归

---

## 6. 排障 FAQ

**Q：路由表里 `alive=false` 是坏了吗？**
不是。`alive=false + ensure_available=true` = 「待拉起」（先跑 ensure/启动器再判）；「真不可用」= `installed=false` 或没有 ensure 手段。

**Q：发送失败了怎么定位？**
分三段看：①输入门（DOM 层：弹层抢焦点/编辑器没聚焦——三重门管线会自动清障重试）→ ②会话建立（WS/HTTP：代理问题，如 Grok 的 WS 阻断是间歇性的，页内 Try again 可恢复）→ ③服务端响应。日志先看 `cp_trusted.log` / `orchestra_bridge.log`。

**Q：站点突然全发不出去？**
大概率站点前端改版（DOM/框架变了）。用 `cdp_inspect.py probe` 重新侦察选择器，更新 SITES 表即可。前端异常站点隔天常自愈，值得复检。

**Q：`send` 报 no cdp target？**
卡片没开或站点 URL 片段没匹配上。先 `orchestra_bridge.py status` 看 `open_sites` 实际开着什么；自定义站直接传 URL 片段也行。

**Q：ChatParty 在跑但脚本全连不上？**
官方 exe 直接双击启动是没有 CDP 的。关闭后用 `start_chatparty.bat` 重开。

**Q：我的真实 routes.yaml / capabilities.md 会被提交到公开仓库吗？**
不会，`.gitignore` 已排除个人档案与路由快照；本仓库只含方法论 + 模板 + 通用脚本。

---

## 7. 更新与回滚

- **更新**：重跑安装脚本（自动备份旧目录）；或进 git clone 目录 `git pull`。
- **回滚**：删掉 `~\.workbuddy\skills\ai-orchestra`，把 `.bak-时间戳` 目录改名回来。
- **ChatParty 补丁回滚**：`copy /y "<asar>.pre-patch-backup" "<asar>"`（replace_v4.py 校验失败时也会打印这条）。

---

## 8. 下一步阅读

- `SKILL.md` — 组长的方法论全典（七步流程 / 任务包模板 / 成员管理 / 双轨规则）
- `references/capabilities.example.md` — 一份真实在用架构的完整脱敏成员档案，照抄即可获得同构分工
- `references/playbooks.md` — 编码 / 自媒体 / 调研 / 本机任务 / 建站的现成工作流剧本
- `CHANGELOG.md` — 版本历史
