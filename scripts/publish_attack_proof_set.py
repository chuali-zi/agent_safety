"""Publish a redacted, independently checked attack-proof evidence subset."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ABSOLUTE_WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:[\\/]")
SENSITIVE_TEXT = re.compile(
    r"(?i)(bearer\s+[a-z0-9._~+/-]+|\"(?:password|token|api_key|secret)\"\s*:)"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sanitize(value: Any, replacements: list[tuple[str, str]]) -> Any:
    if isinstance(value, dict):
        return {key: sanitize(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item, replacements) for item in value]
    if isinstance(value, str):
        cleaned = value
        for source, replacement in replacements:
            cleaned = cleaned.replace(source, replacement)
            cleaned = cleaned.replace(source.replace("\\", "/"), replacement)
        return cleaned
    return value


def verify_hash_manifest(run_dir: Path, manifest: dict[str, Any]) -> dict[str, int]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("artifact-hashes.json files must be an object")
    for relative, expected in files.items():
        path = run_dir / Path(relative)
        if not path.is_file():
            raise ValueError(f"hash manifest file missing: {relative}")
        if not isinstance(expected, dict):
            raise ValueError(f"invalid hash manifest row: {relative}")
        if sha256_file(path) != expected.get("sha256"):
            raise ValueError(f"hash mismatch: {relative}")
        if path.stat().st_size != expected.get("bytes"):
            raise ValueError(f"byte count mismatch: {relative}")
    physical_files = [path for path in run_dir.rglob("*") if path.is_file()]
    if len(files) != len(physical_files) - 1:
        raise ValueError(
            "root hash manifest must cover every file except itself: "
            f"{len(files)} != {len(physical_files) - 1}"
        )
    child_manifests = sum(
        relative.endswith("/artifact-hashes.json") for relative in files
    )
    return {
        "hash_entries": len(files),
        "physical_files": len(physical_files),
        "child_hash_manifests": child_manifests,
    }


def publish(run_dir: Path, provenance_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite public evidence: {output_dir}")
    report = read_json(run_dir / "attack-proof-report.json")
    hashes = read_json(run_dir / "artifact-hashes.json")
    source = read_json(run_dir / "source-provenance.json")
    meta = read_json(run_dir / "meta.json")
    provenance = read_json(provenance_path)
    if report.get("run_id") != provenance.get("run_id"):
        raise ValueError("report/provenance run_id mismatch")
    if report.get("result") != "PASS" or provenance.get("result") != "PASS":
        raise ValueError("only a PASS proof set may be published")
    if meta.get("git", {}).get("dirty") or meta.get("git", {}).get("end_dirty"):
        raise ValueError("public proof provenance must be clean at start and end")
    hash_stats = verify_hash_manifest(run_dir, hashes)
    if sha256_file(run_dir / "artifact-hashes.json") != provenance.get(
        "artifact_manifest_sha256"
    ):
        raise ValueError("artifact manifest/provenance mismatch")
    if sha256_file(run_dir / "source-provenance.json") != provenance.get(
        "source_provenance_sha256"
    ):
        raise ValueError("source provenance hash mismatch")
    tarball = provenance_path.with_name(f"{provenance['run_id']}.tar.gz")
    if sha256_file(tarball) != provenance.get("tarball_sha256"):
        raise ValueError("tarball/provenance mismatch")

    replacements = sorted(
        [
            (str(run_dir.resolve()), "<run>"),
            (str(REPO_ROOT.resolve()), "<repo>"),
        ],
        key=lambda item: len(item[0]),
        reverse=True,
    )
    output_dir.mkdir(parents=True)
    write_json(output_dir / "attack-proof-report.json", sanitize(report, replacements))
    write_json(output_dir / "artifact-hashes.json", sanitize(hashes, replacements))
    write_json(output_dir / "source-provenance.json", sanitize(source, replacements))
    write_json(output_dir / "provenance.json", provenance)

    replay_commands = sum(
        "kernel.range_cli replay" in line
        for line in (run_dir / "commands.txt").read_text(encoding="utf-8").splitlines()
    )
    summary = {
        "schema_version": "xa-attack-proof-public-verification/v1",
        "run_id": report["run_id"],
        "result": report["result"],
        "verified_case_count": report["aggregate"]["verified_case_count"],
        "failed_case_count": report["aggregate"]["failed_case_count"],
        "infra_error_count": report["aggregate"]["infra_error_count"],
        "git_head": provenance["git_head"],
        "git_tree": provenance["git_tree"],
        "git_dirty_start": provenance["git_dirty"],
        "git_dirty_end": provenance["git_end_dirty"],
        "tarball_sha256": provenance["tarball_sha256"],
        "artifact_manifest_sha256": provenance["artifact_manifest_sha256"],
        "source_provenance_sha256": provenance["source_provenance_sha256"],
        "protected_replay_command_count": replay_commands,
        **hash_stats,
    }
    write_json(output_dir / "verification-summary.json", summary)
    (output_dir / "repro-commands.txt").write_text(
        "# Run only from a clean checkout of the git_head in provenance.json.\n"
        "python -m pytest -q -p no:cacheprovider tests/unit/test_attack_proof_set.py\n"
        "python scripts/run_attack_proof_set.py --dry-run --require-clean\n"
        "python scripts/run_attack_proof_set.py --live --repeat 10 --require-clean "
        "--reuse-identity-evidence\n",
        encoding="utf-8",
        newline="\n",
    )
    for path in output_dir.iterdir():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if ABSOLUTE_WINDOWS_PATH.search(text):
            raise ValueError(f"absolute path remained in public output: {path.name}")
        if SENSITIVE_TEXT.search(text):
            raise ValueError(f"credential-shaped text remained: {path.name}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    summary = publish(args.run_dir, args.provenance, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
