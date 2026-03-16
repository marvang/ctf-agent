"""
Protocol generator for Context Handoff Protocol (CHAP).
Generates compact relay protocols from conversation history.
"""

import copy
import json
from typing import Dict, Any, List, Mapping, Sequence
from datetime import datetime
from src.llm_utils.openrouter import call_openrouter_protocol
from src.llm_utils.prompts import format_relay_protocols
from src.utils.state_manager import append_session_event, update_session_tokens

PROTOCOL_GENERATOR_SYSTEM_PROMPT = """ You are a penetration testing agent specializing in generating concise relay protocols in markdown for handoff in a shift‑relay pentesting architecture. Each agent picks up where the last left off, so your protocol must comprehensively summarize all prior actions, findings, and context in a compact format, while avoiding redundancy with earlier protocols. Your protocol will be appended together with all prior protocols to the initial prompt for the next agent in the relay.

**Response Format:** You must respond with a JSON object containing two fields:
{"reasoning":"...", "protocol":"..."}
- "reasoning": Brief chain of thought thinking about the task before protocol generation
- "protocol": The actual markdown relay protocol content
Use the reasoning field to think about what information from the large context matters for handoff and how to compress it as much as possible before writing the protocol.

**Maximize information density in the protocol. Only add information that is not already included in previous protocols:**
- Current position: user, host, shell type, privileges
- Network map: where you've been, what systems/services accessed
- What was tried (successful and failed)
- active sessions (tmux/shells with window names)
- Foothold: exact command sequence

- Failed attempts revealing constraints
- Working exploits, file locations, discovered vulns
- Commands to quickly achieve same state if ever reset

In addition to identified relevant information, explicitly encode the "unexplored surface": any discovered hosts, ports, endpoints, credentials, or features in the data that was missed or overlooked. Mark them tersely as *untried* without speculating on next steps.
Think of this relay as a debugger state snapshot for another expert: record only high‑signal state (exact commands, key outputs, paths, IDs, sessions, constraints) in a way that lets the next agent deterministically reconstruct the current state, foothold and context.
Ignore unverified assistant speculation and summarize only executed commands, observed outputs, credentials, paths, sessions, footholds, blockers, and other verified state.
When trading off detail vs brevity, always preserve raw technical state (commands, parameters, error fragments, IPs, ports) and compress by stripping explanation and narrative, not by omitting important facts.

**Be detailed for critical commands that took trial and error to get right:**
- Non-obvious syntax/escaping
- Complex command sequences
- Active tmux sessions and current state
And finally, include a short paragraph on what has NOT been done or tried yet in a section called "considerations for next agent". Agents tend to follow paths well-trodden by prior agents, so explicitly document unexplored avenues. It could be things not tried, different tools in the pentesters toolkit that could make life easier, different approaches to the one taken, or different angles to the pentest. If the agent struggled with constraints, syntax errors or something else, summarize these in 1 sentence to help the next agent avoid the same pitfalls.

**Protocol format:** Markdown. Aim for a short concise report that gives the agent all necessary info to pick up the pentest. Use markdown sections effectively to organize content.
As for Recommendations, your personal opinions, analysis, speculation, or next step suggestions: Only one extremely brief paragraph is allowed, but it has to be baked in with the "Considerations for next agent" section at the end of the protocol. Do NOT create a separate Recommendations section. The main goal of the protocol is to generate a summary of facts and state.

Most importantly, Never repeat information from previous protocols, the agent will see those too, so writing the same thing twice is redundant and wastes tokens. If a previous protocol mentions open ports do not include it, same with all other facts that are established. If there is little to add from this session, write a shorter protocol with only the new info and updates, and state that not much has changed since the last protocol, which might be the case if the agent struggled to make progress.
"""

