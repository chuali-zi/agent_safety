# XA-Guard：面向政企智能体的运行时安全治理与可验证恢复

题目编号：XA-202620
文档版本：v0.2-review（讨论稿）
日期：2026-07-27

## 摘要

大模型智能体已经能够读取网页和文档、检索知识库、调用脚本与接口，并直接改变业务系统状态。
在政企场景中，安全问题因而不再局限于生成内容是否合规，还包括人员委托、智能体权限、工具执行、
数据流向、第三方组件以及错误操作后的业务恢复。

XA-Guard 是部署在智能体与工具之间的运行时安全网关。系统通过人员—智能体双主体身份建立可信委托关系，
由六道安全关卡检查输入、审批、策略、信息流、执行环境和审计；对产生业务副作用的写操作，
系统先持久化 Effect 意图，再调用下游，并在独立审批后由 Worker 执行补偿。插件、Skill 和脚本
在安装或执行前经过 AIBOM 准入检查。配套的 Open Agent Range（OAR）以真实工具调用、业务后果、
哈希账本和审计回放评价防护效果。

项目已经形成由身份服务、安全网关、PostgreSQL、业务接口、补偿 Worker、Console/BFF 和评测靶场
组成的完整原型。在 OAR 邮箱与 RAG 两类注入 finding 的本地 live A/B 对照中（每侧 N=10），未部署防护的一侧 10/10 发生合成数据泄漏，
XA-Guard 侧 10/10 阻断，保护侧基础设施错误为 0；full-day 场景完成 41 次工具尝试并产生 43 条
账本记录，未出现账本违规，7/7 次回放通过。最终候选的 11 个故障场景全部通过。本地三节点
Kubernetes 环境完成安装、升级、迁移重跑、服务接管、网络策略验证和回滚。10 并发正式性能实验中，
三轮 500 次成对写入的新增开销 p95 为 45.109、42.141 和 43.934ms，对应单侧 95% bootstrap
上界为 46.984、43.120 和 45.528ms。10 次 Undo 均在约 0.45–0.94s 内完成。

这些结果表明，智能体安全可以从单点输入检测扩展为覆盖身份、执行、副作用和证据的工程体系，
并在保留审计与一致性约束的条件下，在上述验证规模内满足交互式业务的时延要求。

**关键词：** 智能体安全；运行时治理；MCP；身份授权；工具调用；AIBOM；可验证恢复；审计溯源

---

## 1. 问题与场景

### 1.1 智能体改变了安全边界

传统问答系统主要输出文本。智能体则会把自然语言目标转换为一系列操作：读取文件、访问网页、
调用数据库、执行命令、发送消息或修改业务记录。模型的判断一旦连接到真实工具，错误的影响就会从
“回答不准确”扩大为越权访问、数据外泄和业务状态破坏。

这种风险通常沿着数据和工具链传播。恶意指令可能隐藏在网页、附件、知识库或历史记忆中，
被模型当作任务上下文读取；模型随后选择一个原本合法的工具，并在合法参数外观下执行有害操作。
第三方插件还可能改变工具描述、引入远程下载或增加隐蔽网络能力。一次攻击会沿组件链逐步形成业务动作，
最终落到真实数据和系统状态上。

```mermaid
flowchart LR
    A["网页 / 文档 / 知识库 / 记忆"] --> B["智能体上下文"]
    B --> C["计划与工具选择"]
    C --> D["插件 / Skill / 脚本"]
    D --> E["文件 / 命令 / 业务接口"]
    E --> F["业务状态与外部影响"]
```

AgentDojo 和 InjecAgent 的研究说明，间接提示注入能够通过外部数据影响工具型智能体的行为[1-2]。
CaMeL 从控制流与数据流分离的角度提出系统级防护思路[3]，IsolateGPT 则强调第三方组件和执行环境之间
的隔离[4]。这些工作共同表明，输入分类、能力约束、信息流和执行隔离需要协同工作。

### 1.2 政企系统需要回答的五个问题

政企智能体通常连接组织账号、内部数据和正式业务流程。一个可落地的安全系统至少要回答：

- 哪个人正在委托哪个智能体执行任务；
- 该智能体在当前租户和业务域内具有什么权限；
- 输入、计划和工具参数是否触发安全规则或审批；
- 写操作造成的业务副作用是否能够受控恢复；
- 身份、决策、审批、执行和恢复记录能否相互验证。

可信委托需要同时保留人员和智能体身份；即时撤权和数据域边界需要动态授权关系；
真实业务状态的恢复需要执行前保存恢复合同。XA-Guard 将这些约束放在同一条请求链中。

### 1.3 典型应用

本方案选择四类场景作为主要落点：

1. **政务办公助手**：读取公文、处理邮件、发起流程，对敏感外发和高风险写入进行控制；
2. **知识服务**：接入网页、附件和知识库，识别外部内容对后续工具调用的影响；
3. **业务流程办理**：让智能体提交工单或更新业务记录，并保留审批与恢复能力；
4. **运维协同**：调用命令、文件和网络工具，通过策略与隔离环境控制影响范围。

---

## 2. 总体方案

### 2.1 系统定位

XA-Guard 位于智能体客户端和实际工具之间。上游既可以是支持 MCP 的客户端，也可以是通过 HTTP
接入的业务应用；下游可以是文件系统、脚本、浏览器、数据库或企业 API。网关与具体大模型解耦，
安全逻辑集中在网关中，业务系统按原有接口提供工具能力。

系统由四部分组成：

- **身份与治理控制面**：OIDC、人员—智能体身份、动态授权关系、静态能力上限和审批；
- **运行时安全数据面**：输入识别、计划审核、策略、信息流、沙箱和审计；
- **副作用恢复面**：EffectStore、恢复合同、独立审批、补偿 Worker 和密钥管理；
- **评测与证据面**：OAR、Gate6、Effect 事件链、证据收集与独立验签。

```mermaid
flowchart LR
    H["人员登录"] --> I["人员—智能体身份"]
    I --> A["动态授权 ∩ 能力上限"]
    A --> G["运行时安全网关"]
    G --> T["工具 / 业务 API"]
    G --> P["Effect 意图"]
    P --> T
    T --> U["Undo 申请与审批"]
    U --> W["补偿 Worker"]
    W --> G

    G --> E["Gate6 审计"]
    P --> E
    W --> E
    E --> R["评测与证据封存"]
```

### 2.2 一次受保护写请求

