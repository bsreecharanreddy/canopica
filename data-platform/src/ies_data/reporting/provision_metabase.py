"""Idempotently provisions Metabase from code: completes the one-time
initial-admin setup if it hasn't run yet, connects Metabase to the serving
Postgres database, and creates the "Determinations by month and outcome"
question plus the "SNAP determinations" dashboard over Task 11's serving
mart. Re-running finds each object by name instead of duplicating it.

uv run python -m ies_data.reporting.provision_metabase

Every request shape below was verified against a live
metabase/metabase:latest (v0.63.14.2) container during development, not
reconstructed from docs alone -- Metabase's REST API is undocumented/
semi-stable across versions, so this file is the source of truth for what
actually works on the version this project runs.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from ies_data.config import Settings

DATABASE_NAME = "IES Serving"
CARD_NAME = "Determinations by month and outcome"
DASHBOARD_NAME = "SNAP determinations"
CARD_QUERY = (
    "select benefit_month, outcome, determination_count, total_benefit_amount "
    "from reporting.mart_determination_outcomes "
    "order by benefit_month"
)


def _serving_connection_details(serving_dsn: str) -> dict[str, object]:
    """serving_dsn's host must be resolvable by Metabase's own container,
    not by whatever process runs this script -- see ../../../reporting/
    dashboard/README.md's "IES_SERVING_DSN's host must resolve for
    Metabase, not for the caller" for the real failure this caused."""
    parsed = urlparse(serving_dsn)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username,
        "password": parsed.password,
    }


def _complete_setup_if_needed(client: httpx.Client, user: str, password: str) -> str | None:
    """Runs Metabase's initial-admin setup if `has-user-setup` is still
    false. Returns a ready-to-use session id when setup ran, else None (the
    caller logs in instead) -- setup can only be called once per instance."""
    properties = client.get("/api/session/properties").raise_for_status().json()
    if properties.get("has-user-setup"):
        return None

    response = client.post(
        "/api/setup",
        json={
            "token": properties["setup-token"],
            "user": {
                "first_name": "IES",
                "last_name": "Admin",
                "email": user,
                "password": password,
            },
            "prefs": {"site_name": "IES Reporting", "site_locale": "en", "allow_tracking": False},
        },
    )
    response.raise_for_status()
    session_id: str = response.json()["id"]
    return session_id


def _login(client: httpx.Client, user: str, password: str) -> str:
    response = client.post("/api/session", json={"username": user, "password": password})
    response.raise_for_status()
    session_id: str = response.json()["id"]
    return session_id


def _find_or_create_database(client: httpx.Client, serving_dsn: str) -> int:
    existing = client.get("/api/database").raise_for_status().json()["data"]
    for db in existing:
        if db["name"] == DATABASE_NAME:
            return int(db["id"])

    response = client.post(
        "/api/database",
        json={
            "engine": "postgres",
            "name": DATABASE_NAME,
            "details": _serving_connection_details(serving_dsn),
        },
    )
    response.raise_for_status()
    database_id: int = response.json()["id"]
    client.post(f"/api/database/{database_id}/sync_schema").raise_for_status()
    return database_id


def _find_or_create_card(client: httpx.Client, database_id: int) -> int:
    existing = client.get("/api/card").raise_for_status().json()
    for card in existing:
        if card["name"] == CARD_NAME:
            return int(card["id"])

    response = client.post(
        "/api/card",
        json={
            "name": CARD_NAME,
            "dataset_query": {
                "type": "native",
                "native": {"query": CARD_QUERY},
                "database": database_id,
            },
            "display": "table",
            "visualization_settings": {},
        },
    )
    response.raise_for_status()
    card_id: int = response.json()["id"]
    return card_id


def _find_or_create_dashboard_with_card(client: httpx.Client, card_id: int) -> int:
    existing = client.get("/api/dashboard").raise_for_status().json()
    dashboard_id: int
    for dashboard in existing:
        if dashboard["name"] == DASHBOARD_NAME:
            dashboard_id = int(dashboard["id"])
            detail = client.get(f"/api/dashboard/{dashboard_id}").raise_for_status().json()
            if any(dashcard["card_id"] == card_id for dashcard in detail["dashcards"]):
                return dashboard_id
            break
    else:
        response = client.post("/api/dashboard", json={"name": DASHBOARD_NAME})
        response.raise_for_status()
        dashboard_id = int(response.json()["id"])

    client.put(
        f"/api/dashboard/{dashboard_id}",
        json={
            "dashcards": [
                {"id": -1, "card_id": card_id, "row": 0, "col": 0, "size_x": 12, "size_y": 8}
            ]
        },
    ).raise_for_status()
    return dashboard_id


def provision(settings: Settings) -> int:
    """Runs the full idempotent provisioning flow against a running Metabase
    instance. Returns the "SNAP determinations" dashboard's id."""
    with httpx.Client(base_url=settings.metabase_url, timeout=30.0) as client:
        session_id = _complete_setup_if_needed(
            client, settings.metabase_user, settings.metabase_password
        )
        if session_id is None:
            session_id = _login(client, settings.metabase_user, settings.metabase_password)
        client.headers["X-Metabase-Session"] = session_id

        database_id = _find_or_create_database(client, settings.serving_dsn)
        card_id = _find_or_create_card(client, database_id)
        return _find_or_create_dashboard_with_card(client, card_id)


if __name__ == "__main__":
    dashboard_id = provision(Settings())
    print(f"Dashboard ready: {dashboard_id}")
