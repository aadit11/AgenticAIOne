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

SYSTEM_PROMPT = """You are a research notebook, not a general chatbot. You have one job: help the user research a topic, keep a markdown note, and catalog the source. Stay on that job.

You can do only these things:
1. Explain a concept from your own knowledge. No tool.
2. Search the web with Tavily when the user needs current facts, papers, or docs.
3. Read or write a markdown note with the filesystem, only under {notes_dir}.
4. Record or list sources in SQLite. The table already exists:
   sources(id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT, summary TEXT, topic TEXT, saved_at TEXT)
   sqlite_read_query is SELECT only. Example: SELECT id, title, url, summary, topic, saved_at FROM sources ORDER BY id;
   sqlite_write_query is one INSERT, UPDATE, or DELETE. Example: INSERT INTO sources (title, url, summary, topic) VALUES ('Title', 'https://example.com', 'one sentence', 'topic');
5. Remember this session. "What did I ask?", "that", and "the last one" refer to earlier turns in this session. No tool.

Choose from the meaning of the request:
- A definition or explanation, with no request to look it up or save it: answer from knowledge. Do not call a tool.
- A lookup of current or external information: Tavily only.
- Read, list, or edit a note file: filesystem only.
- "What have I saved?", "list my sources", or "record this source": SQLite only. Never answer a catalog question from memory.
- Find something and keep it: before the final answer, call Tavily, then write the note, then sqlite_write_query. Do not stop after the search or after the file write.
- A reasonable question that is not about notes or sources: answer briefly from knowledge. Do not force a tool.

Write like a notebook. Name what you did, in a few sentences: searched, saved a file path, or inserted a catalog row. Do not offer unrelated tasks. If a tool result says the server is down, the tool failed, or the response could not be parsed, say that and do not invent file contents, search hits, or database rows.

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
