"""审批令牌（approval_token）签发与验签 —— 赛题方向 2/4 审批闭环。

设计目标：让"谁、在什么时候、对哪一组精确入参、批准了哪个工具、有效到何时"
成为可验证、可审计、不可事后伪造的证据，并且**令牌必须验签通过工具才会执行**
（不是审计里的装饰字段）。

令牌 = HMAC-SHA256(secret, canonical_json(payload))，payload 绑定：
    trace_id + tool_name + args_hash + approver + issued_at + expires_at
    + request_identity + tenant_id + provenance_digest + history_digest
    + taint + policy_bundle_sha + effect_class + nonce

- args_hash 绑定精确入参 → 审批后篡改参数（TOCTOU）会令牌失配。
- identity / tenant / provenance / history / taint / policy / effect 绑定
  → 批准后上下文漂移会被拒绝。
- nonce + 进程内原子消费 → 同一令牌不能重复执行。
- expires_at → 过期令牌不可执行。
- secret 走环境变量 XA_GUARD_APPROVAL_SECRET（缺省 demo 密钥）。

demo 用 HMAC；多实例生产部署仍需把 nonce 消费状态放入共享事务存储，
并用受管密钥替换缺省 demo 密钥。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

from xa_guard.types import Approval

_DEFAULT_SECRET = "xa-guard-demo-approval-secret"
_DEFAULT_TTL_SECONDS = 300
MAX_APPROVAL_TTL_SECONDS = 900
_CONSUMED_LOCK = threading.Lock()
_CONSUMED_TOKENS: dict[str, datetime] = {}


def _secret() -> bytes:
    return os.environ.get("XA_GUARD_APPROVAL_SECRET", _DEFAULT_SECRET).encode("utf-8")


def args_hash(arguments: dict | None) -> str:
    """对工具入参做 canonical sha256，绑定审批与精确参数。"""
    payload = json.dumps(
        arguments or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _payload(
    *, trace_id: str, tool_name: str, ah: str, approver: str, issued_at: str,
    expires_at: str, request_identity: str = "", tenant_id: str = "",
    provenance_digest: str = "", history_digest: str = "", taint: str = "",
    policy_bundle_sha: str = "", effect_class: str = "", nonce: str = "",
) -> dict:
    return {
        "trace_id": trace_id,
        "tool_name": tool_name,
        "args_hash": ah,
        "approver": approver,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "request_identity": request_identity,
        "tenant_id": tenant_id,
        "provenance_digest": provenance_digest,
        "history_digest": history_digest,
        "taint": taint,
        "policy_bundle_sha": policy_bundle_sha,
        "effect_class": effect_class,
        "nonce": nonce,
    }


def _sign(payload: dict) -> str:
    msg = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hmac.new(_secret(), msg, hashlib.sha256).hexdigest()


def issue_approval(
    *,
    trace_id: str,
    tool_name: str,
    arguments: dict | None,
    approver: str,
    reason: str = "",
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    request_identity: str = "",
    tenant_id: str = "",
    provenance_digest: str = "",
    history_digest: str = "",
    taint: str = "",
    policy_bundle_sha: str = "",
    effect_class: str = "",
    nonce: str | None = None,
) -> Approval:
    """在人工 approve 时签发令牌。"""
    if ttl_seconds <= 0 or ttl_seconds > MAX_APPROVAL_TTL_SECONDS:
        raise ValueError(
            f"approval ttl_seconds must be in 1..{MAX_APPROVAL_TTL_SECONDS}"
        )
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=ttl_seconds)
    ah = args_hash(arguments)
    issued_at = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    expires_at = exp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    nonce = nonce or uuid.uuid4().hex
    token = _sign(_payload(
        trace_id=trace_id, tool_name=tool_name, ah=ah,
        approver=approver, issued_at=issued_at, expires_at=expires_at,
        request_identity=request_identity, tenant_id=tenant_id,
        provenance_digest=provenance_digest, history_digest=history_digest,
        taint=taint, policy_bundle_sha=policy_bundle_sha,
        effect_class=effect_class, nonce=nonce,
    ))
    return Approval(
        approver=approver,
        reason=reason,
        args_hash=ah,
        issued_at=issued_at,
        expires_at=expires_at,
        request_identity=request_identity,
        tenant_id=tenant_id,
        provenance_digest=provenance_digest,
        history_digest=history_digest,
        taint=taint,
        policy_bundle_sha=policy_bundle_sha,
        effect_class=effect_class,
        nonce=nonce,
        token=token,
    )


def verify_approval(
    approval: Approval | None,
    *,
    trace_id: str,
    tool_name: str,
    arguments: dict | None,
    now: datetime | None = None,
    request_identity: str = "",
    tenant_id: str = "",
    provenance_digest: str = "",
    history_digest: str = "",
    taint: str = "",
    policy_bundle_sha: str = "",
    effect_class: str = "",
) -> tuple[bool, str]:
    """执行前验签：返回 (是否有效, 原因)。

    任一条件不满足即拒绝：缺令牌 / 参数失配 / 签名错误 / 过期。
    """
    if approval is None or not approval.token:
        return False, "missing_approval_token"
    ah = args_hash(arguments)
    if not hmac.compare_digest(ah, approval.args_hash or ""):
        return False, "args_hash_mismatch"
    bindings = {
        "request_identity": request_identity,
        "tenant_id": tenant_id,
        "provenance_digest": provenance_digest,
        "history_digest": history_digest,
        "taint": taint,
        "policy_bundle_sha": policy_bundle_sha,
        "effect_class": effect_class,
    }
    for field, current in bindings.items():
        bound = getattr(approval, field, "")
        # A non-empty signed binding must always be supplied and match at resume.
        if bound and not hmac.compare_digest(str(bound), str(current)):
            return False, f"{field}_mismatch"
    expected = _sign(_payload(
        trace_id=trace_id, tool_name=tool_name, ah=approval.args_hash,
        approver=approval.approver, issued_at=approval.issued_at, expires_at=approval.expires_at,
        request_identity=approval.request_identity, tenant_id=approval.tenant_id,
        provenance_digest=approval.provenance_digest, history_digest=approval.history_digest,
        taint=approval.taint, policy_bundle_sha=approval.policy_bundle_sha,
        effect_class=approval.effect_class, nonce=approval.nonce,
    ))
    if not hmac.compare_digest(expected, approval.token):
        return False, "bad_signature"
    try:
        exp = datetime.strptime(approval.expires_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False, "bad_expiry"
    if (now or datetime.now(timezone.utc)) > exp:
        return False, "expired"
    return True, "ok"


def verify_and_consume_approval(
    approval: Approval | None,
    *,
    trace_id: str,
    tool_name: str,
    arguments: dict | None,
    now: datetime | None = None,
    request_identity: str = "",
    tenant_id: str = "",
    provenance_digest: str = "",
    history_digest: str = "",
    taint: str = "",
    policy_bundle_sha: str = "",
    effect_class: str = "",
) -> tuple[bool, str]:
    """验签并把 approval token 标记为已消费，防止进程内重放执行。

    这是 L3 原型级的执行闸门：同一 token 在当前进程内只能通过一次。
    多实例/重启后的全局防重放需要外部审批存储或审计索引配合。
    """
    checked_at = now or datetime.now(timezone.utc)
    ok, why = verify_approval(
        approval,
        trace_id=trace_id,
        tool_name=tool_name,
        arguments=arguments,
        now=checked_at,
        request_identity=request_identity,
        tenant_id=tenant_id,
        provenance_digest=provenance_digest,
        history_digest=history_digest,
        taint=taint,
        policy_bundle_sha=policy_bundle_sha,
        effect_class=effect_class,
    )
    if not ok:
        return False, why
    assert approval is not None  # for type checkers; verify_approval already proved it

    try:
        exp = datetime.strptime(approval.expires_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False, "bad_expiry"

    with _CONSUMED_LOCK:
        expired = [token for token, expires_at in _CONSUMED_TOKENS.items() if expires_at <= checked_at]
        for token in expired:
            _CONSUMED_TOKENS.pop(token, None)
        if approval.token in _CONSUMED_TOKENS:
            return False, "approval_token_replay"
        _CONSUMED_TOKENS[approval.token] = exp
    return True, "ok"
