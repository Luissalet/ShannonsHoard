"""Operations shared by the HTTP API and the MCP server; reports are stored
with the exact design they were computed from."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import uuid

from . import analysis, examples, kicad
from .design import DesignError, validate
from .parts import MCUS, REGULATORS

VERSION = "0.1.0"


def data_dir() -> pathlib.Path:
    d = pathlib.Path(os.environ.get("SHANNON_DATA") or pathlib.Path(__file__).resolve().parent.parent / "data")
    (d / "records").mkdir(parents=True, exist_ok=True)
    return d


def _public(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def _save(kind, design, out):
    stamp = dt.datetime.now(dt.timezone.utc)
    digest = hashlib.sha256(json.dumps(design, sort_keys=True, default=str).encode()).hexdigest()[:8]
    rid = f"{stamp:%Y%m%d-%H%M%S}-{kind}-{digest}-{uuid.uuid4().hex}"
    rec = {"id": rid, "kind": kind, "name": design.get("name"), "created": stamp.isoformat(timespec="seconds"),
           "version": VERSION, "design": design, "output": out}
    target = data_dir() / "records" / f"{rid}.json"
    pending = target.with_suffix(".tmp")
    pending.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(pending, target)
    return rid


def _guard(fn):
    try:
        return fn()
    except DesignError as e:
        return {"status": "needs-input" if e.questions else "invalid", "error": str(e), "questions": e.questions}


def parts():
    return {"boards": MCUS, "regulators": REGULATORS}


def example_list():
    return examples.listing()


def example(example_id: str):
    base, _, variant = example_id.partition(":")
    if base != "machine_sensor":
        raise KeyError(example_id)
    return examples.get(variant or None)


def assumptions(d):
    notes = ["DC model: capacitors open, MCU inputs high impedance, LEDs handled by the power budget; no transients, noise or self-heating.",
             "Tolerances are spread uniformly inside each band for the Monte Carlo study; the worst case puts every one at an end.",
             "Pin data and part values are nominal datasheet figures; a simulation does not prove how a real board behaves and nothing here certifies compliance."]
    for ref, c in d["_refs"].items():
        if c["kind"] == "mcu":
            notes.append(f"{ref}: {MCUS[c['part']]['label']}. {MCUS[c['part']]['notes']}")
    return notes


def check(design: dict, save: bool = True):
    def go():
        d = validate(design)
        issues = analysis.connectivity(d)
        if not any(i["code"] in ("unknown-ref", "unknown-pin", "no-ground", "mcu-ground-unwired") for i in issues):
            e, rep = analysis.electrical(d)
            issues += e
        else:
            rep = {}
        f, fwrep = analysis.firmware_checks(d)
        issues += f
        errors = [i for i in issues if i["level"] == "error"]
        out = {"status": "checked", "verdict": "errors" if errors else ("warnings" if issues else "clean"),
               "errors": len(errors), "warnings": len(issues) - len(errors), "issues": issues,
               "operating_point": rep.get("operating_point"), "power": rep.get("power"), "leds": rep.get("leds"),
               "firmware": {"uses": fwrep["parsed"]["uses"], "wifi": fwrep["parsed"]["wifi"],
                            "adc_resolution": fwrep["parsed"]["adc_resolution"]} if fwrep else None,
               "assumptions": assumptions(d)}
        if save:
            out["record_id"] = _save("check", design, out)
        return out
    return _guard(go)


def sensor(design: dict, samples: int = 2000, seed: int = 7, save: bool = True):
    def go():
        d = validate(design)
        if not 100 <= samples <= 20000:
            raise DesignError("samples must be between 100 and 20000")
        ch = analysis.sensor_chain(d, samples, seed)
        ch["test_plan"] = analysis.test_plan(d, ch)
        ch["status"] = "solved"
        ch["assumptions"] = assumptions(d)
        if save:
            out = {k: v for k, v in ch.items() if k != "rows"} | {"rows_kept": len(ch["rows"])}
            ch["record_id"] = _save("sensor", design, out)
        return ch
    return _guard(go)


def firmware_header(design: dict):
    def go():
        d = validate(design)
        ch = analysis.sensor_chain(d, 200)
        return {"status": "ok", "header": ch["firmware_table"]["header"], "points": ch["firmware_table"]["points"],
                "round_trip_max_error": ch["firmware_table"]["round_trip_max_error"]}
    return _guard(go)


def measurements(design: dict, readings: list[dict], noise_lsb: int = 4, save: bool = True):
    def go():
        d = validate(design)
        ch = analysis.sensor_chain(d)
        plan = analysis.test_plan(d, ch, noise_lsb=noise_lsb)
        out = analysis.evaluate_measurements(plan, readings, ch["adc_bits"])
        out["plan"] = plan
        out["status"] = "evaluated"
        if save:
            out["record_id"] = _save("measurements", design, out | {"readings": readings})
        return out
    return _guard(go)


def enclosure(design: dict, wall: float = 2.0, clearance: float = 1.5, cable_hole: float = 6.0):
    def go():
        d = validate(design)
        out = analysis.enclosure_spec(d, None, wall, clearance, cable_hole)
        out["status"] = "ok"
        return out
    return _guard(go)


def import_kicad(text: str, name: str = "KiCad netlist", supplies=None):
    def go():
        out = kicad.to_design(text, name, supplies)
        out["status"] = "needs-input" if out["questions"] else "imported"
        return out
    return _guard(go)


def records(limit: int = 100):
    out = []
    for f in sorted((data_dir() / "records").glob("*.json"), reverse=True)[:limit]:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({k: rec.get(k) for k in ("id", "kind", "name", "created")})
    return out


def record(record_id: str):
    if not re.fullmatch(r"[0-9A-Za-z_-]{1,80}", record_id or ""):
        raise KeyError(record_id)
    f = data_dir() / "records" / f"{record_id}.json"
    if not f.exists():
        raise KeyError(record_id)
    return json.loads(f.read_text(encoding="utf-8"))
