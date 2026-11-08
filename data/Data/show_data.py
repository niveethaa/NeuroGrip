"""
HoldOn: print Alex's grip data from Tiger Data straight into the terminal.

    python3 show_data.py
Needs TIGER_URL set.
"""
import os

import psycopg

conn = psycopg.connect(os.environ["TIGER_URL"], autocommit=True)


def table(title, sql, headers):
    rows = conn.execute(sql).fetchall()
    print(f"\n=== {title} ===")
    widths = [max(len(h), *(len(str(r[i])) for r in rows)) if rows else len(h)
              for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    if not rows:
        print("(no data)")


table(
    "Daily summary, right hand (from the grips_daily continuous aggregate)",
    """SELECT (day AT TIME ZONE 'America/Toronto')::date, grips,
              round(avg_bend::numeric, 1), round(avg_assist::numeric, 1),
              round((avg_hold_ms / 1000)::numeric, 1), round(avg_time_to_grip_ms::numeric)
       FROM grips_daily WHERE hand = 'right' ORDER BY day""",
    ["date", "grips", "own bend (deg)", "glove assist", "hold (s)", "time to grip (ms)"],
)

table(
    "Morning vs afternoon, last 14 days",
    """SELECT CASE WHEN extract(hour FROM time AT TIME ZONE 'America/Toronto') < 12
                   THEN 'morning' ELSE 'afternoon/evening' END AS part,
              count(*), round(avg(bend_deg)::numeric, 1), round(avg(servo_pos)::numeric, 1)
       FROM grips WHERE hand = 'right' AND time > now() - INTERVAL '14 days'
       GROUP BY part ORDER BY part DESC""",
    ["part of day", "grips", "own bend (deg)", "glove assist"],
)

table(
    "Last 10 raw grips",
    """SELECT to_char(time AT TIME ZONE 'America/Toronto', 'Mon DD HH24:MI'),
              bend_deg, time_to_grip_ms, servo_pos, hold_ms, simulated
       FROM grips ORDER BY time DESC LIMIT 10""",
    ["time", "own bend", "time to grip", "assist", "hold (ms)", "simulated"],
)

total, sim = conn.execute("SELECT count(*), count(*) FILTER (WHERE simulated) FROM grips").fetchone()
print(f"\nTotal grips stored: {total}  ({sim} simulated, {total - sim} from the real glove)")
