"""Read a KiCad netlist export (.net, S-expression, KiCad 6-8) into a design.
Only the export format is read; KiCad itself is not needed or launched.
Values are parsed (10k, 100n); kinds come from the library symbol; anything
that cannot be inferred is returned as a question."""
from __future__ import annotations

import re

from .design import DesignError, parse_value
from .parts import MCUS

_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+')


def parse_sexpr(text: str):
    stack, cur = [], []
    for tok in _TOKEN.findall(text):
        if tok == "(":
            stack.append(cur)
            cur = []
        elif tok == ")":
            if not stack:
                raise DesignError("unbalanced parentheses in netlist")
            done, cur = cur, stack.pop()
            cur.append(done)
        else:
            cur.append(tok[1:-1].replace('\\"', '"') if tok.startswith('"') else tok)
    if stack:
        raise DesignError("unbalanced parentheses in netlist")
    return cur


def _find(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def _val(node, key, default=None):
    f = _find(node, key)
    return f[0][1] if f and len(f[0]) > 1 else default


_KIND_BY_PART = [
    (re.compile(r"^Conn_|Screw_Terminal|USB", re.I), "connector"),
    (re.compile(r"^(R|R_Small|R_US)$"), "resistor"),
    (re.compile(r"^(C|C_Small|C_Polarized\w*|CP\w*)$"), "capacitor"),
    (re.compile(r"Thermistor|NTC", re.I), "ntc"),
    (re.compile(r"^LED"), "led"),
    (re.compile(r"^Conn_|Screw_Terminal|USB", re.I), "connector"),
    (re.compile(r"AMS1117|MCP1700|LM78|LDO|Regulator", re.I), "regulator"),
]
_BOARD_BY_TEXT = [(re.compile(r"ESP32", re.I), "esp32_devkit_v1"), (re.compile(r"Uno|ATmega328", re.I), "arduino_uno"),
                  (re.compile(r"Pico|RP2040", re.I), "rpi_pico")]
_REG_BY_TEXT = [(re.compile(r"AMS1117-3\.?3", re.I), "ams1117_3v3"), (re.compile(r"MCP1700.*3\.?3|MCP1700-33", re.I), "mcp1700_3v3"),
                (re.compile(r"7805", re.I), "lm7805")]


def _mcu_pin(board, pinfunction, pinnum):
    pf = (pinfunction or "").upper().replace(" ", "")
    pins = MCUS[board]["pins"]
    for cand in (pf, pf.replace("IO", "GPIO", 1) if pf.startswith("IO") else None, f"GPIO{pf}" if pf.isdigit() else None):
        if cand and cand in pins:
            return cand
    for alias in ("3V3", "3.3V", "+3V3"):
        if pf == alias.upper():
            return "3V3"
    if pf in ("GND", "VSS"):
        return "GND"
    if pf in ("VIN", "5V", "+5V", "VBUS"):
        return "VIN" if "VIN" in pins else ("5V" if "5V" in pins else "VSYS")
    return None


def to_design(text: str, name: str = "KiCad netlist", supplies: list[dict] | None = None) -> dict:
    root = parse_sexpr(text)
    exp = next((x for x in root if isinstance(x, list) and x and x[0] == "export"), None)
    if exp is None:
        raise DesignError("not a KiCad netlist export (no (export ...))")
    comps_node = _find(exp, "components")
    nets_node = _find(exp, "nets")
    if not comps_node or not nets_node:
        raise DesignError("the netlist has no components or nets section")
    components, questions, refs = [], [], {}
    for comp in _find(comps_node[0], "comp"):
        ref = _val(comp, "ref")
        value = _val(comp, "value", "")
        lib = _find(comp, "libsource")
        part = _val(lib[0], "part", "") if lib else ""
        footprint = _val(comp, "footprint", "")
        text_all = " ".join([value, part, footprint])
        kind = next((k for rx, k in _KIND_BY_PART if rx.search(part)), None)
        board = next((b for rx, b in _BOARD_BY_TEXT if rx.search(text_all)), None)
        if board:
            kind = "mcu"
        c = {"ref": ref, "kind": kind or "generic", "source": {"value": value, "part": part, "footprint": footprint}}
        if kind in ("resistor", "capacitor"):
            first, *rest = value.split()
            tol = next((float(t[:-1]) / 100 for t in rest if re.fullmatch(r"\d+(?:\.\d+)?%", t)), None)
            if tol is not None:
                c["tolerance"] = tol
            try:
                c["value"] = parse_value(first)
            except (DesignError, ValueError):
                questions.append(f"{ref}: cannot read value '{value}'")
        elif kind == "ntc":
            m = re.search(r"(\d+(?:\.\d+)?[kKM]?\d*)", value)
            if m:
                c["r25"] = parse_value(m.group(1))
            mb = re.search(r"[Bb](?:eta)?\s*=?\s*(\d{3,5})", value)
            if mb:
                c["beta"] = float(mb.group(1))
            else:
                questions.append(f"What is the beta constant of thermistor {ref} ({value})?")
        elif kind == "mcu":
            c["part"] = board
        elif kind == "regulator":
            reg = next((r for rx, r in _REG_BY_TEXT if rx.search(text_all)), None)
            if reg:
                c["part"] = reg
            else:
                questions.append(f"Which regulator is {ref} ({value})? Give vout, dropout and max_ma.")
        elif kind == "led":
            c["vf"] = 2.0
        refs[ref] = c
        components.append(c)
    nets = {}
    pins_seen = {}
    for net in _find(nets_node[0], "net"):
        nname = _val(net, "name", "") or f"net{_val(net, 'code', '?')}"
        nname = nname.lstrip("/")
        members = []
        for node in _find(net, "node"):
            ref, pin = _val(node, "ref"), _val(node, "pin")
            pinfunction = _val(node, "pinfunction")
            c = refs.get(ref)
            if c is None:
                continue
            if c["kind"] == "mcu":
                mapped = _mcu_pin(c["part"], pinfunction, pin)
                if mapped is None:
                    questions.append(f"{ref} pin {pin} ({pinfunction or 'no function name'}): which board pin is it?")
                    continue
                pin = mapped
            elif c["kind"] == "led":
                pin = {"1": "K", "2": "A"}.get(pin, pin) if not pinfunction else ("A" if pinfunction.upper().startswith("A") else "K")
            elif c["kind"] == "regulator":
                pf = (pinfunction or "").upper()
                pin = "IN" if pf.startswith("VI") or pf == "IN" else "OUT" if pf.startswith("VO") or pf == "OUT" else "GND" if pf in ("GND", "ADJ/GND") else pin
            elif c["kind"] in ("connector", "generic"):
                pins_seen.setdefault(ref, set()).add(pin)
            members.append(f"{ref}.{pin}")
        if members:
            nets[nname] = members
    for ref, pins in pins_seen.items():
        refs[ref]["pins"] = sorted(pins, key=lambda p: (len(p), p))
    gnd = next((n for n in nets if n.upper() in ("GND", "0", "VSS")), None)
    for i, sup in enumerate(supplies or []):
        if sup.get("net") not in nets or gnd is None:
            questions.append(f"supply net '{sup.get('net')}' is not in the netlist (or there is no GND net)")
            continue
        ref = f"PS{i + 1}"
        components.append({"ref": ref, "kind": "source", "voltage": float(sup["voltage"]),
                           "tolerance": float(sup.get("tolerance", 0.05)), "max_ma": sup.get("max_ma"), "label": "external supply"})
        nets[sup["net"]].append(f"{ref}.+")
        nets[gnd].append(f"{ref}.-")
    if not any(c["kind"] in ("source",) for c in components):
        questions.append("Which net receives the external supply, at what voltage and with what current limit? (a netlist only shows a connector)")
    return {"design": {"name": name, "components": components, "nets": nets}, "questions": questions}
