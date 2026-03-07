#!/usr/bin/env bash
# =============================================================================
# Meshtastic Site Planner — Setup & Startup Script (Linux / macOS)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Check dependencies ──────────────────────────────────────────────────────

check_cmd() {
    command -v "$1" &>/dev/null || error "$1 is required but not installed."
}

info "Checking dependencies..."
check_cmd docker
check_cmd git

# Check for docker compose (plugin) or docker-compose (standalone)
if docker compose version &>/dev/null 2>&1; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
else
    error "docker compose is required but not installed."
fi

info "Using: $COMPOSE"

# ── Git submodules ───────────────────────────────────────────────────────────

if [ ! -f "splat/splat.cpp" ]; then
    info "Initializing git submodules..."
    git submodule update --init --recursive
else
    info "Git submodules already initialized."
fi

# ── Environment file ─────────────────────────────────────────────────────────

if [ ! -f ".env" ]; then
    info "Creating .env from .env.example..."
    cp .env.example .env
    warn "Review .env and adjust settings for your environment."
else
    info ".env already exists — skipping copy."
fi

# ── Build and start ──────────────────────────────────────────────────────────

info "Building and starting all services..."
$COMPOSE up --build -d

echo ""
info "Services started. Useful commands:"
echo ""
echo "  $COMPOSE ps                  # Check service status"
echo "  $COMPOSE logs -f app         # Follow app logs"
echo "  $COMPOSE logs -f worker      # Follow light worker logs"
echo "  $COMPOSE logs -f autoscaler  # Follow autoscaler logs"
echo "  $COMPOSE down                # Stop all services"
echo ""
echo "  Flower dashboard:  http://localhost:5555"
echo "  Application:       http://localhost:8080"
echo ""
