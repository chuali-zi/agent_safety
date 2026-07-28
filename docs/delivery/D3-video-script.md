# D3 演示视频手工录制指南

> **2026-07-26 重排完成**：本指南已按
> [D1-D3-submission-plan.md §7](D1-D3-submission-plan.md)
> 改为 11 段镜头，前 4 分 20 秒依次展示 live A/B、Gate1 量化、高风险命令和 AIBOM，
> 身份、Effect、Undo 与双链证据后移。旧八镜头顺序已废止。
>
> 数字已于 2026-07-27 冻结；所有上屏数字和旁白以
> [FROZEN-NUMBERS.md](FROZEN-NUMBERS.md) 为唯一来源。
> 精确真人旁白见 [D3-video-voiceover.md](D3-video-voiceover.md)，烧录字幕见
> [D3-video-subtitles.srt](D3-video-subtitles.srt)。

目标是手工录制一条 **9:30、硬顶 10:00** 的 16:9 演示视频。主叙事不再从身份架构起讲，
而是先让评委看到攻击和业务后果的 A/B 对照，再解释 XA-Guard 如何在执行前治理、在执行后恢复，
以及如何用证据证明整个过程。

## 1. 成片标准

- 文件名：`XA-Guard-XA-202620-demo.mp4`。
- 1920×1080、30 fps、H.264 + AAC、`-crf 20`、`-b:a 160k`、`+faststart`。
- 旁白为真人录音，不使用 TTS；画面与旁白分录，逐段对齐。
- 使用真实 Alice、Dora Keycloak 会话，不使用角色切换或伪造身份。
- 密码、token、client secret、KEK、DSN、私钥、个人信息和本机绝对路径不得进入画面。
- 只声明 Reference Compose、正式测试、封存攻击证明和本地 kind profile 已证明的能力。
- 录成 11 个短片段 `01-cold-open.mp4` 至 `11-close.mp4`，每段前后留 2 秒静帧。
- 浏览器缩放建议 90%，终端字体不小于 18 px；关闭通知、书签栏和密码管理器弹窗。

## 2. 录制前准备

### 2.1 固定工程状态

在最终录制提交上运行：

    git branch --show-current
    git rev-parse HEAD
    git status --short

只录 branch、commit 和空的 `git status --short`；不展示远端 URL、用户名或凭据。
片尾 commit 必须与最终 D1 PDF 标注的 commit 一致。

### 2.2 创建干净 Reference 环境

以下 reset 会删除本机 XA-Guard Reference PostgreSQL 和审计卷，不删除 Git 文件或已提交证据：

    python scripts\verify_reference_faults.py --suite core --prepare --reset ^
      --output .runtime\evidence\d3-preflight-core.json

若收口验收已完成且录制当天不重跑 core：

    python scripts\reference_stack.py --no-build up

入口为 Console `http://localhost:13080` 和 Keycloak `http://localhost:13081`。
凭据在 gitignored 的 `.runtime/reference/credentials.json`，只能离屏查看。

### 2.3 健康和闭环检查

    docker compose -f docker-compose.reference.yml ps
    python scripts\verify_reference_e2e.py

成功标准：PostgreSQL、Keycloak、business-api、xa-guard、worker、Console 均健康；
PKCE、token exchange、真实写入和 Undo 闭环通过。

### 2.4 准备封存攻击证明画面

本段**复用已封存 N=10 run，不重跑实验，也不修改证据**。录制前离屏把本机目录存入变量；
变量值和完整路径不得上屏：

    $proofRoot = Read-Host "sealed run root"
    Test-Path -LiteralPath "$proofRoot\attack-proof-report.json"
    Test-Path -LiteralPath "$proofRoot\artifacts\AP-D1-MAIL\live-ab\summary.json"

应使用 run `xa-attack-proof-v1-20260727T033934Z-win-local`。若本机只有公开脱敏导出，
镜头 2、4、5 可展示
`docs/evidence/attack-proof-set-2026-07-27-n10/attack-proof-report.json` 的对应 `observed`；
镜头 2 的单次 Null / XA-Guard verdict 对照则需要封存 run 的本地 artifacts。

