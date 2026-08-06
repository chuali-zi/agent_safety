# 独立 HTTP Operator HITL live 准备说明

> 状态：`STATIC PREPARATION PASS / 2026-08-05 LIVE PASS`
>
> 日期：2026-08-04

> 后续事实（2026-08-05）：合成凭据已生成，真实双 HTTP 平面 live 已完成；16/16 checks、
> 原包 verifier PASS、篡改副本 FAIL。详见
> [`http-operator-hitl-live-2026-08-05.md`](../evidence/http-operator-hitl-live-2026-08-05.md)。
> 下文保留 2026-08-04 准备阶段的历史事实和冻结契约，不再代表当前 live 状态。

## 1. 本轮完成到哪里

本轮只完成负责人要求的“先准备”，没有启动 HTTP server，没有发 Agent/Operator MCP 请求，
没有产生 pending、批准、下游执行或 replay 结果，因此不得写成 HITL live PASS。

已冻结以下文件：

- 场景 manifest：`open-agent-range/scenarios/live-agent/http-operator-hitl-v1.json`；
- server 模板：`configs/xa-guard.http-operator-hitl-live.template.yaml`；
- credential/static preflight：`python -m kernel.live_agent.http_operator_hitl`；
- 单次执行计数靶子：`demo.targets.http_hitl_target`。

静态检查 12/12 PASS。当前 `.env` 缺少五项 HTTP identity/HITL 专用输入，credential preflight
按预期退出 2，报告位于 gitignored：

```text
open-agent-range/.runtime/http-operator-hitl/preflight-20260804.json
```

缺少的是环境变量名，不是 DeepSeek Key 问题：

```text
XA_HITL_AGENT_BEARER_TOKEN
XA_HITL_OPERATOR_BEARER_TOKEN
XA_GUARD_APPROVAL_OPERATOR_TOKEN
XA_GUARD_APPROVAL_SECRET
XA_HITL_JWKS_FILE
```

任何 secret、JWT 或私钥都没有写入仓库、manifest、preflight report 或本说明。

## 2. 冻结双平面

| 平面 | URL | 身份 |
|---|---|---|
| Agent | `http://127.0.0.1:18766/mcp` | Alice：`alice.requester@acme.local` / `synthetic-change-agent` |
| Operator | `http://127.0.0.1:18766/operator/mcp` | Dora：`dora.approver@acme.local` / `independent-operator-console` |
| Health | `http://127.0.0.1:18766/healthz` | 只作 server readiness |

Operator 请求除 Bearer JWT 外，还必须在独立 HTTP header
`x-xa-guard-operator-token` 携带 `XA_GUARD_APPROVAL_OPERATOR_TOKEN`；该值禁止进入 MCP arguments。
Agent 平面不暴露 `xa_guard_operator_*` 工具。两平面使用不同 MCP session manager，但共享同一
in-memory pending store。

## 3. 身份输入契约

公共 JWKS 只允许公钥字段，禁止 `d/p/q/dp/dq/qi/oth/k` 私钥或对称密钥字段。两枚 JWT 均须：

- `alg=RS256`，`kid` 在 JWKS 中唯一；
- `iss=https://xa-guard.local/http-hitl`；
- `aud=urn:xa-guard:http-hitl`；
- `tenant_id=acme-corp`；
- scope 含 `xa.invoke`；
- 含 `iat/exp/sub/iss/jti`，TTL 不超过 300 秒。

Alice JWT：

```json
{
  "sub": "alice.requester@acme.local",
  "act": {"sub": "synthetic-change-agent"},
  "tenant_id": "acme-corp",
  "scope": "xa.invoke"
}
```

Dora JWT 的 `sub`/`act.sub` 必须不同，并须含角色：

```json
{
  "sub": "dora.approver@acme.local",
  "act": {"sub": "independent-operator-console"},
  "tenant_id": "acme-corp",
  "scope": "xa.invoke",
  "realm_access": {"roles": ["xa_guard.operator"]}
}
```

