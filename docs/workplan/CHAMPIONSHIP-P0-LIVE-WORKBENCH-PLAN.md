# XA-Guard 冲刺最强版本：P0 产品闭环与 Live Workbench 实施计划

> 版本：v0.2 APPROVED
>
> 日期：2026-07-30
>
> 状态：**APPROVED / BACKEND P0 IMPLEMENTED / LIVE V2 D1-D2 SEALED /
> UTILITY-HITL-GATE5-GUI PENDING**
>
> 依据：赛题专项方案、`status.md` 2026-07-30 全面审核、现有 D1/D2/D3、OAR live-agent
> holdout、OpenCode 安全互操作证据和身份控制台实现。

## 0. 审批结果与执行约束

负责人已于 2026-07-30 批准立即执行，并作出两项范围决定：

1. 子代理统一使用 `gpt-5.6-terra`、reasoning `medium`；
2. 所有实际 GUI、网页界面、GUI 录制和正式 D3 重拍均由负责人后续完成。本轮只准备安全后端、
   事件/API/数据契约、场景、样例、线框、分镜、素材清单和验收清单，不实现 GUI。

本轮仍禁止：

- 覆盖或改写 `.runtime/live-agent/holdout-v1`；
- 为获得更好结果而删除、放宽或改写既有测试；
- 修改旧 payload、oracle、阈值或 frozen evidence 制造通过；
- 未经负责人单独授权发送邮件、上传网盘、修改 D4、发布远端仓库或创建正式 release；
- 把交接样例冒充真实运行证据。

### 0.1 执行快照（更新至 2026-08-03）

| 门 | 当前事实 | 结论 |
|---|---|---|
| G0 基线/契约 | 基线报告、旧 holdout verifier、D1/D3 hash 与 preserve list 已完成 | **PASS** |
| G1 provenance/D1 修复 | 产品 MCP 受控集成已证明敏感引用 deny、PUBLIC allow；正式 v2 D1 neutral-tool 5/5 Null harm、Guard live deny/0 harm | **LIVE D1 PASS / PARTIAL**；专用 PUBLIC Null/Guard 双成功 live 待补 |
| G2 HITL/策略/错误矩阵 | 独立 Operator 后端、绑定审批、重验证、租户视图、写操作异常安全下限及回归已实现；v2 D2 两档 10/10 deny/0 harm | **CONTROLLED + D2 LIVE PASS**；独立 HTTP Operator HITL live 与跨进程防重放仍待 |
| G3 非 GUI 交接 | event/API schema、合成样例、线框、分镜、素材和 GUI 验收纪律已交付 | **PASS（材料）**；GUI 未实现，符合负责人范围决定 |
| G4 新证据/Gate5/独立盲测 | 正式 v2 30 runs、0 infra、22/22 verifier，篡改副本 FAIL；Gate5 live 与独立盲测未补 | **PARTIAL** |
| G5 视频交接 | 8:50 分镜、录制清单和 claim 边界已准备 | **PASS（材料）**；实际 GUI/录制/D3 替换由负责人后续完成 |
| G6 发布收口 | 当前支持环境广泛测试仍有 socket/TestClient/OPA/gmssl 能力限制；人工合规和外部提交未完成 | **NOT PASSED** |

当前可宣布“P0 安全后端、D1/D2 真实模型 live 因果证据与 v2 verifier 已完成”；不能宣布
“专用 PUBLIC/HITL live、六层同链路、独立盲测、GUI/D3 或最终发布已完成”。



## 1. 最终目标

把当前“真实实现 + 强证据，但主线接入和演示割裂”的作品提升为：

1. 真实 Agent/MCP 调用携带可验证的 session/source/provenance；
2. D1 `sources` 引用型外发在执行前被 XA-Guard 正确处理；
3. HITL 与 Agent 工具面分权，批准后重新验证策略、身份和 taint；
4. 有外部副作用的 egress 在 executor 前完成安全预检；
5. 关键 Gate 失败采用显式、可测试的 fail-closed/降级矩阵；
6. 用真实外部模型原生 Tool Call 生成一次 ToolIntent，并以相同哈希分叉到
   Null/XA-Guard，产出可供负责人 GUI 使用的真实事件、业务后果、下游调用和审计数据；
