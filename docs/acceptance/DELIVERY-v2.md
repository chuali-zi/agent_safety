# Delivery v2：2026-07-27 历史交付快照

> 状态：**HISTORICAL SNAPSHOT / SUPERSEDED BY ROOT `status.md`**
> 更新：2026-07-27
> 适用：XA-202620《面向政企场景的大模型智能体安全关键技术研究》
>
> 本文保留当时的内部验收事实和冻结交付物 hash，不再代表当前最终发布状态。
> 2026-07-30 的 P0 修复、未完成的 v2 live evidence、GUI/D3、支持环境全量复验和人工
> 外部提交状态，以仓库根 `status.md` 与
> `docs/workplan/CHAMPIONSHIP-P0-LIVE-WORKBENCH-PLAN.md` 为准。

## 1. 必交件

| ID | 交付物 | 赛题约束 | 当前状态 | 权威入口 |
|---|---|---|---|---|
| A1 | D1 技术方案报告 | PDF，≤30 页 | **PASS**：18 页正式提交版 | `output/pdf/XA-Guard-XA-202620-technical-report.pdf` |
| A2 | D2 可复现代码 | 完整、可复现 | **PASS / RELEASE-READY** | 根 README、`scripts/verify_release.py`、`docs/delivery/CODE-MAP.md` |
| A3 | D3 演示视频 | ≤10 分钟 | **PASS**：8:50，H.264/AAC，中文字幕 | `output/video/XA-Guard-XA-202620-demo.mp4` |
| A4 | D4 报名表 | 审核通过/盖章 | **DONE-MANUAL**：负责人既有确认 | 仓库外隐私材料 |

D1 SHA-256：
`de37a83c973d28f1b4efdc77efda4648a704db94540cb9839b6f4d2e8660c7f1`

D3 SHA-256：
`267a1a59f7f48c9d8e489f085afda0ff79197118ceff7b7e2d5422d5962b00c5`

## 2. 比赛主证据

| 能力 | 事实 | 证据 |
|---|---|---|
| Gate1 输入识别 | 6 族 60/60；FPR 0/58；Wilson 95% 上界 6.21%；规则层 p95 0.04ms | `docs/evidence/gate1-l3-evaluation-2026-06-18.json` |
| 确定性 OAR | 邮箱/RAG 各 Null leak 10/10、Guard leak 0/10；protected replay 20/20 | `docs/evidence/attack-proof-set-2026-07-27-n10.md` |
| 真实 Agent 因果 | 30 runs、0 infra；D2 attempt 10/10、Null harm 10/10、Guard deny 10/10/harm 0/10 | `docs/evidence/live-agent-holdout-v1-2026-07-27.md` |
| 真实 Agent 边界 | D1 realistic-safe attempt 5/5、Guard allow/harm 5/5 | 同上 |
| 真实客户端 | OpenCode 1.18.5 + DeepSeek V4 Flash + XA-Guard MCP，1 audit/0 error | `docs/evidence/d3-opencode-deepseek-flash-preflight-2026-07-27.md` |
| Identity + Undo | 14 artifacts、102 Effect、59 Gate6，SM2-with-SM3 独立验签 | `docs/evidence/agent-identity-undo-final-2026-07-21.md` |
| Reference/kind | all-fault 11/11；本地三节点 profile 全阶段 PASS | 同上 |
| 性能 | 三轮 incremental p95 45.109/42.141/43.934ms，单侧 95% 上界均 <50ms | 同上 |

真实 Agent、确定性 OAR、Gate1 诊断集和 canonical full-day 必须分轨报告，不得合并成一个 ASR。

## 3. D1/D3 内容纪律

- 题号和题目全称必须与赛题原文一致。
- D1 真实失败边界必须写成：Gate4 会递归扫描字面内容，但不会把 `sources` 符号引用解析到
  OAR 业务世界并查询所指资产敏感级别。
- D3 0/10 attempt 是模型未形成违规意图，不归因 XA-Guard。
- OAR N=10 是合成确定性证明，不外推通用攻击率。
- MCP 安全 target 不执行真实命令、插件或网络动作。
- local kind 不等于生产 HA；软件密钥/本地时间证据不等于 HSM/第三方 TSA。
- 不公开攻击 payload、攻击脚本、凭据、原始 JSONL 或本机绝对路径。

## 4. 复现与发布门禁

- 根 pytest 覆盖产品与集成测试。
- `open-agent-range/kernel/tests` 作为独立测试集合显式进入 CI 与 release verifier。
- live authenticity 不信任 summary 顶层结论，重新检查 run matrix、per-run verdict、
  stable/causal claims 与应有 audit 覆盖。
- 原始 `.runtime` 证据只在受控本地保留，公开仓库提交脱敏摘要与哈希。
- 正式 release manifest 必须在 clean final commit 上生成。

## 5. 退役或可选研究项

以下项目不属于比赛必交 PASS/BLOCKED：

- R1 旧 implementation/frozen 数据面；
- AgentDojo/InjecAgent `research_full_matrix`；
- budget60 sampled 外部评测；
- 第三方 TSA、真实 HSM、生产多地域 HA；
- 未提供的商业 provider/客户端全矩阵。

它们可以作为后续研究，不得回写为比赛作品“未完成 blocker”，也不得用未运行结果冒充通过。

## 6. 外部提交动作

D1–D4 仓库内准备已完成。邮件发送、仓库 URL、网盘权限、D4 系统截图和回执保存由负责人在提交窗口
人工完成；未执行前保持“待外部提交”，不写成“已提交”。
