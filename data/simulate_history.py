"""
HoldOn: generate 90 days of SIMULATED grip history so the dashboard and Gemini have
something to show. Every row is marked simulated = true. Say so in the pitch.

Modelled on Alex's file (illustrative numbers, not real measurements):
  - steady, roughly linear decline (his ALSFRS-R falls about 0.6 points a month)
  - stronger in the morning, weaker by late afternoon
  - weaker unaided bend -> glove assists more and grips take longer to start

Run once:
    pip install "psycopg[binary]"
    export TIGER_URL="postgres://..."
    python simulate_history.py
To wipe and redo:  DELETE FROM grips WHERE simulated;
"""
import datetime as dt
import os
import random
from zoneinfo import ZoneInfo

import psycopg

TZ = ZoneInfo("America/Toronto")
DAYS = 90
random.seed(47)  # same data every run

today = dt.datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
rows = []
for d in range(DAYS, 0, -1):
    day = today - dt.timedelta(days=d)
    progress = (DAYS - d) / DAYS                 # 0 at start, 1 at today
    base_bend = 55 - 15 * progress               # unaided bend: 55 deg -> 40 deg
    for _ in range(random.randint(25, 50)):      # grips per day
        hour = random.uniform(7, 21.5)
        t = day + dt.timedelta(hours=hour)
        fatigue = max(0.0, min(1.0, (hour - 12) / 6)) * 0.25   # up to 25% weaker by 6 pm
        bend = max(5.0, random.gauss(base_bend * (1 - fatigue), 3))
        assist = int(min(180, max(0, 180 * (1 - bend / 90) + random.gauss(0, 5))))
        ttg = max(150, int(400 + (55 - bend) * 25 + random.gauss(0, 80)))
        hold = int(random.uniform(4000, 45000))
        rows.append((t, round(bend, 1), ttg, assist, hold))

with psycopg.connect(os.environ["TIGER_URL"], autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO grips (time, bend_deg, time_to_grip_ms, servo_pos, hold_ms, simulated) "
            "VALUES (%s, %s, %s, %s, %s, true)",
            rows,
        )
    conn.execute("CALL refresh_continuous_aggregate('grips_hourly', NULL, NULL)")
    conn.execute("CALL refresh_continuous_aggregate('grips_daily', NULL, NULL)")

print(f"Inserted {len(rows)} simulated grips over {DAYS} days.")
