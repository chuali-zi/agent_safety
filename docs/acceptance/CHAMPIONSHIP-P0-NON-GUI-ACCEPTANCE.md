# XA-Guard 冲刺 P0 非 GUI 验收报告

> 日期：2026-07-30
> 范围：P0 安全后端、OAR 可信适配、受控集成测试与 GUI/D3 交接材料
> 不在范围：实际 GUI、录屏、正式 D3 替换、付费模型 v2、Gate5 live、外部提交

> **后续状态（2026-08-03）**：本报告的 2026-07-30 验收事实不改写；正式真实模型 v2 已在
> 新目录完成。D1 neutral-tool 5/5 与 D2 两档 10/10 均为 Null harm、XA-Guard live deny/0 harm，
> 0 infra，verifier 22/22 PASS。详见
> [`live-agent-holdout-v2-2026-08-03.md`](../evidence/live-agent-holdout-v2-2026-08-03.md)。专用 PUBLIC
> 正例、独立 Operator HITL live、Gate5、GUI/D3 和 clean release 仍未完成。

## 1. 结论

**受控非 GUI P0：通过。比赛最终发布门：未通过。**

本轮已经把原先“真实 MCP 主线缺来源、D1 `sources` 引用绕过、Agent 可接触审批、批准后
不完整重验证、tenant overlay 串租户、写操作 Gate 异常可继续”的主要 P0 缺口落实为产品
代码和受控回归。最关键的因果断言已经在真实 Pipeline/MCP handler + 假下游计数器中成立：

- verified `CONFIDENTIAL` 引用：执行前 deny，downstream=0；
- verified `PUBLIC` 引用：allow，downstream=1；
- unknown/tampered provenance：deny，downstream=0；
- 高风险 pending：独立 Operator 准许后重跑治理与 Gate1–4，再执行一次；
- 身份、tenant、history、provenance、taint、policy、effect 任一漂移：不执行；
- 非法 Operator 尝试不能消费或污染 pending；
- provenance 在等待期间过期：即使 approval 尚有效也不能执行；
- 重启后无法重验 identity/provenance/history：要求重新发起。

尚未生成新的真实外部模型 v2 evidence，因此不能把上述受控集成结论表述为“D1 已经被真实
Agent live 实战证明修复”。

## 2. 已完成工作包

| 工作包 | 完成事实 | 主要证据 |
|---|---|---|
| Trusted Context Envelope | HMAC、TTL≤15 分钟、时钟偏差、tool/args/history/identity、nonce；普通 MCP 明确为 `UNKNOWN` | `src/xa_guard/provenance.py`、`proxy/upstream.py` |
| Schema-aware Resolver / DLP | `sources/attachments/records` 解析；敏感/未知 external egress 执行前拒绝；PUBLIC 正例允许 | `gates/gate4_taint.py`、`test_trusted_provenance_mcp.py` |
| Gate6 provenance | 只落 digest、分类、resolution、nonce digest；不落 MAC 或资产正文 | `gates/gate6_audit.py`、`test_gate6_provenance_audit.py` |
| OAR trusted adapter | OAR 不 import 产品；本地生成产品兼容 canonical HMAC，绑定冻结 intent/session/history，只传 source digest | `open-agent-range/kernel/sut.py`、`live_agent/runner.py` |
| HITL binding/revalidation | token 绑定身份、tenant、provenance/history/taint/policy/effect/nonce；治理与 Gate1–4 重评；单次消费 | `pipeline.py`、`approval.py` |
| Operator 分权 | Agent `/mcp` 与 Operator `/operator/mcp` 分离；共享 pending；role/tenant/token/SoD/理由校验 | `proxy/operator.py`、`proxy/upstream.py` |
| Pending 安全恢复 | 不落 session history 正文；可信上下文无法重验时 fail-closed；敏感参数恢复项不执行 | `proxy/pending.py` |
| 错误策略 | read-only 最低 WARN；local write 最低 HITL；external/privileged 固定 DENY；配置不能降级安全下限 | `gates/base.py`、`gate1_input.py` |
| Tenant view | Gate2/3/4 按当前 tenant 取 baseline+单一 overlay；effective bundle SHA 分租户 | `policy/layered.py` |
| GUI/D3 材料 | schema、合成样例、线框、8:50 分镜、素材/claim/录制/实现交接；没有 GUI 代码 | `docs/demo-handoff/` |

本轮未增加第三方运行依赖；新增安全实现使用 Python 标准库和仓库既有依赖。

## 3. 审查中发现并修复的阻断问题

1. **Pending 毒化**：非法自批/错租户/空理由曾会直接在共享请求 ctx 上 append DENY，
   使后续合法审批永久失败。现改为独立、无业务参数的审计 ctx，并有“非法尝试后 Dora 仍可
   批准执行”的回归。
2. **过期 provenance 恢复**：approval token 仍有效时，等待期间过期的 provenance 曾可继续
   被 Gate4 当可信引用使用。现恢复前、Gate1–4 重评后均检查新鲜度及请求绑定。
3. **重启降级**：pending ledger 不持久化 provenance，却可能恢复执行。现对存在 verified
   identity/provenance/history 的恢复项强制重新发起，且 ledger 不写 history 正文。
4. **异常策略可降级**：管理员配置曾能把 external-write Gate error 设为 allow。现硬性限制
   每类 effect 的最低安全决策；Gate1 意外 detector crash 也进入该矩阵。
