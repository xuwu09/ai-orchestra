# AI Orchestra（多 AI 交响调度）

一套 **Agent Skill**（智能体技能）：把多个 AI 客户端编成一支「交响乐团」，按角色调度协作完成任务。设计为 [Claude Code / WorkBuddy 类智能体](https://codebuddy.ai) 的 Skill 目录结构，也适用于任何能读本地文件、跑 shell、管任务的 agent 当「组长」。

## 核心思想

**先定角色，再填成员**——名字会换，角色流程不变：

```
┌─────────────── 组长层（可更换）───────────────────┐
│   准入：能修改本地文件 + 能派单收产物 + 能实测验收 │
│   职责：接单 → 拆解 → 派单 → 监控 → 验收 → 交付    │
└──────┬─────────────────────┬──────────────────────┘
       │ 派出方案任务包        │ 派出实现/修复任务包
       ▼                     ▼
┌── 顾问组 ───────────────────┐  ┌── 干活组 ────────────────┐
│ 能对话产出长方案（网页/CLI） │  │ 能修改本地文件落盘        │
│ 写方案 + 多轮互审 + 修复方案 │  │ （CLI/桌面 agent）        │
│ 不下场干活                  │  │ 只制作与修复，不写方案     │
└─────────────────────────────┘  └──────────────────────────┘

┌── 特殊工作组（与干活组同级，特定任务才启用）──────────────────┐
│ 本机组（本机执行/知识库） · 创意组（生图生视频+设计） · 代码组 │
└──────────────────────────────────────────────────────────────┘
```

关键机制：

- **方案与实现分离**：顾问组多轮互审出「可照做的最详细版方案」（干活组拿到方案后不需要再做任何设计决策），干活组只按方案落盘；bug 走「问题清单 → 修复方案 → 修复 → 复验」有界循环（同一问题 3 轮上限）。
- **验收权归组长**：干活产物组长实测（不轻信交付说明），用户是最终验收人。
- **任务包人话化**：派给网页 AI 的结构化任务包必须重写成「人托人办事」的口吻（禁词清单 + 去 AI 腔），防平台 AI 检测。
- **额度分层**：无限额成员干资料搜集等粗活，限额成员只干方案/定稿等核心活；纯文字出品走快车道跳过干活组。
- **五级降级路由**：官方 CLI → CDP 客户端直连 → OpenCLI 网页 → 剪贴板接力 → 用户中转；`alive=false + ensure_available=true` 是「待拉起」不是「不可用」。

## 目录结构

```
SKILL.md                        # 技能主文档：架构、七步流程、任务包模板、成员管理
install.ps1 / install.sh        # 一键安装脚本（见上）
references/
  capabilities.example.md       # 成员档案【完整脱敏示例】：真实在用架构的成员/分工/状态/坑，复制为 capabilities.md 后改本机路径即可
  routes.example.yaml           # 通道路由模板（复制为 routes.yaml 后填本机路径/端口）
  scan_routes.py                # 本机通道扫描脚本（按需配置路径）
  playbooks.md                  # 典型工作流剧本（编码/自媒体/调研/本机任务/建站）
workflows/
  TEMPLATE.md + INDEX.md        # 工作流沉淀模板与索引
tools/chatparty/                # ChatParty 顾问通道工具链（登录看门狗 + 试跑 + cdp_inspect 巡检）
```

## 一行命令安装

**Windows（PowerShell）**：

```powershell
irm https://raw.githubusercontent.com/xuwu09/ai-orchestra/main/install.ps1 | iex
```

**macOS / Linux**：

```bash
curl -fsSL https://raw.githubusercontent.com/xuwu09/ai-orchestra/main/install.sh | bash
```

默认装到 WorkBuddy 技能目录 `~\.workbuddy\skills\ai-orchestra`（可传参改目标，如 Claude Code 的 `~/.claude/skills/`）。装完即获得**完整功能**：角色制架构、七步流程、任务包人话化模板、通道路由、ChatParty 顾问通道工具链（登录看门狗 + 试跑 + 巡检）——`references/capabilities.example.md` 是一份完整在用架构的脱敏版，照抄即可获得同构成员分工。

## 快速开始（手动安装）

1. 把整个目录放进你的 agent 技能目录（如 Claude Code 的 skills 目录、WorkBuddy 的 `~/.workbuddy/skills/`）。
2. `references/capabilities.example.md` → 复制为 `capabilities.md`，按你的成员清单填档案。
3. `references/routes.example.yaml` → 复制为 `routes.yaml`，填本机路径与端口（或改 `scan_routes.py` 自动扫描）。
4. 想用 ChatParty 顾问通道的话，看 `tools/chatparty/README.md`（纯标准库脚本，无第三方依赖）。
5. 开单：对组长说「调度多个 AI 完成 XX」，技能自动接管。

## 安全与隐私

- 本仓库只含方法论 + 模板 + 通用脚本，**不含任何个人成员档案、本机路径、端口快照**——`capabilities.md` / `routes.yaml` / `workflows/20*-*.md` 已在 `.gitignore` 里排除。
- `tools/chatparty/` **不分发任何第三方应用本体或修改版**；补丁教程仅供对你自己合法安装的副本做个人本地使用。
- 外网成员调度内置硬红线：仅限合法合规内容。

## License

MIT
