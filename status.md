# 仓库状态：XA-Guard / XA-202620

> 快照日期：**2026-07-26**（America/Los_Angeles）
> 当前统一口径：**ENGINEERING-FROZEN / RELEASE-VERIFIED / SUBMISSION-PLANNED**
> 比赛交付口径：[docs/acceptance/DELIVERY-v2.md](docs/acceptance/DELIVERY-v2.md)
> 提交材料收口计划：[docs/delivery/D1-D3-submission-plan.md](docs/delivery/D1-D3-submission-plan.md)
> 本轮评审意见：[docs/delivery/REVIEW-2026-07-26.md](docs/delivery/REVIEW-2026-07-26.md)
> 工作历史见 [log.md](log.md)。

## 总体结论

产品功能已停止扩展并完成本地工程冻结。Gate1–6、OAR 主评测、MCP 代理、OIDC + 动态 assignment、PostgreSQL Effect、独立审批 Undo、Worker 补偿、Console/BFF 与本地 kind HA 主路径均已实现。最终候选的 Reference 全故障 11/11、kind HA 全阶段、正式 10 并发性能和 unified release verifier 均已通过。代表性攻击证明集已在 clean Git 锚点上完成 6/6 verified 的提交级收口。

**当前主线已从工程转为提交材料收口。** 2026-07-26 对照赛题 PDF 完成 D1 两份草稿的评分维度审阅，识别出 6 项 P0 缺口：占 30% 权重的"实际效果"维度缺赛题点名的攻击识别准确率与误报漏报指标（数据已存在于 `docs/evidence/gate1-l3-evaluation-2026-06-18.json` 的 `gate1_scope`，未被引用）；答题要求点名的"指标体系""算法设计""预期效果"与目标(4)五维度无对应章节；赛题原文"兼容 OpenClaw 类智能体"在两稿中均未出现；技术创新性维度无横向对比表；30 页预算仅用 14 页；且**当前 PDF 构建管线无法构建 v0.2 审阅稿**（缺 pagebreak 标记、使用 mermaid 而非 `[DIAGRAM:x]`，`scripts/build_d1_pdf.py:154` 直接 ValueError，已实测）。全部缺口、验收标准与排期见收口计划；审阅本身未改动产品、测试、证据或交付稿。

**同日负责人完成五项决策定案并冻结**：D1 底稿取 v0.2 审阅稿、Gate1 分层识别指标写入正文、OAR live A/B 的 N 由 3 提到 10、视频格式已向赛事方确认无特殊要求、D3 旁白采用真人录音。据此产生三个连带口径：① v1 稿不再作为构建源，D1 在 P0-6 完成前无最终产物，14 页 PDF 仅为过渡兜底；② 数字冻结日锁定 8/9，在此之前 D1 与字幕中 OAR 数字留占位不写定值；③ 下一动作明确为 P0-6，须排在其余 P0 之前。

## 当前交付成熟度

| 交付面 | 状态 | 当前事实与边界 |
|---|---|---|
| 核心功能与四方向覆盖 | DONE | 六关、MCP、AIBOM、OAR、Identity + Undo、Console 和审计均有实现与证据 |
| B6/B7 Identity + Undo | DONE | 最终候选 all fault 11/11、kind HA 和正式性能通过；不外推为生产 IAM/多地域 HA |
| D1 技术方案 | **BASE-FROZEN / BUILD-BLOCKED** | 底稿已定为 v0.2 审阅稿（DEC-1），v1 稿转为历史参考不再作构建源；**v0.2 当前无法构建 PDF**，故 D1 暂无最终产物，`output/pdf/…technical-report.pdf`（14 页，v1 稿产出）为过渡期兜底且不得删除；6 项 P0 缺口待补，P0-6 为硬前置 |
| D2 代码与发布 | DONE-REMOTE / RELEASE-VERIFIED | 最终 evidence、统一复验、冻结提交与 clean manifest 完成并同步 `origin/main`；未创建 tag/release |
| D3 演示视频 | **MANUAL-PENDING / SCRIPT-REVISION-NEEDED** | 逐镜指南与 SRT 模板完成；现行八镜头缺 live 攻击拦截与 AIBOM 画面，方向一/三 0 秒出镜，需按收口计划 §7 重排后再录；成片参数已冻结（1920×1080 / 30fps / H.264+AAC，**真人录音**）；SRT 与旁白稿需按新顺序重写 |
| D4 报名表 | DONE-MANUAL | 负责人已确认审核/盖章完成；隐私材料在仓库外；建议提交前再核实一次系统审核状态 |
| 代表性攻击证明集 | DONE-CLEAN / SEALED / PUBLIC | 六类 case 6/6 verified、0 failed、0 infra_error；Git start/end clean；6/6 protected replay PASS；根清单 240/240 非自身文件 |
| 文档一致性 | REVIEW-OPEN / ATTACK-PROOF-SYNCED | D1 v0.2 5.5、Delivery v2、证据收敛表、公开证据索引与 provenance JSONL 已统一到 2026-07-26 clean run；D1 底稿选择与 P0 缺口仍待负责人定案 |

