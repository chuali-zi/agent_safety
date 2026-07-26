# docs/delivery 工作日志

## 2026-07-26 D1 评分维度审阅 + 提交材料收口计划

对照赛题 PDF（创新 25 / 效果 30 / 完整 20 / 价值 20 / 表达 5）复核两份 D1 稿与 D3 脚本。
未改产品、测试、证据或 D1/D3 正文，未重跑实验。

产出：[D1-D3-submission-plan.md](../D1-D3-submission-plan.md)（决策 5、P0 6、P1 4、P2 3、镜头表、风险 8）、
[REVIEW-2026-07-26.md](../REVIEW-2026-07-26.md)（负责人视角）；同步 `status.md`、`log.md` 顶条、
`submission-checklist.md` 与 `D3-video-script.md` 顶部提示。

三条主要结论：

1. **v0.2 稿当前构建不出 PDF**——无 pagebreak 标记、用 mermaid 而非 `[DIAGRAM:x]`，
   `scripts/build_d1_pdf.py:154` 直接 ValueError（已实测）。列为 P0-6，须第一周修。
2. **占 30% 的"实际效果"缺赛题点名的识别率与误报率**（两稿 grep 均 0 次），
   但 `gate1-l3-evaluation-2026-06-18.json` 的 `gate1_scope` 已有数字：60 例召回 1.0、
   误报 0/134（Wilson 上界 6.21%）、p95 0.04ms。总体 0.3575 是归属误配——
   193 例中 133 例属治理类，由 Gate2/3/5+AIBOM 裁决而非 Gate1。改为分层表 + 四条范围声明。
3. **D3 现行八镜头方向一/三 0 秒出镜**，无 live 攻击拦截与 AIBOM 画面。前 4 分钟重排为四方向实拍。

冻结依赖链：**数字 → 视频 → PDF**。8 月初一次性重跑后冻数字，8 月底录像，9 月初冻 PDF，9/12–14 提交。
