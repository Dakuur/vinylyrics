#!/usr/bin/env bash
set -euo pipefail

echo "Installing vinylyrics system dependencies (Ubuntu/Debian)..."
sudo apt-get update
sudo apt-get install -y ffmpeg libsndfile1 portaudio19-dev python3-dev

echo "Done. Install uv separately if needed:"
echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
