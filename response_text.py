"""Pull the assistant's final answer out of a LangGraph result."""

from __future__ import annotations

EMPTY_RESPONSE = "I could not produce a response for that query."
_HIDDEN_BLOCK_TYPES = {"reasoning", "thinking"}


def _block_type(block: object) -> str:
    if isinstance(block, dict):
        return str(block.get("type") or "")
    return str(getattr(block, "type", "") or "")


def _block_text(block: object) -> str:
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        text = block.get("text")
    else:
        text = getattr(block, "text", None)
    return text if isinstance(text, str) else ""


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if _block_type(block) in _HIDDEN_BLOCK_TYPES:
                continue
            text = _block_text(block).strip()
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _reasoning_reply(message: object) -> str:
    """Last line of the thinking channel, used only when the visible reply is empty."""
    if isinstance(message, dict):
        kwargs = message.get("additional_kwargs") or {}
    else:
        kwargs = getattr(message, "additional_kwargs", None) or {}
    reasoning = kwargs.get("reasoning_content")
    if not isinstance(reasoning, str):
        return ""
    lines = [line.strip() for line in reasoning.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _message_role(message: object) -> str:
    role = getattr(message, "type", None) or getattr(message, "role", None)
    if role is None and isinstance(message, dict):
        role = message.get("type") or message.get("role")
    return str(role or "")


def _message_content(message: object) -> object:
    if isinstance(message, dict):
        return message.get("content")
    return getattr(message, "content", None)


def extract_response(result: object) -> str:
    """Return the last assistant message that contains text."""
    messages = []
    if isinstance(result, dict):
        messages = result.get("messages") or []
    else:
        messages = getattr(result, "messages", None) or []
    for message in reversed(list(messages)):
        role = _message_role(message)
        if role not in {"ai", "assistant", "AIMessage", "AIMessageChunk"}:
            continue
        text = _content_text(_message_content(message)) or _reasoning_reply(message)
        if text:
            return text
    return EMPTY_RESPONSE
