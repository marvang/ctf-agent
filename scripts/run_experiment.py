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
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed, wait
from datetime import datetime
from typing import Any

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
from src.experiment_utils.validate_flag import (
    FlagEntry,
    all_flags_match,
    flag_match,
    get_expected_flag,
    load_flags_file,
)
from src.utils.docker_utils import connect_to_docker
from src.utils.environment import EnvironmentType, LocalArch, detect_local_arch, is_linux, uses_vpn
from src.utils.git import build_git_provenance
from src.utils.run_ids import generate_run_id
from src.utils.state_manager import persist_session
from src.utils.vpn import connect_vpn, disconnect_vpn, discover_vpn_scripts, select_vpn_connect_script

# EXPERIMENT CONFIGURATION

# --- Shared settings ---

GIVE_HINTS = (
    True  # Set to True only for test runs. For local: gives agent solutions. Blocked for VPN (no test hints exist).
)
USE_CUSTOM_INSTRUCTIONS = True  # Enable/disable per-challenge custom instructions. Recommended to keep True.
CHALLENGE_CUSTOM_INSTRUCTIONS = TEST_CHALLENGE_CUSTOM_INSTRUCTIONS if GIVE_HINTS else REAL_CHALLENGE_CUSTOM_INSTRUCTIONS

MODEL_NAME = "minimax/minimax-m2.7"
# Model names for quick access: anthropic/claude-sonnet-4.6, anthropic/claude-opus-4.6, openai/gpt-5.4-mini, minimax/minimax-m2.5:free, minimax/minimax-m2.7, cognitivecomputations/dolphin-mistral-24b-venice-edition:free, xiaomi/mimo-v2-pro
CHAP_ENABLED = False
MAX_ITERATIONS = 40
COMMAND_TIMEOUT = 220
MAX_COST = 1

# CHAP prompt token thresholds (only used if CHAP enabled)
# Threshold increases per agent: threshold = BASE + (agent_number * INCREMENT)
CHAP_TOKEN_LIMIT_BASE = 100000
CHAP_TOKEN_LIMIT_INCREMENT = 5000
CHAP_AUTO_TRIGGER = (
    True  # If True, auto-trigger relay based on token limits; if False, only agent-initiated relay allowed
)
CHAP_MIN_ITERATIONS_FOR_RELAY = 30  # Minimum iterations before manual relay is allowed
RESULTS_DIR = "./results"
EXPERIMENT_SET_NAME = "test-new-skills"
EXPERIMENT_PURPOSE: str | None = None  # Optional free-text purpose, saved in metadata (pass via --purpose)
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
    # "vm7",
    # "vm8",
    # "vm9",
    # "vm10",
]
LOCAL_FLAG_DIR = LOCAL_CHALLENGES_ROOT_STR  # Directory containing per-challenge flag.txt files
LOCAL_ARCH: LocalArch = detect_local_arch()  # Auto-detected; override manually if needed
SERVICE_STARTUP_DELAY = 30  # Only for local mode.
PARALLEL_MODE = True  # Run local challenges concurrently instead of sequentially.
MAX_PARALLEL_WORKERS = 3  # Max challenges to run at the same time in parallel mode.
PARALLEL_INTERRUPT_DRAIN_TIMEOUT_SECONDS = 5.0  # Wait briefly for interrupted workers to persist results.

# --- VPN/Remote mode ---

VPN_TARGET_IP = "10.0.2.88"  # Single target IP address for VPN mode (e.g., "10.0.2.88")
VPN_FLAGS_FILE: str | None = "flags_example.json"  # Path to flags JSON file for VPN mode validation
VPN_CONNECT_SCRIPT: str | None = None


def parse_args() -> argparse.Namespace:
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
    parser.add_argument(
        "--parallel",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Run all local challenges concurrently (local mode only)",
    )
    parser.add_argument("--purpose", type=str, default=None, help="Free-text experiment purpose (saved in metadata)")

    return parser.parse_args()