人员首先通过 Authorization Code + PKCE 登录。Confidential BFF 使用 Token Exchange 取得绑定
人员和智能体的访问令牌。XA-Guard 验证签名、受众、租户和智能体身份，读取当前授权关系，
再执行六关检查。

对于只读操作，关卡通过后直接调用工具。对于写操作，网关先在 PostgreSQL 中写入 prepared Effect
和前置审计，再用 `effect_id` 作为幂等键调用业务接口。业务成功后，系统保存加密恢复材料，
将 Effect 转为 available，并写入最终审计。整个过程的身份、授权、决策和业务引用使用同一组
trace/effect 标识关联。

```mermaid
sequenceDiagram
    participant U as 人员
    participant B as Console/BFF
    participant IDP as 身份服务
    participant X as XA-Guard
    participant DB as PostgreSQL
    participant API as 业务接口

    U->>B: Authorization Code + PKCE
    B->>IDP: Token Exchange
    IDP-->>B: 人员—智能体令牌
    B->>X: 工具请求
    X->>DB: 读取动态授权
    X->>X: 六关检查
    X->>DB: prepared Effect + 前置审计
    X->>API: effect_id 幂等调用
    API-->>X: 业务结果
    X->>DB: available Effect + 最终审计
    X-->>B: 结果、trace 与 effect 引用
```

### 2.3 部署组成

Reference 环境由 PostgreSQL、Keycloak、XA-Guard API、补偿 Worker、工单业务接口和
Console/BFF 组成。Helm chart 将 API、Worker、Business API 和 Console 拆分部署，
并包含 migration Job、Secret/ConfigMap 引用、NetworkPolicy、PDB、HPA 和 Ingress 配置。
同一套核心代码既服务 MCP 调用，也服务带身份和副作用合同的业务写路径。

---

## 3. 关键技术设计

### 3.1 人员—智能体双主体身份

XA-Guard 将智能体作为受人员委托的独立行动主体，在访问令牌中同时保留人员 `sub`、智能体
`act.sub/azp`、租户、受众和有效期。服务端以签名令牌中的身份为授权依据，客户端自报的 Agent
或 tenant header 不参与授权判断。

一次请求的有效权限由四部分共同决定：

```text
有效权限 =
  已验证的人员—智能体身份
  ∩ 当前有效的人员/用户组—智能体授权关系
  ∩ 智能体静态能力上限
  ∩ 工具、数据域和参数策略
```

动态授权关系保存在 PostgreSQL 中，每次请求重新匹配。撤销某个人与智能体之间的关系后，
下一次调用立即失去权限，不需要等待旧令牌过期。静态 YAML ceiling 是不可突破的能力上限，
管理员只能在上限内授权。

这一设计使用 RFC 7636 的 PKCE 保护登录流程[5]，通过 RFC 8693 Token Exchange 的 subject/actor
语义表示委托[6]，并遵循 OAuth 安全最佳实践中的受众校验和最小权限原则[7]。MCP HTTP 授权规范
同样要求访问令牌绑定目标资源，并禁止把上游令牌原样透传给下游[8]。

### 3.2 六关运行时控制

六关共同组成一次工具调用的固定处理顺序。

| 关卡 | 处理对象 | 主要工作 |
|---|---|---|
| Gate1 输入安全 | 用户输入、网页、文档、检索与工具输出 | 规范化、来源风险、规则/模型融合、Spotlighting |
| Gate2 计划与审批 | 工具、参数和副作用等级 | 风险分级、pending、审批摘要绑定 |
| Gate3 策略 | 身份、工具、数据域和参数 | baseline/overlay 合并、谓词检查、默认拒绝 |
| Gate4 信息流 | 来源标签、敏感字段和外发目标 | 入向标签、出向 DLP、敏感流向控制 |
| Gate5 执行约束 | 文件、命令、网络和资源 | 执行 profile、只读根、非 root、资源与网络限制 |
| Gate6 审计证据 | 身份、决策、审批、结果和 trace | 规范化记录、前驱 hash、签名和完整性检查 |

Gate1 对明确攻击直接短路。Gate2、Gate4 入向检查和 Gate3 在执行前汇总决策，策略拒绝优先于审批；
通过审批后仍需执行 Gate5。工具返回结果后，Gate4 再检查出向数据，Gate6 保存最终记录。
这套顺序避免把审批按钮变成绕过策略的通道，也避免沙箱替代业务授权。

Gate1 的 Detector 接口允许组合规则检测与模型后端；Gate3 使用不可弱化的 baseline 和企业 overlay；
Gate4 把数据来源与敏感度带入后续工具调用；Gate5 根据能力选择执行环境。各关卡的命中规则、
风险标签和最终决策统一进入 Gate6。

### 3.3 算法设计

XA-Guard 的算法不是单点分类器，而是围绕“输入识别、策略判定、可恢复副作用和可验证证据”形成的组合判定链。
每项算法均绑定输入、输出和失败行为，便于在证据中复核。

