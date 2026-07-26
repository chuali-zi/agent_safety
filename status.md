# 仓库状态：XA-Guard / XA-202620

> 快照日期：**2026-07-23**（America/Los_Angeles）
> 当前统一口径：**ENGINEERING-FROZEN / RELEASE-VERIFIED / SUBMISSION-MANUAL-PENDING**
> 比赛交付口径：[docs/acceptance/DELIVERY-v2.md](docs/acceptance/DELIVERY-v2.md)
> 工作历史见 [log.md](log.md)。

## 总体结论

产品功能已停止扩展并完成本地工程冻结。Gate1–6、OAR 主评测、MCP 代理、OIDC + 动态 assignment、PostgreSQL Effect、独立审批 Undo、Worker 补偿、Console/BFF 与本地 kind HA 主路径均已实现。最终候选的 Reference 全故障 11/11、kind HA 全阶段、正式 10 并发性能和 unified release verifier 均已通过。

D1 当前 14 页 PDF 候选仍保留且可提交；2026-07-22 至 2026-07-23 已完成 Markdown 审阅稿第二轮改写，正文按问题、方案、关键技术、工程化、实验和应用价值展开，仓库证据与论文/标准分开编排，尚待负责人逐段讨论，未替换当前 PDF。负责人已确认 D1 采用“正文保留攻击证明、脱敏样本与脚本作为可选补充材料、原始 payload 不进正文”的层级；v0.2 的 5.5 已改为一条邮箱攻击链剖面、按赛题四方向映射的六类业务观测表和公开边界，不再把旧 run 写成最终封存证据。代表性攻击证明集的六类业务 oracle 均已成立：邮箱/RAG 注入、高风险命令、恶意插件、审计篡改和身份边界在 run `xa-attack-proof-v1-20260723T100008Z-win-local` 中为 6/6 verified，tarball 与 provenance hash 一致；但本次只读复核发现提交级 provenance 尚未收口，不能把当前 sealed run 作为最终定稿证据：运行发生在 dirty worktree，记录的 git head 不包含新增 runner/manifest；根 `artifact-hashes.json` 仅列出 218/231 个文件；OAR 六个 protected attempt 的 replay/audit alignment 经本轮独立复核全部通过，但未进入原 sealed run 的 case oracle 与命令记录。D2 最终 evidence、统一发布复验、冻结提交、clean release manifest 与 `origin/main` 同步已完成；D3 逐镜录制指南与字幕模板已完成，最终视频仍需负责人手工录制。

## 当前交付成熟度

| 交付面 | 状态 | 当前事实与边界 |
|---|---|---|
| 核心功能与四方向覆盖 | DONE | 六关、MCP、AIBOM、OAR、Identity + Undo、Console 和审计均有实现与证据 |
| B6/B7 Identity + Undo | DONE | 最终候选 all fault 11/11、kind HA 和正式性能通过；不外推为生产 IAM/多地域 HA |
| D1 技术方案 | DONE-CURRENT / REVIEW-v0.2-PENDING | 当前候选为 `output/pdf/XA-Guard-XA-202620-technical-report.pdf`（14 页）；`docs/delivery/D1-technical-report-review-draft.md` 已完成 v0.2 讨论稿，待负责人审核后再决定是否替换并重建 PDF |
| D2 代码与发布 | DONE-REMOTE / RELEASE-VERIFIED | 最终 evidence、统一复验、冻结提交与 clean manifest 完成并同步 `origin/main`；未创建 tag/release |
| D3 演示视频 | MANUAL-PENDING | 录制指南和 SRT 模板完成；MP4 尚未录制 |
| D4 报名表 | DONE-MANUAL | 负责人已确认审核/盖章完成；隐私材料在仓库外 |
| 代表性攻击证明集 | FUNCTIONAL-PASS / EVIDENCE-REPAIR-PENDING | 六类 case 6/6 verified、0 failed、0 infra_error；现有 tarball SHA-256 `bb472da919fed5fc4788242338a87b574a0e919b38a0f8c9028f27a7a7380d31` 与 sidecar/provenance 一致；但 dirty-tree 源码锚点、218/231 根 hash 清单和 replay 未入 sealed oracle 三项需修复后在干净提交上重跑，当前公开材料不能视为最终提交级证据 |
| 文档一致性 | REVIEW-OPEN / ATTACK-PROOF-REPAIR | D1 v0.2、最终 Identity evidence 与 `EVIDENCE-CONSOLIDATION.md` §7 均统一为 14 artifacts/102 Effect/59 Gate6；论文/协议/标准与仓库验证索引已分开；D1 v0.2 仍待负责人逐段审阅，攻击证明集公开材料需随干净重跑结果更新 |

## 2026-07-21 最终候选验证基线

