import unittest
from types import SimpleNamespace

from mcp_errors import classify_failure, format_failure, malformed_reason
from response_text import extract_response


class ClassifyFailureTests(unittest.TestCase):
    def test_transport_error(self) -> None:
        self.assertEqual(classify_failure(ConnectionError("pipe closed")), "transport")

    def test_malformed_json(self) -> None:
        self.assertEqual(classify_failure(json_error()), "malformed")

    def test_tool_execution_error(self) -> None:
        self.assertEqual(classify_failure(RuntimeError("no such column: topic")), "execution")

    def test_nested_transport_wins(self) -> None:
        grouped = RuntimeError("mcp")
        grouped.exceptions = [RuntimeError("sql"), ConnectionError("reset")]  # type: ignore[attr-defined]
        self.assertEqual(classify_failure(grouped), "transport")


class MalformedResultTests(unittest.TestCase):
    def test_none_is_malformed(self) -> None:
        self.assertIsNotNone(malformed_reason(None))

    def test_text_block_is_usable(self) -> None:
        result = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            isError=False,
        )
        self.assertIsNone(malformed_reason(result))

    def test_server_error_result_is_usable(self) -> None:
        result = SimpleNamespace(content=[], isError=True)
        self.assertIsNone(malformed_reason(result))

    def test_empty_success_is_malformed(self) -> None:
        result = SimpleNamespace(content=[], isError=False)
        self.assertIn("empty", malformed_reason(result) or "")

    def test_block_without_type_is_malformed(self) -> None:
        result = SimpleNamespace(content=[SimpleNamespace(type="", text="x")], isError=False)
        self.assertIsNotNone(malformed_reason(result))


class FormatAndResponseTests(unittest.TestCase):
    def test_format_names_the_failure(self) -> None:
        text = format_failure("transport", "read_file", "connection reset")
        self.assertIn("connection failure", text)
        self.assertIn("read_file", text)

    def test_extracts_last_assistant_text(self) -> None:
        result = {
            "messages": [
                SimpleNamespace(type="human", content="hi"),
                SimpleNamespace(type="ai", content=""),
                SimpleNamespace(type="ai", content="the last answer"),
            ]
        }
        self.assertEqual(extract_response(result), "the last answer")


def json_error() -> Exception:
    try:
        import json

        json.loads("{")
    except json.JSONDecodeError as exc:
        return exc
    raise AssertionError("expected JSONDecodeError")


if __name__ == "__main__":
    unittest.main()
