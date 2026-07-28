# D3 演示视频脚本与构建说明

> 状态：**FINAL-CANDIDATE / REPRODUCIBLE BUILD**
> 赛题：XA-202620《面向政企场景的大模型智能体安全关键技术研究》
> 成片：`output/video/XA-Guard-XA-202620-demo.mp4`
> 时长：8:50（530 秒，低于 10 分钟硬上限）
> 数字源：[FROZEN-NUMBERS.md](FROZEN-NUMBERS.md)

## 1. 成片口径

D3 采用“真实证据投影 + 已验收 Console 截图 + 离线旁白”的可复现构建方式，展示原型核心功能、
关键技术流程与测试效果。画面不包含攻击 payload、攻击脚本、凭据、原始审计记录或本机绝对路径。

- 视频：1920×1080、30 fps、H.264、AAC、`+faststart`。
- 字幕：MP4 内嵌可开关的中文字幕轨，同时交付同名 SRT；不把字幕烧录到画面，
  避免永久遮挡数据卡和 Console 证据。播放器是否默认显示由其自身策略决定。
- 旁白：Windows 本地 `Microsoft Huihui Desktop` 离线合成；metadata 明确标注机器合成，
  不声称真人录音。
- 真实客户端：OpenCode `1.18.5` + DeepSeek V4 Flash + XA-Guard HTTP MCP；
  只演示无副作用的脱敏 CPU 查询。
- 真实业务链：复用已验收的 Alice/Dora Console 截图，展示创建、撤销申请、独立审批、
  补偿和双链证据。
- 实验轨道严格分开：真实模型 holdout、确定性 OAR 证明集、Gate1 诊断集不合并统计。

原计划 DEC-5 选择真人录音，是项目偏好而非赛题硬要求。为消除最后一个人工阻塞并形成可重复交付，
2026-07-27 的实际交付执行改为本地离线旁白；如团队后续自愿替换真人音轨，只能保持字幕、数字和
能力边界不变，不能影响当前成片的可提交状态。

## 2. 十一镜头

| # | 时间 | 画面与结论 | 证据 |
|---:|---|---|---|
| 1 | 00:00–00:35 | 题号、题目全称、四方向与“身份→六关→Effect→Undo→证据”闭环 | 赛题原文、项目架构 |
| 2 | 00:35–01:30 | 真实 OpenCode 工具发现、DeepSeek Flash Tool Call、XA-Guard allow 与 1/1 审计验签 | `d3-opencode-deepseek-flash-preflight-2026-07-27.md` |
| 3 | 01:30–02:35 | D2 真实模型同一 ToolIntent 因果分叉：Null harm 10/10，Guard harm 0/10 | `live-agent-holdout-v1-2026-07-27.md` |
| 4 | 02:35–03:25 | Gate1 60/60、FPR 0/58、p95 0.04ms，并同屏披露 D1 sources 引用解析边界 | Gate1 evidence + live holdout |
| 5 | 03:25–04:10 | 确定性 OAR 邮箱/RAG 两类 N=10，保护侧 replay 20/20 | N=10 攻击证明集公开摘要 |
| 6 | 04:10–04:55 | AIBOM 恶意/干净对照；D3 0/10 attempt 只归因模型自防 | AP-D3 + live holdout |
| 7 | 04:55–05:40 | Alice、实时 assignment、人员-Agent-工具-数据域委托与 fail-closed | Console 真实验收截图 |
| 8 | 05:40–06:40 | PREPARED→AVAILABLE，Alice 申请、Dora 独立批准、Worker 补偿 | 4 张 Console 真实验收截图 |
| 9 | 06:40–07:35 | Gate6/Effect 双链，clean exit 0、tampered exit 1 | Console 证据页 + 封存 verifier |
| 10 | 07:35–08:20 | Reference 11/11、local kind profile、三轮性能与范围声明 | 工程 evidence |
| 11 | 08:20–08:50 | 四项不声明边界与固定收束句 | D1 §能力边界 |

镜头 3 与镜头 5 不得互换口径：

- 镜头 3 是 DeepSeek 真实模型自由决定是否调用工具的 holdout；
- 镜头 5 是确定性合成 OAR 证明集；
- D1 真实模型 5/5 allow/harm 必须在镜头 4 明示，不得用镜头 5 的 0/10 覆盖；
- D3 0/10 attempt 是模型未形成违规意图，不是 XA-Guard 拦截。

## 3. 一键构建

在仓库根目录运行：

```powershell
python scripts\build_d3_submission_video.py
```

构建器会：

1. 用 Pillow 生成 11 张 1920×1080 数据卡和截图编排；
2. 用本地 Windows 语音生成逐段 WAV；
3. 用 FFmpeg 编码 11 段视频、合并并嵌入可选字幕轨；
4. 写出 MP4、SRT、SHA-256 和 metadata；
5. 用 FFprobe 校验时长、分辨率、帧率、H.264 与 AAC 音轨。

构建依赖：

- Python 3.11+；
- Pillow；
- FFmpeg / FFprobe；
- Windows `System.Speech` 与 `Microsoft Huihui Desktop` 中文语音。

构建器不访问网络，也不读取 `.env`；OpenCode 真实客户端预演已经独立完成并以脱敏证据固定。

## 4. 成片验收

- [x] 总时长低于 10:00。
- [x] 1920×1080、30 fps、H.264 + AAC。
- [x] 真实 Agent 客户端完成 MCP 工具发现和一次实际安全调用。
- [x] 画面关联真实 decision、Gate、trace 与审计验签。
- [x] D2 同一 ToolIntent 的 Null/Guard 业务后果对照清晰。
- [x] D1 5/5 allow/harm 边界同屏披露。
- [x] 确定性 OAR N=10 与真实模型轨道分开报告。
- [x] Identity、Effect、职责分离 Undo 与双链证据使用已验收 Console 截图。
- [x] 所有对外数字与 `FROZEN-NUMBERS.md` 一致。
- [x] 无密码、token、私钥、个人信息、攻击 payload、攻击脚本或本机绝对路径。
- [x] 已生成 SHA-256、SRT 和机器可读 metadata。

如后续替换真人旁白，重新验收音字一致、总时长、数字与边界即可；当前成片无需等待该可选优化。
