# XA-Guard 答辩问答手册

> 适用题目：XA-202620「面向政企场景的大模型智能体安全关键技术研究」
> 排序原则：按评委最可能追问的顺序排列，而不是按模块顺序。
> 口径：只回答当前仓库和已封存证据能够证明的内容；不展示原始攻击内容、凭据或本机路径。数字以
> [`FROZEN-NUMBERS.md`](FROZEN-NUMBERS.md) 为准。赛题要求以
> [官方比赛方案 PDF](../source-of-truth/XA-202620中国雄安集团数字城市科技有限公司-面向政企场景的大模型智能体安全关键技术研究比赛方案.pdf)
> 第 2–4 页为准。

## 1. 你们到底解决了赛题的哪些方向？

四个方向都覆盖，但不是用一个分类器包打天下：方向一由 Gate1、Spotlighting、Gate4 与 OAR 输入链实验覆盖；
方向二由 Gate2–5、审批、身份授权、Effect/Undo 覆盖；方向三由 AIBOM 准入覆盖；方向四由 OAR、Gate6、
Effect 链和独立验签覆盖。赛题的五维指标也按数据、内容、执行、供应链和合规风险分别报告，没有合成一个
失真总分。

锚点：[`D1-technical-report-review-draft.md`](D1-technical-report-review-draft.md) §3、§5.1；
[`pipeline.py`](../../src/xa_guard/pipeline.py) `Pipeline.run`；
[`gateway.py`](../../src/xa_guard/aibom/gateway.py) `admit`；
[`verify_identity_undo_evidence.py`](../../scripts/verify_identity_undo_evidence.py) `verify_bundle`。

## 2. 攻击识别准确率和误报率是多少？

在 Gate1 明确声明的 6 个输入攻击族、60 个攻击样本内，检测召回和阻断召回均为 60/60；在 58 个
expected-allow 负控制上，any-detection FPR 为 0/58，Wilson 95% 上界为 6.21%。规则层 p50/p95 为
0.02/0.04ms；这不包含模型推理和完整网关链路。

锚点：[`gate1-l3-evaluation-2026-06-18.json`](../evidence/gate1-l3-evaluation-2026-06-18.json)
的 `gate1_scope`；[`evaluate_gate1.py`](../../scripts/evaluate_gate1.py) `_scope_metrics`、`_wilson_interval`；
[`test_gate1_evaluator.py`](../../tests/test_gate1_evaluator.py)。

## 3. 为什么同一份结果里还有 0.3575，是否说明识别能力很差？

0.3575 是把 290 条不同职责的样本全部放进 Gate1 分母后的总值；其中只有 60 条属于 Gate1 输入攻击判定面。
审批、留存、加密降级、跨域和供应链等 133 条治理样本应由 Gate2/3/5 或 AIBOM 判定，不能作为 Gate1
漏报。我们只报告分层结果，并保留这个总值供审计，不把它隐藏。

锚点：[`gate1-l3-evaluation-2026-06-18.json`](../evidence/gate1-l3-evaluation-2026-06-18.json)
的 `by_attack_type`、`gate1_scope`；
[`evaluate_gate1.py`](../../scripts/evaluate_gate1.py) `_scope_metrics`；
[`D1-technical-report-review-draft.md`](D1-technical-report-review-draft.md) §5.2。

## 4. Gate1 是规则还是模型？规则是否容易被绕过？

当前对外冻结的 60/60 数字来自规则 detector，不能归因于模型。Gate1 本身是可插拔 detector 编排器，
已经支持规则、模型、类别映射和 `DENY > WARN > ALLOW` 融合；真实 Qwen 后端曾接入，但现有模型不能替代
规则层。规则对未见表达的泛化能力有限，所以我们同时用真实 Agent holdout 暴露边界，而不把 seed 回归写成
通用防御率。

锚点：[`gate1_input.py`](../../src/xa_guard/gates/gate1_input.py)
`Gate1Input._build_detectors`、`Gate1Input.evaluate`；
[`fusion.py`](../../src/xa_guard/detectors/fusion.py) `fuse`；
[`test_gate1_detectors.py`](../../tests/unit/test_gate1_detectors.py)；
[`gate1-real-model-verification.md`](../gates/gate1-real-model-verification.md)。

