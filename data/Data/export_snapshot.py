"""
HoldOn: export a snapshot of Tiger Data + the latest Gemini report into one file,
holdon_data.json, for the public website to draw its charts from.

The website reads this file. It never needs the database password or Gemini key.

    python3 export_snapshot.py
Needs TIGER_URL set. Re-run it whenever you want the website's data refreshed.
"""
import datetime as dt
import json
import os
from decimal import Decimal

import psycopg

conn = psycopg.connect(os.environ["TIGER_URL"], autocommit=True)


def rows(sql):
    cur = conn.execute(sql)
    cols = [d.name for d in cur.description]
    out = []
    for r in cur.fetchall():
        item = {}
        for c, v in zip(cols, r):
            if isinstance(v, Decimal):
                v = float(v)
            elif isinstance(v, (dt.date, dt.datetime)):
                v = v.isoformat()
            item[c] = v
        out.append(item)
    return out


daily = rows("""
    SELECT (day AT TIME ZONE 'America/Toronto')::date AS date,
           grips,
           round(avg_bend::numeric, 1)                AS own_bend_deg,
           round(avg_assist::numeric, 1)              AS glove_assist,
           round((avg_hold_ms / 1000)::numeric, 1)    AS hold_s,
           round(avg_time_to_grip_ms::numeric)        AS time_to_grip_ms
    FROM grips_daily WHERE hand = 'right' ORDER BY day
""")

by_hour = rows("""
    SELECT extract(hour FROM time AT TIME ZONE 'America/Toronto')::int AS hour,
           round(avg(bend_deg)::numeric, 1)  AS own_bend_deg,
           round(avg(servo_pos)::numeric, 1) AS glove_assist
    FROM grips
    WHERE hand = 'right' AND time > now() - INTERVAL '14 days'
    GROUP BY hour ORDER BY hour
""")

recent = rows("""
    SELECT time AT TIME ZONE 'America/Toronto' AS time,
           bend_deg AS own_bend_deg, servo_pos AS glove_assist,
           time_to_grip_ms, hold_ms
    FROM grips ORDER BY time DESC LIMIT 10
""")

totals = rows("""
    SELECT count(*) AS total, count(*) FILTER (WHERE simulated) AS simulated FROM grips
""")[0]

report = None
if conn.execute("SELECT to_regclass('reports') IS NOT NULL").fetchone()[0]:
    r = conn.execute("SELECT time, report FROM reports ORDER BY time DESC LIMIT 1").fetchone()
    if r:
        report = dict(r[1])
        report["generated_at"] = r[0].isoformat()

snapshot = {
    "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "data_note": ("Simulated from Alex's case file for the demo."
                  if totals["total"] and totals["simulated"] == totals["total"]
                  else "Includes data from the glove."),
    "totals": totals,
    "daily": daily,
    "by_hour": by_hour,
    "recent_grips": recent,
    "gemini_report": report,
}

with open("holdon_data.json", "w") as f:
    json.dump(snapshot, f, indent=2)

print(f"Saved holdon_data.json: {len(daily)} days, {len(by_hour)} hours, "
      f"{len(recent)} recent grips, Gemini report: {'yes' if report else 'none yet'}")
if not report:
    print("Tip: run python3 gemini_report.py first, then export again to include the report.")
