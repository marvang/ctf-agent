# CTF Agent v1.2

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
source ./venv/bin/activate
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
Här kan vi lägga in flera funktioner, logga kommandon, outputs osv.
```bash
python watcher.py
```

## TODO   
- Multi-agentiskt workflow  (VIKTIGT- Erik?)
- Visa USER/HOST/CWD/NETWORK i agentens kontext  
- Token- och kostnadsmätning (live)  
- Koppla till riktig CTF-miljö (VIKTIGT- Adam)
- Agent som kan köra och testa scripts i separat sandboxmiljö, verifiera outputs (multi-agent).
- Huvud-agent som ansvarar för planering, strategi, och delegering av uppgifter.
- Rollback funktion. Detta innebär att lägga in en treshold där efter ett tag, eller viss antal tokens, så stoppar vi körningen. Därefter ber vi språkmodellen sammanfatta det den har gjort, vad som fungerat, vad som inte fungerat, detta ges som fördel till i workspace för nästa körning, så att agenten kan "starta om på nytt" med fördel.
- Temporal AI 
- Structured outputs (json schema)
- reasoning?
- cached tokens?