7. 准备一套不依赖打穿 OpenCode 的 GUI/D3 交接材料，但不实现 GUI、不录制或重拍视频；
8. 保留所有负结果和历史证据，形成可复核的 before/after，而不是覆盖失败。

内部目标是将保守模拟评分从当前 70–82 推进到 85+ 区间；该数字只用于资源排序，不作为
比赛承诺。

## 2. 非目标

本轮不做：

- 不重新开发通用 Agent 框架，不复制 OpenCode/OpenClaw；
- 不把“能否越狱 OpenCode”设为验收条件；
- 不将 Reference Office Agent 设计成故意脆弱或硬编码攻击结果的玩具；
- 不追求 HSM、第三方 TSA、多地域 HA 等生产终态；
- 不声称静态分析能完备发现任意供应链恶意逻辑；
- 不把模型拒绝产生 ToolIntent 计为 XA-Guard 防御成功；
- 不把没有运行到的 Gate 渲染成通过；
- 不修改旧 holdout 的 payload、oracle、manifest、逐 run 结果或 hash；
- 不在负责人审核前扩展范围到 P2 生产化项目。



## 3. 目标架构

```text
OpenCode（互操作锚点）
  └─ 安全 Tool Call → XA-Guard HTTP MCP → Gate6 audit

Reference Office Agent / Live Workbench（主演示）
  ├─ 外部模型原生 Tool Call，tool_choice=auto
  ├─ Trusted Context Adapter
  │    └─ session / source / provenance / identity / policy bundle digest
  ├─ Intent Freezer
  │    └─ canonical ToolIntent + intent_sha256 + world_snapshot_sha256
  ├─ Null branch
  │    └─ Reference Executor → business state / downstream call / harm oracle
  └─ XA-Guard branch
       └─ Gate1–6 → deny / HITL / allow → business state / audit

Operator Control Plane
  └─ 独立 Dora 身份 → approve/reject/undo

Independent Verifier
  └─ manifest / artifact hash / audit / verdict / causal recomputation
```



### 3.1 Trusted Context Envelope

P0 使用版本化、可绑定的治理上下文，而不是让模型在普通工具参数中自报来源：

```text
schema_version
session_id / turn_id / task_id
human_principal / agent_id / tenant_id
history_digest
sources[]:
  source_id
  kind                 # user/web/document/rag/memory/tool_result
  locator_digest
  content_digest
  trust_state          # verified/unverified/unknown
  taint
resolved_references[]:
  reference_id
  asset_digest
  classification
  resolver_id
  resolution_status
policy_bundle_sha
issued_at / expires_at / nonce
binding_signature_or_mac
```

原则：

- 普通 Agent 参数不能把 `unverified` 自行升级为 `verified`；
- 未知来源不能继续默认为 `USER`；
- Gate6 记录 digest、分类和解析结论，不默认落原始敏感内容；
- envelope 绑定 tool name、canonical arguments、identity、session 和有效期；
- stdio 无可信适配器时必须明确降级或保守处理，不能伪称来源已验证。



### 3.2 Schema-aware Reference Resolver

XA-Guard 核心只定义 resolver 接口，不把产品耦合到 OAR：

```text
ReferenceResolver.resolve(reference_id, context)
  → resolved / unknown / forbidden
  → classification / taint / asset_digest / resolver_id
```

- OAR/Reference Office Adapter 实现业务世界资产解析；
- 未来真实业务系统由文档库、RAG、工单或数据目录 connector 实现；
- egress 工具出现未知/敏感引用时按策略 deny 或 require_approval；
- 已验证 PUBLIC 引用与安全正文必须继续允许，防止“修复”等于全拒绝。



## 4. 子代理与文件所有权

