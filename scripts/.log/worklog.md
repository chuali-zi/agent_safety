## 2026-07-26
仅按用户范围修改 build_d1_pdf.py：默认 SOURCE 指向 review draft，parse 无 pagebreak 容错，支持 fenced code 与 5 个 Mermaid 块离线绘制，并保留 [DIAGRAM:x]。验证：新稿临时 PDF 13 页、旧稿兼容 14 页、py_compile 通过；未改正文/测试/status/root log/正式 output。

# Scripts module work log

## 2026-07-20 OpenCode
- Added an optional dev-only timing sidecar to the Identity + Undo benchmark.
- The formal evidence schema, thresholds, paired samples, and bootstrap method are unchanged.
- The sidecar stores only trace IDs and numeric timings, never tokens or credentials.
