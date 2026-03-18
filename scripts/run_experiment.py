#!/usr/bin/env python3
"""
Run CTF experiments on multiple challenges

Usage:
    python scripts/run_experiment.py  # Use defaults from this file
    python scripts/run_experiment.py --chap --name "chap_enabled" --token-base 80000
    python scripts/run_experiment.py --no-chap --name "chap_disabled"
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config.constants import KALI_CONTAINER_NAME, LOCAL_CHALLENGES_ROOT_STR
from src.config.experiment_custom_instructions import (
    DEFAULT_CUSTOM_INSTRUCTIONS,
    REAL_CHALLENGE_CUSTOM_INSTRUCTIONS,
    TEST_CHALLENGE_CUSTOM_INSTRUCTIONS,
)
from src.experiment_utils.docker_ops import (
    start_container,
    start_kali_container,
    start_network,
    stop_container,
    stop_kali_container,
    stop_network,
)
from src.experiment_utils.key_validator import validate_rsa_key_match
from src.experiment_utils.main_experiment_agent import run_experiment_agent
from src.experiment_utils.validate_flag import flag_match, get_expected_flag
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
from src.utils.environment import LocalArch
from src.utils.git import get_git_commit_hash
from src.utils.state_manager import (
    build_used_prompts_payload,
    persist_session,
)

# EXPERIMENT CONFIGURATION

# Toggle between test and production configurations
TEST_RUN = False  # Set to True only for test runs, OBS: gives agent solutions directly in custom instructions.

# Enable/disable per-challenge custom instructions. Recommended to keep True.
USE_CUSTOM_INSTRUCTIONS = True

# Select appropriate config based on TEST_RUN
CHALLENGE_CUSTOM_INSTRUCTIONS = TEST_CHALLENGE_CUSTOM_INSTRUCTIONS if TEST_RUN else REAL_CHALLENGE_CUSTOM_INSTRUCTIONS

CTF_FLAG_PATH = LOCAL_CHALLENGES_ROOT_STR
# Challenges to test (all VMs enabled for overnight runs)
CTF_CHALLENGES = [
    # "vm0",
    "vm1",
    # "vm2",
    # "vm3",
    # "vm4",
    # "vm5",
    # "vm6",
    # "vm7",
    # "vm8",
    # "vm9",
    # "vm10",
]

MODEL_NAME = "openrouter/hunter-alpha"
CHAP_ENABLED = False
MAX_ITERATIONS = 80
COMMAND_TIMEOUT = 220
MAX_COST = 3
MAX_OUTPUT_LENGTH = 12000

# CHAP prompt token thresholds (only used if CHAP enabled)
# Threshold increases per agent: threshold = BASE + (agent_number * INCREMENT)
CHAP_TOKEN_LIMIT_BASE = 100000
CHAP_TOKEN_LIMIT_INCREMENT = 5000

CHAP_AUTO_TRIGGER = (
    True  # If True, auto-trigger relay based on token limits; if False, only agent-initiated relay allowed
)
CHAP_MIN_ITERATIONS_FOR_RELAY = 30  # Minimum iterations before manual relay is allowed

DISCORD_NOTIFICATIONS_ENABLED = True  # Set to False, to enable you need to set DISCORD_MAIN_BOT_TOKEN and DISCORD_GUILD_ID in .env which you can get from your Discord developer portal after creating an application and bot

# Architecture-specific prompt selection for local challenge runs.
LOCAL_ARCH: LocalArch = "aarch64"
SERVICE_STARTUP_DELAY = 30

USE_PTY_MODE = False  # Set to True to use experimental PTY-based execution (interactive prompt support)

RESULTS_DIR = "./results"
EXPERIMENT_SET_NAME = "default"


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

    # PTY execution mode toggle
    pty_group = parser.add_mutually_exclusive_group()
    pty_group.add_argument("--pty", dest="use_pty", action="store_true", help="Use PTY execution mode (experimental)")
    pty_group.add_argument("--no-pty", dest="use_pty", action="store_false", help="Use standard execution mode")
    parser.set_defaults(use_pty=None)  # None means use file default

    return parser.parse_args()


def apply_cli_overrides(args):
    """Apply CLI arguments to global config variables."""
    global CHAP_ENABLED, EXPERIMENT_SET_NAME, CHAP_TOKEN_LIMIT_BASE
    global MODEL_NAME, CHAP_TOKEN_LIMIT_INCREMENT, CHAP_AUTO_TRIGGER, USE_PTY_MODE

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
    if args.use_pty is not None:
        USE_PTY_MODE = args.use_pty


def get_custom_instructions_for_challenge(challenge_name: str) -> str:
    """Get custom instructions for a specific challenge."""
    if not USE_CUSTOM_INSTRUCTIONS:
        return ""
    return CHALLENGE_CUSTOM_INSTRUCTIONS.get(challenge_name, DEFAULT_CUSTOM_INSTRUCTIONS)


def save_results(
    results: list,
    results_dir: str,
    experiment_dir: str | None = None,
    experiment_timestamp: str | None = None,
    termination_reason: str | None = None,
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
            challenge: get_custom_instructions_for_challenge(challenge) for challenge in CTF_CHALLENGES
        }
    experiment_metadata = {
        "timestamp": timestamp,
        "git_commit_hash": get_git_commit_hash(),
        "ctf_flag_path": CTF_FLAG_PATH,
        "ctf_challenges": CTF_CHALLENGES,
        "model": MODEL_NAME,
        "chap_enabled": CHAP_ENABLED,
        "challenge_count": len(CTF_CHALLENGES),
        "completed_challenges": len(results),
        "max_iterations": MAX_ITERATIONS,
        "command_timeout_seconds": COMMAND_TIMEOUT,
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
        "kali_container_name": KALI_CONTAINER_NAME,
        "results_dir": os.path.abspath(results_dir),
        "termination_reason": termination_reason or "unknown",
        "use_amd64_prompt": LOCAL_ARCH == "amd64",
    }

    for result in results:
        challenge_dir = os.path.join(experiment_dir, result["challenge_name"])
        os.makedirs(challenge_dir, exist_ok=True)

        # Save summary data for the challenge (without the heavy session log)
        # Note: custom_instructions available in experiment_summary.json under custom_instructions_by_challenge
        challenge_summary = {k: v for k, v in result.items() if k != "session"}
        challenge_path = os.path.join(challenge_dir, "summary.json")
        with open(challenge_path, "w") as f:
            json.dump(challenge_summary, f, indent=2)

        session_data = result.get("session")
        if session_data:
            session_path = os.path.join(challenge_dir, "session.json")
            persist_session(session_data, session_path)

            prompt_payload = build_used_prompts_payload(
                session_data,
                mode="experiment_script",
                challenge_name=result.get("challenge_name"),
            )
            prompt_path = os.path.join(challenge_dir, "used_prompts.json")
            with open(prompt_path, "w") as f:
                json.dump(prompt_payload, f, indent=2)
                f.write("\n")

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

    print("=" * 80)
    print("CTF EXPERIMENT SUITE")
    print("=" * 80)
    print(f"Model: {MODEL_NAME}")
    print(f"CHAP: {'Enabled' if CHAP_ENABLED else 'Disabled'}")
    if CHAP_ENABLED:
        print(f"CHAP Token Base: {CHAP_TOKEN_LIMIT_BASE}")
        print(f"CHAP Auto-Trigger: {'Enabled' if CHAP_AUTO_TRIGGER else 'Disabled'}")
    print(f"Challenges: {len(CTF_CHALLENGES)}")
    print(f"Max iterations: {MAX_ITERATIONS}")
    print(f"Max cost per challenge: ${MAX_COST}")
    print(f"Experiment name: {EXPERIMENT_SET_NAME}")
    print("=" * 80)

    print("\n🌐 Ensuring Docker network is available...")
    start_network()

    results = []
    experiment_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    discord_experiment_id = f"{EXPERIMENT_SET_NAME}-{experiment_id}" if EXPERIMENT_SET_NAME else experiment_id
    results_dir = os.path.join(RESULTS_DIR, EXPERIMENT_SET_NAME) if EXPERIMENT_SET_NAME else RESULTS_DIR
    experiment_dir = os.path.join(results_dir, f"experiment_{experiment_id}")
    os.makedirs(experiment_dir, exist_ok=True)
    termination_reason = "in_progress"
    save_results(results, results_dir, experiment_dir, experiment_id, termination_reason)
    total_challenges = len(CTF_CHALLENGES)

    channel_id = None
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
                    "challenges": CTF_CHALLENGES,
                    "max_iterations": MAX_ITERATIONS,
                    "max_cost": MAX_COST,
                },
            )

    try:
        for idx, challenge in enumerate(CTF_CHALLENGES, 1):
            print(f"\n{'=' * 80}")
            print(f"Challenge {idx}/{total_challenges}: {challenge}")
            print(f"{'=' * 80}")

            send_challenge_start_message(channel_id=channel_id, challenge=challenge, index=idx, total=total_challenges)

            try:
                # Start vulnerable container
                print(f"\n📦 Starting vulnerable container: {challenge}")
                target_ip = start_container(challenge)
                print(f"✅ Container started at {target_ip}")

                current_time = datetime.now().strftime("%H:%M:%S %Y-%m-%d")
                print(f"🕒 Current time: {current_time}")

                print(f"⏳ Waiting {SERVICE_STARTUP_DELAY}s for service to initialize...")
                time.sleep(SERVICE_STARTUP_DELAY)
                print("✅ Proceeding with challenge")

                if not start_kali_container(KALI_CONTAINER_NAME):
                    send_docker_connection_error_message(
                        channel_id=channel_id,
                        container_name=KALI_CONTAINER_NAME,
                        context={"challenge": challenge, "experiment_id": experiment_id},
                    )
                    raise Exception("Failed to start Kali container")

                if challenge == "vm10":
                    flag_file_path = os.path.join(CTF_FLAG_PATH, challenge, "flag.txt")
                    try:
                        with open(flag_file_path) as f:
                            full_key = f.read().strip()
                        expected_flags = [full_key]
                        print(f"🔑 Loaded RSA private key ({len(full_key)} bytes)")
                    except FileNotFoundError:
                        print(f"⚠️ Flag file not found: {flag_file_path}")
                        expected_flags = None
                else:
                    expected_flags = get_expected_flag(
                        challenge_name=challenge,
                        ctf_flag_path=CTF_FLAG_PATH,
                    )

                if expected_flags:
                    if challenge != "vm10":
                        if len(expected_flags) == 1:
                            print(f"🏁 Expected flag: {expected_flags[0]}")
                        else:
                            print(f"🏁 Expected flags: {', '.join(expected_flags)}")
                else:
                    print("⚠️ No expected flag available for validation")
                    continue

                challenge_dir = os.path.join(experiment_dir, challenge)
                os.makedirs(challenge_dir, exist_ok=True)

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
                    kali_container_name=KALI_CONTAINER_NAME,
                    custom_instructions=get_custom_instructions_for_challenge(challenge),
                    channel_id=channel_id,
                    local_arch=LOCAL_ARCH,
                    session_path=os.path.join(challenge_dir, "session.json"),
                    use_pty=USE_PTY_MODE,
                )

                result["challenge_name"] = challenge
                result["mode"] = "experiment_script"

                captured_flag = result.get("flag_captured") or ""

                if challenge == "vm10":
                    flag_valid = validate_rsa_key_match(captured_flag, expected_flags[0])
                else:
                    flag_valid = flag_match(found_flag=captured_flag, ground_truth_flags=expected_flags)

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
                stop_kali_container(KALI_CONTAINER_NAME)
                print(f"🧹 Stopping vulnerable container: {challenge}")
                stop_container(challenge)

            save_results(results, results_dir, experiment_dir, experiment_id, termination_reason)

    except KeyboardInterrupt:
        termination_reason = "interrupted_by_user"
        print("\n⚠️ Experiment interrupted by user. Saving partial results...")
        save_results(results, results_dir, experiment_dir, experiment_id, termination_reason)

        send_experiment_interrupted_message(
            channel_id=channel_id, partial_results=len(results), total_challenges=total_challenges
        )

    except Exception as e:
        termination_reason = f"error: {e}"
        print(f"\n❌ Experiment aborted due to unexpected error: {e}")
        import traceback

        traceback.print_exc()
        save_results(results, results_dir, experiment_dir, experiment_id, termination_reason)

        send_experiment_error_message(channel_id=channel_id, error_msg=str(e), partial_results=len(results))

    else:
        termination_reason = "completed"
        # Save results
        save_results(results, results_dir, experiment_dir, experiment_id, termination_reason)

        # Print final summary
        print("\n" + "=" * 80)
        print("EXPERIMENT SUITE COMPLETE")
        print("=" * 80)
        print(f"Total challenges: {len(CTF_CHALLENGES)}")
        print(f"Successful: {sum(1 for r in results if r.get('flag_valid', False))}")
        print(f"Failed: {sum(1 for r in results if not r.get('flag_valid', False))}")
        print(f"Total cost: ${sum(r.get('total_cost', 0) for r in results):.4f}")
        print(f"Total time: {sum(r.get('total_time', 0) for r in results):.1f}s")

        # Flag validation summary
        valid_flags = sum(1 for r in results if r.get("flag_valid", False))
        print("\nFlag validation:")
        print(f"  Valid flags captured: {valid_flags}/{len(CTF_CHALLENGES)}")

        print("=" * 80)

        send_experiment_complete_message(
            channel_id=channel_id,
            results=results,
            metadata={
                "total_challenges": len(CTF_CHALLENGES),
                "successful": sum(1 for r in results if r.get("flag_valid", False)),
                "failed": sum(1 for r in results if not r.get("flag_valid", False)),
                "total_cost": sum(r.get("total_cost", 0) for r in results),
                "total_time": sum(r.get("total_time", 0) for r in results),
                "valid_flags": valid_flags,
                "termination_reason": termination_reason,
            },
        )

    print("\n🛑 Stopping Docker network...")
    stop_network()
    print("Exit.")


if __name__ == "__main__":
    main()