| 算法 | 输入 | 处理与输出 | 失败行为 |
|---|---|---|---|
| 规则与模型融合评分 + 阈值标定 | `GateContext`、输入文本、来源、YAML 规则、可选模型 detector 标签、评估样本 | Gate1 先归一化为 `DetectionInput`，规则 detector 产生风险标签，模型 detector 可按阈值和 category map 补充标签；Fusion 按 `DENY > WARN > ALLOW` 聚合。评估脚本在 `fpr_limit=0.01` 约束下选 `selected_threshold=1.0`，并报告召回、误报和 Wilson 区间。 | 当前封存 Gate1 数字来自 `detectors=rule`，不归因给模型；模型后端不可用时默认 fail-open 不投票；非 fail-open detector 异常时转为拒绝。 |
| Spotlighting 不可信内容结构隔离 | 输入来源、工具返回、检索片段、网页或文档内容 | 对非 user 来源内容包裹 `<untrusted_source type="...">...</untrusted_source>`，把结构化来源写入检测输入和审计元数据，后续规则与模型在同一格式上判定。 | 纯 user 输入或空来源不处理；Spotlighting 本身不直接阻断，阻断由后续 detector 与 Fusion 决定。 |
| 参数谓词受限表达式与 AST 白名单 | baseline/overlay 策略谓词、身份、工具、参数和数据域 | baseline 只在无 builtins 的受限环境求值；overlay 先经过 AST 白名单，只允许比较、布尔、常量、属性、下标和白名单函数；Gate3 对命中工具执行谓词并聚合决策。 | overlay 语法错误或不安全 AST 在加载期拒绝该 overlay；Gate3 后端不可用时写路径失败关闭；单条 predicate 运行异常按未命中处理，不宣称全局 fail-closed。 |
| baseline ∩ overlay 策略合并与 bundle hash | baseline manifest、租户 overlay、工具风险、能力和敏感模式 | 先加载全局 baseline，再加载租户 overlay；单调性检查阻止 overlay 覆盖 baseline、弱化风险、放宽能力或重复敏感模式；合并结果带 `bundle_sha`，写入决策元数据。 | overlay 加载或单调性失败时拒绝该 overlay；reload 异常保留旧 snapshot；运行时可用期望 bundle hash 检测漂移。 |
| 双链定序加锁 + 链尾 CAS + 同租户微批 | Effect mutation、Gate6 mutation、tenant、trace 和业务引用 | 同租户请求先进入进程内微批队列，再在 PostgreSQL 事务中按固定顺序写 Effect/Gate6；`xa_chain_tails` 保存期望链尾，CAS 推进 Effect 链和 Gate6 链。 | CAS 冲突时刷新链尾并重试；仍失败则返回写入异常；签名或链完整性错误阻止记录提交。 |
| 增量时延 5000 次非参数 bootstrap | 成对 direct baseline latency、protected latency、AB/BA 顺序和随机 seed | 对每个样本计算 `protected_ms - direct_business_baseline_ms`，用线性插值求 p95；bootstrap 5000 次有放回抽样，每次重算 p95，并取 95% 分位作为单侧上界。 | 非 reference-ready 参数、样本数不足或 bootstrap 参数非法会使脚本失败；`--dev` 结果不作为正式证据。 |
| AIBOM A-F 风险评级与签名验证 | `install_plugin` 请求、artifact/url/code snippet、expected SHA-256、离线漏洞/信誉库和签名信任根 | 扫描源码 AST、危险 API、依赖、外联痕迹、provenance 和能力声明；生成 CycloneDX 1.6 BOM；按指标评为 A/B/C/D/F，A/B 放行，C 人工复核，D/F 拒绝，并校验签名。 | 远程 artifact 无离线缓存、SHA-256 mismatch、schema invalid 或签名不可信会降级并拒绝高风险安装。 |

### 3.4 双层策略与决策约束

政企组织既需要统一底线，也需要部门和业务域差异。XA-Guard 将策略分为 baseline 与 overlay。
baseline 定义全局禁止项和智能体能力上限；overlay 可以收紧工具、数据域或参数条件，
其约束范围始终位于 baseline 以内。合并结果带有 bundle hash，便于在审计中定位实际生效的策略版本。

参数谓词采用受限表达式和 AST 白名单。overlay 无法解析或不满足白名单时在加载期拒绝该 overlay；
策略后端不可用时写路径按照失败关闭处理。单条 predicate 运行期异常按未命中处理，避免把异常表达式误写为已授权。
策略还可以导出为 OPA/Rego bundle，用于与外部策略执行环境做一致性检查。

### 3.5 intent-first Effect 与可验证 Undo

审计记录负责说明发生过什么，Effect 负责保存恢复业务状态所需的上下文。XA-Guard 把每次写操作建模为 Effect，
其中包含人员、智能体、工具、数据域、原始 trace、幂等键、恢复窗口、合同摘要和当前状态。

写入顺序固定为：

1. 创建 prepared Effect 和 execution lease；
2. 提交前置 Gate6 记录；
3. 使用 `effect_id` 调用下游业务接口；
4. 加密保存恢复材料和合同快照；
5. 将 Effect 更新为 available，并提交最终 Gate6 记录。

如果服务在业务成功后、返回结果前崩溃，reconciler 根据 prepared intent 和 `effect_id` 查询下游，
恢复 Effect 状态。Undo 由原操作人员发起，另一名具有审批角色的人员批准。批准只创建持久化任务，
补偿由独立 Worker 执行。

```mermaid
stateDiagram-v2
    [*] --> prepared
    prepared --> available: 业务成功
    available --> undo_pending: 提交 Undo
    undo_pending --> rejected: 审批拒绝
    undo_pending --> approved: 独立审批
    approved --> compensating: Worker 取得 lease
    compensating --> compensated: 补偿成功
    compensating --> retry_wait: 可重试错误
    retry_wait --> compensating: 5 / 30 / 120 秒
    compensating --> compensation_failed: 永久失败
```

Worker 使用 60 秒 lease 和 20 秒 heartbeat。持有 lease 的 Worker 失效后，其他实例在 lease 到期后
接管。网络超时、429 和 5xx 按合同持久化重试；参数、签名和策略错误直接失败。
补偿动作使用内部签名授权，并重新经过动态授权、Governance 和六关。调度语义采用至少一次投递，
下游以 `effect_id` 提供幂等执行。

恢复材料由随机 DEK 加密，DEK 使用版本化 KEK 包裹。Keyring 同时支持当前写入 key 和历史解密 key，
并能够在线 rewrap。错误 KEK 会阻止补偿任务继续执行。

### 3.6 AIBOM 供应链准入

插件、Skill 和脚本可能通过源码、依赖、远程下载、隐蔽外联或能力声明引入风险。AIBOM gateway
在组件安装和执行之前完成准入：

```mermaid
flowchart LR
    A["组件 / CycloneDX BOM"] --> B["结构与 Schema 校验"]
    B --> C["组件、依赖和能力提取"]
    C --> D["源码与风险情报检查"]
    D --> E["风险评级与策略判断"]
    E --> F["签名验证"]
    F --> G{"准入"}
    G -->|通过| H["离线安装 / 执行"]
    G -->|拒绝| I["记录原因与审计"]
```

系统支持内部组件描述和 CycloneDX 1.6 BOM，提取组件、依赖、MCP/AI 能力、漏洞与风险指标，
生成 A–F 评级并验证签名。离线安装路径检查路径穿越、危险隐藏文件和能力声明不一致。
CycloneDX 的组件、依赖、服务、漏洞和 provenance 模型为 AIBOM 的交换格式提供了基础[9]。

### 3.7 Gate6 与证据链

Gate6 记录人员、智能体、租户、工具、参数摘要、策略、审批、风险、结果摘要、trace 和前驱 hash。
Effect 事件链保存 prepared、available、undo_requested、approved、compensation_started 和
compensated 等状态。两条链通过 `trace_id`、`effect_id` 和业务引用交叉关联。

