#!/usr/bin/env python3
"""Run and verify the frozen independent HTTP Agent/Operator HITL scenario.

The harness writes only secret-free artifacts under the gitignored OAR runtime
directory. It requires freshly issued JWTs in the repo-root .env and refuses to
start the server unless the existing credential preflight passes.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import httpx
import yaml
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


ROOT = Path(__file__).resolve().parents[1]
OAR = ROOT / "open-agent-range"
if str(OAR) not in sys.path:
    sys.path.insert(0, str(OAR))

from kernel.live_agent.http_operator_hitl import (  # noqa: E402
    HitlConfig,
    credential_preflight,
)
from kernel.live_agent.models import sha256_json  # noqa: E402
from kernel.live_agent.runner import load_local_env  # noqa: E402
from xa_guard.audit.archive import verify_audit_jsonl  # noqa: E402


DEFAULT_MANIFEST = OAR / "scenarios/live-agent/http-operator-hitl-v1.json"
DEFAULT_ENV = ROOT / ".env"
DEFAULT_RUN_ROOT = OAR / ".runtime/http-operator-hitl"
HASH_EXCLUDES = {
    "artifact-hashes.json",
    "verification.json",
    "tamper-verification.json",
}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_hashes(run_dir: Path) -> dict[str, str]:
    return {
        path.relative_to(run_dir).as_posix(): _sha256_file(path)
        for path in sorted(run_dir.rglob("*"))
        if path.is_file() and path.name not in HASH_EXCLUDES
    }


def verify_run(run_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    hashes_path = run_dir / "artifact-hashes.json"
    result_path = run_dir / "live-result.json"
    if not hashes_path.is_file():
        errors.append("artifact-hashes.json is missing")
        expected_hashes: dict[str, str] = {}
    else:
        expected_hashes = dict(_read_json(hashes_path).get("files", {}))
    actual_hashes = _artifact_hashes(run_dir)
    if expected_hashes != actual_hashes:
        errors.append("artifact hash map differs from the sealed map")
    if not result_path.is_file():
        errors.append("live-result.json is missing")
    else:
        result = _read_json(result_path)
        if result.get("live_result") != "PASS":
            errors.append("live result is not PASS")
        checks = list(result.get("checks", []))
        if not checks or not all(item.get("ok") is True for item in checks):
            errors.append("one or more live checks failed")
    return {
        "schema_version": "xa-guard-http-operator-hitl-verification/v1",
        "ok": not errors,
        "checked_files": len(actual_hashes),
        "errors": errors,
    }


def _render_config(config: HitlConfig, run_dir: Path) -> Path:
    value = yaml.safe_load(config.template_path.read_text(encoding="utf-8"))
    xa = value["xa_guard"]
    source_jwks = Path(os.environ[str(config.identity["jwks_file_env"])]).resolve()
    target_jwks = run_dir / "jwks-public.json"
    shutil.copyfile(source_jwks, target_jwks)
    xa["identity"]["issuers"][0]["jwks_file"] = str(target_jwks.resolve())
    xa["gates"]["gate6"]["audit_dir"] = str((run_dir / "audit").resolve())
    xa["pending_approvals_path"] = str((run_dir / "pending-approvals.jsonl").resolve())
    output = run_dir / "server-config.yaml"
    output.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return output


def _wait_for_health(url: str, timeout_seconds: float, process: subprocess.Popen[Any]) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited before health check (code={process.returncode})")
        try:
            with urlopen(url, timeout=1.0) as response:  # noqa: S310 - frozen loopback URL
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.1)
    raise TimeoutError(f"health check timed out: {last_error}")


def _texts(result: Any) -> list[str]:
    return [str(getattr(item, "text", "")) for item in (getattr(result, "content", None) or [])]


def _one_json_text(result: Any) -> dict[str, Any]:
    texts = _texts(result)
    if len(texts) != 1:
        raise ValueError("expected exactly one MCP text content item")
    return dict(json.loads(texts[0]))


def _ledger_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def _exercise(config: HitlConfig, ledger: Path) -> dict[str, Any]:
    agent_headers = {"Authorization": f"Bearer {os.environ[str(config.agent['token_env'])]}"}
    operator_headers = {
        "Authorization": f"Bearer {os.environ[str(config.operator['token_env'])]}",
        str(config.operator["credential_header"]): os.environ[str(config.operator["credential_env"])],
    }
    agent_url = str(config.server["base_url"]) + str(config.server["agent_path"])
    operator_url = str(config.server["base_url"]) + str(config.server["operator_path"])
    envelope = {
        "human_principal": str(config.agent["human_principal"]),
        "agent_id": str(config.agent["agent_id"]),
        "tenant_id": str(config.identity["tenant_id"]),
    }

    async with httpx.AsyncClient(headers=agent_headers, timeout=15.0) as http_client:
        async with streamable_http_client(agent_url, http_client=http_client) as streams:
            read_stream, write_stream, get_session_id = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                agent_session_id = str(get_session_id() or "")
                agent_tools = sorted(tool.name for tool in (await session.list_tools()).tools)
                call_arguments = {**dict(config.case["arguments"]), "_xa_guard": envelope}
                pending_result = await session.call_tool(str(config.case["tool_name"]), call_arguments)
                pending_text = "\n".join(_texts(pending_result))

    match = re.search(r"trace_id=([0-9a-fA-F-]{16,})", pending_text)
    if not match or "等待人工审批" not in pending_text:
        raise RuntimeError(f"Agent call did not return a pending trace: {pending_text[:240]}")
    trace_id = match.group(1)
    executions_after_pending = len(_ledger_rows(ledger))

    async with httpx.AsyncClient(headers=operator_headers, timeout=15.0) as http_client:
        async with streamable_http_client(operator_url, http_client=http_client) as streams:
            read_stream, write_stream, get_session_id = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                operator_session_id = str(get_session_id() or "")
                operator_tools = sorted(tool.name for tool in (await session.list_tools()).tools)
                listed = _one_json_text(
                    await session.call_tool(
                        "xa_guard_operator_list_pending",
                        {"tenant_id": str(config.identity["tenant_id"])},
                    )
                )
                decided = _one_json_text(
                    await session.call_tool(
                        "xa_guard_operator_decide",
                        {
                            "trace_id": trace_id,
                            "approve": True,
                            "reason": str(config.case["operator_reason"]),
                            "tenant_id": str(config.identity["tenant_id"]),
                        },
                    )
                )
                executions_after_approval = len(_ledger_rows(ledger))
                replayed = _one_json_text(
                    await session.call_tool(
                        "xa_guard_operator_decide",
                        {
                            "trace_id": trace_id,
                            "approve": True,
                            "reason": str(config.case["operator_reason"]),
                            "tenant_id": str(config.identity["tenant_id"]),
                        },
                    )
                )
                executions_after_replay = len(_ledger_rows(ledger))

    return {
        "trace_id": trace_id,
        "agent_session_id_sha256": hashlib.sha256(agent_session_id.encode()).hexdigest(),
        "operator_session_id_sha256": hashlib.sha256(operator_session_id.encode()).hexdigest(),
        "agent_tools": agent_tools,
        "operator_tools": operator_tools,
        "pending_response": pending_text,
        "listed": listed,
        "decided": decided,
        "replayed": replayed,
        "executions_after_pending": executions_after_pending,
        "executions_after_approval": executions_after_approval,
        "executions_after_replay": executions_after_replay,
    }


def _audit_rows(path: Path) -> list[dict[str, Any]]:
    return _ledger_rows(path)


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _secret_scan(run_dir: Path, config: HitlConfig) -> tuple[bool, list[str]]:
    secret_values = {
        name: os.environ.get(name, "").encode("utf-8")
        for name in config.required_env_names
        if name != str(config.identity["jwks_file_env"])
    }
    findings: list[str] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        for name, value in secret_values.items():
            if value and value in data:
                findings.append(f"{path.relative_to(run_dir).as_posix()} contains {name}")
        if b"-----BEGIN PRIVATE KEY-----" in data or b'"d":' in data:
            findings.append(f"{path.relative_to(run_dir).as_posix()} contains private-key material")
    return not findings, findings


def run_live(manifest: Path, env_file: Path, run_root: Path) -> tuple[int, Path]:
    load_local_env(env_file)
    config = HitlConfig.load(manifest)
    preflight = credential_preflight(config)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = run_root / f"run-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(run_dir / "preflight.json", preflight)
    if not preflight["ready_for_live_execution"]:
        result = {
            "schema_version": "xa-guard-http-operator-hitl-live-result/v1",
            "live_executed": False,
            "live_result": "NOT_RUN",
            "checks": [_check("preflight", False, "credential preflight did not pass")],
        }
        _write_json(run_dir / "live-result.json", result)
        _write_json(run_dir / "artifact-hashes.json", {"files": _artifact_hashes(run_dir)})
        return 2, run_dir

    rendered_config = _render_config(config, run_dir)
    ledger = run_dir / "target-executions.jsonl"
    audit_path = run_dir / "audit/audit.jsonl"
    server_env = os.environ.copy()
    python_path = [str(ROOT / "src"), str(ROOT), str(OAR)]
    if server_env.get("PYTHONPATH"):
        python_path.append(server_env["PYTHONPATH"])
    server_env["PYTHONPATH"] = os.pathsep.join(python_path)
    server_env["PYTHONIOENCODING"] = "utf-8"
    server_env["XA_HITL_TARGET_LEDGER"] = str(ledger.resolve())
    log_path = run_dir / "server.log"
    process: subprocess.Popen[Any] | None = None
    exercise: dict[str, Any] = {}
    runtime_error = ""
    health: dict[str, Any] = {}
    with log_path.open("wb") as log_handle:
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "xa_guard.server", "--config", str(rendered_config)],
                cwd=ROOT,
                env=server_env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
            health_url = str(config.server["base_url"]) + str(config.server["health_path"])
            health = _wait_for_health(
                health_url,
                float(config.server.get("startup_timeout_seconds", 30)),
                process,
            )
            exercise = asyncio.run(_exercise(config, ledger))
        except Exception as exc:
            runtime_error = f"{type(exc).__name__}: {exc}"
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

    rows = _audit_rows(audit_path)
    trace_id = str(exercise.get("trace_id", ""))
    tool_rows = [
        row for row in rows
        if row.get("trace_id") == trace_id and row.get("gen_ai.tool.name") == config.case["tool_name"]
    ]
    decisions = [row.get("gen_ai.decision.final") for row in tool_rows]
    target_rows = _ledger_rows(ledger)
    listed_items = list(exercise.get("listed", {}).get("pending_approvals", []))
    listed_match = next((item for item in listed_items if item.get("trace_id") == trace_id), {})
    expected_operator_tools = sorted(config.evidence_contract["operator_plane_tools"])
    audit_verify = verify_audit_jsonl(audit_path, algo="sha256") if audit_path.is_file() else {"ok": False, "record_count": 0}
    approval_rows = [row for row in tool_rows if row.get("gen_ai.decision.final") == "allow"]
    approval_token_values = [str(row.get("gen_ai.tool.approval_token") or "") for row in approval_rows]
    checks = [
        _check("preflight", True, "static and credential preflight passed"),
        _check("server_health", health.get("status") == "ok", "loopback health endpoint returned ok"),
        _check("runtime", not runtime_error, runtime_error or "MCP sequence completed"),
        _check(
            "distinct_sessions",
            bool(exercise.get("agent_session_id_sha256"))
            and exercise.get("agent_session_id_sha256") != exercise.get("operator_session_id_sha256"),
            "Agent and Operator MCP session identifiers differ",
        ),
        _check(
            "agent_plane_tools",
            not any(name.startswith("xa_guard_operator_") for name in exercise.get("agent_tools", [])),
            "Agent plane does not list Operator tools",
        ),
        _check(
            "operator_plane_tools",
            exercise.get("operator_tools") == expected_operator_tools,
            "Operator plane exposes exactly the two frozen tools",
        ),
        _check(
            "pending_exact_request",
            listed_match.get("tool_name") == config.case["tool_name"]
            and listed_match.get("arguments") == config.case["arguments"]
            and sha256_json(listed_match.get("arguments", {})) == sha256_json(config.case["arguments"]),
            "listed pending request preserves frozen tool and exact argument hash",
        ),
        _check(
            "pending_zero_execution",
            exercise.get("executions_after_pending") == 0,
            "pending request caused zero downstream executions",
        ),
        _check(
            "approval_execution",
            exercise.get("decided", {}).get("ok") is True
            and exercise.get("decided", {}).get("decision") == config.case["expected_resume_decision"]
            and exercise.get("executions_after_approval") == config.case["expected_target_executions"],
            "Dora approval allowed and executed exactly once",
        ),
        _check(
            "replay_rejected",
            exercise.get("replayed", {}).get("ok") is False
            and exercise.get("replayed", {}).get("decision") == config.case["expected_replay_decision"]
            and exercise.get("executions_after_replay") == config.case["expected_target_executions"],
            "same-trace replay was denied without a second execution",
        ),
        _check(
            "target_ledger",
            len(target_rows) == config.case["expected_target_executions"]
            and all(row.get("arguments_sha256") == sha256_json(config.case["arguments"]) for row in target_rows),
            "target ledger contains exactly one simulated execution with the frozen argument hash",
        ),
        _check(
            "audit_causal_pair",
            "require_approval" in decisions
            and "allow" in decisions
            and all(row.get("gen_ai.tool.parameters") == config.case["arguments"] for row in tool_rows),
            "same trace contains require_approval then allow with identical tool parameters",
        ),
        _check(
            "audit_approver",
            bool(approval_rows)
            and all(row.get("gen_ai.tool.approval.approver") == config.operator["human_principal"] for row in approval_rows),
            "allow audit binds the independent Dora principal",
        ),
        _check(
            "approval_token_digest_only",
            bool(approval_token_values)
            and all(re.fullmatch(r"[0-9a-f]{64}", value) for value in approval_token_values),
            "audit stores only the 64-hex HMAC approval token digest",
        ),
        _check(
            "audit_hash_chain",
            audit_verify.get("ok") is True
            and bool(tool_rows)
            and all(bool(row.get("record_hash")) for row in tool_rows),
            "Gate6 audit hash chain and relevant record hashes verify",
        ),
    ]
    result = {
        "schema_version": "xa-guard-http-operator-hitl-live-result/v1",
        "experiment_id": config.raw["experiment_id"],
        "run_id": run_dir.name,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "live_executed": True,
        "live_result": "PASS" if all(item["ok"] for item in checks) else "FAIL",
        "runtime_error": runtime_error,
        "manifest_sha256": sha256_json(config.raw),
        "case": {
            "case_id": config.case["case_id"],
            "tool_name": config.case["tool_name"],
            "arguments_sha256": sha256_json(config.case["arguments"]),
            "trace_id": trace_id,
        },
        "health": health,
        "exercise": exercise,
        "audit": {"verification": audit_verify, "matching_decisions": decisions},
        "checks": checks,
    }
    _write_json(run_dir / "live-result.json", result)
    scan_ok, findings = _secret_scan(run_dir, config)
    result["checks"].append(_check("secret_scan", scan_ok, "no configured secret or private key found" if scan_ok else "; ".join(findings)))
    result["live_result"] = "PASS" if all(item["ok"] for item in result["checks"]) else "FAIL"
    _write_json(run_dir / "live-result.json", result)

    _write_json(run_dir / "artifact-hashes.json", {"files": _artifact_hashes(run_dir)})
    original_verify = verify_run(run_dir)
    _write_json(run_dir / "verification.json", original_verify)
    tampered_dir = run_root / f"tampered-{stamp}"
    shutil.copytree(run_dir, tampered_dir)
    tampered_result = _read_json(tampered_dir / "live-result.json")
    tampered_result["live_result"] = "FAIL"
    _write_json(tampered_dir / "live-result.json", tampered_result)
    tampered_verify = verify_run(tampered_dir)
    _write_json(run_dir / "tamper-verification.json", tampered_verify)

    final_ok = result["live_result"] == "PASS" and original_verify["ok"] and not tampered_verify["ok"]
    return (0 if final_ok else 1), run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    run.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    run.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    verify = sub.add_parser("verify")
    verify.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        report = verify_run(args.run_dir.resolve())
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    code, run_dir = run_live(args.manifest.resolve(), args.env_file.resolve(), args.run_root.resolve())
    report = _read_json(run_dir / "live-result.json")
    print(json.dumps({
        "run_dir": str(run_dir),
        "live_result": report.get("live_result"),
        "checks_passed": sum(1 for item in report.get("checks", []) if item.get("ok")),
        "checks_total": len(report.get("checks", [])),
        "verification_ok": _read_json(run_dir / "verification.json").get("ok") if (run_dir / "verification.json").is_file() else False,
        "tamper_rejected": not _read_json(run_dir / "tamper-verification.json").get("ok") if (run_dir / "tamper-verification.json").is_file() else False,
    }, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
