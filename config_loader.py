"""Load MCP server manifests and prepare the notebook's local files."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SOURCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    url TEXT,
    summary TEXT,
    topic TEXT,
    saved_at TEXT DEFAULT (datetime('now'))
)
"""


def notes_dir() -> Path:
    return Path(os.environ.get("NOTES_DIR", ROOT / "notes")).expanduser().resolve()


def sqlite_path() -> Path:
    return Path(os.environ.get("SQLITE_PATH", ROOT / "data" / "research.db")).expanduser().resolve()


def config_path() -> Path:
    return Path(os.environ.get("MCP_SERVERS_CONFIG", ROOT / "mcp_config.json")).expanduser().resolve()


def ensure_storage() -> tuple[Path, Path]:
    """Create the notes directory and the sources table before MCP servers start."""
    notes = notes_dir()
    database = sqlite_path()
    notes.mkdir(parents=True, exist_ok=True)
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(SOURCES_SCHEMA)
        connection.commit()
    return notes, database


def _substitute(value: str, variables: dict[str, str]) -> str:
    rendered = value
    for key, replacement in variables.items():
        rendered = rendered.replace("${" + key + "}", replacement)
    return rendered


def _merge_env(spec_env: dict[str, str] | None, base_env: dict[str, str]) -> dict[str, str]:
    merged = dict(base_env)
    if spec_env:
        merged.update(spec_env)
    merged.setdefault("NPM_CONFIG_LOGLEVEL", "silent")
    merged.setdefault("NPM_CONFIG_UPDATE_NOTIFIER", "false")
    return merged


def _stdio_command(command: str, args: list[str], platform: str) -> tuple[str, list[str]]:
    # Windows cannot exec npx.cmd through the MCP stdio client. cmd.exe can.
    if platform == "win32" and command.lower() in {"npx", "npm"}:
        return "cmd.exe", ["/d", "/s", "/c", command, *args]
    return command, args


def load_server_config(
    path: Path | None = None,
    *,
    environ: dict[str, str] | None = None,
    platform: str | None = None,
    notes: Path | None = None,
    database: Path | None = None,
) -> tuple[dict[str, dict], list[str]]:
    """Return stdio connection configs and servers that were skipped on purpose."""
    manifest_path = path or config_path()
    source_env = dict(os.environ if environ is None else environ)
    current_platform = platform or os.name
    notes_root = (notes or notes_dir()).resolve()
    database_file = (database or sqlite_path()).resolve()
    variables = {
        "NOTES_DIR": str(notes_root),
        "SQLITE_PATH": str(database_file),
        "TAVILY_API_KEY": source_env.get("TAVILY_API_KEY", ""),
    }

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("mcp_config.json must be an object of server names")

    connections: dict[str, dict] = {}
    skipped: list[str] = []
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            skipped.append(f"{name}: server manifest is not an object")
            continue
        command = _substitute(str(spec.get("command", "")), variables).strip()
        args = [_substitute(str(arg), variables) for arg in spec.get("args", [])]
        if not command:
            skipped.append(f"{name}: manifest has no command")
            continue
        if name == "tavily" and not variables["TAVILY_API_KEY"]:
            skipped.append("tavily: TAVILY_API_KEY is not set")
            continue
        spec_env = spec.get("env") or {}
        resolved_env = {
            key: _substitute(str(value), variables) for key, value in spec_env.items()
        }
        command, args = _stdio_command(command, args, current_platform)
        connections[name] = {
            "transport": spec.get("transport", "stdio"),
            "command": command,
            "args": args,
            "env": _merge_env(resolved_env, source_env),
        }
    return connections, skipped
