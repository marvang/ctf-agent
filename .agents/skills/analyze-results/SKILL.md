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
---

The user wants to analyze CTF experiment results. **Before doing any analysis, you MUST follow the mandatory question flow below.** No exceptions — even if the user says "analyze latest", you still present options and ask the clarifying questions before loading any session data.

## Mandatory Question Flow

Every invocation of this skill must go through these steps in order. Do NOT skip steps. Do NOT start reading session.json or summary.json files until step 3 is complete.

### Step 1: Present experiment runs

Scan `results/` and present the most recent/relevant experiment runs. Show a pick list:

```bash
# Find all experiment directories and their summaries
find results/ -name "experiment_summary.json" -type f
```

Read each `experiment_summary.json` to extract: timestamp, model, challenge count, success count, termination reason, and experiment set name. Then present:

```
## Recent Experiment Runs

| # | Name | When | Model | Challenges | Successes | Status |
|---|------|------|-------|------------|-----------|--------|
| 1 | pre-commit-smoke | Today 3:12 PM | mimo-v2-pro | 11 | 8/11 | completed |
| 2 | pre-commit-smoke | Yesterday 8:45 PM | minimax-m2.5:free | 11 | 6/11 | completed |
| 3 | vpn-kth | Mar 16, 7:06 PM | Codex-sonnet-4.6 | 3 | 1/3 | interrupted |

Which run(s) do you want to analyze?
- Pick by number (e.g. "1", "1 and 2" to compare)
- Or describe what you're looking for if none of these match
```

Format timestamps as relative when recent ("Today 3:12 PM", "Yesterday 8:45 PM") and absolute when older ("Mar 16, 7:06 PM"). Sort by most recent first. Show up to 8 runs. If there are more, mention how many total exist.

**STOP HERE and wait for the user's answer before proceeding.**

### Step 2: Ask for context source

After the user picks a run, ask what context you should load to understand **what code changes the experiment was validating**. Experiments are always run to verify that code changes work correctly (smoke tests, feature validation, post-refactor checks). The analysis is meaningless without knowing what was being tested.

Present this question:

```
What context should I load to understand what this experiment was testing?

1. **git diff** — there are uncommitted changes right now that this experiment was testing
2. **A specific commit** — the changes have been committed (give me the hash or I'll check recent commits)
3. **I'll explain** — I'll describe the context myself
```

**STOP HERE and wait for the user's answer before proceeding.**

If the user picks option 1, run `git diff --stat HEAD` and `git diff HEAD` (or targeted file reads for large diffs).
If the user picks option 2, run `git show --stat <hash>` and read the relevant diffs.
If the user picks option 3, wait for their explanation.

### Step 3: Analyze

Only NOW can you start reading experiment data and performing analysis. You have:
- Which run(s) to analyze (from step 1)
- What code changes to contextualize against (from step 2)

Proceed with the analysis workflow below, framing every finding in terms of "did the code changes work correctly?"

---

## Analysis Workflow (after step 1-2 are complete)

### Read experiment data

1. Read `experiment_summary.json` for full metadata
2. Read each challenge's `summary.json` for outcomes
3. Present the overview table (see format below)
4. Frame results in context of the code changes being tested

### Overview Format

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

### Writing the Analysis File

**Always write a single `analysis.md` in the experiment directory** (next to `experiment_summary.json`). This file should contain everything: the overview table, aggregate stats, verdict, AND per-challenge summaries.

File path:
```
results/<name>/experiment_<run_id>/analysis.md
```

The per-challenge summaries go after the overview table. One paragraph per challenge covering: what the agent did, whether it succeeded/failed and why, and any notable observations (e.g. wasted iterations, alternative exploit paths, output issues). Keep it concise — a sentence or two for straightforward successes, a short paragraph for failures or interesting cases.

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

## Deep-Diving into session.json

**CRITICAL: session.json files can be very large (10MB+). Never read them fully.**

Follow this protocol:
1. First check file size: `wc -c results/.../session.json`
2. If under 500KB, read with limit (first 200 lines + last 50 lines)
3. If over 500KB, use targeted reads:
   - Read first 100 lines for session metadata and initial prompts
   - Use `grep -c '"event_index"' file` to count total events
   - Use `grep -n '"tag":' file | tail -20` to find interesting events near the end
   - Read specific line ranges around failures, relay triggers, or the final commands
4. **Monitor context usage** — if you're already above 700k tokens, warn the user before reading more

### What to look for in failures:
- Last few commands before stopping — was the agent stuck in a loop?
- Error messages in stderr
- Did it find the vulnerability but fail to exploit?
- Did it run out of iterations while making progress?
- Did it go down the wrong path early?

### What to look for in successes:
- How quickly did it find the vulnerability?
- Did it use the expected exploit path or find an alternative?
- How many iterations were wasted on dead ends?

## Comparing Experiments

When the user asks to compare two experiments:
- Show side-by-side results tables
- Highlight differences in success rate, cost, time
- Note any challenges that flipped pass/fail between runs
- Frame comparison in terms of what changed between the two runs (different code? different model? different config?)

## Examples

User: "analyze results"
-> Step 1: list runs, ask which one
-> Step 2: ask for context source
-> Step 3: analyze

User: "analyze latest"
-> Step 1: list runs (highlight the latest), still ask to confirm
-> Step 2: ask for context source
-> Step 3: analyze

User: "analyze latest, uncommitted changes"
-> Step 1: list runs, highlight latest, confirm
-> Step 2: SKIP (context already specified — use git diff)
-> Step 3: analyze

User: "why did vm7 fail in the smoke test?"
-> Step 1: list runs from smoke-test, ask which
-> Step 2: ask for context source
-> Step 3: deep-dive into vm7

User: "compare default and chap-enabled results"
-> Step 1: list runs from both sets, ask which runs to compare
-> Step 2: ask for context source (what changed between the two)
-> Step 3: side-by-side comparison
