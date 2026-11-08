"""
HoldOn live logger: reads grips from the Arduino over USB and saves them to Tiger Data.

The Arduino must print ONE line per completed grip, exactly like this:
    GRIP,<bend_deg>,<time_to_grip_ms>,<servo_pos>,<hold_ms>
e.g.
    GRIP,42.5,820,110,15300

Setup:
    pip install pyserial "psycopg[binary]"
    export TIGER_URL="postgres://tsdbadmin:PASSWORD@HOST:PORT/tsdb?sslmode=require"
Run:
    python grip_logger.py /dev/ttyACM0      (Mac: /dev/cu.usbmodem..., Windows: COM3)
"""
import os
import sys

import psycopg
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
HAND = sys.argv[2] if len(sys.argv) > 2 else "right"
BAUD = 9600  # must match Serial.begin() in the Arduino code

conn = psycopg.connect(os.environ["TIGER_URL"], autocommit=True)
ser = serial.Serial(PORT, BAUD, timeout=1)
print(f"Listening on {PORT}, logging {HAND}-hand grips to Tiger Data...")

while True:
    line = ser.readline().decode(errors="ignore").strip()
    if not line.startswith("GRIP,"):
        if line:
            print("  (arduino)", line)  # show other debug prints
        continue
    try:
        _, bend, ttg, servo, hold = line.split(",")
        values = (HAND, float(bend), int(ttg), int(servo), int(hold))
    except ValueError:
        print("  skipped malformed line:", line)
        continue
    conn.execute(
        "INSERT INTO grips (time, hand, bend_deg, time_to_grip_ms, servo_pos, hold_ms) "
        "VALUES (now(), %s, %s, %s, %s, %s)",
        values,
    )
    print("logged grip:", values)
