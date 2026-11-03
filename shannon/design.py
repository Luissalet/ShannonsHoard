"""Design object: components, nets, sensor chain and firmware. Validation
turns missing facts into questions instead of guesses."""
from __future__ import annotations

import copy
import math
import re

from .parts import KINDS, MCUS, REGULATORS


class DesignError(ValueError):
    def __init__(self, message: str, questions: list[str] | None = None):
        super().__init__(message)
        self.questions = questions or []


_SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "R": 1.0, "r": 1.0}


def parse_value(text) -> float:
    """'10k' -> 10000, '4k7' -> 4700, '100n' -> 1e-7, '1%'-free numbers pass through."""
    if isinstance(text, bool):
        raise DesignError(f"bad value {text!r}")
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().replace("Ω", "").replace("ohm", "").replace("F", "").replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([pnuµmkKMGRr]?)(\d*)", s)
    if not m:
        raise DesignError(f"cannot read value '{text}'")
    whole, mult, frac = m.groups()
    v = float(whole + ("." + frac if frac else ""))
    return v * _SI.get(mult, 1.0)


def component_pins(c: dict) -> list[str]:
    k = c["kind"]
    if k in ("resistor", "capacitor", "ntc"):
        return ["1", "2"]
    if k == "led":
        return ["A", "K"]
    if k == "regulator":
        return ["IN", "OUT", "GND"]
    if k == "source":
        return ["+", "-"]
    if k == "mcu":
        return list(MCUS[c["part"]]["pins"])
    return [str(p) for p in c.get("pins", [])]


def validate(design: dict) -> dict:
    if not isinstance(design, dict):
        raise DesignError("design must be an object")
    d = copy.deepcopy(design)
    comps = d.get("components") or []
    if not comps:
        raise DesignError("the design has no components")
    refs = {}
    questions = []
    for c in comps:
        ref = str(c.get("ref") or "")
        if not ref or ref in refs:
            raise DesignError(f"component refs must be unique and non-empty (got '{ref}')")
        kind = c.get("kind")
        if kind not in KINDS:
            raise DesignError(f"{ref}: kind must be one of {', '.join(KINDS)}")
        if kind in ("resistor", "capacitor"):
            if c.get("value") is None:
                questions.append(f"What is the value of {ref}?")
            else:
                c["value"] = parse_value(c["value"])
                if c["value"] <= 0:
                    raise DesignError(f"{ref}: value must be > 0")
            c["tolerance"] = float(c.get("tolerance", 0.05 if kind == "resistor" else 0.2))
        elif kind == "ntc":
            for key in ("r25", "beta"):
                if c.get(key) is None:
                    questions.append(f"What is the {'resistance at 25 °C' if key == 'r25' else 'beta constant'} of thermistor {ref}?")
            if c.get("r25") is not None:
                c["r25"] = parse_value(c["r25"])
            if c.get("beta") is not None:
                c["beta"] = float(c["beta"])
            c["tolerance"] = float(c.get("tolerance", 0.01))
            c["beta_tolerance"] = float(c.get("beta_tolerance", 0.01))
        elif kind == "led":
            c["vf"] = float(c.get("vf", 2.0))
        elif kind == "mcu":
            if c.get("part") not in MCUS:
                raise DesignError(f"{ref}: unknown board '{c.get('part')}'",
                                  [f"Which board is {ref}? Supported: {', '.join(MCUS)}"])
        elif kind == "regulator":
            if c.get("part") not in REGULATORS and c.get("vout") is None:
                questions.append(f"Which regulator is {ref}? Give a known part ({', '.join(REGULATORS)}) or vout, dropout and max_ma.")
            else:
                spec = dict(REGULATORS.get(c.get("part"), {}))
                spec.update({k: c[k] for k in ("vout", "dropout", "max_ma", "quiescent_ma") if k in c})
                c.update({k: spec.get(k, 0.0) for k in ("vout", "dropout", "max_ma", "quiescent_ma")})
                c.setdefault("label", spec.get("label", ref))
        elif kind == "source":
            if c.get("voltage") is None:
                questions.append(f"What voltage does supply {ref} give?")
            else:
                c["voltage"] = float(c["voltage"])
            c["tolerance"] = float(c.get("tolerance", 0.05))
        elif kind in ("connector", "generic"):
            if not c.get("pins"):
                raise DesignError(f"{ref}: list its pins")
        refs[ref] = c
    nets = d.get("nets") or {}
    if not isinstance(nets, dict) or not nets:
        raise DesignError("the design has no nets")
    norm = {}
    for name, members in nets.items():
        lst = []
        for m in members:
            if isinstance(m, str):
                if "." not in m:
                    raise DesignError(f"net {name}: '{m}' must be REF.PIN")
                ref, pin = m.split(".", 1)
            else:
                ref, pin = m[0], m[1]
            lst.append((str(ref), str(pin)))
        norm[str(name)] = lst
    d["nets"] = norm
    d["_refs"] = refs
    sensor = d.get("sensor")
    if sensor:
        if sensor.get("element") not in refs:
            raise DesignError("sensor.element must name a component", ["Which component is the sensing element?"])
        if not sensor.get("pin") or "." not in sensor["pin"]:
            questions.append("Which MCU pin reads the sensor (REF.PIN)?")
        rng = sensor.get("range")
        if not rng or len(rng) != 2 or rng[0] >= rng[1]:
            questions.append("Over which range must the sensor work (min, max)?")
        sensor.setdefault("step", 1.0)
        sensor.setdefault("accuracy", None)
    if questions:
        raise DesignError("the design is incomplete", questions)
    d["name"] = str(d.get("name") or "unnamed design")
    return d


def ntc_resistance(r25, beta, t_c):
    t = t_c + 273.15
    return r25 * math.e ** (beta * (1.0 / t - 1.0 / 298.15))
