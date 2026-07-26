"""Targeted tests for the six-case attack proof set runner.

Only new tests live here; no existing test is modified.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from demo.targets.attack_proof_target import CALL_LOG_ENV, record_call
from scripts.run_attack_proof_set import (
    DEFAULT_MANIFEST,
    build_report,
    evaluate_oar_summary,
    load_manifest,
    main,
    select_cases,
    tamper_audit_copy,
)

EXPECTED_CASE_IDS = {
    "AP-D1-MAIL",
    "AP-D1-RAG",
    "AP-D2-EXEC",
    "AP-D3-SUPPLY",
    "AP-D4-AUDIT",
    "AP-ID-BOUNDARY",
}


def test_manifest_has_six_unique_cases() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST)
    ids = [case["case_id"] for case in manifest["cases"]]
    assert len(ids) == 6
    assert len(set(ids)) == 6
    assert set(ids) == EXPECTED_CASE_IDS


def test_manifest_rejects_bad_schema(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "schema_version: wrong/v9\ncases: []\n", encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_manifest(bad)


def test_manifest_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    dup = tmp_path / "dup.yaml"
    dup.write_text(
        "schema_version: xa-attack-proof-set/v1\n"
        "cases:\n"
        "  - case_id: AP-X-1\n"
        "    kind: k\n"
        "    oracle: {}\n"
        "  - case_id: AP-X-1\n"
        "    kind: k\n"
        "    oracle: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_manifest(dup)


def test_select_cases_rejects_unknown() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST)
    with pytest.raises(ValueError):
        select_cases(manifest, ["AP-NOPE-1"])
    assert [c["case_id"] for c in select_cases(manifest, [])] == [
        c["case_id"] for c in manifest["cases"]
    ]


def test_dry_run_creates_no_output_directory(tmp_path: Path) -> None:
    out = tmp_path / "runs"
    assert main(["--dry-run", "--output-root", str(out)]) == 0
    assert not out.exists()


def test_safe_target_records_without_executing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = tmp_path / "calls.jsonl"
    sentinel = tmp_path / "sentinel.txt"
    monkeypatch.setenv(CALL_LOG_ENV, str(log_path))
    entry = record_call(
        "exec_command",
        {
            "host": "web03",
            "cmd": f"touch {sentinel}",
            "proof_case_id": "TEST:null",
        },
    )
    assert entry["mode"] == "record_only_no_execution"
    assert entry["proof_case_id"] == "TEST:null"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    recorded = json.loads(lines[0])
    assert recorded["arguments_sha256"] == entry["arguments_sha256"]
    assert not sentinel.exists()


def test_oar_oracle_is_case_local() -> None:
    oracle = {
        "null_leak_count": 3,
        "protected_leak_count": 0,
        "protected_infra_error_count": 0,
    }
    summary = {
        "aggregate": {
            "run_count": 3,
            "null_leak_count": 3,
            "protected_leak_count": 0,
            "protected_infra_error_count": 0,
            "asr_null": 1.0,
            "asr_protected": 0.0,
            "protection_delta": 1.0,
        }
    }
    passed, observed = evaluate_oar_summary(summary, oracle)
    assert passed
    assert observed["asr_null"] == 1.0
    bad = {"aggregate": {**summary["aggregate"], "protected_leak_count": 1}}
    passed, _ = evaluate_oar_summary(bad, oracle)
    assert not passed


def _result(case_id: str, status: str, kind: str = "k", direction: str = "D"):
    return {
        "case_id": case_id,
        "direction": direction,
        "kind": kind,
        "status": status,
        "verified": status == "verified",
    }


def test_report_distinguishes_failed_and_infra_error() -> None:
    manifest = {"proof_set_id": "xa-attack-proof-set-v1"}
    results = [
        _result("A", "verified"),
        _result("B", "failed"),
        _result("C", "infra_error"),
    ]
    report = build_report("run-x", manifest, results)
    aggregate = report["aggregate"]
    assert aggregate["selected_case_count"] == 3
    assert aggregate["verified_case_count"] == 1
    assert aggregate["failed_case_count"] == 1
    assert aggregate["infra_error_count"] == 1
    assert report["result"] == "LIMIT"
    assert aggregate["heterogeneous_metrics_combined"] is False


def test_report_pass_only_when_all_verified() -> None:
    manifest = {"proof_set_id": "xa-attack-proof-set-v1"}
    results = [_result("A", "verified"), _result("B", "verified")]
    report = build_report("run-y", manifest, results)
    assert report["result"] == "PASS"
    assert report["aggregate"]["verified_case_count"] == 2


def test_tamper_copy_leaves_original_untouched(tmp_path: Path) -> None:
    first = {"gen_ai.user.role": "user", "record_hash": "a" * 64}
    second = {"gen_ai.user.role": "ops", "record_hash": "b" * 64}
    source = tmp_path / "audit.jsonl"
    source.write_text(
        json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8"
    )
    original_bytes = source.read_bytes()
    dest = tmp_path / "tampered.jsonl"
    tamper_audit_copy(source, dest)
    assert source.read_bytes() == original_bytes
    lines = dest.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["gen_ai.user.role"] != "user"
    assert json.loads(lines[0])["record_hash"] == first["record_hash"]
    assert lines[1] == json.dumps(second)
