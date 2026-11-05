#!/usr/bin/env bash
# Deploys the token broker of MonitorEO (main.py) on Cloud Run, with gcloud signed in with an owner of PROJECT:
#
#     broker/deploy.sh PROJECT [REGION]
#
# PROJECT must be registered in Earth Engine and have billing (Cloud Run). It can be run again: what exists is kept.
# USER_LIMIT (default 10) is the research EECU-hours of each user of the shared account a month: who spends them gets no
# more tokens until the next month. EECU_LIMIT (EECU-hours a month of the Earth Engine tier of PROJECT: 150 Community,
# 1000 Contributor, 100000 Partner; default 150) is only told by GET /usage. REQUIRE_USER=0 gives tokens to the versions
# of the tools without the ID of their user (before 0.3.21), outside those limits.
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
set -euo pipefail
PROJECT=${1:?usage: deploy.sh PROJECT [REGION]}
REGION=${2:-europe-west1}
EECU_LIMIT=${EECU_LIMIT:-150}
USER_LIMIT=${USER_LIMIT:-10}
REQUIRE_USER=${REQUIRE_USER:-1}
HERE=$(cd "$(dirname "$0")" && pwd)
PUBLIC=monitoreo-public@$PROJECT.iam.gserviceaccount.com
BROKER=monitoreo-broker@$PROJECT.iam.gserviceaccount.com
BUILD=monitoreo-build@$PROJECT.iam.gserviceaccount.com

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  iamcredentials.googleapis.com earthengine.googleapis.com monitoring.googleapis.com --project "$PROJECT"

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

gcloud run deploy monitoreo-broker --source "$HERE" --project "$PROJECT" --region "$REGION" \
  --build-service-account "projects/$PROJECT/serviceAccounts/$BUILD" \
  --service-account "$BROKER" --allow-unauthenticated --max-instances 2 --memory 256Mi --cpu 1 \
  --set-env-vars "PUBLIC_SA=$PUBLIC,EE_PROJECT=$PROJECT,EECU_LIMIT=$EECU_LIMIT,USER_LIMIT=$USER_LIMIT,REQUIRE_USER=$REQUIRE_USER" \
  --quiet

gcloud run services describe monitoreo-broker --project "$PROJECT" --region "$REGION" --format 'value(status.url)'
