---
name: run-experiment
description: Configure experiment parameters in scripts/run_experiment.py and display a summary for review before the user runs it manually.
argument-hint: "[challenges or target] [options like --chap, model name, environment]"
allowed-tools:
  - Read
  - Edit
  - Bash
  - Grep
---

The user wants to set up a CTF experiment. Your job is to configure `scripts/run_experiment.py` and present a readable summary. **Do NOT run the experiment** — the user will run `uv run python scripts/run_experiment.py` themselves.

## Workflow

1. **Understand context** — run `git log --oneline -3` and `git diff --stat HEAD` to understand what changed recently. Use this to:
   - Infer the purpose of the run (new feature smoke test? post-refactor validation? baseline measurement?)
   - Propose a good experiment name
   - If the purpose isn't clear from the diffs/commits and the user's request, **ask**: "What's the purpose of this run?" before configuring
2. **Read** the current config at the top of `scripts/run_experiment.py` (~lines 66-116)
3. **Parse** the user's intent and edit the file constants to match
4. **Determine the experiment name** (`EXPERIMENT_SET_NAME`) — see naming rules below
5. **Present a colored summary** of all configured parameters for review, including the inferred purpose
6. **Show the run command** the user should copy-paste

## Experiment Name (`EXPERIMENT_SET_NAME`)

This is the results subdirectory: `results/<name>/experiment_<run_id>/`. **Always ask the user for a name if they didn't specify one.** When asking, propose a name based on context:

- Check `git log --oneline -3` and `git diff --stat HEAD` for recent changes
- If recent commits/changes introduce a new feature → propose something like `feat-<feature>-smoke`
- If recent changes are a refactor → propose `post-refactor-validation`
- If it's a test run with solutions → propose `test-<model>` or `test-all-challenges`
- If it's a real experiment run → propose `baseline-<model>` or `chap-<model>`
- Common names: `default`, `smoke-test`, `baseline`, `chap-enabled`, `vpn-kth`
- Always explain what the name means (results directory path)

## Available Models

Use these exact OpenRouter model strings. **If the user doesn't specify a model, ask which one they want and show this list.** If the user mentions a new model not on this list, use it and update this list in the skill file.

| Short name | Model string | Notes |
|------------|-------------|-------|
| Codex sonnet | `anthropic/Codex-sonnet-4.6` | Paid |
| Codex opus | `anthropic/Codex-opus-4.6` | Paid |
| gpt-5.4-mini | `openai/gpt-5.4-mini` | Paid |
| minimax 2.5 | `minimax/minimax-m2.5:free` | Free |
| minimax 2.7 | `minimax/minimax-m2.7` | Paid |
| dolphin mistral | `cognitivecomputations/dolphin-mistral-24b-venice-edition:free` | Free |
| mimo | `xiaomi/mimo-v2-pro` | Paid |

When the user says a short name (e.g. "minimax", "Codex", "dolphin"), match to the right string. If ambiguous (e.g. "minimax" could be 2.5 or 2.7), ask.

## Configuration (edit file constants)

These are Python constants at the top of `scripts/run_experiment.py`:

- **`CTF_CHALLENGES`** list: Comment/uncomment challenge names (vm0-vm10). "all" = uncomment all.
- **`MODEL_NAME`**: Model string (e.g. `"minimax/minimax-m2.5:free"`, `"anthropic/Codex-sonnet-4-6"`)
- **`ENVIRONMENT_MODE`**: `"local"`, `"private"`, or `"htb"`
- **`TEST_RUN`**: `True` gives agent solutions (local mode), `False` for real experiments
- **`CHAP_ENABLED`**: Enable/disable CHAP relay protocol
- **`EXPERIMENT_SET_NAME`**: Results subdirectory name
- **`VPN_TARGET_IP`**: Target IP for VPN/remote mode
- **`VPN_FLAGS_FILE`**: Path to flags JSON file
- **`MAX_COST`**: Cost limit per challenge in USD
- **`MAX_ITERATIONS`**: Iteration limit
- **`COMMAND_TIMEOUT`**: Seconds before command times out

## Summary Format

After editing, present the configuration as a clear, scannable report. Use this exact format with markdown formatting for terminal readability:

```
## Experiment Configuration

**Purpose:**       Post-hardening validation — executor refactor + used_prompts removal
**Name:**          post-hardening-smoke
**Environment:**   local
**Model:**         minimax/minimax-m2.5:free
**Test Run:**      Yes (agent gets solutions)
**CHAP:**          Disabled
**Challenges:**    vm0, vm1, vm2, vm3, vm4, vm5, vm6, vm7, vm8, vm9, vm10 (11)

**Limits:**
  - Max cost:       $5.00/challenge
  - Max iterations: 100
  - Command timeout: 220s

**Results:** results/post-hardening-smoke/experiment_<run_id>/

---
Run with:
`uv run python scripts/run_experiment.py`
```

Highlight anything unusual — e.g. if TEST_RUN is True for a non-local environment, warn. If CHAP is enabled, show token thresholds.

## Examples

User: "set up vm3 and vm4 locally"
-> Edit CTF_CHALLENGES to uncomment vm3 and vm4, comment out rest
-> Set ENVIRONMENT_MODE = "local"
-> Ask for experiment name, propose based on context
-> Show summary

User: "set up all challenges with chap"
-> Uncomment all vm0-vm10, set CHAP_ENABLED = True
-> Ask for name
-> Show summary including CHAP token thresholds

User: "configure for KTH range at 10.0.2.88 with minimax"
-> Set MODEL_NAME, ENVIRONMENT_MODE = "private", VPN_TARGET_IP
-> Ask for name
-> Show summary
