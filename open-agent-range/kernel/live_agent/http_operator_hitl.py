"""Preparation and credential preflight for independent HTTP Operator HITL live.

This module does not claim or simulate a live PASS.  ``static-check`` verifies
the frozen dual-plane contract in the repository.  ``preflight`` additionally
verifies the externally supplied JWKS, Agent token, independent Operator token,
and two local secrets without printing any secret value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from kernel.live_agent.models import sha256_json
from kernel.live_agent.runner import load_local_env

SCHEMA_VERSION = "xa-guard-http-operator-hitl-live/v1"
PRIVATE_JWK_FIELDS = {"d", "p", "q", "dp", "dq", "qi", "oth", "k"}
TEMPLATE_PLACEHOLDERS = {
    "__XA_HITL_JWKS_FILE_YAML__",
    "__XA_HITL_AUDIT_DIR_YAML__",
    "__XA_HITL_PENDING_PATH_YAML__",
}


@dataclass(frozen=True)
class HitlConfig:
    manifest_path: Path
    raw: dict[str, Any]
    template_path: Path
    server: dict[str, Any]
    identity: dict[str, Any]
    case: dict[str, Any]
    evidence_contract: dict[str, Any]

    @classmethod
    def load(cls, path: Path | str) -> "HitlConfig":
        manifest_path = Path(path).resolve()
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        template_path = (manifest_path.parent / str(raw.get("config_template", ""))).resolve()
        config = cls(
            manifest_path=manifest_path,
            raw=raw,
            template_path=template_path,
            server=dict(raw.get("server", {})),
            identity=dict(raw.get("identity", {})),
            case=dict(raw.get("case", {})),
            evidence_contract=dict(raw.get("evidence_contract", {})),
        )
        config.validate_shape()
        return config

    def validate_shape(self) -> None:
        if self.raw.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if not self.raw.get("experiment_id") or not self.case.get("case_id"):
            raise ValueError("experiment_id and case.case_id are required")
        if not self.template_path.is_file():
            raise FileNotFoundError(f"config template not found: {self.template_path}")

    @property
    def agent(self) -> dict[str, Any]:
        return dict(self.identity.get("agent", {}))

    @property
    def operator(self) -> dict[str, Any]:
        return dict(self.identity.get("operator", {}))

    @property
    def required_env_names(self) -> tuple[str, ...]:
        return (
            str(self.agent.get("token_env", "")),
            str(self.operator.get("token_env", "")),
            str(self.operator.get("credential_env", "")),
            str(self.identity.get("approval_secret_env", "")),
            str(self.identity.get("jwks_file_env", "")),
        )


def static_check(config: HitlConfig) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    root = Path(__file__).resolve().parents[3]
    template_text = config.template_path.read_text(encoding="utf-8")
    template = yaml.safe_load(template_text) or {}
    xa = dict(template.get("xa_guard", {}))
    upstream = dict(xa.get("upstream", {}))
    identity_cfg = dict(xa.get("identity", {}))
    issuers = list(identity_cfg.get("issuers", []))
    gates = dict(xa.get("gates", {}))
    downstream = list(xa.get("downstream", []))
    parsed = urlparse(str(config.server.get("base_url", "")))

    _add(checks, "template_placeholders", TEMPLATE_PLACEHOLDERS == {p for p in TEMPLATE_PLACEHOLDERS if p in template_text}, "all runtime-only paths are placeholders")
    _add(checks, "transport", upstream.get("transport") == "streamable-http", "streamable-http required")
    _add(
        checks,
        "host_port",
        parsed.scheme == "http"
        and parsed.hostname == upstream.get("host") == "127.0.0.1"
        and parsed.port == int(upstream.get("port", 0)),
        "loopback base URL and template host/port must match",
    )
    paths = {
        str(config.server.get("agent_path", "")),
        str(config.server.get("operator_path", "")),
        str(config.server.get("health_path", "")),
    }
    _add(
        checks,
        "separate_endpoints",
        paths == {"/mcp", "/operator/mcp", "/healthz"},
        "Agent, Operator, and health endpoints are distinct",
    )
    _add(
        checks,
        "identity_required",
        identity_cfg.get("enabled") is True
        and identity_cfg.get("required") is True
        and config.identity.get("required_scope") in identity_cfg.get("required_scopes", []),
        "JWT identity is mandatory on both MCP planes",
    )
    issuer_ok = len(issuers) == 1 and isinstance(issuers[0], dict)
    if issuer_ok:
        issuer = dict(issuers[0])
        issuer_ok = (
            issuer.get("issuer") == config.identity.get("issuer")
            and issuer.get("audiences") == [config.identity.get("audience")]
            and issuer.get("algorithms") == [config.identity.get("algorithm")]
            and issuer.get("jwks_file") == "__XA_HITL_JWKS_FILE_YAML__"
        )
    _add(checks, "issuer_contract", issuer_ok, "issuer/audience/algorithm/JWKS placeholder are frozen")
    _add(
        checks,
        "separation_of_duty",
        bool(config.agent.get("human_principal"))
        and config.agent.get("human_principal") != config.operator.get("human_principal")
        and config.agent.get("agent_id") != config.operator.get("agent_id")
        and config.identity.get("operator_role") == "xa_guard.operator",
        "Alice and Dora use distinct human and agent identities",
    )
    command = downstream[0].get("command", []) if len(downstream) == 1 else []
    _add(
        checks,
        "counter_target",
        command == ["python", "-m", "demo.targets.http_hitl_target"]
        and (root / "demo/targets/http_hitl_target.py").is_file()
        and "XA_HITL_TARGET_LEDGER" in downstream[0].get("env_passthrough", []),
        "synthetic target has an execution-count ledger",
    )
    _add(
        checks,
        "gate_contract",
        dict(gates.get("gate2", {})).get("hitl_required_for") == ["red"]
        and dict(gates.get("gate3", {})).get("enabled") is True
        and dict(gates.get("gate4", {})).get("enabled") is True
        and dict(gates.get("gate5", {})).get("enabled") is False
        and dict(gates.get("gate6", {})).get("enabled") is True,
        "Gate2 HITL and Gate3/4/6 are enabled; Gate5 remains explicitly disabled",
    )
    policy_files = [
        root / "policies/baseline/gate2_tool_risks.yaml",
        root / "policies/baseline/gate4_capabilities.yaml",
    ]
    _add(
        checks,
        "pending_tool_registered",
        all(path.is_file() and "pending_approval_op" in path.read_text(encoding="utf-8") for path in policy_files),
        "pending_approval_op is registered red with a Gate4 capability",
    )
    env_names = config.required_env_names
    _add(
        checks,
        "secret_env_contract",
        all(env_names) and len(set(env_names)) == len(env_names),
        "five distinct environment names are frozen; no value is stored in the manifest",
    )
    required_contract = {
        "agent_operator_sessions_distinct",
        "agent_plane_operator_tools_absent",
        "require_exact_arguments_sha256",
        "require_same_trace_id",
        "require_nonempty_record_hash",
        "require_approval_token_digest_only",
        "require_target_execution_ledger",
        "require_replay_rejection",
        "require_secret_scan",
    }
    _add(
        checks,
        "evidence_contract",
        all(config.evidence_contract.get(name) is True for name in required_contract),
        "identity, exact-hash, single-execution, replay, audit, and secret checks are mandatory",
    )
    return _report(config, checks, credential_checks=[], missing_env=[])


def credential_preflight(config: HitlConfig) -> dict[str, Any]:
    static = static_check(config)
    checks = list(static["static_checks"])
    credential_checks: list[dict[str, Any]] = []
    missing = [name for name in config.required_env_names if not os.environ.get(name, "")]
    _add(
        credential_checks,
        "required_environment",
        not missing,
        "all required values are configured" if not missing else f"missing: {missing}",
    )
    if missing:
        return _report(config, checks, credential_checks=credential_checks, missing_env=missing)

    operator_secret = os.environ[str(config.operator["credential_env"])]
    approval_secret = os.environ[str(config.identity["approval_secret_env"])]
    _add(
        credential_checks,
        "independent_local_secrets",
        len(operator_secret) >= 32
        and len(approval_secret) >= 32
        and operator_secret != approval_secret,
        "operator credential and approval-signing secret are distinct and at least 32 characters",
    )

    jwks_path = Path(os.environ[str(config.identity["jwks_file_env"])]).resolve()
    jwks: dict[str, Any] = {}
    jwks_error = ""
    try:
        jwks = json.loads(jwks_path.read_text(encoding="utf-8"))
        keys = list(jwks.get("keys", []))
        if not keys:
            raise ValueError("JWKS contains no keys")
        if any(PRIVATE_JWK_FIELDS.intersection(item) for item in keys if isinstance(item, dict)):
            raise ValueError("JWKS contains private or symmetric key material")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        jwks_error = f"{type(exc).__name__}: {exc}"
    _add(
        credential_checks,
        "public_jwks",
        not jwks_error,
        "public JWKS loaded from configured path" if not jwks_error else jwks_error,
    )

    token_summaries: dict[str, Any] = {}
    if not jwks_error:
        agent_ok, agent_detail, agent_summary = _verify_token(
            os.environ[str(config.agent["token_env"])],
            config=config,
            expected=config.agent,
            require_operator_role=False,
            jwks=jwks,
        )
        operator_ok, operator_detail, operator_summary = _verify_token(
            os.environ[str(config.operator["token_env"])],
            config=config,
            expected=config.operator,
            require_operator_role=True,
            jwks=jwks,
        )
        _add(credential_checks, "agent_jwt", agent_ok, agent_detail)
        _add(credential_checks, "operator_jwt", operator_ok, operator_detail)
        token_summaries = {"agent": agent_summary, "operator": operator_summary}
        distinct = bool(
            agent_ok
            and operator_ok
            and agent_summary.get("human_principal") != operator_summary.get("human_principal")
            and agent_summary.get("agent_id") != operator_summary.get("agent_id")
            and agent_summary.get("jti_sha256") != operator_summary.get("jti_sha256")
            and agent_summary.get("tenant_id") == operator_summary.get("tenant_id")
        )
        _add(
            credential_checks,
            "live_separation_of_duty",
            distinct,
            "verified tokens bind distinct principals/agents/JTIs in the same tenant",
        )

    report = _report(config, checks, credential_checks=credential_checks, missing_env=[])
    report["credential_summaries"] = token_summaries
    report["jwks"] = {
        "configured": True,
        "public_only": not jwks_error,
        "sha256": hashlib.sha256(jwks_path.read_bytes()).hexdigest() if not jwks_error else "",
        "key_count": len(jwks.get("keys", [])) if not jwks_error else 0,
    }
    return report


def _verify_token(
    token: str,
    *,
    config: HitlConfig,
    expected: dict[str, Any],
    require_operator_role: bool,
    jwks: dict[str, Any],
) -> tuple[bool, str, dict[str, Any]]:
    summary: dict[str, Any] = {}
    try:
        import jwt

        header = jwt.get_unverified_header(token)
        kid = str(header.get("kid", ""))
        algorithm = str(header.get("alg", ""))
        keys = [item for item in jwks.get("keys", []) if str(item.get("kid", "")) == kid]
        if len(keys) != 1:
            raise ValueError("JWT kid is missing or ambiguous in JWKS")
        if algorithm != config.identity.get("algorithm"):
            raise ValueError("JWT algorithm does not match frozen manifest")
        key = jwt.PyJWK.from_dict(keys[0]).key
        claims = jwt.decode(
            token,
            key=key,
            algorithms=[algorithm],
            audience=str(config.identity["audience"]),
            issuer=str(config.identity["issuer"]),
            leeway=30,
            options={"require": ["exp", "iat", "sub", "iss", "jti"]},
        )
        actor = claims.get("act") if isinstance(claims.get("act"), dict) else {}
        agent_id = str(actor.get("sub") or claims.get("azp") or "")
        scopes = _strings(claims.get("scope") or claims.get("scopes"), split=True)
        roles = set(_strings(dict(claims.get("realm_access", {})).get("roles")))
        resources = claims.get("resource_access", {})
        if isinstance(resources, dict):
            for value in resources.values():
                if isinstance(value, dict):
                    roles.update(_strings(value.get("roles")))
        issued_at = int(claims["iat"])
        expires_at = int(claims["exp"])
        required_role = str(config.identity["operator_role"])
        if str(claims.get("sub", "")) != expected.get("human_principal"):
            raise ValueError("JWT human principal differs from frozen identity")
        if agent_id != expected.get("agent_id"):
            raise ValueError("JWT agent id differs from frozen identity")
        if str(claims.get("tenant_id", "")) != config.identity.get("tenant_id"):
            raise ValueError("JWT tenant differs from frozen tenant")
        if str(config.identity["required_scope"]) not in scopes:
            raise ValueError("JWT required scope is missing")
        if expires_at - issued_at > int(config.identity["max_token_ttl_seconds"]):
            raise ValueError("JWT lifetime exceeds frozen maximum")
        if require_operator_role and required_role not in roles:
            raise ValueError("Operator JWT lacks xa_guard.operator role")
        if not require_operator_role and required_role in roles:
            raise ValueError("Agent JWT must not carry the operator role")
        summary = {
            "human_principal": str(claims["sub"]),
            "agent_id": agent_id,
            "tenant_id": str(claims["tenant_id"]),
            "issuer": str(claims["iss"]),
            "kid": kid,
            "algorithm": algorithm,
            "scopes": sorted(scopes),
            "roles": sorted(roles),
            "jti_sha256": hashlib.sha256(str(claims["jti"]).encode("utf-8")).hexdigest(),
            "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "expires_in_seconds": max(0, expires_at - int(time.time())),
        }
        return True, "signature and frozen identity claims verified", summary
    except Exception as exc:  # PyJWT exposes several verification subclasses
        return False, f"{type(exc).__name__}: credential verification failed", summary


def _strings(value: Any, *, split: bool = False) -> tuple[str, ...]:
    if split and isinstance(value, str):
        value = value.split()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if str(item))
    return ()


def _add(checks: list[dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def _report(
    config: HitlConfig,
    static_checks: list[dict[str, Any]],
    *,
    credential_checks: list[dict[str, Any]],
    missing_env: list[str],
) -> dict[str, Any]:
    static_ready = bool(static_checks) and all(item["ok"] for item in static_checks)
    credentials_checked = bool(credential_checks)
    credential_ready = credentials_checked and all(item["ok"] for item in credential_checks)
    ready = static_ready and credential_ready
    if ready:
        preparation_status = "READY_FOR_AUTHENTICATED_LIVE_EXECUTION"
    elif static_ready and credentials_checked:
        preparation_status = "STATIC_READY_EXTERNAL_IDENTITY_INPUT_BLOCKED"
    elif static_ready:
        preparation_status = "STATIC_PREPARATION_READY"
    else:
        preparation_status = "STATIC_PREPARATION_FAILED"
    return {
        "schema_version": "xa-guard-http-operator-hitl-preflight/v1",
        "experiment_id": str(config.raw.get("experiment_id", "")),
        "preparation_status": preparation_status,
        "static_ready": static_ready,
        "credentials_checked": credentials_checked,
        "credential_ready": credential_ready,
        "ready_for_live_execution": ready,
        "live_executed": False,
        "live_result": "NOT_RUN",
        "manifest_sha256": sha256_json(config.raw),
        "config_template_sha256": hashlib.sha256(config.template_path.read_bytes()).hexdigest(),
        "case": {
            "case_id": str(config.case.get("case_id", "")),
            "tool_name": str(config.case.get("tool_name", "")),
            "arguments_sha256": sha256_json(config.case.get("arguments", {})),
            "expected_target_executions": int(config.case.get("expected_target_executions", 0)),
        },
        "endpoints": {
            "agent": str(config.server.get("base_url", "")) + str(config.server.get("agent_path", "")),
            "operator": str(config.server.get("base_url", "")) + str(config.server.get("operator_path", "")),
            "health": str(config.server.get("base_url", "")) + str(config.server.get("health_path", "")),
        },
        "required_environment_names": list(config.required_env_names),
        "missing_environment_names": list(missing_env),
        "static_checks": static_checks,
        "credential_checks": credential_checks,
        "claim_boundary": (
            "This report proves preparation only. It is not an HTTP request, pending approval, "
            "operator approval, downstream execution, replay rejection, or live PASS."
        ),
    }


def _write_report(path: str | None, report: dict[str, Any]) -> None:
    if not path:
        return
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Prepare independent HTTP Agent/Operator HITL live")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("static-check", "preflight"):
        command = sub.add_parser(name)
        command.add_argument("--manifest", required=True)
        command.add_argument("--env-file", default=".env")
        command.add_argument("--out")
    args = parser.parse_args(argv)

    config = HitlConfig.load(args.manifest)
    if args.command == "static-check":
        report = static_check(config)
        _write_report(args.out, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["static_ready"] else 1

    load_local_env(args.env_file)
    report = credential_preflight(config)
    _write_report(args.out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready_for_live_execution"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