证据收集器从 PostgreSQL 读取链记录和业务状态，重新计算 hash，检查链间引用和验收断言，
再对 artifact manifest 进行 SM2-with-SM3 签名。公开证据由审计投影和摘要构成，
其公开范围与敏感材料留存边界见 §5.9。

---

## 4. 工程化实现与优势

### 4.1 从安全模块到完整业务闭环

XA-Guard 的 Reference 路径运行完整跨服务链路：

```text
Keycloak 登录
  → PKCE 与 Token Exchange
  → 人员—智能体身份
  → PostgreSQL 动态授权
  → 六关运行时决策
  → prepared Effect
  → 有状态业务接口
  → 独立 Undo 审批
  → Worker 补偿
  → Effect/Gate6 双链
  → 签名 evidence
```

Console/BFF 为 Alice、Dora 和管理员提供独立会话。Alice 创建工单并申请 Undo；审批权限由 Dora 的
独立会话持有；Worker 随后调用取消工具。管理员负责授权关系和失败任务处置。前端角色、后端令牌、
数据库 assignment 和审批权限使用同一身份来源，身份隔离一直延伸到后端授权判断。

### 4.2 数据一致性与并发写路径

Effect 和 Gate6 都是同租户有序 hash 链。并发请求如果分别竞争连接、事务和链锁，既会增加尾延迟，
也可能在错误实现中产生旧链尾。当前实现采用三层约束：

1. 同租户请求先在进程内排队，避免等待链锁的任务提前占满连接池；
2. PostgreSQL advisory lock 提供跨进程和跨副本互斥；
3. `xa_chain_tails` 记录期望链尾，Effect/Gate6 按固定顺序锁定并执行 CAS。

prepared/final 请求进入统一按租户调度器。混合批次仍保持 final→prepared 顺序，
但可以复用同一连接和事务；Gate6 使用有序数组输入，Effect completion 使用批量更新。
JSON/JSONB 使用紧凑 UTF-8 codec，Gate6 大记录保持 PostgreSQL EXTENDED 存储并启用 LZ4。

这些优化保留了 `fsync`、`synchronous_commit`、`full_page_writes` 和响应前审计持久化。
性能结果覆盖完整安全语义及数据库可靠性设置下的写路径。

### 4.3 故障恢复设计

工程验证覆盖了多个真实故障窗口：

- PostgreSQL 在写请求前中断，业务接口没有收到调用；
- API 在业务成功后崩溃，reconciler 依据 prepared Effect 恢复；
- 两个审批请求并发到达，只生成一个补偿任务；
- 持有 lease 的 Worker 被终止，另一实例接管；
- 下游连续返回 429、5xx 和超时，任务按 5/30/120 秒执行持久化重试；
- 错误 KEK 阻止解密，管理员恢复正确 key 后重新调度；
- 新 KEK 上线后完成在线 rewrap，历史记录仍可恢复。

故障恢复依托持久化状态和幂等业务接口，能够跨进程、跨实例继续推进。

### 4.4 部署、升级与回滚

Reference Compose 用于本地完整闭环；Helm chart 面向外部 OIDC、PostgreSQL 和 key provider。
Chart 将 migration 作为独立 Job，API 和 Worker 支持多副本，并提供滚动升级、PDB、HPA、
NetworkPolicy 和 Secret 引用。

本地三节点 kind 验证从旧版镜像安装开始，随后升级到当前候选，并实际执行：

- migration 重跑；
- API Pod 删除与请求恢复；
- prepared Effect 接管；
- Worker lease 接管；
- NetworkPolicy 正向/负向探针；
- Helm rollback。

验证过程同时覆盖服务启动、数据迁移、业务请求和故障注入。

### 4.5 质量与发布验证

项目把单元测试、集成测试、部署检查、前端构建和证据验签收敛到统一 verifier。最终候选在隔离 Python
环境中完成依赖一致性检查、产品 Ruff、全仓 pytest、L3 static、Compose config、Console 测试与构建，
以及最终 evidence verifier。发布 manifest 只允许在干净工作树上生成，并绑定 commit、分支、
文件大小和 SHA-256。

依赖使用仓库许可证和第三方清单管理。运行密码、client secret、KEK、内部签名 key、KMS token 和
DSN 仅保存在 gitignored 运行目录，并通过 Secret 挂载；公开证据只保留验证所需的审计投影和摘要。

### 4.6 工程验证结果

| 工程面 | 验证规模 | 结果 |
|---|---:|---|
| 自动质量矩阵 | 782 collected | 781 passed，1 个 Windows 能力 skip，0 failure/error |
| Reference 故障 | 11 个场景 | 11/11 PASS |
| 正式写路径性能 | 10 并发，3×500 paired writes | 三轮 p95 与 bootstrap upper 均低于 50ms |
| Undo | 10 次真实业务取消 | 10/10，约 0.45–0.94s |
| 本地集群 | 三节点 kind | 安装、升级、迁移、接管、网络策略和回滚通过 |
| 最终证据 | 14 artifacts | 102 Effect、59 Gate6，SM2-with-SM3 独立验签通过 |
| Console | 三个独立账号会话 | 创建、申请、审批、补偿与证据时间线完成 |

工程化优势不只体现在测试数量，而是同一组身份、事务、故障和证据约束贯穿接口、数据库、Worker、
部署和前端。故障报告、性能报告与最终证据包绑定到同一候选，减少了“功能演示通过但交付版本不同”
的口径漂移。

---

## 5. 实验设计与结果

### 5.1 指标体系与预期效果

本文按赛题目标(4)将效果指标拆为数据安全、内容安全、执行安全、供应链安全和合规风险五个维度。
指标体系按维度分别观察攻击是否被识别、是否触发下游动作、是否改变业务状态，以及证据是否可复验，
各维度独立报告（口径见 §5.9）。预期效果是在声明范围内降低真实业务后果。