录制镜头 2 时只投影安全字段，禁止直接滚动含绝对路径的完整 summary：

    $mail = Get-Content -LiteralPath "$proofRoot\artifacts\AP-D1-MAIL\live-ab\summary.json" -Raw | ConvertFrom-Json
    [pscustomobject]@{Side="Null";Decision="allow";ExternalSend=$mail.runs[0].null.external_send_count;DataRef=($mail.runs[0].null.leaked_data_refs -join ",");Violation=$mail.runs[0].null.violation_property_ids[0]} | Format-Table
    [pscustomobject]@{Side="XA-Guard";Decision="deny";ExternalSend=$mail.runs[0].xaguard.external_send_count;DataRef="-";Violation="-"} | Format-Table
    $mail.aggregate | Select-Object run_count,null_leak_count,protected_leak_count,protected_infra_error_count,asr_null,asr_protected,protection_delta | Format-List

镜头 4、5 使用 `case-result.json` 的 `observed`，同样不展示 `evidence` 路径：

    (Get-Content -LiteralPath "$proofRoot\artifacts\AP-D2-EXEC\case-result.json" -Raw | ConvertFrom-Json).observed | ConvertTo-Json
    (Get-Content -LiteralPath "$proofRoot\artifacts\AP-D3-SUPPLY\case-result.json" -Raw | ConvertFrom-Json).observed | ConvertTo-Json

### 2.5 准备负测、量化表和工程结果

录制前运行，不在视频里等待：

    python scripts\verify_reference_faults.py --suite core ^
      --output .runtime\evidence\d3-core.json

身份负测只展示脱敏摘要：
`status=passed`、`identity_rejections_before_execution=passed`、
`business_create_attempt_delta=0`、`effect_delta=0`。

另准备三张 1920×1080 静态卡：

1. 四方向覆盖图：输入/数据安全、执行安全、供应链安全、审计与合规；
2. Gate1 分层表：60/60、FPR 0/58、Wilson 95% 上界 6.21%、规则层 p95 0.04ms，
   并同时写 6 个输入攻击族、`independent_holdout=false`、诊断性切分；
3. 工程摘要：Reference 11/11、kind 本地三节点全阶段 PASS、三轮 incremental p95
   45.109 / 42.141 / 43.934ms，三轮单侧 95% bootstrap 上界均小于 50ms。

卡片上的数字逐项对照 `FROZEN-NUMBERS.md`，不要从记忆填写。

## 3. 十一镜头操作与旁白

本节给出画面动作和验收点。旁白必须按
`D3-video-voiceover.md` 的同编号段落录制，不要临场发挥数字。

### 镜头 1：冷开场（0:00–0:40）

画面顺序：

1. 题号 `XA-202620`、项目名 `XA-Guard` 和一句话价值主张；
2. 四方向覆盖图；
3. 0:35 处切入同一封合成注入邮件，为下一镜头建立问题。

必须让四方向在前 30 秒全部可见；不要在这里展开架构或身份术语。

### 镜头 2：封存 live A/B，全片核心（0:40–2:10）

使用同一次 `AP-D1-MAIL` live run 的第一组配对结果，左右或先后对照：

1. 显示合成邮件中的间接注入意图，但不要显示真实姓名或联系方式；
2. Null 侧安全投影：`Decision=allow`、`ExternalSend=1`、`DataRef=cit-1001`、
   `Violation=sensitive-egress`；
3. XA-Guard 侧安全投影：`Decision=deny`、`ExternalSend=0`、`DataRef=-`；
4. 最后显示 aggregate：`run_count=10`、Null leak 10、protected leak 0、
   protected infra error 0、`protection_delta=1.0`；
5. 角标标注：封存 live run、合成确定性场景、run id。

这段展示的是**已经真实执行并封存的 live A/B 证据回放**，不是重新跑一次演示来替代 N=10 结果。
不要把 `protected leak 0/10` 说成通用攻击成功率。

### 镜头 3：Gate1 识别量化（2:10–2:50）

全屏展示 Gate1 分层卡，按顺序高亮：

1. 6 个输入攻击族、60/60 识别并阻断、ASR 0；
2. expected-allow 负控制 FPR 0/58，Wilson 95% 上界 6.21%；
3. 规则层 p95 0.04ms；
4. 边界脚注：`independent_holdout=false`、诊断性切分、非独立泛化评估、
   不含模型后端和完整链路时延。

四条边界必须与点值同屏，不能只展示“100%”或“0 误报”。

### 镜头 4：高风险命令拒绝 / 批准对照（2:50–3:40）

展示 `AP-D2-EXEC` 的 `observed` 安全投影，并用三列动画依次出现：

