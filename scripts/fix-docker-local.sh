#!/bin/bash
# fix-docker-local.sh
# Fixes Docker credential helper issues for local/offline operation
#
# Problem: Docker Desktop for Windows sets credsStore to "desktop.exe" which
# fails in WSL2 when Docker Desktop isn't running or credentials aren't needed.
#
# Solution: Remove the credential store config so Docker works with local/public images.

set -e

DOCKER_CONFIG="$HOME/.docker/config.json"

echo "=== Docker Local Mode Fix ==="

# Check if config exists
if [ ! -f "$DOCKER_CONFIG" ]; then
    echo "No Docker config found. Creating empty config."
    mkdir -p "$HOME/.docker"
    echo '{}' > "$DOCKER_CONFIG"
    echo "Done."
    exit 0
fi

# Check for problematic credsStore
if grep -q '"credsStore"' "$DOCKER_CONFIG" 2>/dev/null; then
    echo "Found credential store config:"
    grep '"credsStore"' "$DOCKER_CONFIG"
    echo ""

    # Backup existing config
    cp "$DOCKER_CONFIG" "$DOCKER_CONFIG.backup"
    echo "Backed up to: $DOCKER_CONFIG.backup"

    # Remove credsStore (keep other settings if any)
    # Use Python for reliable JSON manipulation
    python3 << 'PYEOF'
import json
import os

config_path = os.path.expanduser("~/.docker/config.json")
with open(config_path, 'r') as f:
    config = json.load(f)

# Remove problematic keys
config.pop('credsStore', None)
config.pop('credHelpers', None)

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')

print("Removed credential store configuration.")
PYEOF

    echo ""
    echo "New config:"
    cat "$DOCKER_CONFIG"
else
    echo "No credential store config found. Docker is already in local mode."
fi

echo ""
echo "=== Done ==="
echo "Docker is now configured for local/offline operation."
echo "Run 'docker compose build' to verify."
