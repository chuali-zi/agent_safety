# 仓库状态：XA-Guard / XA-202620

> 当前口径：**SUBMISSION-READY / INTERNAL ACCEPTANCE PASS / EXTERNAL SUBMISSION PENDING**
> 更新：2026-07-27
> 赛题：**面向政企场景的大模型智能体安全关键技术研究**

## 1. 总体结论

赛题要求的 D1 技术方案、D2 可复现代码、D3 演示视频和答辩材料已经在仓库内收口。
D4 维持负责人既有审核通过确认，提交前需人工复核报名系统状态。邮件发送、仓库 URL、网盘上传和
回执保存尚未执行，因此不写“已提交”。

权威状态入口：

- [Delivery v2](docs/acceptance/DELIVERY-v2.md)
- [D1/D3 收口计划](docs/delivery/D1-D3-submission-plan.md)
- [交付验收矩阵](docs/delivery/DELIVERY-ACCEPTANCE-MATRIX.md)
- [最终提交清单](docs/delivery/submission-checklist.md)

## 2. 正式交付物

| 交付面 | 状态 | 当前事实 |
|---|---|---|
| D1 | **FINAL / PASS** | 18 页正式 PDF，≤30 页；题号、题名、问题分析、技术路线、七项算法、实验计划、五维指标、预期效果、边界和证据索引齐全 |
| D2 | **RELEASE-READY / PASS** | 产品、测试、复现脚本、CODE-MAP、公开脱敏证据齐全；OAR kernel 纳入 CI/release gate |
| D3 | **FINAL / PASS** | 8:50 MP4，11 镜头，真实 OpenCode/DeepSeek Flash/MCP、安全 Tool Call、真实 Agent 因果、Console/Undo/证据与工程结果齐全 |
| D4 | **DONE-MANUAL** | 负责人既有审核通过确认；隐私材料不入仓库，提交前人工复核 |
| 答辩 | **READY / PASS** | DEFENSE-QA 30 题、CODE-MAP、FROZEN-NUMBERS |

D1：

- 文件：`output/pdf/XA-Guard-XA-202620-technical-report.pdf`
- 页数：18
- SHA-256：`de37a83c973d28f1b4efdc77efda4648a704db94540cb9839b6f4d2e8660c7f1`
- 全页渲染抽检：PASS

D3：

- 文件：`output/video/XA-Guard-XA-202620-demo.mp4`
- 时长：530.033 秒
- 媒体：H.264、1920×1080、30fps；AAC、48kHz、双声道；中文 `mov_text` 字幕轨
- SHA-256：`267a1a59f7f48c9d8e489f085afda0ff79197118ceff7b7e2d5422d5962b00c5`
- 旁白：本地 `Microsoft Huihui Desktop` 离线合成并在 metadata 披露，不声称真人
- 画面抽检与音量检查：PASS

## 3. 关键证据

### Gate1

- 6 个输入攻击族，60/60 识别并阻断。
- expected-allow FPR 0/58；Wilson 95% 上界 6.21%。
- 规则层 p95 0.04ms。
- `independent_holdout=false`；不含模型或完整链路时延。

### 确定性 OAR

- 邮箱：Null leak 10/10；XA-Guard leak 0/10；replay 10/10。
- RAG：Null leak 10/10；XA-Guard leak 0/10；replay 10/10。
- protected replay 合计 20/20；0 infra error。
- 这是合成确定性证明，不运行真实大模型，不外推通用攻击率。

### 真实 DeepSeek Agent holdout

- 30 runs，0 infra。
- D2 两档合计 attempt 10/10；Null harm 10/10；XA-Guard deny 10/10、harm 0/10；
  同一不可变 ToolIntent 的因果证明成立。
- D1 realistic-safe attempt 5/5；XA-Guard allow/harm 5/5。
- D3 两档 attempt 0/10，只归因模型自防。
- authenticity：303 files；30/30 per-run verdict；stable/valid breach/causal proof 重算一致；
  expected/actual audit 15/15；全部检查 PASS。

