#!/usr/bin/env bash
# v4: build offline by default. Publishing uses the checked, linked website rollout.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  ""|--no-upload) exec python3 cloud/crowd_build.py ;;
  --check) exec python3 cloud/crowd_launch.py ;;
  --apply) exec python3 cloud/crowd_launch.py --apply ;;
  *) echo "Usage: crowd_extension/publish.sh [--no-upload|--check|--apply]" >&2; exit 2 ;;
esac