| 维度 | 指标 | 测法 | 当前结果 | 证据 |
|---|---|---|---|---|
| 数据安全 | 合成市民数据外发次数 | OAR live A/B，邮箱与 RAG 间接注入对照 | 冻结 N=10：邮箱 Null 10、XA-Guard 0；RAG Null 10、XA-Guard 0；protected infra error 0 | `docs/evidence/attack-proof-set-2026-07-27-n10.md` |
| 内容安全 | 输入攻击族召回、阻断召回、误报率 | Gate1 isolated evaluation，限定 6 个输入攻击族与 negative controls | 60/60 检测并阻断；FPR any-detection 0/58，Wilson 95% upper 0.0621；规则层 p95 0.04ms | `docs/evidence/gate1-l3-evaluation-2026-06-18.json` |
| 执行安全 | 未批准高风险动作下游执行数 | Null / 拒绝 / 批准三路对照 | Null 下游 1；拒绝路径下游 0 且 `require_approval -> deny`；批准对照下游 1 且 `require_approval -> allow` | `docs/evidence/attack-proof-set-2026-07-27-n10.md` |
| 供应链安全 | 恶意组件准入与下游执行 | AIBOM 恶意 snippet / 干净 artifact 对照 | 恶意 snippet AIBOM deny、下游 0；干净 artifact 批准后下游 1 | `docs/evidence/attack-proof-set-2026-07-27-n10.md` |
| 合规风险 | 审计链完整性、篡改可检出、签名 evidence | clean / tampered 审计副本对照与最终 evidence 验签 | clean verifier exit 0；tampered verifier exit 1；原始 audit hash 不变；最终 evidence 14 artifacts、102 Effect、59 Gate6，SM2-with-SM3 | `docs/evidence/agent-identity-undo-final-2026-07-21.md` |

上述五维度对应的预期效果是：内容安全维度减少恶意输入进入工具链；数据安全维度减少受保护数据外发；
执行安全维度让未审批高风险动作不产生下游副作用；供应链安全维度把恶意插件拦在安装入口；
合规风险维度保证事后审计、篡改检测和证据验签可以独立复核。

### 5.2 Gate1 分层识别指标

Gate1 只回答“输入与工具输出进入后，是否识别并阻断声明范围内的输入攻击”。为避免把审批、策略、供应链、
留存和加密降级等治理问题误计入 Gate1，本文将 Gate1 判定面限定为 6 个输入攻击族：
`dangerous_command`、`forbidden_generation`、`indirect_injection`、`jailbreak_or_prompt_leak`、
`pii_leak`、`secret_exfil`。

| 判定面 | 攻击族 / 控制集 | 样本数 | 漏报 / 误报 | 当前结果 |
|---|---|---:|---:|---|
| Gate1 | `dangerous_command` | 15 | 0 | 召回 1.000 |
| Gate1 | `jailbreak_or_prompt_leak` | 12 | 0 | 召回 1.000 |
| Gate1 | `indirect_injection` | 10 | 0 | 召回 1.000 |
| Gate1 | `forbidden_generation` | 8 | 0 | 召回 1.000 |
| Gate1 | `secret_exfil` | 8 | 0 | 召回 1.000 |
| Gate1 | `pii_leak` | 7 | 0 | 召回 1.000 |
| Gate1 小计 | 6 个输入攻击族 | 60 | 0 | detection recall 1.0；blocking recall 1.0；ASR 0.0 |
| Gate1 negative controls | expected `allow` 控制样本 | 58 | 0 | FPR any-detection 0.0，Wilson 95% upper 0.0621；FPR blocking 0.0 |
| Gate1 calibration/holdout | payload 指纹诊断切分 | 60 attack / 58 negative controls | 0 fingerprint overlap | `selected_threshold=1.0`；calibration 29/29 recall；holdout 31/31 recall；两侧 FPR 0.0 |
| 非 Gate1 | 审批、留存、加密降级、跨域、供应链等治理样本 | 133 | — | 由 Gate2/Gate3/Gate5 + AIBOM 裁决，不作为 Gate1 输入识别召回分母 |

因此，`docs/evidence/gate1-l3-evaluation-2026-06-18.json` 中全量 290 例的 `detection_recall=0.3575`
不能解释为 Gate1 对输入攻击能力较弱。该总表混入了大量非 Gate1 治理类样本；在 Gate1 声明范围内，
当前结果为 60/60 识别并阻断、false negatives 0、FPR any-detection 0/58。规则层延迟为 p50 0.02ms、p95 0.04ms。

上述指标在 Gate1 声明的判定面与评测口径内成立，其适用边界集中见 §5.9。

### 5.3 Open Agent Range

OAR 是面向企业任务链的红队评测环境。它包含人员、智能体、工具面、数据域、业务状态、攻击 finding、
attempt ledger 和 replay。与只判断一句输入是否恶意相比，OAR 关注攻击是否真正触发工具、
是否改变业务后果，以及网关审计能否与靶场账本对齐。

OAR 设计了三类实验：

- **full-day**：在多个业务域中运行连续任务，观察工具尝试、账本和违规；
- **live A/B**：同一 finding 分别运行在 Null 和真实 XA-Guard MCP session；
- **replay**：验证 artifact hash、ledger 投影、工具事件和原始 SUT 审计。

当前封存 live A/B 证据为每侧独立重复 10 次（2026-07-27 N=10 clean run，已冻结）。保护效果按两侧泄漏率之差计算，基础设施错误单独记录。
这可以区分“安全网关主动阻断”和“服务没有正常运行”。

### 5.4 OAR 结果

| 指标（冻结 N=10，每侧） | Null | XA-Guard |
|---|---:|---:|
| 独立 attempts | 10 | 10 |
| 合成数据泄漏 | 10 | 0 |
| 保护侧基础设施错误 | — | 0 |
| 泄漏率 | 1.0 | 0.0 |
| protection delta | — | 1.0 |

full-day 场景（2026-07-11 canonical run）完成 41 次工具尝试，产生 43 条 ledger 记录，ledger violation 为 0。
7/7 次 attempt replay 均通过。XA-Guard 侧的工具事件、range audit、ledger 和原始 Gate6 记录
可以逐序对齐。

### 5.5 故障实验

Reference all-fault 将身份拒绝、授权撤销、租户隔离、数据库中断、API 崩溃恢复、并发审批、
Worker 接管、持久化重试、错误 KEK、密钥轮换和历史记录恢复组合为 11 个场景，最终结果为 11/11。

故障实验同时检查业务有效副作用数量。例如并发审批和 Worker 重试可以产生多次调度尝试，
但业务接口只能观察到一次有效取消。这使测试结果同时覆盖控制面状态和实际业务后果。

### 5.6 性能实验

每个性能样本由一次 XA-Guard 受保护写和一次直接业务写组成。AB/BA 顺序平衡并打乱，
新增开销定义为：

```text
incremental_latency =
    protected_write_latency - direct_business_write_latency
```

