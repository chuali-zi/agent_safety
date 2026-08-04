# GUI 实现与真实 v2 录制交接清单

> 本文件只交接已经完成的安全后端、数据来源和后续操作顺序。它不包含 GUI 代码，
> 正式 v2 的 D1/D2 因果包已于 2026-08-03 完成；它不表示专用 PUBLIC 正例、真人审批录屏或
> 新 D3 已完成。

## 1. 负责人可直接复用的后端

| 能力 | 代码/端点 | 当前证据 |
|---|---|---|
| Agent MCP | Streamable HTTP `/mcp`；stdio 正式入口 | Agent 工具面隐藏审批工具；定向单测通过 |
| Operator MCP | Streamable HTTP `/operator/mcp` | 独立 manager、共享 pending、身份/role/tenant/SoD 校验；定向单测通过 |
| 可信上下文 | `src/xa_guard/provenance.py`、`proxy/upstream.py` | HMAC、TTL、nonce、tool/args/history/identity 绑定；产品集成测试通过 |
| OAR Adapter | `open-agent-range/kernel/sut.py`、`live_agent/runner.py` | OAR wire envelope 已被产品解析器交叉验证 |
| 引用 DLP | `gates/gate4_taint.py` | `sources/attachments/records`：敏感/未知 external egress 执行前拒绝，PUBLIC 正例允许 |
| HITL 重验证 | `pipeline.py`、`proxy/operator.py` | approval 绑定、Gate1–4 重评、一次消费、漂移/过期/自批/毒化回归 |
| GUI 数据契约 | `schemas/*.json`、`contracts.md` | schema 与合成样例仅供开发；不是实跑数据 |

尚不存在：`/api/live/*` handler、实时事件总线、Workbench GUI、正式 GUI 自动化测试。

## 2. 支持环境的安全配置

正式演示环境至少注入下列值；不要把值写进仓库、命令历史、截图或 event：

```text
XA_GUARD_PROVENANCE_HMAC_SECRET
XA_GUARD_PROVENANCE_HMAC_KEY_ID
XA_GUARD_APPROVAL_OPERATOR_TOKEN
XA_GUARD_APPROVAL_SECRET
```

同时使用启用 identity 的配置，给 Agent 与 Operator 分配不同的
`human_principal/agent_id`，Operator 角色必须包含 `xa_guard.operator`，tenant 必须匹配。
若 identity、Operator token 或可信 provenance key 缺失，演示应显示 fail-closed，不应临时
关闭检查。

当前 approval/provenance replay store 是单进程内存状态：录制时使用单 worker；不要宣称
跨重启、多实例全局一次性。重启后缺少可重验证 identity/provenance/history 的 pending 必须
重新发起。

## 3. GUI 接线纪律

1. GUI 只消费真实 artifact/event；`examples/synthetic-d2-events.json` 始终显示
   `EXAMPLE / SYNTHETIC`。
2. Agent 和 Operator 使用不同登录会话、不同 MCP endpoint；Operator token 走
   `X-XA-Guard-Operator-Token` header，不做表单字段或 MCP argument。
3. 每个按钮动作保留 `run_id/trace_id`；UI 不自行判定 allow/deny/harm。
4. Gate rail 只呈现实际 audit/event：前置终止为 `NOT_REACHED`，证据缺失为 `UNKNOWN`。
5. pending→approve 后，必须显示新的 span/audit、重验证结论和真实 downstream counter；
   不只把 pending 卡片改成绿色。
6. A/B 的 tool、canonical args hash、world-before hash 任一不同，立即显示
   `INVALID_COMPARISON`，不计算因果差。
7. 屏幕上只显示脱敏参数与 digest；原始 API key、攻击 payload、敏感资产正文和本机绝对
   路径不进入 DOM、console 或录屏。

## 4. 真实 v2 运行顺序

2026-08-03 已在负责人明确授权合成场景外发后，于沙箱外完成正式 v2 D1/D2 运行；受限沙箱
本身仍不能创建 stdio 匿名管道。以下步骤保留为复现和补齐专用 utility/HITL 的操作顺序：

1. 新建 v2 manifest/目录，不修改 `.runtime/live-agent/holdout-v1`。
2. 预先冻结 case、prompt、tool schema、policy、model config、重复数和成功条件。
3. 先运行 `check`，确认 key 与模型配置；失败就停止，不用 forced tool call。
4. 运行一次真实模型观察并冻结 ToolIntent；Null/XA-Guard 两臂复用同一 intent/world。
5. D1 修复与 D2 已完成；继续运行专用安全正例与 HITL。模型不调用时记
   `MODEL_SELF_DEFENSE`。
6. 封存 artifact hash，运行 verifier；只对复制包做 tamper。
7. GUI 读取该 v2 包；旧 v1 只作为 `SEALED REPLAY / historical negative result`。

命令形状（路径由负责人换成新 v2，不要覆盖旧包）：

```bash
cd open-agent-range
PYTHONPATH=. python -m kernel.live_agent.cli check \
  --manifest <new-v2-manifest> --env-file <private-env-file>
PYTHONPATH=. python -m kernel.live_agent.cli freeze \
  --manifest <new-v2-manifest> --phase holdout --out <new-v2-freeze>
PYTHONPATH=. python -m kernel.live_agent.cli evaluate \
  --manifest <new-v2-manifest> --phase holdout \
  --evidence-dir <new-v2-evidence-dir> --env-file <private-env-file> \
  --guard live --xa-guard-root ..
PYTHONPATH=. python -m kernel.live_agent.cli verify \
  --evidence-dir <new-v2-evidence-dir>
```

## 5. 录制前必须拿到的五张“真凭证”

- D1 v2：**已取得**；neutral-tool 5/5 Guard deny/harm=0，并列保留 v1 失败。
- 安全正例：Null/Guard 均成功、downstream=1。
- D2：**已取得**；两档 10/10 同一 ToolIntent/world，Null harm=1、Guard deny/harm=0。
- HITL：Alice/Agent pending，Dora 独立批准，exact-hash 执行一次，replay 拒绝。
- verifier：**已取得**；原 v2 包 22/22 PASS，篡改复制包 FAIL。

任一项未取得真实工件，就从正式旁白中删除对应“已经证明”措辞。
