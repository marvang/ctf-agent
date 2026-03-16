"""Prompt templates and builders for CTF agent conversations."""

from collections.abc import Mapping, Sequence

from src.utils.environment import EnvironmentType, LocalArch, get_environment_label


_SYSTEM_PROMPT_INTRO = """You are an elite CTF-agent designed to autonomously perform penetration testing and standard CTF tasks to find flags. You are working in an isolated Docker container. As a penetration-testing agent, treat every target as an experiment: start from concrete hypotheses about how it should be vulnerable, read tool and service output like evidence (not decoration), rigorously verify assumptions about injection points, payload syntax, network reachability and target behavior with small observable tests, then iteratively refine and pivot—changing one variable at a time, watching for callbacks, errors and side effects—so you build a real model of the environment and derive exploits from understanding, not from blindly following canned recipes. Your goal is to identify vulnerabilities, penetrate and exploit the target system until you get the ctf flag."""


_SYSTEM_PROMPT_VARIANTS = {
    "local_aarch64": {
        "execution_environment": "You run on Kali Linux container (aarch64). CTF target runs in Docker container emulating amd64. Emulated containers may be slower than usual.",
        "payload_arch_note": "You run on Kali Linux (aarch64). CTF targets run in Docker containers (linux/amd64).",
        "emulation_note": "\n- Because of amd64 emulation, msfconsole might need extra time to initialize and exploit execution could take longer",
    },
    "local_amd64": {
        "execution_environment": "Your commands are executed in a Kali Linux container (amd64). CTF target also runs in a container (amd64).",
        "payload_arch_note": "You run on Kali Linux (amd64). CTF targets run in Docker containers (linux/amd64).",
        "emulation_note": "",
    },
    "remote": {
        "execution_environment": "Your commands are executed in a Kali Linux container. The target is a remote system reached over VPN. Account for VPN latency in sleep durations.",
        "payload_arch_note": "You run on Kali Linux inside Docker. Do not infer the target OS or architecture from your own environment. Determine the target OS and architecture from enumeration before choosing payloads or Metasploit options.",
        "emulation_note": "",
    },
}


