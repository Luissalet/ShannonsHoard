"""Batched DC nodal analysis (modified nodal analysis) of the resistive part of
a design: resistors, thermistors, supplies and regulator outputs. Capacitors
are open at DC, MCU pins are high impedance, LEDs are handled by the power
budget. A tiny conductance to ground (gmin) keeps floating nets solvable,
as SPICE does, and floating nets are reported."""
from __future__ import annotations

import numpy as np

from .design import ntc_resistance

GMIN = 1e-12
GROUND_NAMES = ("GND", "0", "VSS", "AGND")


def ground_net(d) -> str:
    for name in d["nets"]:
        if name.upper() in GROUND_NAMES:
            return name
    for name, members in d["nets"].items():
        for ref, pin in members:
            c = d["_refs"].get(ref)
            if c and ((c["kind"] == "source" and pin == "-") or (c["kind"] == "regulator" and pin == "GND")):
                return name
    raise ValueError("no ground net")


def pin_net(d) -> dict:
    out = {}
    for name, members in d["nets"].items():
        for ref, pin in members:
            out.setdefault((ref, pin), []).append(name)
    return out


def board_outputs(d) -> list[tuple]:
    """Supply pins a board drives itself (its on-board regulator): active when
    the board is fed through its power input and nothing else drives that pin.
    Returns (ref, pin, volts, max_ma) and caches the answer on the design."""
    if "_board_outputs" in d:
        return d["_board_outputs"]
    from .parts import MCUS
    pn = pin_net(d)
    driven = set()
    for ref, c in d["_refs"].items():
        pin = {"source": "+", "regulator": "OUT"}.get(c["kind"])
        if pin and (ref, pin) in pn:
            driven.add(pn[(ref, pin)][0])
    out = []
    for _ in range(2):  # a board may feed another board's input
        for ref, c in d["_refs"].items():
            if c["kind"] != "mcu":
                continue
            board = MCUS[c["part"]]
            fed = any((ref, p) in pn and pn[(ref, p)][0] in driven for p in board.get("power_in", []))
            if not fed:
                continue
            for pin, max_ma in board.get("power_out", {}).items():
                net = pn.get((ref, pin), [None])[0]
                if net and net not in driven and not any(o[0] == ref and o[1] == pin for o in out):
                    out.append((ref, pin, board["pins"][pin]["supply"], max_ma))
                    driven.add(net)
    d["_board_outputs"] = out
    return out


def nominal_params(d) -> dict:
    p = {}
    for ref, c in d["_refs"].items():
        if c["kind"] == "resistor":
            p[ref] = c["value"]
        elif c["kind"] == "ntc":
            p[ref + ".r25"] = c["r25"]
            p[ref + ".beta"] = c["beta"]
        elif c["kind"] == "source":
            p[ref] = c["voltage"]
        elif c["kind"] == "regulator":
            p[ref] = c["vout"]
    for ref, pin, v, _ in board_outputs(d):
        p[f"{ref}.{pin}"] = v
    return p


def tolerances(d, extra=None) -> dict:
    t = {}
    for ref, c in d["_refs"].items():
        if c["kind"] == "resistor":
            t[ref] = c["tolerance"]
        elif c["kind"] == "ntc":
            t[ref + ".r25"] = c["tolerance"]
            t[ref + ".beta"] = c["beta_tolerance"]
        elif c["kind"] == "source":
            t[ref] = c["tolerance"]
        elif c["kind"] == "regulator":
            t[ref] = float(c.get("vout_tolerance", 0.02))
    for ref, pin, _, _ in board_outputs(d):
        t[f"{ref}.{pin}"] = 0.03
    t.update(extra or {})
    return t


