"""Worked example: a machine temperature sensor (invented data)."""
from __future__ import annotations

import copy

FIRMWARE = """// Machine temperature node: reads an NTC divider and blinks a status LED.
#include <WiFi.h>
#define SENSOR_PIN 34
const int LED_PIN = 2;

void setup() {
  pinMode(LED_PIN, OUTPUT);
  analogReadResolution(12);
  Serial.begin(115200);
}

void loop() {
  int raw = analogRead(SENSOR_PIN);
  Serial.println(raw);
  digitalWrite(LED_PIN, raw > 100 ? HIGH : LOW);
  delay(1000);
}
"""

MACHINE_SENSOR = {
    "name": "Machine temperature node",
    "components": [
        {"ref": "J1", "kind": "connector", "pins": ["1", "2"], "label": "5 V input"},
        {"ref": "PS1", "kind": "source", "voltage": 5.0, "tolerance": 0.05, "max_ma": 500, "label": "USB 5 V"},
        {"ref": "U2", "kind": "regulator", "part": "ams1117_3v3"},
        {"ref": "U1", "kind": "mcu", "part": "esp32_devkit_v1"},
        {"ref": "R1", "kind": "resistor", "value": "10k", "tolerance": 0.01},
        {"ref": "RT1", "kind": "ntc", "r25": "10k", "beta": 3950, "tolerance": 0.01, "beta_tolerance": 0.01},
        {"ref": "C1", "kind": "capacitor", "value": "100n"},
        {"ref": "R2", "kind": "resistor", "value": 330, "tolerance": 0.05},
        {"ref": "D1", "kind": "led", "vf": 2.0, "label": "status"},
        {"ref": "J2", "kind": "connector", "pins": ["1", "2"], "label": "thermistor cable"},
    ],
    "nets": {
        "+5V": ["PS1.+", "J1.1", "U2.IN"],
        "GND": ["PS1.-", "J1.2", "U2.GND", "U1.GND", "RT1.2", "C1.2", "D1.K", "J2.2"],
        "+3V3": ["U2.OUT", "U1.3V3", "R1.1"],
        "SENSE": ["R1.2", "RT1.1", "C1.1", "U1.GPIO34", "J2.1"],
        "LED_DRIVE": ["U1.GPIO2", "R2.1"],
        "LED_A": ["R2.2", "D1.A"],
    },
    "sensor": {"element": "RT1", "variable": "temperature", "unit": "C", "range": [-20, 120], "step": 1.0,
               "pin": "U1.GPIO34", "accuracy": 2.5,
               "test_points": [{"value": 0, "how": "ice bath"}, {"value": 25, "how": "reference thermometer at room temperature"},
                               {"value": 100, "how": "boiling water (correct for altitude)"}]},
    "firmware": {"source": FIRMWARE},
    "board": {"width_mm": 55.0, "depth_mm": 28.0, "height_mm": 14.0},
}

BROKEN = {
    "wrong_pin": {"title": "Firmware reads GPIO35 while the divider goes to GPIO34",
                  "firmware": FIRMWARE.replace("#define SENSOR_PIN 34", "#define SENSOR_PIN 35")},
    "five_volt_divider": {"title": "Divider fed from 5 V straight into a 3.3 V pin",
                          "nets": {"+3V3": ["U2.OUT", "U1.3V3"], "+5V": ["PS1.+", "J1.1", "U2.IN", "R1.1"]}},
    "led_on_input_only": {"title": "Status LED moved to GPIO36, an input-only pin",
                          "nets": {"LED_DRIVE": ["U1.GPIO36", "R2.1"]},
                          "firmware": FIRMWARE.replace("const int LED_PIN = 2;", "const int LED_PIN = 36;")},
}


def get(variant: str | None = None) -> dict:
    d = copy.deepcopy(MACHINE_SENSOR)
    if variant:
        if variant not in BROKEN:
            raise KeyError(variant)
        v = BROKEN[variant]
        if "firmware" in v:
            d["firmware"] = {"source": v["firmware"]}
        for net, members in (v.get("nets") or {}).items():
            d["nets"][net] = members
        d["name"] = d["name"] + " — " + v["title"]
    return d


def listing():
    return [{"id": "machine_sensor", "title": MACHINE_SENSOR["name"], "variant": None}] + [
        {"id": f"machine_sensor:{k}", "title": v["title"], "variant": k} for k, v in BROKEN.items()]
