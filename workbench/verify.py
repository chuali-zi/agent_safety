"""verifier 包装：原包重算 + 受控篡改副本验证。

纪律（contracts.md §5）：
- 原包只读，绝不修改。
- tamper 只作用于新建复制包（.runtime/workbench/tamper-*）。
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
OAR_ROOT = REPO_ROOT / "open-agent-range"
if str(OAR_ROOT) not in sys.path:
    sys.path.insert(0, str(OAR_ROOT))

TAMPERABLE_ARTIFACTS = ("summary.json", "verdict.json", "tool-intent.json")
_POINTER_RE = re.compile(r"^/[^/]+(?:/[^/]+)*$")
_LOCAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\[^\s\"']+|(?<![A-Za-z0-9._-])/(?:home|mnt|tmp|var|opt|root)(?:/[^\s\"']+)+)"
)


def _safe_detail(value: Any) -> str:
    return _LOCAL_PATH_RE.sub("<path>", str(value))[:300]


def verify_original(pack_root: Path) -> dict[str, Any]:
    from kernel.live_agent.authenticity import verify_evidence

    report = verify_evidence(pack_root)
    return {
        "target": "ORIGINAL_EVIDENCE",
        "ok": bool(report.get("ok")),
        "checks": [
            {"name": str(c.get("name", "")), "ok": bool(c.get("ok")), "detail": _safe_detail(c.get("detail", ""))}
            for c in report.get("checks", [])
        ],
    }


def _locate_artifact(pack_root: Path, artifact_name: str) -> Path:
    if artifact_name not in TAMPERABLE_ARTIFACTS:
        raise ValueError(f"artifact not tamperable: {artifact_name}")
    direct = pack_root / artifact_name
    if direct.is_file():
        return direct
    matches = sorted(pack_root.rglob(artifact_name))
    if not matches:
        raise FileNotFoundError(f"{artifact_name} not found in pack")
    return matches[0]


def _mutate_at_pointer(document: Any, pointer: str) -> None:
    if not _POINTER_RE.match(pointer):
        raise ValueError(f"invalid json_pointer: {pointer}")
    segments = [seg.replace("~1", "/").replace("~0", "~") for seg in pointer.split("/")[1:]]
    node = document
    for seg in segments[:-1]:
        node = node[int(seg)] if isinstance(node, list) else node[seg]
    key = segments[-1]
    if isinstance(node, list):
        key = int(key)
    current = node[key]
    if isinstance(current, bool):
        node[key] = not current
    elif isinstance(current, (int, float)):
        node[key] = current + 1
    elif isinstance(current, str):
        node[key] = current + "-tampered"
    else:
        node[key] = "tampered"


def verify_tampered_copy(
    pack_root: Path,
    artifact_name: str,
    json_pointer: str,
    work_root: Path,
) -> dict[str, Any]:
    from kernel.live_agent.authenticity import verify_evidence

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    copy_label = f"tamper-{stamp}-{secrets.token_hex(4)}"
    work_root.mkdir(parents=True, exist_ok=True)
    copy_root = work_root / copy_label
    shutil.copytree(pack_root, copy_root)
    try:
        target = _locate_artifact(copy_root, artifact_name)
        document = json.loads(target.read_text(encoding="utf-8"))
        _mutate_at_pointer(document, json_pointer)
        target.write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
        )
        report = verify_evidence(copy_root)
    finally:
        shutil.rmtree(copy_root, ignore_errors=True)
    return {
        "target": "TAMPERED_COPY",
        "ok": bool(report.get("ok")),
        "checks": [
            {"name": str(c.get("name", "")), "ok": bool(c.get("ok")), "detail": _safe_detail(c.get("detail", ""))}
            for c in report.get("checks", [])
        ],
        "copy_label": copy_label,
    }