## 提交材料收口计划（2026-07-26 制定）

完整任务、验收标准与风险登记见 [D1-D3-submission-plan.md](docs/delivery/D1-D3-submission-plan.md)。

### 冻结顺序

依赖链为 **数字 → 视频 → PDF**（不是视频 → PDF）。数字是最上游约束：视频录完后若数字变动，只能重录或接受口径不一致，而口径漂移已列为 submission-checklist 红线。

| 周 | 任务 | 冻结点 |
|---|---|---|
| ~~7/26~~ | ~~五项决策定案~~ | ✅ **决策已冻结** |
| 7/27–8/2 | **P0-6 先行**（修构建管线 + 切 SOURCE 到 v0.2 + 产废弃 PDF 量页数）→ 然后 P0-1..P0-5 起草 | — |
| 8/3–8/9 | 唯一一次 OAR 重跑（N=10）+ 重新封存 + 同步全部引用点 + 建 `FROZEN-NUMBERS.md` | **数字冻结** |
| 8/10–8/23 | D1 内容完成 → v0.9 PDF；只改文字不改数字 | — |
| 8/24–9/6 | 按重排镜头表录制 D3（真人旁白） | **视频定版** |
| 9/7–9/11 | 只回改录像暴露的问题；重建 PDF；核页数与 hash | **PDF 冻结** |
| 9/12–9/14 | 提交邮件与附件核对（不踩 9/15） | **提交** |

### 已冻结决策（2026-07-26 负责人定案）

**五项全部定案，不再回退为待办。** 后续工作以收口计划 §1 为唯一依据。

| # | 决策 | 定案 | 连带影响 |
|---|---|---|---|
| DEC-1 | D1 底稿 | **v0.2 审阅稿 `D1-technical-report-review-draft.md`** | v1 稿 `D1-technical-report-draft.md` 转为历史参考与文本来源，**不再作为构建源**；P0-6 升级为硬前置 |
| DEC-2 | Gate1 分层识别指标 | **写入 D1 正文** | 四条范围声明缺一不可（范围 60 例 / 6 族 / `independent_holdout=false` / Wilson 区间） |
| DEC-3 | OAR live A/B 的 N | **由 3 提到 10** | 数字冻结日锁定 **8/9**，无左移空间；8/9 前 D1 与字幕中 OAR 数字留占位，不写定值 |
| DEC-4 | 赛事咨询 | **视频格式已问，答复无特殊要求** | D3 沿用现有成片参数；风险 R6 关闭；邮件命名按赛题 PDF 原文照写 |
| DEC-5 | D3 旁白 | **真人录音**，不用 TTS | 旁白稿须按新镜头表重写并逐段掐表；SRT 需重写；新增风险 R9（读超时长） |

### P0 缺口摘要（按分值排序）

| # | 缺口 | 对应维度 |
|---|---|---|
| P0-1 | 补 Gate1 分层识别指标：声明范围内 60 例召回 1.0、误报 0/134（Wilson 上界 6.21%）、规则层 p95 0.04ms；说明总体 0.3575 系归属误配（193 例中 133 例属 Gate2/3/5 + AIBOM 判定面） | 实际效果 30% |
| P0-2 | 补"指标体系"章节，行名直用目标(4)五维度（数据/内容/执行/供应链/合规） | 实际效果 30% + 完整性 20% |
| P0-3 | 补"算法设计"小节，收拢阈值标定、Spotlighting、AST 谓词、策略合并、双链 CAS、bootstrap、AIBOM 评级 | 完整性 20% |
| P0-4 | 补"兼容 OpenClaw 类智能体"（赛题原文，两稿均 0 次出现） | 应用价值 20% |
| P0-5 | 补横向对比表，突出"副作用恢复 + 双链证据"独占列 | 创新性 25% |
| P0-6 | 修 PDF 构建管线使其能构建 v0.2，并产废弃 PDF 量页数（**须第一周完成**） | 全部 |

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
| Gate1 输入识别指标 | SCOPED-PASS | 声明范围为 6 个输入攻击族 60 例；`independent_holdout=false`，payload 指纹零重叠切分为诊断性质，不外推为泛化召回；治理类用例不属 Gate1 判定面 |
| OIDC 与动态 assignment | REFERENCE-PASS | 每请求实时授权；生产仍需组织 IdP、TLS 与密钥治理 |
| PostgreSQL EffectStore | REFERENCE/PERFORMANCE-PASS | intent-first、双链 CAS、批处理与混合单事务均保留 |
| Undo / Worker | REFERENCE-PASS | 至少一次调度 + 下游幂等，不宣称绝对 exactly-once |
| Console/BFF | BUILT / MANUAL-QA-PASS | 三账号职责分离闭环已由负责人手测 |
| Helm / kind | LOCAL-PROFILE-PASS | 只证明本机三节点 profile，不是生产多地域 HA |
| Evidence | SEALED / VERIFIED | 最终候选 14 artifacts、102 Effect、59 Gate6；SM2-with-SM3 key id `87ca0b5c56dc9313` 独立验签通过 |

