"""Render the dashboard (docs/index.html) and the email body from a Report."""
from __future__ import annotations

import datetime as dt
import html

import pandas as pd

from .analyse import Report, EVENING, MORNING, NIGHT

INK, PAPER, AMBER, TEAL, RED, MUTE = "#1F2A33", "#F3F5F2", "#D98E04", "#237A78", "#B8412A", "#7A858C"


def _delta(a: float, b: float | None, unit: str, nd: int = 1) -> str:
    if b is None or not b:
        return ""
    p = (a - b) / b * 100
    col = RED if p > 15 else (TEAL if p < -10 else MUTE)
    return f'<span style="color:{col}">{p:+.0f}% vs usual {b:.{nd}f} {unit}</span>'


# ---------- charts (inline SVG, no JS) ----------

def day_profile_svg(s: pd.Series, day: dt.date, base_profile: pd.Series | None, w=960, h=220) -> str:
    d = s[s.index.date == day] * 2
    if d.empty:
        return f'<p style="color:{MUTE}">No half-hourly data for this day.</p>'
    slots = [(day_dt := dt.datetime.combine(day, dt.time(hh // 2, 30 * (hh % 2)))) for hh in range(48)]
    vals = [float(d[(d.index.hour == t.hour) & (d.index.minute == t.minute)].iloc[0])
            if ((d.index.hour == t.hour) & (d.index.minute == t.minute)).any() else 0.0 for t in slots]
    top = max(max(vals), (base_profile.max() if base_profile is not None else 0), 1.0) * 1.1
    pad_l, pad_b, pad_t = 40, 26, 8
    cw, ch = w - pad_l - 8, h - pad_b - pad_t
    bw = cw / 48
    y = lambda v: pad_t + ch - v / top * ch
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Half-hourly power for the day" font-family="inherit" font-size="12">']
    for g in (1, 2, 3, 4):
        if g < top:
            out.append(f'<line x1="{pad_l}" x2="{w-8}" y1="{y(g):.1f}" y2="{y(g):.1f}" stroke="{INK}" stroke-opacity=".08"/>')
            out.append(f'<text x="{pad_l-6}" y="{y(g)+4:.1f}" text-anchor="end" fill="{MUTE}">{g} kW</text>')
    for i, v in enumerate(vals):
        hr = i // 2
        col = AMBER if MORNING[0] <= hr < MORNING[1] else (INK if NIGHT[0] <= hr < NIGHT[1] else TEAL)
        out.append(f'<rect x="{pad_l + i*bw + 1:.1f}" y="{y(v):.1f}" width="{bw-2:.1f}" height="{pad_t+ch-y(v):.1f}" fill="{col}" opacity=".85"/>')
    if base_profile is not None and len(base_profile) == 48:
        pts = " ".join(f"{pad_l + i*bw + bw/2:.1f},{y(float(v)):.1f}" for i, v in enumerate(base_profile.values))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{INK}" stroke-width="1.5" stroke-dasharray="4 3"/>')
    for hr in range(0, 24, 3):
        out.append(f'<text x="{pad_l + hr*2*bw:.1f}" y="{h-8}" fill="{MUTE}">{hr:02d}:00</text>')
    out.append("</svg>")
    return "".join(out)


def daily_bars_svg(df: pd.DataFrame, days: int = 56, w=960, h=200) -> str:
    d = df.tail(days)
    if d.empty:
        return ""
    top = max(d["total_kwh"].max(), 1) * 1.1
    pad_l, pad_b, pad_t = 40, 26, 8
    cw, ch = w - pad_l - 8, h - pad_b - pad_t
    bw = cw / len(d)
    y = lambda v: pad_t + ch - v / top * ch
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Daily kWh, last {days} days" font-family="inherit" font-size="12">']
    step = 10 if top < 60 else 20
    for g in range(step, int(top), step):
        out.append(f'<line x1="{pad_l}" x2="{w-8}" y1="{y(g):.1f}" y2="{y(g):.1f}" stroke="{INK}" stroke-opacity=".08"/>')
        out.append(f'<text x="{pad_l-6}" y="{y(g)+4:.1f}" text-anchor="end" fill="{MUTE}">{g}</text>')
    for i, (day, row) in enumerate(d.iterrows()):
        col = TEAL if row["complete"] else MUTE
        if day.weekday() >= 5:
            col = "#4F9E9B" if row["complete"] else MUTE
        out.append(f'<rect x="{pad_l + i*bw + 1:.1f}" y="{y(row["total_kwh"]):.1f}" width="{max(bw-2,1):.1f}" '
                   f'height="{pad_t+ch-y(row["total_kwh"]):.1f}" fill="{col}"><title>{day:%a %d %b}: {row["total_kwh"]:.1f} kWh</title></rect>')
    # rolling median
    med = d["total_kwh"].where(d["complete"]).rolling(7, min_periods=3).median()
    pts = " ".join(f"{pad_l + i*bw + bw/2:.1f},{y(v):.1f}" for i, v in enumerate(med.values) if pd.notna(v))
    out.append(f'<polyline points="{pts}" fill="none" stroke="{INK}" stroke-width="1.5"/>')
    for i, day in enumerate(d.index):
        if day.weekday() == 0:
            out.append(f'<text x="{pad_l + i*bw:.1f}" y="{h-8}" fill="{MUTE}">{day:%d %b}</text>')
    out.append("</svg>")
    return "".join(out)


def _base_profile(s: pd.Series, day: dt.date, n: int = 28) -> pd.Series | None:
    hist = s[(s.index.date < day) & (s.index.date >= day - dt.timedelta(days=n))] * 2
    if hist.empty:
        return None
    return hist.groupby([hist.index.hour, hist.index.minute]).median()


# ---------- pages ----------

CSS = f"""
:root{{--ink:{INK};--paper:{PAPER};--amber:{AMBER};--teal:{TEAL};--red:{RED};--mute:{MUTE}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 "IBM Plex Sans",system-ui,sans-serif}}
main{{max-width:960px;margin:0 auto;padding:40px 20px 60px}}
h1{{font-weight:500;font-size:22px;margin:0 0 4px}}
h2{{font-weight:500;font-size:17px;margin:40px 0 10px}}
.sub{{color:var(--mute);margin:0 0 28px}}
.big{{font-size:64px;font-weight:300;line-height:1;letter-spacing:-.02em;margin:0}}
.big small{{font-size:22px;color:var(--mute);margin-left:6px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:24px 32px;margin:24px 0}}
.stat b{{display:block;font-size:28px;font-weight:400}}
.stat span,.stat i{{display:block;font-style:normal;font-size:14px}}
.stat i{{color:var(--mute)}}
.alert{{border-left:3px solid var(--red);padding:6px 14px;margin:8px 0;background:#fff}}
.alert.info{{border-color:var(--amber)}}
.ok{{color:var(--teal)}}
.legend{{font-size:13px;color:var(--mute)}}
.legend i{{display:inline-block;width:10px;height:10px;margin:0 4px 0 12px;vertical-align:middle;font-style:normal}}
table{{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}}
th,td{{text-align:right;padding:6px 8px;border-bottom:1px solid #dfe3e0}}
th:first-child,td:first-child{{text-align:left}}
tr.incomplete td{{color:var(--mute)}}
footer{{margin-top:48px;color:var(--mute);font-size:13px}}
@media (max-width:600px){{.big{{font-size:48px}}main{{padding:24px 14px}}}}
"""


def _alerts_html(rep: Report) -> str:
    if not rep.alerts:
        return '<p class="ok">Nothing unusual. Overnight, shower window and daily total all within the normal range.</p>'
    return "".join(f'<div class="alert {a.level}">{html.escape(a.text)}</div>' for a in rep.alerts)


def _stats_html(rep: Report) -> str:
    m, b = rep.metrics, rep.base
    if m is None:
        return ""
    bb = (lambda k: b[k] if b is not None else None)
    return f"""
<div class="grid">
 <div class="stat"><b>{m['night_kw']:.2f}<small style="font-size:14px;color:var(--mute)"> kW</small></b><span>Overnight average, {NIGHT[0]:02d}:00 to {NIGHT[1]:02d}:00</span><i>{_delta(m['night_kw'], bb('night_kw'), 'kW', 2)}</i></div>
 <div class="stat"><b>{m['floor_kw']:.2f}<small style="font-size:14px;color:var(--mute)"> kW</small></b><span>Quietest half hour</span><i>{_delta(m['floor_kw'], bb('floor_kw'), 'kW', 2)}</i></div>
 <div class="stat"><b>{m['morning_kwh']:.1f}<small style="font-size:14px;color:var(--mute)"> kWh</small></b><span>Shower window, {MORNING[0]:02d}:00 to {MORNING[1]:02d}:00</span><i>{_delta(m['morning_kwh'], bb('morning_kwh'), 'kWh')}</i></div>
 <div class="stat"><b>{m['evening_kwh']:.1f}<small style="font-size:14px;color:var(--mute)"> kWh</small></b><span>Evening, {EVENING[0]:02d}:00 to {EVENING[1]:02d}:00</span><i>{_delta(m['evening_kwh'], bb('evening_kwh'), 'kWh')}</i></div>
 <div class="stat"><b>{m['peak_kw']:.1f}<small style="font-size:14px;color:var(--mute)"> kW</small></b><span>Highest half hour</span><i>{_delta(m['peak_kw'], bb('peak_kw'), 'kW')}</i></div>
</div>"""


def _week_html(rep: Report) -> str:
    w = rep.week
    if not w:
        return ""
    def line(label, a, b, unit, nd=1):
        p = (a - b) / b * 100 if b else 0
        return f"<tr><td>{label}</td><td>{a:.{nd}f} {unit}</td><td>{b:.{nd}f} {unit}</td><td>{p:+.0f}%</td></tr>"
    return f"""<table><thead><tr><th>Last 7 complete days ({w['start']:%d %b} to {w['end']:%d %b})</th><th>This week</th><th>Week before</th><th></th></tr></thead><tbody>
{line('Total', w['this_total'], w['prev_total'], 'kWh')}
{line('Overnight average', w['this_night'], w['prev_night'], 'kW', 2)}
{line('Shower window per day', w['this_morning'], w['prev_morning'], 'kWh')}
</tbody></table>"""


def _table_html(df: pd.DataFrame, n: int = 14) -> str:
    rows = []
    for day, r in df.tail(n)[::-1].iterrows():
        cls = "" if r["complete"] else ' class="incomplete"'
        rows.append(f"<tr{cls}><td>{day:%a %d %b}</td><td>{r['total_kwh']:.1f}</td><td>{r['night_kw']:.2f}</td>"
                    f"<td>{r['floor_kw']:.2f}</td><td>{r['morning_kwh']:.1f}</td><td>{r['evening_kwh']:.1f}</td><td>{r['peak_kw']:.1f}</td></tr>")
    return ("<table><thead><tr><th>Day</th><th>Total kWh</th><th>Night kW</th><th>Floor kW</th><th>6-9am kWh</th>"
            "<th>Evening kWh</th><th>Peak kW</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def dashboard_html(rep: Report, df: pd.DataFrame, s: pd.Series, site_name: str) -> str:
    m = rep.metrics
    total = f'<p class="big">{m["total_kwh"]:.1f}<small>kWh</small></p>' if m is not None else '<p class="big">—</p>'
    sub = f'{rep.day:%A %d %B %Y}. ' + (_delta(m["total_kwh"], rep.base["total_kwh"] if rep.base is not None else None, "kWh") if m is not None else "")
    now = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%d %b %Y %H:%M %Z")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(site_name)} electricity</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><main>
<h1>{html.escape(site_name)} electricity</h1>
<p class="sub">Half-hourly smart meter data via Bright. Updated {now}.</p>
{total}<p class="sub">{sub}</p>
{day_profile_svg(s, rep.day, _base_profile(s, rep.day))}
<p class="legend">Power through the day. <i style="background:{INK}"></i>overnight <i style="background:{AMBER}"></i>shower window <i style="background:{TEAL}"></i>rest of day. Dashed line is the usual profile over the last 4 weeks.</p>
{_stats_html(rep)}
<h2>Anything to look at?</h2>
{_alerts_html(rep)}
<h2>Week on week</h2>
{_week_html(rep)}
<h2>Last 8 weeks</h2>
{daily_bars_svg(df)}
<p class="legend">Daily kWh; lighter bars are weekends, grey bars are incomplete days. Solid line is the 7-day median.</p>
<h2>Last 14 days</h2>
{_table_html(df)}
<footer>Overnight is the average draw {NIGHT[0]:02d}:00 to {NIGHT[1]:02d}:00. Floor is the single quietest half hour: what the house pulls with everything idle. "Usual" is the median of the previous 28 complete days.</footer>
</main></body></html>"""


def email_html(rep: Report, dashboard_url: str, site_name: str) -> tuple[str, str]:
    """Returns (subject, html body). Plain HTML only: email clients strip SVG and CSS."""
    m, b = rep.metrics, rep.base
    warn = [a for a in rep.alerts if a.level == "warn"]
    flag = f"{len(warn)} alert{'s' if len(warn) > 1 else ''}: " if warn else ""
    subject = f"{flag}{site_name} used {m['total_kwh']:.1f} kWh on {rep.day:%a %d %b}" if m is not None else f"{site_name}: no data for {rep.day:%a %d %b}"
    def row(label, val, base, unit, nd=1):
        p = f"{(val - base) / base * 100:+.0f}%" if base else ""
        return f"<tr><td style='padding:4px 12px 4px 0'>{label}</td><td style='padding:4px 12px;text-align:right'><b>{val:.{nd}f} {unit}</b></td><td style='padding:4px 0;color:#7A858C'>{p}</td></tr>"
    body = [f"<div style='font-family:system-ui,sans-serif;color:#1F2A33;max-width:560px'>"]
    if rep.alerts:
        body += [f"<p style='margin:0 0 4px;padding:6px 12px;border-left:3px solid {'#B8412A' if a.level=='warn' else '#D98E04'};background:#fff'>{html.escape(a.text)}</p>" for a in rep.alerts]
    else:
        body.append("<p style='color:#237A78'>Nothing unusual yesterday.</p>")
    if m is not None:
        bb = (lambda k: b[k] if b is not None else None)
        body.append("<table style='border-collapse:collapse;margin:16px 0'>")
        body.append(row("Total", m["total_kwh"], bb("total_kwh"), "kWh"))
        body.append(row("Overnight average", m["night_kw"], bb("night_kw"), "kW", 2))
        body.append(row("Quietest half hour", m["floor_kw"], bb("floor_kw"), "kW", 2))
        body.append(row("Shower window (6-9am)", m["morning_kwh"], bb("morning_kwh"), "kWh"))
        body.append(row("Evening (4-11pm)", m["evening_kwh"], bb("evening_kwh"), "kWh"))
        body.append("</table>")
    if rep.week:
        w = rep.week
        p = (w["this_total"] - w["prev_total"]) / w["prev_total"] * 100
        body.append(f"<p>Last 7 days: {w['this_total']:.0f} kWh, {p:+.0f}% on the week before.</p>")
    body.append(f"<p><a href='{dashboard_url}'>Open the dashboard</a></p></div>")
    return subject, "".join(body)
