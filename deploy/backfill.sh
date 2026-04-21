#!/bin/bash
set -e

PROJECT_ID="ai-statistics-493215"
REGION="northamerica-northeast1"
FUNCTION_NAME="claude-usage-pipeline"

echo "==> Récupération de l'URL de la Cloud Function..."
FUNCTION_URL=$(gcloud functions describe "${FUNCTION_NAME}" \
  --gen2 \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(serviceConfig.uri)")

echo "==> Déclenchement du backfill (90 derniers jours) sur : ${FUNCTION_URL}"
curl -s -X POST "${FUNCTION_URL}" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token --audiences="${FUNCTION_URL}")" \
  -H "Content-Type: application/json" \
  -d '{"mode": "backfill"}' | python3 -m json.tool

echo ""
echo "==> Backfill déclenché."
