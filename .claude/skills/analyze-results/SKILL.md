---
name: analyze-results
description: Analyze experiment results from the results/ directory — summaries, metadata, flag outcomes, and session deep-dives.
argument-hint: "[experiment name or 'latest'] [challenge name] [focus area]"
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
  - Agent
---

The user wants to analyze CTF experiment results. **Before doing any analysis, you MUST follow the mandatory question flow below.** No exceptions — even if the user says "analyze latest", you still present options and ask the clarifying questions before loading any session data.

## Mandatory Question Flow

Every invocation of this skill must go through these steps in order. Do NOT skip steps. Do NOT start reading session.json or summary.json files until step 3 is complete.

**Smart skipping:** If the user provides information upfront in their /analyze-results invocation:
- Run path specified → still show the table in step 1 but pre-select and confirm ("I see you want to analyze X — confirming")
- Intent specified → skip step 2 entirely, note "Intent: [their words]"
- "with uncommitted changes" or commit hash → skip step 3, load the context directly
- Never skip step 1 (always confirm which run) but it can be a one-liner confirmation instead of a full table when the path is explicit

### Step 1: Present experiment runs

Scan `results/` and present the most recent/relevant experiment runs. Show a pick list:

```bash
# Find all experiment directories, summaries, and existing analysis artifacts
find results/ -name "experiment_summary.json" -type f
find results/ -name "analysis.md" -type f
find results/ -name "updates.md" -type f
```

Read each `experiment_summary.json` to extract: timestamp, model, challenge count, success count, termination reason, and experiment set name. Also check which runs already have `analysis.md` or `updates.md` in their directory. Then present:

```
## Recent Experiment Runs

| # | Name | When | Model | Challenges | Successes | Status | Notes |
|---|------|------|-------|------------|-----------|--------|-------|
| 1 | pre-commit-smoke | Today 3:12 PM | mimo-v2-pro | 11 | 8/11 | completed | analyzed, monitored |
| 2 | pre-commit-smoke | Yesterday 8:45 PM | minimax-m2.5:free | 11 | 6/11 | completed | monitored |
| 3 | vpn-kth | Mar 16, 7:06 PM | claude-sonnet-4.6 | 3 | 1/3 | interrupted | |

Notes column: "analyzed" if analysis.md exists, "monitored" if updates.md exists, blank if neither.

Which run(s) do you want to analyze?
- Pick by number (e.g. "1", "1 and 2" to compare)
- Or describe what you're looking for if none of these match
```

Format timestamps as relative when recent ("Today 3:12 PM", "Yesterday 8:45 PM") and absolute when older ("Mar 16, 7:06 PM"). Sort by most recent first. Show up to 8 runs. If there are more, mention how many total exist.

**STOP HERE and wait for the user's answer before proceeding.**

### Steps 2-3: Intent and code context (one stop)

After the user picks a run, ask both questions together in a single message:

```
What did you want to test with this experiment? And should I load code context?
(git diff / specific commit hash / skip)
```

**STOP HERE and wait for the user's answer before proceeding.**

This is the most important question — the entire analysis is framed around whether the experiment achieved what the user intended. Their answer might be "testing the new parallel mode", "smoke testing after a refactor", "checking if vm7 works with a different model", etc.

If the user picks git diff, run `git diff --stat HEAD` and `git diff HEAD` (or targeted file reads for large diffs).
If the user gives a commit hash, run `git show --stat <hash>` and read the relevant diffs.
If the user says skip (or their answer makes code context clearly unnecessary), proceed without it.

### Step 4: Analyze

Only NOW can you start reading experiment data and performing analysis. You have:
- Which run(s) to analyze (from step 1)
- What the user wanted to test (from step 2)
- Code context if available (from step 3)

Follow the analysis workflow below.

---

## Analysis Workflow

### Step 4a: Read small files (main thread)

1. Read `experiment_summary.json` for full metadata — note the `environment_mode` (local vs private/htb)
2. Read each challenge's `summary.json` for outcomes
3. Build the overview table (see format below)

These are tiny files, safe for the main context.

### Step 4b: Extract sessions & launch parallel agents

**CRITICAL: Never read session.json directly with the Read tool. All session analysis is done by subagents.**

For each challenge with a session.json:

1. Run the extraction script:
```bash
uv run python scripts/extract_session.py results/<run>/<challenge>/session.json --output /tmp/compact_<challenge>.json
```

2. Check compact file word count (approximates tokens):
```bash
wc -w /tmp/compact_<challenge>.json
```

Then launch agents **in parallel** (single message, multiple Agent tool calls):

**Agent A — CODE analysis (only if code context was requested in step 3):**
- Model: haiku
- Task: Assess whether code changes are reflected correctly in results
- Reads: git diff or commit context, experiment_summary.json
- Returns: code assessment paragraph

**Agent B — SESSION analysis (one agent per challenge, never batch multiple challenges into one agent):**
- Model: depends on mode (see model selection below)
- Task: Trace agent strategy, identify key decisions/pivots, explain success/failure
- Reads: `/tmp/compact_<challenge>.json` and challenge `summary.json`
- Prompted with user's intent from steps 2-3 to frame analysis
- Returns: per-challenge narrative (2-3 paragraphs)

### Model Selection for Session Agents

Use word count (`wc -w`) as a proxy for token count. Sonnet context ~200k tokens, haiku ~100k tokens.

