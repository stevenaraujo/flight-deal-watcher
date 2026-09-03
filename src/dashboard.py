"""
Erzeugt ein statisches, responsives HTML-Dashboard aus den in SQLite
gespeicherten Daten. Keine Secrets landen im Output - nur Preisdaten,
Flugzeiten und öffentliche Buchungslinks.

Gedacht für GitHub Pages (docs/index.html), kostenlos & wartungsarm.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import List

from . import config, storage

TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Flight Deal Watcher – ZRH → Rio</title>
<style>
  :root {{ --bg:#0f1115; --card:#181b22; --text:#e8eaed; --muted:#9aa0a6; --accent:#4fd1a5; --warn:#f4c150; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,Segoe UI,Roboto,sans-serif; padding:16px; }}
  h1 {{ font-size:1.3rem; margin-bottom:4px; }}
  .sub {{ color:var(--muted); font-size:0.85rem; margin-bottom:20px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; }}
  .card {{ background:var(--card); border-radius:12px; padding:16px; }}
  .card h2 {{ font-size:0.95rem; color:var(--muted); margin:0 0 10px; text-transform:uppercase; letter-spacing:.04em; }}
  .price {{ font-size:2rem; font-weight:700; color:var(--accent); }}
  .row {{ display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #262a33; font-size:0.9rem; }}
  .row:last-child {{ border-bottom:none; }}
  .label {{ color:var(--muted); }}
  table {{ width:100%; border-collapse:collapse; font-size:0.85rem; }}
  th,td {{ text-align:left; padding:6px 4px; border-bottom:1px solid #262a33; }}
  th {{ color:var(--muted); font-weight:500; }}
  a {{ color:var(--accent); text-decoration:none; }}
  .atl {{ color:var(--warn); font-weight:600; }}
  .footer {{ margin-top:24px; color:var(--muted); font-size:0.75rem; }}
  canvas {{ max-width:100%; }}
</style>
</head>
<body>
<h1>✈️ Flight Deal Watcher – Zürich → Rio de Janeiro</h1>
<div class="sub">Premium Economy · 2 Erwachsene · aktualisiert {generated_at}</div>

<div class="grid">
  <div class="card">
    <h2>Aktuell günstigster Flug</h2>
    {current_best}
  </div>

  <div class="card">
    <h2>All-Time-Low</h2>
    {atl_block}
  </div>

  <div class="card">
    <h2>Letzte Suche</h2>
    {last_run_block}
  </div>
</div>

<div class="card" style="margin-top:14px;">
  <h2>Top Deals</h2>
  <table>
    <tr><th>Preis p.P.</th><th>Hinflug</th><th>Rückflug</th><th>Airline</th><th>Umstiege</th><th>Gepäck</th><th>Link</th></tr>
    {top_deals_rows}
  </table>
</div>

<div class="card" style="margin-top:14px;">
  <h2>Preisverlauf (Preis pro Person über Zeit)</h2>
  <canvas id="priceChart" height="90"></canvas>
</div>

<div class="footer">
  Suchkriterien: ZRH → GIG · max. CHF {max_price}/Person · max. 17h · max. 1 Umstieg · Datenquelle: SerpApi/Google Flights.
  Diese Seite bucht nichts automatisch – Buchung erfolgt manuell über den jeweiligen Link.
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"></script>
<script>
  const labels = {chart_labels};
  const data = {chart_data};
  new Chart(document.getElementById('priceChart'), {{
    type: 'line',
    data: {{ labels, datasets: [{{ label: 'CHF pro Person', data, borderColor: '#4fd1a5', tension: 0.25, pointRadius: 2 }}] }},
    options: {{ responsive: true, plugins: {{ legend: {{ display:false }} }},
      scales: {{ x: {{ ticks: {{ color:'#9aa0a6' }} }}, y: {{ ticks: {{ color:'#9aa0a6' }} }} }} }}
  }});
</script>
</body>
</html>
"""


def _row_block(rows: List[tuple]) -> str:
    return "".join(f'<div class="row"><span class="label">{k}</span><span>{v}</span></div>' for k, v in rows)


def generate_dashboard() -> str:
    top_deals = storage.get_top_deals(config.TOP_DEALS_COUNT)
    atl = storage.get_all_time_low_details()
    runs = storage.get_recent_runs(1)
    history = storage.get_price_history_series()

    if top_deals:
        best = top_deals[0]
        current_best = _row_block([
            ("Preis p.P.", f'<span class="price">CHF {best["price_per_person"]:,.0f}</span>'),
            ("Gesamtpreis", f'CHF {best["price_total"]:,.0f}'),
            ("Airline", best["airline"] or "–"),
            ("Hinflug", best["outbound_date"]),
            ("Rückflug", best["return_date"]),
            ("Umstiege", best["stops"]),
            ("Reisezeit", f'{best["duration_minutes"]//60}h {best["duration_minutes"]%60}min'),
            ("Gepäck", "inkludiert" if best["baggage_included"] else ("Zusatzkosten" if best["baggage_verified"] else "nicht verifiziert")),
            ("Link", f'<a href="{best["booking_link"]}" target="_blank">öffnen</a>' if best["booking_link"] else "–"),
        ])
    else:
        current_best = '<div class="row"><span class="label">Noch keine Daten</span></div>'

    if atl:
        atl_block = _row_block([
            ("Preis p.P.", f'<span class="atl">CHF {atl["price_per_person"]:,.0f}</span>'),
            ("Beobachtet am", atl["checked_at"][:16].replace("T", " ")),
            ("Hinflug", atl["outbound_date"]),
            ("Rückflug", atl["return_date"]),
            ("Airline", atl["airline"] or "–"),
        ])
    else:
        atl_block = '<div class="row"><span class="label">Noch keine Daten</span></div>'

    if runs:
        r = runs[0]
        last_run_block = _row_block([
            ("Zeitpunkt", r["started_at"][:16].replace("T", " ")),
            ("Status", r["status"]),
            ("API", "SerpApi/Google Flights"),
            ("Geprüfte Kombis", r["combinations_checked"]),
            ("Ergebnisse", r["offers_found"]),
        ])
    else:
        last_run_block = '<div class="row"><span class="label">Noch kein Lauf</span></div>'

    rows_html = "".join(
        f"<tr><td>CHF {d['price_per_person']:,.0f}</td><td>{d['outbound_date']}</td>"
        f"<td>{d['return_date']}</td><td>{d['airline'] or '–'}</td><td>{d['stops']}</td>"
        f"<td>{'inkl.' if d['baggage_included'] else ('kostenpfl.' if d['baggage_verified'] else 'unklar')}</td>"
        f"<td>{'<a href=\"' + d['booking_link'] + '\" target=\"_blank\">öffnen</a>' if d['booking_link'] else '–'}</td></tr>"
        for d in top_deals
    ) or "<tr><td colspan='7'>Noch keine Daten</td></tr>"

    chart_labels = json.dumps([h["checked_at"][:10] for h in history])
    chart_data = json.dumps([h["price_per_person"] for h in history])

    html = TEMPLATE.format(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        current_best=current_best,
        atl_block=atl_block,
        last_run_block=last_run_block,
        top_deals_rows=rows_html,
        max_price=config.MAX_PRICE_PER_PERSON,
        chart_labels=chart_labels,
        chart_data=chart_data,
    )
    return html


def write_dashboard() -> None:
    html = generate_dashboard()
    os.makedirs(os.path.dirname(config.DASHBOARD_OUTPUT_PATH) or ".", exist_ok=True)
    with open(config.DASHBOARD_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
