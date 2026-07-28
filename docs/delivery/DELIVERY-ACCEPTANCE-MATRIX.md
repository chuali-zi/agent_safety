# 交付计划验收矩阵

> 日期：2026-07-27
> 结论：**仓库内全部计划 PASS；仅外部提交动作待负责人执行。**

| 计划/交付面 | 验收状态 | 完成证据 | 残余边界 |
|---|---|---|---|
| D1 P0-1..P0-6 | **PASS** | 正式 18 页 PDF、构建器、全页渲染 | ≤30 页，不以凑页数为目标 |
| D1 P1-1..P1-4 | **PASS** | N=10、边界收框、正式命名/格式 | D1 `sources` 引用解析边界保留 |
| D3-P0-1 | **PASS** | OpenCode + DeepSeek Flash + XA-Guard MCP，1 audit/0 error | 安全查询，不是攻击实验 |
| D3 成片 | **PASS** | 8:50 MP4、11 镜头、音频、中文字幕、metadata/hash | 本地合成旁白已披露 |
| P2 答辩材料 | **PASS** | DEFENSE-QA、CODE-MAP、FROZEN-NUMBERS | 只陈述已证事实 |
| 攻击证明集交接 | **PASS / CLOSED** | 6/6 verified、N=10、20/20 replay | 合成确定性，不外推 |
| real-agent holdout | **PASS WITH DISCLOSED FINDING** | 30 runs、D2 因果、D1 失败边界、D3 模型自防 | 不修改 payload/阈值掩盖结果 |
| live authenticity | **PASS** | 30/30 verdict、stable/causal 重算、15/15 audit | 原始 runtime 受控本地保存 |
| governance 静态计划 | **PASS** | 48 定向测试通过 | 不声称生产 SSO/LDAP/SCIM/HSM |
| Identity + Undo 两轮竖切 | **PASS / CLOSED** | 既有两轮竖切与最终 product evidence | 生产组织接入另验 |
| D2 CI/release gate | **PASS** | root tests、OAR 137 tests、Ruff、release verifier 纳入 OAR | 最终 manifest 在 clean commit 后生成 |
| D4 | **DONE-MANUAL** | 负责人既有审核通过确认 | 提交前人工复核系统状态 |
| 外部邮件/网盘 | **OUTSIDE REPOSITORY** | submission-checklist | 未执行前不写“已提交” |

## 固定产物

- D1：`output/pdf/XA-Guard-XA-202620-technical-report.pdf`
- D1 SHA-256：`de37a83c973d28f1b4efdc77efda4648a704db94540cb9839b6f4d2e8660c7f1`
- D3：`output/video/XA-Guard-XA-202620-demo.mp4`
- D3 SHA-256：`267a1a59f7f48c9d8e489f085afda0ff79197118ceff7b7e2d5422d5962b00c5`

## 判定纪律

“PASS WITH DISCLOSED FINDING”表示实验计划和真实性验收通过，同时发现产品未覆盖边界；
它不把防护失败伪造为产品成功。比赛方案要求问题分析、技术路线、算法设计、实验计划、指标与预期效果，
这些内容均已进入 D1；D3 已展示核心功能、关键流程与测试效果。
