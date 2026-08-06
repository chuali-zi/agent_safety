"""Workbench 本地 HTTP server（Python stdlib，仅绑 127.0.0.1）。

启动：
    python -m workbench.server --port 8787 \
        --manifest open-agent-range/scenarios/live-agent/p0-d1-d3-v2.json \
        --env-file .env

安全纪律：响应不回显 API key / env / 绝对路径；artifact 名白名单；
路径解析限定在 pack 根内；写请求带未知字段 → 400。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .events import EventBuilder, sha256_file
from .replay import (
    derive_replay_events,
    list_sealed_runs,
    resolve_run_dir,
    sealed_index_integrity_ok,
)
from .store import RunStore
from .synthetic import OperatorChannel, SCENARIOS, run_synthetic

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_MANIFEST = REPO_ROOT / "open-agent-range" / "scenarios" / "live-agent" / "p0-d1-d3-v2.json"
DEFAULT_PACKS_ROOT = REPO_ROOT / "open-agent-range" / ".runtime" / "live-agent"
DEFAULT_WORK_ROOT = REPO_ROOT / ".runtime" / "workbench"
DEFAULT_XA_GUARD_ROOT = REPO_ROOT

ARTIFACT_WHITELIST = {
    "experiment-manifest.json",
    "agent-transcript.jsonl",
    "tool-intent.json",
    "world-before-intent.json",
    "world-out.json",
    "ledger.jsonl",
    "output.json",
    "verdict.json",
    "audit.jsonl",
    "artifact-hashes.json",
    "summary.json",
}

_SENSITIVE_KEY_RE = re.compile(r"key|token|secret|password|credential", re.IGNORECASE)
_CONTENT_KEY_RE = re.compile(
    r"(?:prompt|content|arguments?|parameters?|payload|body|text|query|task|history|"
    r"injections?|sources?|attachments?|records?|messages?|result|output|data|value|"
    r"reason|error|detail)",
    re.IGNORECASE,
)
_DIGEST_KEY_RE = re.compile(r"(?:sha256|digest|hash)$", re.IGNORECASE)
_POSIX_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9._-])/(?:home|mnt|tmp|var|etc|opt|srv|root|workspace)(?:/[^\s\"'<>]+)+"
)
_MAX_STRING = 2000
_MAX_LINES = 300
_PACK_LEVEL_ARTIFACTS = {
    "experiment-manifest.json",
    "artifact-hashes.json",
    "summary.json",
}


def _redacted_summary(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"<redacted sha256={digest} chars={len(raw)}>"


def _sanitize(value: Any, depth: int = 0) -> Any:
    """递归脱敏：剔除敏感键、截断超长字符串、限制深度。"""
    if depth > 12:
        return "…"
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if _SENSITIVE_KEY_RE.search(str(key)):
                out[str(key)] = "<redacted>"
            elif _CONTENT_KEY_RE.search(str(key)) and not _DIGEST_KEY_RE.search(str(key)):
                out[str(key)] = _redacted_summary(item)
            else:
                out[str(key)] = _sanitize(item, depth + 1)
        return out
    if isinstance(value, list):
        return [_sanitize(item, depth + 1) for item in value[:_MAX_LINES]]
    if isinstance(value, str):
        # 不回显本机绝对路径
        value = re.sub(r"[A-Za-z]:\\\\[^\s\"']+", "<path>", value)
        value = re.sub(r"[A-Za-z]:\\[^\s\"']+", "<path>", value)
        value = _POSIX_PATH_RE.sub("<path>", value)
        if len(value) > _MAX_STRING:
            value = value[:_MAX_STRING] + "…"
        return value
    return value


def _artifact_safe_view(name: str, data: Any) -> Any:
    """生成适合 DOM/录屏的最小视图；world/ledger/output 不回显业务正文。"""
    if name in {"world-before-intent.json", "world-out.json"} and isinstance(data, dict):
        side_effects = data.get("side_effects")
        return {
            "redacted": True,
            "top_level_keys": sorted(str(key) for key in data)[:100],
            "side_effect_count": len(side_effects) if isinstance(side_effects, list) else None,
            "note": "business payload omitted; use the envelope SHA-256 for traceability",
        }
    if name == "ledger.jsonl" and isinstance(data, dict):
        rows = data.get("lines", [])
        return {
            "format": "jsonl",
            "redacted": True,
            "record_count": len(rows) if isinstance(rows, list) else 0,
            "record_sha256": [
                hashlib.sha256(
                    json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                        "utf-8"
                    )
                ).hexdigest()
                for row in rows[:_MAX_LINES]
            ]
            if isinstance(rows, list)
            else [],
        }
    if name == "output.json":
        return {
            "redacted": True,
            "document_sha256": hashlib.sha256(
                json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest(),
            "note": "tool output omitted from the recording surface",
        }
    return _sanitize(data)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _request_origin_is_local(handler: BaseHTTPRequestHandler) -> bool:
    host = handler.headers.get("Host", "")
    if not re.fullmatch(r"(?:127\.0\.0\.1|localhost)(?::\d{1,5})?", host, re.IGNORECASE):
        return False
    origin = handler.headers.get("Origin")
    if not origin:
        return True
    try:
        return urllib.parse.urlparse(origin).hostname in {"127.0.0.1", "localhost"}
    except ValueError:
        return False


class WorkbenchConfig:
    def __init__(
        self,
        *,
        manifest: Path,
        env_file: Path | None,
        packs_root: Path,
        work_root: Path,
        xa_guard_root: Path,
    ) -> None:
        self.manifest = manifest
        self.env_file = env_file
        self.packs_root = packs_root
        self.work_root = work_root
        self.xa_guard_root = xa_guard_root
        self.store = RunStore(work_root)
        self.operator_channels: dict[str, OperatorChannel] = {}
        self._lock = threading.Lock()
        # 合成演示节奏（秒）；演示/截图可用 XA_WORKBENCH_SYNTHETIC_DELAY 调快
        import os

        try:
            self.synthetic_delay = float(os.environ.get("XA_WORKBENCH_SYNTHETIC_DELAY", "0.9"))
        except ValueError:
            self.synthetic_delay = 0.9
        self.synthetic_delay = min(max(self.synthetic_delay, 0.0), 10.0)

    def resolve_pack(self, pack_name: str) -> Path | None:
        """把 pack 名解析为 packs_root 内的目录；拒绝路径穿越。"""
        if not re.fullmatch(r"[A-Za-z0-9._-]+", pack_name or ""):
            return None
        candidate = (self.packs_root / pack_name).resolve()
        try:
            candidate.relative_to(self.packs_root.resolve())
        except ValueError:
            return None
        return candidate if candidate.is_dir() else None


def _parse_scenario_id(scenario_id: str) -> tuple[str, list[str]]:
    kind, _, rest = scenario_id.partition(":")
    return kind, [seg for seg in rest.split("/") if seg]


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    handler.end_headers()
    handler.wfile.write(body)


def _error(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    _json_response(handler, status, {"error": message})


def _read_body(handler: BaseHTTPRequestHandler) -> dict | None:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0 or length > 64 * 1024:
        return None
    try:
        body = json.loads(handler.rfile.read(length).decode("utf-8"))
        return body if isinstance(body, dict) else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def make_handler(config: WorkbenchConfig):
    class Handler(BaseHTTPRequestHandler):
        server_version = "XA-Guard-Workbench/0.1"

        def log_message(self, fmt, *args):  # 静默，避免泄漏到终端
            return

        # ---------- GET ----------
        def do_GET(self):
            if not _request_origin_is_local(self):
                return _error(self, 403, "local origin required")
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            path = parsed.path
            if path == "/" or path == "/index.html":
                return self._serve_static("index.html")
            if path.startswith("/static/"):
                return self._serve_static(path[len("/static/"):])
            if path == "/api/live/scenarios":
                return self._scenarios()
            if path == "/api/live/runs":
                try:
                    limit = int(query.get("limit", ["20"])[0] or 20)
                except ValueError:
                    return _error(self, 400, "limit must be an integer")
                if limit < 1:
                    return _error(self, 400, "limit must be positive")
                return _json_response(self, 200, {"runs": config.store.list_runs(min(limit, 100))})
            if path == "/api/live/events":
                return self._events(query)
            if path == "/api/live/artifact":
                return self._artifact(query)
            return _error(self, 404, "not found")

        def _serve_static(self, name: str):
            if not re.fullmatch(r"[A-Za-z0-9._-]+", name or ""):
                return _error(self, 404, "not found")
            target = STATIC_DIR / name
            if not target.is_file():
                return _error(self, 404, "not found")
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
            }.get(target.suffix, "application/octet-stream")
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "connect-src 'self'; img-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _scenarios(self):
            packs = []
            if config.packs_root.is_dir():
                for child in sorted(config.packs_root.iterdir()):
                    if (
                        not child.is_dir()
                        or not (child / "summary.json").is_file()
                        or not sealed_index_integrity_ok(child)
                    ):
                        continue
                    packs.append(
                        {
                            "pack": child.name,
                            "runs": list_sealed_runs(child)[:50],
                        }
                    )
            live_cases = []
            try:
                from .live import OAR_ROOT  # noqa: F401 - 确保 sys.path
                import sys

                if str(OAR_ROOT) not in sys.path:
                    sys.path.insert(0, str(OAR_ROOT))
                from kernel.live_agent.models import ExperimentConfig

                cfg = ExperimentConfig.load(config.manifest)
                live_cases = [c.case_id for c in cfg.cases_for_phase("holdout")]
            except Exception:  # noqa: BLE001 - manifest 缺失时 live 列表为空，如实
                live_cases = []
            return _json_response(
                self,
                200,
                {
                    "live_cases": live_cases,
                    "sealed_packs": packs,
                    "synthetic": list(SCENARIOS),
                },
            )

        def _events(self, query):
            run_id = query.get("run_id", [""])[0]
            try:
                after_seq = int(query.get("after_seq", ["0"])[0] or 0)
            except ValueError:
                return _error(self, 400, "after_seq must be an integer")
            if after_seq < 0:
                return _error(self, 400, "after_seq must be non-negative")
            result = config.store.events_after(run_id, after_seq)
            if result is None:
                return _error(self, 404, "unknown run_id")
            events, next_after = result
            return _json_response(
                self, 200, {"run_id": run_id, "events": events, "next_after_seq": next_after}
            )

        def _artifact(self, query):
            run_id = query.get("run_id", [""])[0]
            name = query.get("name", [""])[0]
            expected_digest = query.get("sha256", [""])[0]
            record = config.store.get(run_id)
            if record is None or record.artifact_root is None:
                return _error(self, 404, "unknown run_id")
            if name not in ARTIFACT_WHITELIST:
                return _error(self, 400, "artifact name not allowlisted")
            if expected_digest and not re.fullmatch(r"[a-f0-9]{64}", expected_digest):
                return _error(self, 400, "invalid artifact sha256")

            roots = [record.artifact_root]
            matches = sorted(record.artifact_root.rglob(name))
            if (
                name in _PACK_LEVEL_ARTIFACTS
                and record.pack_root is not None
                and record.pack_root.resolve() != record.artifact_root.resolve()
            ):
                pack_level = record.pack_root / name
                if pack_level.is_file():
                    matches.append(pack_level)
                    roots.append(record.pack_root)
            safe_matches: list[tuple[Path, bytes, str]] = []
            for candidate in matches:
                resolved = candidate.resolve()
                if not any(
                    _is_within(resolved, root.resolve())
                    for root in roots
                ):
                    continue
                raw = resolved.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                if not expected_digest or digest == expected_digest:
                    safe_matches.append((resolved, raw, digest))
            # 同一 run 的 Null/Guard 常有同名 world/ledger；没有 hash 时绝不能猜分支。
            unique_digests = {item[2] for item in safe_matches}
            if len(unique_digests) > 1:
                return _error(self, 409, "artifact name is ambiguous; provide sha256")
            matches = safe_matches
            if not matches:
                return _error(self, 404, "artifact not found in run")
            target, raw, digest = matches[0]
            if target.suffix == ".jsonl":
                lines = [
                    json.loads(line)
                    for line in raw.decode("utf-8").splitlines()
                    if line.strip()
                ][: _MAX_LINES]
                data: Any = {"format": "jsonl", "lines": lines}
            else:
                data = json.loads(raw.decode("utf-8"))
            return _json_response(
                self,
                200,
                {
                    "run_id": run_id,
                    "name": name,
                    "sha256": digest,
                    "data": _artifact_safe_view(name, data),
                },
            )

        # ---------- POST ----------
        def do_POST(self):
            if not _request_origin_is_local(self):
                return _error(self, 403, "local origin required")
            parsed = urllib.parse.urlparse(self.path)
            body = _read_body(self)
            if body is None:
                return _error(self, 400, "invalid json body")
            if parsed.path == "/api/live/preflight":
                return self._preflight(body)
            if parsed.path == "/api/live/run":
                return self._run(body)
            if parsed.path == "/api/live/verify":
                return self._verify(body)
            if parsed.path == "/api/live/verify-tampered-copy":
                return self._verify_tampered(body)
            if parsed.path == "/api/live/operator":
                return self._operator(body)
            return _error(self, 404, "not found")

        def _preflight(self, body: dict):
            if not set(body) <= {"scenario_id", "guard_mode", "manifest_id"}:
                return _error(self, 400, "unknown fields")
            scenario_id = str(body.get("scenario_id", ""))
            guard_mode = str(body.get("guard_mode", ""))
            if not scenario_id or guard_mode not in {"live", "offline"}:
                return _error(self, 400, "scenario_id and guard_mode required")
            kind, _ = _parse_scenario_id(scenario_id)
            if kind not in {"live", "sealed", "synthetic"}:
                return _error(self, 400, "unknown scenario kind")
            if kind != "live":
                return _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "checks": [{"name": "non_live_scenario", "ok": True, "detail": "no preflight needed"}],
                        "safe_summary": {"provider_ready": False},
                    },
                )
            from .live import preflight

            checks = preflight(config.manifest, config.env_file, config.xa_guard_root)
            ok = all(c["ok"] for c in checks)
            safe_summary: dict[str, Any] = {
                "provider_ready": any(
                    c["name"] == "provider_key_present" and c["ok"] for c in checks
                )
            }
            if config.manifest.is_file():
                safe_summary["scenario_sha256"] = sha256_file(config.manifest)
            return _json_response(self, 200, {"ok": ok, "checks": checks, "safe_summary": safe_summary})

        def _run(self, body: dict):
            if not set(body) <= {"scenario_id", "guard_mode", "case_id", "recording_label"}:
                return _error(self, 400, "unknown fields")
            scenario_id = str(body.get("scenario_id", ""))
            if not scenario_id or body.get("guard_mode") != "live":
                return _error(self, 400, "scenario_id and guard_mode=live required")
            recording_label = body.get("recording_label")
            if recording_label is not None and (
                not isinstance(recording_label, str) or len(recording_label) > 80
            ):
                return _error(self, 400, "recording_label must be a string of at most 80 chars")
            kind, segments = _parse_scenario_id(scenario_id)

            if kind == "live":
                run_mode = "LIVE_RUN"
                if len(segments) != 1:
                    return _error(self, 400, "live scenario must contain exactly one case id")
                case_id = segments[0]
                requested_case = body.get("case_id")
                if requested_case is not None and requested_case != case_id:
                    return _error(self, 400, "case_id conflicts with scenario_id")
                try:
                    from .live import OAR_ROOT  # noqa: F401 - 导入时设置 OAR sys.path
                    from kernel.live_agent.models import ExperimentConfig

                    live_config = ExperimentConfig.load(config.manifest)
                    available_cases = {
                        item.case_id for item in live_config.cases_for_phase("holdout")
                    }
                except Exception as exc:  # noqa: BLE001 - 配置不可用时不创建幽灵 run
                    return _error(self, 503, f"live manifest unavailable: {type(exc).__name__}")
                if case_id not in available_cases:
                    return _error(self, 400, "unknown live case")
            elif kind == "sealed":
                run_mode = "SEALED_REPLAY"
                if len(segments) != 4:
                    return _error(
                        self,
                        400,
                        "sealed scenario: sealed:<pack>/<case>/<profile>/<run-NNN>",
                    )
                pack = config.resolve_pack(segments[0])
                if pack is None:
                    return _error(self, 400, "unknown sealed pack")
                try:
                    sealed_run_root = resolve_run_dir(
                        pack, segments[1], segments[2], segments[3]
                    )
                except ValueError:
                    return _error(self, 400, "invalid sealed run path")
                if not sealed_run_root.is_dir():
                    return _error(self, 400, "unknown sealed run")
            elif kind == "synthetic":
                run_mode = "EXAMPLE_SYNTHETIC"
                if len(segments) != 1 or segments[0] not in SCENARIOS:
                    return _error(self, 400, "unknown synthetic scenario")
                scenario = segments[0]
            else:
                return _error(self, 400, "scenario_id must start with live:/sealed:/synthetic:")

            # 所有输入验证完成后才注册 run，400/503 不污染最近运行列表。
            record = config.store.create_run(scenario_id, run_mode)

            if kind == "live":
                record.artifact_root = config.work_root / f"live-{record.run_id}"
                record.pack_root = record.artifact_root
                record.pack_label = "live"

                def target():
                    from .live import run_live

                    builder = EventBuilder(record.run_id, run_mode)

                    def emit(event):
                        config.store.append_event(record, event)

                    try:
                        run_live(
                            manifest_path=config.manifest,
                            env_file=config.env_file,
                            case_id=case_id,
                            evidence_dir=record.artifact_root,
                            xa_guard_root=config.xa_guard_root,
                            emit=emit,
                            builder=builder,
                        )
                    except Exception as exc:  # noqa: BLE001
                        try:
                            emit(
                                builder.emit(
                                    "RUN_FAILED",
                                    "FAILED",
                                    message=f"live 线程异常：{type(exc).__name__}",
                                )
                            )
                        except Exception:  # noqa: BLE001
                            pass

            elif kind == "sealed":
                record.artifact_root = sealed_run_root
                record.pack_root = pack
                record.pack_label = segments[0]

                def target():
                    builder = EventBuilder(record.run_id, run_mode)

                    def emit(event):
                        config.store.append_event(record, event)

                    try:
                        derive_replay_events(pack, segments[1], segments[2], segments[3], emit, builder)
                    except Exception as exc:  # noqa: BLE001
                        try:
                            emit(
                                builder.emit(
                                    "RUN_FAILED",
                                    "FAILED",
                                    message=f"replay 失败：{type(exc).__name__}",
                                )
                            )
                        except Exception:  # noqa: BLE001
                            pass

            else:  # synthetic
                channel = OperatorChannel()
                with config._lock:
                    config.operator_channels[record.run_id] = channel
                record.artifact_root = None
                record.pack_label = f"synthetic:{scenario}"

                def target():
                    builder = EventBuilder(record.run_id, run_mode)

                    def emit(event):
                        config.store.append_event(record, event)

                    try:
                        run_synthetic(
                            scenario,
                            emit,
                            builder,
                            operator_channel=channel,
                            step_delay=config.synthetic_delay,
                        )
                    except Exception as exc:  # noqa: BLE001
                        try:
                            emit(
                                builder.emit(
                                    "RUN_FAILED",
                                    "FAILED",
                                    message=f"synthetic 失败：{type(exc).__name__}",
                                )
                            )
                        except Exception:  # noqa: BLE001
                            pass
                    finally:
                        with config._lock:
                            config.operator_channels.pop(record.run_id, None)

            threading.Thread(target=target, daemon=True).start()
            return _json_response(
                self,
                200,
                {"run_id": record.run_id, "state": "MODEL_REQUESTED", "run_mode": run_mode},
            )

        def _verify(self, body: dict):
            if not set(body) <= {"run_id"}:
                return _error(self, 400, "unknown fields")
            record = config.store.get(str(body.get("run_id", "")))
            if record is None or record.pack_root is None:
                return _error(self, 404, "unknown run_id or no pack")
            from .verify import verify_original

            try:
                result = verify_original(record.pack_root)
            except Exception as exc:  # noqa: BLE001
                return _error(self, 500, f"verify failed: {type(exc).__name__}")
            self._emit_verification(record, "VERIFY_COMPLETED", result, "VERIFYING")
            return _json_response(self, 200, result)

        def _verify_tampered(self, body: dict):
            if not set(body) <= {"run_id", "artifact_name", "json_pointer"}:
                return _error(self, 400, "unknown fields")
            record = config.store.get(str(body.get("run_id", "")))
            if record is None or record.pack_root is None:
                return _error(self, 404, "unknown run_id or no pack")
            from .verify import verify_tampered_copy

            try:
                result = verify_tampered_copy(
                    record.pack_root,
                    str(body.get("artifact_name", "")),
                    str(body.get("json_pointer", "")),
                    config.work_root,
                )
            except (ValueError, FileNotFoundError, KeyError) as exc:
                return _error(self, 400, f"tamper request invalid: {type(exc).__name__}")
            except Exception as exc:  # noqa: BLE001
                return _error(self, 500, f"verify failed: {type(exc).__name__}")
            self._emit_verification(record, "VERIFY_COMPLETED", result, "COMPLETE")
            return _json_response(self, 200, result)

        def _emit_verification(self, record, event_type, result, state):
            builder = EventBuilder.__new__(EventBuilder)
            builder.run_id = record.run_id
            builder.run_mode = record.run_mode
            builder._sequence = max((e.get("sequence", 0) for e in record.events), default=0)
            verification = {
                "target": result["target"],
                "ok": result["ok"],
                "check_count": len(result.get("checks", [])),
                "failed_checks": [
                    c["name"] for c in result.get("checks", []) if not c.get("ok")
                ],
            }
            try:
                event = builder.emit(
                    event_type,
                    state,
                    branch="VERIFIER",
                    message=f"verifier {result['target']}: {'PASS' if result['ok'] else 'FAIL'}",
                    verification=verification,
                )
                config.store.append_event(record, event)
            except Exception:  # noqa: BLE001 - 验证结果已通过 API 返回，事件失败不阻断
                pass

        def _operator(self, body: dict):
            """合成 HITL 的 Operator 按钮通道；仅对 EXAMPLE_SYNTHETIC run 有效。"""
            if not set(body) <= {"run_id", "action"}:
                return _error(self, 400, "unknown fields")
            run_id = str(body.get("run_id", ""))
            action = str(body.get("action", ""))
            if action not in {"approve", "reject", "replay"}:
                return _error(self, 400, "action must be approve, reject, or replay")
            record = config.store.get(run_id)
            if record is None or record.run_mode != "EXAMPLE_SYNTHETIC":
                return _error(self, 400, "operator channel only for EXAMPLE_SYNTHETIC runs")
            with config._lock:
                channel = config.operator_channels.get(run_id)
            if channel is None:
                return _error(self, 404, "no operator channel")
            if not channel.submit(action):
                return _error(self, 409, "operator action already submitted")
            return _json_response(self, 200, {"ok": True})

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="XA-Guard Live Workbench local server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--packs-root", default=str(DEFAULT_PACKS_ROOT))
    parser.add_argument("--work-root", default=str(DEFAULT_WORK_ROOT))
    parser.add_argument("--xa-guard-root", default=str(DEFAULT_XA_GUARD_ROOT))
    args = parser.parse_args(argv)

    if args.host != "127.0.0.1":
        raise SystemExit("workbench 只允许绑定 127.0.0.1")

    config = WorkbenchConfig(
        manifest=Path(args.manifest),
        env_file=Path(args.env_file) if args.env_file else None,
        packs_root=Path(args.packs_root),
        work_root=Path(args.work_root),
        xa_guard_root=Path(args.xa_guard_root),
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(config))
    print(f"XA-Guard Live Workbench: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
