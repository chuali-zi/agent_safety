"""Run 注册表与事件日志。

每个 run 的事件保存在内存，并追加写入 .runtime/workbench/runs/<run_id>/events.jsonl，
便于断线重查。run_id 由服务端生成，符合 schema 的 ^run_[A-Za-z0-9_-]{8,96}$。
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .events import now_iso, validate_event

RUN_ID_PATTERN = re.compile(r"^run_[A-Za-z0-9_-]{8,96}$")

_MODE_PREFIX = {
    "LIVE_RUN": "live",
    "SEALED_REPLAY": "sealed",
    "EXAMPLE_SYNTHETIC": "synth",
}


@dataclass
class RunRecord:
    run_id: str
    run_mode: str
    scenario_id: str
    started_at: str
    state: str = "IDLE"
    events: list[dict] = field(default_factory=list)
    # 该 run 可读取 artifact 的根目录（绝对路径，仅供服务端内部使用，不回显给前端）
    artifact_root: Path | None = None
    # 证据包根（sealed 模式用于 verify；live 模式指向 live 产出目录）
    pack_root: Path | None = None
    pack_label: str = ""
    intent_sha256: str = ""
    guard_decision: str = "unknown"
    meta: dict = field(default_factory=dict)

    def summary(self) -> dict:
        payload = {
            "run_id": self.run_id,
            "state": self.state,
            "run_mode": self.run_mode,
            "started_at": self.started_at,
            "guard_decision": self.guard_decision,
            "scenario_id": self.scenario_id,
            "pack_label": self.pack_label,
        }
        if self.intent_sha256:
            payload["intent_sha256"] = self.intent_sha256
        return payload


class RunStore:
    def __init__(self, work_root: Path | str) -> None:
        self.work_root = Path(work_root)
        self._runs: dict[str, RunRecord] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()

    def create_run(self, scenario_id: str, run_mode: str) -> RunRecord:
        prefix = _MODE_PREFIX.get(run_mode, "run")
        token = secrets.token_hex(4)
        run_id = f"run_{prefix}_{token}"
        record = RunRecord(
            run_id=run_id,
            run_mode=run_mode,
            scenario_id=scenario_id,
            started_at=now_iso(),
        )
        with self._lock:
            self._runs[run_id] = record
            self._order.append(run_id)
        return record

    def get(self, run_id: str) -> RunRecord | None:
        if not RUN_ID_PATTERN.match(run_id or ""):
            return None
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self, limit: int = 20) -> list[dict]:
        with self._lock:
            ids = list(reversed(self._order[-limit:]))
            return [self._runs[run_id].summary() for run_id in ids]

    def append_event(self, record: RunRecord, event: dict) -> None:
        with self._lock:
            # 后台 run 与 verifier HTTP 请求可能并发。sequence 由 store 最终裁决，避免两个
            # EventBuilder 同时产生相同序号；重编号后再次过 schema。
            expected_sequence = (
                max((int(item.get("sequence", 0)) for item in record.events), default=0) + 1
            )
            if int(event.get("sequence", 0)) != expected_sequence:
                event = dict(event)
                event["sequence"] = expected_sequence
                validate_event(event)
            record.events.append(event)
            record.state = str(event.get("state", record.state))
            intent = event.get("intent") or {}
            if intent.get("arguments_sha256"):
                record.intent_sha256 = str(intent["arguments_sha256"])
            branch_result = event.get("branch_result") or {}
            if event.get("branch") == "GUARD" and branch_result.get("decision"):
                record.guard_decision = str(branch_result["decision"])
            # 磁盘顺序必须与内存顺序一致，不能在释放锁后让并发写入反转。
            log_dir = self.work_root / "runs" / record.run_id
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def events_after(self, run_id: str, after_seq: int) -> tuple[list[dict], int] | None:
        record = self.get(run_id)
        if record is None:
            return None
        with self._lock:
            events = [e for e in record.events if int(e.get("sequence", 0)) > after_seq]
            next_after = max((int(e.get("sequence", 0)) for e in record.events), default=0)
        return events, next_after