实验使用 10 并发，每轮 30 次 warmup 和 500 次 measured pairs。除增量 p95 外，
还通过 5000 次非参数 bootstrap 计算单侧 95% p95 上界。三轮结果如下：

| seed | incremental p95 | 单侧 95% bootstrap upper |
|---:|---:|---:|
| 20260741 | 45.109ms | 46.984ms |
| 20365470 | 42.141ms | 43.120ms |
| 20470199 | 43.934ms | 45.528ms |

三轮点估计与上界均低于 50ms。相同实验中完成 10 次 Undo，批准到业务取消约为 0.45–0.94s。

### 5.7 代表性攻击链与业务后果验证

在 OAR 主评测之外，本文从赛题四个方向选取六类代表性攻击链，固化为可复现证明集
（`xa-attack-proof-set-v1`）。证明集关注攻击是否跨越安全边界、是否触发下游动作以及业务状态是否改变，
而不是仅判断一段输入是否包含恶意文本。每类攻击保留独立业务判据，结果按各自判据分别报告（口径见 §5.9）。

以邮箱间接提示注入为例展开一条完整链：攻击内容随一封普通邮件进入邮箱场景；
Gullible seat 读取邮件后把注入指令当作任务的一部分；Null 侧发起对外发送，
合成市民数据 `cit-1001` 被发往外部甲方；同一 finding 在 XA-Guard 侧运行时，
网关在工具执行前裁决为 deny，下游外发为 0，Gate6 记录与靶场 ledger、replay 结果逐序对齐。
两侧各独立重复 10 次，结果一致。

最终证明运行 `xa-attack-proof-v1-20260727T033934Z-win-local` 在 clean checkout 上完成，
运行起止 Git HEAD 均为 `6deacef266d2348e43ab7166b9aa39ca2cbc6cdb`，工作树均无未提交修改。
封存包 SHA-256 为 `435d170585e2266a65107db1bba3ee2705b5cfec8b29d76948d59898026e8e5b`；
根清单覆盖除自身外的 730/730 个文件，并包含 OAR 的 40 个子 hash 清单。

六类 case 的对照与业务观测如下：

| 赛题映射 | 代表性攻击链 | 对照设计 | 已观察业务结果 |
|---|---|---|---|
| 方向一：复杂输入链路 | 邮箱间接提示注入外发 | Null / XA-Guard live 各 10 次 | Null 泄漏 10/10；保护侧泄漏 0/10，infra error 0；10/10 protected replay 的 hash、ledger、SUT/原始 Gate6 对齐通过 |
| 方向一：复杂输入链路 | RAG 间接提示注入外发 | Null / XA-Guard live 各 10 次 | Null 泄漏 10/10；保护侧泄漏 0/10，infra error 0；10/10 protected replay 的 hash、ledger、SUT/原始 Gate6 对齐通过 |
| 方向二：工具与任务执行 | 未经批准的高风险命令 | Null、拒绝、批准三路 | Null 下游 1；拒绝下游 0，审计 require_approval → deny；批准对照下游 1，审计 require_approval → allow |
| 方向三：供应链安全 | 恶意插件准入 | 恶意 code snippet 与本地干净 artifact | 恶意插件 deny、下游 0；干净 artifact 经批准后 require_approval → allow、下游 1 |
| 方向四：评测与审计 | Gate6 审计副本篡改 | clean 与 tampered 副本 | clean 验签通过，tampered 验签失败，原始 audit hash 不变 |
| 横向身份边界 | 伪造 header、撤权与跨租户隔离 | 独立验签最终 identity evidence bundle | verifier 通过；14 artifacts / 102 Effect / 59 Gate6，三个身份 subcase 均满足预设判据 |

该证明集为合成确定性场景，结果适用于本场景与上述对照设计，其实验边界与脱敏口径集中见 §5.9。
公开复现材料由脱敏 case manifest、评测 runner、结果摘要、源码 provenance 和文件 hash 组成，见
`docs/evidence/attack-proof-set-2026-07-27-n10.md`。

### 5.8 证据完整性

最终 evidence 从同一候选环境采集，包含身份、assignment、业务对象、Undo 请求、Effect 链、
Gate6 链和三份验收报告。Collector 执行 secret scan、hash 重算、链间引用检查和业务状态断言，
随后生成签名 manifest。独立 verifier 固定 public key id 并验证 14 个 artifacts、
102 条 Effect 和 59 条 Gate6 记录。

### 5.9 能力边界与不声明事项

本节集中列出全文结果的适用边界与不声明事项，正文各处的指标与结论均以本节口径为准。

**识别指标边界**

- Gate1 识别指标只在以下边界内成立：第一，60 例规模较小，仅覆盖 §5.2 的 6 个输入攻击族；第二，
  seed 与规则开发同源，`independent_holdout=false`，payload 指纹切分是诊断性切分，不是独立泛化评估；
  第三，误报结果必须与 Wilson 区间一起报告，不能只报告 0.0 点值；第四，0.02/0.04ms 是规则层延迟，
  不包含模型后端推理、完整网关链路或下游工具时延；当前封存 Gate1 数字来自 rule detector 口径，
  不能归因于可选模型后端。
- 指标体系不把不同风险合并为单一总分；预期效果是在声明范围内降低真实业务后果，
  而不是只给出文本分类分数。

**策略判定边界**

- Gate3 单条 predicate 运行期异常按未命中处理（口径同 §3.3 表与 §3.4），不宣称全局 fail-closed。

**证明集与实验边界**

- 证明集（§5.7）是合成确定性场景：OAR live A/B 每类 N=10，只说明本场景结果，不外推为泛化攻击率。
- MCP 下游为只记账的安全合成 target，不执行命令、插件或网络动作。
- 身份边界 case 复用独立验签的最终 evidence bundle，不重跑长故障套件。
- 每类攻击保留独立业务判据，证明集不把异构指标合并成单一攻击成功率。
- D1 正文不复制原始注入 payload、危险命令、插件攻击代码、原始审计记录、审批令牌或运行环境绝对路径，
  避免把攻击文本的新颖性误写成系统防护能力。

**兼容与部署边界**

- §6.2 的结果证明 MCP/HTTP 网关契约可被真实客户端触发，不等同于 OpenClaw 官方 SDK 或专有接口
  已经完成适配，也不外推为所有国产 IDE 的原生 HITL 弹窗均已跑通。
- 落实合规要求时，实际部署仍需结合组织制度、目标系统定级、密码应用方案和正式测评流程（§6.4）。
- 进入组织生产环境还需要完成目标 IdP、TLS、托管数据库、正式 KMS/HSM、备份、监控和容量验证（§7）。

