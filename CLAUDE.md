# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CHAP (Context Handoff for Autonomous Penetration Testing) is a research framework for agentic pentesting. LLM agents autonomously execute bash commands in Kali Linux Docker containers against vulnerable targets. The key contribution is a relay protocol that compresses conversation history into handoff summaries, allowing fresh agent instances to continue where the previous one left off when context windows fill up.

Published at NDSS Workshop LAST-X 2026.

## Commands

```bash
# Setup
uv venv && source .venv/bin/activate && uv sync
cp .env_example .env  # then add OPENROUTER_API_KEY

# Build containers
docker compose build                                                    # Kali agent container
docker compose -f local_challenges/autopenbench_improved/docker-compose.yml build  # Target VMs
docker compose up -d --force-recreate                                  # Recreate Kali after compose/network changes

# Run interactive mode
uv run python main.py
uv run python main.py --session-id review-1

# Run experiments (all 11 challenges)
uv run python scripts/run_experiment.py
uv run python scripts/run_experiment.py --chap --name "chap_test" --token-base 80000
uv run python scripts/run_experiment.py --no-chap --name "baseline"
uv run python scripts/run_experiment.py --session-id batch-1
uv run python scripts/run_experiment.py --environment private --target-ip 10.0.2.88 --vpn-script vpn-connect.sh

# Tests
uv run python -m unittest discover -s tests
uv run python -m unittest tests.test_prompt_rendering
uv run python -m unittest tests.test_kali_container

# Linting and type checking
uv run ruff check .           # lint (must pass before committing)
uv run ruff check . --fix     # auto-fix lint issues
uv run ruff format .          # auto-format (optional, not yet enforced)
uv run mypy .                 # type check (must pass before committing)
```

## Linting and Type Checking

Ruff is configured in `ruff.toml`. Enabled rule sets: pycodestyle (E/W), pyflakes (F), isort (I), pyupgrade (UP), bugbear (B), simplify (SIM), and ruff-specific (RUF). Line length is 120. `local_challenges/`, `results/`, and `ctf-workspace/` are excluded. Run `uv run ruff check .` and ensure it passes before committing. See `ruff.toml` for the full ignore list and rationale.

Mypy is configured in `pyproject.toml` with `strict = true`. All functions have type hints. Run `uv run mypy .` and ensure it passes before committing. Both ruff and mypy run as pre-commit hooks.

## Git Workflow

Never commit, push, or delete branches/files without explicit user approval. When you finish a piece of work, suggest a short commit message — one line, imperative tense — and wait for the user to act on it.

## Manual Validation Before Push

Whenever you build something new, add a feature, do a refactor, or make any meaningful behavior change, do not rely on code-level tests alone before pushing. Launch the actual agent and exercise it against the relevant real target setup first: Hack The Box, Docker mode, and/or the private VPN environment as appropriate to the change. Use one environment or all of them if needed, but always do a real end-to-end run before push.

## Big Change Review

A big change is PR-bound work: a new feature, a refactor, a schema/result-format change, or any other substantive multi-file behavior change that would normally go into a pull request.

Before you stop on a big change, run a final review with a separate subagent/reviewer focused on reproducibility and entrypoint drift. That review must check:

- whether the change introduced new behavior, metadata, prompts, flags, relay state, or other information that also needs to be persisted in saved results for reproducibility
- whether `main.py`, `scripts/run_experiment.py`, and `src/experiment_utils/main_experiment_agent.py` still agree on shared agent-loop behavior, result saving expectations, and session metadata where applicable
- whether the final summary clearly says what was verified, including any tests or manual runs
- whether the `/run-experiment` and `/analyze-results` skills (`.claude/skills/`) still match the current code (prompts, result format, CLI args, experiment config)

This repo includes a Claude Code `Stop` agent hook in `.claude/settings.json` to enforce that review before Claude finishes. Do not bypass it by declaring work complete early; if the hook sends Claude back to work, treat that as a required follow-up.

## Architecture

### Two Entry Points with Shared Core Logic

- **`main.py`** - Interactive mode with user prompts for environment, model, target, CHAP settings. Intended for standalone CTF use.
- **`src/experiment_utils/main_experiment_agent.py`** (`run_experiment_agent()`) - Non-interactive experiment mode called by `scripts/run_experiment.py`. No user interaction; hard stops on cost/iteration limits.

Both files implement the same agent loop pattern: build prompts -> call LLM -> parse JSON response (`{"reasoning": "...", "shell_command": "..."}`) -> execute command in Docker container -> append output to messages -> repeat. **Changes to core agent behavior must be synced between both files, and PR-bound changes should get a final drift check against `scripts/run_experiment.py` as well.**

### Agent Loop Flow

