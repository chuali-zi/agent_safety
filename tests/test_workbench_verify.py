"""verifier / tamper 测试：原包 PASS、受控篡改副本 FAIL、原包不被修改。"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workbench.verify import verify_original, verify_tampered_copy  # noqa: E402

PACKS_ROOT = REPO_ROOT / "open-agent-range" / ".runtime" / "live-agent"
SMOKE_PACK = PACKS_ROOT / "holdout-v2-smoke-20260803-authorized"


def _pack_fingerprint(pack: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(pack.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(pack)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.mark.skipif(not SMOKE_PACK.is_dir(), reason="sealed smoke pack not present")
def test_original_pack_verifies_pass() -> None:
    result = verify_original(SMOKE_PACK)
    assert result["target"] == "ORIGINAL_EVIDENCE"
    assert result["ok"] is True, [c for c in result["checks"] if not c["ok"]]


@pytest.mark.skipif(not SMOKE_PACK.is_dir(), reason="sealed smoke pack not present")
def test_tampered_copy_fails_and_original_untouched(tmp_path) -> None:
    before = _pack_fingerprint(SMOKE_PACK)
    result = verify_tampered_copy(SMOKE_PACK, "summary.json", "/scheduled_runs", tmp_path)
    assert result["target"] == "TAMPERED_COPY"
    # 受控篡改后 verifier 必须 FAIL（预期行为）
    assert result["ok"] is False
    assert result["copy_label"].startswith("tamper-")
    # 原包只读
    assert _pack_fingerprint(SMOKE_PACK) == before
    # 复制包已清理
    assert not list(tmp_path.glob("tamper-*"))


def test_tamper_rejects_bad_pointer(tmp_path) -> None:
    with pytest.raises(ValueError):
        verify_tampered_copy(PACKS_ROOT, "summary.json", "no-leading-slash", tmp_path)


def test_tamper_rejects_non_allowlisted_artifact(tmp_path) -> None:
    with pytest.raises(ValueError):
        verify_tampered_copy(PACKS_ROOT, "audit.jsonl", "/x", tmp_path)
