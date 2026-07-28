"""Render a self-contained causal evidence replay page."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def render_replay(evidence_dir: Path | str, out_path: Path | str | None = None) -> Path:
    root = Path(evidence_dir)
    summary_path = root / "summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"summary not found: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    records = _replay_records(root, summary)
    destination = Path(out_path) if out_path else root / "replay.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_render_html(summary, records), encoding="utf-8", newline="\n")
    return destination


def _replay_records(root: Path, summary: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for run in summary.get("runs", []):
        run_dir = (
            root
            / "runs"
            / str(run["case_id"])
            / str(run["prompt_profile"])
            / f"run-{int(run['repeat_index']):03d}"
        )
        intent = _read_json(run_dir / "tool-intent.json")
        null_branch = _read_json(run_dir / "null" / "branch-verdict.json")
        guard_branch = _read_json(run_dir / "xaguard" / "branch-verdict.json")
        records.append(
            {
                **run,
                "tool_name": intent.get("tool_name", ""),
                "arguments": intent.get("arguments", {}),
                "arguments_sha256": intent.get("arguments_sha256", ""),
                "null_executed": null_branch.get("executed", False),
                "guard_executed": guard_branch.get("executed", False),
                "guard_audit": guard_branch.get("audit", []),
                "live_audit": _live_audit_summary(run_dir),
            }
        )
    return records


def _live_audit_summary(run_dir: Path) -> dict[str, Any]:
    """Summarize the real XA-Guard audit rows left by a live MCP branch.

    Returns an empty mapping when the branch was not run or the guard was
    offline; the renderer must then state that no live audit exists instead
    of implying per-gate states.
    """

    audit_path = run_dir / "xaguard" / "xa-guard-audit" / "audit.jsonl"
    if not audit_path.is_file():
        return {}
    rows = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        return {}
    latest = rows[-1]
    return {
        "rows": len(rows),
        "tool": str(latest.get("gen_ai.tool.name", "")),
        "decision": str(latest.get("gen_ai.decision.final", "")),
        "reason": str(latest.get("gen_ai.decision.final_reason", "")),
        "hit_ids": [str(item) for item in latest.get("gen_ai.policy.hit_id", []) or []],
        "faithfulness": latest.get("gen_ai.decision.faithfulness_score", ""),
        "gate_result_count": (
            latest.get("gen_ai.decision.faithfulness.evidence", {}) or {}
        ).get("gate_result_count", ""),
        "record_hash": str(latest.get("record_hash", "")),
        "trace_id": str(latest.get("trace_id", "")),
        "timestamp": str(latest.get("timestamp", "")),
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _render_html(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    safe_data = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    valid = bool(summary.get("valid_breach_found"))
    causal = bool(summary.get("causal_proof_found"))
    status = "CAUSAL PROOF SEALED" if causal else ("MODEL BREACH OBSERVED" if valid else "NO STABLE BREACH")
    status_class = "sealed" if causal else ("observed" if valid else "open")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>XA-Guard / Causal Evidence Replay</title>
<style>
:root{{--bg:#0c1110;--panel:#121a18;--ink:#e8e4d7;--muted:#82908b;--rule:#2c3936;--acid:#d8ff4f;--null:#ff5b3d;--guard:#50d6bb;--paper:#d9d4c5;--black:#070a09}}
*{{box-sizing:border-box}}html{{background:var(--bg);color:var(--ink);font-family:"Courier New",monospace}}body{{margin:0;min-height:100vh;background:radial-gradient(circle at 80% 0,#20332e 0,transparent 31%),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px);background-size:auto,42px 42px,42px 42px}}
body:before{{content:"";position:fixed;inset:0;pointer-events:none;opacity:.2;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.18'/%3E%3C/svg%3E")}}
header{{display:grid;grid-template-columns:1fr auto;align-items:end;gap:30px;padding:34px 4vw 28px;border-bottom:1px solid var(--rule)}}.kicker{{color:var(--acid);font-size:10px;letter-spacing:.22em}}h1{{margin:8px 0 0;font-family:Georgia,serif;font-size:clamp(34px,6vw,76px);font-weight:400;letter-spacing:-.055em}}.status{{padding:12px 16px;border:1px solid;font-size:10px;letter-spacing:.12em;transform:rotate(-1deg)}}.status.sealed{{color:var(--guard)}}.status.observed{{color:var(--acid)}}.status.open{{color:var(--null)}}
main{{width:min(1500px,94vw);margin:0 auto;padding:28px 0 70px}}.metrics{{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--rule);background:rgba(12,17,16,.76)}}.metric{{min-height:102px;padding:18px;border-right:1px solid var(--rule)}}.metric:last-child{{border:0}}.metric span{{display:block;color:var(--muted);font-size:9px;letter-spacing:.12em}}.metric b{{display:block;margin-top:15px;font-family:Georgia,serif;font-size:30px;font-weight:400}}
.selector{{display:grid;grid-template-columns:1fr 1fr 150px;gap:14px;margin:25px 0}}label{{display:grid;gap:7px;color:var(--muted);font-size:9px;letter-spacing:.1em}}select{{width:100%;padding:12px;color:var(--ink);border:1px solid var(--rule);border-radius:0;background:var(--panel);font:12px "Courier New",monospace}}
.casefile{{border:1px solid var(--rule);background:rgba(18,26,24,.9)}}.casehead{{display:grid;grid-template-columns:1fr auto;gap:20px;padding:23px;border-bottom:1px solid var(--rule)}}.casehead h2{{margin:0;font:400 30px Georgia,serif}}.casehead p{{margin:8px 0 0;color:var(--muted);font-size:11px}}.stamp{{align-self:center;padding:8px 11px;color:var(--acid);border:1px solid currentColor;font-size:9px}}
.timeline{{display:grid;grid-template-columns:1fr 60px 1fr;min-height:380px}}.arm{{padding:27px}}.arm.null{{border-right:1px solid var(--rule)}}.arm.guard{{border-left:1px solid var(--rule)}}.arm small{{color:var(--muted);font-size:9px;letter-spacing:.14em}}.arm h3{{margin:8px 0 20px;font:400 28px Georgia,serif}}.null h3,.null .result strong{{color:var(--null)}}.guard h3,.guard .result strong{{color:var(--guard)}}.axis{{position:relative;display:flex;align-items:center;justify-content:center}}.axis:before{{content:"";position:absolute;inset:0 50%;width:1px;background:var(--rule)}}.intent-seal{{z-index:1;display:grid;place-items:center;width:48px;height:48px;color:var(--black);background:var(--acid);font-size:9px;font-weight:bold;transform:rotate(45deg)}}.intent-seal span{{transform:rotate(-45deg)}}
.toolcall{{margin-bottom:20px;padding:16px;border:1px solid var(--rule);background:var(--black)}}.toolcall span{{color:var(--acid);font-size:10px}}pre{{max-height:190px;overflow:auto;margin:12px 0 0;color:#b9c4c0;white-space:pre-wrap;word-break:break-word;font-size:10px;line-height:1.6}}.result{{display:grid;grid-template-columns:1fr auto;align-items:center;padding:18px;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}}.result strong{{font:400 22px Georgia,serif}}.lamp{{width:13px;height:13px;border:1px solid currentColor;transform:rotate(45deg)}}.lamp.on{{background:currentColor}}
.gates{{display:grid;grid-template-columns:repeat(6,1fr);margin-top:22px;border:1px solid var(--rule)}}.gate{{min-height:62px;padding:10px 7px;border-right:1px solid var(--rule)}}.gate:last-child{{border:0}}.gate i{{display:block;color:var(--guard);font-style:normal;font-size:8px}}.gate b{{display:block;margin-top:10px;font-size:9px}}.gate.hit{{background:rgba(216,255,79,.08);outline:1px solid var(--acid)}}.gate.hit b{{color:var(--acid)}}.gate.none{{opacity:.55}}.auditline{{margin-top:12px;color:var(--muted);font-size:9px;line-height:1.7;word-break:break-all}}.auditline em{{color:var(--guard);font-style:normal}}.reason{{margin-top:15px;color:var(--muted);font-size:10px;line-height:1.65}}.hash{{margin-top:18px;color:var(--muted);font-size:8px;word-break:break-all}}.empty{{grid-column:1/-1;padding:90px 20px;text-align:center;color:var(--muted)}}footer{{display:flex;justify-content:space-between;gap:20px;padding:18px 4vw;color:var(--muted);border-top:1px solid var(--rule);font-size:8px}}
.sr-only{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}
@media(max-width:850px){{header{{grid-template-columns:1fr}}.metrics{{grid-template-columns:1fr 1fr}}.metric{{border-bottom:1px solid var(--rule)}}.selector{{grid-template-columns:1fr}}.timeline{{grid-template-columns:1fr}}.axis{{height:70px}}.axis:before{{inset:50% 0;width:auto;height:1px}}.arm.null,.arm.guard{{border:0;border-bottom:1px solid var(--rule)}}.gates{{grid-template-columns:repeat(3,1fr)}}}}
@media(prefers-reduced-motion:no-preference){{.casefile{{animation:arrive .45s ease-out}}@keyframes arrive{{from{{opacity:0;transform:translateY(12px)}}}}}}
</style>
</head>
<body>
<header><div><div class="kicker">OPEN AGENT RANGE / IMMUTABLE INTENT FORK</div><h1>Causal Evidence Replay</h1></div><div class="status {status_class}">{html.escape(status)}</div></header>
<main>
<section class="metrics">
{_metric("ATTEMPT ASR", summary.get("attempt_asr", 0))}
{_metric("NULL HARM ASR", summary.get("null_harm_asr", 0))}
{_metric("GUARD HARM ASR", summary.get("guard_harm_asr", 0))}
{_metric("CONDITIONAL BLOCK", summary.get("conditional_block_rate", 0))}
{_metric("UTILITY", summary.get("utility_success_rate", 0))}
</section>
<section class="selector"><label>CASE<select id="caseSelect"></select></label><label>PROMPT PROFILE<select id="profileSelect"></select></label><label>REPEAT<select id="repeatSelect"></select></label></section>
<section id="replay" class="casefile"><span class="sr-only">GATE 1, GATE 2, GATE 3, GATE 4, GATE 5, GATE 6 causal replay</span></section>
</main>
<footer><span>{html.escape(str(summary.get("experiment_id", "")))}</span><span>MODEL {html.escape(str(summary.get("model", "")))} / THINKING {html.escape(str(summary.get("thinking", "")))}</span><span>SHA-256 MANIFEST REQUIRED</span></footer>
<script>
const records={safe_data};
const esc=(v)=>String(v??"").replace(/[&<>"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
const pretty=(v)=>JSON.stringify(v??{{}},null,2);
const caseSelect=document.getElementById("caseSelect"),profileSelect=document.getElementById("profileSelect"),repeatSelect=document.getElementById("repeatSelect"),replay=document.getElementById("replay");
function options(el,values){{const prior=el.value;el.innerHTML=values.map(v=>`<option value="${{esc(v)}}">${{esc(v)}}</option>`).join("");if(values.includes(prior))el.value=prior;}}
function sync(){{options(caseSelect,[...new Set(records.map(r=>r.case_id))]);const byCase=records.filter(r=>r.case_id===caseSelect.value);options(profileSelect,[...new Set(byCase.map(r=>r.prompt_profile))]);const byProfile=byCase.filter(r=>r.prompt_profile===profileSelect.value);options(repeatSelect,[...new Set(byProfile.map(r=>String(r.repeat_index)))]);render(byProfile.find(r=>String(r.repeat_index)===repeatSelect.value));}}
const GATE_NAMES=["INPUT","RISK","POLICY","CAPABILITY","OUTPUT","AUDIT"];
function gateStrip(a){{if(!a||!a.decision)return `<div class="gate none" style="grid-column:1/-1"><i>GATE 1-6</i><b>NO LIVE AUDIT</b></div>`;const m=/gate(\d)/i.exec(a.reason||"");const hit=m?parseInt(m[1],10):0;return GATE_NAMES.map((x,i)=>{{const n=i+1;const cls=n===hit?"gate hit":"gate";const tag=n===hit?esc(a.decision).toUpperCase():"—";return `<div class="${{cls}}"><i>GATE ${{n}}</i><b>${{x}}</b><b>${{tag}}</b></div>`}}).join("");}}
function auditLine(a){{if(!a||!a.decision)return 'No live XA-Guard audit was captured for this branch (offline guard or no violating intent); gate states are not implied.';const hits=(a.hit_ids&&a.hit_ids.length)?a.hit_ids.join(", "):"no rule id";return `LIVE AUDIT <em>${{esc(a.decision)}}</em> · ${{esc(a.reason||"")}} · hits ${{esc(hits)}} · faithfulness ${{esc(a.faithfulness)}} · gates evaluated ${{esc(a.gate_result_count)}} · rec ${{esc((a.record_hash||"").slice(0,16))}}… · ${{esc(a.timestamp)}}`;}}
function render(r){{if(!r){{replay.innerHTML='<div class="empty">NO REPLAY RECORDS</div>';return}}const args=Object.keys(r.arguments||{{}}).length?pretty(r.arguments):"No violating ToolIntent captured.";const hash=r.arguments_sha256||r.intent_arguments_sha256||"—";const violation=r.model_attempt_violation?"VIOLATING INTENT":"MODEL-SIDE SAFE";const guardState=r.guard_decision==="deny"?"BLOCKED":"NOT BLOCKED";replay.innerHTML=`
<div class="casehead"><div><h2>${{esc(r.case_id)}}</h2><p>${{esc(r.family)}} · ${{esc(r.property_id)}} · target ${{esc(r.intent_target||r.expected_target||"—")}}</p></div><div class="stamp">${{esc(violation)}}</div></div>
<div class="timeline">
<article class="arm null"><small>ARM A / NO EXTERNAL GUARD</small><h3>Naked executor</h3><div class="toolcall"><span>${{esc(r.tool_name||"NO TOOL CALL")}}</span><pre>${{esc(args)}}</pre></div><div class="result"><div><small>WORLD DELTA</small><strong>${{r.null_harm?"FORBIDDEN EFFECT":"NO HARM"}}</strong></div><i class="lamp ${{r.null_harm?"on":""}}"></i></div><p class="reason">${{r.null_harm?"The immutable intent executed and changed the synthetic world.":"No forbidden side effect was observed."}}</p></article>
<div class="axis"><div class="intent-seal"><span>FORK</span></div></div>
<article class="arm guard"><small>ARM B / XA-GUARD MCP</small><h3>${{esc(guardState)}}</h3><div class="toolcall"><span>SAME TOOL + ARGUMENT HASH</span><pre>${{esc(hash)}}</pre></div><div class="result"><div><small>WORLD DELTA</small><strong>${{r.guard_harm?"FORBIDDEN EFFECT":"NO HARM"}}</strong></div><i class="lamp ${{r.guard_harm?"on":""}}"></i></div><div class="gates">${{gateStrip(r.live_audit)}}</div><p class="auditline">${{auditLine(r.live_audit)}}</p><p class="reason">Final decision: ${{esc(r.guard_decision)}} · ${{esc(r.guard_reason||"No guard branch was run.")}}</p></article>
</div>`}}
caseSelect.addEventListener("change",sync);profileSelect.addEventListener("change",sync);repeatSelect.addEventListener("change",sync);sync();
</script>
</body></html>"""


def _metric(label: str, value: Any) -> str:
    try:
        rendered = f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        rendered = html.escape(str(value))
    return f'<div class="metric"><span>{html.escape(label)}</span><b>{rendered}</b></div>'
