#!/usr/bin/env python3
"""Generate local synthetic credentials for HTTP Operator HITL preflight/live.

Creates a gitignored RSA keypair + public JWKS, issues short-lived Alice/Dora
JWTs matching scenarios/live-agent/http-operator-hitl-v1.json, and upserts the
five required names into the repo-root .env without printing secret values.

These identities are theater roles for the frozen demo contract. They are not
real company accounts and must never be committed.
"""

from __future__ import annotations

import argparse
import secrets
import sys
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm
import jwt

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IDENTITY_DIR = ROOT / "open-agent-range" / ".runtime" / "http-operator-hitl" / "identity"
DEFAULT_ENV = ROOT / ".env"

ISSUER = "https://xa-guard.local/http-hitl"
AUDIENCE = "urn:xa-guard:http-hitl"
TENANT = "acme-corp"
SCOPE = "xa.invoke"
KID = "xa-hitl-synth-20260804"
TTL_SECONDS = 300

ALICE = {
    "sub": "alice.requester@acme.local",
    "act": {"sub": "synthetic-change-agent"},
    "tools": ["pending_approval_op"],
}
DORA = {
    "sub": "dora.approver@acme.local",
    "act": {"sub": "independent-operator-console"},
    "realm_access": {"roles": ["xa_guard.operator"]},
}

ENV_KEYS = (
    "XA_HITL_JWKS_FILE",
    "XA_HITL_AGENT_BEARER_TOKEN",
    "XA_HITL_OPERATOR_BEARER_TOKEN",
    "XA_GUARD_APPROVAL_OPERATOR_TOKEN",
    "XA_GUARD_APPROVAL_SECRET",
)


def _ensure_keypair(identity_dir: Path) -> tuple[Path, Path, Path]:
    identity_dir.mkdir(parents=True, exist_ok=True)
    private_path = identity_dir / "private.pem"
    public_path = identity_dir / "public.pem"
    jwks_path = identity_dir / "jwks-public.json"

    if not private_path.is_file():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        public_path.write_bytes(
            key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

    private_pem = private_path.read_bytes()
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    jwk = json_jwk_from_private(private_key)
    jwks_path.write_text(__import__("json").dumps({"keys": [jwk]}, indent=2) + "\n", encoding="utf-8")
    return private_path, public_path, jwks_path


def json_jwk_from_private(private_key) -> dict:
    # Use PyJWT helper so encoding matches what preflight verifies.
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    # Defense: never persist private material into JWKS.
    for banned in ("d", "p", "q", "dp", "dq", "qi", "oth", "k"):
        jwk.pop(banned, None)
    assert "n" in jwk and "e" in jwk
    return jwk


def _issue(private_pem: bytes, claims: dict) -> str:
    now = int(time.time())
    payload = {
        **claims,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "tenant_id": TENANT,
        "scope": SCOPE,
        "iat": now,
        "exp": now + TTL_SECONDS,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": KID, "alg": "RS256"})


def _read_env(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _upsert_env(path: Path, updates: dict[str, str]) -> None:
    lines = _read_env(path)
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    if seen != set(updates):
        if out and out[-1].strip():
            out.append("")
        out.append("# Synthetic HTTP Operator HITL credentials (local demo only; do not commit)")
        for key, value in updates.items():
            if key not in seen:
                out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _load_or_create_secret(identity_dir: Path, name: str) -> str:
    path = identity_dir / f"{name}.txt"
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if len(value) >= 32:
            return value
    value = secrets.token_urlsafe(48)
    path.write_text(value + "\n", encoding="utf-8")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-dir", type=Path, default=DEFAULT_IDENTITY_DIR)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument(
        "--rotate-secrets",
        action="store_true",
        help="Replace operator/approval secrets instead of reusing stored ones",
    )
    args = parser.parse_args()

    private_path, _public_path, jwks_path = _ensure_keypair(args.identity_dir)
    private_pem = private_path.read_bytes()

    if args.rotate_secrets:
        for name in ("operator-token", "approval-secret"):
            target = args.identity_dir / f"{name}.txt"
            if target.exists():
                target.unlink()

    operator_token = _load_or_create_secret(args.identity_dir, "operator-token")
    approval_secret = _load_or_create_secret(args.identity_dir, "approval-secret")
    if operator_token == approval_secret:
        print("ERROR: operator and approval secrets collided; re-run with --rotate-secrets", file=sys.stderr)
        return 2

    agent_jwt = _issue(private_pem, ALICE)
    operator_jwt = _issue(private_pem, DORA)

    updates = {
        "XA_HITL_JWKS_FILE": str(jwks_path.resolve()),
        "XA_HITL_AGENT_BEARER_TOKEN": agent_jwt,
        "XA_HITL_OPERATOR_BEARER_TOKEN": operator_jwt,
        "XA_GUARD_APPROVAL_OPERATOR_TOKEN": operator_token,
        "XA_GUARD_APPROVAL_SECRET": approval_secret,
    }
    _upsert_env(args.env_file, updates)

    # Sanity: JWKS must verify without exposing values.
    jwks = __import__("json").loads(jwks_path.read_text(encoding="utf-8"))
    assert all(set(k).isdisjoint({"d", "p", "q", "dp", "dq", "qi", "oth", "k"}) for k in jwks["keys"])
    key = PyJWK.from_dict(jwks["keys"][0]).key
    for token, expect_sub in (
        (agent_jwt, ALICE["sub"]),
        (operator_jwt, DORA["sub"]),
    ):
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "iss", "jti"]},
        )
        assert claims["sub"] == expect_sub

    print("OK: synthetic HTTP HITL credentials written")
    print(f"  env_file={args.env_file}")
    print(f"  jwks_file={jwks_path}")
    print(f"  private_key={private_path} (gitignored; never commit)")
    print(f"  jwt_ttl_seconds={TTL_SECONDS}")
    print("  updated_keys=" + ",".join(ENV_KEYS))
    print("NOTE: JWT expires in <=5 minutes; re-run this script before preflight/live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