1. Build system + user messages via `src/llm_utils/prompt_builder.py`
2. Call OpenRouter API (`src/llm_utils/openrouter.py`) which enforces JSON schema responses
3. Parse `{"reasoning", "shell_command"}` from response (with multi-strategy fallback parsing)
4. Special commands: `"exit"` terminates, `"relay"` triggers CHAP handoff
5. Execute command in Kali Docker container (`src/utils/docker_exec.py`) with timeout using a non-interactive Docker exec (`tty=False`, `stdin=False`, `demux=True`)
6. Sanitize ANSI/control noise, format labeled `[STDOUT]` / `[STDERR]` output (`src/utils/output.py`), append to message history, loop

### CHAP Relay System (`src/chap_utils/`)

When triggered (manually via `"relay"` command or automatically at token threshold):

1. **`protocol_generator.py`** - Sends full conversation history to LLM with a dedicated system prompt to generate a compact markdown summary
2. **`relay_handler.py`** - Orchestrates: generate protocol -> save to session -> increment agent number -> build fresh messages with all accumulated protocols injected
3. **`prompt_builder.py`** `build_relay_messages()` - Constructs new system+user messages with all prior protocols embedded in the user prompt

Protocols accumulate without duplication. Each new agent sees all prior protocols plus the system prompt.

### Prompt System (`src/llm_utils/prompts.py`)

Three system prompt variants based on execution environment:
- **`local_aarch64`** - Kali aarch64 attacking emulated amd64 targets (typical macOS Apple Silicon setup)
- **`local_amd64`** - Native amd64 Kali and targets
- **`remote`** - VPN-connected targets (HackTheBox, private ranges)

The CHAP instructions are appended to the system prompt when enabled. The variant is selected by `_resolve_system_prompt_variant()` based on `environment_mode` and `local_arch`.

### State Management and Config

- **`src/utils/state_manager.py`** - In-memory session dict tracking: per-command token/cost breakdown, accumulated relay protocols, agent number, and replay events. The experiment runner and interactive mode persist these sessions to `results/`.
- **`src/utils/workspace.py`** - Manages workspace cleanup between runs (critical for preventing flag contamination across experiments).
- **`src/config/workspace.py`** - Resolves host workspace directories and the `/ctf-workspace` container mount. Parallel isolated runs use `ctf-workspaces/<session-id>/` on the host while still exposing `/ctf-workspace` inside Kali.
- **`src/config/session_runtime.py`** - Resolves per-session Docker resource names and subnets for `--session-id` runs.
- **`src/config/`** - Shared runtime/config data: constants (`constants.py` — Kali container name, agent loop defaults, session subnet naming), workspace rules (`workspace.py`), session runtime naming (`session_runtime.py`), and experiment instruction sets (`experiment_custom_instructions.py`).

### Experiment Harness (`scripts/run_experiment.py`)

Orchestrates running benchmark challenges sequentially. For each challenge: starts target container -> starts Kali container -> runs `run_experiment_agent()` -> validates captured flag -> saves results -> stops containers. Configuration is set via constants at top of file or CLI args. Per-challenge custom instructions live in `src/config/experiment_custom_instructions.py`. When `--session-id` is provided, the runner uses isolated Docker names, an isolated Docker network, and a private host workspace for that session. It is normal for `scripts/run_experiment.py` to have uncommitted parameter changes (model name, environment mode, target IP, etc.) — these are routine tweaks between experiment runs and do not indicate code quality issues or affect scientific validity of the final results.

### Benchmark (`local_challenges/autopenbench_improved/`)

11 CVE-based challenges (vm0-vm10) each in isolated Docker containers with a flag to capture. Flag validation uses string matching for most challenges; vm10 (Heartbleed) uses RSA key cryptographic validation (`src/experiment_utils/key_validator.py`).

## Task Tracking

`todo.md` in the repo root tracks actionable work items. When you complete a task listed there, move it to the Done section and check it off.

## Worktrees

Feature work happens in git worktrees under `~/work/AI-for-cyber/ctf-agent-worktrees/`. Each worktree has its own branch, `.venv`, and a full checkout. CLAUDE.md, AGENTS.md, todo.md, and `.env` are symlinked from the main worktree so they stay in sync.

Useful commands:
```bash
git worktree list                  # show all worktrees
git worktree add <path> -b <branch>  # create a new one
git worktree remove <path>         # clean up after merging
```

When launching Claude Code in a worktree, `cd` into it first so it picks up the right branch and file state. Each worktree is independent — edits in one don't affect others.

### Worktree Rules

- **Do NOT use the Agent tool's `isolation: "worktree"` parameter.** It creates auto-named branches like `worktree-agent-a0403f31` that are meaningless and clutter the repo.
- Instead, create or reuse worktrees manually under `~/work/AI-for-cyber/ctf-agent-worktrees/`.
- Before writing code for an existing PR, verify the branch first, then verify the worktree:
  ```bash
  git branch -vv
  git worktree list
  cd ~/work/AI-for-cyber/ctf-agent-worktrees/<matching-worktree>
  git rev-parse --abbrev-ref HEAD
  ```
