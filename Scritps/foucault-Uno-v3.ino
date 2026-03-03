#include <QMC5883LCompass.h>
#include <math.h>

QMC5883LCompass compass;

// =====================================================
// ================= PINS ==============================
// =====================================================

#define RIGHT_PWM 5
#define LEFT_PWM 4
#define RIGHT_ENABLE 3
#define LEFT_ENABLE 2
#define LED_MEASURE 8
#define LED_COIL 9

// =====================================================
// ================= STATES ============================
// =====================================================

enum ElectromagnetState { OFF, PULL, PUSH };
ElectromagnetState electromagnetState = OFF;

enum SystemState {
  CYCLE_IDLE,
  CYCLE_ACTIVE
};

SystemState systemState = CYCLE_IDLE;

// =====================================================
// ================= TIMING ============================
// =====================================================

unsigned long peakTime = 0;
unsigned long timeBetweenPeaks = 0;

unsigned long pushStartTime = 0;
unsigned long pullStartTime = 0;
unsigned long electromagnetOffTime = 0;

const unsigned long pushDelay = 50;
const unsigned long pushDuration = 200;

const unsigned long pullDelay = 100;
const unsigned long pullDuration = 100;

const unsigned long measurementDelay = 350;

const unsigned long minimumTimeBetweenPeaks = 1000;
const double peakTolerance = 2;

// =====================================================
// ================= SENSOR ============================
// =====================================================

double xValue, yValue, zValue;
double xOffset = 0;
double yOffset = 0;
double zOffset = 0;

bool measurementReady = false;
bool measurementDone = false;
bool offWindowActive = false;

double deltaX[2];
double deltaY[2];
int angleSampleCount = 0;
double angle;
double angleTime;

// =====================================================
// ===================== SETUP =========================
// =====================================================

void setup() {

  Serial.begin(19200);

  compass.init();
  compass.setSmoothing(10, true);
  compass.setCalibrationScales(0.1, 0.1, 0.1);

  pinMode(RIGHT_PWM, OUTPUT);
  pinMode(LEFT_PWM, OUTPUT);
  pinMode(LEFT_ENABLE, OUTPUT);
  pinMode(RIGHT_ENABLE, OUTPUT);
  pinMode(LED_COIL, OUTPUT);
  pinMode(LED_MEASURE, OUTPUT);

  digitalWrite(LEFT_ENABLE, HIGH);
  digitalWrite(RIGHT_ENABLE, HIGH);

  delay(1000);
}

// =====================================================
// ===================== LOOP ==========================
// =====================================================

void loop() {

  digitalWrite(LED_MEASURE, LOW);

  unsigned long now = millis();

  updateSensor();
  updateControl(now);
  updateMeasurement(now);

  sendSerialData();

  measurementDone = false;
}

// =====================================================
// ================= CONTROL ===========================
// =====================================================

void updateControl(unsigned long now) {

  if (detectPeak(zValue)) {

    timeBetweenPeaks = now - peakTime;
    peakTime = now;

    pushStartTime = now + pushDelay;
    pullStartTime = now + timeBetweenPeaks / 2 + pullDelay;

    systemState = CYCLE_ACTIVE;
  }

  if (systemState != CYCLE_ACTIVE)
    return;

  // ===== PUSH WINDOW =====
  if (now >= pushStartTime &&
      now <= pushStartTime + pushDuration) {

    controlElectromagnet(OFF);   // Change to PUSH to actively push
  }

  // ===== PULL WINDOW =====
  else if (now >= pullStartTime &&
           now <= pullStartTime + pullDuration) {

    controlElectromagnet(PULL);
  }

  // ===== MEASUREMENT WINDOW =====
  else if (now >= pushStartTime + pushDuration &&
           now < pullStartTime) {

    controlElectromagnet(OFF);

    if (!offWindowActive) {
      electromagnetOffTime = now;
      offWindowActive = true;
    }
  }

  // ===== END OF CYCLE =====
  else if (now > pullStartTime + pullDuration) {

    controlElectromagnet(OFF);
    offWindowActive = false;
    measurementReady = false;
    systemState = CYCLE_IDLE;
  }
}

// =====================================================
// ================= MEASUREMENT =======================
// =====================================================

void updateMeasurement(unsigned long now) {

  if (!offWindowActive) return;
  if (electromagnetState != OFF) return;
  if (now <= electromagnetOffTime + measurementDelay) return;
  if (measurementReady) return;

  digitalWrite(LED_MEASURE, HIGH);

  measurementReady = true;
  measurementDone = true;

  calculateAngle(angleTime, angle);
}

// =====================================================
// ================= PEAK DETECTION ====================
// =====================================================

bool detectPeak(double currentValue) {

  static double previousValue = 0;
  static bool rising = false;

  if (abs(currentValue - previousValue) > peakTolerance) {

    if (currentValue > previousValue)
      rising = true;

    else if (rising && currentValue < previousValue) {

      rising = false;

      if (millis() - peakTime > minimumTimeBetweenPeaks) {
        previousValue = currentValue;
        return true;
      }
    }
  }

  previousValue = currentValue;
  return false;
}

// =====================================================
// ============ ELECTROMAGNET CONTROL ==================
// =====================================================

void controlElectromagnet(ElectromagnetState state) {

  electromagnetState = state;

  switch (state) {

    case OFF:
      digitalWrite(RIGHT_PWM, LOW);
      digitalWrite(LEFT_PWM, LOW);
      digitalWrite(LED_COIL, LOW);
      break;

    case PULL:
      digitalWrite(RIGHT_PWM, LOW);
      digitalWrite(LEFT_PWM, HIGH);
      digitalWrite(LED_COIL, HIGH);
      break;

    case PUSH:
      digitalWrite(RIGHT_PWM, HIGH);
      digitalWrite(LEFT_PWM, LOW);
      digitalWrite(LED_COIL, HIGH);
      break;
  }
}

// =====================================================
// ================= SENSOR UPDATE =====================
// =====================================================

void updateSensor() {
  compass.read();
  xValue = compass.getX() + xOffset;
  yValue = compass.getY() + yOffset;
  zValue = compass.getZ() + zOffset;
}

// =====================================================
// ================= ANGLE =============================
// =====================================================

void calculateAngle(double &timeAngle, double &computedAngle) {

  deltaX[angleSampleCount] = xValue;
  deltaY[angleSampleCount] = yValue;
  angleSampleCount++;

  if (angleSampleCount < 2) return;

  angleSampleCount = 0;

  if (deltaX[1] == deltaX[0]) return;

  computedAngle = atan((deltaY[1] - deltaY[0]) /
                       (deltaX[1] - deltaX[0])) * 180.0 / PI;

  if (computedAngle < 0)
    computedAngle += 180;

  timeAngle = millis();
}

// =====================================================
// ================= SERIAL OUTPUT =====================
// =====================================================

void sendSerialData() {

  Serial.print(millis());
  Serial.print(" ; ");
  Serial.print(xValue);
  Serial.print(" ; ");
  Serial.print(yValue);
  Serial.print(" ; ");
  Serial.print(zValue);
  Serial.print(" ; ");
  Serial.print(angleTime);
  Serial.print(" ; ");
  Serial.print(angle);
  Serial.print(" ; ");
  Serial.println(measurementDone);
}
