# 下一步工作设计：提交执行

> 状态：**INTERNAL WORK COMPLETE / EXTERNAL SUBMISSION NEXT**
> 更新：2026-07-27

仓库内的设计、实现、测试、D1、D3、证据和答辩材料已经收口。下一步不再增加产品功能，
只把冻结产物交给负责人完成外部提交。

## 执行顺序

```text
确认 clean final commit
  → 生成/核对 release manifest
  → 核对 D1/D3 SHA-256
  → 上传视频与可选证据
  → 复核 D4 系统状态
  → 发送正式邮件
  → 保存回执与权限截图
```

## 冻结产物

| 产物 | 路径 |
|---|---|
| D1 | `output/pdf/XA-Guard-XA-202620-technical-report.pdf` |
| D3 | `output/video/XA-Guard-XA-202620-demo.mp4` |
| D3 字幕 | `output/video/XA-Guard-XA-202620-demo.srt` |
| D3 metadata | `output/video/XA-Guard-XA-202620-demo.metadata.json` |
| 答辩 QA | `docs/delivery/DEFENSE-QA.md` |
| 代码地图 | `docs/delivery/CODE-MAP.md` |
| 数字源 | `docs/delivery/FROZEN-NUMBERS.md` |
| 最终清单 | `docs/delivery/submission-checklist.md` |

## 变更纪律

- 只允许修复确认的交付缺陷；任何数字变更都必须来自新封存证据并同步 D1/D3/数字源。
- 不再修改真实 Agent holdout payload、case oracle 或阈值。
- 不把外部提交动作提前写成已完成。
- 不把退役研究矩阵重新解释为比赛交付缺口。
- `status.md` 只写当前状态；`log.md` 顶部记录客观历史。
