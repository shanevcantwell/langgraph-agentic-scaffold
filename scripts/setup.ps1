# Interactive installer for langgraph-agentic-scaffold (Windows PowerShell)
# Reduces setup from 30+ minutes to under 5 minutes

$ErrorActionPreference = "Stop"

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "║  LangGraph Agentic Scaffold - Interactive Setup           ║" -ForegroundColor Blue
Write-Host "║  Version: 0.1.0-alpha (Windows)                           ║" -ForegroundColor Blue
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""

# ============================================================================
# STEP 1: Environment Detection
# ============================================================================
Write-Host "[1/6] Detecting your environment..." -ForegroundColor Blue

# Check Docker
$DockerAvailable = $false
try {
    $null = docker --version 2>$null
    $null = docker-compose --version 2>$null
    $DockerAvailable = $true
    Write-Host "✓ Docker detected" -ForegroundColor Green
} catch {
    Write-Host "⚠ Docker not found (will use local Python)" -ForegroundColor Yellow
}

# Check Python version
$PythonOk = $false
try {
    $PythonVersion = (python --version 2>&1) -replace 'Python ', ''
    $VersionParts = $PythonVersion.Split('.')
    $Major = [int]$VersionParts[0]
    $Minor = [int]$VersionParts[1]

    if ($Major -ge 3 -and $Minor -ge 12) {
        $PythonOk = $true
        Write-Host "✓ Python $PythonVersion detected" -ForegroundColor Green
    } else {
        Write-Host "✗ Python 3.12+ required (found $PythonVersion)" -ForegroundColor Red
    }
} catch {
    Write-Host "✗ Python 3 not found" -ForegroundColor Red
}

Write-Host ""

# ============================================================================
# STEP 2: Installation Mode Selection
# ============================================================================
Write-Host "[2/6] Choose installation mode:" -ForegroundColor Blue
Write-Host ""

$ValidChoices = @()
if ($DockerAvailable) {
    Write-Host "1) Docker (Recommended)"
    Write-Host "   - Isolated, sandboxed environment"
    Write-Host "   - No Python version conflicts"
    Write-Host "   - Includes proxy for network security"
    Write-Host ""
    $ValidChoices += "1"
}

if ($PythonOk) {
    Write-Host "2) Local Python Virtual Environment"
    Write-Host "   - Direct access to code for development"
    Write-Host "   - Faster iteration during development"
    Write-Host "   - Requires Python 3.12+"
    Write-Host ""
    $ValidChoices += "2"
}

if (-not $DockerAvailable -and -not $PythonOk) {
    Write-Host "ERROR: Neither Docker nor Python 3.12+ found." -ForegroundColor Red
    Write-Host "Please install Docker Desktop or Python 3.12+ and try again."
    exit 1
}

$InstallMode = Read-Host "Enter choice ($($ValidChoices -join ' or '))"

# ============================================================================
# STEP 3: LLM Provider Selection
# ============================================================================
Write-Host ""
Write-Host "[3/6] Choose your LLM provider:" -ForegroundColor Blue
Write-Host ""
Write-Host "1) Google Gemini (Recommended for Alpha)"
Write-Host "   - Fastest setup (just need API key)"
Write-Host "   - Generous free tier (1500 requests/day)"
Write-Host "   - Tested extensively with this scaffold"
Write-Host "   - Get API key: https://makersuite.google.com/app/apikey"
Write-Host ""
Write-Host "2) LM Studio (Local/Offline)"
Write-Host "   - Zero API costs"
Write-Host "   - Runs completely offline"
Write-Host "   - Requires: LM Studio + downloaded model (~4-8GB)"
Write-Host "   - Download: https://lmstudio.ai"
Write-Host ""
Write-Host "3) Hybrid (Gemini + LM Studio)"
Write-Host "   - Best of both worlds"
Write-Host "   - Requires both setups above"
Write-Host ""

$ProviderChoice = Read-Host "Enter choice (1, 2, or 3)"

# ============================================================================
# STEP 4: Gather Configuration Details
# ============================================================================
Write-Host ""
Write-Host "[4/6] Configuration setup..." -ForegroundColor Blue

