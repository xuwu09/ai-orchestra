# 更新日志

本仓库遵循语义化版本（MAJOR.MINOR.PATCH）。所有显著变更记录在此。

## v1.2.0（2026-09-18）

### Added

- **`tools/chatparty/orchestra_bridge.py`** — 组长遥控桥（本次核心）：ChatParty 12 站的 `status / send / read / ensure` 四件套，纯标准库；URL 片段匹配 + worker target 过滤；发送走 native setter / execCommand + 先按钮后 Enter；`read` 支持轮询等待文本稳定。实测「发送→收到」闭环通过。
- **`tools/chatparty/start_chatparty.bat`** — 幂等启动器模板：带 `--remote-debugging-port=9222` 拉起；「在跑但无 CDP」netstat 检测（官方 exe 不内置 CDP，这是遥控通道的总开关）。
- **`tools/chatparty/patch_main_customsend46.py` + `replace_v4.py`** — 主进程 trusted 三重门发送补丁工具（实测版本，自改教程配套）：probe 门（elementFromPoint 落点验证）→ focus 门 → value 门（trim 非空）→ Enter；asar 重打包完整实现（integrity 保留 + 重算、offset 重排、size-offset 反写）；replace 工具等进程退出 → 自动备份 → 替换 → 读回校验。锚点不匹配安全退出不写盘。**不分发任何程序本体或修改版**，仅供个人本地自改。
- **`TUTORIAL.md`** — 详细教程：从零到第一次派单 15 分钟（三条配置路线：最小可用 / ChatParty 顾问团 / 国外顾问组；工具链速查；自改进阶；排障 FAQ）。
- **安装脚本一键使用增强**：装完自动从脱敏示例生成 `capabilities.md` / `routes.yaml`（已存在则保留），next steps 指向 TUTORIAL.md。

### Changed

- `README.md`：目录结构补 TUTORIAL.md 与新工具；安装说明标注自动生成行为；快速开始加教程入口。
- `tools/chatparty/README.md`：新增 orchestra_bridge / 启动器 / 主进程补丁三节，自改教程扩写（trusted 输入三重门原理、asar 重打包三坑、提取脚本注入），依赖说明更新。

## v1.1.0（2026-09-18）

### Added

- **独立国外顾问组**：ChatGPT / Grok / Copilot / Perplexity / Gemini 五站纳入同一「国外顾问组」（双轨规则不变），共用同一条本地代理通道与同一个独立浏览器 profile（CDP 9227）。
  - `references/capabilities.example.md`：新增「国外顾问组」完整节——成员表（含每站 E2E 状态）、运行形态（页面/iframe 双形态）、登录态边界（独立 profile 人工登录一次即持久）、双轨调度细则；硬红线明确覆盖全部外网成员。
  - `references/scan_routes.py`：外网节扩展为五站（`FOREIGN_MEMBERS`），新增每站 E2E 实测备注（`FOREIGN_NOTES`，Grok 的代理 WebSocket 阻断如实标注）与 `FOREIGN_CLI` 配置项。
  - `references/routes.example.yaml`：外网占位条目替换为五站完整示例（launcher/cli/每站 note）。
  - `SKILL.md`：架构图与路由规则段同步国外顾问组五站描述。
- **`tools/foreign-cli/`**：国外顾问组命令行通道工具（`status / new / send / extract / ensure` 五件套，`@file` 发文件、`--tail` 收回复）。
  - **三重门发送管线**（从 ChatParty 工具链移植到普通网页）：扫描门（15 点多点 elementFromPoint 命中检测 + 弹层自动清障 + trusted Escape）→ 焦点门（trusted click 后 activeElement 校验）→ 值门（insertText 后非空校验）→ trusted Enter；任一门失败 ABORT 并输出分段日志，不盲发。
  - **iframe 双形态支持**：页面标签页与 OOPIF iframe（分屏「全提问」形态）target 同等支持——CDP trusted 输入在 iframe 上与页面完全等价。
  - **host 级 target 匹配**：按 `urlparse(url).netloc` 匹配站点，双域名宽匹配（copilot），防第三方 iframe URL 参数污染子串匹配。
  - **登录态边界文档化**：cookie 绑定独立 profile 加密存储，人工登录一次即持久；README 含幂等启动 bat 要点（`--remote-debugging-port / --proxy-server / --user-data-dir`）。
  - **五站 E2E 实测**：ChatGPT / Copilot / Perplexity / Gemini 发送→回复闭环全通；Grok 输入管线通，回复流受代理 WebSocket 阻断（间歇性，页内可恢复）——如实入档。

### Changed

- `README.md`：目录结构与安装说明补 `tools/foreign-cli/`。

### 涵盖 v1.0 后未发版的远端提交

- `1bb7faa` — 完整脱敏成员名册（`capabilities.example.md`）+ 一行命令安装脚本（`install.ps1` / `install.sh`）。
- `fe0a790` — SKILL.md 新手序言：统合手头已有模型、减少 token 浪费、可升级付费成员。
- `fa2cc44` — FDE 反馈落地：**三层执行模式**、自检纪律、脚本优先验收门。
- `48bade7` — **cutlin 机制**：交付承诺锁（delivery promise lock）、只追加决策日志（append-only decision log）、金样本回归（golden-sample regression）。

## v1.0.0（2026-09-15）

- 首个公开版本：多 AI 交响调度技能——角色制架构（组长层/顾问组/干活组/特殊工作组）、七步流程、任务包人话化模板、五级降级路由、ChatParty 顾问通道工具链（登录看门狗 + 试跑 + 巡检三合一）、工作流沉淀模板。
