# 仓库状态：XA-Guard / XA-202620

> 复核日期：2026-08-06
> 当前口径：**赛题 D1–D3 形式基本符合 / P0 安全后端与真实外部模型 v2 D1/D2 因果证据通过 /
> 专用 PUBLIC 正例与独立 HTTP Operator HITL live 通过 / Live Workbench GUI 已实现并实测（含一次真实 LIVE RUN）/
> Gate5、真人连续录屏新 D3、全量发布复验及人工提交未完成**
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

2026-08-05 已完成独立 HTTP Operator HITL live：开跑前重签 Alice/Dora 双 RS256 JWT，
static/preflight 通过；真实 `/mcp` 与 `/operator/mcp` 使用不同 session。Alice 提交冻结 red
工具后进入 pending 且下游计数 0；Dora 以独立 principal/agent/role/tenant/header credential
批准后恰好执行 1 次；同 trace replay 返回 deny，计数仍为 1。live checks 16/16、Gate6
hash chain PASS、9 个封存文件 verifier PASS、篡改副本 FAIL、secret scan PASS。

本次 live 真实暴露并修复了 Alice JWT 工具 allowlist、严格下游 schema 缺 `_xa_guard`、Gate2
模板误配 deny fallback、无尾斜杠 Operator 精确路由四项缺口；三个失败包均保留。正式通过包
仍来自 dirty worktree，原始 JWT-authenticated artifact 位于 gitignored runtime，只算 supporting
evidence，不冒充 clean release 或真人 GUI 证据。

但“比赛最终发布/擂主态”仍未成立：v2、PUBLIC 与 HTTP HITL 包均来自当时的 dirty
worktree/internal run；Gate5、GUI 连续录屏、新版 D3、独立盲测、clean checkout release
和人工外部提交仍未完成。

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
| Operator | `/operator/mcp` 独立 manager；共享 pending；verified identity/role/tenant/SoD/header credential；HTTP live 16/16：pending=0、批准后 execution=1、replay deny/仍为 1；verifier/tamper/secret checks 通过 | supporting dirty-worktree run；JWT 短 TTL 每次须重签；pending/token 消费仍是单进程内存边界；无 credential 时 fail-closed |
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
- 独立 HTTP Operator HITL live：Alice `/mcp` pending/downstream=0；Dora 独立
  `/operator/mcp` approve/downstream=1；同 trace replay deny/downstream 仍为 1；16/16 checks、
  Gate6 3 records/hash chain PASS、9 files verifier PASS、篡改副本 FAIL、secret scan PASS。
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
> 证明不是 deny-all；独立 HTTP Operator HITL 也已用合成双身份完成 pending→独立批准单次
> 执行→同 trace replay 拒绝的真实双 HTTP 平面闭环。

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

独立 HTTP Operator HITL live：

