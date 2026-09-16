#!/usr/bin/env python3
"""Fetch new readings, rebuild the dashboard, send the daily email.

Usage:
  python run.py                 # fetch + report + email (needs env vars)
  python run.py --no-fetch      # rebuild from data/readings.csv only
  python run.py --no-email      # skip sending
  python run.py --backfill 120  # first run: pull the last N days
  python run.py --seed file.csv # import a Glowmarkt web CSV export

Environment (set as GitHub secrets):
  GLOW_USERNAME, GLOW_PASSWORD          Bright app login
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO, EMAIL_FROM
  DASHBOARD_URL                         link used in the email
  SITE_NAME                             e.g. "12 Example Road" (optional)
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

from glowreport import analyse, render, store

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "readings.csv"
DOCS = ROOT / "docs" / "index.html"


def fetch(s, backfill_days: int | None):
    from glowreport.glow_api import GlowClient
    user, pw = os.environ.get("GLOW_USERNAME"), os.environ.get("GLOW_PASSWORD")
    if not (user and pw):
        sys.exit("GLOW_USERNAME / GLOW_PASSWORD not set")
    cli = GlowClient(user, pw)
    rid = cli.find_resource("electricity.consumption", os.environ.get("GLOW_RESOURCE"))
    cli.catchup(rid)
    today = dt.datetime.now(ZoneInfo(store.TZ)).date()
    if backfill_days:
        start = today - dt.timedelta(days=backfill_days)
    elif len(s):
        start = s.index.max().date() - dt.timedelta(days=7)  # re-check a week: DCC data fills in late
    else:
        start = today - dt.timedelta(days=30)
    new = cli.readings(rid, start, today)
    print(f"fetched {len(new)} readings from {start}")
    return store.merge(s, new)


def send_email(subject: str, body_html: str):
    host, port = os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587"))
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, os.environ["EMAIL_FROM"], os.environ["EMAIL_TO"]
    msg.attach(MIMEText(body_html, "html"))
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        smtp.sendmail(msg["From"], [a.strip() for a in msg["To"].split(",")], msg.as_string())
    print("email sent:", subject)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--backfill", type=int, metavar="DAYS")
    ap.add_argument("--seed", type=Path, help="import a Glowmarkt CSV export")
    ap.add_argument("--day", help="report a specific day, YYYY-MM-DD")
    a = ap.parse_args()

    s = store.load(DATA)
    seed_path = ROOT / "data" / "seed.csv"
    if a.seed is None and seed_path.exists() and DATA.exists() is False:
        a.seed = seed_path
    if a.seed:
        seed = store.load(a.seed)
        s = store.merge(s, list(zip(store.to_epoch(seed), seed.values.tolist())))
        print(f"seeded {len(seed)} readings")
    if not a.no_fetch:
        s = fetch(s, a.backfill)
    store.save(s, DATA)
    print(f"{len(s)} readings, {s.index.min():%Y-%m-%d} to {s.index.max():%Y-%m-%d %H:%M}")

    day = dt.date.fromisoformat(a.day) if a.day else None
    rep, df = analyse.build_report(s, day)
    site = os.environ.get("SITE_NAME", "House")
    DOCS.parent.mkdir(exist_ok=True)
    DOCS.write_text(render.dashboard_html(rep, df, s, site), encoding="utf-8")
    print("dashboard written:", DOCS)
    for al in rep.alerts:
        print(f"[{al.level}] {al.text}")

    if not a.no_email:
        subject, body = render.email_html(rep, os.environ.get("DASHBOARD_URL", "#"), site)
        if os.environ.get("SMTP_HOST"):
            send_email(subject, body)
        else:
            print("SMTP not configured; would send:", subject)


if __name__ == "__main__":
    main()
