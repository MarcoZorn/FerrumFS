// FerrumFS RX: samples the field at a fixed rate and prints one CSV line per
// sample ("v" for Hall, "x,y,z" for QMC5883L). Host does all the decoding.

#include <Arduino.h>

#ifdef SENSOR_QMC
#include <Wire.h>
#define QMC_ADDR 0x0D

static void qmc_write(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(QMC_ADDR);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}
#else
#define PIN_HALL 34  // ADC1, safe with WiFi off or on
#endif

static const uint32_t period_us = 1000000UL / FS_HZ;
static uint32_t next_us;

void setup() {
  Serial.begin(921600);
#ifdef SENSOR_QMC
  Wire.begin(21, 22, 400000);
  qmc_write(0x0B, 0x01);  // set/reset period
  qmc_write(0x09, 0x1D);  // continuous, 200 Hz, 8 G, OSR 512
#else
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_HALL, ADC_11db);
#endif
  next_us = micros();
}

void loop() {
  if ((int32_t)(micros() - next_us) < 0) return;
  next_us += period_us;
#ifdef SENSOR_QMC
  Wire.beginTransmission(QMC_ADDR);
  Wire.write(0x00);
  Wire.endTransmission(false);
  if (Wire.requestFrom(QMC_ADDR, 6) != 6) return;
  int16_t v[3];
  for (int i = 0; i < 3; i++) v[i] = Wire.read() | (Wire.read() << 8);  // LSB first
  Serial.printf("%d,%d,%d\n", v[0], v[1], v[2]);
#else
  Serial.printf("%d\n", analogRead(PIN_HALL));
#endif
}
