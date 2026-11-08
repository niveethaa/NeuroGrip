/*
  BioHacks 2026 - Grip-Assist Brace for Alex (NeuroGrip)
  Hardware: Arduino Uno + Grove Base Shield (switch set to 5V)

  WIRING (Grove cables into the Base Shield):
    Grove Touch Sensor   -> D2   (forefinger: finds the pen, starts the grip)
    Grove Touch Sensor   -> D8   (palm, under the pinky: lifting the pinky releases)
    Grove Button         -> D3   (calibration + caregiver backup release)
    Grove Buzzer         -> D4   (feedback beeps)
    Grove Servo (thumb)  -> D5
    Grove Servo (index)  -> D7   (optional; leave empty if one servo pulls both cables)
    Grove Rotary Angle   -> A0   (mounted at index knuckle = finger-bend sensor)

  POWER: power the servos from a USB power bank if the Arduino resets
  when they move (two servos can pull more current than USB gives).

  HOW IT WORKS:
    1. Fingertip touches an object -> touch sensor fires.
    2. For 0.6 s we measure how far he bends his own finger (his "effort").
    3. Servos close the grip and HOLD it, so he doesn't spend strength holding.
    4. While gripping, the pinky rests on the palm sensor. Lifting it (for more
       than PINKY_GRACE_MS) starts a SLOW release. This is the only way the
       grip opens on its own; the button is a caregiver backup.
       Grip won't re-trigger until the forefinger leaves the pen.
    5. Assist level adapts: the weaker his own bend (fatigue / progression),
       the harder the brace pulls. Every grip is logged as CSV over Serial.

  SERIAL MONITOR (115200 baud) COMMANDS:
    g = force a grip (test servos without sensors)
    o = open / release
    f = toggle "4 PM fatigue" demo mode (+assist)
    c = re-run calibration
    b = print live bend-sensor reading
    s = print status

  Don't touch either touch sensor while the Arduino powers on
  (the Grove touch sensor calibrates itself at power-up).
*/

#include <Arduino.h>
#include <Servo.h>

// ---------------- PINS ----------------
const uint8_t PIN_TOUCH   = 2;
const uint8_t PIN_BUTTON  = 3;
const uint8_t PIN_BUZZER  = 4;
const uint8_t PIN_SERVO_T = 5;
const uint8_t PIN_SERVO_I = 7;
const uint8_t PIN_BEND    = A0;
const uint8_t PIN_PINKY   = 8;

// ---------------- TUNE THESE ON THE REAL GLOVE ----------------
// Angle where the cable is slack (open) and where the finger is fully closed.
// If a servo turns the wrong way, swap its OPEN and CLOSED numbers.
int THUMB_OPEN = 10, THUMB_CLOSED = 140;
int INDEX_OPEN = 10, INDEX_CLOSED = 140;

const unsigned long TOUCH_DEBOUNCE_MS = 150;     // touch must last this long
const unsigned long EFFORT_WINDOW_MS  = 600;     // time to measure his own bend
const unsigned long PINKY_GRACE_MS    = 300;     // pinky must stay lifted this long (ignores brief movements)
const unsigned long REARM_MS          = 700;     // touch must be off this long before next grip
const float         RAMP_PCT_PER_MS   = 0.15;    // ~0.7 s from open to fully closed
const float         RELEASE_PCT_PER_MS= 0.04;    // ~2.5 s to fully open: slow, gentle release

const int MIN_ASSIST    = 30;   // never weaker than this (%)
const int MAX_ASSIST    = 100;
const int FATIGUE_BONUS = 20;   // extra assist in "4 PM" demo mode

// ---------------- STATE ----------------
Servo servoThumb, servoIndex;

enum State { IDLE, SENSING, HOLDING, REARM };
State state = IDLE;

int bendOpen = 300, bendClosed = 700;   // set by calibration

unsigned long touchStart = 0, stateStart = 0;
int  peakEffort = 0;
int  assistPct  = MIN_ASSIST;
bool fatigueMode = false;
bool pinkyArmed  = false;          // pinky has rested on the palm during this grip
unsigned long pinkyOffSince = 0;
bool releasing   = false;          // true while opening slowly

float currentPct = 0, targetPct = 0;
unsigned long lastServoUpdate = 0;