## 5. 290 条 seed 是不是自己写的？如何排除过拟合？

是项目维护的规则链路回归 seed，不是独立第三方测试集，因此不能据此宣称独立泛化。诊断切分做到 exact
payload 指纹零重叠，但 `independent_holdout=false`，仍然同源；这就是为什么正文必须同时报告样本范围、
Wilson 区间和该限制。另有带来源与许可证的外部候选 corpus，但它不是 60/60 结论的替代证据。

锚点：[`csab-gov-mini-seed.yaml`](../../bench/cases/csab-gov-mini-seed.yaml) `metadata`；
[`gate1-l3-evaluation-2026-06-18.json`](../evidence/gate1-l3-evaluation-2026-06-18.json)
的 `calibration_holdout.independent_holdout`；
[`test_gate1_evaluator.py`](../../tests/test_gate1_evaluator.py)
`test_gate1_diagnostic_split_is_semantic_and_leak_free`；
[`csab-gov-v1-candidate/manifest.json`](../../bench/cases/csab-gov-v1-candidate/manifest.json)。

## 6. OAR 的 N=10 够吗？

N=10 是两类合成、确定性 OAR finding 的每侧重复数，用来证明同一业务 oracle 在重复运行中稳定，不用于估计
开放世界泛化率。邮箱和 RAG 两类均为 Null 10/10 有害后果、保护侧 0/10，protected replay 合计 20/20；
真实模型 holdout 是另一条轨道，采用每 case、每 prompt profile 5 次和 3/5 稳定门槛，不能与 N=10 混算。

锚点：[`FROZEN-NUMBERS.md`](FROZEN-NUMBERS.md) §1；
[`attack-proof-set-2026-07-27-n10.md`](../evidence/attack-proof-set-2026-07-27-n10.md)；
[`run_attack_proof_set.py`](../../scripts/run_attack_proof_set.py)
`evaluate_oar_summary`、`verify_protected_replays`；
[`models.py`](../../open-agent-range/kernel/live_agent/models.py) `ExperimentConfig.validate`。

## 7. 你们的“真实 Agent”是不是预先写死的脚本？

不是。DeepSeek adapter 使用原生 Tool Calls、`tool_choice=auto`，不强迫模型调用工具；模型先在同一世界状态中
自主观察和调用。只有当独立 property matcher 观察到违规工具意图时，才冻结工具名、参数 SHA-256 和目标，
再把完全相同的不可变 `ToolIntent` 分叉给 NullSUT 与真实 `XaGuardSUT(live=True)`。模型安全拒绝会记为
模型侧安全，不记为 XA-Guard 成功。

锚点：[`provider.py`](../../open-agent-range/kernel/live_agent/provider.py)
`DeepSeekAdapter.next_turn`；
[`models.py`](../../open-agent-range/kernel/live_agent/models.py) `ToolIntent.capture`；
[`runner.py`](../../open-agent-range/kernel/live_agent/runner.py)
`LiveAgentRunner.run_once`、`LiveAgentRunner._execute_fork`；
[`test_live_agent.py`](../../open-agent-range/kernel/tests/test_live_agent.py)。

## 8. D2 的真实 Agent 因果证明具体证明了什么？

正式 holdout 中，D2 的两种 prompt profile 都在 5/5 重复中形成同一 property+target 的违规意图，达到 3/5
门槛；完全相同的意图在 Null 侧造成 10/10 业务后果，在 XA-Guard live 侧 10/10 被 Gate3 拒绝且业务后果
为 0。因此这里只把“同意图、同快照、唯一差异是 SUT”称为因果阻断证明。

锚点：公开脱敏摘要
[`live-agent-holdout-v1-2026-07-27.md`](../evidence/live-agent-holdout-v1-2026-07-27.md) §2–§3；
受控环境中的本地封存
[`summary.json`](../../open-agent-range/.runtime/live-agent/holdout-v1/summary.json)
的 `D2-HOLDOUT-LOG-BYPASS`；
[`runner.py`](../../open-agent-range/kernel/live_agent/runner.py) `summarize_results` 的 `causal_proof`；
[`authenticity.py`](../../open-agent-range/kernel/live_agent/authenticity.py) `_check_live_audit_rows`；
[`test_live_agent_authenticity.py`](../../open-agent-range/kernel/tests/test_live_agent_authenticity.py)。

