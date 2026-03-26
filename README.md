# CTF-Agent

This repo consists of an AI-driven pentesting agent that solves CTF challenges and a research framework for running scientific experiments to study offensive security agents.

- Autonomous reconnaissance and exploitation
- Optional CHAP context handoff for long-running sessions
- Real-time cost and token tracking
- Session logs with timestamps, commands, context, and results

## Contents

- [Installation](#installation)
- [Interactive Use](#interactive-use)
- [Experiments](#experiments)
- [Benchmark](#benchmark)
- [Research](#research)

## Installation
Requirements:
- Docker Desktop or Docker Engine with Compose
- `uv`
- OpenRouter API key
- Hack The Box account and `.ovpn` file if you want HTB mode

### 1. Install `uv`

Linux/macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone the repository

```bash
git clone <repository-url>
cd ctf-agent
```

### 3. Install Python dependencies

```bash
uv sync
source .venv/bin/activate
```

### 4. Configure environment variables

Copy the example file and add your OpenRouter key:

```bash
cp .env_example .env
```

Then edit `.env`:

```bash
OPENROUTER_API_KEY=sk-or-v1-your-api-key-here
```

### 5. Build the Kali container

```bash
docker compose build
```

The agent starts the Kali container automatically when needed.

## Interactive Use

Use `main.py` when you want to drive a single run interactively against:

- a local Docker challenge
- a private VPN target
- Hack The Box

### Extra setup

For local Docker challenges, also build the challenge images:

```bash
docker compose -f local_challenges/autopenbench_improved/docker-compose.yml build
```

For VPN-based targets, place your VPN material here:

- HTB: `ctf-workspace/vpn/htb/`
- Private range: `ctf-workspace/vpn/private/`

### Run

```bash
python main.py
```

The `ctf-workspace/` directory is mounted into the Kali container and shared with the host.

### Linux Setup

On Linux, Docker runs natively and challenge targets execute at full speed (no emulation). Two extra steps are needed:

1. **Docker group** — add your user so you can run Docker without sudo:
   ```bash
   sudo usermod -aG docker $USER  # then log out and back in
   ```
2. **Sudo for cleanup** — Docker creates root-owned files in the shared workspace. Before running experiments, cache your sudo credentials so cleanup can remove them:
   ```bash
   sudo -v
   ```
   The experiment runner checks for this at startup and exits with a clear message if forgotten.

## Experiments

Use `scripts/run_experiment.py` for reproducible benchmark runs on the local benchmark.

Before running experiments, build the challenge images:

```bash
docker compose -f local_challenges/autopenbench_improved/docker-compose.yml build
```

Then configure `scripts/run_experiment.py` for the run you want. It already has flags for the common overrides, so ask your AI assistant which flags to use for a given experiment setup.

### Run

```bash
python scripts/run_experiment.py
```

Results are written under `results/<experiment_set_name>/<run_id>/`.

## Benchmark

The local benchmark is an improved version of [AutoPenBench](https://github.com/lucagioacchini/auto-pen-bench) with 11 CVE-based challenges under `local_challenges/autopenbench_improved/`.

| VM | CVE | CVSS | Description |
|----|-----|------|-------------|
| vm0 | CVE-2024-36401 | 9.8 | GeoServer RCE |
| vm1 | CVE-2024-23897 | 9.8 | Jenkins arbitrary file read |
| vm2 | CVE-2022-22965 | 9.8 | Spring4Shell |
| vm3 | CVE-2021-3156 | 7.8 | Baron Samedit (sudo) |
| vm4 | CVE-2021-42013 | 9.8 | Apache path traversal |
| vm5 | CVE-2021-43798 | 7.5 | Grafana directory traversal |
| vm6 | CVE-2021-25646 | 9.0 | Apache Druid RCE |
| vm7 | CVE-2021-44228 | 10.0 | Log4Shell |
| vm8 | CVE-2019-16113 | 8.8 | Bludit RCE |
| vm9 | CVE-2017-7494 | 10.0 | SambaCry |
| vm10 | CVE-2014-0160 | 7.5 | Heartbleed |

## Claude Code Skills

The project includes Claude Code skills (`.claude/skills/`): `/run-experiment` helps you configure and preview experiment parameters,`/live-updates` provides real-time monitoring. `/analyze-results` analyzes runs.

## Research

This repository contains the research framework and benchmark used for CHAP, a context relay mechanism for long-running penetration-testing agents.

Paper: [Context Relay for Long-Running Penetration-Testing Agents](https://www.ndss-symposium.org/wp-content/uploads/lastx2026-42.pdf)

If you use this work in research, cite:

```bibtex
@inproceedings{chap2026,
  title={Context Relay for Long-Running Penetration-Testing Agents},
  author={Vangeli, Marius and Brynielsson, Joel and Cohen, Mika and Kamrani, Farzad},
  booktitle={NDSS Workshop on LLM Assisted Security and Trust Exploration (LAST-X)},
  year={2026},
  url={https://dx.doi.org/10.14722/last-x.2026.23042},
  doi={10.14722/last-x.2026.23042}
}
```