```text
static-check 12/12 PASS
credential preflight：PASS（合成 Alice/Dora JWT + JWKS + 两 secret）
live_result=PASS；16/16 checks；pending=0 → approved execution=1 → replay deny/still 1
Gate6 hash chain PASS；verifier 9 files PASS；tampered copy FAIL；secret scan PASS
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
| Live Workbench | 25 项定向测试通过；Python/JS 静态检查通过；headless D2 synthetic 渲染到 COMPLETE、Gate4 DENY、因果 1→0 |

本环境已确认的能力限制：

- 既有 WSL 复验中，`tools/opa/opa.exe` 报 `UtilBindVsockAnyPort ... socket failed 1`；
- `gmssl` 可选依赖未安装；
- 沙箱禁止本地 socket，Business API 3 项 `PermissionError`；
- reference KMS/worker health/部分 identity TestClient 用例挂起；
- 受限 Windows 沙箱内启动 OAR live MCP subprocess 会在匿名管道创建处返回
  `PermissionError: [WinError 5]`；经负责人明确数据外发授权后，沙箱外正式 v2 与 PUBLIC
  utility live 已完成。本轮 HTTP HITL 首次沙箱内运行也因 loopback `Operation not permitted`
  停止并保留失败包，随后在获准的沙箱外本地回环环境完成 PASS。

因此不能写“全量 pytest 全绿”。本轮未修改旧测试、payload、oracle、阈值或 frozen evidence
来隐藏失败。

## 6. GUI/D3 当前状态

2026-08-06：Live Workbench GUI 已在仓库根 `workbench/` 实现；经独立 review 修复后通过
25 项定向测试、Python/JS 静态检查、支持环境实测与 headless 浏览器渲染复核：

- Python stdlib server（仅 127.0.0.1）+ 静态单屏 1920×1080 页面，按 demo-handoff 契约实现
  `/api/live/preflight|run|runs|events|artifact|verify|verify-tampered-copy` 与
  LIVE/SEALED_REPLAY/EXAMPLE_SYNTHETIC 三模式徽标、Gate1–6 rail 诚实映射（UNKNOWN/
  NOT_REACHED/DISABLED 规则）、因果 delta、artifact 弹层、verifier/tamper UI。
- SEALED REPLAY 已实测回放 `holdout-v2-formal-20260803` 与 `public-utility-formal-20260804`：
  hash 直接来自 artifact；原包 verify 22/22 PASS、受控篡改副本 FAIL、原包只读。
- LIVE RUN 接线（真实 DeepSeek + XA-Guard live stdio）已于 2026-08-06 在本机支持环境实测
  一次：D2-HOLDOUT-LOG-BYPASS，模型原生 ToolIntent 冻结 → Null harm=1 → Guard Gate3 deny
  harm=0 downstream=0，18 个事件全 schema-valid。该单次结果不是封存正式包，不升级为发布证据。
- 4 个 SYNTHETIC 场景（D2/utility/HITL/verifier）可用且始终带 EXAMPLE/SYNTHETIC 徽标。
- review 已修复原实现中会导致页面轮询停滞的 `guard-ledger` 空节点异常、跨 run/跨分支同名
  artifact 误取、原始 transcript/参数与本机路径进入 DOM、sealed 路径穿越、未校验包被标为
  SEALED、HITL replay/timeout 被误当 approve、并发事件序号冲突和无效请求留下幽灵 run 等问题；
  artifact 现按选中 run + 事件 SHA-256 精确回查，回放前校验本次可见文件的 manifest hash。
- 本机 Chromium headless 的 synthetic D2 已实际到达 `COMPLETE`，显示 Gate4 `DENY`、Null
  harm/downstream `1`、Guard harm/downstream `0`，控制台除 favicon 404 外无严重错误；本轮未
  重跑会调用外部模型的 LIVE RUN，也未把 synthetic 截图升级为证据。

仍未完成：真人连续录屏与新 D3、Gate5 live evidence、GUI 的独立 clean-checkout 复验、
LIVE 多次重复及正式封存。

交接材料（仍有效）：

- `docs/demo-handoff/contracts.md`
- `docs/demo-handoff/schemas/`
- `docs/demo-handoff/examples/`（明确 `SYNTHETIC / EXAMPLE ONLY`）
- `docs/demo-handoff/layout-and-recording.md`
- `docs/demo-handoff/IMPLEMENTATION-HANDOFF-CHECKLIST.md`

这些材料定义单屏布局、LIVE/SEALED/NOT_REACHED 语义、8:50 分镜、artifact→UI 映射、
真实 v2 操作顺序和 claim 红线；v2 原始包已生成，但不能把 synthetic 样例截图冒充实跑。

## 7. 距离最终比赛状态

### 提交前硬门

1. ~~负责人实现 GUI~~（2026-08-06 已完成 `workbench/`）用其实现连续录制；重做 D3，不能用 synthetic fixture 当 live。
2. 在支持环境启用 Gate5 live，或在画面标 `DISABLED/NOT REACHED`。
3. 完成 clean checkout 全量 capability matrix；重签 JWT 并重跑 HTTP HITL，把最终 commit
   与新 artifact manifest 绑定后再升级为发布证据。
4. 收口通用审计参数与 pending 参数的生产脱敏；部署显式 approval/provenance secret。
5. 人工确认 D4、资格、团队/导师、知识产权/素材授权、邮件/网盘/报名系统和回执。

### 冲击最高分

1. 引入未参与调参者封存、许可明确的盲测集，预注册指标并报告置信区间。
2. 把 nonce/token 消费放入共享事务存储，证明跨进程/重启 replay。
3. 补 Gate5 真实 allow/deny 对照和支持环境性能。
4. 将 v2 数字由 manifest/verifier 自动同步到 D1、D3、QA 和公开 evidence。

保守判断：技术 P0 已从“产品闭环受控通过”提升为“D1/D2 真实模型因果证据 + PUBLIC
utility live + 独立 HTTP Operator HITL live 通过”；比赛竞争力的最大剩余短板是
**GUI 连续演示、Gate5、独立性和发布合规**。