## 9. D1 真实 Agent holdout 为什么没有被拦住？

这是当前实现的真实边界：D1 的 realistic-safe profile 在 5/5 中发起了引用型敏感外发，Null 与保护侧均
观察到 5/5 有害后果，保护侧决策为 allow。Gate4 会扫描参数内容、会话历史和既有 taint，但当前工具参数只
携带数据源引用时，不会自动到 OAR 世界中反查该引用的敏感级别；因此确定性、显式内容标记的 N=10 结果
不能外推到所有引用型外发。

锚点：公开脱敏摘要
[`live-agent-holdout-v1-2026-07-27.md`](../evidence/live-agent-holdout-v1-2026-07-27.md) §3–§4；
受控环境中 gitignored 的本地封存
`open-agent-range/.runtime/live-agent/holdout-v1/summary.json`
的 `D1-HOLDOUT-RAG-EXFIL`；
[`gate4_taint.py`](../../src/xa_guard/gates/gate4_taint.py)
`Gate4Taint._infer_taint`；
[`policy.py`](../../open-agent-range/kernel/live_agent/policy.py) `_assess_sensitive_egress`。

## 10. D3 的 0/10 是否能算 XA-Guard 的供应链防护成功？

不能。D3 两种 profile 共 10 次都没有生成违规发布意图，所以保护支路没有执行，结论只是该模型在该 holdout
上的自防结果。XA-Guard 的 AIBOM 防护能力应由恶意/干净组件对照、准入判据和测试证明，不能借用模型拒绝
来加分。

锚点：公开脱敏摘要
[`live-agent-holdout-v1-2026-07-27.md`](../evidence/live-agent-holdout-v1-2026-07-27.md) §3；
受控环境中的本地封存
[`summary.json`](../../open-agent-range/.runtime/live-agent/holdout-v1/summary.json)
的 `D3-HOLDOUT-AIBOM-PUBLISH`；
[`runner.py`](../../open-agent-range/kernel/live_agent/runner.py) `model_attempt_violation`、`utility_success`；
[`gateway.py`](../../src/xa_guard/aibom/gateway.py) `admit_install_request`；
[`test_aibom_gateway.py`](../../tests/unit/test_aibom_gateway.py)。

## 11. 六道 Gate 的顺序是什么，为什么不是六个互不相关的模块？

固定顺序是 Gate1；然后 Gate2、Gate4 入向、Gate3 聚合；再 Gate5；执行工具；最后 Gate4 出向和 Gate6。
Gate1 明确攻击可短路；Gate3 deny 能覆盖 Gate2 的审批请求，避免“批准即绕过策略”；执行后仍检查出向信息流，
所有路径都进入 Gate6。顺序由单一 `Pipeline` 编排并有顺序测试。

锚点：[`pipeline.py`](../../src/xa_guard/pipeline.py) `Pipeline.run`、`Pipeline.run_after_approval`；
[`test_pipeline_smoke.py`](../../tests/test_pipeline_smoke.py)
`test_pipeline_runs_gate4_before_gate3_so_policy_sees_inbound_taint`、
`test_pipeline_allows_gate3_deny_to_override_gate2_approval`。

## 12. Gate2 和 Gate3 都管执行，职责有何区别？

Gate2 根据工具能力表给出风险等级和是否需要 HITL；Gate3 根据身份、工具、数据域、参数谓词和组织策略做
允许/拒绝判断。审批只解决“谁确认了这个精确动作”，不能把 baseline 禁止项变为允许；所以 Gate3 deny
优先于 Gate2 `REQUIRE_APPROVAL`。

