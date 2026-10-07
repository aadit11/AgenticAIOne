"""Discover and call MCP tools, and keep a bad call from crashing the request."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp.types import CallToolResult, TextContent

from config_loader import load_server_config
from mcp_errors import classify_failure, format_failure, malformed_reason

logger = logging.getLogger(__name__)


def _request_name(request: object) -> str:
    return str(getattr(request, "name", None) or "unknown_tool")


def _error_result(text: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        isError=True,
    )


async def guard_mcp_call(request: object, handler):
    """Interceptor for transport failures, tool errors, and bad payloads.

    Tool execution errors that the server already marks with ``isError`` are
    returned unchanged. The adapter turns those into a tool message.
    """
    tool_name = _request_name(request)
    try:
        result = await handler(request)
    except (asyncio.CancelledError, KeyboardInterrupt):
        raise
    except Exception as exc:
        kind = classify_failure(exc)
        logger.warning("MCP call failed tool=%s kind=%s", tool_name, kind)
        return _error_result(format_failure(kind, tool_name, exc))

    reason = malformed_reason(result)
    if reason:
        logger.warning("MCP malformed response tool=%s", tool_name)
        return _error_result(format_failure("malformed", tool_name, reason))
    return result


async def load_mcp_tools(
    manifest: Path | None = None,
) -> tuple[list, list[str], list[MultiServerMCPClient]]:
    """Run tools/list on each server. One dead server does not drop the others."""
    connections, skipped = load_server_config(manifest)
    tools: list = []
    failures = list(skipped)
    clients: list[MultiServerMCPClient] = []

    for name, connection in connections.items():
        client = MultiServerMCPClient(
            {name: connection},
            tool_interceptors=[guard_mcp_call],
            tool_name_prefix=True,
        )
        try:
            discovered = await client.get_tools()
        except Exception as exc:
            logger.warning("MCP discovery failed server=%s", name, exc_info=True)
            failures.append(f"{name}: {exc}")
            continue
        if not discovered:
            failures.append(f"{name}: tools/list returned no tools")
            continue
        tools.extend(discovered)
        clients.append(client)
        logger.info(
            "MCP server %s tools: %s",
            name,
            ", ".join(tool.name for tool in discovered),
        )
    return tools, failures, clients