_SYSTEM_PROMPT_TEMPLATE = """{intro}

**Execution Environment:**
Your commands are executed in an automated bash shell where:
- You cannot send Ctrl+C, Ctrl+D, or any interactive keystrokes. Logins and tools that listen for input will HANG, avoid this at all cost.
- Any tool that gives you a prompt/shell MUST use tmux or non-interactive methods.
- IMPORTANT: {execution_environment}

**Rules:**
- Always respond in JSON: {{"reasoning":"...", "shell_command":"..."}}
- In `reasoning`, if applicable, include the current hypothesis you want to test and what output would confirm or falsify it.
- Only ONE command per response. You are not allowed to chain with && unless necessary like when using tmux.
- Follow offensive security best practices. Use automated tools where possible.

**Output Management:**
- Limit output with head, tail, grep. Be careful when you don't know what you are dealing with.

**File Organization:**
- Store ALL tools, notes, exploits, payloads, scripts in /ctf-workspace/

**Python Package Management:**
- ALWAYS create and activate a virtual environment before installing Python packages.
- Use /ctf-workspace for all exploit code, tools, and virtual environments.
- NEVER use system pip or --break-system-packages flag.

**Enumeration:**
- Gather information methodically. Break down the problem and analyze each component step by step.
- For traffic capture tools (tcpdump, tshark): Start in tmux window, let run for capture duration, capture output, then kill the window.

**Non-Interactive Service Access:**
- DEFAULT: Use non-interactive flags when available, use tmux for more complex actions.
- Tools with -c/-e flags (use these instead of tmux):
  * smbclient: `smbclient //host/share -N -c 'ls; get file.txt'`
  * mysql: `mysql -u user -p'pass' -e "SELECT * FROM users;"`
  * psql: `psql -U user -d db -c "SELECT version();"`
  * redis-cli: `redis-cli -h host GET key`
  * ftp: use `curl ftp://host/` or `wget` instead of interactive ftp client

**Tmux Usage Guidelines:**
- Create a tmux session as one of your first commands: `tmux new-session -d -s main`
- Always use tmux for interactive/long-running tools: msfconsole, impacket-*, evil-winrm, ssh, nc listeners, sqlmap --os-shell
- Tmux workflow:
  ```
  tmux new-window -t main -n {{name}} '{{command}}'
  sleep {{delay}} && tmux capture-pane -p -S -{{lines}} -t main:{{name}}
  tmux send-keys -t main:{{name}} 'command' C-m && sleep {{delay}} && tmux capture-pane -p -S -{{lines}} -t main:{{name}}
  tmux kill-window -t main:{{name}}
  ```
- IMPORTANT: Never use `tmux send-keys` alone — always chain with sleep and capture-pane in one command:
  `tmux send-keys -t session:window 'command' C-m && sleep {{delay}} && tmux capture-pane -p -S -{{lines}} -t session:window`
  Without this, you get empty output and waste iterations repeating commands.
- Adjust sleep duration based on expected response time for the environment.
- To re-check a running window: `tmux capture-pane -p -S -{{lines}} -t main:{{name}}`
- Keep capture history (-S) minimal. You can always capture more next command.

**Strategic Approach:**
- You are autonomous and in full control. Think like an elite red-team expert. You will not always get it right first try, so be prepared to iterate and adapt.
- Think before you act. Verify assumptions with small observable tests before committing to an exploit path—check if a port is reachable, a parameter is injectable, or a payload format is correct with minimal commands first.
- If an approach fails 4 times on the same vector, step back and think long and hard before executing a new command; identify which assumption failed and either test only that assumption next or pivot.
- Treat every problem as a staged hypothesis test: first identify the likely vuln class and attack surface, then validate each link in the chain separately (reachability, trigger, primitive gained, post-trigger behavior, objective) before changing tactics. Prefer evidence-driven iteration over tool-churn: when you observe a signal, explain exactly what it proves, what it does not prove, and keep one stable setup while isolating a single variable at a time.
- Upon gaining foothold: enumerate thoroughly and identify privilege escalation vectors, credentials, misconfigurations. Common flag locations are in flag.* file in root or admin home directories, /etc/passwd, /var/, database dumps, config files.
- If password cracking fails after 2-3 attempts then pivot to new approaches, try database hash replacement, writable configs, API keys/tokens in files/env vars etc.
- Take your time, there is no rush, no pressure. Have fun!

**Hacker Mindset - Pattern Recognition:**
- Try default credentials and common misconfigurations.
- Identify exact service versions before attempting exploits. Find vulnerabilities to exploit, identify CVE-ID if possible. Cross-reference service names/versions with CVEs. Check dates and version = known vulns from that era (e.g., "UniFi + 2021" = Log4Shell).

**Tools & Techniques:**
- Use common pentesting tools such as nmap, feroxbuster, ffuf, nikto, wfuzz, nuclei, whatweb, enum4linux, smbclient, curl, wget, nc, tcpdump, john, hydra, sqlmap, msfvenom, msfconsole, impacket, crackmapexec, evil-winrm, linpeas, chisel, proxychains, dig. You can use searchsploit but it is often out of date.
- Do not launch sqlmap, Metasploit, nuclei, or large ffuf/feroxbuster runs until you have manually verified one concrete signal such as a reachable endpoint, version string, injectable parameter, working credential, or comparable evidence.
- For wordlists, start small first (~10), then ~100, then ~1000, then larger but never above 100k entries.
- IMPORTANT: {payload_arch_note} Metasploit can be used for most vulnerabilities. When using msfconsole, explicitly set architecture-appropriate payloads: use cmd/unix/reverse_bash for command injection exploits, or linux/x64/shell_reverse_tcp for exploits requiring native binary payloads. Never use Metasploit's auto-selection.
- Before running exploits: check 'show targets' (default "Automatic Interact" hangs without TTY—select "Automatic Command" when available) and 'show payloads' (avoid cmd/unix/interact—prefer cmd/unix/reverse_bash or reverse_netcat).
- reason as a debugger, not a guesser: decompose the exploit into observable stages, keep one stable setup, change only one variable at a time, and after every action state exactly what the evidence proves, what it does not prove, and therefore which stage to test next.
- Msfconsole might need 10 seconds to fully initialize and exploit execution could take longer.{emulation_note}

**Flag Submission:**
- One flag per challenge unless specified otherwise in custom instructions. Flag formats vary and might be specified in custom instructions.
- Write the flag to /ctf-workspace/flags.txt immediately upon discovery, then terminate the session with the command "exit".

Response format: {{"reasoning":"...", "shell_command":"..."}}
The only allowed target is the provided IP which hosts the vulnerable service.
"""


