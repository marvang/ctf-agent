#!/usr/bin/env python3
"""
CTF Agent - Interactive Mode (Product)

This is the user-facing entry point for running the CTF agent interactively.
It prompts the user for configuration (target, VPN, CHAP, model, etc.) and
runs an autonomous agent loop that executes shell commands against CTF targets.

Intended for future release as a standalone tool for CTF practitioners.

The experiment counterpart is src/experiment_utils/main_experiment_agent.py,
which runs the same core loop non-interactively for reproducible scientific
experiments. The two files share similar logic but diverge on user interaction,
error handling, and result saving. Changes to core agent behavior should be
synced between both files.

"""

import json
import os
import subprocess
import time
from datetime import datetime

from dotenv import load_dotenv

from src.chap_utils.protocol_generator import PROTOCOL_GENERATOR_SYSTEM_PROMPT
from src.chap_utils.relay_handler import trigger_relay_handoff
from src.config.constants import (
    COMMAND_TIMEOUT_SECONDS,
    KALI_CONTAINER_NAME,
    LOCAL_CHALLENGES_NETWORK_NAME,
    MAX_EMPTY_COMMAND_RETRIES,
    MAX_OUTPUT_LENGTH,
)
from src.config.workspace import (
    WORKSPACE_DIR,
    WORKSPACE_FILES_TO_EMPTY,
    load_workspace_approved_patterns,
    read_captured_flag,
)
from src.experiment_utils.docker_ops import (
    start_container,
    start_kali_container,
    start_network,
    stop_container,
    stop_kali_container,
)
from src.llm_utils.openrouter import call_openrouter_with_history, call_openrouter_with_history_pty, parse_llm_error
from src.llm_utils.prompt_builder import build_initial_messages
from src.utils.docker_exec import cleanup_tmux_session, execute_command, get_container_ips
from src.utils.docker_utils import connect_to_docker
from src.utils.environment import EnvironmentType, LocalArch, uses_vpn
from src.utils.git import get_git_commit_hash
from src.utils.output import truncate_output
from src.utils.session_utils import display_session_summary
from src.utils.signal_handler import (
    is_vpn_connected,
    register_signal_handler,
    set_cleanup_callback,
    set_container,
    set_iteration,
    set_model,
    set_save_callback,
    set_session,
    set_session_dir,
    set_start_time,
    set_vpn_connected,
    set_vpn_env,
)
from src.utils.state_manager import (
    append_session_event,
    build_assistant_message,
    build_used_prompts_payload,
    create_session,
    persist_session,
    set_session_context,
    update_session_tokens,
)
from src.utils.user_interface import (
    check_private_vpn_setup,
    print_banner,
    print_config_summary,
    prompt_architecture_selection,
    prompt_chap_usage,
    prompt_custom_instructions,
    prompt_environment_selection,
    prompt_local_challenge_selection,
    prompt_model_selection,
    prompt_target_ip,
    prompt_vpn_script_selection,
)
from src.utils.vpn import connect_vpn, disconnect_vpn, discover_vpn_scripts, get_vpn_setup_hint
from src.utils.workspace import cleanup_workspace

MAX_COST_AUTO_MODE = 2
MAX_ITERATIONS_AUTO_MODE = 200
LOCAL_CTF_STARTUP_DELAY_SECONDS = 30
LOCAL_CTF_NETWORK_NAME = LOCAL_CHALLENGES_NETWORK_NAME
USE_PTY_MODE = False


def ensure_kali_container_running(kali_container_name: str = KALI_CONTAINER_NAME):
    """Connect to the Kali container, starting it first if required."""
    _, container = connect_to_docker(kali_container_name=kali_container_name)
    if container is not None:
        container.reload()

    if container is None or container.status != "running":
        print(f"\n🔄 Docker container '{kali_container_name}' is not running. Starting it now...")
        try:
            print(f"🌐 Ensuring Docker network '{LOCAL_CTF_NETWORK_NAME}' is available...")
            start_network()
        except Exception as exc:
            print(f"❌ Failed to prepare Docker network '{LOCAL_CTF_NETWORK_NAME}': {exc}")
            return None

        if not start_kali_container(kali_container_name):
            return None

        _, container = connect_to_docker(kali_container_name=kali_container_name)
        if container is None:
            return None
        container.reload()

    return container


def stop_local_challenge(challenge_name: str, quiet: bool = False) -> None:
    """Stop a local Docker challenge container if it exists."""
    try:
        stop_container(challenge_name)
        if not quiet:
            print(f"🧹 Stopped local challenge: {challenge_name}")
    except Exception as exc:
        if not quiet:
            print(f"⚠️  Failed to stop local challenge '{challenge_name}': {exc}")


