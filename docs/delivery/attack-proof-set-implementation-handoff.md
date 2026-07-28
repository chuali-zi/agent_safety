# 攻击证明集实施交接：已闭环

> 状态：**COMPLETE / HISTORICAL HANDOFF CLOSED**
> 关闭日期：2026-07-27
> 当前事实源：[FROZEN-NUMBERS.md](FROZEN-NUMBERS.md) 与
> [attack-proof-set-2026-07-27-n10.md](../evidence/attack-proof-set-2026-07-27-n10.md)

本文原用于把攻击证明集 runner、六类 case、业务 oracle、证据封存和 D1/D3 引用交给后续实施者。
对应工作已经完成，不再作为待办或新的攻击脚本需求。当前收口只维护结构、验证结果和公开脱敏证据，
不新增攻击 payload 或攻击脚本。

## 1. 完成结论

| 验收面 | 结果 |
|---|---|
| 统一 runner | `scripts/run_attack_proof_set.py` 已实现 dry-run、执行、验证与封存 |
| 六类独立 case/oracle | 6/6 verified，0 infra error |
| OAR 邮箱注入 | Null leak 10/10；XA-Guard leak 0/10；replay 10/10 |
| OAR RAG 注入 | Null leak 10/10；XA-Guard leak 0/10；replay 10/10 |
| 高风险执行 | Null 下游 1；未批准 deny/下游 0；独立批准 allow/下游 1 |
| AIBOM | 风险 snippet deny/下游 0；干净 artifact 批准后下游 1 |
| 审计篡改 | clean exit 0；tampered exit 1；原始 audit hash 不变 |
| 身份边界 | 14 artifacts、102 Effect、59 Gate6，SM2-with-SM3 独立验签通过 |
| 封存 | run `xa-attack-proof-v1-20260727T033934Z-win-local`，tarball SHA-256 `435d170585e2266a65107db1bba3ee2705b5cfec8b29d76948d59898026e8e5b` |
| 公开材料 | 脱敏摘要与六件套位于 `docs/evidence/attack-proof-set-2026-07-27-n10*` |

## 2. 口径边界

- 该证明集是合成确定性场景，不运行真实大模型，不外推为通用攻击成功率。
- 真实 DeepSeek Agent holdout 是独立轨道；其中 D1 5/5 allow/harm 必须如实披露。
- 安全 target 只记录脱敏业务后果，不执行真实命令、插件或网络动作。
- 原始 run、JSONL 和 payload 保存在受控 gitignored runtime，不进入公开仓库。
- 当前工作不修改 case oracle、策略阈值或测试断言。

## 3. 关闭验收

- [x] runner dry-run 与定向测试通过。
- [x] 六类 case 均有独立业务 oracle。
- [x] Null/批准对照的安全 target 真实触达可核验。
- [x] deny/reject case 下游调用为 0。
- [x] clean 通过、tampered 失败、原件 hash 不变。
- [x] Identity verifier 与 14/102/59/key id 一致。
- [x] raw run 与 sealed tarball 在受控环境存在。
- [x] provenance 与 tarball SHA-256 一致。
- [x] 公开报告已脱敏。
- [x] D1/D3 只引用 verified 结果并保留适用范围。
- [x] `status.md` 与 `log.md` 由最终收口统一维护。

历史实现细节可从 Git 历史查看；本文不再保留过时的未勾选交接清单，避免被误读为当前 blocker。