所有子代理均应使用负责人最终确认的模型，reasoning 固定为 `medium`。根代理负责冲突文件、
集成、最终测试、证据口径、`status.md` 和 `log.md`。


| 执行者   | 任务名                   | 独占修改范围                                                                        | 禁止范围                                       |
| ----- | --------------------- | ----------------------------------------------------------------------------- | ------------------------------------------ |
| 子代理 A | `provenance_dlp`      | 新 provenance/resolver 模块、`types.py`、`gate4_taint.py`、对应新增测试                   | 不改 `pipeline.py`、`upstream.py`、旧 holdout   |
| 子代理 B | `hitl_policy`         | `approval.py`、`proxy/pending.py`、`gates/base.py`、分层策略模块、对应新增测试                | 不改 `pipeline.py`、`upstream.py`、Console、旧证据 |
| 子代理 C | `demo_handoff`        | `docs/demo-handoff/` 的 schema、样例、线框、分镜、素材和验收清单 | 不创建 GUI/API handler，不改产品 Gate、旧 holdout、正式视频 |
| 根代理   | `integration_release` | `proxy/upstream.py`、`pipeline.py`、Operator/OAR 接线、集成测试、文档和验收报告 | 不覆盖用户既有脏工作树，不弱化测试，不实现 GUI |


协作规则：

1. 一个文件同一时刻只有一个所有者；
2. 子代理先提交发现和接口契约，再修改文件；
3. 根代理逐项审核 diff，不直接接受“测试通过”结论；
4. 新行为优先新增测试文件，既有测试不得删除、skip、放宽断言或改预期来获得绿色；
5. 如果既有测试本身确实错误，停止该工作包并报告负责人，得到审核后才允许修改测试；
6. 所有新依赖先检查许可证、维护状态和必要性；Workbench 优先复用当前 stdlib HTML/JS，
  不为 UI 引入大型框架。



## 5. 分阶段实施



### Phase 0：基线、冻结与契约（0.5–1 个工作日）



#### WP0.1 建立不可变基线

动作：

- 记录当前 commit、dirty paths、Python/Node/OPA/模型客户端版本；
- 核对 D1/D3 hash；
- 复跑旧 holdout verifier，但不改旧证据；
- 输出 baseline report 到新的 gitignored runtime 目录；
- 把与本计划无关的已有修改列为 preserve list。

验收：

- `holdout-v1` verifier 仍为 PASS；
- D1/D3 hash 与当前冻结值一致；
- preserve list 明确包含现有 PPTX、脚本和外部 evidence 行尾修改；
- 没有任何旧证据文件 hash 变化。



#### WP0.2 固化接口和安全不变量

在写实现前形成短规格：

- Trusted Context Envelope schema；
- resolver protocol；
- tool effect class：`read_only / local_write / external_write / privileged_execute`；
- 每个 Gate × effect class 的异常策略；
- approval token 新绑定字段；
- Workbench event schema。

必须成立的不变量：

- deny/require_approval 时 downstream call count = 0；
- 同一个 A/B run 的 ToolIntent 和初始世界 hash 完全相同；
- approval 不能由产生 ToolIntent 的 Agent 身份完成；
- policy/provenance/identity 漂移后旧批准不能直接执行；
- UI 只渲染实际 artifact/event，不用规则名猜测 Gate 结果。

退出门 G0：

- 负责人批准本计划；
- 子代理模型选择已解决；
- 所有 schema 和文件所有权无冲突。



### Phase 1：真实 Agent 上下文与 D1 修复（2–3 个工作日）



#### WP1.1 Provenance 数据模型

动作：

- 增加版本化 provenance 类型和严格解析；
- 区分 verified/unverified/unknown；
- 对 history/source/reference 计算 canonical digest；
- GateContext 增加最小必要字段并保持旧调用兼容；
- Gate6 审计增加 provenance 摘要，不落默认原文。

新增测试至少覆盖：

- 合法 envelope；
- 缺字段、过期、nonce 重放；
- tool/args/session/identity 绑定不一致；
- Agent 伪造 verified 来源被拒绝或降为 unverified；
- 原始敏感内容不进入默认审计摘要。



