# Fully Autonomous AI-Driven Penetration Testing Framework

AI agent that finds and exploits vulnerabilities to solve CTF challenges.

- Autonomous reconnaissance and exploitation
- HackTheBox VPN support
- Real-time cost & token tracking
- Logs each session with timestamps, commands, context, and results

## Requirements
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

Create a file named `.env` in the project root.
Get an API key from [OpenRouter](https://openrouter.ai/) and add it to your `.env` file.
Add:
```bash
# Required: OpenRouter API credentials
OPENROUTER_API_KEY=sk-or-v1-your-api-key-here

# Required: Model selection
OPENROUTER_MODEL=openai/gpt-5
```

### 6. Install Docker Desktop

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) for your platform.

### 7. Build the Docker Container

Navigate to project folder. The container is based on Kali Linux and includes all penetration testing tools:

```bash
# Build the container (takes 5-15 minutes first time)
docker compose build

# Start the container in detached mode
docker compose up -d
```
### Docker Container Management

```bash
# Check containers
docker ps
# Access the Kali container directly
docker compose exec kali bash

# Stop the container
docker compose down

# Rebuild after Dockerfile changes
docker compose build --no-cache

# View container logs
docker compose logs kali
```

## Getting Started

1. Download your `.ovpn` VPN config from HackTheBox Labs to `ctf-workspace/`
2. Run `python main.py` and wait for VPN connection to establish
3. Start a machine (e.g., from Starting Point) and copy its IP address


Enter target IP address when prompted:
```
🎯 Target IP: <enter-target-ip>
```

Optional: Add custom instructions to LLM (e.g., "run a quick scan to start with" or "this challenge has two flags, find both flags before stopping")

The agent will:
   - Connect to HackTheBox VPN automatically
   - Begin reconnaissance (nmap scans)
   - Enumerate services
   - Exploit vulnerabilities
   - Extract flags to `./ctf-workspace/flags.txt`

The `ctf-workspace` folder is shared between your machine and the Docker container.

## Contributing

Contributions welcome! Areas for improvement:

### TODO
- Multi-agent workflow (separate agents for orchestration, validation, sandbox)
- Benchmark harness feature for running large scale experiments on multiple boxes and ctfs.
- Additional CTF platform integrations (TryHackMe, CTFd, local containers)
- Enhanced prompt caching for cost optimization and context engineering for long running workflows
- Bootstrap functionality for restarting at token treshold, context crunch auto-compact function.
- Give agent tools
- Run agent on local vulnerable containers.