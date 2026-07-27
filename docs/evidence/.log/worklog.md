# worklog - evidence

## 2026-07-27
P1-1：攻击证明集 OAR live A/B 重跑为 N=10 并封存。两次 LIMIT run（harness 子进程启动挂起，非防护失败）完整保留；修复 sut.py 启动重试后 run `xa-attack-proof-v1-20260727T033934Z-win-local` PASS（6/6、protected replay 20/20、根清单 730/730 含 40 子清单、tarball `435d1705...8e5b`）。公开导出 `attack-proof-set-2026-07-27-n10/` 六件套，独立目录复跑字节级一致；新叙述页建立，2026-07-26 N=3 页转为历史标注。旧 run 均未覆盖。

## 2026-07-11
完成证据全量收敛：新跑并封存 OAR full-day + live N=3 A/B canonical run；建立 `EVIDENCE-INDEX.json` 与总表；校验 R4 8/8、R7 20/20、R8 7/7、R9 10/10、R6/OAR sealed hash。R8 修复 Git EOL 字节漂移。未完成 D1 PDF、D2 release freeze、D3 视频、D4 报名。
