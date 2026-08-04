"""Versioned provenance and schema-aware business-reference resolution.

The proxy deliberately keeps this module independent from any particular RAG,
document store, or Open Agent Range world.  A trusted transport adapter owns
the resolver implementation; Gate4 only consumes its small, auditable result.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from xa_guard.types import TaintLabel


PROVENANCE_SCHEMA_VERSION = "1.0"
MAX_PROVENANCE_TTL_SECONDS = 900
PROVENANCE_CLOCK_SKEW_SECONDS = 30


def canonical_sha256(value: Any) -> str:
    """Hash structured data deterministically without retaining its content."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class TrustState(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    UNKNOWN = "unknown"


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    UNKNOWN = "unknown"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class ProvenanceSource:
    source_id: str
    kind: str
    locator_digest: str
    content_digest: str
    trust_state: TrustState = TrustState.UNKNOWN
    taint: TaintLabel = TaintLabel.PUBLIC

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProvenanceSource":
        required = ("source_id", "kind", "locator_digest", "content_digest")
        missing = [key for key in required if not str(value.get(key, ""))]
        if missing:
            raise ValueError(f"provenance source missing: {', '.join(missing)}")
        return cls(
            source_id=str(value["source_id"]), kind=str(value["kind"]),
            locator_digest=str(value["locator_digest"]), content_digest=str(value["content_digest"]),
            trust_state=TrustState(str(value.get("trust_state", TrustState.UNKNOWN.value))),
            taint=TaintLabel(str(value.get("taint", TaintLabel.PUBLIC.value))),
        )


@dataclass(frozen=True)
class ResolvedReference:
    reference_id: str
    status: ResolutionStatus
    classification: TaintLabel = TaintLabel.PUBLIC
    taint: TaintLabel = TaintLabel.PUBLIC
    asset_digest: str = ""
    resolver_id: str = ""
    reason: str = ""

    def audit_summary(self) -> dict[str, str]:
        """Safe metadata for Gate results/audit; never includes the asset body."""
        return {
            "reference_id": self.reference_id,
            "status": self.status.value,
            "classification": self.classification.value,
            "taint": self.taint.value,
            "asset_digest": self.asset_digest,
            "resolver_id": self.resolver_id,
        }


@dataclass(frozen=True)
class ReferenceResolutionContext:
    tool_name: str
    tenant_id: str = ""
    session_id: str = ""
    task_id: str = ""
    human_principal: str = ""
    agent_id: str = ""


class ReferenceResolver(Protocol):
    """Adapter boundary for business assets named in tool arguments."""

    def resolve(self, reference_id: str, context: ReferenceResolutionContext) -> ResolvedReference:
        """Return resolved, unknown, or forbidden; never return raw asset content."""


@dataclass(frozen=True)
class MappingReferenceResolver:
    """Small deterministic resolver useful for adapters and unit tests."""

    references: Mapping[str, ResolvedReference]
    resolver_id: str = "mapping"

    def resolve(self, reference_id: str, context: ReferenceResolutionContext) -> ResolvedReference:
        result = self.references.get(reference_id)
        if result is not None:
            return result
        return ResolvedReference(
            reference_id=reference_id, status=ResolutionStatus.UNKNOWN,
            resolver_id=self.resolver_id, reason="reference is not known to this resolver",
        )


@dataclass(frozen=True)
class ReferenceFieldSpec:
    """Schema declaration for arguments that contain business asset references."""

    name: str
    fields: tuple[str, ...]


DEFAULT_REFERENCE_SCHEMAS: tuple[ReferenceFieldSpec, ...] = (
    ReferenceFieldSpec("sources", ("sources",)),
    ReferenceFieldSpec("attachments", ("attachments",)),
    ReferenceFieldSpec("records", ("records",)),
)


def extract_reference_ids(arguments: Mapping[str, Any], schemas: Sequence[ReferenceFieldSpec] = DEFAULT_REFERENCE_SCHEMAS) -> list[str]:
    """Extract only declared reference fields; arbitrary strings are not treated as IDs."""
    result: list[str] = []
    for schema in schemas:
        for field_name in schema.fields:
            raw = arguments.get(field_name)
            values = raw if isinstance(raw, (list, tuple)) else [raw]
            for item in values:
                if isinstance(item, str) and item:
                    result.append(item)
                elif isinstance(item, Mapping):
                    identifier = item.get("reference_id", item.get("id"))
                    if isinstance(identifier, str) and identifier:
                        result.append(identifier)
    return list(dict.fromkeys(result))


