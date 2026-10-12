"""Classroom node hardware.

On this laptop every device is faked so the project runs with no
equipment: temperature/humidity come from random numbers, the camera
photo is a generated PNG, and the LED is just an on/off state plus a
printed line. On a real Raspberry Pi 3/4/5 the same class uses the
real sensor, camera and GPIO pin with no change to the rest of the app.
"""
import base64
import io
import math
import random
import time

try:
    from gpiozero import LED  # real Pi only
    _HAS_GPIO = True
except Exception:
    _HAS_GPIO = False

# Calibrated mock climate: a sped-up day cycle around a comfortable room.
# The temperature sweeps BASE-AMPLITUDE .. BASE+AMPLITUDE every PERIOD
# seconds so live demos cross the auto light thresholds both ways,
# while consecutive readings still move smoothly (no wild jumps).
BASE_TEMP = 25.5
AMPLITUDE = 2.5      # -> range 23.0 .. 28.0 C
PERIOD_SEC = 90.0
BASE_HUM = 55.0


class ClassroomHardware:
    def __init__(self):
        self.led_on = False
        self._led = None
        # Calibrated mock climate: a comfortable room that drifts slowly
        # like a real one (~25.5 C, ~55 %), not wild jumps each reading.
        self._t = BASE_TEMP
        self._h = BASE_HUM
        self._born = time.monotonic()
        if _HAS_GPIO:
            try:
                self._led = LED(17)
            except Exception:
                self._led = None

    @property
    def mode(self) -> str:
        return "real" if self._led is not None else "mock"

    def read_climate(self) -> tuple:
        """Returns (temp_c, humidity_pct).

        Mock path follows a slow day-cycle sine wave plus tiny noise, so
        readings glide smoothly yet still sweep 23.0..28.0 C and cross
        the auto light thresholds both ways during a demo.
        """
        if self._led is not None:
            try:  # real DHT sensor path (Pi only)
                import board
                import adafruit_dht
                dht = adafruit_dht.DHT11(board.D4)
                t, h = float(dht.temperature), float(dht.humidity)
                dht.exit()
                self._t, self._h = round(t, 1), round(h, 1)
                return self._t, self._h
            except Exception:
                pass
        phase = 2 * math.pi * (time.monotonic() - self._born) / PERIOD_SEC
        target = BASE_TEMP + AMPLITUDE * math.sin(phase)
        step = max(-0.5, min(0.5, target - self._t))
        self._t = round(min(31.0, max(21.0,
                         self._t + step + random.uniform(-0.15, 0.15))), 1)
        self._h = round(min(70.0, max(40.0,
                         self._h + random.uniform(-0.5, 0.5))), 1)
        return self._t, self._h

    def set_led(self, on: bool) -> str:
        self.led_on = bool(on)
        if self._led is not None:
            try:
                self._led.on() if on else self._led.off()
            except Exception:
                pass
            return f"Classroom light is now {'ON' if on else 'OFF'}"
        state = "ON" if on else "OFF"
        print(f"[mock-light] Classroom light is now {state}")
        return f"Classroom light is now {state} (simulated)"

    def take_photo(self) -> str:
        """Returns a PNG image as a base64 string."""
        if self._led is not None:
            try:  # real Pi camera path (Pi only)
                import time
                from picamera2 import Picamera2
                cam = Picamera2()
                cam.start()
                time.sleep(0.5)
                frame = cam.capture_array()
                cam.stop()
                from PIL import Image
                img = Image.fromarray(frame).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return base64.b64encode(buf.getvalue()).decode("ascii")
            except Exception:
                pass
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (320, 180),
                        (random.randint(0, 80), random.randint(100, 180),
                         random.randint(150, 220)))
        draw = ImageDraw.Draw(img)
        draw.text((15, 60), "Classroom camera", fill=(255, 255, 255))
        draw.text((15, 90), f"{self._t} C / {self._h} %", fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
