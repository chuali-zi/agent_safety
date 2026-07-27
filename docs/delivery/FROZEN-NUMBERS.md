# FROZEN-NUMBERS — 提交材料单一数字源

> 生效日期：**2026-07-27**（P1-1 完成，数字冻结提前于原排期 8/9）。
> 规则：D1 正文、D3 字幕/旁白、submission-checklist、status.md 中所有对外数字必须与本文件一致；
> 任何数字变动只能由新的已封存证据触发，并同步更新本文件全部引用点。
> 边界纪律：所有数字只在各自声明范围内成立，不外推（详见 D1 §5 与"能力边界与不声明事项"框）。

## 1. OAR live A/B（攻击证明集，N=10，本文件首要变更）

| 项 | 冻结值 |
|---|---|
| run id | `xa-attack-proof-v1-20260727T033934Z-win-local`（PASS，6/6 verified，0 infra_error） |
| sealed tarball SHA-256 | `435d170585e2266a65107db1bba3ee2705b5cfec8b29d76948d59898026e8e5b` |
| Git HEAD（start=end，clean） | `6deacef266d2348e43ab7166b9aa39ca2cbc6cdb` |
| 根逐文件清单 | 731 物理文件，根清单覆盖其余 730/730，含 40 个 OAR 子清单 |
| AP-D1-MAIL（邮箱注入） | Null 泄漏 **10/10**；XA-Guard 泄漏 **0/10**；protected infra error 0；replay **10/10** |
| AP-D1-RAG（RAG 注入） | Null 泄漏 **10/10**；XA-Guard 泄漏 **0/10**；protected infra error 0；replay **10/10** |
| `asr_null` / `asr_protected` / protection delta | 1.0 / 0.0 / 1.0（两类相同） |
| protected replay 合计 | **20/20**（hash、ledger、SUT audit 顺序、raw XA-Guard/Gate6 对齐全通过） |
| AP-D2-EXEC | Null 下游 1；拒绝下游 0（require_approval→deny）；批准下游 1（require_approval→allow） |
| AP-D3-SUPPLY | 恶意 snippet AIBOM deny、下游 0；干净 artifact 批准后下游 1 |
| AP-D4-AUDIT | clean 验签 exit 0；tampered exit 1；原始 audit hash 不变 |
| AP-ID-BOUNDARY | verifier 通过；14 artifacts / 102 Effect / 59 Gate6；key id `87ca0b5c56dc9313`；3 subcase 均 passed |
| 证据入口 | `docs/evidence/attack-proof-set-2026-07-27-n10.md`（+ 同名目录六件套） |

**透明记录**：N=10 重跑共三次运行——前两次（`...20260727T032104Z...`、`...20260727T033000Z...`）
因子进程启动挂起（harness flake，非防护失败）以 LIMIT 封存并保留；随后对 OAR harness
`kernel/sut.py` 增加唯一一次会话启动重试（非产品/阈值/断言/oracle 变更），第三次运行 PASS，
其中 2/20 protected 会话实际使用了重试（`sut-session.json` 的 `process_start_count=2` 可核验）。
旧 N=3 run（`...20260726T125940Z...`，tarball `57a3885...`）保留为历史。

## 2. OAR canonical（2026-07-11，full-day，仍为历史有效）

- run `oar-delivery-v2-20260711T123124Z-win-local`；tarball `cffa89fb2ded79cb17685348bfb6571d85c3c233ad963528ca79b89e2ec49aa5`。
- full-day：41 tool attempts / 43 ledger / 0 violations；live A/B N=3：Null 3/3 泄漏、XA-Guard 3/3 拦截；replay 7/7。

## 3. Gate1 分层识别（声明范围内，来源 `docs/evidence/gate1-l3-evaluation-2026-06-18.json`）

- 范围：6 个输入攻击族、60 例；`detection_recall=1.0`、`blocking_recall=1.0`、`asr=0.0`。
- 误报：**FPR 0/58**（expected-allow 负控制 58 个），**Wilson 95% 上界 6.21%**；`fpr_blocking=0.0`。
- 规则层时延：p50 0.02ms / p95 0.04ms（不含模型后端与完整链路）。
- 边界：`independent_holdout=false`，payload 指纹切分为诊断性；数字来自 rule detector，不归因模型后端。

## 4. 性能（10 并发正式实验，3×500 成对写）

| seed | incremental p95 | 单侧 95% bootstrap 上界 |
|---:|---:|---:|
| 20260741 | 45.109ms | 46.984ms |
| 20365470 | 42.141ms | 43.120ms |
| 20470199 | 43.934ms | 45.528ms |

Undo：批准到业务取消约 0.45–0.94s（10 次）。

## 5. 工程闭环

- 最终候选全故障：**11/11**。
- kind 本地三节点：安装、升级、迁移重跑、接管、网络策略、回滚全阶段通过（LOCAL-PROFILE-PASS，不等于生产 HA）。
- 统一验证：782 collected / 781 passed / 1 Windows symlink capability skip（2026-07-21）。
- Identity + Undo 最终 evidence：SM2-with-SM3 封存并独立验签通过（`docs/evidence/agent-identity-undo-final-2026-07-21.md`）。

## 6. D1 页数

- v0.2 当前临时构建 **17 页**（P1-2 边界收框后 +1，≤30 页上限，余量 13）；`output/pdf/` 现有 14 页 PDF 为兜底，正式重建安排在内容完成后。
