#!/bin/sh
# Offline install only; authentication and wheel construction belong to the build host.
set -eu
wheelhouse=${1:?wheelhouse directory required}
expected=${2:?expected wheel SHA256 required}
case "$expected" in *[!0-9a-fA-F]*|'') echo "Invalid wheel SHA256" >&2; exit 2;; esac
[ "${#expected}" -eq 64 ] || { echo "Expected 64-character SHA256" >&2; exit 2; }
wheel="$wheelhouse/agent_model_access-0.1.0-py3-none-any.whl"
printf '%s  %s\n' "$expected" "$wheel" | sha256sum -c -
python -m pip install --no-index --no-cache-dir --find-links="$wheelhouse" "$wheel"
python -I -c 'from agent_model_access import create_client; assert callable(create_client)'
