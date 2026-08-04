from __future__ import annotations

import pytest

from xa_guard.approval import issue_approval, verify_approval
from xa_guard.config import GateConfig
from xa_guard.gates.base import Gate
from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.policy.layered import LayeredPolicySource, set_global_source
from xa_guard.types import Decision, GateContext


class _FailingGate(Gate):
    name = "failing_gate"

    def evaluate(self, ctx, stage=None):
        raise RuntimeError("injected")


def _binding() -> dict[str, str]:
    return {
        "request_identity": "human:alice",
        "tenant_id": "tenant-a",
        "provenance_digest": "provenance-v1",
        "history_digest": "history-v1",
        "taint": "INTERNAL",
        "policy_bundle_sha": "policy-v1",
        "effect_class": "external_write",
    }


def test_approval_requires_all_signed_governance_bindings():
    binding = _binding()
    approval = issue_approval(
        trace_id="trace", tool_name="send_email", arguments={"to": "a@example.test"},
        approver="dora", **binding,
    )
    assert approval.nonce
    assert verify_approval(
        approval, trace_id="trace", tool_name="send_email",
        arguments={"to": "a@example.test"}, **binding,
    ) == (True, "ok")
    changed = dict(binding)
    changed["tenant_id"] = "tenant-b"
    assert verify_approval(
        approval, trace_id="trace", tool_name="send_email",
        arguments={"to": "a@example.test"}, **changed,
    ) == (False, "tenant_id_mismatch")
    # Omitting a binding during resume is also a mismatch, never a downgrade.
    assert verify_approval(
        approval, trace_id="trace", tool_name="send_email",
        arguments={"to": "a@example.test"},
    ) == (False, "request_identity_mismatch")


def test_gate_error_policy_is_fail_closed_for_writes():
    gate = _FailingGate()
    assert gate(GateContext(effect_class="read_only")).decision == Decision.WARN
    assert gate(GateContext(effect_class="local_write")).decision == Decision.REQUIRE_APPROVAL
    external = gate(GateContext(effect_class="external_write"))
    assert external.decision == Decision.DENY
    assert external.metadata == {
        "degraded": True, "error_policy": "external_write", "effect_class": "external_write",
    }
    assert gate(GateContext(effect_class="privileged_execute")).decision == Decision.DENY
    # GateContext's side_effect_level defaults to "none" and is not proof of
    # a read-only operation. Unknown tools must therefore require approval.
    assert gate(GateContext(tool_name="unregistered_tool")).decision == Decision.REQUIRE_APPROVAL
    assert gate(GateContext(tool_name="send_email")).decision == Decision.DENY
    assert gate(GateContext(tool_name="exec_command")).decision == Decision.DENY
    assert gate(GateContext(tool_name="get_cpu")).decision == Decision.WARN


def test_gate_error_configuration_cannot_downgrade_write_fail_closed_floor():
    gate = _FailingGate(
        GateConfig(
            options={
                "error_decision_read_only": "allow",
                "error_decision_local_write": "allow",
                "error_decision_external_write": "allow",
                "error_decision_privileged_execute": "warn",
            }
        )
    )

    assert gate(GateContext(effect_class="read_only")).decision == Decision.WARN
    assert (
        gate(GateContext(effect_class="local_write")).decision
        == Decision.REQUIRE_APPROVAL
    )
    assert (
        gate(GateContext(effect_class="external_write")).decision
        == Decision.DENY
    )
    assert (
        gate(GateContext(effect_class="privileged_execute")).decision
        == Decision.DENY
    )


class _CrashingDetector:
    name = "crashing-detector"

    def detect(self, _inp, _ctx):
        raise RuntimeError("injected detector failure")


def test_gate1_unexpected_detector_crash_uses_effect_error_matrix(monkeypatch):
    gate = Gate1Input()
    monkeypatch.setattr(gate, "_build_detectors", lambda: [_CrashingDetector()])

    assert (
        gate(GateContext(tool_name="send_message", effect_class="external_write")).decision
        == Decision.DENY
    )


def test_approval_ttl_is_bounded():
    with pytest.raises(ValueError, match="ttl_seconds"):
        issue_approval(
            trace_id="trace",
            tool_name="send_message",
            arguments={},
            approver="dora",
            ttl_seconds=901,
        )


def _write_overlay(root, tenant, rule_id, marker):
    directory = root / tenant
    directory.mkdir(parents=True)
    (directory / "policy.yaml").write_text(
        f'''rules:\n  - id: "tenant::{tenant}::{rule_id}"\n    name: {rule_id}\n    source: test\n    triggers: [post_url]\n    predicate: "contains('url', '{marker}')"\n    enforce: deny\n''',
        encoding="utf-8",
    )


def test_tenant_effective_views_are_isolated(tmp_path):
    root = tmp_path / "overlay"
    _write_overlay(root, "a", "A-DENY", "a.invalid")
    _write_overlay(root, "b", "B-DENY", "b.invalid")
    project_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    source = LayeredPolicySource(
        manifest_path="policies/baseline/manifest.yaml", overlay_root=root, project_root=project_root,
    )
    rules_a = {rule.id for rule in source.get_policy_rules("a")}
    rules_b = {rule.id for rule in source.get_policy_rules("b")}
    baseline = {rule.id for rule in source.get_policy_rules("")}
    assert "tenant::a::A-DENY" in rules_a and "tenant::b::B-DENY" not in rules_a
    assert "tenant::b::B-DENY" in rules_b and "tenant::a::A-DENY" not in rules_b
    assert "tenant::a::A-DENY" not in baseline and "tenant::b::B-DENY" not in baseline
    assert source.effective_bundle_sha("a") != source.effective_bundle_sha("b")


def test_gate3_uses_the_context_tenant_effective_view(tmp_path):
    root = tmp_path / "overlay"
    _write_overlay(root, "a", "A-DENY", "a.invalid")
    source = LayeredPolicySource(
        manifest_path="policies/baseline/manifest.yaml", overlay_root=root,
        project_root=__import__("pathlib").Path(__file__).resolve().parents[2],
    )
    set_global_source(source)
    try:
        gate = Gate3Policy(GateConfig(options={"prefer_layered": True}))
        assert gate(GateContext(tool_name="post_url", arguments={"url": "https://a.invalid"}, tenant_id="a")).decision == Decision.DENY
        assert gate(GateContext(tool_name="post_url", arguments={"url": "https://a.invalid"}, tenant_id="b")).decision == Decision.ALLOW
    finally:
        set_global_source(None)
