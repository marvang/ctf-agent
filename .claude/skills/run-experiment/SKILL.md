---
name: run-experiment
description: Configure experiment parameters in scripts/run_experiment.py and display a summary for review before the user runs it manually.
argument-hint: "[challenges or target] [options like --chap, model name, environment]"
allowed-tools:
  - Read
  - Edit
  - Bash
  - Grep
  - Agent
---

The user wants to set up a CTF experiment. Your job is to configure `scripts/run_experiment.py`, present a readable summary, and give a copy-paste command. **Do NOT run the experiment.**

## Workflow

### Step 1: Gather context (parallel tool calls)

In a single message, run all three in parallel:

1. `uv run python scripts/experiment_status.py --changes-since-last` — returns JSON with:
   - `timeline` — up to 50 recent commits + last 3 experiments (oldest-first, chronological)
   - `older_commit_count` / `older_commit_messages` — commits older than the 50 shown
   - `since_last.commits` — commits after the latest experiment
   - `since_last.uncommitted_stat` — git diff stat + untracked files (lockfiles excluded)
   - `since_last.untracked_files` — new file paths not yet tracked

2. Read `scripts/run_experiment.py` lines 74-135 for current constants.

3. **Spawn a Haiku subagent** to summarize actual code changes. The agent runs the diff commands itself and returns a brief summary — keeps the diff out of main context. Prompt:
   ```
   Run these commands and return a 2-3 sentence summary of what changed in the code.
   Focus on behavioral changes, not formatting. Be very concise.

   git status --short
   git diff HEAD -- ':!uv.lock' ':!*.lock' ':!package-lock.json'
   git diff --cached -- ':!uv.lock' ':!*.lock' ':!package-lock.json'
   git ls-files --others --exclude-standard

   If ALL outputs are empty, just say "No uncommitted changes."
   Otherwise, summarize what changed — include untracked/new files if any.
   ```
   Use `model: "sonnet"` in the Agent tool.

### Step 2: Propose config (single message, phone-readable)

Present everything in one compact, scannable message.

**Format:**

```
## History
<one-liner about older commits, if any>
1. <set_name> (<Mon DD>) — <model_short>, <N>ch, <test/real>
   <N> commits
2. <set_name> (<Mon DD>) — <model_short>, <N>ch, <test/real>

## Since last run (<N> commits, <N> uncommitted files)
1. <commit summary>
2. <commit summary>
3. <uncommitted changes summary>

## Proposed Config
Purpose:      <suggested purpose>
Name:         <proposed name>
Model:        <model string>
Environment:  local
Test run:     Yes
CHAP:         Disabled
Challenges:   vm0-vm6 (7)
Parallel:     Yes (3 workers)
Limits:       $5/challenge, 100 iters, 220s timeout

Results: results/<name>/experiment_<run_id>/
```

End with: **"Ready, or change something?"**

**Rules:**
- One line per experiment, abbreviated model names (minimax-m2.7 not minimax/minimax-m2.7)
- Show commit count between experiments, not individual commit messages
- The uncommitted stat is for YOUR context — don't dump it to the user, just summarize what changed
- Number each change in "Since last run" so the user can see order: `1. Parallel mode merged. 2. Copilot review rules. 3. (uncommitted) purpose flag + experiment status script.` Group related commits, one number per logical change
- Highlight anything unusual (TEST_RUN=True on VPN, CHAP without thresholds)
- Default: inherit last experiment's config unless changes suggest otherwise
- If CHAP enabled, add token threshold line

### Step 3: User response

- **"ready"** (or similar) → reply with **ONLY** the copy-paste command. Nothing else — no prose, no explanation. User copies entire response and pastes in terminal.
  ```
  uv run python scripts/run_experiment.py --purpose "post-parallel-mode validation — copilot review rules added"
  ```
  Include only CLI flags that differ from the file constants. `--purpose` is always included.

- **User wants changes** → edit `scripts/run_experiment.py` constants, re-present the config summary, ask "Ready, or change something?" again. No command yet.

- **User wants to see the diff** → run `git diff HEAD -- ':!uv.lock' ':!*.lock'` and show relevant parts. Then re-present the config or adjust based on what they saw.

## Experiment Name (`EXPERIMENT_SET_NAME`)

Results subdirectory: `results/<name>/experiment_<run_id>/`. Propose based on context:
- New feature → `feat-<feature>-smoke`
- Refactor → `post-refactor-validation`
- Test run → `test-<model>`
- Real experiment → `baseline-<model>` or `chap-<model>`

## Available Models

| Short name | Model string | Notes |
|------------|-------------|-------|
| claude sonnet | `anthropic/claude-sonnet-4.6` | Paid |
| claude opus | `anthropic/claude-opus-4.6` | Paid |
| gpt-5.4-mini | `openai/gpt-5.4-mini` | Paid |
| minimax 2.5 | `minimax/minimax-m2.5:free` | Free |
| minimax 2.7 | `minimax/minimax-m2.7` | Paid |
| dolphin mistral | `cognitivecomputations/dolphin-mistral-24b-venice-edition:free` | Free |
| mimo | `xiaomi/mimo-v2-pro` | Paid |

If user mentions a new model, use it and update this list.

## Configuration Constants (edit in file)

Top of `scripts/run_experiment.py`:
- `CTF_CHALLENGES` — comment/uncomment vm0-vm10
- `MODEL_NAME` — model string
- `ENVIRONMENT_MODE` — `"local"`, `"private"`, `"htb"`
- `TEST_RUN` — `True` gives solutions (local), `False` real
- `CHAP_ENABLED` — relay protocol toggle
- `EXPERIMENT_SET_NAME` — results subdirectory
- `EXPERIMENT_PURPOSE` — prefer `--purpose` CLI flag
- `MAX_COST`, `MAX_ITERATIONS`, `COMMAND_TIMEOUT`
- `PARALLEL_MODE`, `MAX_PARALLEL_WORKERS`