- Reference clean-volume 全故障 suite：**11/11 PASS**。最终报告：`.runtime/evidence/reference-faults-all-final-rerun-20260721.json`。
- 同一最终候选的 core 恢复复跑：**7/7 PASS**。首次 all 尝试在 PostgreSQL 恢复后的首个 Keycloak 登录出现一次瞬态 400；保留失败报告，随后 core 和完整 all 独立复跑均通过，未修改产品或测试掩盖。
- 本地三节点 kind profile：安装旧版、升级当前版、migration 重跑、API Pod 删除、Effect prepared 接管、Worker lease 接管、NetworkPolicy 正负探针和 Helm rollback **全阶段 PASS**。报告：`.runtime/evidence/kind-ha-final-pass-20260721.json`。
- 完整重建镜像正式性能三轮：incremental p95 **45.109/42.141/43.934ms**；单侧 95% bootstrap upper **46.984/43.120/45.528ms**；均满足 ≤50ms。Undo **10/10**，约 **0.45–0.94s**。
- 隔离发布 Python 环境：项目依赖安装完成，`pip check` PASS。全局 Python 的 `letta-evals`/`anyio` 冲突属于宿主环境，不通过改写项目依赖规避。
- Console 使用 `npm ci` 恢复依赖；audit 为 **0 vulnerabilities**。
- unified verifier：**782 collected / 781 passed / 1 allowed capability skip / 0 failure / 0 error**；隔离 `pip check`、产品 Ruff、L3 static 11/11、Compose config、Console 5/5 + build 和最终 evidence 验签全部 PASS。
- 本轮未修改任何测试代码、既有断言或性能阈值。

## 关键能力边界

| 能力面 | 状态 | 声明边界 |
|---|---|---|
| Gate1–6、Gate6 审计、OAR B1–B5 | DONE | OAR 是自建红队靶场，不冒充官方 benchmark |
| OIDC 与动态 assignment | REFERENCE-PASS | 每请求实时授权；生产仍需组织 IdP、TLS 与密钥治理 |
| PostgreSQL EffectStore | REFERENCE/PERFORMANCE-PASS | intent-first、双链 CAS、批处理与混合单事务均保留 |
| Undo / Worker | REFERENCE-PASS | 至少一次调度 + 下游幂等，不宣称绝对 exactly-once |
| Console/BFF | BUILT / MANUAL-QA-PASS | 三账号职责分离闭环已由负责人手测 |
| Helm / kind | LOCAL-PROFILE-PASS | 只证明本机三节点 profile，不是生产多地域 HA |
| Evidence | SEALED / VERIFIED | 最终候选 14 artifacts、102 Effect、59 Gate6；SM2-with-SM3 key id `87ca0b5c56dc9313` 独立验签通过 |

## 剩余事项

1. 修复攻击证明集的提交级 provenance：根 hash 清单只排除自身而不能排除 12 个 OAR 子清单；把 OAR protected replay/hash/ledger/SUT audit alignment 纳入 runner oracle、report 和 sealed 命令记录；修复 dirty path 首行截断，并在包含 runner/manifest 的干净提交上重跑六类 proof。保留当前 run，不覆盖或伪装首次结果。
2. 攻击内容层级已确认并写入 D1 v0.2。完成干净重跑后，用新 run 更新公开报告、provenance、证据索引和 D1 5.5，再逐段审阅全文，并决定是否替换 14 页 PDF 与重建。
3. 负责人按 D3 指南录制、剪辑并复核不超过 10 分钟的视频。
4. 人工确认 D4 隐私附件、网盘权限和邮件内容；D2 已同步 `origin/main`，本轮未创建 tag/release。
5. 按提交清单核对 D1–D4，并在 2026-09-15 截止前提交。

## 声明边界

- `.runtime/reference/`、`.runtime/kind-ha/`、`.runtime/evidence/` 含运行数据或敏感材料且不进入 Git。
- D1/D3 仓库内容不含学校、个人信息、密码、token 或私钥。
- 新 D1 审阅稿只复用既有封存证据，本轮未重跑产品、故障、kind 或性能测试，也未修改产品/测试代码。
- 攻击证明集为合成确定性场景：OAR live A/B 每类 N=3 只说明本场景结果，MCP 下游 target 只记账不执行命令、插件或网络动作，身份边界复用独立验签的最终 bundle。
- 当前攻击证明集的六类业务观测值有效，但 sealed run 的源码锚定与全量逐文件 hash 不完整；在干净重跑前不得把它表述为最终提交级、可由 git head 精确复原的证据。
- 本轮没有新增产品运行依赖；PDF 生成使用已有本机构建工具，产品依赖清单未改。
- 产品不再新增功能；只有最终验证暴露真实缺陷时才回到修复流程。
