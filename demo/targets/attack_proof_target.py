"""Safe synthetic MCP target used only by the attack proof set.

The target never executes a command, installs a plugin, or opens a network
connection. Each call only appends a redacted JSON record.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mcp.types as mtypes
from mcp.server import Server
from mcp.server.stdio import stdio_server

CALL_LOG_ENV = "XA_ATTACK_PROOF_CALL_LOG"


def _argument_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "argument_keys": sorted(str(key) for key in arguments),
        "arguments_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "proof_case_id": str(arguments.get("proof_case_id", "")),
        "name": str(arguments.get("name", "")),
        "host": str(arguments.get("host", "")),
    }


def record_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Record one call without executing any argument."""
    log_value = os.environ.get(CALL_LOG_ENV, "").strip()
    if not log_value:
        raise RuntimeError(f"{CALL_LOG_ENV} is required")
    log_path = Path(log_value)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": name,
        "mode": "record_only_no_execution",
        **_argument_summary(arguments),
    }
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
    return entry


def _build_app() -> Server:
    app: Server = Server("xa-attack-proof-target")

    @app.list_tools()
    async def _list_tools() -> list[mtypes.Tool]:
        obj = {"type": "object", "properties": {}, "additionalProperties": True}
        return [
            mtypes.Tool(name="proof_read", description="record-only benign control", inputSchema=obj),
            mtypes.Tool(name="exec_command", description="record-only command target", inputSchema=obj),
            mtypes.Tool(name="install_plugin", description="record-only plugin target", inputSchema=obj),
        ]

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[mtypes.TextContent]:
        entry = record_call(name, arguments or {})
        body = {
            "recorded": True,
            "executed": False,
            "tool": name,
            "arguments_sha256": entry["arguments_sha256"],
        }
        return [mtypes.TextContent(type="text", text=json.dumps(body, sort_keys=True))]

    return app


async def _main() -> None:
    app = _build_app()
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
