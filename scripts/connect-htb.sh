#!/bin/bash
# Universal HackTheBox VPN Connection Script for CTF Agent
# Auto-detects OS and adapts commands accordingly

set -e

# Auto-detect VPN config file
OVPN_FILES=(*.ovpn)
OVPN_COUNT=${#OVPN_FILES[@]}

if [ $OVPN_COUNT -eq 0 ] || [ ! -f "${OVPN_FILES[0]}" ]; then
    echo "❌ Error: No .ovpn file found in current directory"
    exit 1
elif [ $OVPN_COUNT -gt 1 ]; then
    echo "❌ Error: Multiple .ovpn files found:"
    ls -1 *.ovpn
    echo "Please keep only one .ovpn file in the directory"
    exit 1
else
    VPN_CONFIG="${OVPN_FILES[0]}"
    echo "✅ Found VPN config: $VPN_CONFIG"
fi

LOG_FILE="/ctf-workspace/vpn.log"

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

echo "$OS_EMOJI Universal HackTheBox VPN Connection Script ($OS_NAME)"
echo "========================================================"

# Check if OpenVPN is installed
if ! command -v openvpn &> /dev/null; then
    echo "❌ OpenVPN not found!"
    if [[ "$OS_TYPE" == "Darwin" ]]; then
        echo "💡 Install with: brew install openvpn"
    else
        echo "💡 Install with: apt-get install openvpn (Linux) or check OpenVPN documentation"
    fi
    exit 1
fi

# Create TUN device if it doesn't exist (Linux only)
if [[ "$OS_TYPE" == "Linux" ]] && [ ! -c /dev/net/tun ]; then
    echo "⚠️  TUN device not found, trying to create..."
    mkdir -p /dev/net
    mknod /dev/net/tun c 10 200
    chmod 666 /dev/net/tun
fi

# Check if already connected
if pgrep openvpn > /dev/null; then
    echo "✅ OpenVPN is already running"
    echo "📊 Current network interfaces:"
    if [[ "$OS_TYPE" == "Darwin" ]]; then
        ifconfig | grep -E "(tun|utun|inet)"
    else
        ip addr show | grep -E "(inet|UP|DOWN)"
    fi
    exit 0
fi

echo "🚀 Starting OpenVPN connection to HackTheBox..."
echo "📝 Logs will be written to: $LOG_FILE"

# Start OpenVPN in background (with sudo on macOS)
if [[ "$OS_TYPE" == "Darwin" ]]; then
    echo "🔐 macOS detected - may require sudo password..."
    nohup sudo openvpn --config "$VPN_CONFIG" --log "$LOG_FILE" --daemon &
    sleep 15  # macOS needs more time
else
    nohup openvpn --config "$VPN_CONFIG" --log "$LOG_FILE" --daemon &
    sleep 10  # Linux timing
fi

# Wait for connection to establish
echo "⏳ Waiting for VPN connection to establish..."

# Check if OpenVPN is running
if pgrep openvpn > /dev/null; then
    echo "✅ OpenVPN process is running"

    # Check for tun interface (OS-specific)
    TUN_FOUND=false
    if [[ "$OS_TYPE" == "Darwin" ]]; then
        # macOS uses utun interfaces
        if ifconfig | grep -E "(tun|utun)" > /dev/null; then
            TUN_FOUND=true
            echo "✅ TUN interface created successfully"
            echo "📊 Network interfaces:"
            ifconfig | grep -E "(tun|utun|inet)" | head -20

            # Show VPN IP if available
            VPN_IP=$(ifconfig | grep -A1 utun | grep inet | awk '{print $2}' | head -1)
            if [ ! -z "$VPN_IP" ]; then
                echo "🌐 VPN IP: $VPN_IP"
            fi
        fi
    else
        # Linux uses tun interfaces
        if ip link show | grep -q tun; then
            TUN_FOUND=true
            echo "✅ TUN interface created successfully"
            echo "📊 Network interfaces:"
            ip addr show | grep -E "(inet|UP|DOWN)"
        fi
    fi

    if [ "$TUN_FOUND" = true ]; then
        # Test connectivity
        echo "🔍 Testing connectivity..."
        if ping -c 3 8.8.8.8 > /dev/null 2>&1; then
            echo "✅ Internet connectivity confirmed"
        else
            echo "⚠️  Internet connectivity test failed"
        fi

        echo ""
        echo "🎉 VPN connection established successfully!"
        echo "📋 You can now start your CTF activities"
        echo "📝 Check logs with: cat $LOG_FILE"

        if [[ "$OS_TYPE" == "Darwin" ]]; then
            echo "🔌 Disconnect with: sudo pkill openvpn"
        else
            echo "🔌 Disconnect with: pkill openvpn"
        fi

    else
        echo "❌ TUN interface not found - connection may have failed"
        echo "📝 Check logs: cat $LOG_FILE"
        exit 1
    fi
else
    echo "❌ OpenVPN process not running - connection failed"
    echo "📝 Check logs: cat $LOG_FILE"
    if [[ "$OS_TYPE" == "Darwin" ]]; then
        echo "💡 Tip: Make sure you entered the correct sudo password"
    fi
    exit 1
fi