#!/usr/bin/env bash
# Adapted from Assignment 1 §4.4 — build the image and deploy it to Cloud Run.
# Credentials come from the shell environment, never from this file.

set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "Copy .env.example to .env and fill in your keys before deploying." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env}"
: "${TAVILY_API_KEY:?Set TAVILY_API_KEY in .env}"
if [[ -z "${NVIDIA_API_KEY:-}" && -z "${OPENAI_API_KEY:-}" ]]; then
  echo "Set NVIDIA_API_KEY or OPENAI_API_KEY in .env" >&2
  exit 1
fi

ENV_VARS="TAVILY_API_KEY=${TAVILY_API_KEY},MCP_SERVERS_CONFIG=/app/mcp_config.json,NOTES_DIR=/app/notes,SQLITE_PATH=/app/data/research.db"
if [[ -n "${NVIDIA_API_KEY:-}" ]]; then
  NVIDIA_MODEL="${NVIDIA_MODEL:-nvidia/nemotron-3.5-lightning-30b-a3b}"
  ENV_VARS="${ENV_VARS},NVIDIA_API_KEY=${NVIDIA_API_KEY},NVIDIA_MODEL=${NVIDIA_MODEL}"
fi
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  OPENAI_MODEL="${OPENAI_MODEL:-gpt-5}"
  ENV_VARS="${ENV_VARS},OPENAI_API_KEY=${OPENAI_API_KEY},OPENAI_MODEL=${OPENAI_MODEL}"
fi
if [[ -n "${OPENAI_BASE_URL:-}" ]]; then
  ENV_VARS="${ENV_VARS},OPENAI_BASE_URL=${OPENAI_BASE_URL}"
fi

gcloud builds submit --tag "gcr.io/${GCP_PROJECT_ID}/csci599-a1"
gcloud run deploy csci599-a1 \
  --image "gcr.io/${GCP_PROJECT_ID}/csci599-a1" \
  --platform managed \
  --region us-west1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 1 \
  --set-env-vars "${ENV_VARS}"
