"""VPN connection management utilities for HackTheBox"""


def check_vpn_connection(container) -> bool:
    """
    Check if VPN is already connected by looking for tun interface

    Args:
        container: Docker container instance

    Returns:
        True if VPN is connected, False otherwise
    """
    try:
        exit_code, output = container.exec_run(["bash", "-c", "ip link show | grep tun"])
        return exit_code == 0
    except Exception:
        return False


def connect_to_hackthebox(container) -> bool:
    """
    Attempt to connect to HackTheBox VPN using the connect script.
    The script auto-detects .ovpn files, so no filename checking needed here.

    Args:
        container: Docker container instance

    Returns:
        True if connection successful, False otherwise
    """
    print("\n🔗 Connecting to HackTheBox VPN...")
    try:
        # Run connection script (it will auto-detect the .ovpn file)
        exit_code, output = container.exec_run([
            "bash", "-c",
            "cd /ctf-workspace && ./connect-htb.sh"
        ])

        # Verify connection
        if check_vpn_connection(container):
            print("✅ VPN connected")
            return True
        else:
            print("❌ VPN connection failed")
            return False

    except Exception as e:
        print(f"❌ VPN error: {e}")
        return False


def disconnect_from_hackthebox(container) -> bool:
    """
    Disconnect from HackTheBox VPN using the disconnect script.

    Args:
        container: Docker container instance

    Returns:
        True if disconnection successful, False otherwise
    """
    print("\n🔌 Disconnecting from HackTheBox VPN...")
    try:
        exit_code, output = container.exec_run([
            "bash", "-c",
            "cd /ctf-workspace && ./disconnect-htb.sh"
        ])

        print(output.decode('utf-8'))

        if exit_code == 0:
            print("✅ VPN disconnected successfully")
        else:
            print(f"⚠️  Disconnect script exited with code {exit_code}")

        return exit_code == 0
    except Exception as e:
        print(f"❌ VPN disconnect error: {e}")
        return False
