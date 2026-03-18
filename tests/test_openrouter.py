import json
import unittest
from unittest.mock import patch

import src.llm_utils.openrouter as openrouter


class ParseJsonFieldsTests(unittest.TestCase):
    def test_pure_json(self) -> None:
        content = json.dumps({"reasoning": "think", "shell_command": "id"})
        result = openrouter._parse_json_fields(content, ["reasoning", "shell_command"])
        self.assertIsNotNone(result)
        self.assertEqual(result["reasoning"], "think")
        self.assertEqual(result["shell_command"], "id")

    def test_json_in_code_block(self) -> None:
        content = '```json\n{"reasoning": "r", "shell_command": "ls"}\n```'
        result = openrouter._parse_json_fields(content, ["reasoning", "shell_command"])
        self.assertIsNotNone(result)
        self.assertEqual(result["shell_command"], "ls")

    def test_missing_reasoning_returns_none(self) -> None:
        content = json.dumps({"shell_command": "id"})
        result = openrouter._parse_json_fields(content, ["reasoning", "shell_command"])
        self.assertIsNone(result)

    def test_extra_fields_ignored(self) -> None:
        content = json.dumps({"reasoning": "r", "shell_command": "id", "stdin_input": "pw"})
        result = openrouter._parse_json_fields(content, ["reasoning", "shell_command", "stdin_input"])
        self.assertIsNotNone(result)
        self.assertEqual(result["stdin_input"], "pw")

    def test_garbage_returns_none(self) -> None:
        result = openrouter._parse_json_fields("not json at all", ["reasoning", "shell_command"])
        self.assertIsNone(result)

    def test_pty_fields(self) -> None:
        content = json.dumps({"reasoning": "r", "shell_command": "", "stdin_input": "yes"})
        result = openrouter._parse_json_fields(content, ["reasoning", "shell_command", "stdin_input"])
        self.assertIsNotNone(result)
        self.assertEqual(result["stdin_input"], "yes")
        self.assertEqual(result["shell_command"], "")


class OpenRouterProtocolTests(unittest.TestCase):
    @patch.object(openrouter, "_call_openrouter_api")
    def test_call_openrouter_protocol_handles_null_content(self, call_api_mock) -> None:
        call_api_mock.return_value = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "reasoning": "separate reasoning",
                    }
                }
            ],
            "usage": {"total_tokens": 7},
        }

        reasoning, protocol, usage = openrouter.call_openrouter_protocol(
            messages=[],
            model_name="openai/gpt-5.3-codex",
        )

        self.assertEqual(reasoning, "separate reasoning")
        self.assertEqual(protocol, "")
        self.assertEqual(usage, {"total_tokens": 7})


class OpenRouterPtyTests(unittest.TestCase):
    @patch.object(openrouter, "_call_openrouter_api")
    def test_call_openrouter_with_history_pty_parses_stdin_input(self, call_api_mock) -> None:
        call_api_mock.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "reasoning": "enter password",
                            "shell_command": "",
                            "stdin_input": "secret123",
                        }),
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        reasoning, shell_command, stdin_input, usage, _ext_reasoning = (
            openrouter.call_openrouter_with_history_pty(
                messages=[],
                model_name="openai/gpt-5.3-codex",
            )
        )

        self.assertEqual(reasoning, "enter password")
        self.assertEqual(shell_command, "")
        self.assertEqual(stdin_input, "secret123")
        self.assertEqual(usage["total_tokens"], 15)
