#!/usr/bin/env bash
# Build AquaSentinel on Cloud Build and deploy it to Cloud Run (one instance, password-protected).
#
#   ./deploy.sh <gcp-project-id> [region]
#
# Reads GEMINI_API_KEY, GEMINI_MODEL and APP_PASSWORD from Aquaculture_Webapp/.env. Needs the gcloud CLI,
# logged in (gcloud auth login), and a project with billing enabled.
set -euo pipefail
cd "$(dirname "$0")"
PROJECT="${1:?usage: ./deploy.sh <gcp-project-id> [region]}"
REGION="${2:-asia-south1}"
SERVICE=aquasentinel
REPO=aquasentinel
IMAGE="$REGION-docker.pkg.dev/$PROJECT/$REPO/$SERVICE:$(date +%Y%m%d-%H%M%S)"

env_val() { grep -E "^$1=" Aquaculture_Webapp/.env 2>/dev/null | tail -1 | cut -d= -f2- || true; }
GEMINI_API_KEY="$(env_val GEMINI_API_KEY)"
GEMINI_MODEL="$(env_val GEMINI_MODEL)"
APP_PASSWORD="$(env_val APP_PASSWORD)"
[ -n "$APP_PASSWORD" ] || { echo "Set APP_PASSWORD in Aquaculture_Webapp/.env first (the login for the public URL)."; exit 1; }
[ -n "$GEMINI_API_KEY" ] || echo "Note: no GEMINI_API_KEY in .env - the agents will be disabled online."

gcloud config set project "$PROJECT" >/dev/null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION"

gcloud builds submit --config cloudbuild.yaml --substitutions "_IMAGE=$IMAGE" .

# Values go through a temp YAML file so special characters in keys and passwords survive
ENVFILE="$(mktemp)"; trap 'rm -f "$ENVFILE"' EXIT
GEMINI_API_KEY="$GEMINI_API_KEY" GEMINI_MODEL="$GEMINI_MODEL" APP_PASSWORD="$APP_PASSWORD" python3 - "$ENVFILE" <<'PY'
import json, os, sys
vals = {k: os.environ[k] for k in ("GEMINI_API_KEY", "GEMINI_MODEL", "APP_PASSWORD")}
vals.update(DATA_SOURCE="simulator", REPLAN_MODE="gemini")
open(sys.argv[1], "w").write("".join(f"{k}: {json.dumps(v)}\n" for k, v in vals.items()))
PY
# At most one instance: the simulator, WebSocket clients and SQLite live in this one process.
# It scales to zero when nobody is connected (costs ~nothing; data resets on the next start).
# To keep it running and keep its data while idle (~USD 40-50/month): MIN_INSTANCES=1 ./deploy.sh ...
MIN="${MIN_INSTANCES:-0}"
THROTTLE=$([ "$MIN" -gt 0 ] && echo --no-cpu-throttling || echo --cpu-throttling)
gcloud run deploy "$SERVICE" --image "$IMAGE" --region "$REGION" \
  --allow-unauthenticated --env-vars-file "$ENVFILE" \
  --min-instances "$MIN" --max-instances 1 "$THROTTLE" \
  --cpu 1 --memory 1Gi --timeout 3600 --session-affinity

echo "Live at: $(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')"
echo "Login: user 'aquasentinel', password = APP_PASSWORD from Aquaculture_Webapp/.env"
