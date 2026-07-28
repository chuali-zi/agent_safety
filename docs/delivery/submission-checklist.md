# XA-202620 最终提交清单

> 仓库内状态：**READY**
> 更新：2026-07-27
> 外部邮件/网盘/报名系统动作在完成前保持未勾选。

## 1. 交付物

| 交付物 | 状态 | 文件/事实 |
|---|---|---|
| D1 技术方案 PDF | **READY** | `output/pdf/XA-Guard-XA-202620-technical-report.pdf`，18 页 |
| D2 代码与复现 | **READY** | 仓库、README、release verifier、CODE-MAP |
| D3 演示视频 | **READY** | `output/video/XA-Guard-XA-202620-demo.mp4`，530.033 秒 |
| D4 报名表 | **DONE-MANUAL / RECHECK AT SUBMIT** | 仓库外隐私材料 |
| 答辩材料 | **READY** | DEFENSE-QA、CODE-MAP、FROZEN-NUMBERS |

## 2. 固定哈希

- [x] D1 SHA-256：
  `de37a83c973d28f1b4efdc77efda4648a704db94540cb9839b6f4d2e8660c7f1`
- [x] D3 SHA-256：
  `267a1a59f7f48c9d8e489f085afda0ff79197118ceff7b7e2d5422d5962b00c5`
- [x] D3 同名 SRT 与 metadata 已生成。
- [x] 最终 commit 由 clean checkout 上生成的 release manifest 记录；不在被提交文件中硬编码，
  避免 commit 自引用。

## 3. 内容与安全复核

- [x] 题号为 XA-202620，题目全称与赛题原文一致。
- [x] D1 18 页，不超过 30 页；全页渲染抽检完成。
- [x] D3 8:50，不超过 10 分钟；1920×1080、30fps、H.264/AAC。
- [x] D3 有中文可开关字幕轨和独立 SRT。
- [x] D1/D3/QA 的所有数字来自 `FROZEN-NUMBERS.md`。
- [x] 真实模型、确定性 OAR、Gate1 诊断集与 canonical 结果分轨报告。
- [x] D1 5/5 allow/harm 边界已披露。
- [x] D3 0/10 attempt 未归因 XA-Guard。
- [x] 无 API key、token、私钥、DSN、账号、个人隐私或本机绝对路径。
- [x] 无攻击 payload 或攻击脚本；原始 runtime 未进入 Git。
- [x] 本地 TSA/软件密钥未写成第三方 TSA/HSM。
- [x] local kind 未写成生产 HA。
- [x] R2/R3 sampled 与 research full matrix 保持退役/可选，不写成比赛 blocker。

## 4. D2 发布复核

- [x] OAR kernel tests 已进入 CI 与 `scripts/verify_release.py`。
- [x] live authenticity 严格检查 30/30 per-run verdict、稳定/因果重算与 15/15 audit。
- [x] `.runtime` 与 `open-agent-range/.runtime` 全面忽略。
- [x] 原先被跟踪的 runtime 已从 Git 索引移除，本地副本保留可复核。
- [x] 公开 live evidence 只含脱敏聚合、哈希与边界。
- [ ] 在最终 clean commit 上运行 `python scripts/build_release_manifest.py`，把生成的 manifest
  与仓库 URL 一并保存到外部提交包。

该未勾选项必须在最终 commit 之后执行，因此不是实现缺口，也不能提前伪造。

## 5. 外部提交

- [ ] 复核 D4 在报名系统仍显示审核通过。
- [ ] 确认最终仓库 URL 对评委可访问。
- [ ] 上传 D3 和可选证据包，检查网盘权限与有效期。
- [ ] 邮件正文首行写题号和题目全称。
- [ ] 附 D1 PDF。
- [ ] 附 D2 仓库 URL 与复现说明。
- [ ] 附 D3 URL。
- [ ] 附 D4。
- [ ] 保存已发送邮件、回执、报名状态和网盘访问截图。

只有负责人实际完成后才能勾选本节；仓库不会把外部动作伪造为已完成。
