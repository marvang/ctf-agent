# CTF Agent v1.0

Två delar för att komma igång:  
1. **Kali Linux container** via Docker  
2. **CTF Agent** som föreslår kommandon som sedan körs (med human approval)  

Dependencies via **uv** istället för pip. Skaffa uv, det är bättre, fråga chatgpt varför.
```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.sh | iex"
# om det inte funkar, testa:
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
astral.sh
```

## Prerequisites
- [Docker](https://docs.docker.com/get-docker/) Desktop  
- [uv](https://github.com/astral-sh/uv)  
- **GROQ_API_KEY** (gratis, snabb inference)  
- **OpenRouter API key** (för GPT-5 Claude och Gemini, ej implementerat än)  

## Quick Start: Kali
I terminalen gå till ctf-agent mappen och kör följande.
```bash
# Bygg image (Tar lång tid, bra internet behövs)
docker compose build
# Kolla docker desktop appen, du ska se en ctf-agent image.
# Starta container (i bakgrunden)
docker compose up -d

# Gå in i Kali från terminalen
docker compose exec kali bash
# Testa köra kommandon: ls, pwd, whoami, nmap localhost

# Avsluta
exit
# kör docker ps för att se aktiva containers.
# Stoppa container
docker compose down
```

## Quick Start: Agent
```bash
# Installera dependencies
uv sync

# Starta container om inte redan igång
docker compose up -d

# Kör playground notebook först och testa köra alla celler
# skapa fil som heter .env
# Lägg till API KEY i .env
# Vi kör GROQ_API_KEY men ska byta till OpenRouter med vår 100$ credit från hackathonet.

# Kör main.py (semi-automatiserad, kör ett kommando och stänger ner)
python main.py
```

### Vad main.py gör
1. Använder LLM för att generera kommando  
2. Frågar efter ditt godkännande (`yes/no`)  
3. Kör i Kali-containern om godkänt och visar output  

## Features
- Laddar API keys från `.env`  
- Human approval före körning  
- Docker-exekvering med error handling  
- Ren outputformattering  

## TODO
- Command history, LLMen kan se historik och fortsätta köra kommandon. 
- Auto Loop mode (ingen mänsklig översikt)
- Validation & safety checks (agenter som dubbellkollar och verifierar vad huvudagenten gör) 
- Köra agenten på riktigt och test om den kan hitta enkla ctf-flaggor
- Lägg till Temporal AI (viktigt)ww
- Multi-agentiskt workflow system (viktigt)
- lägg till Mount/shared volumes: Persist data, logs, code.
- lägg till så LLmen alltid ser vart den är
USER: root
HOST: f08654ced603
CWD: /workspace
NETWORK: container-only
Then include the visible prompt as a cosmetic aid for human readers.

EXTRA:
- Logging & audit trail  # samla och spara all data för analys
- Multi-container support  
- Rollback funktion  
- Specialiserade agenter som huvudagenten kan kalla på för specifika uppgifter
- Agent som kan köra och testa kod i sandbox
- Tillgång till internet eller resurser när den fastnar.