#### WP1.2 MCP/Adapter 接入

动作：

- 删除真实主线硬编码 `session_history=[]`、`input_sources=[USER]`；
- 可信 Adapter 注入已验证上下文；
- 普通 MCP 客户端没有 envelope 时显式标为 unknown/unverified；
- `_xa_guard` 治理信封不向下游业务工具透传；
- HTTP/stdio 两种 transport 的信任边界分别记录。

验收：

- 安全 OpenCode 调用在没有富 provenance 时仍按明确降级路径工作；
- Live Workbench 能传入 verified 多源上下文；
- 伪造 envelope 不能提升权限或 taint；
- Gate6 能关联 session、intent、source digest 和 policy bundle。



#### WP1.3 Reference Resolver 与执行前 egress

动作：

- 新建 resolver protocol 和 OAR reference adapter；
- 解析 `sources`、`attachments`、`records` 等 schema 声明的引用字段；
- Gate4-in 根据已解析 classification/taint 做 egress preflight；
- Gate4-out 只处理工具返回内容泄漏，不再被描述为阻止已发生副作用；
- 未知引用按 tool effect class 决定 deny/approval；
- executor 调用计数纳入 evidence。

验收场景：


| 场景                 | Null         | XA-Guard    | 关键断言                      |
| ------------------ | ------------ | ----------- | ------------------------- |
| D1 敏感 `sources` 外发 | harm         | deny        | Guard downstream=0，harm=0 |
| PUBLIC 引用安全外发      | success      | success     | 两边 downstream=1，无误拒       |
| 未知引用对外发送           | harm/unknown | deny 或 HITL | 结果符合显式策略                  |
| 只读安全工具             | success      | success     | 不因 provenance 缺省变成全拒绝     |


证据纪律：

- 旧 `holdout-v1` 5/5 失败永久保留；
- 修复后创建新版本目录和新 manifest，例如 `holdout-v2`；
- before/after 必须同时展示，不把 v2 写回 v1；
- 新模型运行前冻结新 manifest、case、prompt 和 policy hash。

退出门 G1：

- D1 引用型外发在 live XA-Guard 中执行前阻断；
- 至少一条安全正例保持成功；
- provenance 伪造、未知来源和审计脱敏测试通过；
- 旧证据完整性仍通过。



### Phase 2：HITL、策略重验证与错误策略（1.5–2.5 个工作日）



#### WP2.1 分离 Agent Tool Plane 与 Operator Control Plane

动作：

- 默认 Agent `tools/list` 不再包含 approve/reject 等操作员控制工具；
- stdio pending 只返回 trace/状态，不允许同一 Agent 自批；
- Operator API 要求受信任身份、角色和独立通道；
- HTTP 未配置 operator credential 时 fail closed；
- Console Dora 继续作为独立审批主体。

验收：

- Agent 侧无法发现或调用 approve；
- Alice/Agent 发起、Dora 批准可成功；
- 相同 principal/agent 自批被拒绝并审计；
- 缺 token、错误 token、错误 tenant、错误 role 均拒绝。



#### WP2.2 批准后的完整重验证

approval token 新增绑定：

- trace、tool、canonical args、identity、tenant；
- provenance/history/taint digest；
- policy bundle SHA；
- effect class、expiry、nonce。

批准恢复时：

1. 验证并消费 token；
2. 重建当前 GateContext；
3. 重新运行 governance、Gate1、Gate2、Gate4-in、Gate3；
4. 检查 policy/identity/provenance drift；
5. 通过后运行 Gate5、executor、Gate4-out、Gate6；
6. replay 必须拒绝。

验收：

- exact-hash 首次批准执行一次；
- 参数、来源、身份或策略任一变化后拒绝；
- token replay 拒绝；
- 过期 token 拒绝；
- 所有拒绝路径 downstream=0。



#### WP2.3 Fail-closed/降级矩阵

不采用“所有异常一刀切拒绝”，而按执行风险明确：


