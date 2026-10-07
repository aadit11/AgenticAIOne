"""Pull the assistant's final answer out of a LangGraph result."""

from __future__ import annotations


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part.strip() for part in parts if part and part.strip()).strip()
    return ""


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
        text = _content_text(_message_content(message))
        if text:
            return text
    return "I could not produce a response for that query."