// rolling history of his own effort (last 5 grips)
const int HIST = 5;
int effortHist[HIST];
int histCount = 0, histIdx = 0;
float baselineEffort = -1;   // average of first 3 grips ("morning" strength)

bool lastButton = false;

// Forward declaration (needed outside the Arduino IDE, e.g. PlatformIO)
void setTarget(float pct);

// ---------------- HELPERS ----------------
void beep(int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(PIN_BUZZER, HIGH); delay(60);
    digitalWrite(PIN_BUZZER, LOW);  if (i < times - 1) delay(80);
  }
}

bool buttonPressedEdge() {
  bool now = digitalRead(PIN_BUTTON) == HIGH;
  bool pressed = now && !lastButton;
  lastButton = now;
  if (pressed) delay(20);  // simple debounce
  return pressed;
}

void waitForButton() {
  while (digitalRead(PIN_BUTTON) == HIGH) delay(10);   // wait for release
  while (digitalRead(PIN_BUTTON) == LOW)  delay(10);   // wait for press
  delay(30);
  while (digitalRead(PIN_BUTTON) == HIGH) delay(10);
  lastButton = false;
}

int readBendAvg() {
  long sum = 0;
  for (int i = 0; i < 20; i++) { sum += analogRead(PIN_BEND); delay(5); }
  return sum / 20;
}

// His own finger bend, 0 = fully open, 100 = fully closed
int readEffort() {
  if (bendClosed == bendOpen) return 0;
  long raw = analogRead(PIN_BEND);
  long pct = (raw - bendOpen) * 100L / (bendClosed - bendOpen);  // works either sensor direction
  return constrain(pct, 0, 100);
}

void calibrate() {
  setTarget(0);
  Serial.println(F("# CALIBRATION: relax the hand fully OPEN, then press the button"));
  beep(1);
  waitForButton();
  bendOpen = readBendAvg();
  Serial.println(F("# Now bend the index finger fully CLOSED (help with the other hand), then press the button"));
  beep(1);
  waitForButton();
  bendClosed = readBendAvg();
  Serial.print(F("# bendOpen=")); Serial.print(bendOpen);
  Serial.print(F(" bendClosed=")); Serial.println(bendClosed);
  if (abs(bendClosed - bendOpen) < 50)
    Serial.println(F("# WARNING: small range - check the rotary sensor is mounted at the knuckle"));
  beep(2);
}

void recordEffort(int e) {
  effortHist[histIdx] = e;
  histIdx = (histIdx + 1) % HIST;
  if (histCount < HIST) histCount++;
  if (baselineEffort < 0 && histCount == 3) {
    baselineEffort = (effortHist[0] + effortHist[1] + effortHist[2]) / 3.0;
  }
}

float avgEffort() {
  if (histCount == 0) return 0;
  long s = 0;
  for (int i = 0; i < histCount; i++) s += effortHist[i];
  return (float)s / histCount;
}

// The device supplies what his hand can't: weaker own bend -> more assist.
int computeAssist() {
  int a = 100 - (int)avgEffort();
  if (fatigueMode) a += FATIGUE_BONUS;
  return constrain(a, MIN_ASSIST, MAX_ASSIST);
}

void setTarget(float pct) { targetPct = constrain(pct, 0, 100); }

void updateServos(unsigned long now) {
  unsigned long dt = now - lastServoUpdate;
  lastServoUpdate = now;
  float step = (releasing ? RELEASE_PCT_PER_MS : RAMP_PCT_PER_MS) * dt;
  if (currentPct < targetPct) currentPct = min(currentPct + step, targetPct);
  else if (currentPct > targetPct) currentPct = max(currentPct - step, targetPct);
  if (releasing && currentPct <= 0.5) releasing = false;

  int tAngle = THUMB_OPEN + (int)((THUMB_CLOSED - THUMB_OPEN) * currentPct / 100.0);
  int iAngle = INDEX_OPEN + (int)((INDEX_CLOSED - INDEX_OPEN) * currentPct / 100.0);
  servoThumb.write(tAngle);
  servoIndex.write(iAngle);
}

void logEvent(const char* ev, int effort) {
  // CSV: time_ms,event,own_effort_pct,avg_effort_pct,baseline_pct,assist_pct,fatigue_mode
  Serial.print(millis());              Serial.print(',');
  Serial.print(ev);                    Serial.print(',');
  Serial.print(effort);                Serial.print(',');
  Serial.print(avgEffort(), 1);        Serial.print(',');
  Serial.print(baselineEffort, 1);     Serial.print(',');
  Serial.print(assistPct);             Serial.print(',');
  Serial.println(fatigueMode ? 1 : 0);
}