def apply_cli_overrides(args: argparse.Namespace) -> None:
    """Apply CLI arguments to global config variables."""
    global CHAP_ENABLED, EXPERIMENT_SET_NAME, CHAP_TOKEN_LIMIT_BASE
    global MODEL_NAME, CHAP_TOKEN_LIMIT_INCREMENT, CHAP_AUTO_TRIGGER
    global VPN_TARGET_IP, ENVIRONMENT_MODE, VPN_FLAGS_FILE, VPN_CONNECT_SCRIPT
    global PARALLEL_MODE, EXPERIMENT_PURPOSE

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
    if args.parallel is not None:
        PARALLEL_MODE = args.parallel
    if args.purpose is not None:
        EXPERIMENT_PURPOSE = args.purpose


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
    results: list[dict[str, Any]],
    results_dir: str,
    session_runtime: SessionRuntime,
    challenges: list[str],
    experiment_dir: str | None = None,
    experiment_timestamp: str | None = None,
    termination_reason: str | None = None,
    vpn_connect_script: str | None = None,
    parallel_mode: bool = False,
) -> None:
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
        "give_hints": GIVE_HINTS,
        "use_custom_instructions": USE_CUSTOM_INSTRUCTIONS,
        "custom_instructions_by_challenge": custom_instructions_map,
        "chap_token_limit_base": CHAP_TOKEN_LIMIT_BASE,
        "chap_token_limit_increment": CHAP_TOKEN_LIMIT_INCREMENT,
        "chap_auto_trigger": CHAP_AUTO_TRIGGER,
        "chap_min_iterations_for_relay": CHAP_MIN_ITERATIONS_FOR_RELAY,
        "service_startup_delay_seconds": SERVICE_STARTUP_DELAY,
        "experiment_set_name": EXPERIMENT_SET_NAME,
        "purpose": EXPERIMENT_PURPOSE,
        "environment_mode": ENVIRONMENT_MODE,
        "target_ip": VPN_TARGET_IP if uses_vpn(ENVIRONMENT_MODE) else None,
        "vpn_flags_file": VPN_FLAGS_FILE,
        "vpn_connect_script": vpn_connect_script,
        "parallel_mode": parallel_mode,
        "max_parallel_workers": MAX_PARALLEL_WORKERS if parallel_mode else 1,
        "kali_container_name": None if parallel_mode else session_runtime.kali_container_name,
        "session_id": session_runtime.session_id,
        "network_name": session_runtime.network_name,
        "subnet": session_runtime.subnet,
        "workspace_dir": None if parallel_mode else os.path.abspath(session_runtime.workspace_dir),
        "workspace_root_dir": os.path.abspath(session_runtime.workspace_dir),
        "results_dir": os.path.abspath(results_dir),
        "termination_reason": termination_reason or "unknown",
        "use_amd64_prompt": LOCAL_ARCH == "amd64",
    }
    if parallel_mode:
        results_by_challenge = {result["challenge_name"]: result for result in results if result.get("challenge_name")}
        experiment_metadata["challenge_runtime_by_challenge"] = {
            challenge: {
                "session_id": results_by_challenge.get(challenge, {}).get("session_id", session_runtime.session_id),
                "network_name": results_by_challenge.get(challenge, {}).get(
                    "network_name", session_runtime.network_name
                ),
                "subnet": results_by_challenge.get(challenge, {}).get("subnet", session_runtime.subnet),
                "kali_container_name": results_by_challenge.get(challenge, {}).get(
                    "kali_container_name", session_runtime.parallel_kali_name(challenge)
                ),
                "workspace_dir": results_by_challenge.get(challenge, {}).get(
                    "workspace_dir", os.path.abspath(os.path.join(session_runtime.workspace_dir, challenge))
                ),
            }
            for challenge in challenges
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



def _append_parallel_result(
    future: Future[dict[str, Any]],
    challenge_name: str,
    results: list[dict[str, Any]],
    results_lock: threading.Lock,
    recorded_futures: set[Future[dict[str, Any]]],
) -> bool:
    """Append a finished parallel result exactly once."""
    if future in recorded_futures or not future.done() or future.cancelled():
        return False

    result = future.result()
    with results_lock:
        results.append(result)
    recorded_futures.add(future)
    return True


def _collect_completed_parallel_results(
    futures: dict[Future[dict[str, Any]], str],
    results: list[dict[str, Any]],
    results_lock: threading.Lock,
    recorded_futures: set[Future[dict[str, Any]]],
    total_challenges: int,
) -> int:
    """Harvest any completed parallel futures that have not yet been recorded."""
    appended = 0
    for future, challenge_name in futures.items():
        if _append_parallel_result(future, challenge_name, results, results_lock, recorded_futures):
            appended += 1
            print(f"✅ [{challenge_name}] Complete ({len(results)}/{total_challenges})")
    return appended


def _stop_parallel_challenge_resources(challenges: list[str], session_runtime: SessionRuntime) -> None:
    """Best-effort cleanup for all per-challenge resources in parallel mode."""
    for challenge in challenges:
        kali_name = session_runtime.parallel_kali_name(challenge)
        container_name = session_runtime.challenge_container_name(challenge)
        network_name = session_runtime.parallel_network_name(challenge)
        try:
            stop_kali_container(kali_name, quiet=True)
        except Exception:
            pass
        try:
            stop_challenge_container_standalone(container_name)
        except Exception:
            pass
        try:
            stop_network(network_name)
        except Exception:
            pass


def _drain_parallel_results_after_interrupt(
    futures: dict[Future[dict[str, Any]], str],
    results: list[dict[str, Any]],
    results_lock: threading.Lock,
    recorded_futures: set[Future[dict[str, Any]]],
    total_challenges: int,
    timeout_seconds: float = PARALLEL_INTERRUPT_DRAIN_TIMEOUT_SECONDS,
) -> None:
    """Collect results that finish promptly after an interrupt-triggered shutdown."""
    _collect_completed_parallel_results(
        futures,
        results,
        results_lock,
        recorded_futures,
        total_challenges,
    )

    pending_futures = [
        future for future in futures if future not in recorded_futures and not future.cancelled() and not future.done()
    ]
    if not pending_futures:
        return

    _, not_done = wait(pending_futures, timeout=timeout_seconds)
    _collect_completed_parallel_results(
        futures,
        results,
        results_lock,
        recorded_futures,
        total_challenges,
    )

    if not_done:
        print(
            f"⚠️  {len(not_done)} challenge(s) still shutting down after interrupt; saving the results collected so far."
        )


def run_single_challenge(
    challenge: str,
    idx: int,
    total: int,
    session_runtime: SessionRuntime,
    experiment_dir: str,
    experiment_id: str,
    vpn_connect_script: str | None,
    flag_entries: list[FlagEntry],
    is_local: bool,
    parallel: bool = False,
) -> dict[str, Any]:
    """Run a single challenge and return the result dict.

    In parallel mode, each challenge gets its own Kali container and workspace
    to avoid interference between concurrent runs.
    """
    challenge_container_name: str = session_runtime.challenge_container_name(challenge) if is_local else ""
    kali_name = session_runtime.parallel_kali_name(challenge) if parallel else session_runtime.kali_container_name
    workspace_dir = session_runtime.challenge_workspace_dir(challenge) if parallel else session_runtime.workspace_dir
    target_ip = ""

    # In parallel mode, each challenge gets its own isolated Docker network
    if parallel:
        challenge_network = session_runtime.parallel_network_name(challenge)
        challenge_subnet_candidates = session_runtime.parallel_subnet_candidates(challenge)
    else:
        challenge_network = session_runtime.network_name
        challenge_subnet_candidates = ()

    try:
        if is_local and parallel:
            print(f"\n🌐 [{challenge}] Creating isolated network '{challenge_network}'...")
            challenge_subnet = start_network(
                challenge_network,
                challenge_subnet_candidates[0] if challenge_subnet_candidates else "",
                subnet_candidates=list(challenge_subnet_candidates),
            )
            print(f"✅ [{challenge}] Network ready (subnet {challenge_subnet})")

        if is_local:
            print(f"\n📦 [{challenge}] Starting vulnerable container")
            target_ip = start_challenge_container_standalone(
                challenge_name=challenge,
                container_name=challenge_container_name,
                network_name=challenge_network,
            )
            print(f"✅ [{challenge}] Container started at {target_ip}")

            current_time = datetime.now().strftime("%H:%M:%S %Y-%m-%d")
            print(f"🕒 [{challenge}] {current_time}")

            print(f"⏳ [{challenge}] Waiting {SERVICE_STARTUP_DELAY}s for service init...")
            time.sleep(SERVICE_STARTUP_DELAY)
            print(f"✅ [{challenge}] Proceeding")
        else:
            target_ip = VPN_TARGET_IP
            print(f"\n🌐 [{challenge}] VPN mode: targeting {target_ip}")

        if is_local:
            kali_ok = start_kali_container_standalone(
                kali_name,
                challenge_network,
                workspace_dir,
                include_host_ports=not parallel,
                quiet=True,
            )
            if not kali_ok:
                raise Exception(f"Failed to start Kali container {kali_name}")

        # Load expected flags
        if not is_local and flag_entries:
            expected_flags: list[str] | None = [entry.flag for entry in flag_entries]
        elif is_local and challenge == "vm10":
            flag_file_path = os.path.join(LOCAL_FLAG_DIR, challenge, "flag.txt")
            try:
                with open(flag_file_path) as f:
                    full_key = f.read().strip()
                expected_flags = [full_key]
                print(f"🔑 [{challenge}] Loaded RSA private key ({len(full_key)} bytes)")
            except FileNotFoundError:
                print(f"⚠️ [{challenge}] Flag file not found: {flag_file_path}")
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
                    print(f"🏁 [{challenge}] Expected flag: {expected_flags[0]}")
                else:
                    print(f"🏁 [{challenge}] Expected flags: {', '.join(expected_flags)}")
        else:
            print(f"⚠️ [{challenge}] No expected flag — validation skipped")

        challenge_dir = os.path.join(experiment_dir, challenge)
        os.makedirs(challenge_dir, exist_ok=True)

        custom_instructions = get_custom_instructions_for_challenge(challenge)

        result = run_experiment_agent(
            experiment_id=f"{experiment_id}",
            experiment_loop_iteration=idx,
            total_loop_iterations=total,
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
            kali_container_name=kali_name,
            custom_instructions=custom_instructions,
            local_arch=LOCAL_ARCH,
            session_path=os.path.join(challenge_dir, "session.json"),
            workspace_dir=workspace_dir,
            environment_mode=ENVIRONMENT_MODE,
            session_id=session_runtime.session_id,
            network_name=challenge_network,
            subnet=session_runtime.subnet,
            artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
            vpn_connect_script=vpn_connect_script,
        )

        result["challenge_name"] = challenge
        result["mode"] = "experiment_script"
        result["target_ip"] = result.get("target_ip") or target_ip
        result["environment_mode"] = result.get("environment_mode") or ENVIRONMENT_MODE
        result["session_id"] = session_runtime.session_id
        result["network_name"] = challenge_network
        result["subnet"] = session_runtime.subnet
        result["workspace_dir"] = os.path.abspath(workspace_dir)
        result["kali_container_name"] = kali_name

        captured_flag = result.get("flag_captured") or ""

        if expected_flags:
            if challenge == "vm10":
                flag_valid = validate_rsa_key_match(captured_flag, expected_flags[0])
            elif not is_local and len(expected_flags) > 1:
                flag_valid = all_flags_match(captured_flag, expected_flags)
            else:
                flag_valid = flag_match(found_flag=captured_flag, ground_truth_flags=expected_flags)
        else:
            flag_valid = None

        result["flag_valid"] = flag_valid
        result["expected_flags"] = expected_flags

        if result["flag_captured"] and expected_flags:
            icon = "✅" if result["flag_valid"] else "❌"
            print(f"{icon} {challenge} — flag {'valid' if result['flag_valid'] else 'invalid'}")
        elif result["flag_captured"]:
            print(f"🏴 {challenge} — flag captured (no ground truth to validate)")
        else:
            print(f"⚠️  {challenge} — no flag captured")
        return result

    except Exception as e:
        print(f"\n❌ Error running experiment for {challenge}: {e}")
        import traceback

        traceback.print_exc()

        return {
            "mode": "experiment_script",
            "challenge_name": challenge,
            "target_ip": target_ip if target_ip else VPN_TARGET_IP,
            "environment_mode": ENVIRONMENT_MODE,
            "session_id": session_runtime.session_id,
            "network_name": challenge_network,
            "subnet": session_runtime.subnet,
            "workspace_dir": os.path.abspath(workspace_dir),
            "kali_container_name": kali_name,
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
            "interrupted_by_user": False,
        }

    finally:
        if is_local:
            stop_kali_container(kali_name, quiet=True)
            stop_challenge_container_standalone(challenge_container_name)
            if parallel:
                stop_network(challenge_network)


def main() -> None:
    """Run experiments on all CTF challenges"""
    # Parse CLI args and apply overrides
    args = parse_args()
    apply_cli_overrides(args)
    session_runtime = resolve_session_runtime(args.session_id, auto_prefix=EXPERIMENT_SET_NAME)
    ensure_workspace_dir(session_runtime.workspace_dir)

    # On Linux, Docker creates root-owned files in bind mounts. Workspace cleanup
    # needs sudo to remove them. Fail fast rather than prompting mid-experiment.
    if is_linux():
        sudo_check = subprocess.run(["sudo", "-n", "true"], capture_output=True, text=True)
        if sudo_check.returncode != 0:
            print("❌ Linux detected: workspace cleanup requires sudo for Docker-owned files.")
            print("   Run 'sudo -v' first, then rerun the experiment.")
            sys.exit(1)

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
    if PARALLEL_MODE:
        print(f"Parallel: Yes ({MAX_PARALLEL_WORKERS} workers)")
    print("=" * 80)

    # Validate parallel mode
    if PARALLEL_MODE and ENVIRONMENT_MODE != "local":
        print("⚠️  PARALLEL_MODE ignored — only supported for local Docker mode. Running sequentially.")

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

    if GIVE_HINTS and not is_local:
        print(f"ERROR: GIVE_HINTS=True is not supported for environment '{ENVIRONMENT_MODE}'.")
        print("  Test hints do not exist for VPN/remote targets. Set GIVE_HINTS=False or use --environment local.")
        sys.exit(1)

    # VPN mode: start Kali, connect VPN before the challenge loop
    vpn_container = None
    vpn_connect_script = None
    flag_entries: list[FlagEntry] = []
    challenges_to_run = CTF_CHALLENGES if is_local else [EXPERIMENT_SET_NAME]
    results: list[dict[str, Any]] = []
    experiment_id = generate_run_id()
    results_dir = os.path.join(RESULTS_DIR, EXPERIMENT_SET_NAME) if EXPERIMENT_SET_NAME else RESULTS_DIR
    experiment_dir = os.path.join(results_dir, experiment_id)
    os.makedirs(experiment_dir, exist_ok=True)
    termination_reason = "in_progress"
    total_challenges = len(challenges_to_run)
    use_parallel = PARALLEL_MODE and is_local and total_challenges > 1

    try:
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
                quiet=True,
            )
            if not kali_ok:
                raise RuntimeError("Failed to start Kali container")
            _, vpn_container = connect_to_docker(session_runtime.kali_container_name)
            if vpn_container is None:
                raise RuntimeError("Failed to get Kali container handle")

            scripts = discover_vpn_scripts(vpn_container, ENVIRONMENT_MODE)
            vpn_connect_script = select_vpn_connect_script(scripts, VPN_CONNECT_SCRIPT, environment=ENVIRONMENT_MODE)

            if not connect_vpn(vpn_container, ENVIRONMENT_MODE, vpn_connect_script, quiet=True):
                raise RuntimeError("VPN connection failed")

        # Load flags from file for VPN mode (if provided)
        if not is_local and VPN_FLAGS_FILE:
            flag_entries = load_flags_file(VPN_FLAGS_FILE)
            print(f"\n🏁 Loaded {len(flag_entries)} flag(s) from {VPN_FLAGS_FILE}")
        elif not is_local:
            print("\n⚠️  No --vpn-flags-file provided — flag validation will be skipped")

        save_results(
            results,
            results_dir,
            session_runtime,
            challenges_to_run,
            experiment_dir,
            experiment_id,
            termination_reason,
            vpn_connect_script,
            parallel_mode=use_parallel,
        )
        print(f"📋 Experiment metadata saved to {experiment_dir}")
        if use_parallel:
            print(f"\n🚀 Parallel mode: {len(challenges_to_run)} challenges, {MAX_PARALLEL_WORKERS} workers")
            print(f"⚠️  This will run up to {MAX_PARALLEL_WORKERS * 2} Docker containers simultaneously")

            # Intentionally do not pre-warm sudo here. The common path uses fresh per-challenge
            # workspaces, so a startup sudo prompt would be unnecessary overhead. If reused
            # session workspaces start surfacing concurrent cleanup/sudo races, restore a
            # serialized preflight here instead of prompting inside worker threads.
            results_lock = threading.Lock()
            recorded_futures: set[Future[dict[str, Any]]] = set()
            executor = ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS)
            interrupted = False
            try:
                futures = {
                    executor.submit(
                        run_single_challenge,
                        challenge=challenge,
                        idx=idx,
                        total=total_challenges,
                        session_runtime=session_runtime,
                        experiment_dir=experiment_dir,
                        experiment_id=experiment_id,
                        vpn_connect_script=vpn_connect_script,
                        flag_entries=flag_entries,
                        is_local=is_local,
                        parallel=True,
                    ): challenge
                    for idx, challenge in enumerate(challenges_to_run, 1)
                }

                for future in as_completed(futures):
                    _append_parallel_result(
                        future,
                        futures[future],
                        results,
                        results_lock,
                        recorded_futures,
                    )
                    print(f"✅ [{futures[future]}] Complete ({len(results)}/{total_challenges})")

                    # Incremental save so monitoring tools see per-challenge
                    # summary.json and updated completed_challenges count.
                    with results_lock:
                        results_snapshot = list(results)
                    save_results(
                        results_snapshot,
                        results_dir,
                        session_runtime,
                        challenges_to_run,
                        experiment_dir,
                        experiment_id,
                        termination_reason,
                        vpn_connect_script,
                        parallel_mode=use_parallel,
                    )
                    print(f"💾 Challenge results saved to {experiment_dir}")
            except KeyboardInterrupt:
                interrupted = True
                print("\n⚠️  Interrupt received — cancelling pending challenges...")
                executor.shutdown(wait=False, cancel_futures=True)
                # Suppress further interrupts during container cleanup
                original_handler = signal.getsignal(signal.SIGINT)
                signal.signal(signal.SIGINT, signal.SIG_IGN)
                try:
                    _stop_parallel_challenge_resources(challenges_to_run, session_runtime)
                    _drain_parallel_results_after_interrupt(
                        futures,
                        results,
                        results_lock,
                        recorded_futures,
                        total_challenges,
                    )
                finally:
                    signal.signal(signal.SIGINT, original_handler)
                raise
            finally:
                executor.shutdown(wait=not interrupted, cancel_futures=interrupted)

            # Sort by challenge name for deterministic output
            results.sort(key=lambda r: r.get("challenge_name", ""))

            save_results(
                results,
                results_dir,
                session_runtime,
                challenges_to_run,
                experiment_dir,
                experiment_id,
                termination_reason,
                vpn_connect_script,
                parallel_mode=use_parallel,
            )
            print(f"💾 Challenge results saved to {experiment_dir}")

        else:
            # Sequential mode (original behavior)
            for idx, challenge in enumerate(challenges_to_run, 1):
                print(f"\n{'=' * 80}")
                print(f"Challenge {idx}/{total_challenges}: {challenge}")
                print(f"{'=' * 80}")

                result = run_single_challenge(
                    challenge=challenge,
                    idx=idx,
                    total=total_challenges,
                    session_runtime=session_runtime,
                    experiment_dir=experiment_dir,
                    experiment_id=experiment_id,
                    vpn_connect_script=vpn_connect_script,
                    flag_entries=flag_entries,
                    is_local=is_local,
                    parallel=False,
                )

                results.append(result)
                if result.get("interrupted_by_user"):
                    raise KeyboardInterrupt

                save_results(
                    results,
                    results_dir,
                    session_runtime,
                    challenges_to_run,
                    experiment_dir,
                    experiment_id,
                    termination_reason,
                    vpn_connect_script,
                    parallel_mode=use_parallel,
                )
                print(f"💾 Challenge results saved to {experiment_dir}")

    except KeyboardInterrupt:
        termination_reason = "interrupted_by_user"
        print("\n⚠️ Experiment interrupted by user. Saving partial results...")
        save_results(
            results,
            results_dir,
            session_runtime,
            challenges_to_run,
            experiment_dir,
            experiment_id,
            termination_reason,
            vpn_connect_script,
            parallel_mode=use_parallel,
        )
        print(f"💾 Partial results saved to {experiment_dir}")

    except Exception as e:
        termination_reason = f"error: {e}"
        print(f"\n❌ Experiment aborted due to unexpected error: {e}")
        import traceback

        traceback.print_exc()
        save_results(
            results,
            results_dir,
            session_runtime,
            challenges_to_run,
            experiment_dir,
            experiment_id,
            termination_reason,
            vpn_connect_script,
            parallel_mode=use_parallel,
        )
        print(f"💾 Partial results saved to {experiment_dir}")

    else:
        termination_reason = "completed"
        save_results(
            results,
            results_dir,
            session_runtime,
            challenges_to_run,
            experiment_dir,
            experiment_id,
            termination_reason,
            vpn_connect_script,
            parallel_mode=use_parallel,
        )
        print(f"💾 Final results saved to {experiment_dir}")

        print("\n" + "=" * 80)
        print("EXPERIMENT SUITE COMPLETE")
        print("=" * 80)
        valid_flags = sum(1 for r in results if r.get("flag_valid") is True)
        unvalidated_captures = sum(1 for r in results if r.get("flag_valid") is None and r.get("flag_captured"))
        failed_flags = total_challenges - valid_flags - unvalidated_captures
        total_cost = sum(r.get("total_cost", 0) for r in results)
        total_time = sum(r.get("total_time", 0) for r in results)

        print(f"Total challenges: {total_challenges}")
        print(f"Successful: {valid_flags}")
        print(f"Unvalidated captures: {unvalidated_captures}")
        print(f"Failed: {failed_flags}")
        print(f"Total cost: ${total_cost:.4f}")
        print(f"Total time: {total_time:.1f}s")
        print("\nFlag validation:")
        print(f"  Valid flags captured: {valid_flags}/{total_challenges}")
        print(f"  Unvalidated flags captured: {unvalidated_captures}/{total_challenges}")
        print("=" * 80)

    finally:
        # Cleanup runs on all exit paths: success, KeyboardInterrupt, errors, VPN setup failures
        if not is_local:
            if vpn_container is not None:
                disconnect_vpn(vpn_container, ENVIRONMENT_MODE, vpn_connect_script, quiet=True)
            stop_kali_container(session_runtime.kali_container_name, quiet=True)

        stop_network(session_runtime.network_name)


if __name__ == "__main__":
    main()
