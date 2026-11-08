"""
HoldOn dashboard: Tiger Data + Gemini, live in the browser.

Run (Mac, same terminal where TIGER_URL and GEMINI_API_KEY are set):
    python3 -m pip install streamlit pandas
    python3 -m streamlit run app.py
"""
import os
import random
import subprocess
import sys

import pandas as pd
import psycopg
import streamlit as st

st.set_page_config(page_title="HoldOn", page_icon="✋", layout="wide")


@st.cache_resource
def get_conn():
    return psycopg.connect(os.environ["TIGER_URL"], autocommit=True)


def q(sql, params=None):
    """Run a query and return a DataFrame."""
    conn = get_conn()
    if conn.closed:
        st.cache_resource.clear()
        conn = get_conn()
    cur = conn.execute(sql, params)
    cols = [d.name for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


# ---------------- Data ----------------
daily = q("""
    SELECT (day AT TIME ZONE 'America/Toronto')::date AS day,
           avg_bend::float   AS "Unaided bend (deg)",
           avg_assist::float AS "Glove assist (0-180)",
           grips
    FROM grips_daily WHERE hand = 'right' ORDER BY day
""")

hourly = q("""
    SELECT extract(hour FROM time AT TIME ZONE 'America/Toronto')::int AS hour,
           avg(bend_deg)::float  AS "Unaided bend (deg)",
           avg(servo_pos)::float AS "Glove assist (0-180)"
    FROM grips
    WHERE hand = 'right' AND time > now() - INTERVAL '14 days'
    GROUP BY hour ORDER BY hour
""")

sim = q("SELECT bool_or(simulated) AS any_sim, bool_and(simulated) AS all_sim FROM grips")
all_sim = bool(sim["all_sim"].iloc[0]) if len(sim) else False


def latest_report():
    exists = q("SELECT to_regclass('reports') IS NOT NULL AS ok")["ok"].iloc[0]
    if not exists:
        return None
    r = q("SELECT time, report FROM reports ORDER BY time DESC LIMIT 1")
    return None if r.empty else (r["time"].iloc[0], r["report"].iloc[0])


# ---------------- Header ----------------
st.title("✋ HoldOn")
st.caption("A grip-assist glove that learns Alex's hand. Every grip streams into Tiger Data; "
           "Gemini reads the trends and adapts the glove.")
if all_sim:
    st.info("Demo data: the history below is simulated from Alex's case file. "
            "Live grips from the glove land in the same table.")

if daily.empty:
    st.warning("No data yet. Run simulate_history.py first.")
    st.stop()

# ---------------- Headline numbers ----------------
first, last = daily.iloc[:7], daily.iloc[-7:]
c1, c2, c3 = st.columns(3)
b0, b1 = first["Unaided bend (deg)"].mean(), last["Unaided bend (deg)"].mean()
a0, a1 = first["Glove assist (0-180)"].mean(), last["Glove assist (0-180)"].mean()
c1.metric("Unaided finger bend (last 7 days)", f"{b1:.1f}°", f"{b1 - b0:+.1f}° vs first week")
c2.metric("Glove assistance (last 7 days)", f"{a1:.0f}", f"{a1 - a0:+.0f} vs first week",
          delta_color="inverse")
c3.metric("Grips logged", f"{int(daily['grips'].sum()):,}")

tab_alex, tab_clinic, tab_live = st.tabs(["👤 Alex", "🩺 Clinic", "⚡ Live demo"])

# ---------------- Alex view ----------------
with tab_alex:
    rep = latest_report()
    if rep:
        when, report = rep
        st.subheader("Today's summary")
        st.markdown(f"### {report.get('summary_for_alex', '')}")
        rec = report.get("recommended_settings", {})
        st.write(f"Your glove now gives extra help from "
                 f"**{rec.get('afternoon_boost_start_hour', '?')}:00**, "
                 f"when your hand usually tires.")
    else:
        st.write("No report yet. Go to the Clinic tab and run the Gemini analysis.")

# ---------------- Clinic view ----------------
with tab_clinic:
    left, right = st.columns(2)
    with left:
        st.subheader("90-day trend")
        st.line_chart(daily.set_index("day")[["Unaided bend (deg)", "Glove assist (0-180)"]])
    with right:
        st.subheader("Through the day (last 14 days)")
        st.line_chart(hourly.set_index("hour"))
        st.caption("Stronger in the morning, weaker by late afternoon: the pattern in his file.")

    st.subheader("Gemini analysis")
    if st.button("🤖 Run Gemini analysis now", type="primary"):
        with st.spinner("Gemini is reading the Tiger Data trends..."):
            out = subprocess.run([sys.executable, "gemini_report.py"],
                                 capture_output=True, text=True)
        if out.returncode != 0:
            st.error("Gemini script failed:")
            st.code(out.stderr[-2000:])

    rep = latest_report()
    if rep:
        when, report = rep
        st.caption(f"Report generated {when:%b %d, %H:%M} by {report.get('model', 'Gemini')}")
        for line in report.get("clinic_report", []):
            st.markdown(f"- {line}")
        for flag in report.get("flags", []):
            st.warning(flag)
        st.markdown("**Recommended glove settings** (clamped to hard safety limits in code)")
        st.json(report.get("recommended_settings", {}))
        st.caption(report.get("reasoning", ""))

# ---------------- Live demo ----------------
with tab_live:
    st.subheader("Send a grip to Tiger Data")
    st.write("This button stands in for the glove: it writes the same row the glove's "
             "logger writes after every grip.")


    def add_grip(bend_mean):
        bend = max(5.0, random.gauss(bend_mean, 3))
        assist = int(min(180, max(0, 180 * (1 - bend / 90))))
        ttg = max(150, int(400 + (55 - bend) * 25))
        hold = int(random.uniform(4000, 30000))
        get_conn().execute(
            "INSERT INTO grips (time, bend_deg, time_to_grip_ms, servo_pos, hold_ms, simulated) "
            "VALUES (now(), %s, %s, %s, %s, true)",
            (round(bend, 1), ttg, assist, hold))


    b1_, b2_ = st.columns(2)
    if b1_.button("☀️ Morning-strength grip"):
        add_grip(42)
        st.success("Grip saved to Tiger Data")
    if b2_.button("🌙 Afternoon-strength grip"):
        add_grip(32)
        st.success("Grip saved to Tiger Data")

    # ---- Animated finger: replays the most recent grip ----
    last = q("SELECT time, bend_deg::float AS bend, servo_pos, hold_ms "
             "FROM grips ORDER BY time DESC LIMIT 1")
    if not last.empty:
        g = last.iloc[0]
        bend = max(0.0, min(90.0, float(g["bend"])))
        # his own effort, split across the three joints
        b1, b2, b3 = bend * 0.5, bend * 0.6, bend * 0.4
        # full curl the glove completes around a marker
        f1, f2, f3 = 60, 75, 45
        key = f"{g['time']}"  # changes every grip, so the animation replays
        dur = 2.6

        def joint(a_own, a_full):
            return (f'<animateTransform attributeName="transform" type="rotate" '
                    f'values="0;{a_own:.1f};{a_own:.1f};{a_full}" keyTimes="0;0.35;0.5;1" '
                    f'dur="{dur}s" fill="freeze" calcMode="spline" '
                    f'keySplines=".4 0 .2 1;0 0 1 1;.4 0 .2 1"/>')

        tendon_anim = (f'<animate attributeName="stroke" values="#9aa0a6;#9aa0a6;#e4572e;#e4572e" '
                       f'keyTimes="0;0.45;0.55;1" dur="{dur}s" fill="freeze"/>')
        skin, ring = "#e9b99c", "#5b4fd6"
        svg = f"""
        <div id="{key}" style="font-family:sans-serif">
        <svg viewBox="0 0 430 270" width="100%" style="max-width:520px">
          <rect x="5" y="58" width="100" height="74" rx="24" fill="{skin}"/>
          <rect x="20" y="70" width="70" height="50" rx="10" fill="#3c3c46" opacity="0.85"/>
          <text x="55" y="100" font-size="11" fill="#fff" text-anchor="middle">servo</text>
          <g transform="translate(100,95)"><g>{joint(b1, f1)}
            <rect x="0" y="-17" width="100" height="34" rx="17" fill="{skin}"/>
            <rect x="42" y="-20" width="14" height="40" rx="4" fill="{ring}"/>
            <line x1="0" y1="18" x2="100" y2="18" stroke-width="3">{tendon_anim}</line>
            <g transform="translate(100,0)"><g>{joint(b2, f2)}
              <rect x="0" y="-15" width="70" height="30" rx="15" fill="{skin}"/>
              <rect x="26" y="-18" width="12" height="36" rx="4" fill="{ring}"/>
              <line x1="0" y1="16" x2="70" y2="16" stroke-width="3">{tendon_anim}</line>
              <g transform="translate(70,0)"><g>{joint(b3, f3)}
                <rect x="0" y="-13" width="52" height="26" rx="13" fill="{skin}"/>
                <rect x="18" y="-15" width="34" height="30" rx="10" fill="{ring}" opacity="0.9"/>
                <line x1="0" y1="14" x2="40" y2="14" stroke-width="3">{tendon_anim}</line>
              </g></g>
            </g></g>
          </g></g>
          <text x="215" y="250" font-size="16" text-anchor="middle" fill="#555">
            His own effort: {bend:.0f}°
            <animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.44;0.46;1"
                     dur="{dur}s" fill="freeze"/></text>
          <text x="215" y="250" font-size="16" text-anchor="middle" fill="#e4572e" opacity="0">
            Glove takes over and holds ✓
            <animate attributeName="opacity" values="0;0;1;1" keyTimes="0;0.5;0.52;1"
                     dur="{dur}s" fill="freeze"/></text>
        </svg></div>"""
        import streamlit.components.v1 as components
        st.markdown("**Latest grip, replayed**")
        components.html(svg, height=300)
        st.caption(f"Grey: Alex closes his finger {bend:.0f}° on his own. "
                   f"Red tendon: the glove finishes the grip (assist {int(g['servo_pos'])}/180) "
                   f"and holds it for {g['hold_ms'] / 1000:.0f} s.")

    st.markdown("**Last 10 grips in Tiger Data**")
    st.dataframe(q("""
        SELECT to_char(time AT TIME ZONE 'America/Toronto', 'Mon DD HH24:MI:SS') AS time,
               bend_deg AS "bend (deg)", servo_pos AS assist,
               time_to_grip_ms AS "time to grip (ms)", hold_ms AS "hold (ms)", simulated
        FROM grips ORDER BY grips.time DESC LIMIT 10
    """), use_container_width=True, hide_index=True)