preflight 会真实验证 JWT signature、issuer、audience、kid、TTL、scope、tenant、角色和 Alice/Dora
的 principal/agent/JTI 分离；输出中只保留 JWT SHA-256/JTI SHA-256 等摘要。

## 4. 冻结场景与执行计数

Agent 只能提交合成工具：

```json
{
  "tool_name": "pending_approval_op",
  "arguments": {
    "operation": "rotate synthetic staging signing key",
    "change_ticket": "SYNTH-HITL-2026-0804"
  }
}
```

参数 SHA-256：

```text
3f0ccc855b526ca683a796d89469cb3e2d356867caef175e06c829ca2baadae0
```

`pending_approval_op` 已在 Gate2 登记为 red、在 Gate4 登记为 `AUTHZ_ADMIN`，且不会被 Gate3
另一条 deny 规则抢先终止，故正常路径应进入 pending。专用 downstream 不执行真实管理动作；
它只在真正收到一次批准后的调用时，向 `XA_HITL_TARGET_LEDGER` 指定的 gitignored JSONL 写一条
`execution_id + arguments_sha256 + timestamp + simulated=true`。这样可证明：

- 初始 pending 时 ledger 仍为 0；
- Dora 批准后恰好为 1；
- 同 trace replay 后仍为 1。

## 5. 下一次 live 的强制顺序

1. 新建 evidence 目录，禁止复用/覆盖任何旧 run。
2. 运行 credential preflight，非 0 不启动 server。
3. 把模板的 JWKS/audit/pending placeholder 渲染为该 run 的绝对路径；只复制公共 JWKS。
4. 启动 `python -m xa_guard.server --config <rendered-config>`，等待 `/healthz`。
5. Alice Bearer session 连接 `/mcp`：确认 Operator 工具不可见，调用冻结工具一次。
6. 断言返回 pending trace，target ledger=0。
7. Dora 使用另一 Bearer session + Operator header 连接 `/operator/mcp`：只看到两个 Operator 工具；
   list 中 trace/tool/arguments 与冻结值一致。
8. Dora 提交非空理由批准；断言 response=`allow/approved and executed`，target ledger=1。
9. 对同 trace 再批准一次；必须返回 missing/expired/deny，target ledger 仍为 1。
10. 读取 Gate6 audit：同 trace 至少形成 `require_approval → allow(hitl_approved)`；工具参数完全相同，
    approver 为 Dora，approval 只落摘要，`record_hash` 非空且链可验。
11. 生成 summary/replay/artifact hashes，原包 verifier PASS；复制包篡改后 verifier FAIL。
12. 扫描 JWT、Operator credential、approval secret 和私钥，任一进入证据即整包作废。

## 6. 复现准备命令

从 `open-agent-range/` 执行：

```powershell
python -m kernel.live_agent.http_operator_hitl static-check `
  --manifest scenarios\live-agent\http-operator-hitl-v1.json

python -m kernel.live_agent.http_operator_hitl preflight `
  --manifest scenarios\live-agent\http-operator-hitl-v1.json `
  --env-file ..\.env `
  --out .runtime\http-operator-hitl\preflight-20260804.json
```

当前第一次命令 PASS；第二次因上述五项缺失退出 2。这是可信阻塞，不是 live failure。负责人补齐
短 TTL 合成身份材料后，应先复跑 preflight；在 `ready_for_live_execution=true` 前不得开始 HTTP
live，也不得创建“通过”证据。

## 7. 停止条件与 claim 边界

遇到下列任一情况立即停止并保留失败包：Agent 能看到 Operator 工具、两 JWT principal/agent/JTI
不独立、Operator 无 role 仍可访问、header credential 无效仍可批准、tenant 不一致仍可 list/decide、
pending 前已有执行、批准后不是恰好一次执行、replay 能再执行、audit 参数或 trace 漂移、任何 secret
进入 evidence。

准备阶段当时允许的措辞仅为：**“独立 HTTP Operator HITL 的静态 contract/preflight 已准备，
12/12 PASS；外部 identity/secret 输入未配置，live 尚未运行。”** 该历史措辞已由文首
2026-08-05 后续事实取代。
