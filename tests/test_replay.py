import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import scripts.replay_openrouter_messages as replay_script
import src.chap_utils.protocol_generator as protocol_generator
from src.utils.replay import list_replayable_model_calls, rebuild_model_call_messages
from src.utils.state_manager import (
    append_session_event,
    build_assistant_message,
    create_session,
)


class ReplayHelperTests(unittest.TestCase):
    def test_rebuild_main_agent_call_messages_matches_saved_history(self) -> None:
        session = create_session(model="openai/gpt-5.3-codex")
        initial_system = {"role": "system", "content": "system"}
        initial_user = {"role": "user", "content": "user"}
        command_message = build_assistant_message("enumerate", "id")
        result_message = {
            "role": "user",
            "content": "Command executed with exit code 0. Output:\nuid=0",
        }

        append_session_event(
            session,
            stream="main_agent",
            tag="initial_system_prompt",
            message=initial_system,
            iteration=0,
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="initial_user_prompt",
            message=initial_user,
            iteration=0,
        )
        assistant_event = append_session_event(
            session,
            stream="main_agent",
            tag="assistant_command",
            message=command_message,
            parsed={"reasoning": "enumerate", "shell_command": "id"},
            iteration=0,
            metadata={"included_in_history": True},
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="framework_command_result",
            message=result_message,
            parsed={"exit_code": 0, "output": "uid=0"},
            iteration=0,
            metadata={"assistant_event_index": assistant_event["event_index"], "included_in_history": True},
        )
        exit_event = append_session_event(
            session,
            stream="main_agent",
            tag="assistant_exit",
            message=build_assistant_message("done", "exit"),
            parsed={"reasoning": "done", "shell_command": "exit"},
            iteration=1,
            metadata={"included_in_history": True},
        )

        calls = list_replayable_model_calls(session)

        self.assertEqual(
            [call["tag"] for call in calls],
            ["assistant_command", "assistant_exit"],
        )
        self.assertEqual(
            rebuild_model_call_messages(session, event_index=exit_event["event_index"]),
            [initial_system, initial_user, command_message, result_message],
        )

    @patch.object(protocol_generator, "call_openrouter_protocol")
    def test_rebuild_protocol_generation_call_matches_runtime_messages(
        self,
        call_protocol_mock,
    ) -> None:
        call_protocol_mock.return_value = (
            "summarize",
            "## Current Access\nroot shell",
            {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        )
        session = create_session(model="openai/gpt-5.3-codex", chap_enabled=True)
        session["agent_number"] = 1
        session["relay_protocols"].append(
            {
                "agent_number": 0,
                "protocol_content": "Found port 80",
                "response_event_index": 1,
            }
        )

        runtime_messages = [
            {"role": "system", "content": "relay system"},
            {"role": "user", "content": "relay user"},
            build_assistant_message("enumerate web", "curl http://target"),
            {
                "role": "user",
                "content": "Command executed with exit code 0. Output:\n<html>",
            },
        ]
        append_session_event(
            session,
            stream="main_agent",
            tag="relay_system_prompt",
            message=runtime_messages[0],
            iteration=3,
            agent_number=1,
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="relay_user_prompt",
            message=runtime_messages[1],
            iteration=3,
            agent_number=1,
            metadata={"relay_number": 1},
        )
        assistant_event = append_session_event(
            session,
            stream="main_agent",
            tag="assistant_command",
            message=runtime_messages[2],
            parsed={"reasoning": "enumerate web", "shell_command": "curl http://target"},
            iteration=4,
            agent_number=1,
            metadata={"included_in_history": True},
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="framework_command_result",
            message=runtime_messages[3],
            parsed={"exit_code": 0, "output": "<html>"},
            iteration=4,
            agent_number=1,
            metadata={"assistant_event_index": assistant_event["event_index"], "included_in_history": True},
        )

        protocol_generator.generate_relay_protocol(
            messages=runtime_messages,
            session=session,
            model_name="openai/gpt-5.3-codex",
            current_iteration=5,
        )

        calls = list_replayable_model_calls(session)
        protocol_call = calls[-1]

        self.assertEqual(protocol_call["stream"], "protocol_generation")
        self.assertEqual(
            rebuild_model_call_messages(session, event_index=protocol_call["event_index"]),
            call_protocol_mock.call_args.kwargs["messages"],
        )


class ReplayScriptTests(unittest.TestCase):
    def test_script_replays_messages_for_call_index(self) -> None:
        session = create_session(model="openai/gpt-5.3-codex")
        initial_system = {"role": "system", "content": "system"}
        initial_user = {"role": "user", "content": "user"}

        append_session_event(
            session,
            stream="main_agent",
            tag="initial_system_prompt",
            message=initial_system,
            iteration=0,
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="initial_user_prompt",
            message=initial_user,
            iteration=0,
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="assistant_exit",
            message=build_assistant_message("done", "exit"),
            parsed={"reasoning": "done", "shell_command": "exit"},
            iteration=0,
            metadata={"included_in_history": True},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = os.path.join(temp_dir, "session.json")
            with open(session_path, "w", encoding="utf-8") as handle:
                json.dump(session, handle)

            stdout = io.StringIO()
            with (
                patch(
                    "sys.argv",
                    [
                        "replay_openrouter_messages.py",
                        session_path,
                        "--call-index",
                        "0",
                        "--messages-only",
                    ],
                ),
                redirect_stdout(stdout),
            ):
                replay_script.main()

        self.assertEqual(
            json.loads(stdout.getvalue()),
            [initial_system, initial_user],
        )


if __name__ == "__main__":
    unittest.main()
