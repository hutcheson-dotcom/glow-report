"""Turn a half-hourly kWh series into daily metrics, baselines and alerts."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

# Windows are local time, hour-inclusive start, exclusive end.
NIGHT = (0, 6)        # true idle: what the house draws when nobody's up
MORNING = (6, 9)      # electric-shower rush
EVENING = (16, 23)    # cooking, TVs, heaters

BASELINE_DAYS = 28
MIN_READINGS = 44     # of 48 - treat anything less as an incomplete day


def _window(s: pd.Series, lo: int, hi: int) -> pd.Series:
    return s[(s.index.hour >= lo) & (s.index.hour < hi)]


def daily_metrics(s: pd.Series) -> pd.DataFrame:
    """One row per local calendar day."""
    kw = s * 2  # half-hour kWh -> average kW over that half hour
    g = s.groupby(s.index.date)
    df = pd.DataFrame({
        "total_kwh": g.sum(),
        "readings": g.count(),
        "zeros": g.apply(lambda x: int((x == 0).sum())),
        "floor_kw": kw[kw > 0].groupby(kw[kw > 0].index.date).min(),
        "night_kw": _window(kw, *NIGHT).groupby(_window(kw, *NIGHT).index.date).mean(),
        "morning_kwh": _window(s, *MORNING).groupby(_window(s, *MORNING).index.date).sum(),
        "evening_kwh": _window(s, *EVENING).groupby(_window(s, *EVENING).index.date).sum(),
        "peak_kw": kw.groupby(kw.index.date).max(),
    })
    df.index = pd.to_datetime(df.index)
    df.index.name = "day"
    df = df.fillna({"floor_kw": 0, "night_kw": 0, "morning_kwh": 0, "evening_kwh": 0, "peak_kw": 0})
    df["complete"] = (df["readings"] >= MIN_READINGS) & (df["zeros"] < 6)
    return df


def baseline(df: pd.DataFrame, upto: dt.date) -> pd.Series | None:
    """Median of the previous BASELINE_DAYS complete days before `upto`."""
    hist = df[(df.index.date < upto) & df["complete"]].tail(BASELINE_DAYS)
    if len(hist) < 7:
        return None
    return hist[["total_kwh", "floor_kw", "night_kw", "morning_kwh", "evening_kwh", "peak_kw"]].median()


@dataclass
class Alert:
    level: str   # "warn" | "info"
    text: str


@dataclass
class Report:
    day: dt.date
    metrics: pd.Series | None
    base: pd.Series | None
    alerts: list[Alert] = field(default_factory=list)
    week: dict = field(default_factory=dict)


def _pct(a: float, b: float) -> float:
    return (a - b) / b * 100 if b else 0.0


def check_alerts(m: pd.Series | None, b: pd.Series | None, day: dt.date, df: pd.DataFrame) -> list[Alert]:
    alerts: list[Alert] = []
    if m is None:
        alerts.append(Alert("warn", f"No readings for {day:%a %d %b}. Hildebrand may not have pulled yesterday's data yet."))
        return alerts
    if not m["complete"]:
        alerts.append(Alert("warn", f"Incomplete day: {int(m['readings'])}/48 readings, {int(m['zeros'])} zeros. Possible meter/DCC outage."))
    if b is None:
        alerts.append(Alert("info", "Not enough history for a baseline yet (needs 7 complete days)."))
        return alerts
    if m["night_kw"] > b["night_kw"] * 1.6 and m["night_kw"] - b["night_kw"] > 0.3:
        alerts.append(Alert("warn", f"Overnight load {m['night_kw']:.2f} kW vs usual {b['night_kw']:.2f} kW. "
                                    "Something ran all night: plug-in heater, dryer, or a fault."))
    if m["floor_kw"] > b["floor_kw"] * 1.5 and m["floor_kw"] - b["floor_kw"] > 0.15:
        alerts.append(Alert("warn", f"Idle floor {m['floor_kw']:.2f} kW vs usual {b['floor_kw']:.2f} kW. "
                                    "A new always-on load appeared."))
    if m["total_kwh"] > b["total_kwh"] * 1.3:
        alerts.append(Alert("warn", f"Daily total {m['total_kwh']:.1f} kWh, {_pct(m['total_kwh'], b['total_kwh']):+.0f}% vs usual."))
    if m["morning_kwh"] > b["morning_kwh"] * 1.5:
        alerts.append(Alert("info", f"Heavy shower window: {m['morning_kwh']:.1f} kWh between 6 and 9am."))
    # Slow creep: last 7 complete days vs previous 21.
    comp = df[df["complete"] & (df.index.date <= day)]
    if len(comp) >= 28:
        recent, prior = comp.tail(7)["night_kw"].mean(), comp.tail(28).head(21)["night_kw"].mean()
        if recent > prior * 1.25 and recent - prior > 0.1:
            alerts.append(Alert("info", f"Overnight load trending up: {recent:.2f} kW this week vs {prior:.2f} kW over the prior 3 weeks."))
    return alerts


def build_report(s: pd.Series, day: dt.date | None = None) -> tuple[Report, pd.DataFrame]:
    df = daily_metrics(s)
    if day is None:
        # Most recent complete day, looking back up to 4 days; DCC data arrives late.
        yesterday = (dt.datetime.now(tz=s.index.tz) - dt.timedelta(days=1)).date() if len(s) else dt.date.today()
        day = yesterday
        for back in range(4):
            cand = yesterday - dt.timedelta(days=back)
            if pd.Timestamp(cand) in df.index and df.loc[pd.Timestamp(cand), "complete"]:
                day = cand
                break
    m = df.loc[pd.Timestamp(day)] if pd.Timestamp(day) in df.index else None
    b = baseline(df, day)
    rep = Report(day=day, metrics=m, base=b, alerts=check_alerts(m, b, day, df))

    comp = df[df["complete"] & (df.index.date <= day)]
    if len(comp) >= 14:
        this, prev = comp.tail(7), comp.tail(14).head(7)
        rep.week = {
            "this_total": this["total_kwh"].sum(), "prev_total": prev["total_kwh"].sum(),
            "this_night": this["night_kw"].mean(), "prev_night": prev["night_kw"].mean(),
            "this_morning": this["morning_kwh"].mean(), "prev_morning": prev["morning_kwh"].mean(),
            "start": this.index[0].date(), "end": this.index[-1].date(),
        }
    return rep, df
