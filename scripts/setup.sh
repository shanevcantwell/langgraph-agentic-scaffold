#!/bin/bash
# Interactive installer for langgraph-agentic-scaffold
# Reduces setup from 30+ minutes to under 5 minutes
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/.."
cd "$PROJECT_ROOT"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  LangGraph Agentic Scaffold - Interactive Setup           ║${NC}"
echo -e "${BLUE}║  Version: 0.2.0                                           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================================
# STEP 1: Environment Detection
# ============================================================================
echo -e "${BLUE}[1/6] Detecting your environment...${NC}"

# Check Docker
if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
    DOCKER_AVAILABLE=true
    echo -e "${GREEN}✓${NC} Docker detected"
else
    DOCKER_AVAILABLE=false
    echo -e "${YELLOW}⚠${NC} Docker not found (will use local Python)"
fi

# Check for surf-mcp sibling repo (browser automation)
SURF_MCP_DIR="$PROJECT_ROOT/../surf-mcp"
if [ -d "$SURF_MCP_DIR" ]; then
    SURF_MCP_AVAILABLE=true
    echo -e "${GREEN}✓${NC} surf-mcp detected at $SURF_MCP_DIR"
else
    SURF_MCP_AVAILABLE=false
    echo -e "${YELLOW}⚠${NC} surf-mcp not found (optional: browser automation)"
fi

# Check Python version
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

    if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 12 ]; then
        PYTHON_OK=true
        echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION detected"
    else
        PYTHON_OK=false
        echo -e "${RED}✗${NC} Python 3.12+ required (found $PYTHON_VERSION)"
    fi
else
    PYTHON_OK=false
    echo -e "${RED}✗${NC} Python 3 not found"
fi

echo ""

# ============================================================================
# STEP 2: Installation Mode Selection
# ============================================================================
echo -e "${BLUE}[2/6] Choose installation mode:${NC}"
echo ""

if [ "$DOCKER_AVAILABLE" = true ]; then
    echo "1) Docker (Recommended)"
    echo "   - Isolated, sandboxed environment"
    echo "   - No Python version conflicts"
    echo "   - Includes proxy for network security"
    echo ""
fi

if [ "$PYTHON_OK" = true ]; then
    echo "2) Local Python Virtual Environment"
    echo "   - Direct access to code for development"
    echo "   - Faster iteration during development"
    echo "   - Requires Python 3.12+"
    echo ""
fi

if [ "$DOCKER_AVAILABLE" = false ] && [ "$PYTHON_OK" = false ]; then
    echo -e "${RED}ERROR: Neither Docker nor Python 3.12+ found.${NC}"
    echo "Please install Docker Desktop or Python 3.12+ and try again."
    exit 1
fi

read -p "Enter choice (1 or 2): " INSTALL_MODE

# ============================================================================
# STEP 2.5: Optional surf-mcp Setup
# ============================================================================
if [ "$SURF_MCP_AVAILABLE" = false ]; then
    echo ""
    echo -e "${BLUE}[Optional] surf-mcp Setup${NC}"
    echo ""
    echo "surf-mcp provides browser automation via visual grounding (Fara-7B)."
    echo "This enables specialists to:"
    echo "  - Navigate web pages using natural language"
    echo "  - Click buttons, fill forms without CSS selectors"
    echo ""
    echo "Note: surf-mcp is browser-only. For filesystem, use FileSpecialist."
    echo ""
    read -p "Clone surf-mcp? (y/N): " CLONE_SURF_MCP

    if [[ "$CLONE_SURF_MCP" =~ ^[Yy]$ ]]; then
        echo "Cloning surf-mcp..."
        git clone https://github.com/shanevcantwell/surf-mcp.git "$SURF_MCP_DIR"
        if [ $? -eq 0 ]; then
            SURF_MCP_AVAILABLE=true
            echo -e "${GREEN}✓${NC} surf-mcp cloned to $SURF_MCP_DIR"
        else
            echo -e "${RED}✗${NC} Failed to clone surf-mcp (continuing without it)"
        fi
    else
        echo "Skipping surf-mcp (you can add it later)"
    fi
fi

# ============================================================================
# STEP 3: LLM Provider Selection
# ============================================================================
echo ""
echo -e "${BLUE}[3/6] Choose your LLM provider:${NC}"
echo ""
echo "1) Google Gemini (Recommended to start)"
echo "   - Fastest setup (just need API key)"
echo "   - Generous free tier (1500 requests/day)"
echo "   - Get API key: https://makersuite.google.com/app/apikey"
echo ""
echo "2) Local Inference (LM Studio / llama-server / vLLM)"
echo "   - Zero API costs, runs offline"
echo "   - Any OpenAI-compatible server works"
echo "   - Requires a running server + loaded model"
echo ""
echo "3) Hybrid (Gemini + Local)"
echo "   - Best of both worlds"
echo "   - Requires both setups above"
echo ""

read -p "Enter choice (1, 2, or 3): " PROVIDER_CHOICE

