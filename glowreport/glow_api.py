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

    def catchup(self, resource_id: str) -> None:
        """Ask Hildebrand to pull the latest readings from the DCC. Best effort."""
        try:
            r = self.s.get(f"{BASE}/resource/{resource_id}/catchup", timeout=30)
            print("catchup:", r.status_code, r.text[:120])
        except requests.RequestException as e:
            print("catchup failed:", e)

    def readings(self, resource_id: str, start_day: dt.date, end_day: dt.date) -> list[tuple[int, float]]:
        """Half-hourly kWh readings as (epoch_seconds, kWh) for whole local days
        start_day..end_day inclusive. Missing slots are omitted (nulls=1), never 0."""
        out: list[tuple[int, float]] = []
        cur = start_day
        while cur <= end_day:
            chunk_end = min(cur + dt.timedelta(days=MAX_DAYS_PER_CALL - 1), end_day)
            params = {
                "from": f"{cur:%Y-%m-%d}T00:00:00",
                "to": f"{chunk_end:%Y-%m-%d}T23:59:59",
                "period": "PT30M",
                "function": "sum",
                "offset": 0,
                "nulls": 1,
            }
            r = self.s.get(f"{BASE}/resource/{resource_id}/readings", params=params, timeout=60)
            r.raise_for_status()
            data = r.json().get("data", [])
            got = [(int(ts), float(v)) for ts, v in data if v is not None]
            print(f"  {cur} to {chunk_end}: {len(data)} slots, {len(got)} with data, {sum(v for _, v in got):.1f} kWh")
            out.extend(got)
            cur = chunk_end + dt.timedelta(days=1)
            time.sleep(0.5)
        return out