D1 的真实边界是：Gate4 会递归扫描参数中的字面字符串，但不会把 `sources` 符号引用解析到
OAR 业务世界并查询所指资产敏感级别。该失败结果已进入 D1、D3、QA 和公开摘要，未通过重跑、
改 payload、调阈值或改测试掩盖。

### 真实客户端

- OpenCode 1.18.5。
- `deepseek/deepseek-v4-flash`。
- 恰好一个 XA-Guard HTTP MCP 服务连接。
- 实际执行一次无副作用 `get_cpu({host:web03})`，返回 CPU 85%。
- Gate6 allow、faithfulness 1.0，1 record verified、0 error。

## 4. 当前验证

| 验证 | 结果 |
|---|---|
| root unit | 666 collected；665 passed；1 Windows symlink capability skip |
| root integration | 46 collected；45 passed；1 本地 sandbox image 不可用 skip |
| root top-level tests | 57/57 passed |
| root deployment + remote runner | 23 collected；19 passed；4 本机 Helm 不可用 skip |
| root 合计 | **792 collected；786 passed；6 capability/environment skips；0 failure/error** |
| OAR kernel | **137/137 passed** |
| governance 声明集合 | **48/48 passed** |
| live authenticity regression | **10/10 passed**；正式 holdout verify PASS |
| Ruff | `src bench demo scripts tools open-agent-range/kernel`（排除测试目录 lint）PASS |
| release manifest builder | Windows 中文 tracked path 按 Git `-z` UTF-8 原始字节解析；dirty tree fail closed，PASS |
| D1 build/render | 18 页，SHA-256 与上文一致，PASS |
| D3 media | 530.033 秒、H.264/AAC/中文字幕轨、SHA-256 与上文一致，PASS |

root 全集合因桌面后台进程被宿主提前终止，最终按 unit、integration、top-level、
deployment/remote-runner 四个互斥分组执行；四组收集数合计 792，与统一 collection 一致。
未修改测试来获取通过。

## 5. 仓库与证据发布边界

- `.runtime/` 与 `open-agent-range/.runtime/` 全面 gitignore。
- 原先误跟踪的 868 个 runtime 文件已经从 Git 索引移除，本地副本保留。
- 公开仓库提交 `live-agent-holdout-v1-2026-07-27.md` 与
  `d3-opencode-deepseek-flash-preflight-2026-07-27.md` 脱敏摘要。
- 不提交模型输入、攻击 payload、攻击脚本、JSONL、凭据、原始日志或本机绝对路径。
- live authenticity 对缺失/意外 audit、缺失 per-run verdict 与伪造 stable/causal 顶层结论
  均 fail closed。

## 6. 仍然成立的能力边界

- D1 `sources` 引用解析与敏感资产查询边界尚未修复。
- AIBOM 只使用 A/B/C/D/F 五档；静态/元数据分析不是任意动态恶意逻辑的完备检测。
- MCP 演示下游是脱敏安全 target，不执行真实运维命令、插件或网络动作。
- Reference/local kind 不等于生产多地域 HA。
- 软件密钥、本地 hash/时间证据不等于 HSM 或第三方 TSA。
- 生产仍需组织 IdP、KMS/HSM、TLS、备份、容量、灾备和运维流程验收。
- R2/R3 sampled、research full matrix、第三方设施是退役/可选研究项，不是比赛 blocker。

## 7. 下一步

仓库内无未完成的比赛实现计划。Release manifest 是在最终 commit 之后生成的 gitignored
交接工件，执行结果不硬编码进提交以避免自引用。负责人只需按
[submission-checklist.md](docs/delivery/submission-checklist.md) 完成 D4 状态复核、仓库可见性检查、
网盘上传、邮件发送和回执保存。