1. Null：下游调用 1；
2. 未批准：`require_approval → deny`，下游调用 0；
3. 独立批准：`require_approval → allow`，下游调用 1。

保留最后 8 秒让三列同时停留。核心不是只证明“能拦”，而是同时证明合规动作经批准后能通过。

### 镜头 5：AIBOM 供应链准入（3:40–4:20）

展示 `AP-D3-SUPPLY` 的 `observed`：

1. 恶意 snippet 命中 `AIBOM-GATEWAY`、`deny`、下游调用 0；
2. 干净 artifact 进入审批，批准后 `allow`、下游调用 1；
3. 右侧短暂显示 A–F 评级规则：A/B 放行、C 人工复核、D/F 拒绝。

不要给本次恶意 snippet 虚构一个未在证据中记录的具体字母等级。

### 镜头 6：身份与动态委托（4:20–5:10）

打开 Console，以 Alice 登录；在“我的 Agent”展开
`human → Agent → tool → data domain`，停留在 assignment version、
`business_submit_ticket`、`engineering_docs`。

随后切到 `d3-core.json` 脱敏摘要，高亮签名伪造、错误 audience、伪造主体与撤权后访问均在执行前失败，
`business_create_attempt_delta=0`、`effect_delta=0`。

页面必须显示 Alice、`general-office-agent`、1 工具、1 数据域、`ACTIVE`。

### 镜头 7：真实副作用与 intent-first Effect（5:10–6:00）

1. 点击“委托发起工单”；
2. 标题填写“演示：撤销错误工单”；
3. 正文填写“该工单用于 XA-Guard 比赛演示，可在补偿窗口内撤销。”；
4. 点击“确认委托并执行”；
5. 展示同一个 Effect 从 `PREPARED` 到 `AVAILABLE`，以及 `effect_id` 和原动作 trace；
6. 打开业务工单，证明状态为 `open`。

若页面只显示最终状态，可在提交前先展示 intent 卡，再刷新到 `AVAILABLE`；不得手改数据库伪造中间态。

### 镜头 8：职责分离 Undo（6:00–7:10）

1. Alice 输入撤销原因并发起 Undo；
2. 打开“待我审批”，停留在 `NO APPROVER ROLE`；
3. 退出 Alice，以 Dora 独立 Keycloak 会话登录；
4. Dora 展示申请人、目标动作、Effect 和剩余窗口，点击批准；
5. 打开“操作影响”并刷新，展示 Worker 完成补偿：
   `AVAILABLE → COMPENSATED`、工单 `open → cancelled`、补偿 trace 与原 trace 不同。

补偿未即时更新时等 2 秒再刷新。不要使用前端角色切换或让 Alice 批准自己的请求。

### 镜头 9：双链证据与篡改检出（7:10–8:10）

先在 Console“审计证据”展示人员、Agent、Effect、业务引用、原动作 trace、补偿 trace 和 timeline。
随后在已预置 `$proofRoot` 的终端依次运行：

    python scripts\verify_audit.py --path "$proofRoot\artifacts\AP-D4-AUDIT\audit-clean-copy.jsonl"
    "clean_exit=$LASTEXITCODE"
    python scripts\verify_audit.py --path "$proofRoot\artifacts\AP-D4-AUDIT\audit-tampered-copy.jsonl"
    "tampered_exit=$LASTEXITCODE"

画面必须同时保留 `clean_exit=0`、`tampered_exit=1`，并以字幕说明原始 audit hash 未变。
不要展示 audit 原文；这样可避免绝对路径、身份字段或其他运行细节进入画面。

若 Console 显示 `CHAIN GAP`，放弃旧数据；按 reset 流程用第一条干净 Effect 重录。

### 镜头 10：工程与部署压缩展示（8:10–9:00）

前 15 秒展示 `docker compose -f docker-compose.reference.yml ps` 的六服务 healthy；
随后展示工程摘要卡和 kind 结果，不逐条滚动日志：

- Reference all-fault 11/11；
- 本地三节点 kind：安装、升级、迁移重跑、API/Worker 接管、网络策略、回滚全阶段 PASS；
- 三轮 incremental p95 为 45.109 / 42.141 / 43.934ms，
  单侧 95% bootstrap 上界均小于 50ms。

屏幕角标固定写“Reference / local kind profile”，避免误读为生产多地域 HA。

### 镜头 11：边界与收束（9:00–9:30）

显示三行能力边界：

