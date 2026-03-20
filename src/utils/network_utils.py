"""Shared network inspection helpers for Docker-backed agent runs."""

import re
from typing import Final

_IPV4_ADDR_RE: Final[re.Pattern[str]] = re.compile(r"\binet\s+(\d+\.\d+\.\d+\.\d+)/\d+\b")


def _decode_output(output: bytes | str) -> str:
    """Return container exec output as stripped text."""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace").strip()
    return str(output).strip()


def find_vpn_interface(container) -> str | None:
    """Return the name of the first tun/tap VPN interface, or None."""
    try:
        exit_code, output = container.exec_run(["ip", "-o", "link", "show", "type", "tun"])
    except Exception:
        return None
    if exit_code != 0 or not _decode_output(output):
        return None
    # First line: "4: tun_ethhak: <...>" — extract interface name
    first_line = _decode_output(output).splitlines()[0]
    match = re.match(r"\d+:\s+(\S+?):", first_line)
    return match.group(1) if match else None


def get_interface_ipv4(container, interface: str) -> str | None:
    """Return the IPv4 assigned to an interface, if present."""
    try:
        exit_code, output = container.exec_run(["ip", "-4", "-o", "addr", "show", "dev", interface])
    except Exception:
        return None

    if exit_code != 0:
        return None

    match = _IPV4_ADDR_RE.search(_decode_output(output))
    if not match:
        return None
    return match.group(1)