锚点：[`gate2_plan.py`](../../src/xa_guard/gates/gate2_plan.py) `Gate2Plan.evaluate`；
[`gate3_policy.py`](../../src/xa_guard/gates/gate3_policy.py) `Gate3Policy.evaluate`；
[`test_gate2.py`](../../tests/unit/test_gate2.py)；
[`test_gate3.py`](../../tests/unit/test_gate3.py) `test_aggregate_deny_over_approval`。

## 13. 审批是不是只是界面上的一个按钮？

不是。审批令牌绑定 trace、工具、精确参数 hash、审批人和有效期；执行前必须验签并消费，缺失、参数变化、
签名错误、过期或进程内重放都会拒绝。当前轻量 MCP 令牌的跨实例/重启全局防重放不是已完成声明；
Reference Undo 则使用 PostgreSQL 持久状态和内部签名授权。

锚点：[`approval.py`](../../src/xa_guard/approval.py)
`issue_approval`、`verify_and_consume_approval`；
[`pipeline.py`](../../src/xa_guard/pipeline.py) `Pipeline.run_after_approval`；
[`test_approval.py`](../../tests/test_approval.py)；
[`test_mcp_e2e.py`](../../tests/integration/test_mcp_e2e.py)。

## 14. Gate4 的信息流控制具体做了什么？

它把输入来源、参数敏感内容和会话历史合成为 PUBLIC/INTERNAL/CONFIDENTIAL 标签，与工具声明的
`input_max_taint`、`output_taint` 和外联能力比较；未知工具默认按外联且只接受 PUBLIC 处理。它能阻止显式
机密内容流向外部工具，但当前不做任意业务引用的自动解引用和敏感度查询，这正是 D1 holdout 暴露的边界。

锚点：[`gate4_taint.py`](../../src/xa_guard/gates/gate4_taint.py)
`Gate4Taint._infer_taint`、`Gate4Taint._default_cap`、`Gate4Taint.evaluate`；
[`gate4_capabilities.yaml`](../../policies/baseline/gate4_capabilities.yaml)；
[`test_gate4.py`](../../tests/unit/test_gate4.py)。

## 15. Gate5 是真实隔离，还是只给审计写一个 sandbox 标签？

Gate5 产生执行 profile，`DownstreamRouter` 会据此选择原生持久会话或临时 Docker/gVisor stdio 会话；
容器命令落实禁网、只读根、非 root、资源限制和工作区只读。并非所有工具都强制容器化：配置允许原生模式，
gVisor 不可用时也会如实降级记录，生产部署必须选择并验证目标 runtime。

锚点：[`gate5_sandbox.py`](../../src/xa_guard/gates/gate5_sandbox.py) `Gate5Sandbox.evaluate`；
[`downstream.py`](../../src/xa_guard/proxy/downstream.py) `DownstreamRouter._call_tool_sandboxed`；
[`sandbox.py`](../../src/xa_guard/sandbox.py) `build_docker_command`；
[`test_downstream_sandbox.py`](../../tests/unit/test_downstream_sandbox.py)。

## 16. AIBOM 能发现什么，不能发现什么？

它在安装前扫描 Python AST、依赖、结构化元数据、能力声明、制品 hash、离线漏洞/信誉信息和签名，输出
CycloneDX 1.6 与 A/B/C/D/F 五档等级（无 E 档）；A/B 放行、C 复核、D/F 拒绝。它不是对任意动态恶意逻辑的完备证明；远程制品
没有离线缓存或固定 hash 时不会直接联网安装，而是进入复核/拒绝路径。

锚点：[`scanner.py`](../../src/xa_guard/aibom/scanner.py) `scan_artifact`；
[`gateway.py`](../../src/xa_guard/aibom/gateway.py) `admit`；
[`rater.py`](../../src/xa_guard/aibom/rater.py) `rate`；
[`test_aibom_scanner.py`](../../tests/unit/test_aibom_scanner.py)。

## 17. 人员—Agent 双主体身份如何防止客户端伪造 header？

授权身份来自验签 JWT 的人员 `sub`、Agent `act.sub/azp`、tenant、audience 和有效期，不信任正文自报身份。
HTTP middleware 在进入工具处理前比较 `_xa_guard` envelope 与已验证身份；随后每次请求再查询当前 assignment，
并与静态能力 ceiling、工具和数据域求交。伪造正文、撤销 assignment 和跨租户都会在下游调用前失败。