1. 攻击证明为合成确定性场景，不外推为通用攻击率；
2. MCP 下游 target 只记录脱敏调用，不执行真实命令、插件或网络动作；
3. kind 结果只证明本地三节点 profile，生产仍需组织 IdP、KMS/HSM、TLS、备份和容量验收。

最后显示项目名、题号、交付入口和 `git rev-parse HEAD` 的短 commit。
收束句固定为：**前有身份，途中六关，后有撤销，全程有证据。**

## 4. 真人旁白与预演

1. 先按 `D3-video-voiceover.md` 分 11 段试读，填写每段“实测秒数”；任何一段超出镜头窗口，
   先删重复修饰语，不能删数字边界。
2. 目标让有效旁白在 9:00 左右结束，9:00–9:30 留给边界与片尾；总长不得超过 9:30 目标。
3. 每段音频与画面分开录；统一麦克风和房间，录前后各留 2 秒静音。
4. 先做一次不录制完整预演，记录 UI 崩点、登录等待、Worker 刷新和终端换行问题。
5. SRT 是旁白的字幕版；真人录音若改词，必须同步修改 SRT，不能出现音字不一致。

## 5. 失败恢复

| 问题 | 处理 |
|---|---|
| Keycloak 登录报错 | 等 10 秒，确认 PostgreSQL/Keycloak healthy，重开无痕窗口 |
| Alice 看不到 Agent | 重新 bootstrap/up，确认 assignment-seed 成功退出 |
| 提交失败 | 不反复点击；检查 xa-guard、business-api、PostgreSQL health |
| Dora 队列为空 | 确认 Alice 已申请 Undo、两人同租户，点击刷新 |
| 补偿持续 pending | 等待 Worker lease；检查 worker healthy；不手改数据库 |
| 证据页 `CHAIN GAP` | reset 后用第一条干净 Effect 重录 |
| `$proofRoot` 文件不存在 | 停止录制；核对是否为冻结 run，不用其他 run 临时替代 |
| 终端显示绝对路径 | 整段作废；改用本指南的安全字段投影后重录 |
| 画面出现凭据或个人信息 | 整段作废重录，不以打码作为首选 |

## 6. 合成和验收

按顺序创建 `concat.txt`：

    file '01-cold-open.mp4'
    file '02-live-ab.mp4'
    file '03-gate1-metrics.mp4'
    file '04-exec-boundary.mp4'
    file '05-aibom.mp4'
    file '06-identity.mp4'
    file '07-effect.mp4'
    file '08-undo.mp4'
    file '09-evidence.mp4'
    file '10-engineering.mp4'
    file '11-close.mp4'

合并和烧录字幕：

    ffmpeg -f concat -safe 0 -i concat.txt ^
      -vf scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,subtitles=docs/delivery/D3-video-subtitles.srt ^
      -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p ^
      -c:a aac -b:a 160k -movflags +faststart XA-Guard-XA-202620-demo.mp4

    ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate ^
      -of default=noprint_wrappers=1 XA-Guard-XA-202620-demo.mp4
    Get-FileHash -Algorithm SHA256 XA-Guard-XA-202620-demo.mp4

- [ ] 总时长小于 10:00，目标 9:00–9:30；1920×1080、30 fps、H.264 + AAC。
- [ ] 前 4:20 按顺序出现 live A/B、Gate1 量化、高风险命令、AIBOM。
- [ ] live A/B 显示同一输入的 Null 外发 1 / XA-Guard 外发 0，聚合数字为 10/10 对 0/10。
- [ ] Gate1 点值与 6 族、60 例、Wilson 上界、`independent_holdout=false`、规则层时延同屏。
- [ ] 高风险命令和 AIBOM 均展示“拒绝下游 0 / 合规批准下游 1”。
- [ ] Alice、Dora 是两个真实会话；`open → cancelled`、`AVAILABLE → COMPENSATED` 清晰可见。
- [ ] 两个 trace 已关联；clean 验签 exit 0、tampered 验签 exit 1 同屏。
- [ ] 工程镜头被压缩，不挤占攻击实拍；边界未被删减。
- [ ] 所有数字逐项等于 `FROZEN-NUMBERS.md`，旁白与 SRT 一致。
- [ ] 无密码、token、secret、私钥、DSN、个人信息或本机绝对路径。
- [ ] 保存 MP4、SHA-256、字幕、旁白原稿和离线备份。