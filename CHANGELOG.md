# 更新日志

本仓库遵循语义化版本（MAJOR.MINOR.PATCH）。所有显著变更记录在此。

## v1.3.1（2026-09-18）

> 来源：DSH 实战两轮测试 + 教育产品页成品验收暴露的六个缺口，全部补上并实测。

### Added

- **`tools/chatparty/orchestra_bridge.py` — `broadcast` 子命令**（全员发布+对账）：逐站发送、站间 2~4s 随机节流（同 foreign-cli 防风控参数），末尾输出四态对账清单——`sent`（URL 跳转确认）/ `verify`（URL 未变但残留少，可能已在会话页，read 确认）/ `suspicious`（疑似假成功，read 验证后重发或换站）/ `missing`（无 target，开卡/补发）；支持 `only=k1,k2` / `skip=k` 过滤；退出码非 0 = 有 missing 或 suspicious。实测 `only=kimi,deepseek` 分类全对。
- **多 target 防僵尸**：同站多 webview（deepseek 双 target 实测）按 title 排序取最优（含站名 > 不含 > 空；同组 title 更长者优先），首选发送失败自动换下一候选重试，`used_candidate` 回报实锤。
- **假成功自救（全 trusted 管线 fallback）**：send 后验证 URL 跳转与输入框残留——URL 未变且残留 >8 字时自动走全 trusted 管线（清残留 → trusted click 编辑器中心 → `Input.insertText` 重填 → trusted Enter）→ 复验 URL。实测千问、知乎直达从假成功中复活（Lexical 类富文本编辑器拒收合成事件的根因）。发送成功但框有残留也自动清（metaso 240 字残留课）。
- **`tools/chatparty/clear_doubao_customkey.py`** — 清豆包 custom script 的 `sendMessage`（消「1+11+1」填字竞态；`getLLMLastMessage` 保留——读回复依赖）。键的真实位置：主窗口 `chatallai_custom_scripts` → `doubao` → `scripts.sendMessage`。⚠️ 生效需重启 ChatParty（会丢全部 webview 会话）。
- **SKILL.md 三个门 + 通道路由规则**（教育产品页实战）：
  - **ChatParty 通道选择与对账**：群发用原生多模型讨论+RESCUE 兜底，单站才用 bridge；url_changed=false 必须重发或换站；逐站派发后对账缺谁补谁。
  - **合规门**：对外交付必检广告法红线，指定一名顾问专职审（全员同话术评审会集体漏掉合规——实测 10 顾问无一拦截「平均提分 27 分」类文案）。
  - **交付前验收门**：硬指标 checklist 逐项打勾 + 新眼复审（派未参与制作的顾问通读成品）。
  - **收敛门（硬 gate）**：把「多审原则 3 轮起步」从口号变成检查点——轮次下限 ≥2、收敛判据全满足（意见 100% 处置记录 / 本轮无新增实质意见 / 修订稿经提意见者本人确认——沉默≠确认 / 合规已专审）、回复率 <60% 不算收敛、熔断 4~5 轮僵局升级人类决策。DSH 实测一轮意见就开工，正是没门拦住的后果。
- **`references/discussion-protocols.md` 四个新节**：合规审查清单（广告法红线五类表 + 教育/医疗/金融行业红线 + 成品遗留物检查）、评审维度分配表（结构/合规/技术/转化互斥派单，意见带维度标签，合规一票否决）、任务包落盘协议（`discussions/<时间戳>-<主题>/` 四文件：task.md 不可变 + transcript.jsonl append-only + review.md 按维度归并 + export.md 交付随附）、多轮打磨协议（轮次结构 + 收敛判据 + 假收敛黑名单 + 熔断）。

### Fixed

- `orchestra_bridge.py` send/read 假成功误报：豆包等站点「已在会话页再发消息 URL 不变」不再误判为失败（残留阈值 >8 字区分）。

## v1.3.0（2026-09-18）

