-- HoldOn: Tiger Data setup
-- Paste this whole file into the SQL editor in Tiger Console and run it once.

-- 1. One row per grip the glove performs
CREATE TABLE IF NOT EXISTS grips (
    time             TIMESTAMPTZ NOT NULL,
    hand             TEXT        NOT NULL DEFAULT 'right',
    bend_deg         REAL,       -- how far Alex bent the finger on his own before assist
    time_to_grip_ms  INTEGER,    -- first touch -> grip locked
    servo_pos        INTEGER,    -- assist level, 0-180 (higher = glove doing more)
    hold_ms          INTEGER,    -- how long the grip was held
    simulated        BOOLEAN     NOT NULL DEFAULT false
);

-- 2. Turn it into a hypertable (Tiger Data's time-series table)
SELECT create_hypertable('grips', by_range('time'), if_not_exists => TRUE);

-- 3. Hourly summary that updates itself (continuous aggregate)
CREATE MATERIALIZED VIEW IF NOT EXISTS grips_hourly
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', time) AS bucket,
       hand,
       count(*)              AS grips,
       avg(bend_deg)         AS avg_bend,
       avg(servo_pos)        AS avg_assist,
       avg(hold_ms)          AS avg_hold_ms,
       avg(time_to_grip_ms)  AS avg_time_to_grip_ms
FROM grips
GROUP BY bucket, hand
WITH NO DATA;

-- 4. Daily summary (what the clinic view and Gemini read)
CREATE MATERIALIZED VIEW IF NOT EXISTS grips_daily
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 day', time, 'America/Toronto') AS day,
       hand,
       count(*)              AS grips,
       avg(bend_deg)         AS avg_bend,
       avg(servo_pos)        AS avg_assist,
       avg(hold_ms)          AS avg_hold_ms,
       avg(time_to_grip_ms)  AS avg_time_to_grip_ms
FROM grips
GROUP BY day, hand
WITH NO DATA;

-- 5. Include brand-new grips instantly (so a judge's grip shows up live)
ALTER MATERIALIZED VIEW grips_hourly SET (timescaledb.materialized_only = false);
ALTER MATERIALIZED VIEW grips_daily  SET (timescaledb.materialized_only = false);

-- 6. Keep the summaries refreshed automatically
SELECT add_continuous_aggregate_policy('grips_hourly',
    start_offset => INTERVAL '120 days', end_offset => NULL,
    schedule_interval => INTERVAL '1 minute', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('grips_daily',
    start_offset => INTERVAL '120 days', end_offset => NULL,
    schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);


-- ===== Queries for the website and Gemini (don't run these during setup) =====

-- Trend over weeks (clinic chart)
-- SELECT day, avg_bend, avg_assist, grips FROM grips_daily
-- WHERE hand = 'right' ORDER BY day;

-- Morning vs afternoon (his fatigue pattern), last 14 days
-- SELECT CASE WHEN extract(hour FROM time AT TIME ZONE 'America/Toronto') < 12
--             THEN 'morning' ELSE 'afternoon' END AS part_of_day,
--        round(avg(bend_deg)::numeric, 1)  AS avg_bend,
--        round(avg(servo_pos)::numeric, 1) AS avg_assist
-- FROM grips
-- WHERE time > now() - INTERVAL '14 days'
-- GROUP BY part_of_day;

-- Live feed (last 10 grips, for the expo demo)
-- SELECT * FROM grips ORDER BY time DESC LIMIT 10;
