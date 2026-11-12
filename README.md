# Shannon's Hoard

Local small-electronics checker: a circuit, the microcontroller that reads it, its firmware and its enclosure, checked together. [Español](README.es.md)

![Shannon's Hoard](app-icon.png)

## What it is

Shannon catches the wiring, limit and firmware mistakes that cost a board respin, says how accurate a sensor chain really is once every tolerance is counted, writes the firmware conversion table that matches the circuit, gives acceptance bands for the first physical test, and sizes an enclosure for Vulcan's Hoard.

It is not a schematic editor and does not launch KiCad: it reads KiCad's netlist export, or a design written as JSON.

## What it does

- **Design object** (JSON): components (resistor, capacitor, NTC thermistor, LED, connector, supply, regulator, microcontroller board, generic), nets as `REF.PIN` lists, the sensor chain (element, variable, range, accuracy target, ADC pin), firmware source and board size. Values accept `10k`, `4k7`, `100n`. Missing values (a thermistor without beta, a resistor without value, a supply without voltage) come back as questions.
- **Boards with real pin capabilities**: ESP32 DevKit v1 (ADC1/ADC2, input-only GPIO34-39, strapping pins, 3.6 V limit), Arduino Uno (A0-A5, 5 V), Raspberry Pi Pico (GP26-28 ADC). Regulators: AMS1117-3.3, MCP1700-3.3, LM7805.
- **Connectivity checks**: unknown references or pins, pins on two nets (shorts), unconnected passive pins, single-pin nets, nets with no DC path, missing ground.
- **Electrical checks** by DC nodal analysis across the whole sensor range: pin over-voltage (a 5 V divider into a 3.3 V pin), supply pins at the wrong voltage, rails driven twice, regulator dropout, overload and dissipation, LED current against the driving pin's limit, LEDs on input-only pins, and a power budget per rail and supply.
- **Firmware coherence** (Arduino-style C/C++): pins resolved through `#define`, `const`, `constexpr`; `analogRead` on the wired sensor pin and on an ADC pin; outputs not on input-only pins; ADC2 pins with Wi-Fi started; pins used in code but not wired, or wired but never used; ADC resolution set in code.
- **Sensor study**: transfer from the physical variable to ADC code, resolution per LSB, Monte Carlo over every tolerance (resistors, thermistor R25 and beta, supply, ADC reference) and worst case with every tolerance at an end; range where the accuracy target is met; saturation; monotonicity.
- **Firmware table**: a C header (`sensor_table.h`) with the code-to-value table of the nominal circuit and its interpolation function, with the round-trip error; it compiles warning-free with `-std=c99 -Wall -Werror`.
- **Physical test**: acceptance code bands at reference points (ice bath, room with a reference thermometer, boiling water) from the tolerance study, and evaluation of the readings taken on the real board: pass, fail, unstable, or rail (open or shorted sensor), plus monotonicity.
- **Enclosure**: open box with floor, cable hole and lid as CAD specs (mm) for Vulcan's Hoard, sized from the board and its tallest part; the spec compiles with Vulcan's CAD engine.
- **KiCad netlist import** (.net, KiCad 6-8): components by library symbol, values and tolerances from the value field, thermistor beta from `10k B3950`, ESP32/Uno/Pico pins from pin functions (`IO34` → `GPIO34`), regulators by part; the external supply is given explicitly because a netlist only shows a connector.
- **Records**: every check and study with the exact design it used.

Worked example included: a machine temperature node (ESP32, 10k NTC divider on GPIO34, AMS1117 from USB 5 V, status LED) that checks clean, meets ±2.5 °C from 10 to 84 °C with 1 % parts and misses it at the ends; three broken variants (firmware reading the wrong pin, divider fed from 5 V, LED on an input-only pin) that the checks catch.

## Run

Requires Python 3.11 or later.

```
python -m venv .venv
.venv\Scripts\pip install -e .[test]
.venv\Scripts\python -m shannon            # http://127.0.0.1:5245
.venv\Scripts\python -m pytest
```

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | `{service: "shannon-hoard"}` |
| GET | `/api/parts` | boards with pin capabilities, regulators |
| GET | `/api/examples`, `/api/examples/{id}` | worked design and broken variants (`machine_sensor:wrong_pin`, …) |
| POST | `/api/check` | `{design}` → issues, operating point, power budget, firmware pin use |
| POST | `/api/sensor` | `{design, samples, seed}` → transfer, errors, accuracy range, firmware table, test plan |
| POST | `/api/firmware/header` | `{design}` → `sensor_table.h` |
| POST | `/api/measurements` | `{design, readings: [{value, codes}], noise_lsb}` → verdicts |
| POST | `/api/enclosure` | `{design, wall, clearance, cable_hole}` → Vulcan CAD specs |
| POST | `/api/import/kicad` | `{netlist, name, supplies: [{net, voltage, max_ma}]}` |
| GET | `/api/records`, `/api/records/{id}` | saved checks and studies |

## Limits

DC only: no transients, filtering, noise, self-heating of the thermistor or ADC sampling effects; LEDs and MCU outputs are handled by the power budget, not by the nodal solver. The ESP32 ADC is modelled as ideal and linear; the real one needs calibration. Only three boards and three regulators are described. Firmware reading is pattern-based for Arduino-style code, not a compiler. A simulation does not prove how a real board behaves, and nothing here certifies compliance; the test bands exist so the first real readings can say whether the model holds.

## Connection with Faustus and Hoard Hub

`faustus-plugin.json` registers the app as a Faustus plugin. The Hub starts the web application explicitly, on a port that adapts if the default is taken. Faustus gets a panel that receives the current circuit draft (including incomplete JSON) and the last operation with its exact input and result summary; the conversation, model and tools stay in Faustus.

MCP (stdio, `python -m shannon.mcp_server`) starts no HTTP application.

| Group | Tools |
| --- | --- |
| Pure reads (read-only hint, usable in Faustus Plan mode; they create no records or files) | `shannon_examples`, `shannon_parts` |
| Checks and studies | `shannon_check`, `shannon_sensor_study`, `shannon_evaluate_measurements` |
| Firmware, enclosure and import | `shannon_firmware_header`, `shannon_enclosure`, `shannon_import_kicad` |
| Records | `shannon_records` |

The app also carries procedures from the family's skill library for connecting agents (`electronics-wiring-check`, `spec-driven-development`, `verification-loop`). They are named in what an agent reads on connecting, read with `skills_list` and `skill_read`, searched and assigned with `skills_library` and `skills_assign`, and offered as prompts. They are chosen on the skills page (`/api/agent/skills/page`) or in the Hub's Skills tab.

## Project layout

| Path | Contents |
| --- | --- |
| `shannon/circuit.py`, `analysis.py` | Netlist model and DC nodal analysis |
| `shannon/design.py`, `parts.py` | Design object and board/regulator library |
| `shannon/firmware.py` | Firmware pin analysis and header generation |
| `shannon/kicad.py` | KiCad netlist import |
| `shannon/service.py`, `app.py`, `static/` | Service, HTTP API and web page |
| `shannon/mcp_server.py` | MCP server |
| `shannon/hoard_link/` | Shared Hoard family code |
| `tests/` | Test suite (two checks need GCC and are skipped without it) |
| `docs/` | Research notes (Spanish) |

## Credits

Python with NumPy; the generated header is plain C99.
