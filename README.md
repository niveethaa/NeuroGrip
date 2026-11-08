# NeuroGrip

## Description

**Product Name:** NeuroGrip

**Description:** NeuroGrip is a soft, sensor-guided grip-assist brace for people living with ALS. It helps the thumb and index finger close around a pen, marker or spoon, holds the grip steady so the user doesn't tire, and logs every grip to Tiger Data so the Gemini API can track changes over time and adjust support as strength changes.

Built in 24 hours by a team of 4 at **BioHacks 2026**, McMaster University (Wearable Devices and Quality of Life track).

![NeuroGrip Landing Page](https://github.com/niveethaa/NeuroGrip/blob/a9d9e7fde5f91137652f1792824f6c38bb487fa0/docs/neurogrip-landing-page.png)

**Live website:** [add your Vultr link or domain here]


## Team Information


**Team Name**: SomaLink

<table>
  <tr>
    <th>Name</th>
    <th>Email</th>
  </tr>
  <tr>
    <td>Niveetha Sivakaran</td>
    <td>niveetha.siva@gmail.com</td>
  </tr>
  <tr>
    <td>Hira Ali </td>
    <td>hiraali.ali@mail.utoronto.ca</td>
  </tr>
  <tr>
    <td>Joury Alhaj-Ali</td>
    <td>alhajalj1@gmail.com</td>
  </tr>
  <tr>
    <td>Ruchi Shah</td>
    <td>rmshah016@gmail.com</td>
  </tr>
</table>


## The Problem


Our patient case, Alex, is a 47-year-old high school biology teacher with limb-onset ALS. He waited two years for a diagnosis. Today:

- His right-hand **key pinch is 3 kg**, against a typical 11 kg, and his left hand is starting to weaken.
- He can **start** a pinch but **can't hold it** for more than a few seconds, and his handwriting fades after about ten minutes.
- He is **stronger in the morning than in the afternoon**, so a fixed level of help doesn't fit his day.
- He wants to **be in a classroom in June** and keep **cooking for his family on Sundays**.

Most assistive devices end up unused because they don't match what the person wants. NeuroGrip focuses on one thing Alex asked for: keeping hold of a pen.



## How It Works


1. **Touch:** a touch sensor on the forefinger feels the pen.
2. **Measure:** a rotary angle sensor at the knuckle reads how far Alex bends his finger on his own.
3. **Hold:** the Arduino tells a servo on the forearm how much to pull a cable tendon, which presses the thumb against the pen. Support = 100% − his average finger bend, with extra help in the afternoon, kept between 30% and 100%.
4. **Release:** while he writes, his pinky rests on a palm sensor. Lifting it releases the tendon slowly. A caregiver backup button also releases it.
5. **Remember:** every grip is logged to **Tiger Data**. The **Gemini API** reads the trends and writes a summary for Alex, a report for his clinic, and recommended brace settings (clamped to hard safety limits in code).

![NeuroGrip glove diagram](https://github.com/niveethaa/NeuroGrip/blob/a9d9e7fde5f91137652f1792824f6c38bb487fa0/docs/glove-diagram.png)
*Palm side: touch sensors on the forefinger and under the pinky, a cable tendon from the thumb to a servo on the forearm.*

![NeuroGrip brace simulator](https://github.com/niveethaa/NeuroGrip/blob/a9d9e7fde5f91137652f1792824f6c38bb487fa0/docs/stimulator.png)
*The forefinger finds the pen, then the servo pulls the tendon to press the thumb in and hold the grip.*


## Hardware


| Part | Job |
|------|-----|
| Grove touch sensor (forefinger) | Detects contact with the pen |
| Grove touch sensor (palm, under the pinky) | Lifting the pinky starts a slow release |
| Grove rotary angle sensor | Reads finger position to set thumb pressure |
| Arduino Uno + Grove Base Shield | Runs the grip logic and logs every grip |
| Grove servo + Motor/Servo Driver | Pulls the cable tendon to apply grip pressure |
| Cable tendon (fishing line) + fabric glove | Exoskeleton path from servo to thumb |
| Grove button | Backup release for a caregiver |
| 3D-printed rings, spool and mounts | Tendon guides and servo mount |

**Estimated parts cost:** under $100.

## Tech Stack


| Area | Tools |
|------|-------|
| Hardware | Arduino Uno, Grove sensors, servo, 3D printing (Onshape, PLA) |
| Data | **Tiger Data** (Tiger Cloud, PostgreSQL + TimescaleDB hypertables and continuous aggregates) |
| AI | **Gemini API** (`google-genai`, `gemini-2.5-flash`) |
| Dashboard | Python, Streamlit, pandas, psycopg |
| Website | HTML/CSS/JavaScript, hosted on **Vultr** with nginx |


## Repository Structure


```
neurogrip/
  firmware/
    grip_assist.ino        # Arduino grip logic
  data/
    tiger_setup.sql        # Tiger Data tables, hypertable and continuous aggregates
    run_sql.py             # Runs tiger_setup.sql against Tiger Data
    simulate_history.py    # 90 days of simulated grip history (marked simulated)
    grip_logger.py         # Reads grips from the Arduino and saves them to Tiger Data
    show_data.py           # Prints the grip data in the terminal
    gemini_report.py       # Gemini analysis: summary, clinic report, safe settings
    export_snapshot.py     # Exports a snapshot (holdon_data.json) for the website
    app.py                 # Streamlit dashboard
    requirements.txt
  website/
    index.html             # NeuroGrip website
  docs/
    neurogrip-landing-page.png
  README.md
```



## Getting Started

### 1. Install

```bash
python3 -m pip install -r data/requirements.txt pyserial
```

### 2. Set your keys

Never put these in a file you commit.

```bash
export TIGER_URL="postgres://tsdbadmin:PASSWORD@HOST:PORT/tsdb?sslmode=require"
export GEMINI_API_KEY="your-gemini-key"
```

### 3. Set up the database (once)

```bash
cd data
python3 run_sql.py tiger_setup.sql
python3 simulate_history.py      # optional demo data
```

### 4. Run it

| What | Command |
|------|---------|
| Log live grips from the glove | `python3 grip_logger.py /dev/cu.usbmodemXXXX` |
| See the data in the terminal | `python3 show_data.py` |
| Gemini analysis | `python3 gemini_report.py` |
| Dashboard | `python3 -m streamlit run app.py` |
| Snapshot for the website | `python3 export_snapshot.py` |

The Arduino prints one line per grip in this format, which `grip_logger.py` reads:

```
GRIP,<bend_deg>,<time_to_grip_ms>,<servo_pos>,<hold_ms>
```

### 5. Deploy the website (Vultr)

```bash
ssh root@YOUR_IP
apt update && apt install -y nginx && ufw allow 'Nginx Full'
exit
scp website/index.html root@YOUR_IP:/var/www/html/index.html
```


## Safety

- **Capped force:** the servo has a hard limit so it can't squeeze too hard.
- **He chooses when to let go:** release starts only when he lifts his pinky, and the tendon loosens slowly so nothing drops suddenly.
- **Caregiver backup button** releases the grip at any time.
- **AI can't override safety:** Gemini only *suggests* settings, and the code clamps every suggestion to fixed safe ranges. A real version would have his clinic approve changes.


## Limitations

- **Simulated data:** the 90-day grip history and website charts are **simulated from the case file** and clearly labelled. They are not real patient measurements.
- **Glove and data are not yet connected:** the brace and the data platform each work. Connecting them is one serial line, and the logger is already written.
- **Small servo:** the Grove servo can hold a pen or spoon, not a heavy pot. A real version would need a stronger, lighter actuator.
- **Not a medical device yet:** its Health Canada device class must be confirmed before any clinical use.


## Future Improvements

- **Smart tuning:** Gemini adjusts sensor sensitivity automatically as his strength changes.
- **Automatic calibration** in about three seconds, without a helper.
- **Fingertip pressure sensor** that becomes more sensitive over time.
- **Lighter and wireless:** a small board and battery on a forearm cuff, Bluetooth to his phone.
- **Both hands:** a mirrored left-hand version.
- **Clinic pilot** with occupational therapists and people living with ALS.


## Acknowledgements

Built at **BioHacks 2026**, McMaster University, hosted by BioHacks, BMETT and the iBioMed Society, with Major League Hacking.

Sponsor tools used: **Tiger Data**, **Gemini API**, **Vultr**, and the MLH hardware lab.

*Alex, his family and every clinician in the case are fictional, from the BioHacks 2026 case file.*
