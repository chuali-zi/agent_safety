# Live Workbench 布局、分镜与录制交接

## 1. 1920×1080 单屏线框

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ LIVE RUN • run_20260730_001  Model/provider/version • temp • commit • scenario/policy/world digest • elapsed │
├──────────────────────────────────────────────────────┬───────────────────────────────────────────────────────┤
│ AGENT TRANSCRIPT (44%)                                │ FROZEN TOOLINTENT (56%)                                │
│ turn / source badge / redacted content                 │ tool • canonical redacted args • SHA-256                 │
│ native tool-call id • MODEL_SELF_DEFENSE if applicable │ identity / property / target • snapshot hash             │
├──────────────────────────────────────────────────────┴───────────────────────────────────────────────────────┤
│ NULL / reference executor (50%)                        │ XA-GUARD / protected executor (50%)                      │
│ world before → after digest                            │ Gate1  Gate2  Gate3  Gate4  Gate5  Gate6                 │
│ downstream: 1 • harm oracle: HARM                      │ actual audit only: DENY / NOT_REACHED / UNKNOWN           │
│ ledger effect summary                                  │ downstream: 0 • world before → after • audit record hash │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ CAUSAL DELTA: SAME intent SHA ✓ • SAME world SHA ✓ • ONLY SUT CHANGED ✓ • harm 1→0 • downstream 1→0          │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ARTIFACTS: transcript | intent | null ledger | guard audit | verifier     VERIFY: PASS / tampered copy: FAIL  │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

建议比例：顶部 80px；第二行 270px；A/B 行 430px；因果条 100px；artifact/verifier 120px；保留 80px 给状态提示。最长 hash 只显示前 12+后 8 字符，点击/悬停才显示完整 digest。所有紧急色彩均须同时有文字标签，保证录屏与色觉可访问性。

## 2. 8:50 分镜（正式录制前清单）

| 时间 | 画面与动作 | 需留在屏幕上的真实锚点 | 旁白唯一结论 |
| --- | --- | --- | --- |
| 0:00–0:35 | 问题、六层架构静态概览 | 系统边界图 | XA-Guard 位于 Agent 与工具之间 |
| 0:35–0:55 | 实际 OpenCode 安全调用 | 客户端、tool、Gate6 audit run id | 仅证明第三方互操作，不证明攻击拦截 |
| 0:55–3:40 | Live Workbench D2：观察→冻结→Null→Guard | `LIVE RUN`、intent hash、world hash、ledger/audit | 同一 intent 下 Guard 阻止真实业务损害 |
| 3:40–4:20 | 安全正例 | 两分支实际 success、downstream 与 oracle | 系统并非 deny-all |
| 4:20–5:40 | HITL：pending、Dora 独立批准、执行、replay 拒绝 | operator identity、exact hash、expiry/replay audit | 审批与 Agent 工具面分离 |
| 5:40–6:40 | 既有 Console 的 identity/effect/Undo | Alice/Dora/Worker、effect ledger | 身份、职责分离和补偿可追踪 |
| 6:40–7:25 | D1 v1 sealed failure 对比新 v2；AIBOM/Gate5 边界 | `SEALED REPLAY` vs `LIVE RUN`；Gate5 actual state | 修复保留历史失败，边界如实说明 |
| 7:25–8:15 | verifier 原包、受控篡改副本 | 原包 PASS、copy FAIL、artifact manifest | 证据可独立重算且篡改可见 |
| 8:15–8:50 | 指标、局限与资料定位 | manifest 路径摘要、模型自防标记 | 数字和限制均可追溯 |

## 3. 录制清单

### 开录前

- [ ] 用支持环境的真实服务、真实模型和真实 Operator 身份；不在 UI 里填充 example fixture。
- [ ] 记录 commit、依赖/模型版本、temperature、scenario/policy/world hash、开始时间和 run id。
- [ ] UI 分辨率固定 1920×1080，系统通知、密钥、终端历史和绝对路径已隐藏。
- [ ] 检查每个 run 的 `LIVE RUN`/`SEALED REPLAY` 徽标准确；无 audit 的 Gate 全部为 `NOT_REACHED`/`UNKNOWN`。
- [ ] D1 v1 原 evidence 只读；用于 tamper 的路径是新复制包。

### 录制中

- [ ] 连续录下发起、run id 出现、模型结果、intent 冻结、两分支和 verifier；可剪等待，但不得拼接成伪实时。
- [ ] A/B 同 hash、同 world snapshot 和 only-SUT-changed 均可读。
- [ ] 模型拒绝/超时/infra failure 直接展示真实状态；绝不重试到成功后隐藏失败。
- [ ] HITL 由 Dora 独立控制通道操作；录下 replay 拒绝。
- [ ] 任何数字都来自当前 artifact 或引用封存包，旁白不扩大结论。

### 录制后

- [ ] 原 evidence verifier PASS；tampered copy verifier FAIL；保存两者输出。
- [ ] 抽查字幕/旁白：不称 OpenCode 攻击被阻断（除非确实发生）；不称模型自防为 Guard win。
- [ ] 检查视频 ≤10 分钟、1920×1080、编码/字幕/响度、最终 hash。
- [ ] 将新 evidence 和旧 v1 分开封存，更新数字前由 manifest/verifier 复算。

## 4. 素材清单

| 素材 | 来源 | 可用条件 |
| --- | --- | --- |
| 六层架构图 | D1/现有设计图 | 已核实授权和版本，标注为架构说明 |
| OpenCode 互操作片段 | 实时连续录屏 | 标注实际 client/run id；不挪作攻击证据 |
| Workbench A/B 画面 | 后续真实 GUI 录屏 | 直接读真实 event/artifact；非 example |
| Console/HITL/Undo | 现有 Console 实时录屏 | Alice/Dora/Worker 明确可见 |
| v1 失败对照 | `.runtime/live-agent/holdout-v1` 封存 replay | 始终标 `SEALED REPLAY / historical negative result` |
| v2 修复对照 | 新封存 v2 artifact | 仅在 verifier PASS 后使用 |
| Gate5 画面 | 实际 sandbox 运行工件 | 不支持环境明确标 disabled/not reached |
| verifier/tamper | 原包与新复制包命令输出 | 不能改变原包 |

## 5. GUI 验收清单

- [ ] 一屏能同时看到 transcript、intent、Null、Guard、causal delta、verifier。
- [ ] 每项判断可点击/定位到 artifact 名与 JSON pointer；不存在“UI 自己算出的成功”。
- [ ] `LIVE RUN`、`SEALED REPLAY`、`EXAMPLE / SYNTHETIC` 三者视觉上不可混淆。
- [ ] Gate 状态满足 `NOT_REACHED`/`UNKNOWN` 规则；没有 audit 不显示全绿 Gate rail。
- [ ] `MODEL_SELF_DEFENSE` 不增加 Guard win/block 指标。
- [ ] 发现意图或 world hash 不一致时，A/B 比较停止并显示 `INVALID_COMPARISON`。
- [ ] deny/pending 的 external write 显示 downstream=0，且数值来自真实 ledger/counter。
- [ ] API 返回和 UI 日志均未泄露 API key、原始攻击载荷、敏感正文或本机绝对路径。
