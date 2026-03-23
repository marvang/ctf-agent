#!/usr/bin/env python3
"""
Run CTF experiments on multiple challenges

Usage:
    python scripts/run_experiment.py  # Use defaults from this file
    python scripts/run_experiment.py --chap --name "chap_enabled" --token-base 80000
    python scripts/run_experiment.py --no-chap --name "chap_disabled"
    python scripts/run_experiment.py --environment private --target-ip 10.0.2.88
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config.constants import (
    ARTIFACT_SCHEMA_VERSION,
    LOCAL_CHALLENGES_ROOT_STR,
    MAX_OUTPUT_LENGTH,
)
from src.config.experiment_custom_instructions import (
    DEFAULT_CUSTOM_INSTRUCTIONS,
    REAL_CHALLENGE_CUSTOM_INSTRUCTIONS,
    TEST_CHALLENGE_CUSTOM_INSTRUCTIONS,
)
from src.config.session_runtime import SessionRuntime, resolve_session_runtime
from src.config.workspace import ensure_workspace_dir
from src.experiment_utils.docker_ops import (
    start_challenge_container_standalone,
    start_kali_container_standalone,
    start_network,
    stop_challenge_container_standalone,
    stop_kali_container,
    stop_network,
)
from src.experiment_utils.key_validator import validate_rsa_key_match
from src.experiment_utils.main_experiment_agent import run_experiment_agent
from src.experiment_utils.validate_flag import flag_match, get_expected_flag, load_flags_file
from src.utils.discord_utils import (
    create_experiment_channel,
    send_challenge_complete_message,
    send_challenge_error_message,
    send_challenge_start_message,
    send_docker_connection_error_message,
    send_experiment_complete_message,
    send_experiment_error_message,
    send_experiment_interrupted_message,
    send_experiment_start_message,
)
from src.utils.docker_utils import connect_to_docker
from src.utils.environment import EnvironmentType, LocalArch, uses_vpn
from src.utils.git import build_git_provenance
from src.utils.run_ids import generate_run_id
from src.utils.state_manager import persist_session
from src.utils.vpn import connect_vpn, disconnect_vpn, discover_vpn_scripts, select_vpn_connect_script

# EXPERIMENT CONFIGURATION

# --- Shared settings ---

TEST_RUN = True  # Set to True only for test runs. For local: gives agent solutions. Blocked for VPN (no test hints exist).
USE_CUSTOM_INSTRUCTIONS = True  # Enable/disable per-challenge custom instructions. Recommended to keep True.
CHALLENGE_CUSTOM_INSTRUCTIONS = TEST_CHALLENGE_CUSTOM_INSTRUCTIONS if TEST_RUN else REAL_CHALLENGE_CUSTOM_INSTRUCTIONS

MODEL_NAME = "xiaomi/mimo-v2-pro"
# Model names for quick access: anthropic/claude-sonnet-4.6, anthropic/claude-opus-4.6, openai/gpt-5.4-mini, minimax/minimax-m2.5:free, minimax/minimax-m2.7, cognitivecomputations/dolphin-mistral-24b-venice-edition:free, xiaomi/mimo-v2-pro
CHAP_ENABLED = False
MAX_ITERATIONS = 100
COMMAND_TIMEOUT = 220
MAX_COST = 5

# CHAP prompt token thresholds (only used if CHAP enabled)
# Threshold increases per agent: threshold = BASE + (agent_number * INCREMENT)
CHAP_TOKEN_LIMIT_BASE = 100000
CHAP_TOKEN_LIMIT_INCREMENT = 5000
CHAP_AUTO_TRIGGER = (
    True  # If True, auto-trigger relay based on token limits; if False, only agent-initiated relay allowed
)
CHAP_MIN_ITERATIONS_FOR_RELAY = 30  # Minimum iterations before manual relay is allowed

DISCORD_NOTIFICATIONS_ENABLED = True  # Set to False, to enable you need to set DISCORD_MAIN_BOT_TOKEN and DISCORD_GUILD_ID in .env which you can get from your Discord developer portal after creating an application and bot
RESULTS_DIR = "./results"
EXPERIMENT_SET_NAME = "pre-commit-smoke"
ENVIRONMENT_MODE: EnvironmentType = "local"  # "local", "private", or "htb"

# --- Local Docker mode ---

CTF_CHALLENGES = [
    "vm0",
    "vm1",
    "vm2",
    "vm3",
    "vm4",
    "vm5",
    "vm6",
    "vm7",
    "vm8",
    "vm9",
    "vm10",
]
LOCAL_FLAG_DIR = LOCAL_CHALLENGES_ROOT_STR  # Directory containing per-challenge flag.txt files
LOCAL_ARCH: LocalArch = "aarch64"  # Architecture-specific prompt selection for local challenge runs
SERVICE_STARTUP_DELAY = 30 # Only for local mode.

# --- VPN/Remote mode ---

VPN_TARGET_IP = "10.0.2.88"  # Single target IP address for VPN mode (e.g., "10.0.2.88")
VPN_FLAGS_FILE: str | None = "flags_example.json"  # Path to flags JSON file for VPN mode validation
VPN_CONNECT_SCRIPT: str | None = None


def parse_args():
    """Parse command line arguments to override defaults."""
    parser = argparse.ArgumentParser(description="Run CTF experiments")

    # CHAP toggle

    chap_group = parser.add_mutually_exclusive_group()
    chap_group.add_argument("--chap", dest="chap_enabled", action="store_true", help="Enable CHAP (default)")
    chap_group.add_argument("--no-chap", dest="chap_enabled", action="store_false", help="Disable CHAP")
    parser.set_defaults(chap_enabled=None)  # None means use file default

    # Other overrides
    parser.add_argument("--name", type=str, default=None, help="Experiment set name (for results folder)")
    parser.add_argument("--token-base", type=int, default=None, help="Override CHAP token limit base")
    parser.add_argument("--model", type=str, default=None, help="Model name")
    parser.add_argument(
        "--token-increment", type=int, default=None, help="Override CHAP token limit increment per relay"
    )

    # Auto-trigger toggle (only relevant when CHAP enabled)
    auto_trigger_group = parser.add_mutually_exclusive_group()
    auto_trigger_group.add_argument(
        "--auto-trigger",
        dest="auto_trigger",
        action="store_true",
        help="Enable auto-trigger relay based on token limits (default)",
    )
    auto_trigger_group.add_argument(
        "--no-auto-trigger",
        dest="auto_trigger",
        action="store_false",
        help="Disable auto-trigger, only agent-initiated relay allowed",
    )
    parser.set_defaults(auto_trigger=None)  # None means use file default

    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Session ID for isolated Docker/workspace resources",
    )

    # Environment / VPN overrides
    parser.add_argument(
        "--environment",
        type=str,
        choices=["local", "private", "htb"],
        default=None,
        help="Environment mode: local (Docker), private (VPN cyber range), or htb (Hack The Box)",
    )
    parser.add_argument("--target-ip", type=str, default=None, help="Single target IP address (required for VPN mode)")
    parser.add_argument(
        "--vpn-flags-file", type=str, default=None, help="Path to flags JSON file for validation (VPN mode)"
    )
    parser.add_argument("--vpn-script", type=str, default=None, help="Explicit VPN connect script for VPN mode")

    return parser.parse_args()


def apply_cli_overrides(args):
    """Apply CLI arguments to global config variables."""
    global CHAP_ENABLED, EXPERIMENT_SET_NAME, CHAP_TOKEN_LIMIT_BASE
    global MODEL_NAME, CHAP_TOKEN_LIMIT_INCREMENT, CHAP_AUTO_TRIGGER
    global VPN_TARGET_IP, ENVIRONMENT_MODE, VPN_FLAGS_FILE, VPN_CONNECT_SCRIPT

    if args.chap_enabled is not None:
        CHAP_ENABLED = args.chap_enabled
    if args.name is not None:
        EXPERIMENT_SET_NAME = args.name
    if args.token_base is not None:
        CHAP_TOKEN_LIMIT_BASE = args.token_base
    if args.model is not None:
        MODEL_NAME = args.model
    if args.token_increment is not None:
        CHAP_TOKEN_LIMIT_INCREMENT = args.token_increment
    if args.auto_trigger is not None:
        CHAP_AUTO_TRIGGER = args.auto_trigger

    if args.environment is not None:
        ENVIRONMENT_MODE = args.environment
    if args.target_ip is not None:
        VPN_TARGET_IP = args.target_ip
    if args.vpn_flags_file is not None:
        VPN_FLAGS_FILE = args.vpn_flags_file
    if args.vpn_script is not None:
        VPN_CONNECT_SCRIPT = args.vpn_script


def get_custom_instructions_for_challenge(challenge_name: str) -> str:
    """Get custom instructions for a specific challenge.

    For VPN mode, the challenge_name is the experiment set name (e.g. "vpn-test")
    which may not have a dedicated entry. Falls back to the environment mode key
    (e.g. "private", "htb") before using the default.
    """
    if not USE_CUSTOM_INSTRUCTIONS:
        return ""
    if challenge_name in CHALLENGE_CUSTOM_INSTRUCTIONS:
        return CHALLENGE_CUSTOM_INSTRUCTIONS[challenge_name]
    return CHALLENGE_CUSTOM_INSTRUCTIONS.get(ENVIRONMENT_MODE, DEFAULT_CUSTOM_INSTRUCTIONS)


def save_results(
    results: list,
    results_dir: str,
    session_runtime: SessionRuntime,
    challenges: list[str],
    experiment_dir: str | None = None,
    experiment_timestamp: str | None = None,
    termination_reason: str | None = None,
    vpn_connect_script: str | None = None,
):
    """Save experiment results to structured per-challenge files."""
    os.makedirs(results_dir, exist_ok=True)
    timestamp = experiment_timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    if experiment_dir is None:
        experiment_dir = os.path.join(results_dir, f"experiment_{timestamp}")
    os.makedirs(experiment_dir, exist_ok=True)

    custom_instructions_map: dict[str, str] = {}
    if USE_CUSTOM_INSTRUCTIONS:
        custom_instructions_map = {
            challenge: get_custom_instructions_for_challenge(challenge) for challenge in challenges
        }
    experiment_metadata = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "timestamp": timestamp,
        "local_flag_dir": LOCAL_FLAG_DIR,
        "challenges": challenges,
        "model": MODEL_NAME,
        "chap_enabled": CHAP_ENABLED,
        "challenge_count": len(challenges),
        "completed_challenges": len(results),
        "max_iterations": MAX_ITERATIONS,
        "command_timeout_seconds": COMMAND_TIMEOUT,
        "max_output_length": MAX_OUTPUT_LENGTH,
        "max_cost": MAX_COST,
        "test_run": TEST_RUN,
        "use_custom_instructions": USE_CUSTOM_INSTRUCTIONS,
        "custom_instructions_by_challenge": custom_instructions_map,
        "chap_token_limit_base": CHAP_TOKEN_LIMIT_BASE,
        "chap_token_limit_increment": CHAP_TOKEN_LIMIT_INCREMENT,
        "chap_auto_trigger": CHAP_AUTO_TRIGGER,
        "chap_min_iterations_for_relay": CHAP_MIN_ITERATIONS_FOR_RELAY,
        "service_startup_delay_seconds": SERVICE_STARTUP_DELAY,
        "experiment_set_name": EXPERIMENT_SET_NAME,
        "discord_notifications_enabled": DISCORD_NOTIFICATIONS_ENABLED,
        "environment_mode": ENVIRONMENT_MODE,
        "target_ip": VPN_TARGET_IP if uses_vpn(ENVIRONMENT_MODE) else None,
        "vpn_flags_file": VPN_FLAGS_FILE,
        "vpn_connect_script": vpn_connect_script,
        "kali_container_name": session_runtime.kali_container_name,
        "session_id": session_runtime.session_id,
        "network_name": session_runtime.network_name,
        "subnet": session_runtime.subnet,
        "workspace_dir": os.path.abspath(session_runtime.workspace_dir),
        "results_dir": os.path.abspath(results_dir),
        "termination_reason": termination_reason or "unknown",
        "use_amd64_prompt": LOCAL_ARCH == "amd64",
    }
    experiment_metadata.update(build_git_provenance())

    for result in results:
        challenge_dir = os.path.join(experiment_dir, result["challenge_name"])
        os.makedirs(challenge_dir, exist_ok=True)

        # Save summary data for the challenge (without the heavy session log)
        # Note: custom_instructions available in experiment_summary.json under custom_instructions_by_challenge
        challenge_summary = {
            "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
            **{k: v for k, v in result.items() if k != "session"},
        }
        challenge_path = os.path.join(challenge_dir, "summary.json")
        with open(challenge_path, "w") as f:
            json.dump(challenge_summary, f, indent=2)

        session_data = result.get("session")
        if session_data:
            session_path = os.path.join(challenge_dir, "session.json")
            persist_session(session_data, session_path)

    # Write overall experiment summary for quick inspection
    summary_path = os.path.join(experiment_dir, "experiment_summary.json")
    with open(summary_path, "w") as f:
        json.dump({"metadata": experiment_metadata}, f, indent=2)

    print(f"💾 Results saved to {experiment_dir}")


def main():
    """Run experiments on all CTF challenges"""
    # Parse CLI args and apply overrides
    args = parse_args()
    apply_cli_overrides(args)
    session_runtime = resolve_session_runtime(args.session_id, auto_prefix=EXPERIMENT_SET_NAME)
    ensure_workspace_dir(session_runtime.workspace_dir)

    is_local = ENVIRONMENT_MODE == "local"

    print("=" * 80)
    print("CTF EXPERIMENT SUITE")
    print("=" * 80)
    print(f"Model: {MODEL_NAME}")
    print(f"CHAP: {'Enabled' if CHAP_ENABLED else 'Disabled'}")
    if CHAP_ENABLED:
        print(f"CHAP Token Base: {CHAP_TOKEN_LIMIT_BASE}")
        print(f"CHAP Auto-Trigger: {'Enabled' if CHAP_AUTO_TRIGGER else 'Disabled'}")
    print(f"Max iterations: {MAX_ITERATIONS}")
    print(f"Max cost per challenge: ${MAX_COST}")
    print(f"Environment: {ENVIRONMENT_MODE}")
    if is_local:
        print(f"Challenges: {len(CTF_CHALLENGES)}")
    else:
        print(f"Target: {VPN_TARGET_IP}")
        if VPN_FLAGS_FILE:
            print(f"Flags file: {VPN_FLAGS_FILE}")
    print(f"Experiment name: {EXPERIMENT_SET_NAME}")
    print(f"Session ID: {session_runtime.session_id}")
    print(f"Kali container: {session_runtime.kali_container_name}")
    print(f"Network: {session_runtime.network_name} ({session_runtime.subnet})")
    print(f"Workspace: {session_runtime.workspace_dir}")
    print("=" * 80)

    # Validate VPN configuration
    if not is_local and not VPN_TARGET_IP:
        print("ERROR: --target-ip is required when environment is not 'local'")
        sys.exit(1)

    if not is_local:
        import ipaddress

        try:
            ipaddress.ip_address(VPN_TARGET_IP)
        except ValueError:
            print(f"ERROR: --target-ip must be a single valid IP address, got '{VPN_TARGET_IP}'")
            print("  For IP ranges or extra target info, use custom instructions instead.")
            sys.exit(1)

    if TEST_RUN and not is_local:
        print(f"ERROR: TEST_RUN=True is not supported for environment '{ENVIRONMENT_MODE}'.")
        print("  Test hints do not exist for VPN/remote targets. Set TEST_RUN=False or use --environment local.")
        sys.exit(1)

    # VPN mode: start Kali, connect VPN before the challenge loop
    vpn_container = None
    vpn_connect_script = None
    flag_entries: list = []
    challenges_to_run = CTF_CHALLENGES if is_local else [EXPERIMENT_SET_NAME]
    results: list = []
    experiment_id = generate_run_id()
    discord_experiment_id = f"{EXPERIMENT_SET_NAME}-{experiment_id}" if EXPERIMENT_SET_NAME else experiment_id
    results_dir = os.path.join(RESULTS_DIR, EXPERIMENT_SET_NAME) if EXPERIMENT_SET_NAME else RESULTS_DIR
    experiment_dir = os.path.join(results_dir, f"experiment_{experiment_id}")
    os.makedirs(experiment_dir, exist_ok=True)
    termination_reason = "in_progress"
    total_challenges = len(challenges_to_run)
    channel_id = None

    try:
        print(f"\n🌐 Ensuring Docker network '{session_runtime.network_name}' is available...")
        session_runtime.subnet = start_network(
            session_runtime.network_name,
            session_runtime.subnet or "",
            subnet_candidates=session_runtime.subnet_candidates,
        )

        if not is_local:
            kali_ok = start_kali_container_standalone(
                session_runtime.kali_container_name,
                session_runtime.network_name,
                session_runtime.workspace_dir,
            )
            if not kali_ok:
                raise RuntimeError("Failed to start Kali container")
            _, vpn_container = connect_to_docker(session_runtime.kali_container_name)
            if vpn_container is None:
                raise RuntimeError("Failed to get Kali container handle")

            scripts = discover_vpn_scripts(vpn_container, ENVIRONMENT_MODE)
            vpn_connect_script = select_vpn_connect_script(scripts, VPN_CONNECT_SCRIPT)
            if vpn_connect_script:
                print(f"🔌 Using VPN connect script: {vpn_connect_script}")

            if not connect_vpn(vpn_container, ENVIRONMENT_MODE, vpn_connect_script):
                raise RuntimeError("VPN connection failed")

        # Load flags from file for VPN mode (if provided)
        if not is_local and VPN_FLAGS_FILE:
            flag_entries = load_flags_file(VPN_FLAGS_FILE)
            print(f"\n🏁 Loaded {len(flag_entries)} flag(s) from {VPN_FLAGS_FILE}")
        elif not is_local:
            print("\n⚠️  No --vpn-flags-file provided — flag validation will be skipped")

        save_results(
            results, results_dir, session_runtime, challenges_to_run,
            experiment_dir, experiment_id, termination_reason, vpn_connect_script,
        )

        if DISCORD_NOTIFICATIONS_ENABLED:
            channel_id = create_experiment_channel(discord_experiment_id)
            if not channel_id:
                print("⚠️  Failed to create Discord channel. Continuing without Discord notifications.")
                print("   To enable: set DISCORD_MAIN_BOT_TOKEN, DISCORD_GUILD_ID in .env")
            else:
                send_experiment_start_message(
                    channel_id=channel_id,
                    experiment_id=experiment_id,
                    config={
                        "model": MODEL_NAME,
                        "chap_enabled": CHAP_ENABLED,
                        "challenges": challenges_to_run,
                        "max_iterations": MAX_ITERATIONS,
                        "max_cost": MAX_COST,
                    },
                )
        for idx, challenge in enumerate(challenges_to_run, 1):
            print(f"\n{'=' * 80}")
            print(f"Challenge {idx}/{total_challenges}: {challenge}")
            print(f"{'=' * 80}")
            challenge_container_name = session_runtime.challenge_container_name(challenge) if is_local else None
            target_ip = ""

            send_challenge_start_message(channel_id=channel_id, challenge=challenge, index=idx, total=total_challenges)

            try:
                if is_local:
                    # Start vulnerable container
                    print(f"\n📦 Starting vulnerable container: {challenge}")
                    target_ip = start_challenge_container_standalone(
                        challenge_name=challenge,
                        container_name=challenge_container_name,
                        network_name=session_runtime.network_name,
                    )
                    print(f"✅ Container started at {target_ip}")

                    current_time = datetime.now().strftime("%H:%M:%S %Y-%m-%d")
                    print(f"🕒 Current time: {current_time}")

                    print(f"⏳ Waiting {SERVICE_STARTUP_DELAY}s for service to initialize...")
                    time.sleep(SERVICE_STARTUP_DELAY)
                    print("✅ Proceeding with challenge")
                else:
                    target_ip = VPN_TARGET_IP
                    print(f"\n🌐 VPN mode: targeting {target_ip}")

                # In local mode, start Kali per-challenge. In VPN mode it's already running.
                if is_local:
                    kali_ok = start_kali_container_standalone(
                        session_runtime.kali_container_name,
                        session_runtime.network_name,
                        session_runtime.workspace_dir,
                    )
                    if not kali_ok:
                        send_docker_connection_error_message(
                            channel_id=channel_id,
                            container_name=session_runtime.kali_container_name,
                            context={"challenge": challenge, "experiment_id": experiment_id},
                        )
                        raise Exception("Failed to start Kali container")

                # Load expected flags
                if not is_local and flag_entries:
                    expected_flags = [entry.flag for entry in flag_entries]
                elif is_local and challenge == "vm10":
                    flag_file_path = os.path.join(LOCAL_FLAG_DIR, challenge, "flag.txt")
                    try:
                        with open(flag_file_path) as f:
                            full_key = f.read().strip()
                        expected_flags = [full_key]
                        print(f"🔑 Loaded RSA private key ({len(full_key)} bytes)")
                    except FileNotFoundError:
                        print(f"⚠️ Flag file not found: {flag_file_path}")
                        expected_flags = None
                elif is_local:
                    expected_flags = get_expected_flag(
                        challenge_name=challenge,
                        ctf_flag_path=LOCAL_FLAG_DIR,
                    )
                else:
                    expected_flags = None

                if expected_flags:
                    if challenge != "vm10":
                        if len(expected_flags) == 1:
                            print(f"🏁 Expected flag: {expected_flags[0]}")
                        else:
                            print(f"🏁 Expected flags: {', '.join(expected_flags)}")
                else:
                    print("⚠️ No expected flag available — agent will run but validation skipped")

                challenge_dir = os.path.join(experiment_dir, challenge)
                os.makedirs(challenge_dir, exist_ok=True)

                custom_instructions = get_custom_instructions_for_challenge(challenge)

                result = run_experiment_agent(
                    experiment_id=f"{experiment_id}",
                    experiment_loop_iteration=idx,
                    total_loop_iterations=total_challenges,
                    target_ip=target_ip,
                    challenge_name=challenge,
                    model_name=MODEL_NAME,
                    chap_enabled=CHAP_ENABLED,
                    chap_auto_trigger=CHAP_AUTO_TRIGGER,
                    max_iterations=MAX_ITERATIONS,
                    command_timeout_seconds=COMMAND_TIMEOUT,
                    max_cost=MAX_COST,
                    max_output_length=MAX_OUTPUT_LENGTH,
                    chap_token_limit_base=CHAP_TOKEN_LIMIT_BASE,
                    chap_token_limit_increment=CHAP_TOKEN_LIMIT_INCREMENT,
                    chap_min_iterations_for_relay=CHAP_MIN_ITERATIONS_FOR_RELAY,
                    kali_container_name=session_runtime.kali_container_name,
                    custom_instructions=custom_instructions,
                    channel_id=channel_id,
                    local_arch=LOCAL_ARCH,
                    session_path=os.path.join(challenge_dir, "session.json"),
                    workspace_dir=session_runtime.workspace_dir,
                    environment_mode=ENVIRONMENT_MODE,
                    session_id=session_runtime.session_id,
                    network_name=session_runtime.network_name,
                    subnet=session_runtime.subnet,
                    artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
                    vpn_connect_script=vpn_connect_script,
                )

                result["challenge_name"] = challenge
                result["mode"] = "experiment_script"
                result["target_ip"] = result.get("target_ip") or target_ip
                result["environment_mode"] = result.get("environment_mode") or ENVIRONMENT_MODE

                captured_flag = result.get("flag_captured") or ""

                if expected_flags:
                    if challenge == "vm10":
                        flag_valid = validate_rsa_key_match(captured_flag, expected_flags[0])
                    else:
                        flag_valid = flag_match(found_flag=captured_flag, ground_truth_flags=expected_flags)
                else:
                    flag_valid = None  # No flags available for validation

                result["flag_valid"] = flag_valid
                result["expected_flags"] = expected_flags

                results.append(result)

                print(f"\n{'=' * 80}")
                print(f"RESULT: {challenge}")
                print(f"{'=' * 80}")
                print(f"Flag captured: {result['flag_captured']}")
                if expected_flags:
                    print(f"Flag valid: {'✅' if result['flag_valid'] else '❌'} {result['flag_valid']}")
                print(f"Iterations: {result['iterations']}")
                print(f"Relay count: {result['relay_count']}")
                print(f"Cost: ${result['total_cost']:.4f}")
                print(f"Time: {result['total_time']:.1f}s")
                print(f"Stopping reason: {result['stopping_reason']}")
                if result["error"]:
                    print(f"Error: {result['error']}")
                print(f"{'=' * 80}")

                send_challenge_complete_message(channel_id=channel_id, challenge=challenge, result=result)
                if result.get("interrupted_by_user"):
                    raise KeyboardInterrupt

            except Exception as e:
                print(f"\n❌ Error running experiment for {challenge}: {e}")
                import traceback

                traceback.print_exc()

                send_challenge_error_message(
                    channel_id=channel_id, challenge=challenge, error_msg=str(e), experiment_id=experiment_id
                )

                results.append(
                    {
                        "mode": "experiment_script",
                        "challenge_name": challenge,
                        "target_ip": target_ip if "target_ip" in locals() else VPN_TARGET_IP,
                        "environment_mode": ENVIRONMENT_MODE,
                        "flag_captured": None,
                        "session": None,
                        "iterations": 0,
                        "relay_count": 0,
                        "relay_triggers": [],
                        "error": str(e),
                        "llm_error_details": None,
                        "cost_limit_reached": False,
                        "iteration_limit_reached": False,
                        "stopping_reason": "exception_error",
                        "total_cost": 0.0,
                        "total_time": 0.0,
                        "flag_valid": False,
                        "expected_flags": None,
                    }
                )

            finally:
                print("\n🧹 Cleaning up...")
                if is_local:
                    stop_kali_container(session_runtime.kali_container_name)
                    print(f"🧹 Stopping vulnerable container: {challenge}")
                    stop_challenge_container_standalone(challenge_container_name)

            save_results(
                results, results_dir, session_runtime, challenges_to_run,
                experiment_dir, experiment_id, termination_reason, vpn_connect_script,
            )

    except KeyboardInterrupt:
        termination_reason = "interrupted_by_user"
        print("\n⚠️ Experiment interrupted by user. Saving partial results...")
        save_results(
            results, results_dir, session_runtime, challenges_to_run,
            experiment_dir, experiment_id, termination_reason, vpn_connect_script,
        )

        send_experiment_interrupted_message(
            channel_id=channel_id, partial_results=len(results), total_challenges=total_challenges
        )

    except Exception as e:
        termination_reason = f"error: {e}"
        print(f"\n❌ Experiment aborted due to unexpected error: {e}")
        import traceback

        traceback.print_exc()
        save_results(
            results, results_dir, session_runtime, challenges_to_run,
            experiment_dir, experiment_id, termination_reason, vpn_connect_script,
        )

        send_experiment_error_message(channel_id=channel_id, error_msg=str(e), partial_results=len(results))

    else:
        termination_reason = "completed"
        save_results(
            results, results_dir, session_runtime, challenges_to_run,
            experiment_dir, experiment_id, termination_reason, vpn_connect_script,
        )

        print("\n" + "=" * 80)
        print("EXPERIMENT SUITE COMPLETE")
        print("=" * 80)
        valid_flags = sum(1 for r in results if r.get("flag_valid", False))
        failed_flags = total_challenges - valid_flags
        total_cost = sum(r.get("total_cost", 0) for r in results)
        total_time = sum(r.get("total_time", 0) for r in results)

        print(f"Total challenges: {total_challenges}")
        print(f"Successful: {valid_flags}")
        print(f"Failed: {failed_flags}")
        print(f"Total cost: ${total_cost:.4f}")
        print(f"Total time: {total_time:.1f}s")
        print("\nFlag validation:")
        print(f"  Valid flags captured: {valid_flags}/{total_challenges}")
        print("=" * 80)

        send_experiment_complete_message(
            channel_id=channel_id,
            results=results,
            metadata={
                "total_challenges": total_challenges,
                "successful": valid_flags,
                "failed": failed_flags,
                "total_cost": total_cost,
                "total_time": total_time,
                "valid_flags": valid_flags,
                "termination_reason": termination_reason,
            },
        )

    finally:
        # Cleanup runs on all exit paths: success, KeyboardInterrupt, errors, VPN setup failures
        print("\n🧹 Final cleanup...")
        if not is_local:
            if vpn_container is not None:
                disconnect_vpn(vpn_container, ENVIRONMENT_MODE, vpn_connect_script)
            stop_kali_container(session_runtime.kali_container_name)

        print(f"\n🛑 Stopping Docker network '{session_runtime.network_name}'...")
        stop_network(session_runtime.network_name)
        print("Exit.")


if __name__ == "__main__":
    main()
