import io
import unittest
from contextlib import redirect_stdout

from src.utils.session_utils import display_session_summary
from src.utils.state_manager import append_session_event, build_assistant_message, create_session


class SessionSummaryTests(unittest.TestCase):
    def test_display_session_summary_counts_commands_from_events(self) -> None:
        session = create_session(model="openai/gpt-5.3-codex")
        append_session_event(
            session,
            stream="main_agent",
            tag="assistant_command",
            message=build_assistant_message("enumerate", "id"),
            parsed={"reasoning": "enumerate", "shell_command": "id", "extended_reasoning": ""},
            iteration=0,
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="assistant_exit",
            message=build_assistant_message("done", "exit"),
            parsed={"reasoning": "done", "shell_command": "exit", "extended_reasoning": ""},
            iteration=1,
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            display_session_summary(
                session,
                iterations=1,
                elapsed_seconds=5.0,
                selected_model="openai/gpt-5.3-codex",
            )

        self.assertIn("1 iterations | 1 commands", stdout.getvalue())
