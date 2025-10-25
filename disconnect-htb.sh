#!/bin/bash
# Universal HackTheBox VPN Disconnection Script
# Auto-detects OS and adapts commands accordingly

# Detect OS
OS_TYPE=$(uname)
case "$OS_TYPE" in
    "Darwin")
        OS_NAME="macOS"
        OS_EMOJI="🍎"
        ;;
    "Linux")
        OS_NAME="Linux"
        OS_EMOJI="🐧"
        ;;
    *)
        OS_NAME="Unknown"
        OS_EMOJI="❓"
        ;;
esac

echo "$OS_EMOJI Disconnecting from HackTheBox VPN ($OS_NAME)..."

# Kill OpenVPN processes (without sudo - container has root access)
if pgrep openvpn > /dev/null; then
    echo "� Terminating OpenVPN..."
    pkill -TERM openvpn
    sleep 2
    
    # Force kill if still running
    if pgrep openvpn > /dev/null; then
        echo "⚠️  Force killing OpenVPN..."
        pkill -KILL openvpn
        sleep 1
    fi
    
    echo "✅ OpenVPN processes terminated"
else
    echo "ℹ️  No OpenVPN processes found"
fi

# Final check
if ! pgrep openvpn > /dev/null; then
    echo "✅ Successfully disconnected from VPN"
else
    echo "❌ Warning: Some OpenVPN processes may still be running"
    exit 1
fi