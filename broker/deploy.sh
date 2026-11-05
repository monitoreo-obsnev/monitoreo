#!/usr/bin/env bash
# Deploys the token broker of MonitorEO (main.py) on Cloud Run, with gcloud signed in with an owner of PROJECT:
#
#     broker/deploy.sh PROJECT [REGION]
#
# PROJECT must be registered in Earth Engine and have billing (Cloud Run). It can be run again: what exists is kept.
# USER_LIMIT (default 25) is the research EECU-hours of each user of the shared account a month: who spends them gets no
# more tokens until the next month. EECU_LIMIT is the EECU-hours a month of the Earth Engine tier of PROJECT (150
# Community, 1000 Contributor, 100000 Partner; default 1000): the users of the shared account stop getting tokens when
# the project has spent all of it but PROJECT_RESERVE (default 10 % of EECU_LIMIT), kept for the app of Earth Engine
# and the team. REQUIRE_USER=0 gives tokens to the versions of the tools without the ID of their user (before 0.3.21),
# outside those limits.
# It creates two service accounts, without keys:
#   monitoreo-public  computes in Earth Engine with the quota of PROJECT and nothing else (the role monitoreoCompute,
#                     below); the broker gives tokens of 1 hour of this account.
#   monitoreo-broker  runs the service and may only create tokens of monitoreo-public and read the metrics of
#                     PROJECT (Monitoring Viewer: the EECUs spent this month by each user).
#   monitoreo-build   builds its container in Cloud Build (role run.builder), instead of the default service account.
# monitoreoCompute is not earthengine.viewer on purpose: that role would also let anyone with a token read every asset
# of PROJECT and list its tasks. This one only computes (values, pixels, maps, thumbnails and tables of the public
# catalog of Earth Engine): no assets, no tasks, no exports.
#
# To stop the shared account at once (the tokens given stop working):
#     gcloud iam service-accounts disable monitoreo-public@PROJECT.iam.gserviceaccount.com --project PROJECT
# and `enable` to restart it.
#
# The language model of the assistant (/chat): Gemini of the Gemini API with the billing of PROJECT (its paid tier in
# Google AI Studio). The first time, it creates the API key monitoreo-gemini, which only opens the Gemini API, and keeps
# it in the secret monitoreo-gemini-key of Secret Manager, which only monitoreo-broker may read: the key is never
# printed nor written anywhere else. Claude (models claude-*) needs the key of the API of Anthropic in the secret
# monitoreo-claude-key, created once by hand from the Console of Anthropic, without showing it (copy the key, then):
#     pbpaste | gcloud secrets create monitoreo-claude-key --project PROJECT --replication-policy automatic --data-file -
# CHAT_MODELS (comma-separated, in order: the first one answers, the next ones only while it has no credit; default
# claude-sonnet-5-5,gemini-3.8-flash, chosen on 2026-11-05 by a comparison of the models on a bank of questions; the
# users do not choose: CHAT_CHOOSE stays 0), CHAT_REASONING (default low),
# CHAT_MAX_TOKENS (default 8192), CHAT_LIMIT (requests per address and hour, default 120) and CHAT_USER_DAY (requests
# of each user a day, default 400) are those of main.py. Set spend caps in AI Studio (Spend) and in the Console of
# Anthropic: they are what limit the cost. To stop the language model at once:
#     gcloud services api-keys delete monitoreo-gemini --project PROJECT
# (`undelete` within 30 days), or disable the key of Anthropic in its Console.
set -euo pipefail
PROJECT=${1:?usage: deploy.sh PROJECT [REGION]}
REGION=${2:-europe-west1}
EECU_LIMIT=${EECU_LIMIT:-1000}
USER_LIMIT=${USER_LIMIT:-25}
PROJECT_RESERVE=${PROJECT_RESERVE:-$(( EECU_LIMIT / 10 ))}
REQUIRE_USER=${REQUIRE_USER:-1}
CHAT_MODELS=${CHAT_MODELS:-claude-sonnet-5-5,gemini-3.8-flash}
CHAT_REASONING=${CHAT_REASONING:-low}
CHAT_MAX_TOKENS=${CHAT_MAX_TOKENS:-8192}
CHAT_LIMIT=${CHAT_LIMIT:-120}
CHAT_USER_DAY=${CHAT_USER_DAY:-400}
KEY=monitoreo-gemini
SECRET=monitoreo-gemini-key
CLAUDE_SECRET=monitoreo-claude-key
HERE=$(cd "$(dirname "$0")" && pwd)
PUBLIC=monitoreo-public@$PROJECT.iam.gserviceaccount.com
BROKER=monitoreo-broker@$PROJECT.iam.gserviceaccount.com
BUILD=monitoreo-build@$PROJECT.iam.gserviceaccount.com

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  iamcredentials.googleapis.com earthengine.googleapis.com monitoring.googleapis.com secretmanager.googleapis.com \
  generativelanguage.googleapis.com apikeys.googleapis.com --project "$PROJECT"

