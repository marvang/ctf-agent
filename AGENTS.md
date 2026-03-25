# Repository Guidelines

## Project Structure & Module Organization
Core Python code lives in `src/`. `experiment_utils/` contains batch-run orchestration, Docker lifecycle helpers, flag validation, and the experiment agent loop in `main_experiment_agent.py`. `llm_utils/` handles prompt construction, response schemas, and OpenRouter calls. `chap_utils/` implements relay handoff and protocol generation. `config/` holds shared constants, workspace policy, and experiment-specific instructions. `utils/` contains reusable support code for Docker exec, VPN setup, session/state persistence, replay helpers, and CLI prompts. Use `main.py` for the interactive product-style flow, `scripts/run_experiment.py` for reproducible benchmark runs, and `scripts/replay_openrouter_messages.py` to reconstruct saved OpenRouter payloads from `session.json`. It is normal for `scripts/run_experiment.py` to have uncommitted parameter changes (model name, environment mode, target IP, etc.) — these are routine tweaks between experiment runs and should not be flagged as code quality issues. `ctf-experiment-runner/` wraps repeated overnight experiment batches. Local benchmark targets live under `local_challenges/autopenbench_improved/`, `ctf-workspace/` is the mounted runtime workspace for the Kali container, and `results/` contains generated run artifacts that should not see incidental churn.

## Build, Test, and Development Commands
Set up the environment with `uv venv`, `source .venv/bin/activate`, and `uv sync` (activation is optional if you use `uv run`). Build the Kali image with `docker compose build` and the benchmark targets with `docker compose -f local_challenges/autopenbench_improved/docker-compose.yml build`. Recreate the Kali container after Docker or network changes with `docker compose up -d --force-recreate ctf-agent-kali`. Run the interactive agent with `uv run python main.py` or `uv run python main.py --session-id <id>` for isolated parallel runs. Run a batch experiment with `uv run python scripts/run_experiment.py --chap --name local_smoke --token-base 50000`, add `--session-id <id>` for isolated parallel runs, or use `--environment private --target-ip <ip> --vpn-script <script.sh>` for non-local benchmark targets. Replay saved model calls with `uv run python scripts/replay_openrouter_messages.py <path-to-session.json> --list`. Run tests with `uv run python -m unittest discover -s tests`. Lint and format touched Python code with `uv run ruff check .` and `uv run ruff format .`. Type-check with `uv run mypy .` (strict mode, configured in `pyproject.toml`). Both ruff and mypy run as pre-commit hooks.

## Working Style
Take your time. Use extended thinking liberally, especially for non-trivial tasks. The user works asynchronously and prefers thoroughness over speed. When you touch Python code, run Ruff before finishing and do not leave new lint violations behind in the files you changed.

Do not make any code, test, config, prompt, docs, or workflow changes unless the user explicitly asks you to implement something. If the user asks for review, diagnosis, go/no-go, commit readiness, or explanation, stop at inspection and recommendations unless they clearly authorize edits.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, type hints on public helpers, concise docstrings, and `snake_case` for modules, functions, and variables. Use `PascalCase` for classes and uppercase names for constants, for example `MAX_OUTPUT_LENGTH`. Keep reusable configuration in `src/config/`, reusable logic in `src/`, and CLI wiring in `main.py`, `scripts/`, or `ctf-experiment-runner/`. A project-level `ruff.toml` is checked in; match its conventions, including double quotes, 120-character lines, and first-party imports rooted under `src`.

## Testing Guidelines
The automated suite uses `unittest`. Add tests under `tests/` with filenames like `test_<feature>.py`, and mirror the behavior of the production module you changed. Prefer focused coverage for prompt rendering, replay reconstruction, session metadata, CLI/config edge cases, and Docker lifecycle helpers that can be validated with mocks rather than long-running containers. Run `uv run python -m unittest discover -s tests` before finalizing substantial changes.

Manual end-to-end validation is also required before pushing changes. Whenever you build something new, add a feature, do a refactor, or make any meaningful behavior change, do not rely on code-level tests alone. Launch the actual agent and exercise it against the relevant real target setup before pushing: Hack The Box, Docker mode, and/or the private VPN environment as appropriate to the change. Use one environment or all of them if needed, but always do a real run before push.

## Big Change Review
A big change is PR-bound work: a new feature, a refactor, a schema/result-format change, or any other substantive multi-file behavior change that would normally go into a pull request.

Before you stop on a big change, run a final review with a separate subagent/reviewer. That review must check:

- whether the change introduced new behavior, metadata, prompts, flags, relay state, or other information that also needs to be persisted in saved results for reproducibility
- whether `main.py`, `scripts/run_experiment.py`, and `src/experiment_utils/main_experiment_agent.py` still agree on shared agent-loop behavior, result saving expectations, and session metadata where applicable
- whether the final response clearly says what was verified, including any tests or manual runs