# ============================================================================
# STEP 4: Gather Configuration Details
# ============================================================================
echo ""
echo -e "${BLUE}[4/6] Configuration setup...${NC}"

# Initialize config variables
GOOGLE_API_KEY=""
LOCAL_INFERENCE_URL=""
DEFAULT_PROVIDER=""
ROUTER_PROVIDER=""

case $PROVIDER_CHOICE in
    1)
        echo ""
        echo "Enter your Google API key (from https://makersuite.google.com/app/apikey):"
        read -p "> " GOOGLE_API_KEY
        DEFAULT_PROVIDER="gemini_flash"
        ROUTER_PROVIDER="gemini_flash"
        ;;
    2)
        echo ""
        echo "Local Inference Setup:"
        echo "Start your server (LM Studio, llama-server, vLLM, etc.) and load a model."
        echo "The default URL is http://localhost:1234/v1 (LM Studio's default)."
        echo ""
        read -p "Enter server base URL [http://localhost:1234/v1]: " LOCAL_INPUT
        LOCAL_INFERENCE_URL=${LOCAL_INPUT:-"http://localhost:1234/v1"}

        # If using Docker, convert localhost to host.docker.internal
        if [ "$INSTALL_MODE" = "1" ]; then
            LOCAL_INFERENCE_URL=$(echo $LOCAL_INFERENCE_URL | sed 's/localhost/host.docker.internal/')
            echo -e "${YELLOW}Note:${NC} Docker mode detected. Using $LOCAL_INFERENCE_URL"
        fi

        DEFAULT_PROVIDER="lmstudio_specialist"
        ROUTER_PROVIDER="lmstudio_router"
        ;;
    3)
        echo ""
        echo "Enter your Google API key:"
        read -p "> " GOOGLE_API_KEY
        echo ""
        read -p "Enter local server base URL [http://localhost:1234/v1]: " LOCAL_INPUT
        LOCAL_INFERENCE_URL=${LOCAL_INPUT:-"http://localhost:1234/v1"}

        if [ "$INSTALL_MODE" = "1" ]; then
            LOCAL_INFERENCE_URL=$(echo $LOCAL_INFERENCE_URL | sed 's/localhost/host.docker.internal/')
        fi

        DEFAULT_PROVIDER="gemini_flash"
        ROUTER_PROVIDER="gemini_flash"
        ;;
esac

# ============================================================================
# STEP 5: Create Configuration Files
# ============================================================================
echo ""
echo -e "${BLUE}[5/6] Generating configuration files...${NC}"

# Copy example files if they don't exist
[ ! -f config.yaml ] && cp config.yaml.example config.yaml && echo -e "${GREEN}✓${NC} Created config.yaml"
[ ! -f proxy/squid.conf ] && cp proxy/squid.conf.example proxy/squid.conf && echo -e "${GREEN}✓${NC} Created proxy/squid.conf"

# Create .env file
cat > .env << EOF
# Auto-generated by setup.sh on $(date)
# You can edit this file to customize your environment

# ===================================================================
#  System Configuration
# ===================================================================
WORKSPACE_PATH=workspace

# ===================================================================
#  LLM Provider Configuration
# ===================================================================

EOF

if [ -n "$GOOGLE_API_KEY" ]; then
    cat >> .env << EOF
# Google Gemini
GOOGLE_API_KEY="$GOOGLE_API_KEY"

EOF
fi

if [ -n "$LOCAL_INFERENCE_URL" ]; then
    cat >> .env << EOF
# Local Inference Server (LM Studio, llama-server, vLLM, etc.)
LOCAL_INFERENCE_BASE_URL="$LOCAL_INFERENCE_URL"
# LOCAL_INFERENCE_TIMEOUT=180

# Distributed inference (multiple GPUs/machines):
# LOCAL_INFERENCE_SERVERS="rtx3090=http://192.168.1.100:1234/v1,rtx8000=http://192.168.1.101:8081/v1"

EOF
fi

cat >> .env << EOF
# ===================================================================
#  Observability (Optional but Recommended)
# ===================================================================
# LangSmith provides visual tracing of agent workflows
# Sign up at https://smith.langchain.com
# LANGCHAIN_TRACING_V2="true"
# LANGCHAIN_API_KEY="ls__your_api_key_here"
# LANGCHAIN_PROJECT="langgraph-agentic-scaffold"

EOF

echo -e "${GREEN}✓${NC} Created .env"

# Create user_settings.yaml with smart defaults
cat > user_settings.yaml << EOF
# Auto-generated by setup.sh on $(date)
# You can edit this file to customize model assignments
# See user_settings.yaml.example for all options

architecture: "default"
max_image_size_mb: 10

llm_providers:
EOF

if [ -n "$GOOGLE_API_KEY" ]; then
    cat >> user_settings.yaml << EOF
  gemini_flash:
    type: "gemini"
    api_identifier: "gemini-2.5-flash"
  gemini_pro:
    type: "gemini"
    api_identifier: "gemini-2.5-pro"
EOF
fi

