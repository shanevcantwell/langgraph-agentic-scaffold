#!/bin/bash

# A simple backup script for the LangGraph project.
# This should be run from the project root (e.g., from /MyLangGraphProject).

# --- Configuration ---
# The directory containing the source code to be backed up
SOURCE_DIR="./app/langgraph-boilerplate"

# The directory where backups will be stored
BACKUP_DIR="./backups"

# The filename for the backup, with a timestamp
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILENAME="app-backup-${TIMESTAMP}.tar.gz"
DESTINATION_FILE="${BACKUP_DIR}/${BACKUP_FILENAME}"

# --- Exclusions ---
# List of patterns to exclude from the backup
# Useful for ignoring virtual environments, cache, etc.
EXCLUDE_PATTERNS=(
  "--exclude='*.pyc'"
  "--exclude='__pycache__'"
  "--exclude='.venv'"
  "--exclude='.git'"
)

# --- Script Logic ---
echo "Starting backup of ${SOURCE_DIR}..."

# Check if the source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
  echo "Error: Source directory ${SOURCE_DIR} not found."
  exit 1
fi

# Create the backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

echo "Creating archive: ${DESTINATION_FILE}"

# Create the compressed tarball
# -c: create archive
# -z: compress with gzip
# -v: verbose (shows files being added)
# -f: use archive file
tar -czvf "${DESTINATION_FILE}" ${EXCLUDE_PATTERNS[*]} -C "$(dirname "$SOURCE_DIR")" "$(basename "$SOURCE_DIR")"

echo ""
echo "Backup complete!"
echo "Archive created at: ${DESTINATION_FILE}"

