# CTF Agent v1.4 - Med HackTheBox VPN Support

**Nytt i v1.4:** Fullständigt stöd för HackTheBox VPN-anslutning!

## Översikt
Två delar för att komma igång:
1. **Kali Linux container** via Docker med VPN-support
2. **CTF Agent** som föreslår kommandon som sedan körs (med human approval)  

## Prerequisites
- [Docker](https://docs.docker.com/get-docker/) Desktop  
- [uv](https://github.com/astral-sh/uv) package manager
- **OPENROUTER_API_KEY** (från hackathon Discord channel)
- **HackTheBox VPN-fil** (.ovpn format)

## Quick Start

### 1) Install Dependencies
```bash
source ./venv/bin/activate
uv sync
```

### 2) Konfigurera API Key
Skapa `.env` fil i project root:
```bash
OPENROUTER_API_KEY=din_nyckel_här
OPENROUTER_MODEL=openai/gpt-5-mini
# Andra modeller: anthropic/claude-sonnet-4.5, x-ai/grok-code-fast-1
```

### 3) Förbered VPN (för HackTheBox)
- Ladda ner din HackTheBox VPN-fil (.ovpn)
- Kopiera den till `ctf-workspace/hackthebox.ovpn`
- Eller använd det befintliga exemplet för "starting_point_thepostman"

### 4) Starta Docker Environment
```bash
# Bygger container med VPN-support (kan ta några minuter första gången)
docker compose build 

# Startar container i bakgrund
docker compose up -d

# Verifiera att containern körs
docker compose ps
```

### 5) Anslut till HackTheBox VPN
```bash
# Öppna shell i Kali container
docker compose exec kali bash

# I containern, anslut till VPN
./connect-htb.sh

# Verifiera anslutning (bör visa tun-interface)
ip addr show
```

### 6) Kör CTF Agent
```bash
# Från host-systemet (inte i containern)
python main.py
```

### 7) Koppla ner när du är klar
```bash
# I containern
./disconnect-htb.sh

# Stäng ner hela miljön
docker compose down
```

## Användning

### VPN Management
- **Anslut:** `./connect-htb.sh` (i containern)
- **Koppla ner:** `./disconnect-htb.sh` (i containern)
- **Status:** `ip addr show` eller `ping target_ip`
- **Loggar:** `cat /ctf-workspace/vpn.log`

### CTF Agent Modes
- **Auto:** Kör kommandon automatiskt (max 15 iterationer)
- **Semi-Auto:** Frågar om godkännande för varje kommando

### Workspace
- `ctf-workspace/` - Delad mapp mellan host och container
- `flags.txt` - Automatiskt sparade flaggor
- `reports.txt` - Automatiska rapporter efter sessions

## Troubleshooting

### VPN Problem
```bash
# Kontrollera OpenVPN status
ps aux | grep openvpn

# Kontrollera TUN device
ls -la /dev/net/tun

# Manuell VPN-anslutning för debugging
openvpn --config /ctf-workspace/hackthebox.ovpn --log /tmp/vpn-debug.log
```

### Docker Problem
```bash
# Återställ Docker environment
docker compose down
docker system prune -f
docker compose build --no-cache
docker compose up -d
```

### Nätverk Debugging
```bash
# I containern
ping 8.8.8.8                    # Test internet
nmap -sn 10.10.10.0/24         # Scan HackTheBox subnet
traceroute target_ip           # Trace route to target
```

## HackTheBox Specifika Tips

### Starting Point: The Postman
- **Target IP:** Vanligtvis i 10.10.10.x range
- **Initial Scan:** `nmap -sCV target_ip`
- **Common Ports:** 22 (SSH), 80 (HTTP), 443 (HTTPS)

### Vanliga Kommandon
```bash
# Grundläggande reconnaissance
nmap -sCV -oA postman_scan target_ip
gobuster dir -u http://target_ip -w /usr/share/wordlists/dirb/common.txt

# Web enumeration
curl -I http://target_ip
nikto -h http://target_ip

# Service enumeration
telnet target_ip port
nc -nv target_ip port
```

## Optional: Watcher
```bash
# Kör i separat terminal för att övervaka workspace
python watcher.py
```

## Säkerhet & Begränsningar
- Containern körs med `privileged: true` för VPN-funktionalitet
- Detta krävs för TUN/TAP device access
- Använd endast i isolerade testmiljöer
- Stäng alltid ner miljön efter användning

## Features
- ✅ HackTheBox VPN integration
- ✅ Automatisk flaggdetektering
- ✅ Session logging och token tracking
- ✅ Timeout-skydd för kommandon
- ✅ Auto/Semi-auto modes
- ✅ Comprehensive network tools (Kali Linux)

## Kommande Features
- Multi-agent workflow
- Temporal AI integration
- Rollback-funktionalitet
- Automatisk target discovery

---
**Version:** 1.4  
**Senast uppdaterad:** September 30, 2025