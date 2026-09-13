"""Flat-file store: data/readings.csv with columns epoch,kWh (UTC epoch seconds)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

TZ = "Europe/London"


def to_epoch(s: pd.Series) -> list[int]:
    """Epoch seconds regardless of index resolution."""
    return (s.index.tz_convert("UTC") - pd.Timestamp(0, tz="UTC")).total_seconds().astype(int).tolist()


def load(path: Path) -> pd.Series:
    """Return a tz-aware (Europe/London) half-hourly kWh series, or empty."""
    if not path.exists():
        return pd.Series(dtype=float, name="kWh")
    df = pd.read_csv(path)
    if "epoch" not in df.columns:  # Glowmarkt web export format
        df = df.rename(columns={"epochTimestamp": "epoch"})
    idx = pd.to_datetime(df["epoch"], unit="s", utc=True).dt.tz_convert(TZ)
    s = pd.Series(df["kWh"].astype(float).values, index=idx, name="kWh")
    return s[~s.index.duplicated(keep="last")].sort_index()


def merge(existing: pd.Series, new: list[tuple[int, float]]) -> pd.Series:
    if not new:
        return existing
    idx = pd.to_datetime([t for t, _ in new], unit="s", utc=True).tz_convert(TZ)
    s_new = pd.Series([k for _, k in new], index=idx, name="kWh")
    out = pd.concat([existing, s_new])
    return out[~out.index.duplicated(keep="last")].sort_index()


def save(s: pd.Series, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"epoch": to_epoch(s), "kWh": s.values.round(3)})
    df.to_csv(path, index=False)
