# Live Workbench GUI 交接包

**用途**：给后续录制者/GUI 实现者的材料包。它不实现网页、GUI、录屏或正式 D3，也不构成新的实跑证据。

**事实边界（更新至 2026-08-03）**：`open-agent-range/kernel/live_agent` 已能产生真实模型
ToolIntent、冻结参数哈希、Null/XA-Guard 分叉、world/ledger/audit 工件及封存验真。
XA-Guard 已实现独立 `/operator/mcp` 后端、身份/角色/租户校验、自批阻断和批准后重验证；
正式 v2 已完成 D1/D2 真实模型因果包与 verifier；专用 PUBLIC 正例和独立 Operator HITL
仍只有受控测试证据，尚无真人连续录屏。计划中的 `/api/live/*`、实时事件流和
1920×1080 Workbench 仍待负责人实现。所有 `examples/` 内容均为
**SYNTHETIC / EXAMPLE ONLY**，不能截图后称为实跑。

## 阅读顺序

1. [contracts.md](contracts.md)：状态机、API、artifact→UI 映射、状态渲染纪律与场景数据映射。
2. [IMPLEMENTATION-HANDOFF-CHECKLIST.md](IMPLEMENTATION-HANDOFF-CHECKLIST.md)：已完成后端、
   安全配置、GUI 接线纪律和真实 v2 支持环境操作顺序。
3. [layout-and-recording.md](layout-and-recording.md)：1920×1080 线框、8:50 分镜、录制/素材/验收清单。
4. [schemas/live-workbench-event.schema.json](schemas/live-workbench-event.schema.json)：事件 JSON Schema。
5. [schemas/live-workbench-api.schema.json](schemas/live-workbench-api.schema.json)：目标 API 的 request/response Schema。
6. `examples/`：仅用于 UI 开发和人工走查的合成样例。

## 现有真实工件位置（只读引用）

| 目的 | 现有来源 | 关键字段/文件 |
| --- | --- | --- |
| 模型原生 Tool Call 与冻结意图 | `open-agent-range/kernel/live_agent/models.py`、`runner.py` | `tool-intent.json`，`arguments_sha256` |
| 分叉与业务后果 | 每个 run 的 `null/`、`xaguard/` | `world-out.json`、`ledger.jsonl`、`output.json`、`verdict.json` |
| 真实 XA-Guard 审计（仅 live 分支） | `xaguard/xa-guard-audit/audit.jsonl` | decision、reason、hit ids、record hash、faithfulness |
| 封存验证 | `kernel/live_agent/authenticity.py` | `artifact-hashes.json`、`experiment-manifest.json`、`summary.json` |
| 当前封存旧证据 | `.runtime/live-agent/holdout-v1/` | 仅可标为 `SEALED REPLAY`，不得改写 |
| 当前正式 v2 | `.runtime/live-agent/holdout-v2-formal-20260803/`、`docs/evidence/live-agent-holdout-v2-2026-08-03.md` | D1/D2 live causal PASS；0 infra；22/22 verifier |
| 独立审批后端 | `src/xa_guard/proxy/operator.py`、HTTP `/operator/mcp` | 已实现并定向测试；不等同真人 live 证据 |
| 可信上下文与引用解析 | `src/xa_guard/provenance.py`、OAR `kernel/sut.py` | 产品/OAR 合约及 v2 D1 外部模型证据已验证 |

不要从 UI 规则名、预期结果或截图推导 Gate 状态；只能从实际 audit/event 渲染。没有该工件即显示 `NOT_REACHED` 或 `UNKNOWN`。
