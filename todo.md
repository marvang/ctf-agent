# TODO

## Backlog

### Extract shared agent loop from main.py and main_experiment_agent.py
~300 lines of near-identical loop logic (command tagging, empty retries, relay triggering, token thresholds, exit/relay detection). Extract into a shared module with callbacks for interactive/experiment-specific behavior. High impact but high risk — needs careful testing. Subsumes ~15 smaller duplication findings between the two files.

### Group `run_experiment_agent()` parameters into dataclasses
18 scalar parameters covering CHAP config, Docker names, workspace, and environment. Group into config dataclasses (`CHAPConfig`, `DockerConfig`, `WorkspaceConfig`) to reduce call-site errors and improve API clarity.

### Multi-host target metadata/schema (future)
Keep the current run metadata as-is for now, but design a richer target-scope representation later so benchmark artifacts can describe multi-host environments, pivots, and allowed ranges without overloading `target_ip`.

### Inject flag signatures into VPN agent custom instructions
`build_flag_hint_text()` exists in `validate_flag.py` but is currently unused. When real flags are available (not dummy), inject flag signatures into the agent's custom instructions so it knows what to look for. Currently disabled to avoid confusing the agent with dummy flag signatures during testing.

### Modular experiment runner (single-challenge + batch)
Refactor `scripts/run_experiment.py` into two scripts: one for single-challenge runs (both local and VPN), and one for batch orchestration (local Docker challenges). The single-challenge script would be the core, and the batch script would call it in a loop. This would simplify the if/else branching between local and VPN modes and allow VPN batch runs in the future.

### Auto-analysis hook for experiment runs
Create a Claude Code hook that triggers after `scripts/run_experiment.py` completes. The hook should automatically run the `/analyze-results` skill on the finished experiment and write the analysis as markdown files: an `analysis.md` next to `experiment_summary.json` with the overview table and aggregate stats, and a per-challenge `analysis.md` inside each challenge directory with detailed failure/success analysis from session.json inspection.

### Parallel local experiment mode — run all Docker challenges concurrently
Add a `PARALLEL_MODE` constant and `--parallel` flag to `scripts/run_experiment.py` that runs all 11 local Docker challenges at the same time instead of sequentially. Each challenge would get its own session-scoped resources (Kali container, challenge container, network, workspace) — essentially auto-generating a `--session-id` per challenge. This would dramatically reduce total experiment wall-clock time from ~11×T to ~1×T. Requires: auto-session-id generation per challenge, concurrent agent loops (threads or asyncio), aggregated result collection, and a resource ceiling guard (Docker memory/CPU) to avoid overloading the host.

### Human-in-the-loop (HITL)
Add a human-in-the-loop mode where the agent can pause and ask the operator for guidance during a challenge run. Useful for debugging agent behavior, providing hints on stuck challenges, and supervised runs where a human monitors progress and can intervene.

### Clean up orphaned branches and worktrees
Delete stale remote branches after their PRs are merged or closed, and prune any leftover local worktrees. Known stale branches: `worktree-agent-a0403f31` (PR #2 merged), `worktree-agent-a28f5543`, `worktree-agent-ad564b46`, `worktree-agent-a8138c8b`, `claude/research-mobile-coding-o3jPH`, `add-claude-github-actions-1773787370711`.

## In Review

### Linux compatibility — PR #4
All review issues fixed (try-unprivileged-first, path validation, portable truncation). Ready to merge.

### PTY exec model (experimental) — PR #8
Fixes applied (relay handoff, pexpect deps, empty command guard). Mergeable as experimental. Open items: parsing regression, ANSI stripping, session history, prompt contradiction.

## Done
- [x] Harden default command execution to use non-interactive `tty=False`, `stdin=False`, `demux=True` with labeled `[STDOUT]` / `[STDERR]` output and ANSI stripping
- [x] Save branch/dirty/diff provenance plus runtime metadata (VPN script, subnet, session/network/workspace identifiers) in run artifacts
- [x] Add deterministic VPN script selection for experiments and mount shared VPN material into isolated standalone Kali containers
- [x] Make isolated network creation use collision-resistant names plus subnet fallback and stop destructive shared-network disconnect behavior
- [x] Port fail-closed workspace cleanup with sudo fallback and symlink containment checks
- [x] Track `AGENTS.md`, `CLAUDE.md`, `todo.md`, and `.claude/settings.json` in git
- [x] Set up ruff linter with `ruff.toml` and fix all violations
- [x] Add linting docs to CLAUDE.md and AGENTS.md
- [x] Set up git worktrees for parallel Claude Code instances
- [x] Add pre-commit hooks for ruff (PR #2 merged)
- [x] Add type hints to all functions, enable mypy strict mode, and add the mypy pre-commit hook
- [x] Merge VPN experiment mode (PR #5)
- [x] Merge per-session Docker isolation (PR #6) with collision-resistant naming and subnet fallback
- [x] Remove legacy `used_prompts.json` — `session.json` event stream captures all prompt/metadata
- [x] Unify `MAX_OUTPUT_LENGTH` constant (12000) across entry points
- [x] Fix hardcoded container name in docker_exec.py error message
- [x] Add unit tests for `flag_match()`, `get_expected_flag()`, `truncate_output()`, `strip_ansi_escape_codes()`
