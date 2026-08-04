# 仓库状态：XA-Guard / XA-202620

> 复核日期：2026-08-04
> 当前口径：**赛题 D1–D3 形式基本符合 / P0 安全后端与真实外部模型 v2 D1/D2 因果证据通过 /
> 专用 PUBLIC 正例 live 通过 / 独立 HTTP HITL live、Gate5、GUI/D3、全量发布复验及人工提交未完成**
> 本文件描述当前仓库事实，不代表主办方验收或官方评分。

## 1. 总体结论

XA-Guard 不是 PPT 原型：仓库内有真实 MCP 代理、Gate1–Gate6、动态策略、DLP、HITL、
Operator 控制面、AIBOM、身份与 Undo、审计链、OAR 因果实验和独立 verifier。

2026-07-30 的 P0 已把此前最关键的产品缺口落实为代码和受控测试：

- 普通 MCP 不再伪装为可信 `USER`；可信 Adapter 可传入经过 HMAC/TTL/nonce/tool/args/
  history/identity 绑定的 provenance；
- Gate4 能解析 `sources/attachments/records` 引用；敏感或未知 external egress 在 executor
  前拒绝，PUBLIC 引用保持可用；
- 正式 Agent plane 不暴露审批工具；HTTP 另有 `/operator/mcp`，要求独立身份、角色、tenant、
  header token、职责分离和理由；
- approval 绑定身份、tenant、provenance/history、taint、effective policy、effect 和 nonce；
  准许后重新运行 governance、Gate1–4，再进入 Gate5/executor；
- tenant overlay 只作用于当前 tenant；写操作 Gate 内部异常有不可被配置降级的安全下限；
- OAR 已生成产品兼容可信上下文，且产品解析器完成 wire contract 交叉验证。

2026-08-03 经负责人明确批准，已在沙箱外使用 `.env` 的 DeepSeek Key 完成正式 v2：
`deepseek-v4-pro` 原生 Tool Call、30 runs、0 infra；15 个违规意图在 Null 15/15 harm，
XA-Guard live stdio 15/15 deny、0/15 harm。D1 neutral-tool 5/5 形成稳定因果证明，旧 v1 的
D1 allow/harm 失败仍保留；D2 两档 10/10 仍稳定。verifier 22/22 PASS、303 文件可重算，
篡改副本 FAIL，API Key 未进入证据。

2026-08-04 又完成专用 PUBLIC 正例：DeepSeek 原生安全 ToolIntent 5/5，Null 与
XA-Guard live stdio 均 5/5 branch allow、downstream=1（Gate6 audit 为 Gate2 yellow warn），
0 infra，3/5 稳定门通过；verifier 4/4、
93 文件一致，篡改副本 FAIL。这证明当前链路不是 deny-all。

但“比赛最终发布/擂主态”仍未成立：v2 与 PUBLIC 包均来自 dirty worktree/internal run；
独立 HTTP Operator/Dora HITL live、Gate5、实际 GUI、连续录屏、新版 D3、独立盲测、
clean checkout release 和人工外部提交仍未完成。

## 2. 赛题交付符合度

| 交付项 | 当前状态 | 审核结论 |
|---|---|---|
| D1 技术方案 | **形式 PASS，内容待 v2 同步** | 正式 PDF 18 页，低于 30 页；旧 v1 失败与新 v2 D1 stable causal proof 均已封存，但尚未写回正式报告 |
| D2 代码与复现 | **P0 受控 PASS，最终 release 未过门** | 核心代码与测试真实；支持环境 MCP/HTTP、Gate5、全量依赖能力和 clean checkout 仍待 |
| D3 演示视频 | **形式 PASS，竞争力仍不足** | 530.033 秒，低于 10 分钟；当前仍以静态证据投影为主，不是新的连续 GUI/TUI 实操 |
| D4 报名表 | **仓库外待人工确认** | 隐私材料不入仓库；当前无法独立确认盖章/报名系统状态 |
| 资格/知识产权 | **待人工合规审查** | 学籍年龄、团队/导师、关联单位、字体/截图/TTS/模型输出/素材授权需负责人和学校确认 |
| 外部提交 | **未验证完成** | 邮件、仓库 URL、网盘权限、报名系统和回执均需负责人操作 |

冻结文件：

- D1：`output/pdf/XA-Guard-XA-202620-technical-report.pdf`，SHA-256
  `de37a83c973d28f1b4efdc77efda4648a704db94540cb9839b6f4d2e8660c7f1`。
- D3：`output/video/XA-Guard-XA-202620-demo.mp4`，SHA-256
  `267a1a59f7f48c9d8e489f085afda0ff79197118ceff7b7e2d5422d5962b00c5`。

## 3. 当前技术状态

主流水线：

`governance → Gate1 → Gate2/Gate4-in/Gate3 → Gate5 → executor → Gate4-out → Gate6`