void startGrip(int effort) {
  assistPct = computeAssist();
  setTarget(assistPct);
  beep(1);
  logEvent("GRIP", effort);
  state = HOLDING;
  stateStart = millis();
  pinkyArmed = false;
  pinkyOffSince = 0;
  releasing = false;
}

void releaseGrip(const char* why) {
  releasing = true;     // open slowly
  setTarget(0);
  beep(2);
  logEvent(why, -1);
  state = REARM;
  stateStart = millis();
}

void handleSerial() {
  if (!Serial.available()) return;
  char c = Serial.read();
  switch (c) {
    case 'g': if (state != HOLDING) { recordEffort(0); startGrip(0); } break;
    case 'o': releaseGrip("RELEASE_SERIAL"); break;
    case 'f':
      fatigueMode = !fatigueMode;
      Serial.print(F("# 4 PM fatigue mode: ")); Serial.println(fatigueMode ? F("ON") : F("OFF"));
      break;
    case 'c': calibrate(); state = IDLE; break;
    case 'b':
      Serial.print(F("# bend raw=")); Serial.print(analogRead(PIN_BEND));
      Serial.print(F(" effort%=")); Serial.println(readEffort());
      break;
    case 's':
      Serial.print(F("# state=")); Serial.print(state);
      Serial.print(F(" avgEffort=")); Serial.print(avgEffort(), 1);
      Serial.print(F(" baseline=")); Serial.print(baselineEffort, 1);
      Serial.print(F(" assist=")); Serial.print(computeAssist());
      Serial.print(F(" pinky=")); Serial.println(digitalRead(PIN_PINKY) == HIGH ? F("on palm") : F("lifted"));
      break;
  }
}

// ---------------- SETUP / LOOP ----------------
void setup() {
  Serial.begin(115200);
  pinMode(PIN_TOUCH, INPUT);
  pinMode(PIN_PINKY, INPUT);
  pinMode(PIN_BUTTON, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  servoThumb.attach(PIN_SERVO_T);
  servoIndex.attach(PIN_SERVO_I);
  currentPct = targetPct = 0;
  updateServos(millis());

  Serial.println(F("# Grip-Assist Brace starting"));
  calibrate();
  Serial.println(F("time_ms,event,own_effort_pct,avg_effort_pct,baseline_pct,assist_pct,fatigue_mode"));
  lastServoUpdate = millis();
}

void loop() {
  unsigned long now = millis();
  handleSerial();

  bool touch  = digitalRead(PIN_TOUCH) == HIGH;
  bool button = buttonPressedEdge();

  // SAFETY: the button always opens the hand, in any state.
  if (button && (state == HOLDING || state == SENSING || currentPct > 1)) {
    releaseGrip("RELEASE_BUTTON");
    button = false;
  }

  switch (state) {
    case IDLE:
      if (touch) {
        if (touchStart == 0) touchStart = now;
        else if (now - touchStart >= TOUCH_DEBOUNCE_MS) {
          state = SENSING; stateStart = now; peakEffort = 0;
        }
      } else touchStart = 0;
      break;

    case SENSING:   // measure how far he can bend on his own
      peakEffort = max(peakEffort, readEffort());
      if (!touch) { state = IDLE; touchStart = 0; break; }   // let go before grip
      if (now - stateStart >= EFFORT_WINDOW_MS) {
        recordEffort(peakEffort);
        startGrip(peakEffort);
      }
      break;

    case HOLDING: {   // servo holds the grip until the pinky lifts
      bool pinkyDown = digitalRead(PIN_PINKY) == HIGH;
      if (pinkyDown) { pinkyArmed = true; pinkyOffSince = 0; }
      else if (pinkyArmed) {
        if (pinkyOffSince == 0) pinkyOffSince = now;
        else if (now - pinkyOffSince >= PINKY_GRACE_MS) releaseGrip("RELEASE_PINKY");
      }
      break;
    }

    case REARM:     // wait until he lets go of the object before arming again
      if (touch) stateStart = now;
      else if (now - stateStart >= REARM_MS) { state = IDLE; touchStart = 0; }
      break;
  }

  updateServos(now);
}
