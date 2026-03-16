#!/usr/bin/env bash
# Generic Private VPN Connection Script
# Auto-detects .ovpn file and connects via OpenVPN.
#
# Usage:
#   ./vpn-connect.sh              # Connect
#   ./vpn-connect.sh --disconnect  # Disconnect
#
# For complex VPN setups, replace this script with your own.
# Must support --disconnect flag. Runs as root inside Kali container.

set -e

cd "$(dirname "$(realpath "$0")")" || exit 1

# Check root
if [[ "${UID:-0}" -ne 0 ]]; then
    echo "This script must be run as root (required for VPN management)"
    exit 1
fi

# Check OpenVPN
if ! command -v openvpn &>/dev/null; then
    echo "OpenVPN is not installed. Install with: apt-get install openvpn"
    exit 1
fi

# Auto-detect .ovpn file
OVPN_FILES=(*.ovpn)
OVPN_COUNT=0
for f in "${OVPN_FILES[@]}"; do
    [[ -f "$f" ]] && ((OVPN_COUNT++))
done

if [[ "$OVPN_COUNT" -eq 0 ]]; then
    echo "No .ovpn file found in $(pwd)"
    echo "Place your VPN configuration file (.ovpn) in this directory."
    exit 1
elif [[ "$OVPN_COUNT" -gt 1 ]]; then
    echo "Multiple .ovpn files found:"
    ls -1 *.ovpn
    echo "Keep only one .ovpn file in this directory."
    exit 1
fi

OVPN_FILE="${OVPN_FILES[0]}"
LOG_FILE=".openvpn.log"

# Handle --disconnect
if [[ "$1" == "--disconnect" ]]; then
    echo "Stopping VPN connections..."
    if pgrep -f "openvpn.*${OVPN_FILE}" &>/dev/null; then
        pkill -f "openvpn.*${OVPN_FILE}" && echo "VPN disconnected." || {
            echo "Force killing..."
            pkill -9 -f "openvpn.*${OVPN_FILE}" 2>/dev/null
        }
    else
        echo "No active VPN connection found."
    fi
    exit 0
fi

# Check if already connected
if pgrep -f "openvpn.*${OVPN_FILE}" &>/dev/null; then
    echo "OpenVPN is already running with ${OVPN_FILE}."
    echo "Disconnect first with: $0 --disconnect"
    exit 1
fi

# Create TUN device if missing
if [[ ! -c /dev/net/tun ]]; then
    echo "Creating TUN device..."
    mkdir -p /dev/net
    mknod /dev/net/tun c 10 200
    chmod 666 /dev/net/tun
fi

# Check internet connectivity
if ! ping -c 2 -W 2 8.8.8.8 &>/dev/null; then
    echo "Warning: No internet connectivity detected. VPN may fail."
fi

# Start OpenVPN
echo "Connecting with ${OVPN_FILE}..."
openvpn --config "$OVPN_FILE" --log "$LOG_FILE" --daemon

# Wait for connection
echo "Waiting for VPN connection..."
CONNECTED=false
for i in $(seq 1 15); do
    if grep -q "Initialization Sequence Completed" "$LOG_FILE" 2>/dev/null; then
        CONNECTED=true
        break
    fi
    sleep 1
done

if [[ "$CONNECTED" == "true" ]] && ip link show | grep -q tun; then
    echo "VPN connection successful."
    ip addr show | grep -E "(tun|inet)" | head -10
else
    echo "VPN connection failed."
    echo "Check logs: cat $(pwd)/$LOG_FILE"
    exit 1
fi