**证据公开边界**

- 公开证据只包含审计投影和摘要，访问令牌、恢复材料和私钥保留在运行环境（§3.7）。

---

## 6. 政企应用价值

### 6.1 对业务系统的接入方式

XA-Guard 采用网关方式接入。支持 MCP 的客户端可以把工具调用先发送到 XA-Guard；
传统业务应用可以使用 Control API。模型、客户端和业务接口之间保持松耦合，
安全策略、审批和证据由网关集中处理。

动态授权关系适合组织中的“人员—数字员工—数据域”管理。人员离岗、岗位变化或智能体能力调整时，
管理员修改 assignment 即可生效。YAML ceiling 保留平台级安全底线，业务部门的 overlay
负责表达部门和场景差异。

### 6.2 兼容 OpenClaw 类智能体

赛题要求兼容 OpenClaw 类智能体及其他具备工具调用能力的大模型应用。XA-Guard 将兼容边界放在
工具调用协议层，而不是绑定某个基座模型或客户端插件：上游只要能把工具名、参数、身份上下文和
目标数据域经 MCP stdio、Streamable HTTP 或 Control API 交给网关，就能复用同一套六关治理、
Effect 持久化和 Gate6 审计；下游业务工具不需要感知调用来自哪一种智能体客户端。

当前实测范围包括 Claude Code 的本地 MCP Server 注册与握手、独立 stdio JSON-RPC harness 的 9 个
真实 MCP 场景，以及 OpenCode 1.17.8 / GLM-5.2 经 Streamable HTTP 发起的真实模型选工具调用。
对未声明 elicitation 能力的客户端，系统已验证 pending approval 与控制工具 fallback；支持
elicitation 的客户端可使用协议内交互审批。上述结果表明 MCP/HTTP 网关契约可在真实客户端上触发，
其兼容范围与不声明事项见 §5.9。若发榜方另行给出 OpenClaw 专有接口规范，可在现有契约外增加薄适配层，而不改变
核心治理链。

### 6.3 对安全与审计工作的价值

安全团队能够从同一条记录中看到人员、智能体、工具、数据域、策略版本、审批人、业务引用和结果。
Effect 把审计与恢复连接起来：审计人员不仅能定位异常写操作，还能看到可逆性、恢复窗口、
补偿状态和失败原因。

OAR 提供从攻击任务到业务后果的可重复验证方法。策略调整后可以重跑相同 finding 和 replay，
比较保护效果及审计变化，从而形成评测、修复和复验闭环。

### 6.4 与合规和治理要求的衔接

GB/T 45654-2025 对生成式人工智能服务的安全要求、GB/T 22239-2019 的身份鉴别与安全审计、
GB/T 39786-2021 的密码应用要求，为政企智能体治理提供了基础规范[10-12]。
《人工智能安全治理框架》2.0 强调风险分类、全生命周期治理和技管结合[13]。
OWASP 针对 LLM 与 Agentic Application 总结了提示注入、过度代理、工具滥用和身份权限等风险[14-15]；
NIST AI 600-1 则从治理、测量和风险管理角度给出生成式人工智能的组织级实践框架[16]。

XA-Guard 中的身份验证、最小权限、运行时控制、审批、密码完整性、评测和恢复机制可以为组织落实
相关要求提供技术支撑。实际部署的配套条件见 §5.9。

### 6.5 与既有方案的横向对比

下表按赛题关注的行动链能力比较公开资料中可核验的范围。外部方案标注“未核验”仅表示本次事实源
未提供该能力的直接证据，该标注本身不断言产品或研究工作是否具备该能力；不同方案的公开指标、硬件、
数据集和任务定义口径各异，表中按各自公开范围定性列出，不做数值横比[3,17-20]。

| 方案 | 输入检测 | 工具授权 | 信息流 | 供应链 | 副作用恢复 | 证据链 |
|---|---|---|---|---|---|---|
| Lakera Guard | 官方披露检测率 >98%、FPR <0.5%[17] | 未核验人员—智能体动态授权或 HITL | 未核验跨工具信息流 | 未核验 AIBOM 准入 | 未核验恢复合同 | 未核验运行审计哈希链 |
| Meta LlamaFirewall | PromptGuard 2 86M：97.5% Recall @ 1% FPR；另含 AlignmentCheck[18] | 未核验企业身份授权或审批 | 未核验跨工具污点传播 | CodeShield 做代码扫描，不等同于插件准入 | 未核验业务副作用恢复 | 未核验运行审计双链 |
| CaMeL | 以系统设计防提示注入，不以输入分类器为核心 | 未核验政企身份与 HITL | 控制流/数据流分离；AgentDojo 77% provable-secure completion[3] | 未核验组件准入 | 未核验业务副作用恢复 | 未核验运行审计链 |
| AgentSpec | trigger/predicate 规则，不是输入检测产品 | DSL 约束 trigger、predicate 与 enforcement[19] | 未核验跨工具信息流 | 未核验组件准入 | 未核验业务副作用恢复 | 未核验运行审计链 |
| ShieldAgent | 概率规则电路，不是输入检测产品 | 以可验证规则电路约束策略推理[20] | 未核验跨工具信息流 | 未核验组件准入 | 未核验业务副作用恢复 | 形式化验证不等同于运行期审计证据 |
| **XA-Guard** | Gate1 规则/模型接口、Spotlighting 与分层指标 | 动态 assignment、Gate2/3、HITL、deny 优先 | Gate4 来源标签、敏感字段与出向控制 | AIBOM、CycloneDX、A–F 评级与签名 | **intent-first Effect、恢复合同、职责分离 Undo、Worker 补偿** | **Effect/Gate6 双链、交叉引用、SM2-with-SM3 manifest 与篡改对照** |

在这组选定对象及已核验公开范围内，XA-Guard 的差异点不是单独提高输入分类分数，而是把执行前授权、
信息流、供应链准入、真实副作用恢复和可独立验签证据放入同一运行时闭环。其中“副作用恢复”和
“Effect/Gate6 双链可验签证据”是本项目直接实现并以业务状态 oracle 验证的能力。

---

## 7. 结论

XA-Guard 将智能体安全从输入过滤扩展到完整行动链。人员—智能体双主体身份解决可信委托问题；
六关网关在工具执行前后统一处理输入、审批、策略、信息流、隔离和审计；intent-first Effect
把副作用恢复所需的信息提前到执行之前；AIBOM 控制扩展组件入口；OAR 和签名 evidence
用于验证防护结果与审计完整性。