def list_network_container_names(network_name: str = LOCAL_CTF_NETWORK_NAME) -> list[str] | None:
    """List container names still attached to the local challenge Docker network."""
    inspect = subprocess.run(
        [
            "docker",
            "network",
            "inspect",
            network_name,
            "--format",
            "{{range $id, $container := .Containers}}{{$container.Name}}\n{{end}}",
        ],
        capture_output=True,
        text=True,
    )
    if inspect.returncode != 0:
        return None

    return [line.strip() for line in inspect.stdout.splitlines() if line.strip()]


def remove_local_network_if_unused(network_name: str = LOCAL_CTF_NETWORK_NAME) -> None:
    """Remove the local challenge Docker network only when nothing else is attached."""
    attached_containers = list_network_container_names(network_name)
    if attached_containers is None:
        return

    if attached_containers:
        print(
            f"⚠️  Leaving Docker network '{network_name}' in place; active endpoints remain: "
            f"{', '.join(attached_containers)}"
        )
        return

    remove = subprocess.run(
        ["docker", "network", "rm", network_name],
        capture_output=True,
        text=True,
    )
    if remove.returncode == 0:
        print(f"🧹 Removed Docker network: {network_name}")
        return

    stderr = (remove.stderr or "").strip()
    if "No such network" in stderr:
        return
    print(f"⚠️  Leaving Docker network '{network_name}' in place: {stderr or 'unknown error'}")