For Claude Code, the repo includes a `.claude/settings.json` `Stop` agent hook that enforces this review before Claude finishes. In other agent environments, do this manually: spawn a dedicated reviewer subagent near the end instead of self-certifying the change.

## Task Tracking
`todo.md` in the repo root tracks actionable work items. When you complete a task listed there, move it to the Done section and check it off.

## Worktrees
Feature work uses git worktrees under `~/work/AI-for-cyber/ctf-agent-worktrees/`, one per feature branch. Each has its own `.venv` (run `uv sync` after creation). CLAUDE.md, AGENTS.md, todo.md, and `.env` are symlinked from the main repo so all worktrees share them. Run `git worktree list` to see active worktrees. When working in a worktree, commit to its feature branch; do not check out another worktree's branch.

**Never delete a worktree unless its feature branch has been merged into master.** Open PRs need their worktrees for continued development. Only clean up after the PR is merged.

Before making changes for an existing PR or feature branch, first verify which branch the PR targets and whether a matching worktree already exists. Do that before editing any files. If the task is to fix a reviewed PR on a feature branch, do not implement the fix in the main checkout or on `master`; switch to the correct feature worktree under `~/work/AI-for-cyber/ctf-agent-worktrees/`, or create one for that branch first. If the user explicitly says the fix is for `master` or explicitly instructs you to stay on `master`, follow that. If you are in the wrong checkout, stop and correct that before writing code.

Preferred verification sequence before coding:
1. `git branch -vv` or inspect the PR to identify the correct branch.
2. `git worktree list` to find the matching worktree.
3. `cd` into that worktree and verify with `git rev-parse --abbrev-ref HEAD`.

The main checkout is not the default place for PR fixes. Treat it as shared infrastructure and only use it when the task is explicitly about `master` itself or the user explicitly tells you to fix on `master`.

## Dependency Lockfile
Treat `uv.lock` as generated state, not hand-merged source.

- If a change does not intentionally modify dependencies, do not commit `uv.lock`.
- If a change does modify dependencies, commit `pyproject.toml` and `uv.lock` together.
- When `uv.lock` conflicts across worktrees or PRs, do not hand-merge it. Resolve the dependency declarations first, then regenerate with `uv lock`.
- After regenerating the lockfile, run `uv sync` and the relevant test/lint commands before committing.
- If your branch picked up an incidental `uv.lock` diff, drop it with `git restore uv.lock` before committing.

## Refactoring and Code Review Principles

When reviewing code for cleanup or refactoring:

- **Rate every finding by risk** (zero/low/medium/high) before implementing. Only batch changes of the same risk level.
- **Verify findings against actual code** before acting — initial analysis produces false positives. Read the code to confirm.
- **Walk back honestly** when closer inspection shows a change isn't worth it. Don't implement something just because it was proposed.
- **Redundant guards that prevent unnecessary work have a purpose.** Early-return checks that duplicate a downstream check may exist to skip expensive computation. Don't remove them.
- **Defensive patterns may be intentional.** Double validation (e.g., path containment before and after sudo) is defense-in-depth. Investigate before removing.
- **Duplication across entry points is a known tradeoff.** `main.py` and `main_experiment_agent.py` share similar loop logic by design. Extracting it is high-risk, not a casual cleanup.
- **Don't optimize what doesn't matter.** Focus on changes that improve maintainability or prevent real bugs, not micro-optimizations.

## Commit & Pull Request Guidelines
Recent history uses short imperative subjects without prefixes, for example `update readme` and `Remove legacy references and delete unused code`. Keep commit messages brief, specific, and action-oriented. PRs should explain the runtime or research impact, list the commands you ran, and call out any required Docker, VPN, or `.env` setup changes. Include screenshots only when updating generated figures or user-facing terminal flows.

## Executor Change Watchlist (March 2026)
The default command executor was changed from `tty=True, stdin=True` to `tty=False, stdin=False, demux=True`. Commands requiring interactive input now fail fast instead of hanging. If any tool produces unexpected output formatting or behavior in experiments, check whether it's TTY-dependent. Known safe: nmap, curl, msfconsole -x. Watch for: tools that detect TTY and change output format, commands that silently need stdin.

## Security & Configuration Tips
Copy `.env_example` to `.env` and set `OPENROUTER_API_KEY`. Never commit populated `.env` files, private VPN material under `ctf-workspace/vpn/private/`, or captured flags from `ctf-workspace/flags.txt`. Session logs and results can include prompts, command history, and model outputs, so review `results/` artifacts before sharing them externally. If a change affects reproducibility, document the expected output location under `results/`.
