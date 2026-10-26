"""Search Console numbers inside the dashboard (phase 3).

Uses a Google service account that has been added as a user on the Search Console property.
Without credentials the dashboard shows setup instructions instead."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import requests
from urllib.parse import quote
from flask import current_app

SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


def is_configured() -> bool:
    return bool(current_app.config.get("GSC_CREDENTIALS_FILE"))


def _token() -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        current_app.config["GSC_CREDENTIALS_FILE"], scopes=[SCOPE])
    creds.refresh(Request())
    return creds.token  # type: ignore[return-value]


def query(dimension: str, days: int = 28, limit: int = 25) -> list[dict[str, Any]]:
    prop = quote(current_app.config["GSC_PROPERTY"], safe="")
    end = date.today() - timedelta(days=2)  # GSC data lags ~2 days
    body = {"startDate": (end - timedelta(days=days)).isoformat(), "endDate": end.isoformat(),
            "dimensions": [dimension], "rowLimit": limit}
    r = requests.post(f"https://searchconsole.googleapis.com/webmasters/v3/sites/{prop}/searchAnalytics/query",
                      json=body, headers={"Authorization": f"Bearer {_token()}"}, timeout=20)
    r.raise_for_status()
    return [{"key": row["keys"][0], "clicks": row["clicks"], "impressions": row["impressions"],
             "ctr": round(row["ctr"] * 100, 1), "position": round(row["position"], 1)}
            for row in r.json().get("rows", [])]