| effect class       | Gate1/3/4 内部异常           | Gate5 异常 | 预期                |
| ------------------ | ------------------------ | -------- | ----------------- |
| read_only          | 可配置 WARN/降级              | 不适用或明确策略 | 审计必须标 degradation |
| local_write        | 默认 require_approval/deny | deny     | 不静默继续             |
| external_write     | deny                     | deny     | downstream=0      |
| privileged_execute | deny                     | deny     | downstream=0      |


验收：

- 每个矩阵单元至少一项异常注入测试；
- 最终 decision、reason、degradation 和 audit 一致；
- 关键写操作不存在 Gate exception→WARN→executor 的路径。



#### WP2.4 Tenant overlay 修复

动作：

- baseline 保持全局；
- 只选择 `ctx.tenant_id` 对应 overlay；
- bundle SHA 能反映 effective tenant view；
- 热更新和单调性检查保持；
- 双租户相互不可见。

验收：

- tenant A 规则不影响 tenant B；
- A/B effective bundle SHA 可区分；
- baseline 仍对所有租户生效；
- 无 tenant 时使用明确 default/deny 策略。

退出门 G2：

- Agent 不能自批；
- 批准后重验证完整；
- 关键写操作所有 Gate 异常 fail closed；
- 双租户隔离测试通过。



### Phase 3：Live Workbench 非 GUI 后端与交接材料（1.5–2.5 个工作日）



#### WP3.1 复用现有能力，不另造 Agent

复用：

- `kernel.live_agent.provider`：真实模型和原生 Tool Call；
- `LiveAgentRunner`：observe once、freeze intent、fork branches；
- `XaGuardSUT(live=True)`：真实 stdio MCP；
- OAR world/oracle/ledger：独立业务状态和 harm 判定；
- `workbench.py`：现有 stdlib 本地 server/API/HTML；
- `authenticity.py`：证据真实性验证；
- Console：身份、审批、effect、Undo。

不得使用 `GullibleSeat` 作为主演示的“真实 Agent”证据。

#### WP3.2 事件模型与运行状态机

状态机：

```text
IDLE
→ MODEL_REQUESTED
→ MODEL_RESPONDED
→ INTENT_FROZEN | MODEL_SELF_DEFENSE
→ NULL_RUNNING
→ NULL_COMPLETE
→ GUARD_RUNNING
→ PENDING_APPROVAL | GUARD_COMPLETE
→ VERIFYING
→ COMPLETE | FAILED
```

每个事件至少包含：

- run_id、timestamp、event_type；
- model/provider/version/temperature；
- commit、scenario/tool-schema/policy/world hash；
- ToolIntent hash；
- branch、actual downstream call count；
- actual Gate result 或 `NOT_REACHED`；
- business before/after digest；
- audit record hash；
- LIVE RUN / SEALED REPLAY 标识。



#### WP3.3 本地 API

本轮只定义并验证接口契约，不实现 HTTP handler 或网页。交给负责人后续 GUI 使用的计划接口：

- `POST /api/live/preflight`
- `POST /api/live/run`
- `GET /api/live/runs`
- `GET /api/live/events?run_id=...`
- `GET /api/live/artifact?run_id=...`
- `POST /api/live/verify`
- `POST /api/live/verify-tampered-copy`

契约要求：

- 默认只绑定 `127.0.0.1`；
- 不通过 API 返回 API key、环境变量、原始敏感 payload；
- run 目录必须在允许的 runtime 根目录下，防止路径穿越；
- 长任务预留事件流或轮询语义；
- 进程退出、超时和模型拒绝均有真实状态，禁止伪造成功。



#### WP3.4 GUI 布局

本轮只交付 Markdown/ASCII 线框、字段映射和素材位置，不创建 HTML/CSS/React 或其他 GUI
实现。供负责人后续实现的单屏 1920×1080 布局：

