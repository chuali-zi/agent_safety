# 独立 HTTP Operator HITL live 脱敏摘要（2026-08-05）

> 分类：`supporting-private-dirty-worktree`
>
> 结论：**HTTP Operator HITL live PASS**。这是本地合成身份和模拟下游的真实双 HTTP
> 平面运行，不是 clean release、真人 GUI 录制、Gate5 live 或外部提交证明。

## 1. 正式运行

正式原始目录（gitignored）：

```text
open-agent-range/.runtime/http-operator-hitl/run-20260805T074229138249Z
```

runner 在开跑前重新签发 TTL 300 秒的 Alice/Dora RS256 JWT；preflight 验证签名、issuer、
audience、kid、scope、tenant、Agent 工具 allowlist、Dora role 和职责分离。JWT、Operator
credential、approval secret 与私钥均未写入证据。

实际 HTTP/MCP 顺序及结果：

| 阶段 | 结果 | 下游累计执行 |
|---|---|---:|
| Alice `/mcp` 调用冻结 red 工具 | `require_approval`，trace `77aa82ab-cb0f-4374-9fc9-132b2a8a1695` | 0 |
| Dora `/operator/mcp` 列出并批准 | `allow` / `approved and executed` | 1 |
| Dora 对同 trace 再批准 | `deny` / pending missing or expired | 1 |

Agent 与 Operator 使用不同 MCP session；Agent 工具列表不含 Operator 工具；Operator 平面只
暴露冻结的 list/decide 两个工具。pending 中的工具、参数和参数 SHA-256
`3f0ccc855b526ca683a796d89469cb3e2d356867caef175e06c829ca2baadae0` 与 manifest 完全一致。
下游仅向本地 JSONL 写一条 `simulated=true` 计数事实，不执行真实管理动作。

## 2. 审计与防篡改

- live checks：`16/16 PASS`；
- Gate6：3 条记录，hash chain 重算 `ok=true`；同 trace 的目标工具记录为
  `require_approval → allow`，参数相同，allow approver 为 Dora，`record_hash` 非空；
- 原包 verifier：`ok=true`，9 个受封存文件 hash 一致；
- 篡改副本：只把 `live-result.json.live_result` 改为 `FAIL`，verifier 按预期拒绝；
- secret scan：JWT、Operator credential、approval secret、私钥标记均未进入证据包。

根文件 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `preflight.json` | `1535346ab5238ef4f4ef2df8a35d940aae73f1dc47061008eabe1b25b75be936` |
| `live-result.json` | `8553b0d2360bcbf26d9bb66855dae6be51ef728269d84c9f4d062a93a64daf7b` |
| `artifact-hashes.json` | `e4d7c615ea2543e1f3a1763613fb6f2e8780ed9a155976b445ff1ac6c7745f44` |
| `verification.json` | `12d47aceb88bed0d54156e13bb42e37567f292f73aaaccfce3bf78c3bf2b5358` |
| `tamper-verification.json` | `ce511f3e17c9b0cf33e62c26d37a4590b8e25c890f30db169e9bc5eaf9559c93` |

## 3. live 暴露并修复的问题

失败包均保留，没有覆盖：

1. `run-20260805T073544244527Z`：受限沙箱禁止 loopback socket，未发生 live 请求；
2. `run-20260805T073646032109Z`：Alice JWT 缺目标工具 allowlist，且 Agent 对外 schema 未声明
   transport-required `_xa_guard` envelope；
3. `run-20260805T073805774188Z`：冻结模板把 red fallback 配成直接 deny；无尾斜杠的精确
   `/operator/mcp` 又落入 Agent root fallback。

修复内容是身份契约、Agent schema、Gate2 live 模板和 HTTP 精确路由，没有修改测试、风险等级、
冻结业务参数、审批 oracle 或执行计数标准。相关定向测试 `41 passed`；另一次含 Gate6 SM2 的
回归为 `37 passed, 2 failed`，两个失败均因本环境缺可选 `gmssl`，与本 live 的 SHA-256/无签名
配置无关。

## 4. 复现

从仓库根目录执行；JWT 只有 5 分钟有效期，因此必须紧接着运行：

```bash
python scripts/generate_http_hitl_synth_credentials.py
PYTHONPATH=src:. python scripts/run_http_operator_hitl_live.py run
PYTHONPATH=src:. python scripts/run_http_operator_hitl_live.py verify \
  open-agent-range/.runtime/http-operator-hitl/run-20260805T074229138249Z
```

运行环境必须允许启动本地子进程和访问 `127.0.0.1:18766`。原始包来自 dirty worktree，只能作为
supporting evidence；发布前仍须在 clean checkout 重跑并把最终 commit 绑定到 release manifest。
