# Private VPN Setup

## Quick setup (simple VPN)

1. Place your `.ovpn` file in this directory
2. If your VPN needs separate cert/key files, place those here too
3. Run the CTF agent (`python main.py`) and select **Private VPN**
4. The included `vpn-connect.sh` auto-detects your `.ovpn` file and connects

## Custom setup (complex VPN)

If your VPN needs a custom connection script:

1. Place your `.ovpn` and cert files in this directory
2. Add your own `.sh` script to this directory
3. Make the script executable with `chmod +x your-script.sh`
4. When prompted, select your script instead of the generic one

### Script requirements

- Must support `--disconnect` flag to tear down the connection
- Must be executable (`chmod +x your-script.sh`)
- Runs as root inside the Kali Docker container
- Working directory is this folder (`/ctf-workspace/vpn/private/` inside container)