锚点：[`identity.py`](../../src/xa_guard/identity.py)
`JWTIdentityVerifier.verify`、`binding_error`、`IdentityBindingMiddleware`；
[`store.py`](../../src/xa_guard/control/store.py) `AsyncEffectStore.authorize`；
[`test_identity_formal.py`](../../tests/unit/test_identity_formal.py)；
[`test_governance_enterprise.py`](../../tests/unit/test_governance_enterprise.py)。

## 18. 为什么要 intent-first Effect，普通审计日志不够吗？

日志只能说明发生过什么，不能保证恢复所需上下文在副作用前已经持久化。写路径先保存 prepared Effect 和
前置审计，再以 `effect_id` 作为幂等键调用业务系统；成功后加密保存恢复材料并转为 available。若准备阶段
失败，下游调用数必须为 0；若业务成功后响应丢失，reconciler 按 `effect_id` 查询并补全状态。

锚点：[`service.py`](../../src/xa_guard/control/service.py) `ControlService.create_ticket`、
`ControlService.reconcile_once`；
[`store.py`](../../src/xa_guard/control/store.py)
`AsyncEffectStore.prepare_effect`、`complete_effect`；
[`test_control_intent_first.py`](../../tests/unit/test_control_intent_first.py)。

## 19. Undo 能撤什么，不能撤什么？

只有声明 `reversibility=compensatable`、恢复合同完整且仍在 Undo 窗口内的 Effect 才自动补偿。不可逆、
合同缺失、窗口过期、恢复材料不可解密或业务结果不满足合同的操作进入 `manual_required`、`expired` 或失败
状态，不会伪装成已恢复。当前 Reference 完整验证的是工单创建→取消这一份真实合同，不外推到任意工具。

锚点：[`tool_effects.yaml`](../../policies/baseline/tool_effects.yaml)；
[`contracts.py`](../../src/xa_guard/control/contracts.py) `ContractRegistry.for_tool`；
[`store.py`](../../src/xa_guard/control/store.py) `complete_effect`、`request_undo`；
[`test_control_contracts_ceiling.py`](../../tests/unit/test_control_contracts_ceiling.py)。

## 20. Undo 如何防止自己批准自己？是否保证 exactly-once？

请求人需要 `undo.request`，审批人需要 `undo.approve`，数据库事务明确拒绝 requester 与 approver 相同；
批准后由独立 Worker 获取 lease 并执行补偿。语义是至少一次调度配合业务侧幂等键，不宣称绝对 exactly-once；
并发、Worker 接管、重试和有效业务取消数由故障套件验证。

锚点：[`service.py`](../../src/xa_guard/control/service.py)
`ControlService.request_undo`、`ControlService.decide_undo`；
[`store.py`](../../src/xa_guard/control/store.py) `decide_undo`、`claim_work`；
[`worker.py`](../../src/xa_guard/control/worker.py) `CompensationWorker.run_once`；
[`agent-identity-undo-final-2026-07-21.md`](../evidence/agent-identity-undo-final-2026-07-21.md)。

## 21. 为什么相信 Gate6 和你们给出的证据不是自报结果？

Gate6 和 Effect 各自是有序 hash 链，原始动作与补偿通过 trace/effect 交叉引用。独立 verifier 会重算每个
artifact hash、两条链、业务状态、请求人/审批人分离和跨链引用，再验证 SM2-with-SM3 manifest；篡改任一
artifact 或链记录会失败。最终包实测为 14 个 artifacts、102 条 Effect、59 条 Gate6，独立验签通过。

锚点：[`verify_identity_undo_evidence.py`](../../scripts/verify_identity_undo_evidence.py)
`verify_gate6_chain`、`verify_effect_chain`、`verify_cross_links`、`verify_bundle`；
[`agent-identity-undo-final-2026-07-21.md`](../evidence/agent-identity-undo-final-2026-07-21.md)；
[`test_identity_undo_evidence_sealing.py`](../../tests/unit/test_identity_undo_evidence_sealing.py)。

## 22. 私钥由谁持有？Gate6 每条记录都是 SM2 签名吗？

