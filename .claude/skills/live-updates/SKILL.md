---
name: live-updates
description: Live experiment monitoring — quick status checks and automatic quick summaries, readable from mobile SSH.
argument-hint: "[experiment name or 'latest']"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Agent
---

The user wants a status update on a running or recent experiment. This skill produces concise, mobile-friendly output and maintains a living `updates.md` document in the experiment directory.

**This is a research codebase where scientific rigor and reproducibility are of utmost importance.** All analysis and reporting must be accurate — do not speculate or infer results that aren't in the data.

## Workflow

### Step 1: Automatic data gathering

Run these in parallel — they are instant and deterministic:

```bash
# 1. Find running experiments (filtered — avoids dumping all history into context)
uv run python scripts/experiment_status.py --list --running-only

# If the above returns [], fall back to the most recent experiment:
# uv run python scripts/experiment_status.py --list --limit 1

# 2. Get per-challenge breakdown (after identifying the experiment)
uv run python scripts/experiment_status.py --status <experiment_dir>
```

**Experiment selection:**
- If the user provided a name argument, use `--list --limit 5` and match against `set_name` or `path`
- If no argument: use `--list --running-only`. If empty, fall back to `--list --limit 1` for the most recent.
- If multiple running experiments exist and it's ambiguous, ask the user — otherwise just proceed.

**Also read:** `<experiment_dir>/updates.md` if it exists. Parse the YAML frontmatter between `---` markers to get `challenge_state` (previous status and `last_event_index` per challenge) and `last_update` timestamp. This is your baseline — only report what changed.

### Step 2: Auto-analyze changed challenges + auto quick summaries

For each challenge that is `in_progress` OR newly `completed` since the last update (compare against `challenge_state` from updates.md), spawn an agent to produce a brief summary.

**Each agent runs the script itself** — do NOT run `--extract-recent` in the main conversation. The agent loads the data into its own context.

**Always use `model: "haiku"`.** Scale iteration window by active session count:
- **1-2 active sessions**: `--tail-iterations 40`
- **3-5 active sessions**: `--tail-iterations 25`
- **6+ active sessions**: `--tail-iterations 15`

**Spawn all agents in a single message** for parallelism. Each agent should:

1. Run `--extract-recent` to get compact events (reasoning, commands, outputs only — no token stats or metadata):
   ```bash
   uv run python scripts/experiment_status.py --extract-recent <experiment_dir>/<challenge>/session.json --tail-iterations <N>
   ```
2. Read the extracted events and produce a summary of what approach the agent is taking, what it found, where it's stuck (if applicable).
3. Return just the summary text — nothing else.

Example agent prompt:
```
Run this command and analyze the output:
uv run python scripts/experiment_status.py --extract-recent <path>/session.json --tail-iterations <N>

Produce a summary of what the CTF agent is doing and how it's progressing.
Be factual — only report what's in the data. Return ONLY the summary text.
```

**Skip challenges that are `not_started` or unchanged since last update.**

**Auto quick summaries (up to 2):**

In addition to the per-challenge `→` one-liner summaries in the status table, automatically launch quick summaries for up to 2 challenges — no need to ask the user first:

- If only 1-2 challenges changed since last update: summarize all of them
- If 3+ changed: pick 2, preferring challenges not previously summarized (check `updates.md` challenge_state for existing `last_event_index`). If all are new, pick randomly.
- These use the same haiku agents as above — just include the quick summary request in the same agent prompt.

### Step 3: Print update with summaries

Print a concise terminal update. Keep lines under 60 characters for mobile readability:

```
## post-merge-parallel (minimax-m2.7)
5/11 done | 3 running | 3 queued

DONE  vm0  flag:valid  11i  $0.02  102s
  → Exploited CVE via metasploit, got flag
[NEW] DONE  vm4  flag:no  100i  $0.45  600s
  → Tried SQLi extensively, hit iteration limit
RUN   vm5  62 evts  $0.12  8k tok
  → Running dirb on port 8080, found /admin
RUN   vm7  30 evts  $0.04  4k tok
  → Setting up msfconsole for shellshock
---   vm8  queued
```

Use these status tags: `DONE`, `RUN`, `ERR`, `STOP`, `---` (queued).
Mark changed items with `[NEW]`.
For completed challenges: show flag validity, iterations, cost, time.
For in-progress: show event count, cost, token count (actual values from metrics — no `~` prefix).
The `→` line is the agent's summary for that challenge.

**Flag display:** Challenges may have multiple flags (especially VPN mode with up to ~26 flags per challenge). Show flag count when >1: `flag:3/26` or `flag:valid(3)`. For single-flag challenges, use the existing `flag:valid` / `flag:no` format.

**Then print quick summaries inline.** Scale detail to the number of summaries:

- **1-2 summaries**: print the full agent output (the 2-4 sentence summary)
- **3-5 summaries**: truncate to 1-2 sentences each
- **6+ summaries**: truncate to 1 sentence each

After summaries, list what was covered:
```
Summarized: vm3, vm7. Others available: vm0, vm1, vm4.
```

If no others are available (all were summarized), skip the "Others available" line.

**Then ask:** `More summaries? Deep dive? Save updates.md? (or 'no')`

