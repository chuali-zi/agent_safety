"""CLI for freezing, running and rendering real-model causal experiments."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from kernel.live_agent.models import ExperimentConfig
from kernel.live_agent.provider import DeepSeekAdapter
from kernel.live_agent.render import render_replay
from kernel.live_agent.runner import LiveAgentRunner, freeze_manifest, load_local_env


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Open Agent Range real-model causal experiment")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate manifest and local DeepSeek configuration")
    _manifest_arg(check)
    check.add_argument("--env-file", default=".env")

    freeze = sub.add_parser("freeze", help="freeze a phase-specific experiment manifest")
    _manifest_arg(freeze)
    freeze.add_argument("--phase", choices=["development", "holdout", "all"], default="holdout")
    freeze.add_argument("--out", required=True)

    for name, help_text, default_phase in (
        ("discover", "run the development attack-discovery set", "development"),
        ("evaluate", "run the frozen holdout evaluation", "holdout"),
    ):
        command = sub.add_parser(name, help=help_text)
        _manifest_arg(command)
        command.add_argument("--phase", choices=["development", "holdout", "all"], default=default_phase)
        command.add_argument("--evidence-dir", required=True)
        command.add_argument("--env-file", default=".env")
        command.add_argument("--guard", choices=["live", "offline"], default="live")
        command.add_argument("--xa-guard-root")
        command.add_argument("--repeats", type=int)

    render = sub.add_parser("render", help="render a self-contained evidence replay page")
    render.add_argument("--evidence-dir", required=True)
    render.add_argument("--out")

    verify = sub.add_parser("verify", help="authenticity acceptance for a sealed evidence package")
    verify.add_argument("--evidence-dir", required=True)

    args = parser.parse_args(argv)
    if args.command == "check":
        return _check(args)
    if args.command == "freeze":
        return _freeze(args)
    if args.command in {"discover", "evaluate"}:
        return _run(args)
    if args.command == "render":
        path = render_replay(args.evidence_dir, args.out)
        print(path)
        return 0
    if args.command == "verify":
        from kernel.live_agent.authenticity import verify_evidence

        report = verify_evidence(args.evidence_dir)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    raise AssertionError(f"unhandled command: {args.command}")


def _manifest_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", required=True)


def _check(args: argparse.Namespace) -> int:
    config = ExperimentConfig.load(args.manifest)
    load_local_env(args.env_file)
    result = {
        "ok": True,
        "experiment_id": config.experiment_id,
        "model": config.model,
        "thinking": config.thinking,
        "development_cases": len(config.cases_for_phase("development")),
        "holdout_cases": len(config.cases_for_phase("holdout")),
        "prompt_profiles": [item.profile_id for item in config.prompt_profiles],
        "api_key_configured": bool(os.environ.get("DEEPSEEK_API_KEY", "")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _freeze(args: argparse.Namespace) -> int:
    config = ExperimentConfig.load(args.manifest)
    payload = freeze_manifest(config, phase=args.phase, repeats=config.repeats)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(path)
    return 0


def _run(args: argparse.Namespace) -> int:
    config = ExperimentConfig.load(args.manifest)
    load_local_env(args.env_file)
    _assert_env_matches_manifest(config)
    adapter = DeepSeekAdapter(
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        base_url=config.base_url,
        model=config.model,
        thinking=config.thinking,
        temperature=config.temperature,
        timeout_seconds=config.timeout_seconds,
        http_retries=config.http_retries,
    )
    runner = LiveAgentRunner(
        config,
        adapter,
        evidence_dir=args.evidence_dir,
        guard_mode=args.guard,
        xa_guard_root=Path(args.xa_guard_root).resolve() if args.xa_guard_root else None,
    )
    summary = runner.run(phase=args.phase, repeats=args.repeats)
    replay_path = Path(args.evidence_dir) / "replay.html"
    print(json.dumps({**summary, "replay_path": str(replay_path)}, ensure_ascii=False, indent=2))
    return 0 if summary["infra_failures"] == 0 else 2


def _assert_env_matches_manifest(config: ExperimentConfig) -> None:
    frozen = {
        "XA_LIVE_AGENT_BASE_URL": config.base_url,
        "XA_LIVE_AGENT_MODEL": config.model,
        "XA_LIVE_AGENT_THINKING": config.thinking,
        "XA_LIVE_AGENT_MAX_TURNS": str(config.max_turns),
        "XA_LIVE_AGENT_TIMEOUT_SECONDS": str(int(config.timeout_seconds)),
    }
    mismatches = {
        key: {"expected": expected, "actual": os.environ[key]}
        for key, expected in frozen.items()
        if os.environ.get(key) and os.environ[key] != expected
    }
    if mismatches:
        raise ValueError(f"environment overrides conflict with frozen manifest: {mismatches}")


if __name__ == "__main__":
    raise SystemExit(main())
