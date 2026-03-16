"""
Relay handler for Context Handoff Protocol (CHAP).
Orchestrates the handoff process between agent instances.
"""

from typing import Dict, Any, List, Optional
from src.chap_utils.protocol_generator import generate_relay_protocol
from src.utils.state_manager import (
    add_relay_protocol,
    append_session_event,
    increment_agent_number,
    get_current_agent_tokens,
    persist_session,
)
from src.llm_utils.prompt_builder import build_relay_messages
from src.utils.environment import EnvironmentType, LocalArch


def trigger_relay_handoff(
    session: Dict[str, Any],
    messages: List[Dict[str, str]],
    model_name: str,
    environment_mode: EnvironmentType,
    target_info: str,
    custom_instructions: str,
    current_iteration: int,
    agent_ips: Optional[dict] = None,
    local_arch: LocalArch | None = None,
    session_path: str | None = None,
) -> List[Dict[str, str]]:
    """
    Executes relay handoff:
    1. Generate protocol from current history
    2. Save protocol to session
    3. Build fresh initial messages for new agent with all protocols injected
    4. Return new messages list

    Args:
        session: Current session object
        messages: Current conversation history
        model_name: Model being used
        environment_mode: Selected environment mode for the run
        target_info: Target IP or description
        custom_instructions: User's custom instructions
        current_iteration: Current iteration count to accumulate
        agent_ips: Dict with agent IP addresses (eth0, tun0 if VPN)
        local_arch: Local execution architecture used for prompt selection

    Returns:
        New messages list with protocols injected
    """

    agent_tokens = get_current_agent_tokens(session)

    print(f"\n🔄 Initiating relay handoff...")
    print(f"📊 Current agent: Agent {session['agent_number']}")
    print(f"💰 Agent token usage: {agent_tokens:,} tokens")
    print(f"💰 Total session tokens: {session['metrics']['total_tokens']:,} tokens")
    print(f"🔄 Total iterations: {session['metrics']['total_iterations']}")
    print(f"🕒 Total time: {session['metrics']['total_time']:.2f} seconds")
    print(f"💵 Cost: ${session['metrics']['total_cost']:.4f}")

    print(f"\n📝 Generating relay protocol...")
    try:
        protocol = generate_relay_protocol(
            messages,
            session,
            model_name,
            current_iteration=current_iteration,
        )
        print(f"✅ Protocol generated successfully")
        print(f"📄 Protocol content:\n{protocol['protocol_content']}\n")
    except Exception as e:
        print(f"❌ Error generating protocol: {e}")
        raise e

    add_relay_protocol(session, protocol)
    increment_agent_number(session)
    new_agent_number = session["agent_number"]

    new_messages = build_relay_messages(
        session=session,
        environment_mode=environment_mode,
        target_info=target_info,
        custom_instructions=custom_instructions,
        agent_ips=agent_ips,
        local_arch=local_arch,
    )

    append_session_event(
        session,
        stream="main_agent",
        tag="relay_system_prompt",
        message=new_messages[0],
        iteration=current_iteration,
        agent_number=new_agent_number,
        model_name=model_name,
        metadata={"relay_number": len(session["relay_protocols"])},
    )
    append_session_event(
        session,
        stream="main_agent",
        tag="relay_user_prompt",
        message=new_messages[1],
        iteration=current_iteration,
        agent_number=new_agent_number,
        model_name=model_name,
        metadata={"relay_number": len(session["relay_protocols"])},
    )

    if session_path:
        persist_session(session, session_path)

    print(f"\n✨ Relay handoff complete!")
    print(f"🤖 Now operating as Agent {new_agent_number}")
    print(f"📚 Carrying forward {len(session['relay_protocols'])} protocol(s)")
    print("="*60)

    return new_messages