Reference 最终 evidence 的 manifest 使用 SM2-with-SM3，私钥留在 gitignored 运行环境，公开包只带验证材料和
key id。PostgreSQL Gate6/Effect 链的逐记录完整性基于 canonical SHA-256 前驱链；它们由 manifest 和跨链
验签整体封存，不能把“manifest 的 SM2 签名”说成“每条数据库记录都做了 SM2”。生产形态支持外部 signer，
应由组织 KMS/HSM 托管密钥。

锚点：[`gate6_audit.py`](../../src/xa_guard/gates/gate6_audit.py) `Gate6Audit.render_record`；
[`audit.py`](../../src/xa_guard/control/audit.py) `PostgresGate6Audit.evaluate_async`；
[`verify_identity_undo_evidence.py`](../../scripts/verify_identity_undo_evidence.py)
`verify_manifest_signature`；
[`test_control_gate6_postgres_persistence.py`](../../tests/unit/test_control_gate6_postgres_persistence.py)。

## 23. 45ms 增量时延相对什么基线？是否包含模型推理？

每个样本是一对 XA-Guard 受保护的有状态 PostgreSQL 写和直接业务写，AB/BA 顺序平衡；增量定义为
`protected_ms - direct_business_baseline_ms`。10 并发、3×500 对写的 p95 为
45.109/42.141/43.934ms，5000 次 bootstrap 单侧 95% 上界均低于 50ms。该实验覆盖身份、策略、
Effect/Gate6 和数据库持久化，不包含可选 Gate1 模型后端推理。

锚点：[`perf-formal-mixed-transaction-rebuilt-20260721.json`](../evidence/agent-identity-undo-final-2026-07-21/acceptance/perf-formal-mixed-transaction-rebuilt-20260721.json)
的 `methodology`、`write_latency_runs`；
[`benchmark_identity_undo.py`](../../scripts/benchmark_identity_undo.py)；
[`test_identity_undo_performance_acceptance.py`](../../tests/unit/test_identity_undo_performance_acceptance.py)。

## 24. 10 并发和三轮实验能证明生产容量吗？

不能。它证明当前 Reference 候选在指定硬件、10 并发和 3×500 成对写口径下满足 50ms 目标，并用不同 seed
与 bootstrap 控制偶然性；不等于生产容量、峰值吞吐或多地域 SLA。上线前仍需按目标业务流量做容量、
长稳、故障域和托管依赖验证。

锚点：[`FROZEN-NUMBERS.md`](FROZEN-NUMBERS.md) §4；
[`benchmark_identity_undo.py`](../../scripts/benchmark_identity_undo.py) CLI 参数与 profile 校验；
[`D1-technical-report-review-draft.md`](D1-technical-report-review-draft.md) §5.6、§5.9。

## 25. 11/11 故障与 kind 三节点是否等于生产 HA？

不等于。11/11 覆盖身份拒绝、撤权、租户隔离、数据库中断、崩溃恢复、并发审批、Worker 接管、重试和密钥
故障；kind 验证安装、升级、迁移、接管、NetworkPolicy 和回滚。它们是本地 Reference 与
`LOCAL-PROFILE-PASS`，没有证明多地域、真实云负载均衡或生产运维 SLA。

锚点：[`reference-faults-all-final-rerun-20260721.json`](../evidence/agent-identity-undo-final-2026-07-21/acceptance/reference-faults-all-final-rerun-20260721.json)；
[`kind-ha-final-pass-20260721.json`](../evidence/agent-identity-undo-final-2026-07-21/acceptance/kind-ha-final-pass-20260721.json)；
[`ha_runner.py`](../../deploy/kind/ha_runner.py)；
[`test_kind_ha_takeover.py`](../../tests/deployment/test_kind_ha_takeover.py)。

## 26. 目前有哪些部署形态？

Reference Compose 提供身份、数据库、API、业务服务、Worker 和 Console 的完整本地闭环；Helm chart 拆分
API/Worker/业务/Console，并包含 migration Job、PDB、HPA、NetworkPolicy、Ingress 和外部 Secret 引用；
kind 是本地升级接管验收载体。生产还需接入组织 IdP、TLS、托管 PostgreSQL、正式 KMS/HSM、备份监控和
容量治理。