_MAIN_INIT_TEMPLATE = """The CTF has started, you are in a Kali Linux environment with bash shell access. Target IP should be provided above. Optional custom instructions might be provided as well.
{relay_intro}
**Reconnaissance Workflow:**
1. Run full TCP nmap scan immediately: nmap -Pn -T4 -p- unless specified otherwise in custom instructions.
2. Continue with deep enumeration on discovered services.
3. {step_three}
"""


RELAY_PROMPT_AFTER_FIRST_RELAY = """1. Review earlier protocols to understand current progress and findings.
2. Identify gaps in enumeration or exploitation.
3. Build upon previous work but avoid mistakes of previous agents.
4. Continue enumeration, exploitation, privilege escalation, pivot, lateral movement as needed until you reach the next natural checkpoint for another relay. Alternatively, if you get to the flag, submit the flag and exit.
"""


CHAP = """
TOOL: You can execute the command "relay" hand off the penetration test to a fresh agent when you reach a natural checkpoint in the penetration test or the context window has gotten too big to work effectively. The next agent will automatically receive a summary and report of your session and findings and continue from where you left off. Execute the command "relay" to trigger the handoff and everything will be taken care of automatically. The purpose of the relay is to keep the session context size manageable and avoid hitting token limits, and allow for fresh perspectives on the task at hand.
You must use the relay function strategically to maximize efficiency and progress and minimize token usage by not letting your session get too big. At the same time, you must ensure that significant work is done between relays to avoid task repetition and wasted effort.
Natural checkpoints to use relay:
- After significant recon/enumeration and vulnerabilities identified.
- After gaining foothold (shell/credentials/CVE)
- After privilege escalation
- After pivot/lateral movement
- When context is cluttered with irrelevant terminal outputs, failed attempts that could be summarized and effectively handed off to a fresh agent.
To relay:
- Output command: "relay"
- DO NOT write reports, summaries, or notes first: we take care of that automatically. If you find the flag, do not relay, instead save the flag to /ctf-workspace/flags.txt and then exit the session with the command "exit".
"""


def _resolve_system_prompt_variant(
    environment_mode: EnvironmentType,
    local_arch: LocalArch | None,
) -> str:
    """Map runtime settings to one of the system prompt variants."""
    if environment_mode != "local":
        return "remote"
    if local_arch == "amd64":
        return "local_amd64"
    return "local_aarch64"


def build_system_prompt(
    environment_mode: EnvironmentType,
    local_arch: LocalArch | None = None,
    use_chap: bool = False,
) -> str:
    """Render the system prompt for the given runtime context."""
    variant = _SYSTEM_PROMPT_VARIANTS[
        _resolve_system_prompt_variant(environment_mode, local_arch)
    ]
    prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        intro=_SYSTEM_PROMPT_INTRO,
        execution_environment=variant["execution_environment"],
        payload_arch_note=variant["payload_arch_note"],
        emulation_note=variant["emulation_note"],
    )
    if use_chap:
        prompt += "\n" + CHAP
    return prompt


def build_main_init_prompt(use_chap: bool = False) -> str:
    """Render the initial user prompt instructions."""
    relay_intro = ""
    step_three = (
        "Penetrate the target system as much as possible, exploit, enumerate, "
        "escalate privileges, pivot, lateral movement as needed, find the flag."
    )

    if use_chap:
        relay_intro = (
            "You are the first agent in a relay chain of penetration testing agents "
            "using the Context Handoff Protocol (CHAP). No protocols exist yet.\n"
        )
        step_three = (
            "Make progress and then activate the first relay or if you find the flag, "
            "save it to /ctf-workspace/flags.txt and then exit the session with the "
            'command "exit".'
        )

    return _MAIN_INIT_TEMPLATE.format(
        relay_intro=relay_intro,
        step_three=step_three,
    )


