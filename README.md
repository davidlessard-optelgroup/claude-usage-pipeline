# Claude Usage Pipeline

Pipeline GCP pour extraire les métriques d'utilisation de Claude (Anthropic) et les charger dans BigQuery.

## Architecture

```
Cloud Scheduler (quotidien 06h00)
        │
        ▼
Cloud Function Gen2 (HTTP)
        │
        ├── Anthropic Admin API  ──► Extraction usage par modèle/workspace/utilisateur
        ├── Secret Manager       ──► Clé API Admin Anthropic
        └── BigQuery             ──► Stockage dans claude_ai_usage
```

**Tables BigQuery :**
- `daily_tokens` — agrégé par date / modèle / workspace
- `user_daily_tokens` — détail par date / modèle / utilisateur

---

## Prérequis

### 1. Clé Admin API Anthropic dans Secret Manager

```bash
echo -n "sk-ant-admin-VOTRE_CLE" | gcloud secrets create anthropic-admin-api-key \
  --project=ai-statistics-493215 \
  --replication-policy=automatic \
  --data-file=-
```

### 2. Compte de service avec les bons rôles

```bash
gcloud projects add-iam-policy-binding ai-statistics-493215 \
  --member="serviceAccount:claude-usage-sa@ai-statistics-493215.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding ai-statistics-493215 \
  --member="serviceAccount:claude-usage-sa@ai-statistics-493215.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

gcloud secrets add-iam-policy-binding anthropic-admin-api-key \
  --project=ai-statistics-493215 \
  --member="serviceAccount:claude-usage-sa@ai-statistics-493215.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### 3. APIs GCP activées

```bash
gcloud services enable cloudfunctions.googleapis.com \
  --project=ai-statistics-493215

gcloud services enable cloudscheduler.googleapis.com \
  --project=ai-statistics-493215

gcloud services enable secretmanager.googleapis.com \
  --project=ai-statistics-493215

gcloud services enable bigquery.googleapis.com \
  --project=ai-statistics-493215

gcloud services enable run.googleapis.com \
  --project=ai-statistics-493215

gcloud services enable cloudbuild.googleapis.com \
  --project=ai-statistics-493215
```

---

## Déploiement

```bash
cd deploy
chmod +x deploy.sh
./deploy.sh
```

Le script :
1. Crée le dataset BigQuery `claude_ai_usage` si inexistant
2. Crée les tables `daily_tokens` et `user_daily_tokens` (partitionnées par date)
3. Déploie la Cloud Function Gen2 en région `northamerica-northeast1`
4. Crée le job Cloud Scheduler quotidien à 06h00 (America/Toronto)

---

## Lancer le backfill (90 derniers jours)

```bash
cd deploy
chmod +x backfill.sh
./backfill.sh
```

Le backfill peut prendre quelques minutes selon le volume de données.

---

## Valider dans BigQuery

### Vérifier les données agrégées par workspace

```sql
SELECT
  DATE(start_time)            AS date,
  model,
  workspace_id,
  SUM(input_tokens)           AS total_input_tokens,
  SUM(output_tokens)          AS total_output_tokens,
  SUM(cache_read_input_tokens) AS total_cache_read
FROM `ai-statistics-493215.claude_ai_usage.daily_tokens`
WHERE DATE(start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 4 DESC;
```

### Vérifier les données par utilisateur

```sql
SELECT
  DATE(start_time)  AS date,
  model,
  user,
  SUM(input_tokens)  AS total_input_tokens,
  SUM(output_tokens) AS total_output_tokens
FROM `ai-statistics-493215.claude_ai_usage.user_daily_tokens`
WHERE DATE(start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 4 DESC;
```

### Vérifier la fraîcheur des données

```sql
SELECT
  MAX(DATE(start_time)) AS derniere_date,
  COUNT(*)              AS nb_lignes
FROM `ai-statistics-493215.claude_ai_usage.daily_tokens`;
```

---

## Variables d'environnement

| Variable               | Valeur                     | Description                           |
|------------------------|----------------------------|---------------------------------------|
| `GCP_PROJECT_ID`       | `ai-statistics-493215`     | Projet GCP cible                      |
| `ANTHROPIC_SECRET_NAME`| `anthropic-admin-api-key`  | Nom du secret dans Secret Manager     |
| `BQ_DATASET`           | `claude_ai_usage`          | Dataset BigQuery cible                |

---

## Structure du repo

```
claude-usage-pipeline/
├── main.py              # Entry point Cloud Function (handler HTTP)
├── requirements.txt     # Dépendances Python
├── schema.sql           # DDL BigQuery (2 tables partitionnées)
├── .env.example         # Modèle de variables d'environnement
├── deploy/
│   ├── deploy.sh        # Script de déploiement complet
│   └── backfill.sh      # Déclenchement du backfill 90 jours
└── README.md
```
