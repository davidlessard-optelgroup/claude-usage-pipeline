import json
import logging
import os
from datetime import datetime, timedelta, timezone

import functions_framework
import requests
from google.cloud import bigquery, secretmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
ANTHROPIC_SECRET_NAME = os.environ["ANTHROPIC_SECRET_NAME"]
BQ_DATASET = os.environ["BQ_DATASET"]

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/organizations/usage_report/messages"
ANTHROPIC_VERSION = "2023-06-01"


def get_secret(secret_name: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8").strip()


def fetch_usage(api_key: str, starting_at: str, ending_at: str, group_by: list[str]) -> list[dict]:
    headers = {
        "anthropic-version": ANTHROPIC_VERSION,
        "x-api-key": api_key,
    }

    all_records: list[dict] = []
    page_token: str | None = None

    while True:
        params: list[tuple[str, str]] = [
            ("starting_at", starting_at),
            ("ending_at", ending_at),
            ("bucket_width", "1d"),
        ]
        for g in group_by:
            params.append(("group_by[]", g))
        if page_token:
            params.append(("page", page_token))

        response = requests.get(ANTHROPIC_API_URL, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()

        batch = payload.get("data", [])
        all_records.extend(batch)
        logger.info("Fetched %d records (total: %d), groups: %s", len(batch), len(all_records), group_by)

        if not payload.get("has_more"):
            break
        page_token = payload.get("next_page")

    return all_records


def build_daily_row(record: dict) -> dict:
    return {
        "start_time": record["start_time"],
        "end_time": record["end_time"],
        "model": record.get("model"),
        "workspace_id": record.get("workspace_id"),
        "input_tokens": record.get("input_tokens", 0),
        "output_tokens": record.get("output_tokens", 0),
        "cache_read_input_tokens": record.get("cache_read_input_tokens", 0),
        "cache_creation_input_tokens": record.get("cache_creation_input_tokens", 0),
    }


def build_user_daily_row(record: dict) -> dict:
    user = record.get("user")
    if isinstance(user, dict):
        user = user.get("email") or user.get("id") or json.dumps(user)
    return {
        "start_time": record["start_time"],
        "end_time": record["end_time"],
        "model": record.get("model"),
        "workspace_id": record.get("workspace_id"),
        "user": user,
        "input_tokens": record.get("input_tokens", 0),
        "output_tokens": record.get("output_tokens", 0),
        "cache_read_input_tokens": record.get("cache_read_input_tokens", 0),
        "cache_creation_input_tokens": record.get("cache_creation_input_tokens", 0),
    }


def load_to_bigquery(client: bigquery.Client, table_id: str, rows: list[dict]) -> None:
    if not rows:
        logger.info("No rows to insert for %s — skipping.", table_id)
        return

    dates = sorted({r["start_time"][:10] for r in rows})
    date_list = ", ".join(f"DATE '{d}'" for d in dates)
    delete_sql = f"DELETE FROM `{table_id}` WHERE DATE(start_time) IN ({date_list})"

    client.query(delete_sql).result()
    logger.info("Purged %d date(s) from %s", len(dates), table_id)

    errors = client.insert_rows_json(table_id, rows)
    if errors:
        raise RuntimeError(f"BigQuery streaming insert errors for {table_id}: {errors}")

    logger.info("Inserted %d rows into %s", len(rows), table_id)


@functions_framework.http
def handler(request):
    try:
        body = request.get_json(silent=True) or {}
        mode = body.get("mode", "daily")

        now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        if mode == "backfill":
            starting_at = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
            ending_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            yesterday = now - timedelta(days=1)
            starting_at = yesterday.strftime("%Y-%m-%dT%H:%M:%SZ")
            ending_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.info("Mode: %s | %s → %s", mode, starting_at, ending_at)

        api_key = get_secret(ANTHROPIC_SECRET_NAME)

        daily_records = fetch_usage(api_key, starting_at, ending_at, ["model", "workspace_id"])
        user_records = fetch_usage(api_key, starting_at, ending_at, ["model", "workspace_id", "user"])

        daily_rows = [build_daily_row(r) for r in daily_records]
        user_daily_rows = [build_user_daily_row(r) for r in user_records]

        bq = bigquery.Client(project=GCP_PROJECT_ID)
        daily_table = f"{GCP_PROJECT_ID}.{BQ_DATASET}.daily_tokens"
        user_table = f"{GCP_PROJECT_ID}.{BQ_DATASET}.user_daily_tokens"

        load_to_bigquery(bq, daily_table, daily_rows)
        load_to_bigquery(bq, user_table, user_daily_rows)

        result = {
            "status": "ok",
            "mode": mode,
            "range": {"starting_at": starting_at, "ending_at": ending_at},
            "daily_rows_inserted": len(daily_rows),
            "user_daily_rows_inserted": len(user_daily_rows),
        }
        logger.info("Pipeline complete: %s", result)
        return result, 200

    except Exception:
        logger.exception("Pipeline error")
        return {"status": "error"}, 500
