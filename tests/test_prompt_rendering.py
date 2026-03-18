import json
import os
import tempfile
import unittest
from unittest.mock import patch

import main
import scripts.run_experiment as run_experiment
import src.chap_utils.protocol_generator as protocol_generator
import src.experiment_utils.main_experiment_agent as experiment_agent
import src.utils.discord_utils.error_messages as error_messages
from src.config.session_runtime import resolve_session_runtime
from src.llm_utils.prompt_builder import build_initial_messages, build_relay_messages
from src.utils.state_manager import (
    append_session_event,
    build_assistant_message,
    build_used_prompts_payload,
    create_session,
    set_session_context,
)


class PromptRenderingTests(unittest.TestCase):
    def test_local_aarch64_initial_prompt(self) -> None:
        messages = build_initial_messages(
            environment_mode="local",
            target_info="10.13.37.5",
            use_chap=False,
            custom_instructions="",
            agent_ips={"eth0": "172.18.0.2"},
            local_arch="aarch64",
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn(
            "CTF target runs in Docker container emulating amd64.",
            messages[0]["content"],
        )
        self.assertIn("Environment: Local Docker challenge", messages[1]["content"])
        self.assertIn("Target IP address: 10.13.37.5", messages[1]["content"])
        self.assertIn("Agent Docker IP (eth0): 172.18.0.2", messages[1]["content"])

    def test_local_amd64_initial_prompt(self) -> None:
        messages = build_initial_messages(
            environment_mode="local",
            target_info="10.13.37.6",
            use_chap=False,
            custom_instructions="Check web first",
            agent_ips={"eth0": "172.18.0.3"},
            local_arch="amd64",
        )

        self.assertIn(
            "Your commands are executed in a Kali Linux container (amd64).",
            messages[0]["content"],
        )
        self.assertNotIn(
            "CTF target runs in Docker container emulating amd64.",
            messages[0]["content"],
        )
        self.assertIn(
            "ADDITIONAL CUSTOM INSTRUCTIONS FROM THE TEAM: Check web first",
            messages[1]["content"],
        )

    def test_remote_prompt_uses_remote_variant_and_chap(self) -> None:
        messages = build_initial_messages(
            environment_mode="htb",
            target_info="10.10.10.10",
            use_chap=True,
            custom_instructions="",
            agent_ips={"eth0": "172.18.0.4", "tun0": "10.10.14.7"},
            local_arch=None,
        )

        self.assertIn(
            "The target is a remote system reached over VPN.",
            messages[0]["content"],
        )
        self.assertIn('TOOL: You can execute the command "relay"', messages[0]["content"])
        self.assertNotIn(
            "CTF target also runs in a container (amd64).",
            messages[0]["content"],
        )
        self.assertNotIn(
            "CTF target runs in Docker container emulating amd64.",
            messages[0]["content"],
        )
        self.assertIn(
            "include the current hypothesis you want to test",
            messages[0]["content"],
        )
        self.assertIn(
            "If an approach fails 4 times on the same vector",
            messages[0]["content"],
        )
        self.assertIn(
            "Do not launch sqlmap, Metasploit, nuclei, or large ffuf/feroxbuster runs",
            messages[0]["content"],
        )
        self.assertIn("Target: Hack The Box", messages[1]["content"])
        self.assertIn("Agent VPN IP (tun0): 10.10.14.7", messages[1]["content"])

    def test_relay_prompt_includes_protocols(self) -> None:
        messages = build_relay_messages(
            session={
                "relay_protocols": [
                    {"agent_number": 0, "protocol_content": "Found port 80."},
                    {"agent_number": 1, "protocol_content": "Got a shell."},
                ]
            },
            environment_mode="private",
            target_info="10.0.0.9",
            custom_instructions="Get both flags",
            agent_ips={"eth0": "172.18.0.5", "tun0": "10.8.0.5"},
            local_arch=None,
        )

        user_content = messages[1]["content"]
        self.assertIn("=== RELAY MISSION ===", user_content)
        self.assertIn("=== TARGET ===", user_content)
        self.assertIn("Target: Private Cyber Range", user_content)
        self.assertIn("=== RELAY PROTOCOLS ===", user_content)
        self.assertIn("=== PROTOCOL 1 - From PENTEST AGENT SHIFT 1 ===", user_content)
        self.assertIn("=== PROTOCOL 2 - From PENTEST AGENT SHIFT 2 ===", user_content)
        self.assertIn("Current Agent: You are Agent 3.", user_content)
        self.assertIn("Custom Instructions: Get both flags", user_content)


class ResultMetadataTests(unittest.TestCase):
    def test_interactive_results_keep_use_amd64_prompt_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session = create_session(model="openai/gpt-5.3-codex")
            session["metrics"]["total_cost"] = 0.0
            session["metrics"]["total_time"] = 1.25
            set_session_context(session, environment_mode="local", target_ip="10.13.37.7")
            append_session_event(
                session,
                stream="main_agent",
                tag="initial_system_prompt",
                message={"role": "system", "content": "system"},
                iteration=0,
            )
            append_session_event(
                session,
                stream="main_agent",
                tag="initial_user_prompt",
                message={"role": "user", "content": "user"},
                iteration=0,
            )
            main.save_interactive_results(
                session=session,
                stopping_reason="agent_exit",
                error_message=None,
                llm_error_details=None,
                relay_count=0,
                iteration=3,
                session_dir=temp_dir,
                selected_model="openai/gpt-5.3-codex",
                environment_mode="local",
                use_chap=False,
                chap_config={},
                local_arch="amd64",
                custom_instructions="",
                challenge_name="vm0",
                target_ip="10.13.37.7",
                timestamp="20260316_120000",
                workspace_dir=temp_dir,
                session_runtime=resolve_session_runtime(None),
            )

            with open(os.path.join(temp_dir, "session_summary.json")) as handle:
                metadata = json.load(handle)["metadata"]

            self.assertTrue(metadata["use_amd64_prompt"])

    def test_interactive_results_keep_used_prompts_legacy_shape_from_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session = create_session(model="openai/gpt-5.3-codex", chap_enabled=True)
            set_session_context(
                session,
                experiment_id="session-1",
                challenge_name="vm0",
                model_name="openai/gpt-5.3-codex",
                chap_enabled=True,
                chap_auto_trigger=True,
                environment_mode="local",
                target_ip="10.13.37.7",
            )
            append_session_event(
                session,
                stream="main_agent",
                tag="initial_system_prompt",
                message={"role": "system", "content": "event system"},
                iteration=0,
            )
            append_session_event(
                session,
                stream="main_agent",
                tag="initial_user_prompt",
                message={"role": "user", "content": "event user"},
                iteration=0,
            )
            append_session_event(
                session,
                stream="protocol_generation",
                tag="protocol_generator_system_prompt_template",
                message={"role": "system", "content": "protocol system"},
                iteration=0,
            )
            append_session_event(
                session,
                stream="main_agent",
                tag="relay_user_prompt",
                message={"role": "user", "content": "relay user"},
                iteration=4,
                metadata={"relay_number": 1},
            )

            main.save_interactive_results(
                session=session,
                stopping_reason="agent_exit",
                error_message=None,
                llm_error_details=None,
                relay_count=1,
                iteration=3,
                session_dir=temp_dir,
                selected_model="openai/gpt-5.3-codex",
                environment_mode="local",
                use_chap=True,
                chap_config={"auto_trigger": True},
                local_arch="amd64",
                custom_instructions="",
                challenge_name="vm0",
                target_ip="10.13.37.7",
                timestamp="20260316_120000",
                workspace_dir=temp_dir,
                session_runtime=resolve_session_runtime(None),
            )

            with open(os.path.join(temp_dir, "used_prompts.json")) as handle:
                payload = json.load(handle)

        self.assertEqual(payload["system_prompt"], "event system")
        self.assertEqual(payload["initial_messages"], [{"role": "user", "content": "event user"}])
        self.assertEqual(payload["protocol_generator_system_prompt"], "protocol system")
        self.assertEqual(
            payload["relay_initial_messages"],
            [{"relay_number": 1, "user_content": "relay user"}],
        )
        self.assertEqual(payload["challenge_name"], "vm0")
        self.assertEqual(payload["environment_mode"], "local")
        self.assertEqual(payload["target_ip"], "10.13.37.7")

    def test_experiment_results_keep_use_amd64_prompt_metadata(self) -> None:
        original_local_arch = run_experiment.LOCAL_ARCH
        try:
            run_experiment.LOCAL_ARCH = "amd64"
            with tempfile.TemporaryDirectory() as temp_dir:
                experiment_dir = os.path.join(temp_dir, "experiment_20260316_120000")
                run_experiment.save_results(
                    results=[],
                    results_dir=temp_dir,
                    session_runtime=resolve_session_runtime(None),
                    experiment_dir=experiment_dir,
                    experiment_timestamp="20260316_120000",
                    termination_reason="completed",
                )

                with open(
                    os.path.join(experiment_dir, "experiment_summary.json"),
                ) as handle:
                    metadata = json.load(handle)["metadata"]

            self.assertTrue(metadata["use_amd64_prompt"])
        finally:
            run_experiment.LOCAL_ARCH = original_local_arch

    def test_experiment_results_keep_used_prompts_legacy_shape_from_events(self) -> None:
        session = create_session(model="openai/gpt-5.3-codex", chap_enabled=True)
        set_session_context(
            session,
            experiment_id="exp-1",
            challenge_name="vm0",
            model_name="openai/gpt-5.3-codex",
            chap_enabled=True,
            chap_auto_trigger=True,
            target_ip="192.168.5.5",
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="initial_system_prompt",
            message={"role": "system", "content": "event system"},
            iteration=0,
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="initial_user_prompt",
            message={"role": "user", "content": "event user"},
            iteration=0,
        )
        append_session_event(
            session,
            stream="protocol_generation",
            tag="protocol_generator_system_prompt_template",
            message={"role": "system", "content": "protocol system"},
            iteration=0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            experiment_dir = os.path.join(temp_dir, "experiment_20260316_120000")
            run_experiment.save_results(
                results=[
                    {
                        "challenge_name": "vm0",
                        "session": session,
                        "flag_captured": None,
                        "iterations": 0,
                        "relay_count": 0,
                        "error": None,
                        "llm_error_details": None,
                        "cost_limit_reached": False,
                        "iteration_limit_reached": False,
                        "stopping_reason": "agent_exit",
                        "total_time": 0.0,
                        "total_cost": 0.0,
                        "mode": "experiment_script",
                        "flag_valid": False,
                        "expected_flags": None,
                    }
                ],
                results_dir=temp_dir,
                session_runtime=resolve_session_runtime(None),
                experiment_dir=experiment_dir,
                experiment_timestamp="20260316_120000",
                termination_reason="completed",
            )

            with open(os.path.join(experiment_dir, "vm0", "used_prompts.json")) as handle:
                payload = json.load(handle)

        self.assertEqual(payload["system_prompt"], "event system")
        self.assertEqual(payload["initial_messages"], [{"role": "user", "content": "event user"}])
        self.assertEqual(payload["protocol_generator_system_prompt"], "protocol system")
        self.assertEqual(payload["challenge_name"], "vm0")


class SessionStateTests(unittest.TestCase):
    def test_create_session_initializes_relay_triggers(self) -> None:
        session = create_session(model="openai/gpt-5.3-codex")

        self.assertEqual(session["relay_triggers"], [])
        self.assertFalse(session["chap_enabled"])

    def test_create_session_stores_chap_enabled_flag(self) -> None:
        session = create_session(model="openai/gpt-5.3-codex", chap_enabled=True)

        self.assertTrue(session["chap_enabled"])

    def test_create_session_initializes_event_log(self) -> None:
        session = create_session(model="openai/gpt-5.3-codex")

        self.assertEqual(session["schema_version"], 2)
        self.assertEqual(session["events"], [])
        self.assertEqual(session["context"], {})

    def test_build_used_prompts_payload_uses_session_chap_enabled_fallback(self) -> None:
        session = create_session(model="openai/gpt-5.3-codex", chap_enabled=True)
        append_session_event(
            session,
            stream="main_agent",
            tag="initial_system_prompt",
            message={"role": "system", "content": "system"},
            iteration=0,
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="initial_user_prompt",
            message={"role": "user", "content": "user"},
            iteration=0,
        )

        payload = build_used_prompts_payload(
            session,
            mode="experiment_script",
            chap_auto_trigger=False,
        )

        self.assertTrue(payload["chap_enabled"])
        self.assertFalse(payload["chap_auto_trigger"])

    def test_build_used_prompts_payload_raises_for_missing_chap_auto_trigger(self) -> None:
        session = create_session(model="openai/gpt-5.3-codex", chap_enabled=True)
        append_session_event(
            session,
            stream="main_agent",
            tag="initial_system_prompt",
            message={"role": "system", "content": "system"},
            iteration=0,
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="initial_user_prompt",
            message={"role": "user", "content": "user"},
            iteration=0,
        )

        with self.assertRaisesRegex(ValueError, "chap_auto_trigger"):
            build_used_prompts_payload(session, mode="experiment_script")

    def test_events_capture_all_turns_including_non_executed(self) -> None:
        session = create_session(model="openai/gpt-5.3-codex")
        assistant_event = append_session_event(
            session,
            stream="main_agent",
            tag="assistant_command",
            message={"role": "assistant", "content": '{"reasoning":"r","shell_command":"id"}'},
            parsed={"reasoning": "r", "shell_command": "id", "extended_reasoning": ""},
            iteration=0,
            usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="framework_command_result",
            message={"role": "user", "content": "Command executed with exit code 0. Output:\nuid=0"},
            parsed={"exit_code": 0, "output": "uid=0"},
            iteration=0,
            metadata={"assistant_event_index": assistant_event["event_index"]},
        )
        append_session_event(
            session,
            stream="main_agent",
            tag="assistant_exit",
            message={"role": "assistant", "content": '{"reasoning":"done","shell_command":"exit"}'},
            parsed={"reasoning": "done", "shell_command": "exit", "extended_reasoning": ""},
            iteration=1,
        )

        self.assertEqual(len(session["events"]), 3)
        self.assertNotIn("commands", session)
        self.assertEqual(session["events"][0]["tag"], "assistant_command")
        self.assertEqual(session["events"][1]["tag"], "framework_command_result")
        self.assertEqual(session["events"][-1]["tag"], "assistant_exit")


class ProtocolGenerationTests(unittest.TestCase):
    @patch.object(protocol_generator, "call_openrouter_protocol")
    def test_generate_relay_protocol_keeps_reasoning_and_logs_compact_events(
        self,
        call_protocol_mock,
    ) -> None:
        call_protocol_mock.return_value = (
            "summarize the foothold",
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

        protocol = protocol_generator.generate_relay_protocol(
            messages=runtime_messages,
            session=session,
            model_name="openai/gpt-5.3-codex",
            current_iteration=5,
        )

        self.assertEqual(protocol["reasoning"], "summarize the foothold")
        self.assertEqual(protocol["protocol_content"], "## Current Access\nroot shell")
        self.assertEqual(
            [event["tag"] for event in session["events"]],
            [
                "relay_system_prompt",
                "relay_user_prompt",
                "assistant_command",
                "framework_command_result",
                "protocol_request_system_prompt",
                "protocol_request_user_prompt",
                "protocol_response",
            ],
        )
        request_user_event = session["events"][-2]
        self.assertEqual(
            request_user_event["message"]["content"],
            "[rebuild via protocol_request_builder_v1]",
        )
        self.assertEqual(
            request_user_event["parsed"]["prior_protocol_count"],
            1,
        )
        rebuilt_messages = protocol_generator.rebuild_protocol_request_messages(
            session,
            request_user_event,
        )
        self.assertEqual(rebuilt_messages, call_protocol_mock.call_args.kwargs["messages"])
        self.assertNotIn("curl http://target", request_user_event["message"]["content"])
        self.assertEqual(
            session["events"][-1]["parsed"],
            {
                "reasoning": "summarize the foothold",
                "protocol": "## Current Access\nroot shell",
            },
        )


class ExperimentErrorResultTests(unittest.TestCase):
    def test_error_result_uses_shared_template_for_startup_failures(self) -> None:
        cases = [
            ("missing keep file", "workspace_config_error"),
            ("cleanup failed", "workspace_cleanup_failed"),
            ("docker unavailable", "docker_connection_error"),
        ]

        for error, stopping_reason in cases:
            with self.subTest(stopping_reason=stopping_reason):
                result = experiment_agent._error_result(error, stopping_reason)

                self.assertEqual(result["error"], error)
                self.assertEqual(result["stopping_reason"], stopping_reason)
                self.assertEqual(result["relay_triggers"], [])
                self.assertIsNone(result["session"])
                self.assertEqual(result["iterations"], 0)
                self.assertEqual(result["relay_count"], 0)
                self.assertFalse(result["cost_limit_reached"])
                self.assertFalse(result["iteration_limit_reached"])
                self.assertEqual(result["total_time"], 0.0)
                self.assertEqual(result["total_cost"], 0.0)


class DiscordNotificationTests(unittest.TestCase):
    @patch.object(error_messages, "_safe_send", return_value=True)
    @patch.object(error_messages, "_create_embed", side_effect=lambda **kwargs: kwargs)
    def test_send_empty_command_stop_message_uses_retry_limit(
        self,
        create_embed_mock,
        safe_send_mock,
    ) -> None:
        result = error_messages.send_empty_command_stop_message(
            channel_id="123456789",
            context={"challenge": "vm0", "iteration": 8},
            retry_limit=5,
        )

        self.assertTrue(result)
        self.assertEqual(
            create_embed_mock.call_args.kwargs["description"],
            "Agent provided empty command 5 times consecutively and was stopped",
        )
        safe_send_mock.assert_called_once()


class ProtocolPromptTests(unittest.TestCase):
    def test_protocol_generator_prompt_includes_compaction_guidance(self) -> None:
        prompt = protocol_generator.PROTOCOL_GENERATOR_SYSTEM_PROMPT

        self.assertIn(
            "Use the reasoning field to think about what information from the large context matters for handoff",
            prompt,
        )
        self.assertIn(
            "Ignore unverified assistant speculation",
            prompt,
        )


if __name__ == "__main__":
    unittest.main()