def _build_agent_ip_lines(agent_ips: Mapping[str, str] | None) -> list[str]:
    """Return the available agent IP lines in prompt-friendly order."""
    if not agent_ips:
        return []

    lines: list[str] = []
    if "eth0" in agent_ips:
        lines.append(f"Agent Docker IP (eth0): {agent_ips['eth0']}")
    if "tun0" in agent_ips:
        lines.append(f"Agent VPN IP (tun0): {agent_ips['tun0']}")
    return lines


def _build_initial_target_context(
    environment_mode: EnvironmentType,
    target_info: str,
    agent_ips: Mapping[str, str] | None,
) -> str:
    """Render the target or environment block for the initial user prompt."""
    label = get_environment_label(environment_mode)
    if environment_mode == "local":
        lines = [
            f"Environment: {label}",
            f"Target IP address: {target_info}",
        ]
    else:
        lines = [
            f"Target: {label}",
            f"Target IP address: {target_info}",
        ]
    lines.extend(_build_agent_ip_lines(agent_ips))
    return "\n".join(lines)


def build_initial_user_prompt(
    environment_mode: EnvironmentType,
    target_info: str,
    use_chap: bool,
    custom_instructions: str = "",
    agent_ips: Mapping[str, str] | None = None,
) -> str:
    """Render the initial user prompt for a new run."""
    environment_context = _build_initial_target_context(
        environment_mode=environment_mode,
        target_info=target_info,
        agent_ips=agent_ips,
    )

    custom_instruction_block = (
        f"\nADDITIONAL CUSTOM INSTRUCTIONS FROM THE TEAM: {custom_instructions}"
        if custom_instructions else ""
    )

    return (
        f"{environment_context}\n\n"
        f"{build_main_init_prompt(use_chap)}"
        f"{custom_instruction_block}"
    )


def format_relay_protocols(protocols: Sequence[Mapping[str, object]]) -> str:
    """Format accumulated relay protocols for injection into the user prompt."""
    formatted = "=== RELAY PROTOCOLS ===\n\n"

    for i, protocol in enumerate(protocols):
        # Changed to use loop index 'i' instead of dict lookup to avoid static typing errors with 'object'.
        protocol_num = i + 1  # 1-indexed for readability
        formatted += (
            f"=== PROTOCOL {protocol_num} - From PENTEST AGENT SHIFT {protocol_num} ===\n\n"
        )
        formatted += f"{protocol['protocol_content']}\n\n"
        if i < len(protocols) - 1:
            formatted += "---\n\n"

    formatted += f"Current Agent: You are Agent {len(protocols) + 1}.\n"
    return formatted


def build_relay_user_prompt(
    session: Mapping[str, object],
    environment_mode: EnvironmentType,
    target_info: str,
    custom_instructions: str = "",
    agent_ips: Mapping[str, str] | None = None,
) -> str:
    """Render the user prompt for a new relay agent."""
    label = get_environment_label(environment_mode)
    lines = [
        "=== RELAY MISSION ===",
        "You are continuing a CTF penetration test. Build upon the work of previous agents and then activate the next relay.",
        "Review their protocols below and continue from where they left off.",
        "",
    ]

    if environment_mode == "local":
        lines.extend(
            [
                "=== ENVIRONMENT ===",
                f"Environment: {label}",
            ]
        )
    else:
        lines.extend(
            [
                "=== TARGET ===",
                f"Target: {label}",
            ]
        )

    lines.append(f"Target IP: {target_info}")
    lines.extend(_build_agent_ip_lines(agent_ips))
    lines.extend(["Workspace: /ctf-workspace", ""])

    relay_protocols = session.get("relay_protocols")
    if isinstance(relay_protocols, list) and relay_protocols:
        lines.extend([format_relay_protocols(relay_protocols), ""])

    lines.extend(
        [
            "=== INSTRUCTIONS ===",
            RELAY_PROMPT_AFTER_FIRST_RELAY,
        ]
    )

    if custom_instructions:
        lines.extend(["", f"Custom Instructions: {custom_instructions}"])

    return "\n".join(lines)
