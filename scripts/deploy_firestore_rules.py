"""Deploy Firestore security rules for NewQ via the Rules REST API.

NewQ uses Firestore for exactly one purpose: the backend publishes its
LAN address to `config/apiServer` (server presence for mobile
auto-discovery). The document contains a LAN address only — nothing
sensitive — so it is readable by any client; all other reads and all
client writes stay denied (Admin SDK writes bypass rules).

Usage:
    .venv/Scripts/python.exe scripts/deploy_firestore_rules.py

Authenticates with the service-account JSON (Editor role includes the
firebaserules.update permission).
"""

import json
import sys
import urllib.request

from google.oauth2 import service_account
from google.auth.transport.requests import Request

PROJECT_ID = "newq-05-01"
SERVICE_ACCOUNT = "firebase-service-account.json"
RULES_BASE = "https://firebaserules.googleapis.com/v1"

RULES_SOURCE = """rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // NewQ server presence: LAN address for mobile auto-discovery.
    // Contains nothing sensitive; open read, no client writes.
    match /config/{document} {
      allow read: if true;
      allow write: if false;
    }
  }
}
"""


def api_call(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    if url.startswith("/"):
        url = f"{RULES_BASE}{url}"
    elif not url.startswith("https://"):
        url = f"{RULES_BASE}/{url}"
    request = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def main() -> int:
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(Request())

    release_url = f"{RULES_BASE}/projects/{PROJECT_ID}/releases/cloud.firestore"

    # Show the currently deployed rules for transparency.
    current_source = None
    try:
        release = api_call("GET", release_url, creds.token)
        current_ruleset = api_call("GET", release["rulesetName"], creds.token)
        current_source = current_ruleset["source"]["files"][0]["content"]
        print("Current rules:")
        print(current_source)
        if "/config/{document}" in current_source:
            print("NewQ presence rules already deployed — nothing to do.")
            return 0
    except Exception as exc:
        print(f"No existing release (fresh project): {exc}")

    created = api_call(
        "POST",
        f"{RULES_BASE}/projects/{PROJECT_ID}/rulesets",
        creds.token,
        {"source": {"files": [{"name": "firestore.rules", "content": RULES_SOURCE}]}},
    )

    # UpdateReleaseRequest wraps the Release resource in a `release` field;
    # the release for Firestore is always named `cloud.firestore`.
    api_call(
        "PATCH",
        release_url,
        creds.token,
        {
            "release": {
                "name": f"projects/{PROJECT_ID}/releases/cloud.firestore",
                "rulesetName": created["name"],
            }
        },
    )

    release = api_call("GET", release_url, creds.token)
    live = api_call("GET", release["rulesetName"], creds.token)
    if "/config/{document}" not in live["source"]["files"][0]["content"]:
        print("ERROR: live ruleset does not contain the presence rule")
        return 1
    print(f"Deployed NewQ presence rules -> {created['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