### Added

- **`references/discussion-protocols.md`** — 讨论工作流协议库（本次核心）：把两个 DSH 生态项目（[dsh-plugin-roundtable](https://github.com/9931666/dsh-plugin-roundtable)、[dsh-deepseek-web-login](https://github.com/cv-superding/dsh-deepseek-web-login)，均致谢）的可借鉴设计，落到 ai-orchestra 的纯编排层（与具体站点无关）：
  - **三种讨论模式**：主持人统筹 / 平等互辩 / 针锋相对红队——模式选择表 + 各自的轮次编排语义。
  - **汇聚网关**：round2 禁止全文拼接上一轮回答（token 爆炸 + 上下文空转根因）——LLM 观点自动拆分（段落切分兜底）→ 去重归并 → 分维度摘要后再下发。
  - **红队评审闭环**：三态表态（支持 / 驳回必填理由 / 取消）、maxReviewPass=3、驳回认定 ≥3 触发重新协商、驳回理由回传给原作者修订。
  - **预算熔断**：单任务最大轮次/最大消息数上限，超限熔断出阶段结论而非死循环。
  - **人类决策暂停**：关键分歧点暂停出决策卡片（选项+各立场一句话），等人拍板再继续。
  - **落盘与导出**：transcript append-only 逐轮追加、export.md 定稿导出、原子写（tmp+rename）+ malformed 计数。
  - **防风控节流**：同站发送随机间隔 2000~4000ms（固定间隔方差≈0 是定时器特征，双窗口高并发实测触发封禁）；明确「发送成功 ≠ 服务端接受」；429 按 retryAfter 退避。muted 教训只能从「生成被拒」学到——只读探查探不出来，故刻意不做自动换号。
- **`tools/chatparty/patch_main_customsend47.py`** — **RESCUE 群发漏站补扫**（实测版本）：群发循环在渲染进程（50ms 内连发 IPC），漏站 = 渲染进程没发 IPC。补扫挂在 `ipcMain.handle("send-message-to-webview")` wrapper：60s 滑窗记账 → ≥3 条完全一致消息判定群发语义（单发/2 站对比不触发）→ 3.5s 静默 → DOM 枚举 `webview[id]` → 缺失站直调原 handler 补发（复用 custom script + trusted 全套）；防重 = 同消息 90s 时间桶。实测：两次群发分别救回 kimi 单站、kimi+知乎直达双站（时序 ENTRY→+3.5s 补扫→BRANCH→跳会话页，符合设计）。
- **`tools/chatparty/patch_main_customsend48.py`** — **豆包改版适配**（实测版本）：豆包前端改版后 guidance textarea 形态消失（编辑器变 tiptap ProseMirror contenteditable、发送按钮 class 更换），custom script 填字成功但按旧 class 找按钮静默放弃。五锚点 D1~D5 把 `__cpIsDoubao` 并入 metaso/kimi 的 attach + 三重门 trusted 分支（contenteditable 版表达式自动适用），custom 填字在前、trusted Enter 兜底。实测发送后跳会话页。

### Changed

- `SKILL.md`：第 4 步「定稿标准」后新增**红队评审**段落（定稿后可选环节），引用 `references/discussion-protocols.md`。
- `tools/foreign-cli/foreign_cli.py`：**防风控节流**——同站发送前按 `ORCHESTRA_FOREIGN_GAP_MIN/MAX`（默认 2.0~4.0s）随机等待；`send` 输出新增 `url_changed`（URL 是否变化，辅助判定服务端是否真正接受），note 明确「front-end submit only; verify reply via extract」。
- `tools/chatparty/README.md`：主进程补丁节提级到 v4.7/v4.8（RESCUE 补扫机制、豆包并入 trusted 分支、无害填字竞态说明），依赖说明同步。
- `.gitignore`：排除补丁产物 JS（`main_v4*_sendpatch.js`），只入库 patch 工具脚本。

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
