"""DeepSeek V4 Pro adapter using native OpenAI-compatible tool calls."""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

from kernel.live_agent.models import AgentToolCall, AgentTurn


class ModelAdapter(Protocol):
    def next_turn(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AgentTurn:
        """Return the next native model turn."""


class DeepSeekAdapter:
    """Thin, auditable DeepSeek adapter.

    The SDK is imported lazily so the default deterministic OAR test path does
    not require the optional live-agent dependency.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-pro",
        thinking: str = "disabled",
        temperature: float = 0,
        timeout_seconds: float = 120,
        http_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required for live-agent runs")
        if model != "deepseek-v4-pro":
            raise ValueError("P0 adapter only permits deepseek-v4-pro")
        if thinking not in {"enabled", "disabled"}:
            raise ValueError("thinking must be enabled or disabled")
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover - depends on optional installation
            raise RuntimeError("install xa-guard[live-agent] to use DeepSeekAdapter") from exc
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds, max_retries=0)
        self.model = model
        self.thinking = thinking
        self.temperature = temperature
        self.http_retries = http_retries

    def next_turn(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AgentTurn:
        last_error: BaseException | None = None
        for attempt in range(self.http_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=self.temperature,
                    extra_body={"thinking": {"type": self.thinking}},
                )
                return _parse_response(response, model_requested=self.model)
            except BaseException as exc:  # SDK exposes several transport-specific exception classes
                last_error = exc
                if attempt >= self.http_retries:
                    raise
                time.sleep(2**attempt)
        assert last_error is not None
        raise last_error


def _parse_response(response: Any, *, model_requested: str) -> AgentTurn:
    choice = response.choices[0]
    message = choice.message
    calls: list[AgentToolCall] = []
    for raw_call in message.tool_calls or []:
        raw_arguments = str(raw_call.function.arguments or "")
        parse_error = ""
        try:
            arguments = json.loads(raw_arguments or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            arguments = {}
            parse_error = str(exc)
        calls.append(
            AgentToolCall(
                tool_call_id=str(raw_call.id),
                name=str(raw_call.function.name),
                arguments=arguments,
                raw_arguments=raw_arguments,
                parse_error=parse_error,
            )
        )
    usage: dict[str, Any] = {}
    raw_usage = getattr(response, "usage", None)
    if raw_usage is not None:
        if hasattr(raw_usage, "model_dump"):
            usage = raw_usage.model_dump(exclude_none=True)
        elif isinstance(raw_usage, dict):
            usage = dict(raw_usage)
    return AgentTurn(
        response_id=str(getattr(response, "id", "") or ""),
        model_requested=model_requested,
        model_returned=str(getattr(response, "model", "") or model_requested),
        content=str(message.content or ""),
        tool_calls=tuple(calls),
        finish_reason=str(getattr(choice, "finish_reason", "") or ""),
        system_fingerprint=str(getattr(response, "system_fingerprint", "") or ""),
        usage=usage,
    )


def openai_tools(surface: Any, tool_names: tuple[str, ...]) -> list[dict[str, Any]]:
    """Convert the selected OAR ToolSurface declarations into function tools."""

    tools: list[dict[str, Any]] = []
    for name in tool_names:
        definition = surface.get(name)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.input_schema,
                    "strict": False,
                },
            }
        )
    return tools
