"""Small part library: microcontroller boards with their pin capabilities,
regulators and passive kinds. Pin data are from public board pinouts and
datasheets; they are nominal and listed in every report."""
from __future__ import annotations

# Pin capabilities: adc = analog input, in = digital input, out = digital output,
# input_only = cannot drive, boot = strapping pin (avoid for inputs pulled at boot),
# power = supply/ground pin.
def _esp32():
    pins = {}
    for g in (0, 2, 4, 5, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33):
        pins[f"GPIO{g}"] = {"gpio": g, "caps": ["in", "out"]}
    for g in (34, 35, 36, 39):
        pins[f"GPIO{g}"] = {"gpio": g, "caps": ["in", "input_only"]}
    for g in (32, 33, 34, 35, 36, 39):  # ADC1: usable while Wi-Fi runs
        pins[f"GPIO{g}"]["caps"].append("adc")
        pins[f"GPIO{g}"]["adc_unit"] = 1
    for g in (0, 2, 4, 12, 13, 14, 15, 25, 26, 27):  # ADC2: not usable with Wi-Fi on
        pins[f"GPIO{g}"]["caps"].append("adc")
        pins[f"GPIO{g}"]["adc_unit"] = 2
    for g in (0, 2, 5, 12, 15):
        pins[f"GPIO{g}"]["caps"].append("boot")
    pins["3V3"] = {"caps": ["power"], "supply": 3.3}
    pins["VIN"] = {"caps": ["power"], "supply": 5.0}
    pins["GND"] = {"caps": ["power"], "supply": 0.0}
    return pins


def _uno():
    pins = {}
    for d in range(14):
        pins[f"D{d}"] = {"gpio": d, "caps": ["in", "out"]}
    for a in range(6):
        pins[f"A{a}"] = {"gpio": 14 + a, "alias": f"A{a}", "caps": ["in", "out", "adc"]}
    pins["5V"] = {"caps": ["power"], "supply": 5.0}
    pins["3V3"] = {"caps": ["power"], "supply": 3.3}
    pins["VIN"] = {"caps": ["power"], "supply": None}
    pins["GND"] = {"caps": ["power"], "supply": 0.0}
    return pins


def _pico():
    pins = {}
    for g in range(29):
        if g in (23, 24, 25):
            continue
        pins[f"GP{g}"] = {"gpio": g, "caps": ["in", "out"]}
    for g in (26, 27, 28):
        pins[f"GP{g}"]["caps"].append("adc")
    pins["3V3"] = {"caps": ["power"], "supply": 3.3}
    pins["VSYS"] = {"caps": ["power"], "supply": 5.0}
    pins["GND"] = {"caps": ["power"], "supply": 0.0}
    return pins


MCUS = {
    "esp32_devkit_v1": {"label": "ESP32 DevKit v1 (ESP32-WROOM-32)", "logic_v": 3.3, "max_pin_v": 3.6,
                        "adc_bits": 12, "adc_ref": 3.3, "current_ma": 80.0, "pins": _esp32(),
                        "notes": "ADC modelled as ideal and linear over 0-3.3 V (11 dB attenuation); the real ESP32 ADC is non-linear near the ends and needs calibration."},
    "arduino_uno": {"label": "Arduino Uno (ATmega328P)", "logic_v": 5.0, "max_pin_v": 5.5, "adc_bits": 10,
                    "adc_ref": 5.0, "current_ma": 50.0, "pins": _uno(),
                    "notes": "ADC referenced to the 5 V rail (DEFAULT reference)."},
    "rpi_pico": {"label": "Raspberry Pi Pico (RP2040)", "logic_v": 3.3, "max_pin_v": 3.6, "adc_bits": 12,
                 "adc_ref": 3.3, "current_ma": 30.0, "pins": _pico(),
                 "notes": "ADC referenced to ADC_VREF (3.3 V nominal)."},
}

REGULATORS = {
    "ams1117_3v3": {"label": "AMS1117-3.3 LDO", "vout": 3.3, "dropout": 1.1, "max_ma": 800.0, "quiescent_ma": 5.0},
    "mcp1700_3v3": {"label": "MCP1700-3.3 LDO", "vout": 3.3, "dropout": 0.178, "max_ma": 250.0, "quiescent_ma": 0.0016},
    "lm7805": {"label": "LM7805", "vout": 5.0, "dropout": 2.0, "max_ma": 1000.0, "quiescent_ma": 5.0},
}

KINDS = ("resistor", "capacitor", "ntc", "led", "connector", "mcu", "regulator", "source", "generic")