$GoogleApiKey = ""
$LmStudioBaseUrl = ""
$DefaultProvider = ""
$RouterProvider = ""

switch ($ProviderChoice) {
    "1" {
        Write-Host ""
        $GoogleApiKey = Read-Host "Enter your Google API key (from https://makersuite.google.com/app/apikey)"
        $DefaultProvider = "gemini_flash"
        $RouterProvider = "gemini_flash"
    }
    "2" {
        Write-Host ""
        Write-Host "LM Studio Setup:"
        Write-Host "1. Download and install LM Studio from https://lmstudio.ai"
        Write-Host "2. Download a model (recommended: Llama 3 8B Instruct)"
        Write-Host "3. Start the local server (look for 'Start Server' button)"
        Write-Host "4. Note the server URL (usually http://localhost:1234/v1)"
        Write-Host ""
        $LmStudioInput = Read-Host "Enter LM Studio base URL [http://localhost:1234/v1]"
        $LmStudioBaseUrl = if ($LmStudioInput) { $LmStudioInput } else { "http://localhost:1234/v1" }

        if ($InstallMode -eq "1") {
            $LmStudioBaseUrl = $LmStudioBaseUrl -replace "localhost", "host.docker.internal"
            Write-Host "Note: Docker mode detected. Using $LmStudioBaseUrl" -ForegroundColor Yellow
        }

        $DefaultProvider = "lmstudio_specialist"
        $RouterProvider = "lmstudio_router"
    }
    "3" {
        Write-Host ""
        $GoogleApiKey = Read-Host "Enter your Google API key"
        Write-Host ""
        $LmStudioInput = Read-Host "Enter LM Studio base URL [http://localhost:1234/v1]"
        $LmStudioBaseUrl = if ($LmStudioInput) { $LmStudioInput } else { "http://localhost:1234/v1" }

        if ($InstallMode -eq "1") {
            $LmStudioBaseUrl = $LmStudioBaseUrl -replace "localhost", "host.docker.internal"
        }

        $DefaultProvider = "gemini_flash"
        $RouterProvider = "gemini_flash"
    }
}

# ============================================================================
# STEP 5: Create Configuration Files
# ============================================================================
Write-Host ""
Write-Host "[5/6] Generating configuration files..." -ForegroundColor Blue

# Copy example files
if (-not (Test-Path "config.yaml")) {
    Copy-Item "config.yaml.example" "config.yaml"
    Write-Host "✓ Created config.yaml" -ForegroundColor Green
}

if (-not (Test-Path "proxy\squid.conf")) {
    Copy-Item "proxy\squid.conf.example" "proxy\squid.conf"
    Write-Host "✓ Created proxy\squid.conf" -ForegroundColor Green
}

# Create .env
$EnvContent = @"
# Auto-generated by setup.ps1 on $(Get-Date)
# You can edit this file to customize your environment

# ===================================================================
#  System Configuration
# ===================================================================
WORKSPACE_PATH=workspace

# ===================================================================
#  LLM Provider Configuration
# ===================================================================

"@

if ($GoogleApiKey) {
    $EnvContent += @"
# Google Gemini
GOOGLE_API_KEY="$GoogleApiKey"

"@
}

if ($LmStudioBaseUrl) {
    $EnvContent += @"
# LM Studio (Local)
LMSTUDIO_BASE_URL="$LmStudioBaseUrl"
# LMSTUDIO_TIMEOUT=180

"@
}

$EnvContent += @"
# ===================================================================
#  Observability (Optional but Recommended)
# ===================================================================
# LangSmith provides visual tracing of agent workflows
# Sign up at https://smith.langchain.com
# LANGCHAIN_TRACING_V2="true"
# LANGCHAIN_API_KEY="ls__your_api_key_here"
# LANGCHAIN_PROJECT="langgraph-agentic-scaffold"

"@

$EnvContent | Out-File -FilePath ".env" -Encoding UTF8
Write-Host "✓ Created .env" -ForegroundColor Green

# Create user_settings.yaml
$UserSettingsContent = @"
# Auto-generated by setup.ps1 on $(Get-Date)
# You can edit this file to customize model assignments

llm_providers:
"@

