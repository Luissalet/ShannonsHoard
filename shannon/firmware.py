"""Read the pin usage of Arduino-style firmware (C/C++) and generate the
conversion table that matches the circuit. Only what the code states is
read: symbolic pins are resolved through #define, const and constexpr."""
from __future__ import annotations

import re

from .parts import MCUS

_SYM = re.compile(r"#\s*define\s+(\w+)\s+\(?\s*(\w+)\s*\)?|(?:static\s+)?(?:const(?:expr)?\s+)?(?:u?int(?:8|16|32)?_t|int|byte|uint8_t|gpio_num_t|auto)\s+(\w+)\s*=\s*(\w+)\s*;")
_CALL = re.compile(r"\b(pinMode|digitalWrite|digitalRead|analogRead|analogWrite|analogReadResolution|ledcAttachPin|ledcAttach)\s*\(\s*([^,\)]+)\s*(?:,\s*([^\)]+))?\)")


def _strip_comments(src: str) -> str:
    # Keep the newlines of block comments so line numbers stay right.
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n") or " ", src, flags=re.S)
    return re.sub(r"//[^\n]*", " ", src)


def _line_of(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


def parse(source: str, board: str) -> dict:
    if board not in MCUS:
        raise ValueError(f"unknown board {board}")
    code = _strip_comments(source)
    symbols = {}
    for m in _SYM.finditer(code):
        name, value = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        symbols[name] = value
    uses, unresolved = [], []
    resolution = None
    for m in _CALL.finditer(code):
        fn, arg, arg2 = m.group(1), m.group(2).strip(), (m.group(3) or "").strip()
        line = _line_of(code, m.start())
        if fn == "analogReadResolution":
            try:
                resolution = int(_resolve(arg, symbols))
            except ValueError:
                unresolved.append({"call": fn, "arg": arg, "line": line})
            continue
        try:
            value = _resolve(arg, symbols)
            if fn == "analogRead" and board == "arduino_uno" and isinstance(value, int) and 0 <= value <= 5:
                value = f"A{value}"  # analogRead(0..5) means A0..A5 on the Uno
            pin = pin_name(value, board)
        except ValueError:
            unresolved.append({"call": fn, "arg": arg, "line": line})
            continue
        use = {"call": fn, "pin": pin, "line": line, "symbol": arg if not arg.isdigit() else None}
        if fn == "pinMode":
            use["mode"] = arg2
        uses.append(use)
    return {"board": board, "symbols": symbols, "uses": uses, "unresolved": unresolved,
            "adc_resolution": resolution, "wifi": bool(re.search(r"\bWiFi\s*\.\s*begin\b|\besp_wifi_start\b", code))}


def _resolve(token: str, symbols: dict, depth=0):
    token = token.strip().strip("()")
    if depth > 8:
        raise ValueError(token)
    if re.fullmatch(r"\d+", token):
        return int(token)
    if re.fullmatch(r"A\d", token) or re.fullmatch(r"GPIO_NUM_\d+", token) or re.fullmatch(r"D\d+", token):
        return token
    if token in symbols:
        return _resolve(symbols[token], symbols, depth + 1)
    raise ValueError(token)


def pin_name(value, board: str) -> str:
    """Firmware pin number/symbol -> pin name of the board's pinout."""
    if isinstance(value, str) and value.startswith("GPIO_NUM_"):
        value = int(value[9:])
    if board == "esp32_devkit_v1":
        if isinstance(value, int) and f"GPIO{value}" in MCUS[board]["pins"]:
            return f"GPIO{value}"
    elif board == "rpi_pico":
        if isinstance(value, str) and value.startswith("A"):
            value = 26 + int(value[1:])
        if isinstance(value, int) and f"GP{value}" in MCUS[board]["pins"]:
            return f"GP{value}"
    elif board == "arduino_uno":
        if isinstance(value, str) and re.fullmatch(r"A[0-5]", value):
            return value
        if isinstance(value, str) and re.fullmatch(r"D\d+", value):
            value = int(value[1:])
        if isinstance(value, int):
            if 0 <= value <= 13:
                return f"D{value}"
            if 14 <= value <= 19:
                return f"A{value - 14}"
    raise ValueError(f"pin {value} does not exist on {board}")


def lookup_header(name: str, codes: list[int], temps: list[float], unit: str = "C", full: int = 4095) -> str:
    """C header with a monotonic code->value table and linear interpolation.
    Codes 0 and full scale mean an open or shorted sensor and return NAN."""
    ident = re.sub(r"\W", "_", name).upper()
    if not ident or ident[0].isdigit():
        ident = "S_" + ident
    rows = ",\n".join(f"  {{{c}, {t:.3f}f}}" for c, t in zip(codes, temps))
    return f"""// Generated from the circuit model: ADC code -> {unit}. Linear interpolation between points.
// Codes 0 and {full} (rail) return NAN: open or shorted sensor, not a reading.
#pragma once
#include <math.h>
#include <stdint.h>
typedef struct {{ uint16_t code; float value; }} {ident}_point_t;
static const {ident}_point_t {ident}_TABLE[] = {{
{rows}
}};
static const int {ident}_POINTS = {len(codes)};
static inline float {ident.lower()}_from_code(uint16_t code) {{
  const {ident}_point_t *t = {ident}_TABLE;
  int n = {ident}_POINTS;
  if (code == 0 || code >= {full}) return NAN;
  int up = t[n - 1].code > t[0].code;
  if (up ? code <= t[0].code : code >= t[0].code) return t[0].value;
  if (up ? code >= t[n - 1].code : code <= t[n - 1].code) return t[n - 1].value;
  for (int i = 1; i < n; i++) {{
    if (up ? code <= t[i].code : code >= t[i].code) {{
      float f = ((float)code - t[i - 1].code) / ((float)t[i].code - t[i - 1].code);
      return t[i - 1].value + f * (t[i].value - t[i - 1].value);
    }}
  }}
  return t[n - 1].value;
}}
"""
