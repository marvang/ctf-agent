# Kali Machine with Docker Compose + CTF Agent

This project provides two main components:

1. **Kali Linux container** via Docker Compose.  
2. **CTF Agent** that uses LLM reasoning to propose and execute commands (with human approval).  

Dependencies are managed with **uv** instead of pip.

---

## Prerequisites
- [Docker](https://docs.docker.com/get-docker/) installed.  
- [uv](https://github.com/astral-sh/uv) installed.  
- API keys:
  - **GROQ_API_KEY** (free, for fast/cheap inference).  
  - **OpenRouter API key** (for GPT-5 and other larger models).  

---

# Quick Start: Kali Container

### 1. Build and start
```bash
docker compose build
docker compose up -d
```

### 2. Enter Kali
```bash
docker compose exec kali bash
```

### 3. Exit
```bash
exit
```

### 4. Stop container
```bash
docker compose down
```

---

# Quick Start: CTF Agent

### 1. Install dependencies
```bash
uv sync
```

### 2. Configure environment variables
```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### 3. Ensure Kali container is running
```bash
docker compose up -d
```

### 4. Run the agent
```bash
python main.py
```

The agent will:
1. Use LLM to reason about the environment.  
2. Generate a shell command.  
3. Ask for your approval (`yes/no`).  
4. If approved, execute inside the Kali container and display the output.  

---

## Features
- Loads API keys from `.env`.  
- Human approval before execution.  
- Docker container execution with error handling.  
- Clean output formatting.  

---

## Roadmap / TODO
- Command history  
- Continuous loop mode  
- Validation and safety checks  
- Multiple challenge modes  
- Logging and audit trail  
- Configurable environments  
- Multi-container support  
- Rollback functionality  
