#!/bin/bash
set -e

PROJECT_ID="ai-statistics-493215"
REGION="northamerica-northeast1"
FUNCTION_NAME="claude-usage-pipeline"
SA="claude-usage-sa@ai-statistics-493215.iam.gserviceaccount.com"
BQ_DATASET="claude_ai_usage"
SECRET_NAME="anthropic-admin-api-key"

echo "==> Création du dataset BigQuery (si inexistant)..."
bq --project_id="${PROJECT_ID}" mk \
  --dataset \
  --location=northamerica-northeast1 \
  "${PROJECT_ID}:${BQ_DATASET}" || echo "Dataset déjà existant, on continue."

echo "==> Application du schéma BigQuery..."
bq query \
  --project_id="${PROJECT_ID}" \
  --use_legacy_sql=false \
  --nouse_cache \
  "$(cat ../schema.sql)"

echo "==> Déploiement de la Cloud Function Gen2..."
gcloud functions deploy "${FUNCTION_NAME}" \
  --gen2 \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --runtime=python311 \
  --source=.. \
  --entry-point=handler \
  --trigger-http \
  --no-allow-unauthenticated \
  --service-account="${SA}" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},ANTHROPIC_SECRET_NAME=${SECRET_NAME},BQ_DATASET=${BQ_DATASET}" \
  --memory=512Mi \
  --timeout=540s

echo "==> Récupération de l'URL de la fonction..."
FUNCTION_URL=$(gcloud functions describe "${FUNCTION_NAME}" \
  --gen2 \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(serviceConfig.uri)")

echo "Function URL: ${FUNCTION_URL}"

echo "==> Création du job Cloud Scheduler (quotidien 06h00 America/Toronto)..."
gcloud scheduler jobs create http claude-usage-daily \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --schedule="0 6 * * *" \
  --time-zone="America/Toronto" \
  --uri="${FUNCTION_URL}" \
  --message-body='{"mode": "daily"}' \
  --headers="Content-Type=application/json" \
  --oidc-service-account-email="${SA}" \
  --oidc-token-audience="${FUNCTION_URL}"

echo "==> Déploiement terminé avec succès!"
echo "URL de la fonction : ${FUNCTION_URL}"
