# CTF Agent v1.4 - HackTheBox Integration

## 🚀 Snabbstart

### Förkunskaper
- Docker Desktop
- uv (Python package manager)
- OPENROUTER_API_KEY

### Installation

1. **Installera uv (Python package manager)**
```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.sh | iex"
# om det inte funkar, testa:
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

2. **Installera dependencies**
```bash
source ./venv/bin/activate
uv sync
```

3. **Konfigurera API-nycklar**
```bash
# Skapa .env-fil i projektets root
echo "OPENROUTER_API_KEY=din_nyckel_här" > .env
echo "OPENROUTER_MODEL=anthropic/claude-3.5-sonnet" >> .env
echo "TARGET_IP=10.129.80.148" >> .env

# Supportade modeller:
# OPENROUTER_MODEL=openai/gpt-4o-mini
# OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
# OPENROUTER_MODEL=x-ai/grok-beta
```

4. **Starta Docker-miljön**
```bash
# Bygg container (tar några minuter första gången)
docker compose build 

# Starta container i bakgrunden
docker compose up -d
```

5. **Kör CTF Agent**
```bash
python main.py
```

## 🌟 Nya funktioner i v1.4

### 🌐 HackTheBox VPN Integration
- **Automatisk VPN-anslutning** till HackTheBox labs
- **Dual-miljö support**: Lokal container + HackTheBox VPN
- **Target IP konfiguration** via .env-variabler

### 🎯 Miljöval vid start
```
🌐 Välj miljö:
1. Lokal miljö (standard)
2. HackTheBox - Meow (Starting Point)
```

### 🤖 Förbättrad AI-agent
- **Specialiserad HackTheBox prompt** med Telnet-exploitation kunskap
- **Automatisk nmap-scanning** av target IP
- **Smart exit-detection** för automatisk avslutning
- **Flagga-saving automation** innan programavslutning

### ⚙️ Körlägen
- **Auto**: Kör kommandon automatiskt (max 15 iterationer)
- **Semi-Auto**: Frågar innan varje kommando

## 📋 Manuell setup för HackTheBox

### 🔧 HackTheBox VPN Setup
```bash
# 1. Ladda ner din .ovpn-fil från HackTheBox
# 2. Kopiera till ctf-workspace
cp ~/Downloads/lab_connection.ovpn ./ctf-workspace/hackthebox.ovpn

# 3. Gör VPN-skript körbara
chmod +x ./ctf-workspace/connect-htb.sh
chmod +x ./ctf-workspace/disconnect-htb.sh
```

### 🚀 Daglig användning
```bash
# 1. Starta programmet
python main.py

# 2. Välj HackTheBox-miljö (alternativ 2)
# 3. Agenten ansluter automatiskt till VPN
# 4. Börjar med nmap-scanning av target IP
# 5. Följer Telnet-exploitation strategi
# 6. Sparar flaggan och avslutar automatiskt
```

## 🛠️ Grundläggande funktioner (från v1.3)

### Container Management
```bash
# Kali shell (optional)
docker compose exec kali bash
exit

# Stäng ner miljön
docker compose down
```

### Workspace
- **Delad mapp** mellan projektet och containern
- **Automatisk filhantering** för flaggor och rapporter
- **Session-logging** av alla kommandon och resultat

### Optional: Watcher
```bash
# Kör i separat terminal för att övervaka ändringar
python watcher.py
```

## 📁 Automatiskt skapade filer

```
ctf-logs/
├── sessions.json       # Session-historik med kommandon
├── token_logs.jsonl    # API-användningsstatistik
└── token_state.json    # Token-räknare per modell

ctf-workspace/
├── flags.txt          # Upptäckta flaggor
├── reports.txt        # Detaljerade rapporter
├── hackthebox.ovpn    # VPN-konfiguration (manuell)
├── connect-htb.sh     # VPN-anslutningsskript
└── disconnect-htb.sh  # VPN-frånkopplingsskript
```

## 🔍 Övervakningspunkter

### För användaren att hålla koll på:
1. **API-krediter** i OpenRouter-kontot
2. **VPN-anslutningsstatus** (visas i programmet)
3. **Target IP-adresser** (updatera TARGET_IP i .env vid behov)
4. **Session-resultat** i ctf-logs-mappen
5. **Docker-containernsatuts** (kör `docker ps` för att kontrollera)

## 🛡️ Säkerhetsfunktioner

- **Signal-hantering** för graceful shutdown (Ctrl+C)
- **Timeout-skydd** för kommandon (120 sekunder)
- **Iteration-begränsning** (max 15 i auto-läge)
- **VPN-verifiering** innan målscanning
- **Automatisk filrensning** mellan sessions

## TODO v1.5+

### Högt prioriterat:
- ✅ **Koppla till riktig CTF-miljö** (HackTheBox integration klar)
- **Multi-agentiskt workflow** (separata agenter för recon, exploit, post-exploit)
- **Utökat HackTheBox support** (fler Starting Point labs)

### Medel prioriterat:
- **Visa USER/HOST/CWD/NETWORK** i agentens kontext
- **Agent som kan testa scripts** i separat sandboxmiljö
- **Huvudagent för planering** och strategisk delegering
- **Rollback-funktion** med sammanfattningar

### Lågt prioriterat:
- **Reasoning caching**
- **Cached tokens** för kostnadsoptimering
- **Temporal AI** för tidsbaserade beslut

---

**🎯 CTF Agent v1.4 är nu helt automatiserad för HackTheBox Meow-utmaningen och kräver minimal manuell intervention!**