## 剩余事项

决策项已全部关闭（见上节）。以下按执行顺序排列。

1. **P0-6（下一动作，硬前置）**：修 PDF 构建管线使 v0.2 可构建，`SOURCE` 切到 v0.2，产一版废弃 PDF 量实际页数。**必须排在 P0-1..P0-5 之前**——先让管线跑通再灌内容，否则内容改完仍不知页数是否超限（风险 R1，已升级为致命）。
2. 按 P0-1..P0-5 补写 D1 正文（Gate1 分层指标、指标体系、算法设计、OpenClaw、横向对比表）；补写时四条范围声明缺一不可，对比表只用事实源已核实条目。
3. 8/3–8/9 完成唯一一次 OAR N=10 重跑与重新封存，随后建立 `FROZEN-NUMBERS.md` 并冻结数字；**在此之前 D1 与字幕中 OAR 数字留占位，不写定值**。
4. 按收口计划 §7 重排 D3 镜头；重写旁白稿与 `D3-video-subtitles.srt`（现有版本对应旧顺序）；先做不录制预演找 UI 崩点，再真人录音。
5. 并行准备答辩问答手册与 `CODE-MAP.md`（P2-1/P2-2）。
6. 人工确认 D4 隐私附件、网盘权限和邮件内容，并再核实一次报名表系统审核状态（风险 R8）；攻击证明源码锚点提交与公开材料尚未推送，未创建 tag/release。
7. 按提交清单核对 D1–D4，目标 2026-09-12–14 提交，不踩 9/15 截止。

## 声明边界

- `.runtime/reference/`、`.runtime/kind-ha/`、`.runtime/evidence/` 含运行数据或敏感材料且不进入 Git。
- D1/D3 仓库内容不含学校、个人信息、密码、token 或私钥。
- 2026-07-26 D1 评审与收口计划为纯文档工作：未重跑产品、故障、kind、性能或攻击实验，未修改产品/测试代码，未替换当前 14 页 PDF。
- 收口计划识别的缺口是**材料表述缺口，不是新发现的功能缺陷**；补缺方式为引用已封存证据，不允许为凑指标重测、改阈值或改断言。
- Gate1 分层指标若写入 D1，必须同时声明：范围 60 例、6 个攻击族、seed 与规则开发同源、`independent_holdout=false`、诊断性切分、Wilson 区间、时延为规则层。
- 攻击证明集为合成确定性场景：**当前已封存证据为 OAR live A/B 每类 N=3**，只说明本场景结果；MCP 下游 target 只记账不执行命令、插件或网络动作，身份边界复用独立验签的最终 bundle。按 DEC-3，N 将在 8/3–8/9 的一次性重跑中提到 10；在该重跑落地前，对外仍只能引用 N=3 的既有数字，旧 run 事后保留为历史、不覆盖。
- OAR 重跑的红线：只改 N，不改阈值、断言、产品代码或 case oracle；若 protected 侧出现非零泄漏或 infra error，照实记录并按真实值调整 D1 表述，不重跑掩盖。
- 2026-07-26 攻击证明 clean run 可由记录的 Git head 精确定位 runner/manifest/record-only target；公开仓库只含脱敏摘要、完整文件名/hash 索引和 provenance，不含 raw payload/audit。2026-07-23 dirty run 仅保留为历史功能结果。
- 产品不再新增功能；唯一允许的实验变更是 OAR 的 N 值调参重跑，只有最终验证暴露真实缺陷时才回到修复流程。
