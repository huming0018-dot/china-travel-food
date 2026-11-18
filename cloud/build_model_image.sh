#!/usr/bin/env bash
# Build only. Never starts the service or reads runtime credentials.
set -euo pipefail
cd "$(dirname "$0")"
: "${MODEL_WHEELHOUSE:?Set an absolute private wheelhouse outside the checkout}"
: "${MODEL_ACCESS_WHEEL_SHA256:?Set the recorded wheel SHA256}"
[[ "$MODEL_WHEELHOUSE" = /* ]] || { echo 'Wheelhouse must be absolute' >&2; exit 2; }
wheelhouse=$(cd "$MODEL_WHEELHOUSE" && pwd -P)
checkout=$(cd .. && pwd -P)
case "$wheelhouse/" in "$checkout/"*) echo 'Wheelhouse must be outside the checkout' >&2; exit 2;; esac
[[ "$MODEL_ACCESS_WHEEL_SHA256" =~ ^[a-fA-F0-9]{64}$ ]] || { echo 'Invalid wheel SHA256' >&2; exit 2; }
wheel="$wheelhouse/agent_model_access-0.1.0-py3-none-any.whl"
printf '%s  %s\n' "$MODEL_ACCESS_WHEEL_SHA256" "$wheel" | sha256sum -c -
docker buildx version >/dev/null
docker buildx build --load --platform linux/amd64 \
  --build-context "model_wheels=$wheelhouse" \
  --build-arg "MODEL_ACCESS_WHEEL_SHA256=$MODEL_ACCESS_WHEEL_SHA256" \
  -t "${MODEL_IMAGE_TAG:-food-model-access-check}" .
