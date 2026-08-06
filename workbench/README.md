# XA-Guard Live Workbench（靶场演示 GUI）

单屏 1920×1080 演示 GUI：假智能体（live agent）→ 冻结 ToolIntent → Null 无防护对照 →
XA-Guard Gate1–Gate6 → 因果 delta → verifier 全过程可视化。
契约与纪律见 `docs/demo-handoff/contracts.md`（本目录是它的实现）。

## 启动

```bash
python -m pip install -e ".[workbench]"  # LIVE 模式另加 live-agent extra
python -m workbench.server --port 8787 \
  --manifest open-agent-range/scenarios/live-agent/p0-d1-d3-v2.json \
  --env-file .env          # 可选；只在 LIVE 模式需要，值绝不回显
# 浏览器打开 http://127.0.0.1:8787/
```

录屏/无头验证：`http://127.0.0.1:8787/?scenario=<scenario_id>&autorun=1` 自动选择并运行。

## 三种运行模式（视觉上不可混淆）

| 模式 | scenario_id | 数据来源 | 徽标 |
|---|---|---|---|
| LIVE RUN | `live:<case_id>` | 真实模型 + XA-Guard live stdio 当次实跑 | 蓝色 LIVE RUN |
| SEALED REPLAY | `sealed:<pack>/<case>/<profile>/<run-NNN>` | `open-agent-range/.runtime/live-agent/` 封存包 artifact | 紫色 SEALED REPLAY |
| EXAMPLE / SYNTHETIC | `synthetic:d2|utility|hitl|verifier` | 脚本化假数据动画，**不是证据** | 灰斜纹 EXAMPLE / SYNTHETIC |

## Gate rail 推导规则（诚实映射）

audit.jsonl 没有逐 Gate 字段，只有 final decision / reason / faithfulness evidence：

- 决定 Gate：从 `gen_ai.decision.final_reason` 的 `gateN_*` 前缀解析（如 `gate3_policy` → GATE3）；
  该格显示实际 decision、`record_hash`、hit ids、faithfulness。
- 决定 Gate 之前：`UNKNOWN`（audit 未记录逐 Gate 结果，不渲染为“安全通过”）。
- 决定 Gate 之后：`NOT_REACHED`。
- GATE5：无 sandbox 工件一律 `NOT_REACHED`。
- GATE6：存在带 `record_hash` 的 audit 记录 → `ALLOW`（已落链，展示 hash）。
- allow 且 reason 含 `warn`（如 `gate2_plan: warned`）→ 对应 Gate `WARN`。

## API（仅 127.0.0.1）

`POST /api/live/preflight|run|verify|verify-tampered-copy`，`GET /api/live/scenarios|runs|events|artifact`，
`POST /api/live/operator`（仅 EXAMPLE_SYNTHETIC 的 HITL 按钮通道）。
安全纪律：artifact 名白名单、pack 路径限定在 packs-root 内、响应脱敏（敏感键/绝对路径/超长串）、
同名 artifact 按事件中的 SHA-256 精确选择（不猜 run/Null/Guard 分支）、写请求带未知字段 → 400、
tamper 只作用于新建复制包且验证后删除。transcript 的正文/参数以及 world、ledger、tool output
只返回摘要或 digest，不进入 DOM/录屏。

## claim 红线（沿用 status.md §4）

- SYNTHETIC 画面与 `docs/demo-handoff/examples/` 一样只是演示材料，不得截图为实跑证据。
- `MODEL_SELF_DEFENSE` 不计 Guard win；deny/pending 时 downstream 必须显示 0（来自真实 ledger）。
- A/B intent/world hash 不一致时 UI 显示 `INVALID_COMPARISON`，不下因果结论。
- LIVE RUN 的单次结果 ≠ 封存正式证据包；正式 claim 仍以 verifier PASS 的封存包为准。

## 环境变量

- `XA_WORKBENCH_SYNTHETIC_DELAY`（默认 0.9 秒）：合成演示节奏。

## 测试

```bash
python -m pytest tests/test_workbench_events.py tests/test_workbench_replay.py \
  tests/test_workbench_api.py tests/test_workbench_verify.py -q
```
