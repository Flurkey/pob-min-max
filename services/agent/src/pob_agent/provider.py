"""Model providers.

Tests use FakeProvider. Live vendors can be described as an HTTP request, but
nothing in this module sends one. API keys are arguments, never files in the repo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pob_agent.errors import ProviderError

LIVE_KINDS = ("openai", "openai-compatible", "anthropic", "gemini", "ollama")

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "ollama": "http://127.0.0.1:11434",
}


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str


@dataclass(frozen=True)
class ProviderMessage:
    role: str
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class ProviderTurn:
    content: str
    tool_calls: tuple[ToolCall, ...] = ()


class ModelProvider(Protocol):
    kind: str

    def complete(self, messages: list[ProviderMessage], tools: list[dict]) -> ProviderTurn:
        """Next assistant turn. Character stats arrive only as earlier tool results."""


@dataclass
class FakeProvider:
    """Scripted turns. It has no calculator and no game data."""

    script: list[ProviderTurn]
    kind: str = "fake"
    seen: list[list[ProviderMessage]] = field(default_factory=list)

    def complete(self, messages: list[ProviderMessage], tools: list[dict]) -> ProviderTurn:
        self.seen.append(list(messages))
        if not self.script:
            return ProviderTurn(content="")
        return self.script.pop(0)


@dataclass(frozen=True)
class ProviderSpec:
    kind: str
    model: str
    base_url: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in LIVE_KINDS:
            raise ProviderError(f"Unknown provider {self.kind}.")
        if self.kind == "openai-compatible" and not self.base_url:
            raise ProviderError("An OpenAI-compatible provider needs a base URL.")


def render_tools(kind: str, tools: list[dict]) -> list[dict]:
    if kind not in LIVE_KINDS and kind != "fake":
        raise ProviderError(f"Unknown provider {kind}.")
    if kind in {"openai", "openai-compatible", "ollama", "fake"}:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in tools
        ]
    if kind == "anthropic":
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["parameters"],
            }
            for tool in tools
        ]
    return [
        {
            "functionDeclarations": [
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                }
                for tool in tools
            ]
        }
    ]


def build_http_request(
    spec: ProviderSpec,
    messages: list[ProviderMessage],
    tools: list[dict],
    api_key: str | None,
) -> dict:
    """Describe one vendor request. This function does not send it."""
    base = (spec.base_url or DEFAULT_BASE_URLS[spec.kind]).rstrip("/")
    rendered = render_tools(spec.kind, tools)
    if spec.kind in {"openai", "openai-compatible"}:
        _require_key(api_key)
        return {
            "method": "POST",
            "url": f"{base}/chat/completions",
            "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            "json": {
                "model": spec.model,
                "messages": _openai_messages(messages),
                "tools": rendered,
            },
        }
    if spec.kind == "anthropic":
        _require_key(api_key)
        return {
            "method": "POST",
            "url": f"{base}/v1/messages",
            "headers": {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            "json": {
                "model": spec.model,
                "max_tokens": 1024,
                "tools": rendered,
                "messages": _anthropic_messages(messages),
            },
        }
    if spec.kind == "gemini":
        _require_key(api_key)
        return {
            "method": "POST",
            "url": f"{base}/v1beta/models/{spec.model}:generateContent",
            "headers": {"Content-Type": "application/json", "x-goog-api-key": api_key},
            "json": {"contents": _gemini_contents(messages), "tools": rendered},
        }
    return {
        "method": "POST",
        "url": f"{base}/api/chat",
        "headers": {"Content-Type": "application/json"},
        "json": {
            "model": spec.model,
            "messages": _openai_messages(messages),
            "tools": rendered,
            "stream": False,
        },
    }


class LiveProvider:
    """A named vendor. complete() sends only through an injected transport.

    With no transport this process refuses the call. It does not fall back to a
    local socket or a paid API.
    """

    def __init__(self, spec: ProviderSpec, *, api_key: str | None = None, transport=None):
        self.spec = spec
        self.kind = spec.kind
        self._api_key = api_key
        self._transport = transport

    def complete(self, messages: list[ProviderMessage], tools: list[dict]) -> ProviderTurn:
        if self._transport is None:
            raise ProviderError(
                "Refusing to call a model API. Pass a transport to send this request, "
                "or use a fake provider in tests."
            )
        request = build_http_request(self.spec, messages, tools, self._api_key)
        turn = self._transport(request)
        if not isinstance(turn, ProviderTurn):
            raise ProviderError("The transport must return a ProviderTurn. Vendor payloads are not parsed here.")
        return turn


def _require_key(api_key: str | None) -> None:
    if not api_key:
        raise ProviderError("This provider needs a local API key. None is configured.")


def _openai_messages(messages: list[ProviderMessage]) -> list[dict]:
    rendered = []
    for message in messages:
        if message.role == "tool":
            rendered.append(
                {
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "content": message.content,
                }
            )
            continue
        item: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            item["tool_calls"] = [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
                for call in message.tool_calls
            ]
        rendered.append(item)
    return rendered


def _anthropic_messages(messages: list[ProviderMessage]) -> list[dict]:
    rendered = []
    for message in messages:
        if message.role == "tool":
            rendered.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.tool_call_id,
                            "content": message.content,
                        }
                    ],
                }
            )
            continue
        if message.role == "assistant" and message.tool_calls:
            content: list[dict] = []
            if message.content:
                content.append({"type": "text", "text": message.content})
            for call in message.tool_calls:
                content.append(
                    {
                        "type": "tool_use",
                        "id": call.call_id,
                        "name": call.name,
                        "input": call.arguments,
                    }
                )
            rendered.append({"role": "assistant", "content": content})
            continue
        if message.role == "system":
            continue
        rendered.append({"role": message.role, "content": message.content})
    return rendered


def _gemini_contents(messages: list[ProviderMessage]) -> list[dict]:
    contents = []
    for message in messages:
        role = "model" if message.role == "assistant" else "user"
        if message.role == "tool":
            contents.append(
                {
                    "role": "user",
                    "parts": [{"functionResponse": {"name": message.name, "response": {"content": message.content}}}],
                }
            )
            continue
        parts: list[dict] = []
        if message.content:
            parts.append({"text": message.content})
        for call in message.tool_calls:
            parts.append({"functionCall": {"name": call.name, "args": call.arguments}})
        if parts:
            contents.append({"role": role, "parts": parts})
    return contents
