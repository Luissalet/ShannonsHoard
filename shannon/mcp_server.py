"""MCP tools. Discovery is static: listing tools computes and writes nothing."""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import service

mcp = MCPServer("Shannon's Hoard")


@mcp.tool()
def shannon_examples(example_id: str | None = None) -> dict | list:
    """List the worked designs (a machine temperature node and three broken variants) or return one."""
    return service.example(example_id) if example_id else service.example_list()


@mcp.tool()
def shannon_parts() -> dict:
    """Boards with every pin's capabilities (ADC, input-only, strapping), voltage limits and ADC data; regulators."""
    return service.parts()


@mcp.tool()
def shannon_check(design: dict) -> dict:
    """Check a design: connectivity (unknown pins, shorts, unconnected pins, floating nets), electrical limits across the
    sensor range (pin over-voltage relative to the board ground, rail conflicts, regulator dropout/overload/heat,
    LED and pin currents, power budget propagated through cascaded regulators independently of component order)
    and firmware coherence (pins read or driven by the code versus the wiring, ADC pins, input-only pins, ADC2 with Wi-Fi).
    A missing MCU ground is a wiring error. Missing values come back as questions. Saved as a record."""
    return service.check(design)


@mcp.tool()
def shannon_sensor_study(design: dict, samples: int = 2000) -> dict:
    """Sensor chain from the physical variable to ADC code: nominal transfer, resolution, Monte Carlo and worst-case error
    with every tolerance, range that meets the accuracy target, firmware lookup table and acceptance bands for a physical test."""
    return service.sensor(design, samples)


@mcp.tool()
def shannon_firmware_header(design: dict) -> dict:
    """C header with the ADC-code-to-value table that matches the circuit, and its round-trip error."""
    return service.firmware_header(design)


@mcp.tool()
def shannon_evaluate_measurements(design: dict, readings: list[dict], noise_lsb: int = 4) -> dict:
    """Compare readings taken on the real board ({value, codes:[...]}) with the acceptance bands: pass, fail, unstable or
    rail (open or shorted sensor). Does not recalibrate anything."""
    return service.measurements(design, readings, noise_lsb)


@mcp.tool()
def shannon_enclosure(design: dict, wall: float = 2.0, clearance: float = 1.5, cable_hole: float = 6.0) -> dict:
    """Enclosure and lid as CAD specs (mm) for Vulcan's Hoard, sized from design.board (width_mm, depth_mm, height_mm)."""
    return service.enclosure(design, wall, clearance, cable_hole)


@mcp.tool()
def shannon_import_kicad(netlist_path: str | None = None, netlist: str | None = None, supplies: list[dict] | None = None) -> dict:
    """Read a KiCad netlist export (.net) from a path or text into a design; supplies = [{net, voltage, tolerance, max_ma}].
    KiCad is not launched. What cannot be inferred is returned as questions."""
    if bool(netlist_path) == bool(netlist):
        return {"status": "invalid", "error": "give netlist_path or netlist", "questions": []}
    if netlist_path:
        import pathlib
        p = pathlib.Path(netlist_path)
        if p.suffix.lower() != ".net" or not p.is_file():
            return {"status": "invalid", "error": f"{netlist_path} is not an existing .net file", "questions": []}
        return service.import_kicad(p.read_text(encoding="utf-8", errors="replace"), p.stem, supplies)
    return service.import_kicad(netlist, "KiCad netlist", supplies)


@mcp.tool()
def shannon_records(record_id: str | None = None, limit: int = 50) -> dict | list:
    """List saved checks and studies, or read one with the exact design it used."""
    if record_id:
        try:
            return service.record(record_id)
        except KeyError:
            return {"status": "invalid", "error": f"unknown record {record_id}"}
    return service.records(limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
