# CTF Agent v1.1

Två delar för att komma igång:  
1. **Kali Linux container** via Docker  
2. **CTF Agent** som föreslår kommandon som sedan körs (med human approval)  

Dependencies via **uv** istället för pip.
ladda ner:
```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.sh | iex"
# om det inte funkar, testa:
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
astral.sh
```

Get the **OpenRouter API key** from the hackathon Discord channel.

## Prerequisites
- [Docker](https://docs.docker.com/get-docker/) Desktop  
- [uv](https://github.com/astral-sh/uv)  
- **OPENROUTER_API_KEY**

## Quick Start
1) **Install dependencies**
```bash
uv sync
```

2) **Set API key**
```bash
# skapa fil som heter .env in the project root and add OPENROUTER_API_KEY=nyckel
# eller kör
echo "OPENROUTER_API_KEY=your-key-here" > .env
# get the key from the hackathon Discord channel
```

3) **Start container and run agent**
```bash
# build kan ta några minuter
docker compose build 
# kör container i bakgrund
docker compose up -d
python main.py
# ctrl+C för att stänga av, och sen kör: docker compose down
```

- **Kali shell (optional):**
```bash
docker compose exec kali bash
exit
docker compose down
```
- **Workspace:** en delad mapp som finns både i projektet och inne i containern.

- **Playground (optional):** snabb plats att testa nya idéer och förstå grunderna innan du läser main-koden.

## Features
- Läser **OPENROUTER_API_KEY** från `.env`   
- Timeout-skydd för kommandon   

## Optional: Watcher
Kör i separat terminal på din dator för att se ändringar i workspace och logga dem.
```bash
pip install watchdog
python watcher.py ./ctf-workspace
# gör en ändring i workspace för att se loggar
```

## TODO
- Command history och sessioner per körning  
- Semi-auto läge och full-auto läge  
- Validation & safety checks (dubbelkolla och verifiera steg)  
- Multi-agentiskt workflow  
- Visa USER/HOST/CWD/NETWORK i agentens kontext  
- Token- och kostnadsmätning (live)  
- Koppla till riktig CTF-miljö
- Agent som kan köra och testa kod i sandbox
- Rollback funktion 
