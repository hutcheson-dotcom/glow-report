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

    def find_resource(self, classifier: str = "electricity.consumption") -> str:
        for res in self.resources():
            if res.get("classifier") == classifier:
                return res["resourceId"]
        raise RuntimeError(f"No resource with classifier {classifier!r}")

    def readings(self, resource_id: str, start: dt.datetime, end: dt.datetime) -> list[tuple[int, float]]:
        """Half-hourly kWh readings as (epoch_seconds, kWh). Times are UTC."""
        out: list[tuple[int, float]] = []
        cur = start
        while cur < end:
            chunk_end = min(cur + dt.timedelta(days=MAX_DAYS_PER_CALL), end)
            params = {
                "from": cur.strftime("%Y-%m-%dT%H:%M:%S"),
                "to": chunk_end.strftime("%Y-%m-%dT%H:%M:%S"),
                "period": "PT30M",
                "function": "sum",
                "offset": 0,
            }
            r = self.s.get(f"{BASE}/resource/{resource_id}/readings", params=params, timeout=60)
            r.raise_for_status()
            for ts, kwh in r.json().get("data", []):
                if kwh is not None:
                    out.append((int(ts), float(kwh)))
            cur = chunk_end
            time.sleep(0.5)  # be polite
        return out