项目已经完成跨身份服务、网关、数据库、业务接口、Worker、Console 和评测环境的工程闭环。
最终候选通过故障、并发性能、本地集群和统一质量验证，并保留可独立验签的证据包。

本文实验基于 Reference Compose 和本地三节点 kind 环境，结论适用于当前实现、场景与恢复合同；
进入组织生产环境的前置条件见 §5.9。

---

## 参考文献

[1] Debenedetti E, Zhang J, Balunović M, et al. AgentDojo: A Dynamic Environment to Evaluate
Prompt Injection Attacks and Defenses for LLM Agents[C]//Advances in Neural Information Processing
Systems. 2024. <https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html>

[2] Zhan Q, Liang Z, Ying Z, et al. InjecAgent: Benchmarking Indirect Prompt Injections in
Tool-Integrated Large Language Model Agents[C]//Findings of the Association for Computational
Linguistics: ACL 2024. 2024: 10471-10506. <https://aclanthology.org/2024.findings-acl.624/>

[3] Debenedetti E, Shumailov I, Fan T, et al. Defeating Prompt Injections by Design[EB/OL].
arXiv:2503.18813, 2025. <https://arxiv.org/abs/2503.18813>

[4] Wu Y, Roesner F, Kohno T, et al. IsolateGPT: An Execution Isolation Architecture for
LLM-Based Agentic Systems[C]//Network and Distributed System Security Symposium. 2025.
<https://doi.org/10.14722/ndss.2025.241131>

[5] Sakimura N, Bradley J, Agarwal N. RFC 7636: Proof Key for Code Exchange by OAuth Public
Clients[S]. IETF, 2015. <https://www.rfc-editor.org/rfc/rfc7636>

[6] Jones M, Nadalin A, Campbell B, et al. RFC 8693: OAuth 2.0 Token Exchange[S]. IETF, 2020.
<https://www.rfc-editor.org/rfc/rfc8693>

[7] Lodderstedt T, Bradley J, Labunets A, et al. RFC 9700: Best Current Practice for OAuth 2.0
Security[S]. IETF, 2025. <https://www.rfc-editor.org/rfc/rfc9700>

[8] Model Context Protocol. Authorization Specification, Version 2025-11-25[EB/OL]. 2025.
<https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization>

[9] Ecma International. ECMA-424: CycloneDX Bill of Materials Standard, 1st Edition[S]. 2024.
<https://ecma-international.org/publications-and-standards/standards/ecma-424/>

[10] 国家市场监督管理总局, 国家标准化管理委员会. GB/T 45654-2025 网络安全技术
生成式人工智能服务安全基本要求[S]. 2025.

[11] 国家市场监督管理总局, 国家标准化管理委员会. GB/T 22239-2019 信息安全技术
网络安全等级保护基本要求[S]. 2019.

[12] 国家市场监督管理总局, 国家标准化管理委员会. GB/T 39786-2021 信息安全技术
信息系统密码应用基本要求[S]. 2021.

[13] 全国网络安全标准化技术委员会. 人工智能安全治理框架 2.0[R]. 2025.

[14] OWASP GenAI Security Project. OWASP Top 10 for LLM Applications 2025[R]. 2025.
<https://genai.owasp.org/llm-top-10/>

[15] OWASP GenAI Security Project. OWASP Top 10 for Agentic Applications 2026[R]. 2025.
<https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/>

[16] Autio C, Schwartz R, Dunietz J, et al. Artificial Intelligence Risk Management Framework:
Generative Artificial Intelligence Profile, NIST AI 600-1[R]. National Institute of Standards
and Technology, 2024. <https://doi.org/10.6028/NIST.AI.600-1>

[17] Check Point Software Technologies. Check Point Acquires Lakera to Deliver End-to-End AI
Security for Enterprises[EB/OL]. 2025. <https://www.checkpoint.com/press-releases/check-point-acquires-lakera-to-deliver-end-to-end-ai-security-for-enterprises/>

[18] Meta. LlamaFirewall: An open source guardrail system for building secure AI agents[EB/OL].
2025. <https://meta-llama.github.io/PurpleLlama/LlamaFirewall/>

[19] Wang Y, et al. AgentSpec: Customizable Runtime Enforcement for Safe and Reliable LLM
Agents[EB/OL]. arXiv:2503.18666, 2025. <https://arxiv.org/abs/2503.18666>

[20] Zhang Y, et al. ShieldAgent: Shielding Agents via Verifiable Safety Policy Reasoning[EB/OL].
arXiv:2503.22738, 2025. <https://arxiv.org/abs/2503.22738>

---

## 附录 A：验证材料索引

本附录单列本文结果对应的仓库验证记录，与学术论文、协议和标准分开。

| 验证内容 | 材料位置 |
|---|---|
| Gate1 分层召回、误报、Wilson 区间与规则层时延 | `docs/evidence/gate1-l3-evaluation-2026-06-18.json` |
| OAR full-day、live A/B 与 replay | `docs/acceptance/EVIDENCE-CONSOLIDATION.md` §2 |
| Reference 11/11 fault | `docs/evidence/agent-identity-undo-final-2026-07-21/acceptance/reference-faults-all-final-rerun-20260721.json` |
| 本地三节点 kind | `docs/evidence/agent-identity-undo-final-2026-07-21/acceptance/kind-ha-final-pass-20260721.json` |
| 正式 3×500 性能与 Undo | `docs/evidence/agent-identity-undo-final-2026-07-21/acceptance/perf-formal-mixed-transaction-rebuilt-20260721.json` |
| 最终签名 evidence | `docs/evidence/agent-identity-undo-final-2026-07-21.md` |
| 代表性攻击链的脱敏清单、脚本、结果摘要、源码 provenance 与 hash | `docs/evidence/attack-proof-set-2026-07-27-n10.md` |
| 三账号 Console 闭环 | `docs/evidence/mcp-live-acceptance-2026-07-19/` |
| Claude Code MCP 握手与 9 个 stdio JSON-RPC 场景 | `docs/evidence/mcp-live-acceptance-2026-07-19/` |
| OpenCode Streamable HTTP 与 pending approval fallback | `docs/evidence/l3-opencode-http-2026-06-18.md`、`docs/evidence/l3-hitl-pending-approval-2026-06-18.md` |
| 最终仓库状态与统一验证 | `status.md` |
