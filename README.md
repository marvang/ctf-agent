# Fully Autonomous AI-Driven Penetration Testing Framework

AI agent that finds and exploits vulnerabilities to solve CTF challenges.

- Autonomous reconnaissance and exploitation
- HackTheBox VPN support
- Local (Docker) and remote target support
- Real-time cost & token tracking
- Logs each session with timestamps, commands, context, and results

## Requirements

- Python 3.10+ 
- Docker Desktop  
- uv (Python package manager)  
- OpenRouter API key  
- HackTheBox account

## Installation

### 1. Install uv (Python Package Manager)

**Linux/macOS:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -c "irm https://astral.sh/uv/install.sh | iex"
```

If the above doesn't work on Windows, try:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After installation, restart your terminal or add uv to your PATH.

### 2. Clone the Repository

```bash
git clone <repository-url>
cd ctf-agent
```

### 3. Install Python Dependencies

```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv sync
```

### 4. Configure Environment Variables

Create a `ctf-workspace/` folder in project root and add the connect-htb.sh and disconnect-htb.sh scripts there.

Create a `.env` file in the project root:

```bash
# Required: OpenRouter API credentials
OPENROUTER_API_KEY=sk-or-v1-your-api-key-here

# Required: Model selection
OPENROUTER_MODEL=openai/gpt-5 # pick any model but gpt-5 and codex are good, sonnet-4.5 is also good but not as tested.
```

### 5. Get OpenRouter API Key

Get an API key from [OpenRouter](https://openrouter.ai/) and add it to your `.env` file.

### 6. Install Docker Desktop

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) for your platform.

### 7. Build the Docker Container

Navigate to project folder. The container is based on Kali Linux and includes all penetration testing tools:

```bash
# Build the container (takes 5-15 minutes first time)
docker compose build

# Start the container in detached mode
docker compose up -d

# Verify the container is running
docker ps
```

## Getting Started

Navigate to your active machine on HackTheBox and download your `.ovpn` VPN configuration file to `ctf-workspace/` folder.

**Start the CTF Agent:**
```bash
python main.py
```

Select environment `2` (local container recommended first time for testing) and mode `1` (semi-auto recommended first time for testing).

Enter target IP address (find it on the HackTheBox machine page):
```
🎯 Target IP [10.129.80.148]: <enter-target-ip>
```

Optional: Add custom instructions to LLM (e.g., "run a quick scan to start with" or "this challenge has two flags, find both flags before stopping")

The agent will:
   - Connect to HackTheBox VPN automatically
   - Begin reconnaissance (nmap scans)
   - Enumerate services
   - Exploit vulnerabilities
   - Extract flags to `./ctf-workspace/flags.txt`

## Project Structure

The `ctf-workspace` directory is shared between your machine and the Docker container

```
.
├── main.py
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── README.md
├── .env *                     # Requires manual setup
├── ctf-workspace/ *           # Requires manual setup
│   ├── flags.txt              
│   ├── report.txt             
│   ├── improvement_notes.txt  
│   ├── *.ovpn *               
│   ├── connect-htb.sh        
│   └── disconnect-htb.sh      
└── src/
    ├── config/
    │   └── logging.py
    ├── llm_utils/
    │   ├── api_call.py
    │   ├── openrouter.py
    │   └── prompts.py
    └── utils/
        ├── model_utils.py
        ├── response_schema.py
        └── state_manager.py
```

### Docker Container Management

```bash
# Access the Kali container directly
docker compose exec kali bash

# Stop the container
docker compose down

# Rebuild after Dockerfile changes
docker compose build --no-cache

# View container logs
docker compose logs kali
```

## Contributing

Contributions welcome! Areas for improvement:

### TODO
- Multi-agent workflow (separate agents for orchestration, validation, sandbox)
- Benchmark harness feature for running large scale experiments on multiple boxes and ctfs.
- Additional CTF platform integrations (TryHackMe, CTFd, local containers)
- Enhanced prompt caching for cost optimization and context engineering for long running workflows
- Give agent tools