def save_interactive_results(
    session: dict,
    stopping_reason: str,
    error_message: str | None,
    llm_error_details: dict | None,
    relay_count: int,
    iteration: int,
    session_dir: str,
    selected_model: str,
    environment_mode: EnvironmentType,
    use_chap: bool,
    chap_config: dict,
    local_arch: LocalArch | None,
    custom_instructions: str,
    challenge_name: str | None,
    target_ip: str,
    timestamp: str,
) -> None:
    """Save interactive session results to structured per-run files (mirrors experiment format)."""
    os.makedirs(session_dir, exist_ok=True)
    use_vpn = uses_vpn(environment_mode)

    # 1. session.json - Full command/output history
    session_path = os.path.join(session_dir, "session.json")
    persist_session(session, session_path)

    # 2. summary.json - Lightweight metrics (no command history)
    captured_flag = read_captured_flag()
    summary = {
        "mode": "interactive",
        "challenge_name": challenge_name,
        "environment_mode": environment_mode,
        "target_ip": target_ip,
        "flag_captured": captured_flag,
        "iterations": iteration,
        "relay_count": relay_count,
        "relay_triggers": session.get("relay_triggers", []),
        "error": error_message,
        "llm_error_details": llm_error_details,
        "cost_limit_reached": stopping_reason == "cost_limit",
        "iteration_limit_reached": stopping_reason == "iteration_limit",
        "stopping_reason": stopping_reason,
        "total_cost": session["metrics"]["total_cost"],
        "total_time": session["metrics"]["total_time"],
    }
    summary_path = os.path.join(session_dir, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # 3. used_prompts.json - Prompts for reproducibility
    prompt_payload = build_used_prompts_payload(
        session,
        mode="interactive",
        experiment_id=session.get("id"),
        challenge_name=challenge_name,
        model_name=selected_model,
        chap_enabled=use_chap,
        chap_auto_trigger=chap_config.get("auto_trigger", False),
        environment_mode=environment_mode,
        target_ip=target_ip,
    )

    prompt_path = os.path.join(session_dir, "used_prompts.json")
    with open(prompt_path, "w") as f:
        json.dump(prompt_payload, f, indent=2)
        f.write("\n")

    # 4. session_summary.json - Run-level metadata
    session_summary = {
        "metadata": {
            "timestamp": timestamp,
            "git_commit_hash": get_git_commit_hash(),
            "mode": "interactive",
            "model": selected_model,
            "chap_enabled": use_chap,
            "chap_auto_trigger": chap_config.get("auto_trigger", False),
            "chap_token_limit_base": chap_config.get("token_limit_base"),
            "chap_token_limit_increment": chap_config.get("token_limit_increment"),
            "chap_min_iterations_for_relay": chap_config.get("min_iterations_for_relay"),
            "environment_mode": environment_mode,
            "challenge_name": challenge_name,
            "use_vpn": use_vpn,
            "target_ip": target_ip,
            "use_amd64_prompt": local_arch == "amd64",
            "custom_instructions": custom_instructions,
            "max_cost_auto_mode": MAX_COST_AUTO_MODE,
            "max_iterations_auto_mode": MAX_ITERATIONS_AUTO_MODE,
            "max_output_length": MAX_OUTPUT_LENGTH,
            "command_timeout_seconds": COMMAND_TIMEOUT_SECONDS,
            "stopping_reason": stopping_reason,
            "results_dir": os.path.abspath(session_dir),
        }
    }
    summary_meta_path = os.path.join(session_dir, "session_summary.json")
    with open(summary_meta_path, "w") as f:
        json.dump(session_summary, f, indent=2)

    print(f"💾 Results saved to {session_dir}")


def main():
    # Register signal handler for graceful shutdown
    register_signal_handler()
    # Load environment variables
    load_dotenv()

    # Display banner and get user selections
    print_banner()
    environment_mode, vpn_environment = prompt_environment_selection()
    local_arch: LocalArch | None = None
    if environment_mode == "local":
        local_arch = prompt_architecture_selection()
    selected_model = prompt_model_selection()
    use_vpn = uses_vpn(environment_mode)

    challenge_name: str | None = None
    target_ip = ""
    target_info = ""
    container = None
    vpn_connect_script: str | None = None
    cleanup_completed = False

    def cleanup_on_exit():
        nonlocal cleanup_completed
        if cleanup_completed:
            return
        cleanup_completed = True

        if container is not None:
            cleanup_tmux_session(container)

        if is_vpn_connected() and container is not None and vpn_environment is not None:
            disconnect_vpn(container, vpn_environment, vpn_connect_script)
            set_vpn_connected(False)

        if environment_mode == "local":
            if challenge_name:
                stop_local_challenge(challenge_name)
            stop_kali_container(KALI_CONTAINER_NAME)
            remove_local_network_if_unused()

    set_cleanup_callback(cleanup_on_exit)

    # Prompt for CHAP (Context Handoff Protocol) configuration
    chap_config = prompt_chap_usage()
    use_chap = bool(chap_config.get("enabled", False))

    try:
        approved_workspace_patterns = load_workspace_approved_patterns()
    except RuntimeError as exc:
        print(f"\n❌ {exc}")
        return

    # Clean up workspace files from previous sessions
    if not cleanup_workspace(
        WORKSPACE_DIR,
        approved_workspace_patterns,
        WORKSPACE_FILES_TO_EMPTY,
    ):
        return

    if environment_mode == "local":
        print("\n📦 Local Container Mode")
        challenge_name = prompt_local_challenge_selection()
        if not challenge_name:
            return

        try:
            print("\n🌐 Ensuring Docker network is available...")
            start_network()

            print(f"\n🧹 Resetting local challenge: {challenge_name}")
            stop_local_challenge(challenge_name, quiet=True)

            print(f"\n📦 Starting vulnerable container: {challenge_name}")
            target_ip = start_container(challenge_name)
            print(f"✅ Container started at {target_ip}")

            print(f"⏳ Waiting {LOCAL_CTF_STARTUP_DELAY_SECONDS}s for service to initialize...")
            time.sleep(LOCAL_CTF_STARTUP_DELAY_SECONDS)
            print("✅ Proceeding with challenge")
        except Exception as exc:
            print(f"\n❌ Failed to start local challenge '{challenge_name}': {exc}")
            cleanup_on_exit()
            return

        target_info = f"{challenge_name} ({target_ip})"

    container = ensure_kali_container_running(KALI_CONTAINER_NAME)
    if container is None:
        cleanup_on_exit()
        return

    set_container(container)

    # Handle VPN connection if requested
    if use_vpn:
        if vpn_environment is None:
            print("❌ VPN environment not configured")
            cleanup_on_exit()
            return

        # For private VPN: check setup and discover scripts
        if vpn_environment == "private":
            if not check_private_vpn_setup():
                cleanup_on_exit()
                return
            scripts = discover_vpn_scripts(container, vpn_environment)
            if scripts:
                vpn_connect_script = prompt_vpn_script_selection(scripts)

        if not connect_vpn(container, vpn_environment, vpn_connect_script):
            print(get_vpn_setup_hint(vpn_environment))
            cleanup_on_exit()
            return
        else:
            set_vpn_connected(True)
            set_vpn_env(vpn_environment)

        target_ip = prompt_target_ip()
        if not target_ip:
            cleanup_on_exit()
            return
        target_info = target_ip

    # Create session
    session = create_session(model=selected_model, chap_enabled=use_chap)
    set_session(session)
    set_model(selected_model)

    # Display configuration summary
    print_config_summary(target_info)

    # Get agent IP addresses from container
    agent_ips = get_container_ips(container, use_vpn)

    # Get custom instructions and build initial messages
    custom_instructions = prompt_custom_instructions()
    messages = build_initial_messages(
        environment_mode=environment_mode,
        target_info=target_ip,
        use_chap=use_chap,
        custom_instructions=custom_instructions,
        agent_ips=agent_ips,
        local_arch=local_arch,
        use_pty=USE_PTY_MODE,
    )

    # Set challenge_name for VPN modes (local mode already set by prompt_local_challenge_selection)
    if challenge_name is None:
        if environment_mode == "htb":
            challenge_name = "hack_the_box"
        else:
            challenge_name = "private_vpn_range"

    # Results directory setup
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = os.path.join("./results/interactive", f"session_{run_timestamp}", challenge_name)
    os.makedirs(session_dir, exist_ok=True)

    session_path = os.path.join(session_dir, "session.json")
    set_session_context(
        session,
        mode="interactive",
        experiment_id=session["id"],
        challenge_name=challenge_name,
        model_name=selected_model,
        chap_enabled=use_chap,
        chap_auto_trigger=chap_config.get("auto_trigger", False),
        environment_mode=environment_mode,
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
    if use_chap:
        append_session_event(
            session,
            stream="protocol_generation",
            tag="protocol_generator_system_prompt_template",
            message={"role": "system", "content": PROTOCOL_GENERATOR_SYSTEM_PROMPT},
            iteration=0,
            metadata={"included_in_history": False, "template_only": True},
            session_path=session_path,
        )

    # Stopping/error tracking (mirrors main_experiment_agent.py)
    stopping_reason = None
    error_message = None
    llm_error_details = None
    relay_count = 0

    iteration = 0
    set_iteration(iteration)

    # Track session start time
    session_start_time = time.time()
    set_start_time(session_start_time)

    # Threshold tracking flags
    cost_threshold_prompted = False
    iteration_threshold_prompted = False

    # CHAP tracking variables
    last_relay_iteration = 0  # Track iteration when last relay occurred
    chap_80_percent_warning_shown = False  # Track if 80% token warning has been shown

    # PTY session manager (opt-in)
    pty_manager = None
    if USE_PTY_MODE:
        from src.utils.pty_session import PtySessionManager

        pty_manager = PtySessionManager(container_name=KALI_CONTAINER_NAME)

    # Empty command retry tracking
    empty_command_count = 0

    # Guard flag to prevent double-save (signal handler + finally both fire on sys.exit)
    _results_saved = False

    # Register save callback for signal handler (Ctrl+C)
    def save_on_interrupt():
        nonlocal _results_saved
        session["metrics"]["total_iterations"] = iteration
        session["metrics"]["total_time"] = time.time() - session_start_time
        save_interactive_results(
            session=session,
            stopping_reason="interrupted_by_user",
            error_message=error_message,
            llm_error_details=llm_error_details,
            relay_count=relay_count,
            iteration=iteration,
            session_dir=session_dir,
            selected_model=selected_model,
            environment_mode=environment_mode,
            use_chap=use_chap,
            chap_config=chap_config,
            local_arch=local_arch,
            custom_instructions=custom_instructions,
            challenge_name=challenge_name,
            target_ip=target_ip,
            timestamp=run_timestamp,
        )
        _results_saved = True

    set_save_callback(save_on_interrupt)
    set_session_dir(session_dir)

    try:
        while True:
            print(f"\n{'=' * 40}")
            iteration_header = f"Iteration {iteration + 1}"
            if use_chap:
                iteration_header += f" (CHAP Agent #{session['agent_number']})"
            print(iteration_header)
            print("=" * 40)

            current_session_cost = session["metrics"]["total_cost"]

            if not cost_threshold_prompted and current_session_cost >= MAX_COST_AUTO_MODE:
                cost_threshold_prompted = True
                print(f"\n⚠️  Cost limit reached: ${current_session_cost:.4f} / ${MAX_COST_AUTO_MODE:.2f}")
                user_input = input("Continue? (y/n) [n]: ").strip().lower()
                if user_input != "y":
                    print("\n👋 Exiting...")
                    stopping_reason = "cost_limit"
                    break

            if not iteration_threshold_prompted and iteration >= MAX_ITERATIONS_AUTO_MODE:
                iteration_threshold_prompted = True
                print(f"\n⚠️  Iteration limit reached: {iteration} / {MAX_ITERATIONS_AUTO_MODE}")
                user_input = input("Continue? (y/n) [n]: ").strip().lower()
                if user_input != "y":
                    print("\n👋 Exiting...")
                    stopping_reason = "iteration_limit"
                    break

            stdin_input = ""
            try:
                if USE_PTY_MODE:
                    reasoning, shell_command, stdin_input, usage, extended_reasoning = (
                        call_openrouter_with_history_pty(
                            messages=messages,
                            model_name=selected_model,
                        )
                    )
                else:
                    reasoning, shell_command, usage, extended_reasoning = call_openrouter_with_history(
                        messages=messages,
                        model_name=selected_model,
                    )
            except Exception as e:
                print(f"❌ LLM API error: {e}")
                llm_error_details = parse_llm_error(e)
                error_message = f"LLM API error: {e}"
                stopping_reason = "llm_error"
                break

            # Display LLM response
            if extended_reasoning:
                # Truncate long extended reasoning for display
                display_extended = extended_reasoning[:500]
                if len(extended_reasoning) > 500:
                    display_extended += "..."
                print(f"\n💭 Internal Reasoning:\n<thinking>\n{display_extended}\n</thinking>")
            print(f"\n🧠 {reasoning}")
            print(f"💻 {shell_command}")
            if USE_PTY_MODE and stdin_input:
                print(f"⌨️  stdin: {stdin_input}")

            # Track token usage in session
            prompt_tokens = 0
            token_limit_for_agent = 0
            token_usage_percentage = 0.0

            if usage:
                update_session_tokens(session, usage)

                # Calculate token metrics for CHAP (used for auto-trigger and 80% warning)
                if use_chap:
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    token_limit_for_agent = chap_config["token_limit_base"] + (
                        session["agent_number"] * chap_config["token_limit_increment"]
                    )
                    if token_limit_for_agent > 0:
                        token_usage_percentage = (prompt_tokens / token_limit_for_agent) * 100

                # Check if input prompt exceeded threshold (CHAP only, when auto-trigger enabled)
                if use_chap and chap_config["auto_trigger"] and prompt_tokens >= token_limit_for_agent:
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
                            "relay_number": relay_count + 1,
                            "trigger_type": "auto",
                            "iteration": iteration,
                            "reason": "prompt_token_threshold",
                            "prompt_tokens": prompt_tokens,
                            "token_limit": token_limit_for_agent,
                            "trigger_event_index": auto_relay_event["event_index"],
                        }
                    )
                    persist_session(session, session_path)

                    messages = trigger_relay_handoff(
                        session=session,
                        messages=messages,
                        model_name=selected_model,
                        environment_mode=environment_mode,
                        target_info=target_ip,
                        custom_instructions=custom_instructions,
                        current_iteration=iteration,
                        agent_ips=agent_ips,
                        local_arch=local_arch,
                        session_path=session_path,
                    )
                    relay_count += 1

                    # Reset per-agent state
                    last_relay_iteration = iteration
                    chap_80_percent_warning_shown = False
                    continue  # Skip to next iteration with fresh agent

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
                                f"FINAL WARNING: {empty_command_count} consecutive empty commands. One more will prompt for user input.\n"
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
                else:
                    print(f"\n⚠️  No command provided {MAX_EMPTY_COMMAND_RETRIES} times")
                    retry_choice = input("Continue trying? (y/n) [n]: ").strip().lower()
                    if retry_choice == "y":
                        empty_command_count = 0  # Reset counter
                        continue_message = {
                            "role": "user",
                            "content": (
                                "User has requested to continue. Please provide a valid command.\n"
                                "Respond with ONLY a JSON object of the form:\n"
                                '{"reasoning": "...", "shell_command": "..."}'
                            ),
                        }
                        messages.append(continue_message)
                        append_session_event(
                            session,
                            stream="main_agent",
                            tag="framework_empty_user_continue",
                            message=continue_message,
                            iteration=iteration,
                            metadata={
                                "assistant_event_index": assistant_event["event_index"],
                                "included_in_history": True,
                            },
                            session_path=session_path,
                        )
                        continue
                    else:
                        print("\n👋 Exiting...")
                        stopping_reason = "empty_command"
                        break

            empty_command_count = 0

            if shell_cmd_clean.lower() in ["exit", "quit", "terminate"]:
                print("\n✅ Agent requested termination. Exiting...")
                stopping_reason = "agent_exit"
                break

            if shell_cmd_clean.lower() == "relay":
                if not use_chap:
                    print("\n⚠️  CHAP not enabled. Cannot trigger relay.")
                    print("💡 Restart the agent with CHAP enabled to use relay functionality.")
                    stopping_reason = "relay_without_chap"
                    error_message = "Relay requested but CHAP not enabled"
                    break

                iterations_since_relay = iteration - last_relay_iteration
                if iterations_since_relay < chap_config["min_iterations_for_relay"]:
                    iterations_remaining = chap_config["min_iterations_for_relay"] - iterations_since_relay
                    print(f"\n⚠️  Relay rejected: Too early. Need {iterations_remaining} more iterations.")
                    rejection_message = {
                        "role": "user",
                        "content": f"CHAP: Relay rejected - too early to relay. Minimum {chap_config['min_iterations_for_relay']} iterations required since last relay. Current agent iterations: {iterations_since_relay}. Continue for {iterations_remaining} more iterations.",
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
                        "relay_number": relay_count + 1,
                        "trigger_type": "manual",
                        "iteration": iteration,
                        "reason": "agent_command",
                        "trigger_event_index": assistant_event["event_index"],
                    }
                )
                persist_session(session, session_path)

                session["metrics"]["total_time"] = time.time() - session_start_time
                messages = trigger_relay_handoff(
                    session=session,
                    messages=messages,
                    model_name=selected_model,
                    environment_mode=environment_mode,
                    target_info=target_ip,
                    custom_instructions=custom_instructions,
                    current_iteration=iteration,
                    agent_ips=agent_ips,
                    local_arch=local_arch,
                    session_path=session_path,
                )
                relay_count += 1

                # Reset per-agent state
                last_relay_iteration = iteration
                chap_80_percent_warning_shown = False
                continue

            if USE_PTY_MODE and pty_manager is not None:
                from src.utils.pty_session import dispatch_pty_command, resolve_pty_fields

                shell_command, stdin_input = resolve_pty_fields(shell_command, stdin_input)

                print("\n🤖 Executing (PTY)...")
                exec_start = time.time()
                output, process_exited, exit_code = dispatch_pty_command(
                    pty_manager, shell_command, stdin_input
                )
                wall_time = time.time() - exec_start
                llm_output = truncate_output(output, MAX_OUTPUT_LENGTH)

                print("\n📤 Output:")
                print(llm_output)

                status_line = f"[Process exited (code {exit_code})]" if process_exited else "[Process running]"
                result_content = f"{status_line} Wall time: {wall_time:.1f}s\nOutput:\n{llm_output}"
                success = (exit_code == 0) if exit_code is not None else (not process_exited)
            else:
                print("\n🤖 Executing...")
                success, output, exit_code = execute_command(container, shell_command, COMMAND_TIMEOUT_SECONDS)

                llm_output = truncate_output(output, MAX_OUTPUT_LENGTH)

                print("\n📤 Output:")
                print(llm_output)
                if not success:
                    print(f"⚠️  Exit code: {exit_code}")

                result_content = f"Command executed with exit code {exit_code}. Output:\n{llm_output}"

            # Show CHAP 80% warning ONCE when threshold is crossed
            if use_chap and token_limit_for_agent > 0:
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
            persist_session(session, session_path)
            set_iteration(iteration)

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        if stopping_reason is None:
            stopping_reason = "crash"
            error_message = str(e)

    finally:
        # Save results unless already saved by signal handler
        if not _results_saved:
            if stopping_reason is None:
                stopping_reason = "unknown"

            session["metrics"]["total_iterations"] = iteration
            session["metrics"]["total_time"] = time.time() - session_start_time
            persist_session(session, session_path)

            save_interactive_results(
                session=session,
                stopping_reason=stopping_reason,
                error_message=error_message,
                llm_error_details=llm_error_details,
                relay_count=relay_count,
                iteration=iteration,
                session_dir=session_dir,
                selected_model=selected_model,
                environment_mode=environment_mode,
                use_chap=use_chap,
                chap_config=chap_config,
                local_arch=local_arch,
                custom_instructions=custom_instructions,
                challenge_name=challenge_name,
                target_ip=target_ip,
                timestamp=run_timestamp,
            )

        if pty_manager is not None:
            pty_manager.cleanup()

        cleanup_on_exit()

        # Display summary
        display_session_summary(session, iteration, session["metrics"]["total_time"], selected_model)


if __name__ == "__main__":
    main()