5. **统计错误**：tenant overlay 的 accepted 计数曾重复减去 rejection，现按实际已接受
   snapshot 计数。

## 4. 本轮实际验证

### 4.1 P0 主验收

```text
80 passed
```

覆盖 provenance/reference DLP、HITL 绑定/漂移/过期/replay、Operator 分权/毒化/重启恢复、
Gate6 provenance、真实 MCP handler 集成、OAR wire contract 和 full-gate stress。

### 4.2 OAR 非基础设施契约

```text
10 passed, 1 deselected
```

通过项覆盖进程会话复用的 fake live session、OAR envelope/引用解析、surfaced channels、
冻结 ToolIntent 与模型历史绑定、A/B hash/summary/render。被排除项是本环境会挂起的真实
XA-Guard MCP subprocess，不记为通过。

### 4.3 更广泛批量回归

| 测试组 | 结果 |
|---|---|
| AIBOM/bench/audit/config | 199 passed, 1 skipped |
| control 核心（排除会挂起的 TestClient 文件） | 51 passed |
| Gate1–5 | 171 passed；另 4 个 OPA capability failure |
| Gate6/provenance | 13 passed；另 2 个缺 `gmssl` failure |
| L3/layered/OPA export/OpenCode bridge | 84 passed |
| P0/operator/pending/resilience/server/crypto 等 | 95 passed, 13 skipped |
| changed Python lint | Ruff: all checks passed |
| GUI schema/sample | 2 个 JSON Schema 合法；4 个 synthetic events 通过验证 |

这些组有重叠，不能相加冒充“全量总通过数”。

### 4.4 冻结交付物复验

- D1 SHA-256：
  `de37a83c973d28f1b4efdc77efda4648a704db94540cb9839b6f4d2e8660c7f1`
- D3 SHA-256：
  `267a1a59f7f48c9d8e489f085afda0ff79197118ceff7b7e2d5422d5962b00c5`
- 旧 `holdout-v1` authenticity：`ok=true`；303 files；30/30 verdict；15/15 audit；
  metrics、stability、causal proof 全部重算一致。

旧 evidence 未被覆盖。

## 5. 未通过/未运行及原因

| 项 | 本次事实 | 不能据此声称 |
|---|---|---|
| OPA 4 项 | 仓库是 Windows `tools/opa/opa.exe`；WSL 报 `UtilBindVsockAnyPort ... socket failed 1` | Rego 支持环境全绿 |
| strict SM2 2 项 | 可选 `gmssl` 未安装 | 当前环境真实 SM2 可签验 |
| Business API 3 项 | 沙箱禁止创建 `127.0.0.1` socket，`PermissionError` | Business API socket 集成通过 |
| 部分 Starlette TestClient | reference KMS / worker health /部分 identity 用例在本环境挂起 | 全量 unit suite 完成 |
| MCP subprocess | OAR live 与产品 base stdio smoke 均会挂起 | 真实 stdio 串接通过 |
| Streamable HTTP 实传 | 当前仅完成 ASGI factory/共享 store/路由构造和 service tests | 双端点网络实传通过 |
| 外部模型 v2 | `DEEPSEEK_API_KEY` 未配置；本轮 0 次付费调用 | D1 v2 live 已完成 |
| Gate5 live | 未在 Docker/runc/runsc 支持环境开启 | 六层在同一 live 链路全部生效 |
| GUI/D3 | 按负责人要求只准备材料 | Workbench/D3 已完成 |

未改旧测试、payload、oracle、阈值或 frozen evidence 来制造绿色。

## 6. 对外 claim 边界

### 可以说

> XA-Guard 已在受控 MCP 集成中验证可信 provenance 与业务引用解析：敏感或未知 external
> egress 在 executor 前拒绝且 downstream=0，PUBLIC 引用保持可用。独立 Operator 后端、
> 绑定审批与批准后重验证已有代码和确定性回归。

> OAR 与产品已完成可信上下文 wire contract；旧 D1 v1 失败永久保留，新产品修复等待支持
> 环境的真实外部模型 v2 封存验证。

### 不能说

- OpenCode 攻击已经被 XA-Guard 阻断；
- D1 v2 已由真实外部模型或 GUI 实战证明；
- Gate1–6 已在同一 live 链路全部运行；
- 真人 Dora/OIDC 连续审批已经录制；
- 独立第三方盲测、100% 防御、任意 Agent 通用；
- 跨进程/多实例全局 nonce 防重放；
- 生产级 HSM/TSA/HA；
- 最终提交、D4、资格和知识产权人工审查已完成。

## 7. 剩余门禁

负责人后续应按 `docs/demo-handoff/IMPLEMENTATION-HANDOFF-CHECKLIST.md` 完成：

1. 在支持环境复验真实 stdio 与 HTTP `/mcp` + `/operator/mcp`；
2. 新建而非覆盖 v2 manifest/evidence，运行 D1 修复、安全正例、D2 与 HITL；
3. 开启并封存 Gate5 live，或在画面明确 `DISABLED/NOT REACHED`；
4. 实现 GUI 并连续录制；所有字段直接读 artifact/event；
5. 运行原包 PASS / tampered copy FAIL；
6. 在 clean checkout 完成全量能力矩阵与 release manifest；
7. 人工完成 D4、资格、IP/素材授权和外部提交回执。
