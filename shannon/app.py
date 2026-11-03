"""HTTP API and the workbench page."""
from __future__ import annotations

import pathlib
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import service
from .hoard_link.copilot import install_copilot

STATIC = pathlib.Path(__file__).resolve().parent / "static"
app = FastAPI(title="Shannon's Hoard", version=service.VERSION)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
install_copilot(app, "shannon", os.environ.get("SHANNON_DATA", str(STATIC.parents[1] / "data")), app_name="Shannon's Hoard")


class DesignIn(BaseModel):
    design: dict[str, Any]


class SensorIn(DesignIn):
    samples: int = Field(2000, ge=100, le=20000)
    seed: int = 7


class MeasureIn(DesignIn):
    readings: list[dict[str, Any]]
    noise_lsb: int = Field(4, ge=0, le=200)


class EnclosureIn(DesignIn):
    wall: float = Field(2.0, gt=0.4, le=20)
    clearance: float = Field(1.5, ge=0, le=20)
    cable_hole: float = Field(6.0, gt=0, le=40)


class KicadIn(BaseModel):
    netlist: str = Field(..., max_length=5_000_000)
    name: str = "KiCad netlist"
    supplies: list[dict[str, Any]] | None = None


def _ok(res):
    if isinstance(res, dict) and res.get("status") in ("invalid", "needs-input"):
        raise HTTPException(422, res)
    return res


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"service": "shannon-hoard", "version": service.VERSION}


@app.get("/api/parts")
def parts():
    return service.parts()


@app.get("/api/examples")
def examples():
    return service.example_list()


@app.get("/api/examples/{example_id}")
def example(example_id: str):
    try:
        return service.example(example_id)
    except KeyError:
        raise HTTPException(404, "unknown example")


@app.post("/api/check")
def check(body: DesignIn):
    return _ok(service.check(body.design))


@app.post("/api/sensor")
def sensor(body: SensorIn):
    return _ok(service.sensor(body.design, body.samples, body.seed))


@app.post("/api/firmware/header")
def header(body: DesignIn):
    res = _ok(service.firmware_header(body.design))
    return PlainTextResponse(res["header"], headers={"Content-Disposition": 'attachment; filename="sensor_table.h"'})


@app.post("/api/measurements")
def measurements(body: MeasureIn):
    return _ok(service.measurements(body.design, body.readings, body.noise_lsb))


@app.post("/api/enclosure")
def enclosure(body: EnclosureIn):
    return _ok(service.enclosure(body.design, body.wall, body.clearance, body.cable_hole))


@app.post("/api/import/kicad")
def import_kicad(body: KicadIn):
    return service.import_kicad(body.netlist, body.name, body.supplies)


@app.get("/api/records")
def records(limit: int = 100):
    return service.records(limit)


@app.get("/api/records/{record_id}")
def record(record_id: str):
    try:
        return service.record(record_id)
    except KeyError:
        raise HTTPException(404, "unknown record")