for sa in monitoreo-public monitoreo-broker monitoreo-build; do
  gcloud iam service-accounts describe "$sa@$PROJECT.iam.gserviceaccount.com" --project "$PROJECT" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "$sa" --project "$PROJECT" --display-name "MonitorEO: $sa"
done

PERMISSIONS=earthengine.computations.create,earthengine.maps.create,earthengine.maps.get,\
earthengine.thumbnails.create,earthengine.thumbnails.get,earthengine.tables.create,earthengine.tables.get,\
earthengine.config.get,serviceusage.services.use,resourcemanager.projects.get
if gcloud iam roles describe monitoreoCompute --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam roles update monitoreoCompute --project "$PROJECT" --permissions "$PERMISSIONS" --quiet >/dev/null
else
  gcloud iam roles create monitoreoCompute --project "$PROJECT" --title "MonitorEO: compute in Earth Engine" \
    --description "Shared account of MonitorEO: computations only (no assets, tasks or exports)" \
    --permissions "$PERMISSIONS" --stage GA --quiet >/dev/null
fi
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$PUBLIC" \
  --role "projects/$PROJECT/roles/monitoreoCompute" --condition None --quiet >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$PUBLIC" --project "$PROJECT" \
  --member "serviceAccount:$BROKER" --role roles/iam.serviceAccountTokenCreator --quiet >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$BROKER" --role roles/monitoring.viewer \
  --condition None --quiet >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$BUILD" --role roles/run.builder \
  --condition None --quiet >/dev/null

# the key of the Gemini API, from its creation straight into Secret Manager
if ! gcloud secrets describe "$SECRET" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud services api-keys describe "$KEY" --project "$PROJECT" >/dev/null 2>&1 ||
    gcloud services api-keys create --key-id "$KEY" --project "$PROJECT" --display-name "MonitorEO: Gemini of the broker" \
      --api-target service=generativelanguage.googleapis.com >/dev/null 2>&1
  gcloud services api-keys get-key-string "$KEY" --project "$PROJECT" --format 'value(keyString)' |
    tr -d '\n' | gcloud secrets create "$SECRET" --project "$PROJECT" --replication-policy automatic --data-file -
fi
gcloud secrets add-iam-policy-binding "$SECRET" --project "$PROJECT" --member "serviceAccount:$BROKER" \
  --role roles/secretmanager.secretAccessor --condition None --quiet >/dev/null
SECRETS="GEMINI_API_KEY=$SECRET:latest"
if gcloud secrets describe "$CLAUDE_SECRET" --project "$PROJECT" >/dev/null 2>&1; then  # Claude, if its key is there
  gcloud secrets add-iam-policy-binding "$CLAUDE_SECRET" --project "$PROJECT" --member "serviceAccount:$BROKER" \
    --role roles/secretmanager.secretAccessor --condition None --quiet >/dev/null
  SECRETS="$SECRETS,ANTHROPIC_API_KEY=$CLAUDE_SECRET:latest"
fi

# ^;^: the variables are separated by ; (CHAT_MODELS has commas)
gcloud run deploy monitoreo-broker --source "$HERE" --project "$PROJECT" --region "$REGION" \
  --build-service-account "projects/$PROJECT/serviceAccounts/$BUILD" \
  --service-account "$BROKER" --allow-unauthenticated --max-instances 2 --memory 256Mi --cpu 1 \
  --set-env-vars "^;^PUBLIC_SA=$PUBLIC;EE_PROJECT=$PROJECT;EECU_LIMIT=$EECU_LIMIT;USER_LIMIT=$USER_LIMIT;PROJECT_RESERVE=$PROJECT_RESERVE;REQUIRE_USER=$REQUIRE_USER;CHAT_MODELS=$CHAT_MODELS;CHAT_REASONING=$CHAT_REASONING;CHAT_MAX_TOKENS=$CHAT_MAX_TOKENS;CHAT_LIMIT=$CHAT_LIMIT;CHAT_USER_DAY=$CHAT_USER_DAY" \
  --set-secrets "$SECRETS" \
  --quiet

gcloud run services describe monitoreo-broker --project "$PROJECT" --region "$REGION" --format 'value(status.url)'