@dataclass(frozen=True)
class TrustedContextEnvelope:
    """Versioned, binding-ready provenance metadata supplied by a trusted adapter.

    This type validates structure and context binding.  Signature/MAC verification
    is intentionally an adapter responsibility: setting this object alone is not a
    trust upgrade.
    """

    schema_version: str
    session_id: str
    turn_id: str
    task_id: str
    human_principal: str
    agent_id: str
    tenant_id: str
    history_digest: str
    sources: tuple[ProvenanceSource, ...] = ()
    resolved_references: tuple[ResolvedReference, ...] = ()
    policy_bundle_sha: str = ""
    issued_at: str = ""
    expires_at: str = ""
    nonce: str = ""
    tool_name: str = ""
    arguments_sha256: str = ""
    key_id: str = ""
    signature: str = ""

    def unsigned_payload(self) -> dict[str, Any]:
        """Canonical signing payload.  Signatures never sign themselves."""
        return {
            "schema_version": self.schema_version, "session_id": self.session_id,
            "turn_id": self.turn_id, "task_id": self.task_id,
            "human_principal": self.human_principal, "agent_id": self.agent_id,
            "tenant_id": self.tenant_id, "history_digest": self.history_digest,
            "sources": [
                {"source_id": s.source_id, "kind": s.kind, "locator_digest": s.locator_digest,
                 "content_digest": s.content_digest, "trust_state": s.trust_state.value, "taint": s.taint.value}
                for s in self.sources
            ],
            "resolved_references": [
                {"reference_id": r.reference_id, "resolution_status": r.status.value,
                 "classification": r.classification.value, "taint": r.taint.value,
                 "asset_digest": r.asset_digest, "resolver_id": r.resolver_id, "reason": r.reason}
                for r in self.resolved_references
            ],
            "policy_bundle_sha": self.policy_bundle_sha, "issued_at": self.issued_at,
            "expires_at": self.expires_at, "nonce": self.nonce, "tool_name": self.tool_name,
            "arguments_sha256": self.arguments_sha256, "key_id": self.key_id,
        }

    def sign(self, key: bytes) -> "TrustedContextEnvelope":
        """Return a signed copy; only a trusted adapter should call this."""
        if not self.key_id:
            raise ValueError("provenance envelope signing requires key_id")
        signature = hmac.new(key, canonical_sha256(self.unsigned_payload()).encode("ascii"), hashlib.sha256).hexdigest()
        return dataclass_replace(self, signature=signature)

    def verify_signature(self, keys: Mapping[str, bytes]) -> bool:
        """Verify authenticity in constant time; false is never a trust upgrade."""
        key = keys.get(self.key_id)
        if not key or not self.signature:
            return False
        expected = hmac.new(key, canonical_sha256(self.unsigned_payload()).encode("ascii"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)

    def verify_for_context(
        self, keys: Mapping[str, bytes], *, tool_name: str, arguments: Mapping[str, Any], now: datetime | None = None,
    ) -> bool:
        """Single fail-closed adapter check for structure, binding, expiry and MAC."""
        try:
            self.validate(tool_name=tool_name, arguments=arguments, now=now)
        except ValueError:
            return False
        return self.verify_signature(keys)

    def validate(self, *, tool_name: str, arguments: Mapping[str, Any], now: datetime | None = None) -> None:
        if self.schema_version != PROVENANCE_SCHEMA_VERSION:
            raise ValueError("unsupported provenance schema version")
        if not self.session_id or not self.turn_id or not self.nonce:
            raise ValueError("provenance envelope requires session_id, turn_id, and nonce")
        if self.tool_name and self.tool_name != tool_name:
            raise ValueError("provenance envelope tool binding mismatch")
        if self.arguments_sha256 and self.arguments_sha256 != canonical_sha256(arguments):
            raise ValueError("provenance envelope arguments binding mismatch")
        current = now or datetime.now(timezone.utc)
        issued = datetime.fromisoformat(self.issued_at.replace("Z", "+00:00"))
        expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        if issued.tzinfo is None:
            raise ValueError("provenance issued_at must include timezone")
        if expiry.tzinfo is None:
            raise ValueError("provenance expiry must include timezone")
        if current >= expiry:
            raise ValueError("provenance envelope expired")
        if issued > current + timedelta(seconds=PROVENANCE_CLOCK_SKEW_SECONDS):
            raise ValueError("provenance envelope issued in the future")
        if expiry <= issued:
            raise ValueError("provenance expiry must be after issued_at")
        if (expiry - issued).total_seconds() > MAX_PROVENANCE_TTL_SECONDS:
            raise ValueError("provenance envelope lifetime exceeds maximum")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TrustedContextEnvelope":
        required = ("schema_version", "session_id", "turn_id", "task_id", "human_principal", "agent_id", "tenant_id", "history_digest", "issued_at", "expires_at", "nonce")
        missing = [key for key in required if not str(value.get(key, ""))]
        if missing:
            raise ValueError(f"provenance envelope missing: {', '.join(missing)}")
        refs: list[ResolvedReference] = []
        for item in value.get("resolved_references", []) or []:
            if not isinstance(item, Mapping) or not str(item.get("reference_id", "")):
                raise ValueError("invalid resolved reference")
            refs.append(ResolvedReference(
                reference_id=str(item["reference_id"]),
                status=ResolutionStatus(str(item.get("resolution_status", item.get("status", "unknown")))),
                classification=TaintLabel(str(item.get("classification", "PUBLIC"))),
                taint=TaintLabel(str(item.get("taint", "PUBLIC"))),
                asset_digest=str(item.get("asset_digest", "")), resolver_id=str(item.get("resolver_id", "")),
                reason=str(item.get("reason", "")),
            ))
        return cls(
            schema_version=str(value["schema_version"]), session_id=str(value["session_id"]),
            turn_id=str(value["turn_id"]), task_id=str(value["task_id"]),
            human_principal=str(value["human_principal"]), agent_id=str(value["agent_id"]),
            tenant_id=str(value["tenant_id"]), history_digest=str(value["history_digest"]),
            sources=tuple(ProvenanceSource.from_dict(item) for item in value.get("sources", []) or []),
            resolved_references=tuple(refs), policy_bundle_sha=str(value.get("policy_bundle_sha", "")),
            issued_at=str(value["issued_at"]), expires_at=str(value["expires_at"]), nonce=str(value["nonce"]),
            tool_name=str(value.get("tool_name", "")), arguments_sha256=str(value.get("arguments_sha256", "")),
            key_id=str(value.get("key_id", "")), signature=str(value.get("signature", "")),
        )


def dataclass_replace(envelope: TrustedContextEnvelope, **changes: Any) -> TrustedContextEnvelope:
    """Local helper avoids exposing mutation on the immutable envelope."""
    from dataclasses import replace
    return replace(envelope, **changes)
