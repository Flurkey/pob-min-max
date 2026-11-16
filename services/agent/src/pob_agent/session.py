"""Run a provider's tool calls against the engine and the knowledge import."""

from __future__ import annotations

import json

from pob_agent.errors import AgentError
from pob_agent.provider import ModelProvider, ProviderMessage
from pob_agent.tools import Toolset
from pob_engine.errors import EngineError
from pob_knowledge.errors import KnowledgeError

ENGINE_CALCULATION_TOOLS = {
    "import_build",
    "get_build_state",
    "calculate_build",
    "equip_item",
    "allocate_passives",
}
KNOWLEDGE_LIST_KEYS = ("items", "gems", "nodes")


class AgentSession:
    def __init__(self, tools: Toolset, provider: ModelProvider):
        self.tools = tools
        self.provider = provider

    def run(self, prompt: str, *, max_steps: int = 8) -> dict:
        if max_steps < 1:
            raise AgentError("max_steps must be at least 1.")
        messages = [ProviderMessage(role="user", content=prompt)]
        steps: list[dict] = []
        for _ in range(max_steps):
            turn = self.provider.complete(messages, self.tools.schemas())
            if not turn.tool_calls:
                return {"message": turn.content, "steps": steps}
            messages.append(
                ProviderMessage(role="assistant", content=turn.content, tool_calls=tuple(turn.tool_calls))
            )
            for call in turn.tool_calls:
                try:
                    result = self.tools.invoke(call.name, call.arguments)
                    _require_provenance(call.name, result)
                    payload = result
                    ok = True
                except (AgentError, EngineError, KnowledgeError, KeyError) as exc:
                    payload = {"error": str(exc)}
                    ok = False
                steps.append(
                    {
                        "tool": call.name,
                        "arguments": call.arguments,
                        "ok": ok,
                        "result": payload,
                    }
                )
                messages.append(
                    ProviderMessage(
                        role="tool",
                        content=json.dumps(payload),
                        tool_call_id=call.call_id,
                        name=call.name,
                    )
                )
        return {"message": None, "steps": steps, "stopped": "max_steps"}


def _require_provenance(name: str, result: dict) -> None:
    if name in ENGINE_CALCULATION_TOOLS:
        calculation = result.get("calculation")
        if not isinstance(calculation, dict) or calculation.get("source") != "pob-engine":
            raise AgentError(f"{name} did not return an engine calculation.")
        if "stats" not in calculation:
            raise AgentError(f"{name} returned an engine envelope with no stat table.")
        if name in {"equip_item", "allocate_passives"}:
            edited = (result.get("revision") or {}).get("id")
            copied_from = result.get("copiedFromRevisionId")
            working_copy = result.get("workingCopyRevisionId")
            if not copied_from or not working_copy or not edited:
                raise AgentError(f"{name} did not report the copy it edited.")
            if len({copied_from, working_copy, edited}) < 3:
                raise AgentError(f"{name} edited the caller's revision instead of a copy.")
        return
    if name == "compare_builds":
        if result.get("source") != "pob-engine":
            raise AgentError("compare_builds did not return an engine comparison.")
        return
    if name == "export_build":
        xml = result.get("xml")
        if result.get("source") != "pob-engine" or not isinstance(xml, str) or "<PathOfBuilding" not in xml:
            raise AgentError("export_build did not return engine XML.")
        return
    if result.get("source") != "pob-knowledge":
        raise AgentError(f"{name} did not return imported game data.")
    if "nodeIds" in result:
        if not result.get("sourceCommit"):
            raise AgentError(f"{name} returned a path with no source commit.")
        return
    for key in KNOWLEDGE_LIST_KEYS:
        for record in result.get(key) or []:
            if not record.get("sourceCommit"):
                raise AgentError(f"{name} returned a record with no source commit.")
