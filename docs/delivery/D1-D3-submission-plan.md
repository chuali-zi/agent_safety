# XA-202620 提交材料收口计划：验收完成

> 当前状态：**ALL INTERNAL PLAN GATES PASS / SUBMISSION PACKAGE READY**
> 完成日期：2026-07-27
> 赛题：**面向政企场景的大模型智能体安全关键技术研究**
> 题号：**XA-202620**
> 赛题原文是唯一需求源；外部邮件发送、网盘上传与报名系统复核不属于仓库内自动执行范围。

## 1. 最终交付

| 交付物 | 状态 | 文件 | 验收事实 |
|---|---|---|---|
| D1 技术方案报告 | **PASS / FINAL** | `output/pdf/XA-Guard-XA-202620-technical-report.pdf` | 18 页，≤30 页；SHA-256 `de37a83c973d28f1b4efdc77efda4648a704db94540cb9839b6f4d2e8660c7f1` |
| D2 可复现代码 | **PASS / RELEASE-READY** | 仓库根、`scripts/verify_release.py`、`docs/delivery/CODE-MAP.md` | 产品、测试、证据索引与复现入口齐全；OAR kernel 已纳入 CI/release gate |
| D3 演示视频 | **PASS / FINAL** | `output/video/XA-Guard-XA-202620-demo.mp4` | 8:50，1920×1080、30fps、H.264/AAC、中文字幕轨；SHA-256 `267a1a59f7f48c9d8e489f085afda0ff79197118ceff7b7e2d5422d5962b00c5` |
| D4 报名表 | **DONE-MANUAL** | 仓库外隐私材料 | 负责人既有确认保持；提交前只需人工复核系统可见状态 |
| 答辩材料 | **PASS** | `docs/delivery/DEFENSE-QA.md`、`CODE-MAP.md`、`FROZEN-NUMBERS.md` | 30+ 问答、代码/测试/证据映射与单一数字源齐全 |

## 2. 赛题评分贴合

| 评分维度 | 权重 | 交付覆盖 | 状态 |
|---|---:|---|---|
| 技术创新性 | 25% | intent-first Effect、职责分离 Undo、Gate6/Effect 双链、真实 Agent 同一 ToolIntent 因果分叉 | **PASS** |
| 实际效果 | 30% | Gate1 分层数字、确定性 OAR N=10、真实 DeepSeek holdout、业务后果与故障/性能 | **PASS** |
| 方案完整性 | 20% | 问题分析、技术路线、七项算法、原型、实验方案、五维指标、预期效果、边界 | **PASS** |
| 应用价值 | 20% | MCP/HTTP 接入、OpenCode/Claude Code 真实客户端、Identity/Effect/Undo、Reference/kind | **PASS** |
| 展示表达 | 5% | 18 页正式 PDF、8:50 证据驱动视频、答辩问答与 CODE-MAP | **PASS** |

## 3. D1 验收

### P0

- [x] P0-1：Gate1 六族 60/60、FPR 0/58、Wilson 95% 上界 6.21%、规则层 p95 0.04ms，
  并保留 `independent_holdout=false` 与非完整链路声明。
- [x] P0-2：按赛题目标写入数据、内容、执行、供应链、合规五维指标体系与预期效果。
- [x] P0-3：写入阈值标定、Spotlighting、AST 谓词、策略合并、双链 CAS、bootstrap、AIBOM
  五档评级等算法设计。
- [x] P0-4：写入 OpenClaw 类智能体的 MCP/HTTP 协议层兼容与专有接口边界。
- [x] P0-5：写入六能力横向对比，外部方案只按已核验事实描述。
- [x] P0-6：PDF 构建器支持正式封面、Mermaid、表格、分页、metadata、SHA-256 与全页渲染。

### P1

- [x] P1-1：确定性 OAR 邮箱/RAG 各 N=10，保护侧 replay 20/20，数字冻结。
- [x] P1-2：能力边界集中收框，真实 D1 5/5 allow/harm 不被确定性 0/10 覆盖。
- [x] P1-3：页数策略关闭为“可读性优先”；18 页已覆盖赛题全部点名项，不以凑满 30 页为目标。
- [x] P1-4：赛事方已答复视频无特殊格式要求；正式文件名、题号和题目全称已统一。

### 正式 PDF

- [x] 封面使用题号、题目全称、学生赛道、提交版与日期。
- [x] 正文明确分开 Gate1 诊断集、确定性 OAR、真实 DeepSeek holdout 与 canonical full-day。
- [x] 真实 D1 边界精确表述为：Gate4 会扫描字面内容，但不会把 `sources` 符号引用解析到
  OAR 业务世界并查询所指资产敏感级别。