def solve(d, params: dict, temperature) -> dict:
    """params: name -> array (N,) or scalar; temperature: array (N,) in °C.
    Returns node voltages {net: (N,)} relative to ground."""
    temperature = np.atleast_1d(np.asarray(temperature, float))
    N = len(temperature)
    gnd = ground_net(d)
    pn = pin_net(d)
    nodes = [n for n in d["nets"] if n != gnd]
    idx = {n: i for i, n in enumerate(nodes)}
    sources = [(ref, c) for ref, c in d["_refs"].items() if c["kind"] in ("source", "regulator")]
    sources += [(f"{ref}.{pin}", {"kind": "board_out", "ref": ref, "pin": pin}) for ref, pin, _, _ in board_outputs(d)]
    n, m = len(nodes), len(sources)
    A = np.zeros((N, n + m, n + m))
    b = np.zeros((N, n + m))
    A[:, np.arange(n), np.arange(n)] += GMIN

    def node(ref, pin):
        nets = pn.get((ref, pin))
        return None if not nets else nets[0]

    def stamp_g(a, c, g):
        ia = idx.get(a) if a is not None and a != gnd else None
        ic = idx.get(c) if c is not None and c != gnd else None
        if ia is not None:
            A[:, ia, ia] += g
        if ic is not None:
            A[:, ic, ic] += g
        if ia is not None and ic is not None:
            A[:, ia, ic] -= g
            A[:, ic, ia] -= g

    for ref, c in d["_refs"].items():
        if c["kind"] == "resistor":
            a, k = node(ref, "1"), node(ref, "2")
            if a is None or k is None:
                continue
            stamp_g(a, k, 1.0 / np.broadcast_to(np.asarray(params[ref], float), (N,)))
        elif c["kind"] == "ntc":
            a, k = node(ref, "1"), node(ref, "2")
            if a is None or k is None:
                continue
            r = ntc_resistance(np.asarray(params[ref + ".r25"], float), np.asarray(params[ref + ".beta"], float), temperature)
            stamp_g(a, k, 1.0 / np.broadcast_to(r, (N,)))
    for j, (ref, c) in enumerate(sources):
        if c["kind"] == "source":
            pos, neg = node(ref, "+"), node(ref, "-")
        elif c["kind"] == "board_out":
            pos, neg = node(c["ref"], c["pin"]), node(c["ref"], "GND")
        else:
            pos, neg = node(ref, "OUT"), node(ref, "GND")
        row = n + j
        for net, sign in ((pos, 1.0), (neg, -1.0)):
            if net is not None and net != gnd:
                A[:, idx[net], row] += sign
                A[:, row, idx[net]] += sign
        if pos is None:
            A[:, row, row] = 1.0  # unconnected supply: its current is free, no constraint
            continue
        b[:, row] = np.broadcast_to(np.asarray(params[ref], float), (N,))
    x = np.linalg.solve(A, b[..., None])[..., 0]
    volts = {gnd: np.zeros(N)}
    for name, i in idx.items():
        volts[name] = x[:, i]
    return volts


def floating_nets(d) -> list[str]:
    """Nets with no DC path to ground through resistors, thermistors or supplies."""
    gnd = ground_net(d)
    adj = {name: set() for name in d["nets"]}
    pn = pin_net(d)
    for ref, c in d["_refs"].items():
        pairs = {"resistor": ("1", "2"), "ntc": ("1", "2"), "source": ("+", "-"), "regulator": ("OUT", "GND"),
                 "led": ("A", "K")}.get(c["kind"])
        if not pairs:
            continue
        a, k = pn.get((ref, pairs[0])), pn.get((ref, pairs[1]))
        if a and k:
            adj[a[0]].add(k[0])
            adj[k[0]].add(a[0])
    for ref, pin, _, _ in board_outputs(d):
        a, k = pn.get((ref, pin)), pn.get((ref, "GND"))
        if a and k:
            adj[a[0]].add(k[0])
            adj[k[0]].add(a[0])
    # A net with a microcontroller pin on it is driven (output) or deliberately
    # high impedance (input): the MCU anchors it.
    anchored = {name for name, members in d["nets"].items()
                if any(d["_refs"].get(r, {}).get("kind") == "mcu" for r, _ in members)}
    seen, stack = {gnd} | anchored, [gnd, *anchored]
    while stack:
        for nb in adj[stack.pop()]:
            if nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return sorted(set(d["nets"]) - seen)
