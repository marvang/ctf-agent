# Copilot Code Review Instructions

## Experiment parameter changes are not issues

It is normal for `scripts/run_experiment.py` to have changes to default parameters such as `MODEL_NAME`, `EXPERIMENT_SET_NAME`, the challenge subset list, `ENVIRONMENT_MODE`, `TARGET_IP`, or other run configuration constants. These are routine tweaks between experiment runs and do not indicate code quality issues, scope creep, or unrelated changes. Do not flag them in reviews. The same applies to commented-out challenge entries — these reflect the current test subset, not dead code.

## Scientific rigor and reproducibility

This is a research codebase targeting peer-reviewed publication. Any change that could affect experiment reproducibility, result validity, or benchmark isolation is a high-priority finding — treat it with more weight than code style or ergonomic improvements.

## Focus review on behavioral correctness

For each change, reason about what breaks downstream if this is wrong. When reviewing PRs, focus on:
- Logic errors, race conditions, and correctness issues in new or changed code
- Security concerns (command injection, path traversal, credential exposure)
- Breaking changes to the agent loop, result format, or Docker lifecycle
- Missing error handling at system boundaries (Docker API, network calls, file I/O)

Do not flag:
- Style or formatting issues (ruff handles this via pre-commit hooks)
- Type annotation choices that pass mypy strict mode
- Minor naming or wording preferences in comments, TODOs, or documentation
- Import ordering (isort is enforced by ruff)

## Project context

This is a research framework where an LLM agent autonomously executes commands in Docker containers. Two entry points share similar agent loop logic by design (`main.py` and `src/experiment_utils/main_experiment_agent.py`) — duplication between them is intentional and documented. See `CLAUDE.md` and `AGENTS.md` for full architecture details and coding guidelines.
