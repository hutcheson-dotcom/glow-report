"""Minimal client for the Glowmarkt (Bright app) API.

Auth is the same username/password you use in the Bright app. The
application ID below is Hildebrand's published ID for individual users.
"""
from __future__ import annotations

import datetime as dt
import time

import requests

BASE = "https://api.glowmarkt.com/api/v0-1"
APP_ID = "b0f1b774-a586-4f72-9edd-27ead8aa7a8d"
MAX_DAYS_PER_CALL = 10  # API limit for PT30M readings


class GlowClient:
    def __init__(self, username: str, password: str):
        self.s = requests.Session()
        self.s.headers.update({"Content-Type": "application/json", "applicationId": APP_ID})
        r = self.s.post(f"{BASE}/auth", json={"username": username, "password": password}, timeout=30)
        r.raise_for_status()
        self.s.headers["token"] = r.json()["token"]

    def resources(self) -> list[dict]:
        r = self.s.get(f"{BASE}/resource", timeout=30)
        r.raise_for_status()
        return r.json()

    def entities(self) -> list[dict]:
        """Virtual entities = properties/meter groups on the account, with their resources."""
        r = self.s.get(f"{BASE}/virtualentity", timeout=30)
        r.raise_for_status()
        return r.json()

    def list_meters(self, classifier: str = "electricity.consumption") -> list[dict]:
        """Every matching resource on the account, with the property it belongs to."""
        out = []
        for ve in self.entities():
            for res in ve.get("resources", []):
                if res.get("classifier", "") == classifier or classifier in res.get("name", "").replace(" ", "."):
                    out.append({"property": ve.get("name", "?"), "veId": ve.get("veId"),
                                "name": res.get("name"), "resourceId": res["resourceId"]})
        if not out:  # fall back to the flat resource list
            out = [{"property": "?", "name": r.get("name"), "resourceId": r["resourceId"]}
                   for r in self.resources() if r.get("classifier") == classifier]
        return out

    def find_resource(self, classifier: str = "electricity.consumption", wanted: str | None = None) -> str:
        """Pick a resource. `wanted` is a resource ID or a case-insensitive fragment of the property name."""
        meters = self.list_meters(classifier)
        print(f"{len(meters)} {classifier} meter(s) on this account:")
        for m in meters:
            print(f"  property={m['property']!r}  resourceId={m['resourceId']}")
        if not meters:
            raise RuntimeError(f"No resource with classifier {classifier!r}")
        if wanted:
            w = wanted.strip().lower()
            for m in meters:
                if m["resourceId"].lower() == w or w in str(m["property"]).lower():
                    print(f"using {m['property']!r} ({m['resourceId']})")
                    return m["resourceId"]
            raise RuntimeError(f"GLOW_RESOURCE {wanted!r} did not match any meter above")
        if len(meters) > 1:
            raise RuntimeError("More than one electricity meter on this account. Set the GLOW_RESOURCE variable "
                               "to the property name or resourceId from the list above.")
        return
