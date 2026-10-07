"""LangGraph research agent. Session memory is MemorySaver, keyed by thread id."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError

from config_loader import ensure_storage
from mcp_client import load_mcp_tools
from response_text import extract_response

logger = logging.getLogger(__name__)

RECURSION_LIMIT = 20

SYSTEM_PROMPT = """You are a research notebook agent. You look things up, save markdown notes, and keep a catalog of sources.

Three MCP servers are connected:
- filesystem: read and write markdown notes. Stay inside the notes directory ({notes_dir}).
- tavily: search the web for current facts, papers, docs, and sources.
- sqlite: the sources catalog in the local database. The table already exists:
  sources(id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT, summary TEXT, topic TEXT, saved_at TEXT)
  Call sqlite_read_query only with a SELECT. Call sqlite_write_query only with one INSERT, UPDATE, or DELETE.
  Insert example: INSERT INTO sources (title, url, summary, topic) VALUES ('Title', 'https://example.com', 'one sentence', 'topic');
  List example: SELECT id, title, url, summary, topic, saved_at FROM sources ORDER BY id;

Decide from the meaning of the question:
- Definitions, explanations, and questions about this conversation need no tool. Answer from your knowledge and this session's history.
- Current facts, papers, and "search" or "find sources" questions use tavily.
- Saving, reading, listing, or editing a note uses filesystem.
- "What have I saved?", "list my sources", and "record this source" must use sqlite. Do not answer those from memory.
- If the user asks you to find something and keep it, do all three steps before the final answer: tavily search, filesystem write, then sqlite_write_query to insert one sources row. Do not stop after the file write.
- If a tool result says a server is unavailable, a tool failed, or a response could not be parsed, say that plainly. Never invent file contents, search hits, or database rows.
- "That", "the last one", and "what did I ask" refer to this session's earlier turns.

Discovered tools:
{tool_catalog}

Unavailable servers:
{unavailable}
"""


@dataclass
class ResearchAgent:
    agent: object
    checkpointer: MemorySaver
    tool_names: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    clients: list = field(default_factory=list)


def build_model():
    """Use the NVIDIA NIM client when NVIDIA_API_KEY is set, otherwise OpenAI."""
    nvidia_key = os.environ.get("NVIDIA_API_KEY")
    if nvidia_key:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        # Same client settings as the NIM sample for this key.
        return ChatNVIDIA(
            model=os.environ.get(
                "NVIDIA_MODEL",
                "nvidia/nemotron-3.5-lightning-30b-a3b",
            ),
            api_key=nvidia_key,
            temperature=1,
            top_p=0.95,
            max_tokens=16384,
            reasoning_budget=16384,
            chat_template_kwargs={"enable_thinking": True},
        )

    from langchain_openai import ChatOpenAI

    model_name = os.environ.get("OPENAI_MODEL", "gpt-5")
    kwargs: dict = {
        "model": model_name,
        "api_key": os.environ["OPENAI_API_KEY"],
    }
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def render_prompt(tools: list, unavailable: list[str], notes_dir: str) -> str:
    if tools:
        catalog = "\n".join(f"- {tool.name}: {tool.description}" for tool in tools)
    else:
        catalog = "- none"
    skipped = "\n".join(f"- {item}" for item in unavailable) if unavailable else "- none"
    return SYSTEM_PROMPT.format(
        notes_dir=notes_dir,
        tool_catalog=catalog,
        unavailable=skipped,
    )


async def build_agent() -> ResearchAgent:
    notes, _database = ensure_storage()
    tools, unavailable, clients = await load_mcp_tools()
    if unavailable:
        logger.warning("MCP servers unavailable: %s", "; ".join(unavailable))
    checkpointer = MemorySaver()
    agent = create_agent(
        model=build_model(),
        tools=tools,
        system_prompt=render_prompt(tools, unavailable, str(notes)),
        checkpointer=checkpointer,
    )
    return ResearchAgent(
        agent=agent,
        checkpointer=checkpointer,
        tool_names=[tool.name for tool in tools],
        unavailable=unavailable,
        clients=clients,
    )


async def ask(runtime: ResearchAgent, query: str, session_id: str) -> str:
    """Run one turn. MemorySaver reloads history for this session_id."""
    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": RECURSION_LIMIT,
    }
    try:
        result = await runtime.agent.ainvoke(
            {"messages": [{"role": "user", "content": query}]},
            config,
        )
    except GraphRecursionError:
        logger.warning("tool loop hit recursion_limit session=%s", session_id)
        return (
            "I stopped because the tool loop ran too long. "
            "Ask me to continue with one smaller step."
        )
    return extract_response(result)
