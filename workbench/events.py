"""Workbench 事件构建与 schema 校验。

事件契约：docs/demo-handoff/schemas/live-workbench-event.schema.json。
所有发出的事件必须先通过 jsonschema 校验，校验失败直接抛错（宁可 run 失败也不发不合规事件）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
EVENT_SCHEMA_PATH = (
    REPO_ROOT / "docs" / "demo-handoff" / "schemas" / "live-workbench-event.schema.json"
)

SCHEMA_VERSION = "xa-guard-live-workbench-event/v1"
RUN_MODES = ("LIVE_RUN", "SEALED_REPLAY", "EXAMPLE_SYNTHETIC")

_validator = None


def _get_validator():
    global _validator
    if _validator is None:
        import jsonschema

        schema = json.loads(EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
        _validator = jsonschema.Draft202012Validator(schema)
    return _validator


def validate_event(event: dict[str, Any]) -> None:
    """按事件 schema 校验；不合规抛 jsonschema.ValidationError。"""
    _get_validator().validate(event)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_file(path: Path | str) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def sha256_canonical(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


class EventBuilder:
    """为单个 run 顺序构建并校验事件。"""

    def __init__(self, run_id: str, run_mode: str) -> None:
        if run_mode not in RUN_MODES:
            raise ValueError(f"invalid run_mode: {run_mode}")
        self.run_id = run_id
        self.run_mode = run_mode
        self._sequence = 0

    def emit(
        self,
        event_type: str,
        state: str,
        *,
        branch: str | None = None,
        message: str | None = None,
        artifact_refs: list[dict[str, Any]] | None = None,
        intent: dict[str, Any] | None = None,
        gate: dict[str, Any] | None = None,
        branch_result: dict[str, Any] | None = None,
        verification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._sequence += 1
        event: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "sequence": self._sequence,
            "timestamp": now_iso(),
            "event_type": event_type,
            "run_mode": self.run_mode,
            "state": state,
        }
        if branch is not None:
            event["branch"] = branch
        if message:
            event["message"] = message[:500]
        if artifact_refs:
            event["artifact_refs"] = artifact_refs
        if intent is not None:
            event["intent"] = intent
        if gate is not None:
            event["gate"] = gate
        if branch_result is not None:
            event["branch_result"] = branch_result
        if verification is not None:
            event["verification"] = verification
        validate_event(event)
        return event


def artifact_ref(name: str, json_pointer: str, path: Path | str) -> dict[str, Any]:
    """从真实文件构建 artifact 引用（sha256 直接来自文件字节）。"""
    return {"name": name, "json_pointer": json_pointer, "sha256": sha256_file(path)}
