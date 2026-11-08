"""
HoldOn: Gemini analysis.

Reads Alex's grip history from Tiger Data, asks Gemini to find the patterns,
and gets back:
  - a short, kind summary for Alex
  - a clinic report for his ALS team
  - recommended glove settings (clamped to safe limits in code below)
The result is saved in Tiger Data (table: reports) and in latest_report.json
so the website can show it.

Setup (Mac, in the same terminal where TIGER_URL is set):
    python3 -m pip install google-genai
    export GEMINI_API_KEY="your key from aistudio.google.com"
Run:
    python3 gemini_report.py
"""
import json
import os

import psycopg
from psycopg.types.json import Jsonb
from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# What the glove is set to right now (keep in sync with the Arduino code)
CURRENT_SETTINGS = {
    "trigger_bend_deg": 30,            # unaided bend needed before the glove takes over
    "afternoon_boost_start_hour": 14,  # when extra assistance starts
    "afternoon_assist_boost_pct": 0,   # extra assist in the afternoon
}

# Hard safety limits: whatever Gemini suggests is clamped to these
LIMITS = {
    "trigger_bend_deg": (10, 45),
    "afternoon_boost_start_hour": (10, 18),
    "afternoon_assist_boost_pct": (0, 30),
}

conn = psycopg.connect(os.environ["TIGER_URL"], autocommit=True)

# ---- 1. Pull the data from Tiger Data ----
daily = conn.execute("""
    SELECT (day AT TIME ZONE 'America/Toronto')::date,
           grips,
           round(avg_bend::numeric, 1),
           round(avg_assist::numeric, 1),
           round((avg_hold_ms / 1000)::numeric, 1),
           round(avg_time_to_grip_ms::numeric)
    FROM grips_daily
    WHERE hand = 'right' AND day > now() - INTERVAL '90 days'
    ORDER BY day
""").fetchall()

time_of_day = conn.execute("""
    SELECT CASE WHEN extract(hour FROM time AT TIME ZONE 'America/Toronto') < 12
                THEN 'morning' ELSE 'afternoon/evening' END AS part,
           count(*),
           round(avg(bend_deg)::numeric, 1),
           round(avg(servo_pos)::numeric, 1)
    FROM grips
    WHERE hand = 'right' AND time > now() - INTERVAL '14 days'
    GROUP BY part
""").fetchall()

any_sim, all_sim = conn.execute(
    "SELECT bool_or(simulated), bool_and(simulated) FROM grips "
    "WHERE time > now() - INTERVAL '90 days'"
).fetchone()

if not daily:
    raise SystemExit("No grip data found. Run simulate_history.py or grip_logger.py first.")

daily_table = "date | grips | avg_unaided_bend_deg | avg_assist_0_180 | avg_hold_s | avg_time_to_grip_ms\n"
daily_table += "\n".join(" | ".join(str(v) for v in row) for row in daily)
tod_table = "part_of_day | grips | avg_unaided_bend_deg | avg_assist_0_180\n"
tod_table += "\n".join(" | ".join(str(v) for v in row) for row in time_of_day)

data_note = (
    "ALL of this data is SIMULATED for a demo." if all_sim
    else "Some of this data is simulated; the rest is from the real glove." if any_sim
    else "This data is from the real glove."
)

# ---- 2. Ask Gemini ----
prompt = f"""
You are the analysis engine inside HoldOn, a grip-assist glove for a person with ALS.

Patient context: Alex, 47, high school biology teacher, limb-onset ALS, right hand most
affected (key pinch 3 kg, cannot sustain a pinch more than a few seconds), left hand
starting to weaken. Stronger in the morning, weaker in the afternoon. ALSFRS-R falling
about 0.6 points per month. Priorities: keep teaching, cook Sunday dinner for his family.

How the glove works: when Alex bends his fingers past trigger_bend_deg and touches an
object, a servo closes and holds the grip. "assist" (0-180) is how much the servo had to
do. Lower unaided bend and higher assist mean weaker hand.

{data_note}

Daily summary, right hand, last 90 days:
{daily_table}

Morning vs afternoon, last 14 days:
{tod_table}

Current glove settings: {json.dumps(CURRENT_SETTINGS)}
Safe ranges: {json.dumps(LIMITS)}

Return ONLY a JSON object with these keys:
- "summary_for_alex": 2-3 warm, plain sentences, second person, no jargon, no prognosis.
- "clinic_report": list of 3-5 short factual bullet strings with numbers (trend over
  the period, rate of change, morning vs afternoon gap, anything unusual).
- "flags": list of strings for things the clinic should look at (empty list if none).
- "recommended_settings": object with trigger_bend_deg, afternoon_boost_start_hour,
  afternoon_assist_boost_pct, each within the safe ranges.
- "reasoning": one or two sentences explaining the recommended settings.
Do not diagnose or give medical advice; describe the data.
"""

client = genai.Client()  # reads GEMINI_API_KEY
response = client.models.generate_content(
    model=MODEL,
    contents=prompt,
    config=types.GenerateContentConfig(response_mime_type="application/json"),
)
report = json.loads(response.text)

# ---- 3. Safety: clamp settings to hard limits ----
rec = report.get("recommended_settings", {})
for key, (lo, hi) in LIMITS.items():
    try:
        value = float(rec.get(key, CURRENT_SETTINGS[key]))
    except (TypeError, ValueError):
        value = CURRENT_SETTINGS[key]
    rec[key] = int(round(min(hi, max(lo, value))))
report["recommended_settings"] = rec
report["data_note"] = data_note
report["model"] = MODEL

# ---- 4. Save to Tiger Data and to a file for the website ----
conn.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        time   TIMESTAMPTZ NOT NULL DEFAULT now(),
        model  TEXT,
        report JSONB
    )
""")
conn.execute("INSERT INTO reports (model, report) VALUES (%s, %s)", (MODEL, Jsonb(report)))
with open("latest_report.json", "w") as f:
    json.dump(report, f, indent=2)

# ---- 5. Show it ----
print("\n=== For Alex ===")
print(report.get("summary_for_alex", ""))
print("\n=== Clinic report ===")
for line in report.get("clinic_report", []):
    print(" -", line)
if report.get("flags"):
    print("\n=== Flags ===")
    for line in report["flags"]:
        print(" !", line)
print("\n=== Recommended glove settings ===")
print(json.dumps(rec, indent=2))
print("Why:", report.get("reasoning", ""))
print(f"\n({data_note}) Saved to Tiger Data 'reports' table and latest_report.json")