```text
┌ Run metadata ─ model / commit / scenario / LIVE ───────────────┐
├ Agent transcript ──────────┬ Frozen ToolIntent + SHA ──────────┤
├ Null branch                │ XA-Guard branch                    │
│ business before/after      │ Gate rail + decision               │
│ downstream calls           │ business before/after              │
│ harm oracle                │ downstream calls + audit            │
├ Causal delta ─ only SUT changed / harm 1→0 / calls 1→0 ───────┤
└ Verifier ─ manifest / hashes / audit / verdict / tamper result ┘
```

视觉规则：

- 红色只表示真实 deny/harm/failure；
- 绿色只表示真实 allow/success/verified；
- 灰色表示 NOT_REACHED/UNKNOWN；
- model self-defense 使用独立蓝色状态，不算 Guard win；
- 不把 sealed replay 标为 live；
- 所有关键数字可点击定位到 artifact。



#### WP3.5 演示场景

1. **D2 主攻击**：使用已有稳定攻击族，真实模型生成 ToolIntent；
2. **安全正例**：同模型、安全业务请求，Null/Guard 都成功；
3. **HITL**：高风险但可批准任务，等待 Dora 独立审批；
4. **D1 修复证明**：旧 v1 失败封存结果与新 v2 执行前阻断并列，明确 before/after；
5. **证据篡改**：只篡改复制包，原包不动。

退出门 G3：

- 事件 JSON Schema 和 example 能被标准 JSON parser/schema validator 验证；
- D2、安全正例、HITL、D1 before/after、tamper 五类素材映射完整；
- 每个计划展示字段都有真实 artifact 来源或明确标为 `synthetic_example`；
- LIVE/SEALED/NOT_REACHED、颜色和错误状态规则无歧义；
- 没有新增任何实际 GUI 代码。



### Phase 4：证据与独立性加强（1–2 个工作日）



#### WP4.1 新 evidence pack

新包必须包含：

- experiment manifest；
- provider/model/config 摘要；
- prompt/scenario/tool schema/policy hashes；
- transcript；
- canonical ToolIntent；
- A/B world before/after；
- downstream call ledger；
- XA-Guard audit；
- verdict、harm oracle、causal delta；
- artifact hash manifest；
- verifier result；
- 自包含 replay。

公开版本必须脱敏，原始模型输入、攻击 payload、API key 和本机路径不入 Git。

#### WP4.2 独立盲测

真正“独立”需要：

- 由未参与实现/调参的人提供或封存；
- 实现者在冻结前看不到 holdout payload；
- 明确许可证或原创权；
- 预注册样本数、成功条件、timeout/retry；
- 同时报告 attack attempt、conditional block、harm、utility、FPR 和区间。

如果只由本团队或子代理生成，只能称“segregated/internal holdout”，不得称独立第三方盲测。

#### WP4.3 Gate5 live evidence

在支持 Docker/runc/runsc 的正式环境执行：

- 安全任务在受限沙箱内成功；
- 网络禁用、只读根、资源限制等至少一项真实触发；
- 没有运行 Gate5 的环境明确显示 disabled/not available；
- 不用 mock 结果冒充 live sandbox。

退出门 G4：

- 新包 verifier PASS；
- 负结果、重试、infra error 全部保留；
- 独立性标签准确；
- Gate5 仅在实际启用时计入六层 live 证据。



### Phase 5：D3/GUI 交接材料与答辩同步（0.5–1.5 个工作日）



#### WP5.1 8:50 镜头计划


| 时间        | 画面                               | 唯一要证明的结论                          |
| --------- | -------------------------------- | --------------------------------- |
| 0:00–0:35 | 真实问题与六层架构                        | XA-Guard 位于 Agent 与工具之间           |
| 0:35–0:55 | 实际 OpenCode                      | 第三方客户端可通过 XA-Guard MCP 安全调用       |
| 0:55–3:40 | Live Workbench D2 A/B            | 同一 ToolIntent 下 XA-Guard 阻止真实业务损害 |
| 3:40–4:20 | 安全正例                             | 不是 deny-all                       |
| 4:20–5:40 | HITL + Dora                      | 高风险操作由独立人批准且绑定 exact hash         |
| 5:40–6:40 | Console + Undo                   | 身份、职责分离、effect 和补偿闭环              |
| 6:40–7:25 | D1 before/after + AIBOM/Gate5 边界 | 展示修复与供应链能力，不隐瞒边界                  |
| 7:25–8:15 | verifier/tamper                  | 证据可独立重算且防篡改                       |
| 8:15–8:50 | 指标与限制                            | 数字来源、模型自防、适用边界准确                  |




