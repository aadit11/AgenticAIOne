"""Classify MCP failures so the agent can recover instead of crashing."""

from __future__ import annotations

TRANSPORT_MARKERS = (
    "connection",
    "closed",
    "broken pipe",
    "brokenresource",
    "session",
    "transport",
    "eof",
    "stdio",
    "not found",
    "filenotfound",
    "winerror",
    "timeout",
    "reset",
    "refused",
    "unavailable",
    "spawn",
)

MALFORMED_MARKERS = (
    "json",
    "decode",
    "validation",
    "schema",
    "parse",
    "malformed",
    "invalid response",
    "content type",
    "unexpected token",
)


def classify_failure(exc: BaseException) -> str:
    """Map an exception to transport, malformed, or tool-execution failure."""
    nested = getattr(exc, "exceptions", None)
    if nested:
        kinds = {classify_failure(item) for item in nested}
        if "transport" in kinds:
            return "transport"
        if "malformed" in kinds:
            return "malformed"
        return "execution"

    blob = f"{type(exc).__name__} {exc}".lower()
    if any(marker in blob for marker in MALFORMED_MARKERS):
        return "malformed"
    if any(marker in blob for marker in TRANSPORT_MARKERS):
        return "transport"
    return "execution"


def format_failure(kind: str, tool_name: str, detail: object) -> str:
    """Build the text the model should see for a failed MCP call."""
    detail_text = str(detail).strip() or kind
    if kind == "transport":
        return (
            f"MCP connection failure while calling {tool_name}: {detail_text}. "
            "The server was unavailable. Do not invent this tool's result."
        )
    if kind == "malformed":
        return (
            f"MCP tool {tool_name} returned a malformed response: {detail_text}. "
            "Do not treat it as data."
        )
    return (
        f"MCP tool {tool_name} failed during execution: {detail_text}. "
        "Explain the failure instead of inventing a result."
    )


def malformed_reason(result: object) -> str | None:
    """Return why an MCP tool result cannot be used, or None if it is usable.

    Tool execution errors (``isError``) are usable: the server described the
    failure, and the adapter turns that into a tool message.
    """
    if result is None:
        return "the server returned no result"
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
        is_error = bool(result.get("isError") or result.get("is_error"))
    else:
        is_error = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
    if content is None:
        return "the result has no content field"
    if isinstance(content, str):
        return None if content.strip() or is_error else "the server returned empty text"
    if not isinstance(content, list):
        return "content is not a list of MCP content blocks"
    if len(content) == 0:
        return None if is_error else "the server returned an empty content list"
    for block in content:
        if isinstance(block, str):
            continue
        if isinstance(block, dict):
            block_type = block.get("type")
            text = block.get("text")
        else:
            block_type = getattr(block, "type", None)
            text = getattr(block, "text", None)
        if not isinstance(block_type, str) or not block_type:
            return "a content block is missing its type"
        if block_type == "text" and not isinstance(text, str):
            return "a text block has no text"
    return None
