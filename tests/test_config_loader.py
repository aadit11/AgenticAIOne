import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from config_loader import ensure_storage, load_server_config


class ConfigLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.notes = self.root / "notes"
        self.database = self.root / "data" / "research.db"
        self.manifest = self.root / "mcp_config.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "filesystem": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-filesystem", "${NOTES_DIR}"],
                    },
                    "tavily": {
                        "command": "npx",
                        "args": ["-y", "tavily-mcp@latest"],
                        "env": {"TAVILY_API_KEY": "${TAVILY_API_KEY}"},
                    },
                    "sqlite": {
                        "command": "mcp-server-sqlite",
                        "args": ["--db-path", "${SQLITE_PATH}"],
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_skips_tavily_without_a_key(self) -> None:
        connections, skipped = load_server_config(
            self.manifest,
            environ={"PATH": "/usr/bin"},
            platform="posix",
            notes=self.notes,
            database=self.database,
        )
        self.assertIn("filesystem", connections)
        self.assertIn("sqlite", connections)
        self.assertNotIn("tavily", connections)
        self.assertTrue(any(item.startswith("tavily:") for item in skipped))
        self.assertEqual(
            connections["filesystem"]["args"][-1],
            str(self.notes.resolve()),
        )

    def test_windows_wraps_npx(self) -> None:
        connections, _skipped = load_server_config(
            self.manifest,
            environ={"PATH": "C:\\Windows", "TAVILY_API_KEY": "tvly-test"},
            platform="win32",
            notes=self.notes,
            database=self.database,
        )
        self.assertEqual(connections["tavily"]["command"], "cmd.exe")
        self.assertEqual(connections["tavily"]["args"][:4], ["/d", "/s", "/c", "npx"])
        self.assertEqual(connections["tavily"]["env"]["TAVILY_API_KEY"], "tvly-test")
        self.assertIn("PATH", connections["sqlite"]["env"])

    def test_weather_server_needs_no_key(self) -> None:
        manifest = Path(__file__).resolve().parents[1] / "mcp_config.json"
        connections, skipped = load_server_config(
            manifest,
            environ={"PATH": "/usr/bin", "TAVILY_API_KEY": "tvly-test"},
            platform="posix",
            notes=self.notes,
            database=self.database,
        )
        self.assertIn("weather", connections)
        self.assertEqual(connections["weather"]["command"], "npx")
        self.assertIn("weather-open-meteo-mcp@0.1.2", connections["weather"]["args"])
        self.assertFalse(any(item.startswith("weather:") for item in skipped))

    def test_schema_is_created(self) -> None:
        previous_notes = os.environ.get("NOTES_DIR")
        previous_db = os.environ.get("SQLITE_PATH")
        os.environ["NOTES_DIR"] = str(self.notes)
        os.environ["SQLITE_PATH"] = str(self.database)
        try:
            ensure_storage()
        finally:
            if previous_notes is None:
                os.environ.pop("NOTES_DIR", None)
            else:
                os.environ["NOTES_DIR"] = previous_notes
            if previous_db is None:
                os.environ.pop("SQLITE_PATH", None)
            else:
                os.environ["SQLITE_PATH"] = previous_db
        with sqlite3.connect(self.database) as connection:
            columns = connection.execute("PRAGMA table_info(sources)").fetchall()
        self.assertIn("title", [column[1] for column in columns])
        self.assertTrue(self.notes.is_dir())


if __name__ == "__main__":
    unittest.main()
