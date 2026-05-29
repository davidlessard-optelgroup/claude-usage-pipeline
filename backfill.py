"""
Backfill script — appelle le pipeline pour chaque jour manquant.

Usage:
    FUNCTION_URL=https://... python backfill.py

Variables d'environnement:
    FUNCTION_URL  URL de la Cloud Function (obligatoire)
    NO_AUTH       Si défini (ex: "1"), désactive l'authentification GCP (dev local)
"""

import os
import sys
import time
from datetime import date, timedelta

import requests

try:
    import google.auth.transport.requests
    import google.oauth2.id_token
    HAS_GOOGLE_AUTH = True
except ImportError:
    HAS_GOOGLE_AUTH = False


BACKFILL_START = date(2026, 4, 16)
BACKFILL_END = date(2026, 5, 29)  # inclusif

DELAY_BETWEEN_CALLS = 2  # secondes entre chaque appel


def get_id_token(url: str) -> str:
    auth_req = google.auth.transport.requests.Request()
    return google.oauth2.id_token.fetch_id_token(auth_req, url)


def call_pipeline(function_url: str, start_date: date, end_date: date, use_auth: bool) -> bool:
    payload = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }

    headers = {"Content-Type": "application/json"}
    if use_auth:
        if not HAS_GOOGLE_AUTH:
            print("ERREUR: google-auth non installé. Installez avec: pip install google-auth")
            sys.exit(1)
        token = get_id_token(function_url)
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.post(function_url, json=payload, headers=headers, timeout=120)
        if response.status_code == 200:
            data = response.json()
            print(
                f"  OK | daily_rows={data.get('daily_rows_inserted', '?')} "
                f"user_rows={data.get('user_daily_rows_inserted', '?')}"
            )
            return True
        else:
            print(f"  ERREUR HTTP {response.status_code}: {response.text[:200]}")
            return False
    except requests.exceptions.Timeout:
        print("  ERREUR: timeout (>120s)")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  ERREUR: {e}")
        return False


def main():
    function_url = os.environ.get("FUNCTION_URL", "").strip()
    if not function_url:
        print("ERREUR: la variable d'environnement FUNCTION_URL est requise.")
        print("  Exemple: FUNCTION_URL=https://region-project.cloudfunctions.net/nom python backfill.py")
        sys.exit(1)

    use_auth = not os.environ.get("NO_AUTH")

    current = BACKFILL_START
    total = (BACKFILL_END - BACKFILL_START).days + 1
    failed = []

    print(f"Backfill de {BACKFILL_START} à {BACKFILL_END} ({total} jour(s))")
    print(f"URL: {function_url}")
    print(f"Auth GCP: {'activée' if use_auth else 'désactivée'}")
    print()

    for i in range(total):
        day = BACKFILL_START + timedelta(days=i)
        next_day = day + timedelta(days=1)
        print(f"[{i + 1}/{total}] {day.isoformat()} ...", end=" ", flush=True)
        success = call_pipeline(function_url, day, next_day, use_auth)
        if not success:
            failed.append(day.isoformat())
        if i < total - 1:
            time.sleep(DELAY_BETWEEN_CALLS)

    print()
    print(f"Terminé. {total - len(failed)}/{total} jours réussis.")
    if failed:
        print(f"Jours en échec ({len(failed)}):")
        for d in failed:
            print(f"  - {d}")
        sys.exit(1)


if __name__ == "__main__":
    main()
