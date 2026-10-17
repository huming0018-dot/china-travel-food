#!/usr/bin/env bash
set -eu
skill_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
exec "${FOOD_RADAR_PYTHON:-python3}" "$skill_dir/scripts/doctor.py" "$@"
