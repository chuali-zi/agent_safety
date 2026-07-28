# XA-Guard 最终 TODO

> 状态：**仓库内比赛计划全部完成；只剩外部提交动作**
> 更新：2026-07-27
> 权威口径：[Delivery v2](../acceptance/DELIVERY-v2.md)

## 1. 已完成

| 项 | 状态 | 结果 |
|---|---|---|
| D1 正式 PDF | **DONE** | 18 页；正式封面、题号、题名、实验/边界/证据齐全 |
| D2 代码与复现 | **DONE / RELEASE-READY** | 代码、测试、CI、release verifier、CODE-MAP、脱敏证据齐全 |
| D3 正式视频 | **DONE** | 8:50；真实客户端、真实模型因果、Console、工程与边界齐全 |
| D4 | **DONE-MANUAL** | 负责人既有审核通过确认保持 |
| 答辩材料 | **DONE** | DEFENSE-QA、CODE-MAP、FROZEN-NUMBERS |
| governance 静态计划 | **DONE** | 48 项声明测试通过 |
| Identity + Undo 竖切计划 | **DONE** | 两轮竖切和最终产品化证据均已闭环 |
| 攻击证明集交接计划 | **DONE** | 6/6 verified、N=10 封存、公开脱敏摘要 |
| D3-P0-1 | **DONE** | OpenCode + DeepSeek Flash + XA-Guard MCP 真实安全调用通过 |
| live authenticity | **DONE** | 30/30 verdict、stable/causal 重算、15/15 audit 严格覆盖 |

## 2. 下一步只做外部提交

这些动作需要负责人账号、报名系统和网盘权限，不是仓库实现缺口：

1. 核对 D4 在报名系统仍显示审核通过；
2. 上传 D3 视频和可选证据包，确认链接有效期；
3. 核对最终仓库 URL 可访问；
4. 邮件正文首行写“XA-202620 面向政企场景的大模型智能体安全关键技术研究”；
5. 附 D1、D2 URL、D3 URL 和 D4；
6. 保存发送回执、网盘权限与报名状态截图。

## 3. 不再执行

- 不为凑页数扩写 D1；
- 不新增攻击 payload 或攻击脚本；
- 不修改测试、oracle、策略阈值来追求更好数字；
- 不把 R2/R3 sampled、research full matrix、第三方 TSA/HSM 或生产 HA 重新列为比赛 blocker；
- 不把真实 D1 5/5 allow/harm 隐藏或改写为防护成功；
- 不把 D3 0/10 attempt 归因 XA-Guard。
