#!/bin/bash
# docker-offline.sh
# Export/import Docker images for true offline operation
#
# Usage:
#   ./docker-offline.sh export   # Save all images to .docker-images/
#   ./docker-offline.sh import   # Load images from .docker-images/
#   ./docker-offline.sh status   # Check what's cached vs available

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."
IMAGE_DIR="$PROJECT_ROOT/.docker-images"

# Base images required (these are the external dependencies)
BASE_IMAGES=(
    "python:3.12-slim"
    "debian:bookworm-slim"
    "node:18-alpine"
)

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

export_images() {
    echo "=== Exporting Docker Images for Offline Use ==="
    mkdir -p "$IMAGE_DIR"

    # First, ensure all images are pulled/built
    echo "Pulling base images..."
    for img in "${BASE_IMAGES[@]}"; do
        echo -n "  $img... "
        if docker pull "$img" > /dev/null 2>&1; then
            echo -e "${GREEN}OK${NC}"
        else
            echo -e "${RED}FAILED${NC}"
        fi
    done

    echo ""
    echo "Building project images..."
    cd "$PROJECT_ROOT"
    docker compose build --quiet
    echo -e "${GREEN}Build complete${NC}"

    echo ""
    echo "Exporting images to $IMAGE_DIR..."

    # Export base images
    for img in "${BASE_IMAGES[@]}"; do
        filename=$(echo "$img" | tr ':/' '_').tar
        echo -n "  $img -> $filename... "
        docker save "$img" -o "$IMAGE_DIR/$filename"
        echo -e "${GREEN}OK${NC} ($(du -h "$IMAGE_DIR/$filename" | cut -f1))"
    done

    # Export built project images
    PROJECT_IMAGES=$(docker compose config --images 2>/dev/null)
    for img in $PROJECT_IMAGES; do
        filename=$(echo "$img" | tr ':/' '_').tar
        echo -n "  $img -> $filename... "
        docker save "$img" -o "$IMAGE_DIR/$filename"
        echo -e "${GREEN}OK${NC} ($(du -h "$IMAGE_DIR/$filename" | cut -f1))"
    done

    echo ""
    echo "=== Export Complete ==="
    echo "Total size: $(du -sh "$IMAGE_DIR" | cut -f1)"
    echo ""
    echo "To use on offline machine:"
    echo "  1. Copy .docker-images/ folder to target machine"
    echo "  2. Run: ./scripts/docker-offline.sh import"
}

import_images() {
    echo "=== Importing Docker Images from Offline Cache ==="

    if [ ! -d "$IMAGE_DIR" ]; then
        echo -e "${RED}ERROR: $IMAGE_DIR not found${NC}"
        echo "Run './scripts/docker-offline.sh export' first on a connected machine."
        exit 1
    fi

    for tarfile in "$IMAGE_DIR"/*.tar; do
        if [ -f "$tarfile" ]; then
            filename=$(basename "$tarfile")
            echo -n "  Loading $filename... "
            if docker load -i "$tarfile" > /dev/null 2>&1; then
                echo -e "${GREEN}OK${NC}"
            else
                echo -e "${RED}FAILED${NC}"
            fi
        fi
    done

    echo ""
    echo "=== Import Complete ==="
    echo "You can now run: docker compose up -d"
}

status() {
    echo "=== Docker Offline Status ==="
    echo ""

    echo "Base images (external dependencies):"
    for img in "${BASE_IMAGES[@]}"; do
        if docker image inspect "$img" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $img (cached)"
        else
            echo -e "  ${RED}✗${NC} $img (not cached)"
        fi
    done

    echo ""
    echo "Offline image cache ($IMAGE_DIR):"
    if [ -d "$IMAGE_DIR" ]; then
        count=$(ls -1 "$IMAGE_DIR"/*.tar 2>/dev/null | wc -l)
        size=$(du -sh "$IMAGE_DIR" 2>/dev/null | cut -f1)
        echo -e "  ${GREEN}✓${NC} $count images ($size)"
        ls -1 "$IMAGE_DIR"/*.tar 2>/dev/null | while read f; do
            echo "      $(basename "$f")"
        done
    else
        echo -e "  ${YELLOW}⚠${NC} Not created (run 'export' to create)"
    fi

    echo ""
    echo "Project images:"
    cd "$PROJECT_ROOT"
    PROJECT_IMAGES=$(docker compose config --images 2>/dev/null)
    for img in $PROJECT_IMAGES; do
        if docker image inspect "$img" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $img"
        else
            echo -e "  ${RED}✗${NC} $img (needs build)"
        fi
    done
}

case "${1:-status}" in
    export)
        export_images
        ;;
    import)
        import_images
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {export|import|status}"
        echo ""
        echo "  export  - Pull/build and save all images to .docker-images/"
        echo "  import  - Load images from .docker-images/ (for offline use)"
        echo "  status  - Show what's cached and available"
        exit 1
        ;;
esac