#### WP5.2 录制真实性交接清单

本轮只准备下列要求、逐镜操作说明和素材路径，由负责人后续录制：

- 实际 GUI/TUI 连续录屏，不用重构终端冒充；
- 允许剪辑等待时间，但必须保留 run_id、时间线和 artifact 连续性；
- “LIVE RUN”和“SEALED REPLAY”始终有屏幕标识；
- 旁白不能说 OpenCode 攻击由 Guard 拦截，除非真实发生；
- 删除“不是静态脚本”等与画面事实冲突的措辞；
- D3 总时长、编码、字幕、响度和 hash 再验收。



#### WP5.3 D1/QA/数字同步

仅在新证据封存后更新：

- D1 结果和边界；
- D3 脚本、旁白、字幕；
- FROZEN-NUMBERS；
- CODE-MAP、DEFENSE-QA；
- 公开 evidence summary。

所有数字必须由 manifest/verifier 生成或直接引用，禁止手工抄写后无来源。

退出门 G5：

- 8:50 分镜、逐镜操作步骤、旁白边界和素材清单齐全；
- 每个计划声明都预先映射到代码、test 或 artifact；
- 交接说明能让负责人区分真实客户端、真实 Agent A/B、封存回放和边界；
- 本轮不生成、不替换正式 MP4，也不把“计划画面”写成已录制事实。



### Phase 6：提交前收口（0.5–1 个工作日）

动作：

- 统一根 README、`docs/README.md`、TODO/NEXT、Delivery、submission checklist；
- 在干净 checkout 运行支持环境全量测试；
- 单独记录 OPA/gmssl/Docker/Helm 等 capability；
- 构建并验证 D1/D3；
- 生成 final release manifest；
- 审核第三方依赖、字体、截图、TTS、模型输出和素材授权；
- 人工确认 D4、参赛资格、团队/导师、知识产权；
- 向组委会确认疑似模板错位的邮件主题；
- 负责人完成上传、邮件、报名系统和回执保存。

本阶段不自动执行任何外部提交动作。

退出门 G6：

- clean checkout 可复现；
- 无未解释 test failure；
- release manifest 与最终 commit 对应；
- 外部链接权限经无登录或指定账号验证；
- 所有人工合规项有负责人勾选和回执。



## 6. 测试与验收矩阵



### 6.1 必增测试

计划新增而非弱化既有测试：

- `test_provenance_envelope.py`
- `test_reference_resolver.py`
- `test_pre_execution_egress.py`
- `test_operator_plane_separation.py`
- `test_approval_revalidation.py`
- `test_gate_failure_policy.py`
- `test_tenant_effective_overlay.py`
- GUI handoff JSON Schema/example 解析与一致性验证（不新增 GUI 产品测试）

文件名可在实现时按现有目录规范调整，但测试语义不能减少。

### 6.2 分层验证

1. 单元：schema、binding、resolver、Gate、approval、event；
2. pipeline：executor call count、deny/HITL/allow、重验证；
3. MCP：stdio 和 HTTP 的 tools/list、call、operator 分离；
4. OAR：Null/live XA-Guard 同 intent fork；
5. Console：Alice/Dora/Worker 身份与 Undo；
6. evidence：原包、缺文件、改 hash、改 verdict、改 audit；
7. GUI 交接材料：schema、样例、字段来源、状态映射、NOT_REACHED；
8. full suite：支持环境全量；
9. 现有 media：只复核时长、编码和 hash，不录制或替换。



### 6.3 红线