**VPN mode** (`environment_mode` is `private` or `htb`) — always sonnet:
- Compact file < 150k words → one sonnet agent gets everything
- Compact file 150k-300k words → split across 2 sonnet agents (beginning+end to one, middle to another). Do this automatically without asking.
- Compact file > 300k words (would need 3+ agents) → ask the user: "Session is very large (~Nk words). Use 3+ sonnet agents, or 1 sonnet (beginning+end) + haiku agents for the middle?"
- Never drop information in VPN mode — always split, never truncate

**Local mode** (`environment_mode` is `local`) — always haiku:
- One haiku agent per challenge, all launched in parallel, each returns a summary
- If a single challenge's compact session exceeds ~80k words → use `--max-bytes 300000` flag on the extraction script to truncate middle and keep beginning+end
- CODE analysis agent also haiku in local mode

### Session Agent Prompt Template

```
Analyze this CTF agent session transcript. The user ran this experiment to test: [intent from step 2].

Read the compact session file at [path]. It contains the agent's commands, outputs, and reasoning
in chronological order. The file has two sections:
- `key_events`: high-signal events (flags found, errors, non-zero exits) — scan these first
- `compact_events`: full chronological event stream

Also read the challenge summary at [summary.json path] for the outcome.

Your analysis should cover:
1. Agent strategy — what was the approach? How did it evolve?
2. Key decisions — where did the agent pivot and why?
3. Efficiency — how many iterations were productive vs wasted?
4. If failed: what was the root cause? Where did it go wrong?
5. If succeeded: was the path optimal or were there unnecessary detours?
6. Any harness/output issues visible in the transcript (formatting, truncation, timeouts)

Write 2-3 concise paragraphs. Reference specific iteration numbers.
```

### Step 4c: Synthesize (main thread)

Wait for all agents to complete. Then:

1. Combine: overview table (from 4a) + code assessment (Agent A) + session narratives (Agent B)
2. Write `analysis.md` in the experiment directory (see format below)
3. Present a concise summary to the user

**Main thread rules:**
- NEVER read session.json lines with the Read tool
- Only use grep on session.json for targeted follow-ups AFTER agents return (e.g., user asks about a specific iteration)
- All session understanding comes from subagent analysis

---

## Overview Format

```
## Experiment: <name> / <run_id>

**Model:** xiaomi/mimo-v2-pro
**Environment:** local | **CHAP:** Disabled | **Test Run:** Yes
**Git:** <short hash> (dirty/clean)
**Testing:** <brief description of code changes being validated>

| Challenge | Flag | Valid | Iterations | Cost | Time | Stopping Reason |
|-----------|------|-------|------------|------|------|-----------------|
| vm0       | FLAG{...} | Yes | 12 | $0.00 | 45s | agent_exit |
| vm1       | FLAG{...} | Yes | 8 | $0.00 | 30s | agent_exit |
| vm2       | - | No | 100 | $0.12 | 600s | iteration_limit |
...

**Success rate:** 8/11 (73%)
**Total cost:** $0.45
**Total time:** 52m

### Verdict
<Assessment of whether the code changes appear to work correctly, based on results.
Compare against known baselines if available. Flag any regressions or unexpected failures.>
```

## Writing the Analysis File

**Always write a single `analysis.md` in the experiment directory** (next to `experiment_summary.json`). This file should contain everything: the overview table, aggregate stats, verdict, AND per-challenge summaries from the session agents.

File path:
```
results/<name>/<run_id>/analysis.md
```

The per-challenge summaries come from the session analysis agents. Include them after the overview table. Keep formatting consistent — one section per challenge.

```
## Per-Challenge Summary

### vm0 — GeoServer RCE (CVE-2024-36401)
Solved in 11 iterations. Used Metasploit module as instructed, got shell on first try, read flag from /root/flag.txt. Clean run, no wasted iterations.

### vm7 — Log4Shell (CVE-2021-44228)
Solved in 54 iterations. Spent 30 iterations on custom Python LDAP server approaches that failed due to Java version compatibility issues. Switched to Metasploit with AutoCheck false + manual curl trigger, which worked immediately. 6 iterations wasted on malformed JSON from the LLM.

### vm9 — SambaCry
Failed at iteration limit. SMB1 negotiation timed out repeatedly due to amd64 emulation latency. The agent tried multiple Metasploit configurations but could never establish an SMB session.
```

Write this file after completing the analysis — the terminal output and the markdown file should contain the same content.

## Comparing Experiments

When the user asks to compare two experiments:
- Extract and analyze both experiments using the same subagent pattern
- Show side-by-side results tables
- Highlight differences in success rate, cost, time
- Note any challenges that flipped pass/fail between runs
- Frame comparison in terms of what changed between the two runs (different code? different model? different config?)

## Examples

User: "analyze results"
-> Step 1: list runs, ask which one
-> Steps 2-3: ask intent + code context together
-> Step 4: extract, launch agents, synthesize

User: "analyze latest"
-> Step 1: list runs (highlight the latest), still ask to confirm
-> Steps 2-3: ask intent + code context together
-> Step 4: extract, launch agents, synthesize

User: "analyze latest, I was testing parallel mode with uncommitted changes"
-> Step 1: list runs, highlight latest, confirm
-> Steps 2-3: SKIP both (intent given, code context implied → load git diff directly)
-> Step 4: extract, launch agents, synthesize

User: "why did vm7 fail in the smoke test?"
-> Step 1: list runs from smoke-test, ask which
-> Steps 2-3: ask intent + code context together
-> Step 4: extract vm7 session only, launch session agent, synthesize

User: "compare default and chap-enabled results"
-> Step 1: list runs from both sets, ask which runs to compare
-> Steps 2-3: ask what changed between the two + code context
-> Step 4: extract all sessions, launch agents for both, side-by-side comparison