- [x] AIBOM 只使用 A/B/C/D/F 五档，不虚构 E 档或未记录等级。
- [x] 18 页全部渲染抽检，无越界、乱码或 `---` 残留。
- [x] 附录列出所有核心证据，包括 OpenCode 1.18.5 + DeepSeek V4 Flash 预演。

## 4. D3-P0-1 验收

- [x] 真实 OpenCode 客户端只连接一个 XA-Guard HTTP MCP 服务。
- [x] DeepSeek V4 Flash 完成工具发现与一次无副作用 `get_cpu` Tool Call。
- [x] XA-Guard 产生 allow、六关状态、trace 与唯一 Gate6 审计；1 record、0 error。
- [x] 真实 DeepSeek holdout 30 runs、0 infra；D2 两档因果证明成立。
- [x] D1 realistic-safe 5/5 attempt、XA-Guard allow/harm 5/5 在 D1/D3 同屏披露。
- [x] D3 0/10 attempt 只归因模型自防，不计作网关拦截。
- [x] 确定性 OAR N=10 与真实模型轨道分开展示。
- [x] Identity、Effect、职责分离 Undo 与双链证据使用真实验收截图。
- [x] 11 镜头、旁白、SRT 与成片同步。
- [x] MP4 530.033 秒，H.264 1920×1080 30fps，AAC 48kHz 双声道，内嵌 `mov_text`
  中文轨并附独立 SRT。
- [x] metadata 明示旁白由本地 System.Speech 合成，不虚称真人。
- [x] 成片不包含攻击 payload、攻击脚本、凭据、原始审计、个人信息或绝对路径。

原 DEC-5 的真人旁白属于团队偏好，不是赛题要求。为了形成可重复、无人工阻塞的正式候选，
实际执行改为离线中文合成旁白并如实披露。团队后续可以自愿替换真人音轨，但这不是当前 PASS 的前置。

## 5. 答辩材料验收

- [x] P2-1：`DEFENSE-QA.md` 覆盖指标、因果归因、D1 失败边界、Identity、Effect、Undo、
  AIBOM、性能、部署、证据链与生产边界。
- [x] P2-2：`CODE-MAP.md` 将每项核心声明映射到实现、测试和证据。
- [x] P2-3：`FROZEN-NUMBERS.md` 是 D1、D3、status、checklist 的单一数字源。

## 6. 证据与验真门禁

正式 live holdout 的原始 runtime 只在受控本地保留，公开仓库提交脱敏摘要，不跟踪 JSONL、
模型输入或攻击内容。验真器已经从“信任 summary”升级为重新检查：

1. 30/30 frozen run 坐标与逐次 `verdict.json`；
2. summary 指标重算；
3. stable result、valid breach 与 causal proof 重算；
4. 15/15 应有真实 audit 的严格覆盖；
5. ToolIntent、Gate decision、branch verdict 与 record hash 一致。

缺失 audit、意外 audit、缺失 per-run verdict、伪造 stable/causal 顶层结论都会使验证失败。
OAR kernel tests 已显式加入 GitHub Actions 和 `scripts/verify_release.py`。

## 7. 风险关闭

| 风险 | 处置 | 状态 |
|---|---|---|
| PDF 最后阶段不可构建 | 正式构建 + 18 页全页渲染 + hash | **CLOSED** |
| D1/D3 数字漂移 | 单一数字源 + 分轨报告 + hash | **CLOSED** |
| D3 只有静态脚本 | 真实 OpenCode/DeepSeek Flash/MCP 预演 + Console 真实截图 | **CLOSED** |
| 真实 D1 失败被掩盖 | D1、D3、QA、状态四处同口径披露 | **CLOSED** |
| runtime 原始攻击内容进入 Git | `.runtime` 全面忽略，已从 Git 跟踪移除，公开脱敏摘要 | **CLOSED** |
| summary 自报结论可伪造 | authenticity 强一致性重算与回归测试 | **CLOSED** |
| 生产能力越界宣称 | Reference/local kind/合成 target/软件密钥边界同屏 | **MITIGATED / ACCEPTED** |

## 8. 交付之外的人工动作

仓库内计划门禁已经全部通过。以下是提交行为，不是未完成的实现计划：

1. 人工复核 D4 报名表在报名系统仍显示审核通过；
2. 上传 D3/补充证据到长期有效网盘；
3. 在邮件正文首行写题号 XA-202620 与题目全称；
4. 附 D1、D2 仓库链接、D3 链接和 D4；
5. 保存已发送邮件、回执和网盘权限截图。

不得把这些外部动作提前写成“已提交”，也不得把它们重新解释为产品或赛题方案 blocker。
