"""
CTF Agent - Experiment Function
Automated agent runner for CTF experiments (no user interaction)
"""

import time
from typing import Any

from dotenv import load_dotenv

from src.chap_utils.protocol_generator import PROTOCOL_GENERATOR_SYSTEM_PROMPT
from src.chap_utils.relay_handler import trigger_relay_handoff
from src.config.constants import KALI_CONTAINER_NAME, MAX_EMPTY_COMMAND_RETRIES
from src.config.workspace import (
    WORKSPACE_DIR,
    WORKSPACE_FILES_TO_EMPTY,
    ensure_workspace_dir,
    load_workspace_approved_patterns,
    read_captured_flag,
)
from src.llm_utils.openrouter import call_openrouter_with_history, parse_llm_error
from src.llm_utils.prompt_builder import build_initial_messages
from src.utils.discord_utils import (
    send_auto_relay_message,
    send_empty_command_stop_message,
    send_llm_error_message,
    send_manual_relay_message,
)
from src.utils.docker_exec import cleanup_tmux_session, execute_command, get_container_ips
from src.utils.docker_utils import connect_to_docker
from src.utils.environment import EnvironmentType, LocalArch, uses_vpn
from src.utils.output import truncate_output
from src.utils.state_manager import (
    append_session_event,
    build_assistant_message,
    create_session,
    persist_session,
    set_session_context,
    update_session_tokens,
)
from src.utils.workspace import cleanup_workspace


def _error_result(error: str, stopping_reason: str) -> dict[str, Any]:
    """Return the common experiment failure payload used before execution starts."""
    return {
        "flag_captured": None,
        "session": None,
        "iterations": 0,
        "relay_count": 0,
        "relay_triggers": [],
        "error": error,
        "llm_error_details": None,
        "cost_limit_reached": False,
        "iteration_limit_reached": False,
        "stopping_reason": stopping_reason,
        "total_time": 0.0,
        "total_cost": 0.0,
    }