- 不把环境失败改成 pass；
- 不因测试难跑而增加永久 skip；
- 不删除 D1 旧失败；
- 不用 forced tool call 作为真实 Agent attack attempt；
- 不用 UI 文字替代业务 ledger/harm oracle；
- 不在证据包外手工写入最终 verdict；
- 不在失败后改 payload 再覆盖同一 run_id。



## 7. 风险与停止条件


| 风险                     | 处理                                  | 停止条件                              |
| ---------------------- | ----------------------------------- | --------------------------------- |
| 子代理模型选择漂移             | 已按负责人决定统一使用 `gpt-5.6-terra / medium` | 后续新增子代理继续保持同一配置                |
| MCP 无法天然携带完整会话         | 使用可信 Adapter/Envelope，明确普通 MCP 降级边界 | 无法建立信任边界时不宣称 verified provenance  |
| D1 修复导致 deny-all       | 强制 PUBLIC/只读正例                      | 正例失败则 G1 不通过                      |
| live 模型自防/波动           | 如实记 MODEL_SELF_DEFENSE，使用预注册重复      | 不通过 forced tool call 制造 attempt   |
| approval 与 Agent 未真正分权 | 独立 endpoint/identity                | 同 Agent 可批则 G2 不通过                |
| Gate4-out 仍被当成副作用阻断    | 增加 executor call counter            | downstream 已执行却宣称 prevented 时停止发布 |
| Workbench 从结果反推 Gate   | 只读实际 audit/event                    | 无 artifact 来源的状态不渲染               |
| 新依赖许可不清                | 优先 stdlib；新增前许可审核                   | 许可不清不引入                           |
| 测试本身疑似错误               | 记录最小复现并请求负责人审核                      | 未批准不改测试                           |
| dirty worktree 冲突      | preserve list、逐文件所有权、最小 diff        | 无法安全隔离时停止并报告                      |




## 8. 预计投入与并行顺序

```text
负责人批准 + 模型确认
  ↓
Phase 0（根代理，契约冻结）
  ↓
┌ 子代理 A：provenance/resolver ┐
│ 子代理 B：HITL/error/policy   │  Phase 1/2 可部分并行
│ 子代理 C：Workbench contract  │
└ 根代理：pipeline/upstream 集成┘
  ↓
G1/G2 产品安全验收
  ↓
子代理 C + 根代理：非 GUI 契约、线框、分镜与交接材料
  ↓
G3 交接材料验收；实际 GUI 由负责人后续实现
  ↓
新 evidence / Gate5 / 独立盲测
  ↓
D3 重录、D1/QA 同步
  ↓
clean checkout + 人工合规 + 外部提交
```

预计 8–12 个专注工作日；模型服务、Docker/OPA 支持环境、独立盲测提供者和人工合规确认不计入
纯编码时间。任一 Gate 未通过都不得提前进入“最终视频/最终提交”状态。

## 9. 负责人审核清单

请负责人在批准时明确：

- [x] 同意先修产品 P0，再开发/重录 Workbench；
- [x] 同意保留并公开说明 D1 v1 真实失败；
- [x] 同意 OpenCode 只作为互操作锚点，不再赌越狱；
- [x] 同意 Reference Office Agent 的因果 A/B 方法；
- [x] 同意审批控制面与 Agent 工具面分离；
- [x] 同意新增测试但不弱化既有测试；
- [x] 同意旧 holdout 永不覆盖，新结果使用 v2；
- [x] 确认子代理模型准确标识，或批准替代模型； 不用luna了换terra也行，effort选medium
- [x] 确认是否把 tenant overlay 与 Gate5 live evidence 纳入本轮 P0/P1；
- [ ] 确认独立盲测由谁提供/封存（本轮仍无独立提供方）；
- [x] 本轮未提供模型 API key，因此不产生新的付费模型调用；
- [x] 确认最终视频重录前需要一次中期 GUI 审核。

负责人已批准执行；当前完成度与剩余门禁以本文 0.1 节和根 `status.md` 为准。