PROTOCOL_GENERATOR_SYSTEM_PROMPT_V2 = """ You are a penetration testing agent specializing in generating concise relay protocols in markdown for handoff in a shift‑relay pentesting architecture. Each agent picks up where the last left off, so your protocol must comprehensively summarize all prior actions, findings, and context in a compact format, while avoiding redundancy with earlier protocols. Your protocol will be appended together with all prior protocols to the initial prompt for the next agent in the relay.

**Response Format:** You must respond with a JSON object containing two fields:
{"reasoning":"...", "protocol":"..."}
- "reasoning": Brief chain of thought thinking about the task before protocol generation
- "protocol": The actual markdown relay protocol content
Use the reasoning field to think about what information from the large context matters for handoff and how to compress it as much as possible before writing the protocol.

Ignore unverified assistant speculation and summarize only executed commands, observed outputs, credentials, paths, sessions, footholds, blockers, and other verified state.
Aim for 200-350 words unless foothold, pivot, or session state is unusually complex.

Write the protocol using exactly these sections, in this order:
## Current Access
## New Facts Since Prior Protocol
## Constraints and Failed Attempts
## Artifacts and Paths
## Untried Surface
## Considerations for Next Agent

Section requirements:
- Current Access: current user, host, privilege level, shell type, active sessions, listener state, pivot state.
- New Facts Since Prior Protocol: only new verified facts from this agent’s work.
- Constraints and Failed Attempts: only failures that reveal a real constraint or eliminate a path.
- Artifacts and Paths: exact commands, payloads, URLs, file paths, creds, hashes, ports, or IDs needed to resume quickly.
- Untried Surface: discovered but still untested hosts, ports, endpoints, creds, files, or features.
- Considerations for Next Agent: one short paragraph only; include what has not been tried yet and any pitfall worth avoiding.

When trading off detail vs brevity, always preserve raw technical state and compress by stripping explanation and narrative, not by omitting important facts. Never repeat information already established in prior protocols unless correcting or updating it.
"""

_NO_PRIOR_PROTOCOLS = (
    "No prior protocols available. You are the first agent in the pentest-relay, "
    "this means you will generate the first protocol in the chain, setting the "
    "precedent for structure and format and content."
)
_PROTOCOL_REQUEST_BUILDER_VERSION = "protocol_request_builder_v1"


def _copy_message(message: Mapping[str, Any]) -> dict[str, Any]:
    """Detach a message mapping while preserving insertion order for stable repr output."""
    return copy.deepcopy(dict(message))


def _format_prior_protocols(prior_protocols: Sequence[Mapping[str, Any]]) -> str:
    """Render prior protocol content exactly as used in the protocol request prompt."""
    if prior_protocols:
        return format_relay_protocols(prior_protocols)
    return _NO_PRIOR_PROTOCOLS