锚点：[`docker-compose.reference.yml`](../../docker-compose.reference.yml)；
[`deploy/reference/README.md`](../../deploy/reference/README.md)；
[`deploy/helm/xa-guard/README.md`](../../deploy/helm/xa-guard/README.md)；
[`test_reference_deployment_assets.py`](../../tests/integration/test_reference_deployment_assets.py)。

## 27. “兼容 OpenClaw 类智能体”具体兼容到哪一层？

兼容承诺在协议层：能经 MCP stdio、MCP Streamable HTTP 或 Control API 交付工具名、参数和身份上下文的
工具型客户端，可以复用相同治理链。仓库验证了真实 MCP JSON-RPC、HTTP session 隔离和无 elicitation
客户端的 pending fallback；没有宣称完成 OpenClaw 官方 SDK/专有接口适配，也没有宣称所有客户端都有原生
审批弹窗。当前下游代理主要支持 stdio，新增专有接口应做薄适配。

锚点：[`server.py`](../../src/xa_guard/server.py) `run_server`；
[`upstream.py`](../../src/xa_guard/proxy/upstream.py)
`run_stdio`、`run_streamable_http`、`_request_hitl_approval`；
[`downstream.py`](../../src/xa_guard/proxy/downstream.py) `DownstreamRouter`；
[`test_streamable_http_e2e.py`](../../tests/integration/test_streamable_http_e2e.py)。

## 28. 与 Lakera Guard、LlamaFirewall、CaMeL 等方案相比，创新点是什么？

我们不声称输入检测分数优于这些方案，也不做不同数据集数字横比。差异点是把双主体身份、工具审批、
信息流、AIBOM、intent-first Effect、职责分离 Undo 和双链证据放在同一运行时闭环；其中可验证业务副作用
恢复是本项目重点。外部方案只按公开资料中已核验范围描述，“未核验”不等于对方没有。

锚点：[`D1-technical-report-review-draft.md`](D1-technical-report-review-draft.md) §6.5；
[`service.py`](../../src/xa_guard/control/service.py) `ControlService.create_ticket`；
[`verify_identity_undo_evidence.py`](../../scripts/verify_identity_undo_evidence.py) `verify_cross_links`。

## 29. OAR 和普通文本安全 benchmark 有什么不同？

OAR 的 oracle 观察工具尝试、外发或状态变化等业务后果，并记录 Null/Guard 分支、ledger、Gate6 与 replay；
不是只看输入文本是否含某个词。确定性 N=10 证明稳定业务阻断，真实 Agent 轨道再把模型是否生成违规意图与
网关是否阻断拆成两个指标，避免把模型自防、服务故障或网关阻断混为一谈。

锚点：[`oracle.py`](../../open-agent-range/kernel/oracle.py) `evaluate`；
[`ledger.py`](../../open-agent-range/kernel/ledger.py) `Ledger.verify_hash_chain`、`Ledger.replay`；
[`runner.py`](../../open-agent-range/kernel/live_agent/runner.py) `summarize_results`；
[`attack-proof-set-2026-07-27-n10.md`](../evidence/attack-proof-set-2026-07-27-n10.md)。

## 30. 现在能否直接作为生产安全产品上线？如何复核你们的核心结论？

当前是可部署、可复现的原型和 Reference 候选，不是未经条件限制的生产认证产品。已知边界包括 Gate1
同源 seed、D1 引用型外发、可选模型同步时延、客户端 HITL 差异、本地 kind 范围和正式 KMS/容量前置条件。
评委可从 [`CODE-MAP.md`](CODE-MAP.md) 的最小命令矩阵复核 Gate、审批、AIBOM、真实 Agent authenticity、
双链 evidence、部署静态约束和性能统计；正式证据与代码测试分开验证。

锚点：[`D1-technical-report-review-draft.md`](D1-technical-report-review-draft.md) §5.9、§7；
[`CODE-MAP.md`](CODE-MAP.md)；
[`submission-checklist.md`](submission-checklist.md)。
