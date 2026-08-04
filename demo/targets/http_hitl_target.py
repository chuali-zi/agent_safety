"""Synthetic counter target for the independent HTTP Operator HITL live.

The target performs no real administration.  Its single tool appends one
secret-free execution fact to a runner-selected JSONL ledger so the later live
evidence can prove: pending caused zero executions, approval caused exactly
one, and replay caused no second execution.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

_LEDGER_ENV = "XA_HITL_TARGET_LEDGER"
app = Server("xa-guard-http-hitl-target", version="0.1.0")


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="pending_approval_op",
            description=(
                "Synthetic red operation for independent HTTP HITL evidence; "
                "records one local execution fact and performs no real administration."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {"type": "string"},
                    "change_ticket": {"type": "string"},
                },
                "required": ["operation", "change_ticket"],
                "additionalProperties": False,
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name != "pending_approval_op":
        payload = {"ok": False, "error": "unknown tool"}
    else:
        ledger_value = os.environ.get(_LEDGER_ENV, "")
        if not ledger_value:
            raise RuntimeError(f"{_LEDGER_ENV} must be configured by the live harness")
        ledger = Path(ledger_value).resolve()
        ledger.parent.mkdir(parents=True, exist_ok=True)
        fact = {
            "schema_version": "xa-guard-http-hitl-target-execution/v1",
            "execution_id": uuid4().hex,
            "tool_name": name,
            "arguments_sha256": _canonical_sha256(arguments),
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "simulated": True,
        }
        with ledger.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(fact, ensure_ascii=False, sort_keys=True) + "\n")
        payload = {
            "ok": True,
            "executed": True,
            "simulated": True,
            "execution_id": fact["execution_id"],
            "arguments_sha256": fact["arguments_sha256"],
        }
    return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, sort_keys=True))]


async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
