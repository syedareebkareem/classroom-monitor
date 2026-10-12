# Classroom Monitor (Virtual Raspberry Pi + Staff-Room Server)

One computer acts as a virtual Raspberry Pi in a classroom. It makes fake
temperature/humidity readings and a fake camera photo, and sends them over a
Python TCP socket to a second computer (staff room). The server shows every
reading on a dashboard, saves them to `readings.csv`, and can send commands
(Light ON / Light OFF / Take Photo). The Pi carries them out and reports back.

No Phase 1 code is used here. Same language and tools (Python, `socket`,
`threading`, CustomTkinter), all new files built for this scenario.

Simulated data is calibrated like a real room: temperature follows a
slow 90-second day cycle sweeping 23.0..28.0 C (so demos cross the auto
thresholds both ways), with only tiny noise between consecutive readings.
Humidity rides near 55 %. The Pi panel shows a lamp
bulb that glows yellow when the light is ON and goes dark gray when OFF;
the dashboard mirrors it with a lamp dot next to the AUTO badge.

## Files (everything runs inside the isolated `.venv`)
```
Classroom-Monitor/
  .venv/           private Python env (does not touch your system or other projects)
  requirements.txt
  protocol.py      JSON messages: sensor | photo | command | reply | hello
  hal.py           devices: mock on laptop, real sensor/camera/GPIO on a real Pi
  net.py           TCP plumbing (persistent connection, message framing)
  server_ui.py     staff-room dashboard window (fresh, no name prompt)
  pi_ui.py         classroom Pi window (fresh)
  server_app.py    server logic + CSV saving  (--headless for terminal)
  pi_app.py        Pi logic + command execution (--headless for terminal)
  test_all.py      verifies every claim below
  readings.csv     created at runtime (timestamp, temp_c, humidity)
```

## Run it
```
cd Classroom-Monitor
./.venv/bin/python test_all.py              # all checks
./.venv/bin/python server_app.py            # window 1: dashboard
./.venv/bin/python pi_app.py                # window 2: Pi panel
```
The Pi auto-sends a reading every 5 seconds (switch on its panel). On the
server press **Light ON** and watch the Pi panel flip to `Light: ON`; press
**Take Photo** and watch the photo appear on the dashboard.

Terminal-only version (no windows):
```
./.venv/bin/python server_app.py --headless --send-command LED_ON &
./.venv/bin/python pi_app.py --headless --count 2
```

## Automatic light control (live data, real behavior)
The server watches every reading as it arrives:
* temp >= `--auto-high` (default 28.0 C) -> sends `LED_ON`
* temp <= `--auto-low` (default 26.5 C) -> sends `LED_OFF`
* the gap between them stops flicker at the boundary; commands go out
  only on state change, max one per `--auto-cooldown` seconds (default 10)
* dashboard switch flips Auto/Manual; a manual button press pauses auto
  for 60 s so the human always wins; every auto action is logged as
  `AUTO: <temp>C -> <command>`
* `--manual` runs the server with auto off entirely

Try: `./.venv/bin/python server_app.py --headless --auto-high 27 --auto-low 23 &`
then the Pi client - heat spikes flip the light ON by themselves.

## On a real Raspberry Pi 3/4/5 later
Copy the folder to the Pi, put the Pi and server PC on the same WiFi, start
the server with `--host 0.0.0.0`, start the Pi with `--host <PC-IP>`, and
`pip install gpiozero adafruit-dht picamera2` on the Pi. `hal.py` switches
from simulated to real devices by itself.