if [ -n "$LOCAL_INFERENCE_URL" ]; then
    cat >> user_settings.yaml << EOF
  # type: "lmstudio" works for LM Studio and most local servers.
  # Use type: "local" for llama-server/vLLM, "local_pool" for multi-GPU.
  lmstudio_router:
    type: "lmstudio"
    api_identifier: "local-model"
  lmstudio_specialist:
    type: "lmstudio"
    api_identifier: "local-model"
EOF
fi

cat >> user_settings.yaml << EOF

specialist_model_bindings:
  router_specialist: "$ROUTER_PROVIDER"
  prompt_triage_specialist: "$ROUTER_PROVIDER"
  triage_architect: "$ROUTER_PROVIDER"
  default_responder_specialist: "$ROUTER_PROVIDER"
  chat_specialist: "$DEFAULT_PROVIDER"
  systems_architect: "$DEFAULT_PROVIDER"
  prompt_specialist: "$DEFAULT_PROVIDER"
  exit_interview_specialist: "$DEFAULT_PROVIDER"
  summarizer_specialist: "$DEFAULT_PROVIDER"

  # Tiered chat subgraph (parallel execution)
  progenitor_alpha_specialist: "$DEFAULT_PROVIDER"
  progenitor_bravo_specialist: "$DEFAULT_PROVIDER"

default_llm_config: "$DEFAULT_PROVIDER"

# UI module (default: gradio_app)
ui_module: "gradio_app"

# Checkpointing (required for human-in-the-loop)
checkpointing:
  enabled: false
  backend: "sqlite"
  sqlite_path: "./data/checkpoints.db"
EOF

echo -e "${GREEN}✓${NC} Created user_settings.yaml"

# ============================================================================
# STEP 6: Install and Start
# ============================================================================
echo ""
echo -e "${BLUE}[6/6] Installing and starting...${NC}"

if [ "$INSTALL_MODE" = "1" ]; then
    # Docker installation
    echo "Building Docker containers (this may take a few minutes)..."
    docker compose build --quiet
    echo -e "${GREEN}✓${NC} Docker build complete"

    # Build surf-mcp if available
    if [ "$SURF_MCP_AVAILABLE" = true ]; then
        echo "Building surf-mcp container..."
        docker compose -f "$SURF_MCP_DIR/docker-compose.yml" build --quiet
        echo -e "${GREEN}✓${NC} surf-mcp build complete"
    fi

    echo "Starting services..."
    docker compose up -d
    if [ "$SURF_MCP_AVAILABLE" = true ]; then
        docker compose -f "$SURF_MCP_DIR/docker-compose.yml" up -d
    fi
    echo -e "${GREEN}✓${NC} Services started"

    # Wait for services to be ready
    echo "Waiting for services to initialize..."
    sleep 5

    # Check if services are running
    if docker compose ps | grep -q "running"; then
        echo -e "${GREEN}✓${NC} All services healthy"
    else
        echo -e "${YELLOW}⚠${NC} Services may still be starting..."
    fi

else
    # Local Python installation
    echo "Creating Python virtual environment..."
    python3 -m venv .venv_agents
    source ./.venv_agents/bin/activate
    echo -e "${GREEN}✓${NC} Virtual environment created"

    echo "Installing Python dependencies..."
    pip install -q -e '.[dev]'
    echo -e "${GREEN}✓${NC} Dependencies installed"
fi

# ============================================================================
# Success Message
# ============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Setup Complete! Your agentic system is ready.            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo ""

if [ "$INSTALL_MODE" = "1" ]; then
    echo "Access your system:"
    echo "  - Web UI (VEGAS):  http://localhost:3000"
    echo "  - Gradio UI:       http://localhost:5003"
    echo "  - API Docs:        http://localhost:8000/docs"
    echo ""
    echo "Useful commands:"
    echo "  - View logs:     docker compose logs -f app"
    echo "  - Stop system:   docker compose down"
    echo "  - Restart:       docker compose restart app"
    echo ""
else
    echo "Activate the virtual environment:"
    echo "  source ./.venv_agents/bin/activate"
    echo ""
    echo "Start the services:"
    echo "  ./scripts/server.sh start"
    echo "  python -m app.src.ui --port 5003"
    echo ""
fi

echo "Documentation:"
echo "  - Developer's Guide:  ./docs/DEVELOPERS_GUIDE.md"
echo "  - Configuration:      ./docs/CONFIGURATION_GUIDE.md"
echo ""

if [ -n "$GOOGLE_API_KEY" ]; then
    echo -e "${YELLOW}Note:${NC} Using Gemini Flash (1500 free requests/day)"
fi

if [ -n "$LOCAL_INFERENCE_URL" ]; then
    echo -e "${YELLOW}Note:${NC} Ensure your local inference server is running at $LOCAL_INFERENCE_URL"
fi

if [ "$SURF_MCP_AVAILABLE" = true ]; then
    echo -e "${GREEN}Note:${NC} surf-mcp is available for browser automation"
    echo "  Docs: $SURF_MCP_DIR/README.md"
fi

echo ""
echo "Happy building!"
