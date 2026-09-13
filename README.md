# glow-report

Daily electricity report for a house with a smart meter connected to the Bright app.
Pulls half-hourly readings from the Glowmarkt API each morning, keeps a running
history in `data/readings.csv`, publishes a dashboard to GitHub Pages and emails
a short summary with alerts when something looks off.

Runs entirely on GitHub Actions. No server, no cost on a public or private repo
within the free minutes.

## What it watches

- **Daily total** against the median of the last 28 complete days
- **Overnight average (00:00 to 06:00)** – flags a big jump, e.g. a heater left on
- **Quietest half hour** – the always-on floor; a rise here means a new permanent load
- **Shower window (06:00 to 09:00)** and **evening (16:00 to 23:00)**
- **Missing or zero data** – DCC/meter outages
- **Week-on-week** totals and a slow-creep check on overnight load

Windows and thresholds are constants at the top of `glowreport/analyse.py`.

## Setup (about 15 minutes)

1. **Create a repo** from these files and push it.
2. **Secrets** (Settings → Secrets and variables → Actions → *Secrets*):
   - `GLOW_USERNAME`, `GLOW_PASSWORD` – your Bright app login
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `EMAIL_TO`
     For Gmail: host `smtp.gmail.com`, port `587`, user = your address, pass = an
     [app password](https://myaccount.google.com/apppasswords) (needs 2-step verification on).
     `EMAIL_TO` can be a comma-separated list.
3. **Variables** (same page, *Variables* tab):
   - `SITE_NAME` – e.g. `12 Example Road`
   - `DASHBOARD_URL` – `https://<your-user>.github.io/<repo>/` (fill in after step 4)
4. **Pages**: Settings → Pages → Source: *GitHub Actions*.
5. **First run**: Actions → *Daily electricity report* → *Run workflow*, set
   `backfill_days` to e.g. `180`. This pulls history and builds the dashboard
   without emailing. Later runs are automatic at 07:30 UTC.

If you already have a CSV export from glowmarkt.com, drop it in as
`data/seed.csv`, run `python run.py --no-fetch --no-email --seed data/seed.csv`
locally, commit `data/readings.csv`, and skip the backfill.

## Running locally

```
pip install -r requirements.txt
export GLOW_USERNAME=... GLOW_PASSWORD=...
python run.py --backfill 30 --no-email      # first pull
python run.py --no-fetch --no-email          # rebuild dashboard from stored data
open docs/index.html
```

## Notes

- The Bright/DCC pipeline delivers yesterday's readings once a day, usually by
  early morning UK time. If the 07:30 run finds nothing, the next day's run
  re-fetches with a 3-day overlap, so gaps fill themselves.
- Readings are stored as UTC epoch seconds; all analysis is in Europe/London.
- Only `electricity.consumption` is pulled. To add gas, call
  `find_resource("gas.consumption")` in `run.py` and store it in a second file.
- The dashboard is a static HTML file with inline SVG, no JavaScript, so it
  works anywhere and is safe to leave public. Note that a public Pages site
  reveals when the house is empty; use a private repo with Pages enabled on a
  paid plan, or drop the Pages step and rely on the email, if that matters.
