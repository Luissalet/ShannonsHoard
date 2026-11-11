# Shannon's Hoard

MCP declares examples, parts, in-memory firmware headers and enclosure specs as pure reads, available to Faustus in Plan mode. These helpers create no check records or files. Checks, sensor studies and measurement evaluation keep their existing record persistence and are not labelled as reads. The combined suite passes40tests with2GCC/cc-specific skips, including the real MCP wire contract.

Family integration1988 adds the canonical Faustus panel and an explicit, port-adaptable Hub launch hint. The panel receives the current circuit draft, including incomplete JSON, and the last operation with its exact input and result summary. An edited draft stays distinct from the previous operation. The conversation, model and tools remain in Faustus; Shannon adds no conversation loop. MCP discovery starts no HTTP application.

Status: integrated in main and listed in the Hub (explicit start). History: ecosystem1936, correction1983, family integration1988, icon1996, MCP helpers2000 in the shannon Ágora space. Native Faustus project74d2bc0f38db is linked to that space.

## Integrated corrections (1983)

A microcontroller board without its ground connection is a wiring error and produces no invented operating point. Pin and supply voltage checks use the board's own ground reference. Loads propagate from downstream converters to their sources in dependency order, including on-board regulators; changing component order does not change the power budget. Converter cycles are reported explicitly.

Different measurements or checks saved in the same second receive unique record IDs and are published atomically. Existing record IDs remain readable.

Validation:38 tests pass and2 are skipped by the GCC/cc-specific checks. Eight review regressions include a real MCP stdio round trip and immutable same-second measurement records. Brave on an isolated instance reports the missing MCU ground, a584mA load against a100mA upstream regulator, and589mA at the supply. These are invented circuits, not physical board measurements. No models, GPUs or hardware were used.

Small electronics on your own PC: a circuit, the microcontroller that reads it, its firmware and its box, checked together. Shannon catches the wiring, limit and firmware mistakes that cost a board respin, says how accurate a sensor chain really is once every tolerance is counted, writes the firmware conversion table that matches the circuit, gives acceptance bands for the first physical test, and sizes an enclosure for Vulcan's Hoard.

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

Worked example: a machine temperature node (ESP32, 10k NTC divider on GPIO34, AMS1117 from USB 5 V, status LED) that checks clean, meets ±2.5 °C from 10 to 84 °C with 1 % parts and misses it at the ends; three broken variants (firmware reading the wrong pin, divider fed from 5 V, LED on an input-only pin) that the checks catch.

## Run

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

## MCP (stdio, `python -m shannon.mcp_server`)

`shannon_examples`, `shannon_parts`, `shannon_check`, `shannon_sensor_study`, `shannon_firmware_header`, `shannon_evaluate_measurements`, `shannon_enclosure`, `shannon_import_kicad`, `shannon_records`.

## Limits

DC only: no transients, filtering, noise, self-heating of the thermistor or ADC sampling effects; LEDs and MCU outputs are handled by the power budget, not by the nodal solver. The ESP32 ADC is modelled as ideal and linear; the real one needs calibration. Only three boards and three regulators are described. Firmware reading is pattern-based for Arduino-style code, not a compiler. A simulation does not prove how a real board behaves, and nothing here certifies compliance; the test bands exist so the first real readings can say whether the model holds.

Both generated-header cases compile and execute with the installed MSVC compiler (`/TC /std:c11 /W4 /WX`), including a name beginning with a digit. Calibration points and both rail codes pass. This supplements the two GCC-specific pytest skips and does not certify a physical board.

Native registration: connector `c157889e-09ea-46cd-b296-6182e2a5effd`, MCP server `0605ea67`. Main source and installed dependencies checked; client verification invokes the pure helpers without creating app data. The HTTP application retains its manual stop; isolated QA uses another port. The implementation was integrated by Claude without an approved cross-review; the historical review votes remain unchanged.

## Skills for the agents that connect

This app carries procedures from the skill library of the family's workspace for the agents that connect to it: `electronics-wiring-check`, `spec-driven-development`, `verification-loop`. They are named in what an agent reads on connecting, read with `skills_list` and `skill_read`, searched and assigned with `skills_library` and `skills_assign`, and offered as prompts. The person chooses them on the skills page (`/api/agent/skills/page`) or in the hub's Skills tab; the `skills` block of `faustus-plugin.json` holds what the app asks for by default.
