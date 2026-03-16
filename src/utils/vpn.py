"""VPN connection management utilities"""
import os
import re
import shlex


def _filter_vpn_output(text: str) -> str:
    """Remove noisy/unhelpful lines from VPN connect script output."""
    skip_patterns = [
        re.compile(r"^\d{4}-\d{2}-\d{2}\s"),          # timestamped OpenVPN log lines
        re.compile(r"^📊 Network interfaces:"),
        re.compile(r"^🔍 Testing connectivity"),
        re.compile(r"^🎉 VPN connection established"),
        re.compile(r"^📋 You can now start"),
    ]
    lines = text.splitlines()
    filtered: list[str] = []
    inside_iface_block = False
    for line in lines:
        if any(p.search(line) for p in skip_patterns):
            if "📊 Network interfaces:" in line:
                inside_iface_block = True
            continue
        if inside_iface_block:
            # interface block lines: numbered entries or indented inet lines
            if re.match(r"^\d+:|^\s+inet", line):
                continue
            inside_iface_block = False
        filtered.append(line)
    return "\n".join(filtered).strip()


def _build_command(workdir: str, command: str) -> str:
    """Build a shell command that runs inside a VPN environment directory."""
    return f"cd {shlex.quote(workdir)} && {command}"


ENVIRONMENTS = {
    "private": {
        "label": "Private Cyber Range",
        "workdir": "/ctf-workspace/vpn/private",
        "connect_cmd": "./vpn-connect.sh",
        "disconnect_cmd": "./vpn-connect.sh --disconnect",
    },
    "htb": {
        "label": "HackTheBox",
        "workdir": "/ctf-workspace/vpn/htb",
        "connect_cmd": "./connect-htb.sh",
        "disconnect_cmd": "./disconnect-htb.sh",
    },
}


def get_vpn_setup_hint(environment: str) -> str:
    """Return a short setup hint for the selected VPN environment."""
    workdir = ENVIRONMENTS[environment]["workdir"]
    return f"📝 VPN setup required: place your .ovpn file in {workdir} and try again."


def discover_vpn_scripts(container, environment: str) -> list[str]:
    """List .sh files in the VPN workdir inside the container."""
    workdir = ENVIRONMENTS[environment]["workdir"]
    exit_code, output = container.exec_run(
        ["bash", "-c", f"ls {shlex.quote(workdir)}/*.sh 2>/dev/null"]
    )
    if exit_code != 0:
        return []
    return [
        os.path.basename(f)
        for f in output.decode("utf-8", errors="replace").strip().splitlines()
        if f.strip()
    ]


def check_vpn_connection(container) -> bool:
    try:
        exit_code, _ = container.exec_run(["bash", "-c", "ip link show | grep tun"])
        return exit_code == 0
    except Exception:
        return False


def connect_vpn(container, environment: str = "private", connect_script: str | None = None) -> bool:
    env = ENVIRONMENTS[environment]
    connect_cmd = f"./{connect_script}" if connect_script else env["connect_cmd"]

    print(f"\n🔗 Connecting to {env['label']} VPN...")
    try:
        exit_code, output = container.exec_run(
            ["bash", "-c", _build_command(env["workdir"], connect_cmd)]
        )
        command_output = output.decode("utf-8", errors="replace").strip()
        if command_output:
            filtered = _filter_vpn_output(command_output)
            if filtered:
                print(filtered)

        if exit_code == 0 and check_vpn_connection(container):
            print("✅ VPN connected")
            return True
        if exit_code != 0:
            print(f"⚠️  VPN connect script exited with code {exit_code}")
        print("❌ VPN connection failed")
        return False
    except Exception as e:
        print(f"❌ VPN error: {e}")
        return False


def disconnect_vpn(container, environment: str = "private", connect_script: str | None = None) -> bool:
    env = ENVIRONMENTS[environment]
    if connect_script:
        disconnect_cmd = f"./{connect_script} --disconnect"
    else:
        disconnect_cmd = env["disconnect_cmd"]

    print(f"🔌 Disconnecting VPN...")
    try:
        exit_code, output = container.exec_run(
            ["bash", "-c", _build_command(env["workdir"], disconnect_cmd)]
        )
        if exit_code == 0:
            print("✅ VPN disconnected")
        else:
            print(f"⚠️  VPN disconnect failed (exit code {exit_code})")
        return exit_code == 0
    except Exception as e:
        print(f"❌ VPN disconnect error: {e}")
        return False
