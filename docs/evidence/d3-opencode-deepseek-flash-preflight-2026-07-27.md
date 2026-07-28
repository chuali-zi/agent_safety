# D3 真实 Agent 客户端预演：OpenCode + DeepSeek Flash + XA-Guard MCP

> 状态：**PASS**
> 本地日期：2026-07-27（UTC 证据时间为 2026-07-28）
> 用途：闭合 D3-P0-1 的“真实客户端工具发现 + 一次实际调用 + 可回溯 Gate 状态”验收项。
> 安全边界：本预演只调用无副作用的脱敏 CPU 查询，不包含攻击 payload、攻击脚本、凭据或真实运维动作。

## 1. 隔离条件

- 客户端：OpenCode `1.18.5`。
- 模型：`deepseek/deepseek-v4-flash`。
- MCP：仅启用 `xa_guard_l3_http`，地址为本机 XA-Guard HTTP MCP。
- 客户端权限：全局 deny，仅显式允许本次无副作用 CPU 查询工具。
- 配置、数据和缓存目录均指向仓库外临时目录，不继承用户全局 MCP 配置。
- API key 只在进程启动时从 gitignored `.env` 读取；不写入配置、日志或本证据。

## 2. 实际观测

| 验收点 | 观测结果 |
|---|---|
| 工具发现 | `opencode mcp list` 显示恰好 1 个服务：`xa_guard_l3_http connected` |
| 模型调用 | 模型发出 1 次 `xa_guard_l3_http_get_cpu` Tool Call |
| 脱敏参数 | `host=web03` |
| 脱敏结果 | `host=web03, cpu=85%` |
| XA-Guard 最终决策 | `allow` |
| Gate 结果 | 6 个 Gate 结果齐全，命中规则数 0 |
| 决策忠实度 | `1.0`，basis=`all_gates_allow` |
| 审计完整性 | 1 record verified，0 chain/hash、JSON、字段、anchor、signature error |
| trace | `9eb1b0fe-dd15-41a9-8a24-a4b366fee03d` |
| record hash | `f17810ab1b494a9e28cff1231fba2e9374699d91ff0210cda48e53713a7a725d` |

该结果证明真实 Agent 客户端完成了 MCP 工具发现、模型原生 Tool Call、XA-Guard 裁决、
下游脱敏返回和 Gate6 审计闭环。它不是静态 JSON 演示，也不用于证明任何攻击阻断率。

## 3. 本地原始证据与哈希

原始证据保存在 gitignored 的
`.runtime/d3-opencode-preflight-20260727-r5/`。公开仓库只提交本脱敏摘要，不提交配置、
JSONL、服务日志或可能泄露本机状态的绝对路径。

| 文件 | SHA-256 |
|---|---|
| `mcp-list.txt` | `b3a12666a8e30c9a692252d7f3fcf5b9bf5bd66f1b3cd7cd3306994ce2a083a3` |
| `opencode.json` | `8054c369efd86570ebae40665ccbbba8b647483370192445aa66d2df1f46393d` |
| `run.jsonl` | `9bf32ca61dd5517c32ed8ae99a357b1a904e9acc4d7cd1323c2b24315e5f884e` |
| `xa-guard.yaml` | `78e8d433c524654f8d01ca0c543df219989a711b316d87ea57027c0f3079e81a` |
| `audit/audit.jsonl` | `b67299ad5b324543481b0657eafb07c04f4501369eaeea3ac3d236109adc0a72` |
| `verify-audit.txt` | `43d13bf7dc969f504120bdc27480840ea1134c9678289ec4f6d8fe845ef4070b` |

复核时应先按上表核对逐文件哈希，再检查：

1. MCP 列表只有一个 XA-Guard 服务；
2. 运行流中只有一个 completed Tool Call；
3. Tool Call 输入、输出与 Gate6 参数/结果哈希一致；
4. `verify_audit.py` 报告 1 record、0 error；
5. trace ID 和 record hash 与本摘要一致。

## 4. 不声明事项

- 不把安全 CPU 查询写成攻击实验或高风险动作。
- 不把本地 MCP 连接写成 OpenCode 专有集成；XA-Guard 验证的是标准 HTTP MCP 协议面。
- 不把一次客户端预演外推为可用性或性能统计。
- 不公开 `.env`、API key、完整 OpenCode 配置、原始日志或本机绝对路径。