### Step 4: Persist to updates.md (only if user wants)

**Do NOT write updates.md in the same turn as the status output.** The user should see the status immediately. Only write updates.md if the user asks for it (responds with "save", "write", "yes" to the updates.md prompt, or similar). If the user just moves on, that's fine — the output was already printed.

`updates.md` is a **living document** — always rewrite the entire file with a single Write call (never multiple Edits).

- Update YAML frontmatter with current `challenge_state` for all challenges
- Rewrite the `## Status` section to show current state (including summaries)
- Keep relevant historical notes in a `## Notes` section (e.g. "vm3 crashed at iteration 42", "vm0 completed at 16:30")
- Truncate notes that are no longer relevant
- Summary/deep dive links go in a `## Summaries` section pointing to separate files

**Format:**

```markdown
---
experiment: <experiment_dir_path>
last_update: <ISO-8601 UTC timestamp>
challenge_state:
  vm0: {status: completed, last_event_index: 30, flag_valid: true}
  vm1: {status: in_progress, last_event_index: 48}
  vm2: {status: not_started, last_event_index: -1}
---

# Experiment: <set_name> / <timestamp>

Model: <model> | CHAP: on/off | Test: yes/no | Parallel: yes/no

## Status (updated HH:MM)

X/Y done | Z running | W queued

DONE  vm0  flag:valid  11i  $0.02  102s
  → Exploited CVE via metasploit, got flag
RUN   vm1  48 evts  6k tok
  → Scanning with nmap, found SSH on non-standard port
---   vm2  queued

## Notes
- vm1 failed flag validation despite agent claiming exit
- vm2 started at 16:45, running smoothly

## Summaries
- [vm0 summary (16:45)](summary_vm0_20260323_164500.md) — events 0-30
```

### Step 5: Deep dive (only on explicit user request)

Deep dives are longer, more detailed analysis than quick summaries. Only run when the user explicitly requests one.

**5a. Size the session:**

```bash
uv run python scripts/experiment_status.py --session-info <experiment_dir>/<challenge>/session.json
```

Print the session size: event count, total tokens, cost.

**5b. Cost check — propose a plan if expensive:**

If `total_tokens` > 50k, tell the user the size and propose options:
```
vm3: 180k tokens, 90 iterations. Options:
(a) haiku, key events only (~fast, ~cheap)
(b) haiku, last 50 iterations
(c) full read with <model> (~$X estimate)
```

The user can also request a specific model (e.g. "deep dive vm3 with sonnet"). Default is haiku.

For sessions under 50k tokens, just proceed with haiku — no need to ask.

**5c. Reading strategy** based on `total_tokens`:
- **<50k tokens**: Full session read via `--extract-recent` with full iteration count
- **50-200k tokens**: Extract key events + context:
  ```bash
  uv run python scripts/experiment_status.py --extract-key-events <session.json> --after-index <N>
  ```
- **>200k tokens**: Key events only, or chunk into segments with multiple haiku agents

**5d. Incremental analysis:**

If `updates.md` has a `last_event_index` for this challenge, use `--after-index <N>` to only analyze new events. Tell the agent what was already covered.

**5e. Spawn the agent:**

Use the Agent tool with the chosen model (default haiku). Example prompt:

```
Analyze this CTF agent session for challenge <name>.

This is a research experiment — accuracy matters. Produce a 2-4 paragraph narrative covering:
1. What exploit approach the agent took
2. Key successes and failures
3. Where the agent got stuck (if applicable)
4. Current state and likely next steps (if still running)

Keep it concise — this will be read on a mobile terminal.

[If incremental]: This is a continuation. Previous analysis covered events 0-N.
Focus on what happened after event N.

Session data:
<extracted events or full session>
```

**5f. Print result first, then persist:**

Print the deep dive to the user immediately. On the next turn, save it:

- Write the agent's report to `deep_dive_<challenge>_<timestamp>.md` in the experiment directory
- Include a header noting: event range analyzed, model used, timestamp
- Rewrite updates.md (single Write call) with updated `last_event_index` and a link in `## Summaries`

## Key Principles

- **Response before persistence** — always print status/summaries to the user first, write files on the next turn. The user is checking from mobile SSH; latency to first useful output matters more than file freshness.
- **Auto-summarize, don't gate** — up to 2 quick summaries launch automatically with the status check; user can request more
- **Scale detail to count** — full output for 1-2 summaries, truncate progressively for more
- **Never redo analysis** — read updates.md first, only process challenges that changed
- **Summaries are incremental** — `last_event_index` tracks what's been analyzed
- **updates.md is a living document** — rewrite to stay current, keep relevant history, drop stale details. Always use a single Write call, never multiple Edits.
- **Summaries and deep dives are separate files** — linked from updates.md, not embedded in it
- **Mobile-first** — concise output, narrow lines, short status tags, no wide tables
- **Deep dives need user request** — quick summaries are automatic, but deep dives (expensive, detailed) require explicit user request. If cost is high, propose options.
- **Flexible flag counts** — challenges may have 1 flag (local benchmarks) or many (VPN mode, up to ~26). Display accordingly.
- **Works for all modes** — local, VPN, parallel, sequential — the script reads whatever result files exist
