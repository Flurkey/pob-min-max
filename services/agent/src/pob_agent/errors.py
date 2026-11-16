class AgentError(RuntimeError):
    """A tool call was refused, or a result did not come from the engine or the import."""


class ToolArgumentError(AgentError):
    """The arguments do not match the tool's typed schema."""


class ProviderError(AgentError):
    """A model provider cannot be used for this call."""
