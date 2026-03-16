"""Shared environment typing and helpers for interactive and experiment flows."""

from typing import Literal

EnvironmentType = Literal["local", "private", "htb"]
VpnEnvironment = Literal["private", "htb"]
LocalArch = Literal["aarch64", "amd64"]

_ENVIRONMENT_LABELS: dict[EnvironmentType, str] = {
    "local": "Local Docker challenge",
    "private": "Private Cyber Range",
    "htb": "Hack The Box",
}


def get_environment_label(environment_mode: EnvironmentType) -> str:
    """Return the user-facing label for a selected environment."""
    return _ENVIRONMENT_LABELS[environment_mode]


def uses_vpn(environment_mode: EnvironmentType) -> bool:
    """Return whether the selected environment relies on a VPN interface."""
    return environment_mode != "local"
