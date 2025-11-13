# Quickstart Guide

Get your agentic system running in under 5 minutes with the interactive installer.

## Prerequisites

Choose **ONE** of the following:

- **Docker Desktop** (Recommended) - [Download here](https://www.docker.com/products/docker-desktop/)
- **Python 3.12+** - [Download here](https://www.python.org/downloads/)

Plus, choose your LLM provider:

- **Google Gemini** (Easiest) - Free tier: 1500 requests/day - [Get API key](https://makersuite.google.com/app/apikey)
- **LM Studio** (Offline) - Zero cost, runs locally - [Download here](https://lmstudio.ai)

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/shanevcantwell/langgraph-agentic-scaffold.git
cd langgraph-agentic-scaffold
```

---

## Step 2: Run the Interactive Installer

The installer will:
- ✅ Detect your environment (Docker/Python)
- ✅ Ask which LLM provider you want to use
- ✅ Configure all files automatically
- ✅ Start the system and verify it's working

### Linux / macOS

```bash
./scripts/setup.sh
```

### Windows (PowerShell)

```powershell
.\scripts\setup.ps1
```

> **Note**: If you get a "script not allowed" error on Windows, run:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

---

## Step 3: Access Your System

Once setup completes, access your agentic system:

- **Web UI**: http://localhost:5003
- **API Docs**: http://localhost:8000/docs

### Try Your First Query

Open the Web UI and try:

> "Hello! Can you help me understand what this system can do?"

The system will route your question to the appropriate specialist and respond.

---

## What Just Happened?

The installer configured three files for you:

1. **`.env`** - Your API keys and environment settings
2. **`user_settings.yaml`** - Model assignments to specialists
3. **`config.yaml`** - System architecture (already configured)

You can edit these files later to customize behavior.

---

## Next Steps

### Learn the System

- **[Developer's Guide](./docs/DEVELOPERS_GUIDE.md)** - Complete architecture overview
- **[Creating a Specialist](./docs/CREATING_A_NEW_SPECIALIST.md)** - Add custom specialists
- **[Integration Tests](./docs/INTEGRATION_TEST_GUIDE.md)** - Write tests for your specialists

### Enable Observability (Recommended)

LangSmith provides visual tracing of your agent workflows:

1. Sign up at https://smith.langchain.com
2. Get your API key
3. Edit `.env` and uncomment the LangSmith section:
   ```bash
   LANGCHAIN_TRACING_V2="true"
   LANGCHAIN_API_KEY="ls__your_api_key_here"
   LANGCHAIN_PROJECT="langgraph-agentic-scaffold"
   ```
4. Restart: `docker compose restart app` (or restart your server)

Now you'll see beautiful traces in the LangSmith UI showing exactly what your agents are doing.

### Explore Features

Your alpha installation includes these production-ready features:

- ✅ **Tiered Chat** - Multi-perspective responses with parallel execution
- ✅ **File Operations** - Safe sandbox for file read/write/list
- ✅ **MCP Protocol** - Direct specialist-to-specialist communication
- ✅ **Graceful Degradation** - System continues working when components fail

### Customize Your System

Edit `user_settings.yaml` to:
- Change which models power which specialists
- Switch between cloud and local models
- Adjust the default model for all specialists

Edit `config.yaml` to:
- Enable/disable specific specialists
- Configure timeouts and behavior
- Add new specialists (see Creating a Specialist guide)

---

## Troubleshooting

### Docker: Services won't start

```bash
# Check logs for errors
docker compose logs -f app

# Common fixes:
docker compose down
docker compose up --build -d
```

### Docker: Can't connect to LM Studio

If using LM Studio with Docker, the installer automatically converts `localhost` to `host.docker.internal`.

Verify in `.env`:
```bash
LMSTUDIO_BASE_URL="http://host.docker.internal:1234/v1"
```

### Python: Import errors

```bash
# Activate virtual environment first
source ./.venv_agents/bin/activate  # Linux/Mac
.\.venv_agents_windows\Scripts\Activate.ps1  # Windows

# Then reinstall
pip install -e '.[dev]'
```

### LM Studio: Model not responding

1. Ensure LM Studio server is running (look for green "Server Running" indicator)
2. Check that a model is loaded (you should see it in the server panel)
3. Test the connection:
   ```bash
   curl http://localhost:1234/v1/models
   ```

### Gemini: API key not working

1. Verify your API key at https://makersuite.google.com/app/apikey
2. Check `.env` has the key without extra spaces:
   ```bash
   GOOGLE_API_KEY="your-key-here"
   ```
3. Restart: `docker compose restart app`

---

## Stopping the System

### Docker
```bash
docker compose down
```

### Local Python
Press `Ctrl+C` in the terminal running the server, then deactivate:
```bash
deactivate
```

---

## Getting Help

- **Documentation**: See `./docs/` directory
- **Issues**: https://github.com/shanevcantwell/langgraph-agentic-scaffold/issues
- **Discussions**: https://github.com/shanevcantwell/langgraph-agentic-scaffold/discussions

---

## What's Next?

Now that you have a working system, try:

1. **Run the test suite** to verify everything works:
   ```bash
   docker compose exec app python -m pytest app/tests/ -v
   ```

2. **Create your first specialist** following the [specialist creation guide](./docs/CREATING_A_NEW_SPECIALIST.md)

3. **Explore the architecture** in the [Developer's Guide](./docs/DEVELOPERS_GUIDE.md)

4. **Join the community** and share what you're building!

---

**Happy building! 🚀**