- **Never fix an existing PR from the main checkout or from `master`.** If the task is about an open PR, work in that PR branch's worktree or create one first.
- For new feature worktrees, use descriptive names under `~/work/AI-for-cyber/ctf-agent-worktrees/`:
  ```bash
  git worktree add ~/work/AI-for-cyber/ctf-agent-worktrees/<short-name> -b <descriptive-name>
  ```
- Branch names should be human-readable (e.g., `vpn-experiments`, not `worktree-agent-a0403f31`).
- **Never delete a worktree unless its feature branch has been merged into master.** Open PRs need their worktrees to stay around for continued development.
- After merging, clean up: `git worktree remove <path>` and delete the branch.

## Dependency Lockfile

Treat `uv.lock` as generated output, not as a file to hand-merge.

- If a task does not intentionally change dependencies, do not commit `uv.lock`.
- If a task does change dependencies, commit `pyproject.toml` and `uv.lock` together.
- If `uv.lock` conflicts after rebasing or merging, do not resolve the conflict markers manually. Resolve the dependency declarations first, then regenerate with:
  ```bash
  uv lock
  uv sync
  ```
- After regenerating, rerun the relevant validation commands before committing.
- If a branch picked up an incidental lockfile diff, remove it with `git restore uv.lock`.

## Refactoring and Code Review Principles

When reviewing code for cleanup or refactoring, apply these filters before making changes:

- **Rate every finding by risk before implementing.** Classify as zero-risk (mechanical, behavior-preserving), low-risk (minor logic reorganization), medium-risk (changes function signatures or persistence behavior), or high-risk (touches hot paths or multiple entry points). Only batch changes of the same risk level together.
- **Verify findings against actual code before committing to them.** Initial analysis (especially from automated review) produces false positives. Read the code to confirm the issue is real before proposing a fix.
- **Walk back recommendations honestly.** If closer inspection shows a proposed change isn't beneficial, say so and explain why — don't implement it just because it was proposed.
- **Redundant guards that prevent unnecessary work have a purpose.** An early `if not x: return` that duplicates a later check may exist to skip expensive field-building, string formatting, or embed construction. Don't remove it just because the downstream function also checks.
- **Defensive patterns may be intentional.** Double validation (e.g., path containment checks before and after sudo escalation) may be defense-in-depth. Investigate before removing.
- **Duplication across entry points is a known tradeoff.** `main.py` and `main_experiment_agent.py` share ~300 lines of similar loop logic. This is documented and intentional — extracting a shared agent loop is high-risk and requires end-to-end validation, not a casual cleanup.
- **Don't optimize what doesn't matter.** Moving two lines inside an `if` to avoid one string allocation is not worth a commit. Focus on changes that improve maintainability or prevent real bugs.

## Key Design Decisions

- **OpenRouter only**: All LLM calls go through OpenRouter API (`urllib` directly, no SDK). Model is configurable via `MODEL_NAME`. JSON structured output is enforced via `response_format` schema.
- **Docker execution split**: Commands execute inside containers via the Docker Python SDK in `src/utils/docker_exec.py`, while container and network lifecycle uses targeted `subprocess` Docker/Compose calls in `src/experiment_utils/docker_ops.py`.
- **VPN in experiments is supported**: `scripts/run_experiment.py` can run against `local`, `private`, or `htb` environments. Private/HTB runs may require `--vpn-script` when multiple connect scripts are present.
- **Default exec model is non-interactive**: bare prompt-driven commands like `ssh`, `sudo`, and `msfconsole` should use tmux or explicit non-interactive flags; the baseline executor now fails fast instead of pretending to support live input.
- **Results format**: Each run saves `session.json` (full event stream including prompts, commands, reasoning, token usage, and `session.context` with environment/target metadata), `summary.json` (metrics), and `session_summary.json`/`experiment_summary.json` (metadata including git provenance, runtime IDs, VPN script, and subnet).
- **Executor change watchlist (March 2026)**: The default command executor was changed from `tty=True, stdin=True` to `tty=False, stdin=False, demux=True`. Commands requiring interactive input now fail fast instead of hanging. If any tool produces unexpected output formatting or behavior in experiments, check whether it's TTY-dependent. Known safe: nmap, curl, msfconsole -x. Watch for: tools that detect TTY and change output format, commands that silently need stdin.
- **Canonical Kali container name**: `src/config/constants.py` defines `ctf-agent-kali` as the shared default Kali service/container name. Session-isolated runs derive unique container names and networks from `src/config/session_runtime.py`.
