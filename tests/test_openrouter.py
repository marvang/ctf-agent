import unittest
from unittest.mock import MagicMock, patch

import src.llm_utils.openrouter as openrouter


class OpenRouterProtocolTests(unittest.TestCase):
    @patch.object(openrouter, "_call_openrouter_api")
    def test_call_openrouter_protocol_handles_null_content(self, call_api_mock: MagicMock) -> None:
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