def build_protocol_request_messages(
    messages: Sequence[Mapping[str, Any]],
    prior_protocols: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Build the exact protocol-generator request payload sent to the model."""
    formatted_protocols = _format_prior_protocols(prior_protocols)
    rendered_history = [_copy_message(message) for message in messages]
    return [
        {
            "role": "system",
            "content": PROTOCOL_GENERATOR_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": f"""**Prior protocols:**
{formatted_protocols}

**Session history:**
{rendered_history}

Generate Protocol N+1.""",
        },
    ]


def _rebuild_main_agent_history(
    session: Mapping[str, Any],
    *,
    agent_number: int,
    history_end_event_index: int,
) -> list[dict[str, Any]]:
    """Rebuild the main-agent message history for one agent from replay events."""
    rebuilt_messages: list[dict[str, Any]] = []
    events = session.get("events", [])
    if not isinstance(events, list):
        raise ValueError("Session does not contain a replay event list")

    for event in events:
        if not isinstance(event, Mapping):
            continue
        event_index = event.get("event_index")
        if not isinstance(event_index, int):
            continue
        if event_index > history_end_event_index:
            break
        if event.get("stream") != "main_agent":
            continue
        if event.get("agent_number") != agent_number:
            continue

        metadata = event.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("included_in_history") is False:
            continue

        message = event.get("message")
        if isinstance(message, Mapping):
            rebuilt_messages.append(_copy_message(message))

    return rebuilt_messages


def rebuild_protocol_request_messages(
    session: Mapping[str, Any],
    request_user_event: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Rebuild the exact protocol request payload from a compact request event."""
    parsed = request_user_event.get("parsed")
    if not isinstance(parsed, Mapping):
        raise ValueError("Protocol request event is missing reconstruction metadata")
    if parsed.get("builder_version") != _PROTOCOL_REQUEST_BUILDER_VERSION:
        raise ValueError("Unsupported protocol request builder version")

    system_event_index = parsed.get("system_event_index")
    history_agent_number = parsed.get("history_agent_number")
    history_end_event_index = parsed.get("history_end_event_index")
    prior_protocol_count = parsed.get("prior_protocol_count")
    if not all(isinstance(value, int) for value in (
        system_event_index,
        history_agent_number,
        history_end_event_index,
        prior_protocol_count,
    )):
        raise ValueError("Protocol request event is missing required reconstruction indices")

    events = session.get("events", [])
    if not isinstance(events, list):
        raise ValueError("Session does not contain a replay event list")
    if system_event_index >= len(events):
        raise ValueError("Protocol request references a missing system prompt event")

    system_event = events[system_event_index]
    if not isinstance(system_event, Mapping):
        raise ValueError("Protocol request system prompt event is invalid")
    system_message = system_event.get("message")
    if not isinstance(system_message, Mapping):
        raise ValueError("Protocol request system prompt message is missing")

    relay_protocols = session.get("relay_protocols", [])
    if not isinstance(relay_protocols, list):
        raise ValueError("Session relay protocols are invalid")
    if prior_protocol_count > len(relay_protocols):
        raise ValueError("Protocol request references more prior protocols than are available")

    rebuilt_history = _rebuild_main_agent_history(
        session,
        agent_number=history_agent_number,
        history_end_event_index=history_end_event_index,
    )
    rebuilt_messages = build_protocol_request_messages(
        rebuilt_history,
        relay_protocols[:prior_protocol_count],
    )
    rebuilt_messages[0] = _copy_message(system_message)
    return rebuilt_messages


def generate_relay_protocol(
    messages: List[Dict[str, str]],
    session: Dict[str, Any],
    model_name: str,
    current_iteration: int,
) -> Dict[str, Any]:
    """
    Prompts LLM to generate compact relay protocol from conversation history.

    Args:
        messages: Full conversation history
        session: Current session object
        model_name: Model to use for protocol generation

    Returns:
        Protocol dictionary with structured summary
    """

    prior_protocols = session.get("relay_protocols", [])
    protocol_messages = build_protocol_request_messages(messages, prior_protocols)
    history_end_event_index = len(session.get("events", [])) - 1

    request_system_event = append_session_event(
        session,
        stream="protocol_generation",
        tag="protocol_request_system_prompt",
        message=protocol_messages[0],
        iteration=current_iteration,
    )
    request_user_event = append_session_event(
        session,
        stream="protocol_generation",
        tag="protocol_request_user_prompt",
        message={
            "role": "user",
            "content": f"[rebuild via {_PROTOCOL_REQUEST_BUILDER_VERSION}]",
        },
        parsed={
            "builder_version": _PROTOCOL_REQUEST_BUILDER_VERSION,
            "system_event_index": request_system_event["event_index"],
            "history_agent_number": session["agent_number"],
            "history_end_event_index": history_end_event_index,
            "history_message_count": len(messages),
            "prior_protocol_count": len(prior_protocols),
        },
        iteration=current_iteration,
    )

    try:
        reasoning, protocol_content, usage = call_openrouter_protocol(
            messages=protocol_messages,
            model_name=model_name
        )

        if usage:
            update_session_tokens(session, usage)

        full_protocol_content = protocol_content

    except Exception as e:
        print(f"⚠️  Error generating relay protocol: {e}")
        raise e

    protocol_response_event = append_session_event(
        session,
        stream="protocol_generation",
        tag="protocol_response",
        message={
            "role": "assistant",
            "content": json.dumps({"reasoning": reasoning, "protocol": full_protocol_content}),
        },
        parsed={
            "reasoning": reasoning,
            "protocol": full_protocol_content,
        },
        iteration=current_iteration,
        usage=usage,
    )

    # Build protocol dictionary with snapshot metrics (renamed to clarify these are cumulative values at snapshot time)
    snapshot_metrics = {
        "snapshot_total_input_tokens": session["metrics"]["total_input_tokens"],
        "snapshot_total_output_tokens": session["metrics"]["total_output_tokens"],
        "snapshot_total_tokens": session["metrics"]["total_tokens"],
        "snapshot_total_reasoning_tokens": session["metrics"]["total_reasoning_tokens"],
        "snapshot_total_cached_tokens": session["metrics"]["total_cached_tokens"],
        "snapshot_total_audio_tokens": session["metrics"]["total_audio_tokens"],
        "snapshot_total_cost": session["metrics"]["total_cost"],
        "snapshot_total_upstream_inference_cost": session["metrics"]["total_upstream_inference_cost"],
        "snapshot_total_iterations": session["metrics"]["total_iterations"],
        "snapshot_total_time": session["metrics"]["total_time"],
    }

    protocol = {
        "agent_number": session["agent_number"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "metrics": snapshot_metrics,
        "protocol_content": full_protocol_content,
        "reasoning": reasoning,
        "request_event_indices": [
            request_system_event["event_index"],
            request_user_event["event_index"],
        ],
        "response_event_index": protocol_response_event["event_index"],
    }

    return protocol