def run_experiment_agent(
    experiment_id: str,  # info purposes
    experiment_loop_iteration: int,  # info purposes
    total_loop_iterations: int,  # info purposes
    target_ip: str,
    challenge_name: str,  # info purposes
    model_name: str,
    chap_enabled: bool,
    chap_auto_trigger: bool,
    max_iterations: int,
    command_timeout_seconds: int,
    max_cost: float,
    max_output_length: int,
    chap_token_limit_base: int,
    chap_token_limit_increment: int,
    chap_min_iterations_for_relay: int = 30,
    kali_container_name: str = KALI_CONTAINER_NAME,
    custom_instructions: str = "",
    channel_id: str | None = None,
    local_arch: LocalArch = "aarch64",
    session_path: str | None = None,
    workspace_dir: str = WORKSPACE_DIR,
    environment_mode: EnvironmentType = "local",
) -> dict[str, Any]:
    """
    Run CTF agent in experiment mode (no user interaction)

    Args:
        target_ip: IP address of target container (e.g., "192.168.5.0")
        challenge_name: Name of challenge (e.g., "vm0")
        model_name: OpenRouter model identifier
        chap_enabled: Whether to enable CHAP (Context Handoff Protocol)
        chap_auto_trigger: Whether to auto-trigger relay based on token limits (only used if chap_enabled)
        max_iterations: Maximum number of iterations before stopping
        command_timeout: Timeout in seconds for each command execution
        max_cost: Cost threshold to stop at (in USD)
        max_output_length: Maximum output characters to retain for LLM context
        token_limit_base: Starting token limit before first relay
        token_limit_increment: Additional tokens allowed per agent number
        chap_min_iterations_for_relay: Minimum iterations before manual relay is allowed
        custom_instructions: Additional instructions for the agent
        channel_id: Discord channel for webhook notifications (optional)
        local_arch: Local execution architecture used for prompt selection
        workspace_dir: Host workspace directory mounted into the Kali container

    Returns:
        {
            "flag_captured": str or None,
            "session": session_dict,
            "iterations": int,
            "challenge_name": str,
            "target_ip": str,
            "error": str or None,
            "cost_limit_reached": bool,
            "iteration_limit_reached": bool,
            "stopping_reason": str or None,
            "total_time": float,
            "total_cost": float
        }
    """
    load_dotenv()

    print(f"\n{'=' * 60}")
    print(f"🏴‍☠️  Experiment ID: {experiment_id}")
    print(f"🔁 Iteration: {experiment_loop_iteration} / {total_loop_iterations}")
    print(f"🎯 CTF Challenge: {challenge_name}")
    print(f"📍 Target IP: {target_ip}")
    print(f"🤖 Model: {model_name}")
    print(f"🔄 CHAP: {'Enabled' if chap_enabled else 'Disabled'}")
    print(f"📊 Max Iterations: {max_iterations}")
    print("=" * 60)

    try:
        approved_workspace_patterns = load_workspace_approved_patterns()
    except RuntimeError as exc:
        return _error_result(str(exc), "workspace_config_error")

    ensure_workspace_dir(workspace_dir)
    if not cleanup_workspace(
        workspace_dir,
        approved_workspace_patterns,
        WORKSPACE_FILES_TO_EMPTY,
        auto_confirm=True,
    ):
        return _error_result(
            "Workspace cleanup failed - aborting to prevent flag contamination",
            "workspace_cleanup_failed",
        )

    _, container = connect_to_docker(kali_container_name)
    if container is None:
        return _error_result("Failed to connect to Docker container", "docker_connection_error")

    agent_ips = get_container_ips(container, use_vpn=uses_vpn(environment_mode))
    print(f"\n🔍 Agent IP: {', '.join(agent_ips)}")

    session = create_session(model=model_name, chap_enabled=chap_enabled)

    messages = build_initial_messages(
        environment_mode=environment_mode,
        target_info=target_ip,
        use_chap=chap_enabled,
        custom_instructions=custom_instructions,
        agent_ips=agent_ips,
        local_arch=local_arch,
    )

    set_session_context(
        session,
        mode="experiment_script",
        experiment_id=experiment_id,
        challenge_name=challenge_name,
        model_name=model_name,
        chap_enabled=chap_enabled,
        chap_auto_trigger=chap_auto_trigger,
        target_ip=target_ip,
    )
    append_session_event(
        session,
        stream="main_agent",
        tag="initial_system_prompt",
        message=messages[0],
        iteration=0,
        session_path=session_path,
    )
    append_session_event(
        session,
        stream="main_agent",
        tag="initial_user_prompt",
        message=messages[1],
        iteration=0,
        session_path=session_path,
    )
    if chap_enabled:
        append_session_event(
            session,
            stream="protocol_generation",
            tag="protocol_generator_system_prompt_template",
            message={"role": "system", "content": PROTOCOL_GENERATOR_SYSTEM_PROMPT},
            iteration=0,
            metadata={"included_in_history": False, "template_only": True},
            session_path=session_path,
        )

    iteration = 0
    relay = 0
    last_relay_iteration = 0
    chap_80_percent_warning_shown = False
    session_start_time = time.time()

    cost_limit_reached = False
    iteration_limit_reached = False
    error_message = None
    llm_error_details = None
    empty_command_count = 0
    stopping_reason = None

    while True:
        print(f"\n{'=' * 40}")
        iteration_header = f"Iteration {iteration + 1}"
        if chap_enabled:
            iteration_header += f" (CHAP Agent #{session['agent_number']})"
        print(iteration_header)
        print("=" * 40)

        current_session_cost = session["metrics"]["total_cost"]
        if current_session_cost >= max_cost:
            print(f"\n⚠️  Cost limit reached: ${current_session_cost:.4f} >= ${max_cost:.2f}")
            print("Stopping experiment due to cost limit (non-interactive mode)...")
            cost_limit_reached = True
            stopping_reason = "cost_limit"
            break

        if iteration >= max_iterations:
            print(f"\n⚠️  Iteration limit reached: {iteration} > {max_iterations}")
            print("Stopping experiment...")
            iteration_limit_reached = True
            stopping_reason = "iteration_limit"
            break

        try:
            reasoning, shell_command, usage, extended_reasoning = call_openrouter_with_history(
                messages=messages,
                model_name=model_name,
            )
        except Exception as e:
            print(f"❌ LLM API error: {e}")
            llm_error_details = parse_llm_error(e)

            send_llm_error_message(
                channel_id=channel_id,
                error_msg=str(e),
                context={
                    "challenge": challenge_name,
                    "iteration": iteration,
                    "model": model_name,
                    "experiment_id": experiment_id,
                },
            )

            error_message = f"LLM API error: {e!s}"
            stopping_reason = "llm_error"
            break

        # Display LLM response
        if extended_reasoning:
            # Truncate long extended reasoning for display
            display_extended = extended_reasoning[:500]
            if len(extended_reasoning) > 500:
                display_extended += "..."
            print(f"\n💭 Internal Reasoning:\n<thinking>\n{display_extended}\n</thinking>")
        print(f"\n🧠 Reasoning: {reasoning}")
        print(f"\n💻 Command: {shell_command}")

        prompt_tokens = 0
        token_limit_for_agent = 0
        token_usage_percentage = 0.0

        if usage:
            update_session_tokens(session, usage)

            if chap_enabled:
                prompt_tokens = usage.get("prompt_tokens", 0)
                token_limit_for_agent = chap_token_limit_base + (session["agent_number"] * chap_token_limit_increment)
                if token_limit_for_agent > 0:
                    token_usage_percentage = (prompt_tokens / token_limit_for_agent) * 100

            if chap_enabled and chap_auto_trigger and prompt_tokens >= token_limit_for_agent:
                print("\n⚠️  Auto-triggering relay: Input prompt exceeded threshold!")
                print(f"💬 Prompt tokens: {prompt_tokens:,} / {token_limit_for_agent:,}")
                print(f"🤖 Agent {session['agent_number']} handing off...")

                auto_relay_event = append_session_event(
                    session,
                    stream="main_agent",
                    tag="assistant_auto_relay_discarded",
                    message=build_assistant_message(reasoning, shell_command),
                    parsed={
                        "reasoning": reasoning,
                        "shell_command": shell_command,
                        "extended_reasoning": extended_reasoning,
                    },
                    iteration=iteration,
                    usage=usage,
                    metadata={
                        "included_in_history": False,
                        "prompt_tokens": prompt_tokens,
                        "token_limit": token_limit_for_agent,
                    },
                    session_path=session_path,
                )

                session["metrics"]["total_time"] = time.time() - session_start_time
                session["relay_triggers"].append(
                    {
                        "relay_number": relay + 1,
                        "trigger_type": "auto",
                        "iteration": iteration,
                        "reason": "prompt_token_threshold",
                        "prompt_tokens": prompt_tokens,
                        "token_limit": token_limit_for_agent,
                        "trigger_event_index": auto_relay_event["event_index"],
                    }
                )
                if session_path:
                    persist_session(session, session_path)

                messages = trigger_relay_handoff(
                    session=session,
                    messages=messages,
                    model_name=model_name,
                    environment_mode=environment_mode,
                    target_info=target_ip,
                    custom_instructions=custom_instructions,
                    current_iteration=iteration,
                    agent_ips=agent_ips,
                    local_arch=local_arch,
                    session_path=session_path,
                )
                relay += 1

                send_auto_relay_message(
                    channel_id=channel_id,
                    relay_data={
                        "agent_number": session["agent_number"] - 1,
                        "prompt_tokens": prompt_tokens,
                        "token_threshold": token_limit_for_agent,
                        "iteration": iteration,
                        "challenge": challenge_name,
                        "experiment_id": experiment_id,
                    },
                )

                last_relay_iteration = iteration
                chap_80_percent_warning_shown = False
                continue

        assistant_message = build_assistant_message(reasoning, shell_command)
        shell_cmd_clean = shell_command.strip()
        assistant_tag = "assistant_command"
        if not shell_cmd_clean:
            assistant_tag = "assistant_empty_command"
        elif shell_cmd_clean.lower() in ["exit", "quit", "terminate"]:
            assistant_tag = "assistant_exit"
        elif shell_cmd_clean.lower() == "relay":
            assistant_tag = "assistant_relay"

        assistant_event = append_session_event(
            session,
            stream="main_agent",
            tag=assistant_tag,
            message=assistant_message,
            parsed={
                "reasoning": reasoning,
                "shell_command": shell_command,
                "extended_reasoning": extended_reasoning,
            },
            iteration=iteration,
            usage=usage,
            metadata={"included_in_history": True},
            session_path=session_path,
        )
        messages.append(assistant_message)

        if not shell_cmd_clean:
            empty_command_count += 1

            if empty_command_count < MAX_EMPTY_COMMAND_RETRIES:
                print(f"\n⚠️  No command provided - retrying ({empty_command_count}/{MAX_EMPTY_COMMAND_RETRIES})...")

                retry_tag = "framework_empty_retry"
                if empty_command_count == MAX_EMPTY_COMMAND_RETRIES - 1:
                    retry_tag = "framework_empty_final_warning"
                    retry_message = {
                        "role": "user",
                        "content": (
                            f"FINAL WARNING: {empty_command_count} consecutive empty commands. One more will stop the experiment.\n"
                            "If your complex commands are failing to parse, output a simple command like 'pwd' to reset the counter and continue.\n"
                            "Respond with ONLY a JSON object of the form:\n"
                            '{"reasoning": "...", "shell_command": "..."}\n'
                            'If you intend to stop, respond with "exit".'
                        ),
                    }
                else:
                    retry_message = {
                        "role": "user",
                        "content": (
                            "Your last response yielded no command after parsing, perhaps it did not contain a valid JSON object with keys "
                            '"reasoning" and "shell_command", so parsing failed.\n'
                            "Respond again with ONLY a JSON object of the form:\n"
                            '{"reasoning": "...", "shell_command": "..."}'
                        ),
                    }
                messages.append(retry_message)
                append_session_event(
                    session,
                    stream="main_agent",
                    tag=retry_tag,
                    message=retry_message,
                    iteration=iteration,
                    metadata={
                        "assistant_event_index": assistant_event["event_index"],
                        "included_in_history": True,
                    },
                    session_path=session_path,
                )
                continue

            print(f"\n⚠️  No command provided {MAX_EMPTY_COMMAND_RETRIES} times in a row - stopping")
            error_message = f"Agent provided empty command {MAX_EMPTY_COMMAND_RETRIES} times"
            stopping_reason = "empty_command"

            send_empty_command_stop_message(
                channel_id=channel_id,
                context={"challenge": challenge_name, "iteration": iteration + 1, "experiment_id": experiment_id},
                retry_limit=MAX_EMPTY_COMMAND_RETRIES,
            )

            break

        empty_command_count = 0

        if shell_cmd_clean.lower() in ["exit", "quit", "terminate"]:
            print("\n✅ Agent requested termination")
            stopping_reason = "agent_exit"
            break

        if shell_cmd_clean.lower() == "relay":
            if not chap_enabled:
                print("\n⚠️  CHAP not enabled. Cannot trigger relay.")
                error_message = "Relay requested but CHAP not enabled"
                stopping_reason = "relay_without_chap"
                break

            iterations_since_relay = iteration - last_relay_iteration
            if iterations_since_relay < chap_min_iterations_for_relay:
                iterations_remaining = chap_min_iterations_for_relay - iterations_since_relay
                print(f"\n⚠️  Relay rejected: Too early. Need {iterations_remaining} more iterations.")
                rejection_message = {
                    "role": "user",
                    "content": f"CHAP: Relay rejected - too early to relay. Minimum {chap_min_iterations_for_relay} iterations required since last relay. Current agent iterations: {iterations_since_relay}. Continue for {iterations_remaining} more iterations.",
                }
                messages.append(rejection_message)
                append_session_event(
                    session,
                    stream="main_agent",
                    tag="framework_relay_rejection",
                    message=rejection_message,
                    iteration=iteration,
                    metadata={
                        "assistant_event_index": assistant_event["event_index"],
                        "included_in_history": True,
                        "iterations_remaining": iterations_remaining,
                    },
                    session_path=session_path,
                )
                continue

            session["relay_triggers"].append(
                {
                    "relay_number": relay + 1,
                    "trigger_type": "manual",
                    "iteration": iteration,
                    "reason": "agent_command",
                    "trigger_event_index": assistant_event["event_index"],
                }
            )
            if session_path:
                persist_session(session, session_path)

            session["metrics"]["total_time"] = time.time() - session_start_time
            messages = trigger_relay_handoff(
                session=session,
                messages=messages,
                model_name=model_name,
                environment_mode="local",
                target_info=target_ip,
                custom_instructions=custom_instructions,
                current_iteration=iteration,
                agent_ips=agent_ips,
                local_arch=local_arch,
                session_path=session_path,
            )
            relay += 1

            send_manual_relay_message(
                channel_id=channel_id,
                relay_data={
                    "agent_number": session["agent_number"] - 1,  # Previous agent that triggered relay
                    "iteration": iteration,
                    "challenge": challenge_name,
                    "experiment_id": experiment_id,
                    "reason": "Agent command",
                },
            )

            last_relay_iteration = iteration
            chap_80_percent_warning_shown = False
            continue

        print("\n🤖 Executing...")
        success, output, exit_code = execute_command(container, shell_command, command_timeout_seconds)

        llm_output = truncate_output(output, max_output_length)

        print("\n📤 Output:")
        print(llm_output)
        if not success:
            print(f"⚠️  Exit code: {exit_code}")

        result_content = f"Command executed with exit code {exit_code}. Output:\n{llm_output}"

        # Show CHAP 80% warning ONCE when threshold is crossed
        if chap_enabled and token_limit_for_agent > 0:
            if not chap_80_percent_warning_shown and token_usage_percentage >= 80:
                result_content += "\n\nCHAP: 80% of tokens used, auto-relay at 100%"
                chap_80_percent_warning_shown = True

        result_message = {"role": "user", "content": result_content}
        messages.append(result_message)
        append_session_event(
            session,
            stream="main_agent",
            tag="framework_command_result",
            message=result_message,
            parsed={
                "exit_code": exit_code,
                "output": llm_output,
            },
            iteration=iteration,
            metadata={
                "assistant_event_index": assistant_event["event_index"],
                "included_in_history": True,
                "success": success,
            },
            session_path=session_path,
        )

        iteration += 1
        session["metrics"]["total_iterations"] = iteration
        if session_path:
            persist_session(session, session_path)

    session["metrics"]["total_time"] = time.time() - session_start_time
    if session_path:
        persist_session(session, session_path)
    cleanup_tmux_session(container)
    captured_flag = read_captured_flag(workspace_dir)

    cleanup_workspace(
        workspace_dir,
        approved_workspace_patterns,
        WORKSPACE_FILES_TO_EMPTY,
        auto_confirm=True,
    )

    print(f"\n{'=' * 60}")
    print(f"🏁 CTF Complete: {challenge_name}")
    print(f"⏱️  Time: {session['metrics']['total_time']:.1f}s")
    print(f"🔢 Iterations: {iteration}")
    print(f"💰 Cost: ${session['metrics']['total_cost']:.4f}")
    print(f"🛑 Stopping Reason: {stopping_reason}")
    print(f"🤖 Final Agent Number: {session['agent_number']}")
    print(f"🏴 Flag: {captured_flag if captured_flag else 'No flag detected/captured'}")
    if error_message:
        print(f"❌ Error: {error_message}")
    print("=" * 60)

    return {
        "flag_captured": captured_flag,
        "session": session,
        "iterations": iteration,
        "relay_count": relay,
        "error": error_message,
        "llm_error_details": llm_error_details,
        "cost_limit_reached": cost_limit_reached,
        "iteration_limit_reached": iteration_limit_reached,
        "stopping_reason": stopping_reason,
        "total_time": session["metrics"]["total_time"],
        "total_cost": session["metrics"]["total_cost"],
        "relay_triggers": session.get("relay_triggers", []),
    }