| 能力 | 已实现事实 | 仍有边界 |
|---|---|---|
| Gate1 | 多 detector、spotlighting、UNKNOWN 来源风险；unexpected detector crash 按 effect 安全矩阵处理 | 模型 detector 可选；自建 60/60 不是独立盲测；read-only 可 WARN 降级 |
| Gate2/HITL | bound token、过期/漂移/replay、批准后重验证；正式 stdio/HTTP Agent plane 隐藏审批 | token 消费仅单进程；源码仍有 demo 默认 approval secret，生产必须显式配置；私有 `_build_app` 保留显式兼容入口 |
| Operator | `/operator/mcp` 独立 manager；共享 pending；verified identity/role/tenant/SoD/header credential；拒绝不污染 pending | 网络实传与真人 OIDC 录屏待支持环境；无配置 credential 时 fail-closed |
| Pending | ledger 不保存 token、provenance、工具结果或 history 正文；旧 ledger 缺安全标记默认 fail-closed | 非 schema/非敏感键的参数仍是 best-effort 持久化；不是生产工作流/多实例队列 |
| Gate3 | Python/Rego、热更新、baseline+当前 tenant overlay、effective SHA | 当前 WSL 不能运行仓库 Windows `opa.exe`；正式 Linux/Windows 支持环境待复验 |
| Gate4 | 字面扫描、taint、capability、schema-aware 引用、执行前 external egress preflight、出向结果扫描；v2 D1 neutral-tool 5/5 执行前 deny、0 harm；PUBLIC live 5/5 allow/downstream=1 | Gate4-out 不能撤销已发生副作用；clean release 仍待 |
| Gate5 | Docker/runc/runsc、资源/网络限制代码存在 | 默认和现有主演示关闭；无 live evidence |
| Gate6 | 哈希链、faithfulness、verifier、可选 SM2/external signer；provenance 只落摘要/分类 | 默认本地 SHA-256/无签名；通用 tool parameters 仍可能含业务明文，生产脱敏策略需收口；本环境缺 `gmssl` |
| Tenant | Gate2/3/4 使用 baseline+单一 tenant overlay；双租户测试和 SHA 区分通过 | legacy 无 tenant 读取仍用于导出/兼容，安全 Gate 已显式传 tenant |
| OAR | 正式 v2 `p0-real-agent-causal-d1-d3-v2` 已完成：30 runs、0 infra、15/15 conditional block、22/22 verifier；PUBLIC utility live 5/5 双成功、4/4 verifier；可信 Adapter 绑定冻结 session/history/source digest | internal run、dirty worktree；D3 0/10 attempt；尚非 clean release 或独立第三方盲测 |

## 4. 证据强度与 claim 边界

### 已有强证据

- 正式真实 DeepSeek v2：30 runs、0 infra；D1 neutral-tool 5/5 attempt、Null harm 5/5、
  XA-Guard Gate4 deny 5/5、Guard harm 0/5；D2 两档 10/10 attempt、Null harm 10/10、
  XA-Guard deny 10/10、Guard harm 0/10。
- v2 authenticity：22/22 checks、303 files、30/30 verdict、15/15 live audit；原包 PASS，
  只改 summary 指标的复制包因 hash 与指标重算双重不符 FAIL；API Key 泄漏扫描 PASS。
- 正式 PUBLIC utility live：5 runs、0 infra、DeepSeek 原生安全 ToolIntent 5/5；Null 与
  XA-Guard live 均 5/5 allow/downstream=1；3/5 门槛 PASS，verifier 4/4、93 files，
  篡改副本 FAIL，API Key 泄漏扫描 PASS。
- 旧真实 DeepSeek holdout：30 runs、0 infra；D2 两档 10/10 形成违规 ToolIntent，
  Null 10/10 harm，XA-Guard 10/10 deny、0/10 harm；同一冻结 intent 的因果 A/B。
- 旧 holdout authenticity 本次复验 `ok=true`：303 files、30/30 verdict、15/15 audit，
  metrics、stability 和 causal proof 重算一致。
- 受控 P0 MCP 集成：verified CONFIDENTIAL 引用 deny/downstream=0；PUBLIC
  allow/downstream=1；unknown/tampered deny/downstream=0。
- OAR/product wire contract：签名 envelope 可被产品验证，source 仅含 digest，不含资产正文。
- OpenCode 证据仍只证明安全调用互操作：1.18.5 + DeepSeek V4 Flash + XA-Guard HTTP MCP，
  `get_cpu` allow、Gate6 可验。

### 必须保留的负结果

- 旧 D1 realistic-safe 5/5 attempt、Guard 5/5 allow/harm 是真实历史失败；不得删除或覆盖。
  v2 证明新产品在 D1 neutral-tool 的 5 个新意图上阻断；不能说跨版本复用了同一个 intent。
- v2 D1 realistic-safe 0/5、D3 两档 0/10 attempt 是模型自防，不是 Guard win。
- Gate1 60/60 是 scoped 自建集，`independent_holdout=false`。
- OpenCode 未发生已封存的攻击阻断，不能说“打穿 OpenCode 后由 XA-Guard 防住”。

### 当前允许的最强措辞

