#!/bin/sh
set -e

echo "[entrypoint] Generating config.yaml from environment variables..."
python /app/generate_config.py

echo "[entrypoint] Starting LiteLLM Proxy..."
exec litellm --config /app/config.yaml --port 4000
