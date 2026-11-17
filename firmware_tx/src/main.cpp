// FerrumFS TX: loads frames over serial, then loops them forever through the
// coil as Manchester half-bits clocked by a hardware timer (the "loop buffer").
//
// Serial protocol (921600 baud), every command answered with 'K':
//   'C'                 clear frame buffer
//   'F' + 28 bytes      append a frame (host does all framing/FEC)
//   'R' + u16 BE        bitrate in bit/s (default 500)
//   'G' / 'S'           go / stop

#include <Arduino.h>

#define PIN_COIL 25      // MOSFET gate (or DRV8833 IN1)
#define PIN_COIL_B -1    // DRV8833 IN2 for bipolar N/S drive, -1 = unipolar
#define FRAME_LEN 28
#define MAX_FRAMES 256
#define GAP_BITS 8       // coil off between frames: lets RX lose and re-acquire lock

static uint8_t frames[MAX_FRAMES][FRAME_LEN];
static volatile uint16_t nframes = 0;
static volatile bool running = false;
static volatile uint16_t cur = 0;   // frame index
static volatile uint16_t half = 0;  // half-bit index inside frame + gap
static hw_timer_t *timer = nullptr;
static uint16_t bitrate = 500;

static void IRAM_ATTR coil(int level, bool idle) {
  digitalWrite(PIN_COIL, level);
  if (PIN_COIL_B >= 0) digitalWrite(PIN_COIL_B, idle ? 0 : !level);
}

static void IRAM_ATTR on_tick() {
  if (!running || nframes == 0) return coil(0, true);
  const uint16_t gap = GAP_BITS * 2, total = gap + FRAME_LEN * 16;
  if (half < gap) {
    coil(0, true);
  } else {
    uint16_t h = half - gap;
    uint8_t bit = (frames[cur][h >> 4] >> (7 - ((h >> 1) & 7))) & 1;
    coil((h & 1) ? bit : !bit, false);  // 1 = low->high, 0 = high->low
  }
  if (++half >= total) {
    half = 0;
    cur = (cur + 1) % nframes;
  }
}

static void set_rate(uint16_t bps) {
  bitrate = bps ? bps : 1;
  timerAlarmWrite(timer, 1000000UL / (2UL * bitrate), true);  // 1 MHz timer, half-bit period
}

static int read_byte() {
  while (!Serial.available()) {}
  return Serial.read();
}

void setup() {
  pinMode(PIN_COIL, OUTPUT);
  if (PIN_COIL_B >= 0) pinMode(PIN_COIL_B, OUTPUT);
  coil(0, true);
  Serial.begin(921600);
  timer = timerBegin(0, 80, true);  // 80 MHz / 80 = 1 MHz
  timerAttachInterrupt(timer, &on_tick, true);
  set_rate(bitrate);
  timerAlarmEnable(timer);
}

void loop() {
  if (!Serial.available()) return;
  switch (Serial.read()) {
    case 'C': running = false; nframes = 0; cur = half = 0; break;
    case 'F':
      for (int i = 0; i < FRAME_LEN; i++) {
        uint8_t b = read_byte();
        if (nframes < MAX_FRAMES) frames[nframes][i] = b;
      }
      if (nframes < MAX_FRAMES) nframes++;
      break;
    case 'R': { uint16_t hi = read_byte(); set_rate((hi << 8) | read_byte()); break; }
    case 'G': cur = half = 0; running = true; break;
    case 'S': running = false; break;
    default: return;
  }
  Serial.write('K');
}