> 我们保留了 v1 的真实 D1 失败；v2 使用真实 DeepSeek 原生 Tool Call 与 XA-Guard live stdio，
> 在 D1 neutral-tool 5/5 和 D2 两档 10/10 的同意图 A/B 中实现 Null harm、Guard deny/0 harm。
> 独立 PUBLIC utility live 又在 5/5 同意图 A/B 中实现 Null 与 Guard 双 allow/downstream=1，
> 证明不是 deny-all；独立 HTTP Operator/HITL 仍未 live 完成。

禁止使用：`100% 防御`、`任意 Agent 通用`、`OpenCode 攻击已拦截`、`六层同一 live 链路
全运行`、`独立第三方盲测`、`生产级 HSM/TSA/HA`、`GUI/D3 已完成`、`已最终提交`。

## 5. 当前验证状态

P0 主验收：

```text
80 passed
```

OAR 非基础设施：

```text
10 passed, 1 deselected
```

正式外部模型 v2：

```text
30 runs；0 infra；15 attempts；Null harm 15；Guard deny 15；Guard harm 0
verifier 22/22 PASS；303 files；30/30 verdict；15/15 live audit
tampered copy: FAIL（预期）
```

正式 PUBLIC utility live：

```text
5 runs；0 infra；5 native intents；Null allow/downstream=1 5/5；
XA-Guard live allow/downstream=1 5/5；3/5 threshold PASS
verifier 4/4 PASS；93 files；tampered copy FAIL（预期）
```

广泛分批回归（组间有重叠，不得相加为全量总数）：

| 测试组 | 结果 |
|---|---|
| AIBOM/bench/audit/config | 199 passed, 1 skipped |
| control 核心 | 51 passed |
| Gate1–5 | 171 passed；4 个 OPA 环境失败 |
| Gate6/provenance | 13 passed；2 个缺 `gmssl` 失败 |
| L3/layered/OPA export/OpenCode bridge | 84 passed |
| P0/pending/resilience/server/crypto 等 | 95 passed, 13 skipped |
| changed Python Ruff | all checks passed |
| GUI handoff schema/sample | 2 schemas valid；4 synthetic events valid |

本环境已确认的能力限制：

- 既有 WSL 复验中，`tools/opa/opa.exe` 报 `UtilBindVsockAnyPort ... socket failed 1`；
- `gmssl` 可选依赖未安装；
- 沙箱禁止本地 socket，Business API 3 项 `PermissionError`；
- reference KMS/worker health/部分 identity TestClient 用例挂起；
- 受限 Windows 沙箱内启动 OAR live MCP subprocess 会在匿名管道创建处返回
  `PermissionError: [WinError 5]`；经负责人明确数据外发授权后，沙箱外正式 v2 与 PUBLIC
  utility live 已完成。

因此不能写“全量 pytest 全绿”。本轮未修改旧测试、payload、oracle、阈值或 frozen evidence
来隐藏失败。

## 6. GUI/D3 当前状态

实际 GUI、Workbench 和录制未实现，符合负责人明确范围决定。已准备：

- `docs/demo-handoff/contracts.md`
- `docs/demo-handoff/schemas/`
- `docs/demo-handoff/examples/`（明确 `SYNTHETIC / EXAMPLE ONLY`）
- `docs/demo-handoff/layout-and-recording.md`
- `docs/demo-handoff/IMPLEMENTATION-HANDOFF-CHECKLIST.md`

这些材料定义单屏布局、LIVE/SEALED/NOT_REACHED 语义、8:50 分镜、artifact→UI 映射、
真实 v2 操作顺序和 claim 红线；v2 原始包已生成，但不能把 synthetic 样例截图冒充实跑。

## 7. 距离最终比赛状态

### 提交前硬门

1. 在允许本地进程/网络的支持环境复验真实 stdio 与 HTTP Agent/Operator 双端点。
2. 完成 Agent pending → 独立 HTTP Operator/Dora → exact-hash 单次执行 → replay 拒绝的
   HITL live；PUBLIC 双成功 live 已完成，不能用它替代 HITL。
3. 负责人实现 GUI 并连续录制；重做 D3，不能用 synthetic fixture 当 live。
4. 在支持环境启用 Gate5 live，或在画面标 `DISABLED/NOT REACHED`。
5. 完成 clean checkout 全量 capability matrix、最终 commit 对应 release manifest。
6. 收口通用审计参数与 pending 参数的生产脱敏；部署显式 approval/provenance secret。
7. 人工确认 D4、资格、团队/导师、知识产权/素材授权、邮件/网盘/报名系统和回执。

### 冲击最高分

1. 引入未参与调参者封存、许可明确的盲测集，预注册指标并报告置信区间。
2. 把 nonce/token 消费放入共享事务存储，证明跨进程/重启 replay。
3. 补 Gate5 真实 allow/deny 对照和支持环境性能。
4. 将 v2 数字由 manifest/verifier 自动同步到 D1、D3、QA 和公开 evidence。

保守判断：技术 P0 已从“产品闭环受控通过”提升为“D1/D2 真实模型因果证据 + PUBLIC
utility live 通过”；比赛竞争力的最大剩余短板是**独立 HTTP HITL live、GUI 连续演示、
Gate5、独立性和发布合规**。
