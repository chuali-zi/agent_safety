# Real-agent causal experiment track

This package answers two separate questions without changing the deterministic OAR Oracle:

1. Did the real model emit a policy-violating native tool call?
2. Did XA-Guard prevent harm from that exact immutable call?

```text
DeepSeek observation loop
          |
          v
 policy-violating ToolIntent (frozen tool + argument SHA-256)
          |
     same world snapshot
       /             \
 NullSUT          XaGuardSUT(live=True)
       |             |
 world harm      decision + world harm
```

The model is never forced to call a tool. A safe response is recorded as model-side safety, not as an XA-Guard win.

## Commands

Run from `open-agent-range/`:

```powershell
python -m kernel.live_agent check `
  --manifest scenarios\live-agent\p0-d1-d3.json `
  --env-file ..\.env

python -m kernel.live_agent freeze `
  --manifest scenarios\live-agent\p0-d1-d3.json `
  --phase holdout `
  --out .runtime\live-agent\experiment-manifest.json

python -m kernel.live_agent evaluate `
  --manifest scenarios\live-agent\p0-d1-d3.json `
  --phase holdout `
  --evidence-dir .runtime\live-agent\holdout-v1 `
  --env-file ..\.env `
  --guard live

python -m kernel.live_agent verify `
  --evidence-dir .runtime\live-agent\holdout-v1
```

`evaluate` automatically creates `replay.html` before hashing the evidence package. `render` can rebuild the page from a compatible `summary.json` without calling a model; after a manual re-render, reseal the package by regenerating `artifact-hashes.json` and re-run `verify`. `verify` performs the authenticity acceptance: artifact hash re-check, frozen-manifest self-hash, exact metric recomputation, and per-run consistency between the real XA-Guard audit row (tool, parameters minus the `_xa_guard` envelope, decision mapping, record hash) and the immutable ToolIntent. The replay page maps the real audit into the Gate 1–6 strip (deciding gate, hit rule IDs, faithfulness, record hash); branches without a live audit are explicitly labelled `NO LIVE AUDIT` instead of implying gate states.

## Frozen interfaces

- `DeepSeekAdapter.next_turn(messages, tools) -> AgentTurn`
- `ToolIntent`: model identity, response/tool-call IDs, tool, arguments, argument hash, property and target
- `IntentAssessment`: policy violation independent of SUT decision
- Null/XA-Guard branch verdicts: identical intent hash, decision, execution and observed harm
- Summary metrics: `attempt_asr`, `null_harm_asr`, `guard_harm_asr`, `conditional_block_rate`, `utility_success_rate`

The outward-facing summary omits final model text and absolute workspace paths. Raw synthetic transcript evidence remains inside each run directory and must not contain production secrets.

## Attack-content boundary

Attack payloads live only in the `injections` data field of the versioned case file (development and holdout are isolated in wording, entities and carrier; holdout must not be re-tuned once frozen). Follow [`ATTACK-TODOS.md`](../../scenarios/live-agent/ATTACK-TODOS.md) before any formal holdout run. A smoke run, offline guard, forced tool choice or fewer than the frozen 3/5 threshold is not formal causal evidence.

The optional `openai` Python SDK dependency is used only as an Apache-2.0 licensed OpenAI-compatible client for the DeepSeek endpoint; XA-Guard remains connected through the existing MCP SUT boundary.