if ($GoogleApiKey) {
    $UserSettingsContent += @"
  gemini_flash:
    type: "gemini"
    api_identifier: "gemini-2.5-flash"
  gemini_pro:
    type: "gemini"
    api_identifier: "gemini-2.5-pro"
"@
}

if ($LmStudioBaseUrl) {
    $UserSettingsContent += @"
  lmstudio_router:
    type: "lmstudio"
    api_identifier: "local-model"
  lmstudio_specialist:
    type: "lmstudio"
    api_identifier: "local-model"
"@
}

$UserSettingsContent += @"

specialist_model_bindings:
  router_specialist: "$RouterProvider"
  prompt_triage_specialist: "$DefaultProvider"
  chat_specialist: "$DefaultProvider"
  systems_architect: "$DefaultProvider"
  prompt_specialist: "$DefaultProvider"
  open_interpreter_specialist: "$DefaultProvider"
  end_specialist: "$DefaultProvider"

  # Tiered chat subgraph (parallel execution)
  progenitor_alpha_specialist: "$DefaultProvider"
  progenitor_bravo_specialist: "$DefaultProvider"

default_llm_config: "$DefaultProvider"

# UI module (default: gradio_app)
ui_module: "gradio_app"
"@

$UserSettingsContent | Out-File -FilePath "user_settings.yaml" -Encoding UTF8
Write-Host "✓ Created user_settings.yaml" -ForegroundColor Green

# ============================================================================
# STEP 6: Install and Start
# ============================================================================
Write-Host ""
Write-Host "[6/6] Installing and starting..." -ForegroundColor Blue

if ($InstallMode -eq "1") {
    Write-Host "Building Docker containers (this may take a few minutes)..."
    docker compose build --quiet
    Write-Host "✓ Docker build complete" -ForegroundColor Green

    Write-Host "Starting services..."
    docker compose up -d
    Write-Host "✓ Services started" -ForegroundColor Green

    Write-Host "Waiting for services to initialize..."
    Start-Sleep -Seconds 5

    $Running = docker compose ps | Select-String "running"
    if ($Running) {
        Write-Host "✓ All services healthy" -ForegroundColor Green
    } else {
        Write-Host "⚠ Services may still be starting..." -ForegroundColor Yellow
    }
} else {
    Write-Host "Creating Python virtual environment..."
    python -m venv .venv_agents_windows
    Write-Host "✓ Virtual environment created" -ForegroundColor Green

    Write-Host "Installing Python dependencies..."
    & ".\.venv_agents_windows\Scripts\Activate.ps1"
    pip install -q -e ".[dev]"
    Write-Host "✓ Dependencies installed" -ForegroundColor Green
}

# ============================================================================
# Success Message
# ============================================================================
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║  ✓ Setup Complete! Your agentic system is ready.          ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Blue
Write-Host ""

if ($InstallMode -eq "1") {
    Write-Host "Access your system:"
    Write-Host "  • Web UI:  http://localhost:5003"
    Write-Host "  • API:     http://localhost:8000/docs"
    Write-Host ""
    Write-Host "Useful commands:"
    Write-Host "  • View logs:     docker compose logs -f app"
    Write-Host "  • Stop system:   docker compose down"
    Write-Host "  • Restart:       docker compose restart app"
    Write-Host ""
} else {
    Write-Host "Activate the virtual environment:"
    Write-Host "  .\.venv_agents_windows\Scripts\Activate.ps1"
    Write-Host ""
    Write-Host "Start the services:"
    Write-Host "  .\scripts\server.bat start"
    Write-Host "  python -m app.src.ui --port 5003"
    Write-Host ""
}

Write-Host "Documentation:"
Write-Host "  • Developer's Guide:  .\docs\DEVELOPERS_GUIDE.md"
Write-Host "  • Create Specialist:  .\docs\CREATING_A_NEW_SPECIALIST.md"
Write-Host ""

if ($GoogleApiKey) {
    Write-Host "Note: Using Gemini Flash (1500 free requests/day)" -ForegroundColor Yellow
}

if ($LmStudioBaseUrl) {
    Write-Host "Note: Ensure LM Studio server is running at $LmStudioBaseUrl" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Happy building! 🚀"
