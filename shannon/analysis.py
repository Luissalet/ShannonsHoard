"""Checks and studies over a validated design."""
from __future__ import annotations

import itertools

import numpy as np

from . import firmware as fw
from .circuit import floating_nets, ground_net, nominal_params, pin_net, solve, tolerances
from .design import DesignError, component_pins
from .parts import MCUS

PIN_CURRENT_MA = {"esp32_devkit_v1": 20.0, "arduino_uno": 20.0, "rpi_pico": 12.0}


def _issue(level, code, message, where=None):
    out = {"level": level, "code": code, "message": message}
    if where:
        out["where"] = where
    return out


def _mcus(d):
    return [(ref, c) for ref, c in d["_refs"].items() if c["kind"] == "mcu"]


def _ground_pin(board):
    return next(pin for pin, info in board["pins"].items()
                if "power" in info["caps"] and info.get("supply") == 0)


def _power_order(d, outs, pn):
    """Converters ordered from downstream loads towards their power source."""
    net = lambda ref, pin: pn.get((ref, pin), [None])[0]
    pending = {}
    for ref, c in d["_refs"].items():
        if c["kind"] == "regulator":
            pending[ref] = {"ref":ref, "out":net(ref,"OUT"), "in":net(ref,"IN")}
    for ref, pin, vout, max_ma in outs:
        board = MCUS[d["_refs"][ref]["part"]]
        inp = next((net(ref,p) for p in board.get("power_in",[]) if net(ref,p)),None)
        pending[f"{ref}.{pin}"] = {"ref":ref, "pin":pin, "out":net(ref,pin), "in":inp,
                                   "vout":vout, "max_ma":max_ma}
    order = []
    while pending:
        ready = sorted(key for key, item in pending.items()
                       if item["out"] is None or not any(other["in"] == item["out"] for other in pending.values()))
        if not ready:
            raise DesignError("power-supply converter cycle: " + ", ".join(sorted(pending)))
        for key in ready:
            order.append(pending.pop(key))
    return order


def connectivity(d) -> list[dict]:
    issues = []
    pn = pin_net(d)
    for name, members in d["nets"].items():
        for ref, pin in members:
            c = d["_refs"].get(ref)
            if c is None:
                issues.append(_issue("error", "unknown-ref", f"net {name} names {ref}, which is not a component", name))
            elif pin not in component_pins(c):
                issues.append(_issue("error", "unknown-pin", f"net {name}: {ref} has no pin '{pin}'", name))
        if len(members) == 1:
            issues.append(_issue("warning", "dangling-net", f"net {name} connects a single pin ({members[0][0]}.{members[0][1]})", name))
    for (ref, pin), nets in pn.items():
        if len(nets) > 1:
            issues.append(_issue("error", "short", f"{ref}.{pin} is on several nets ({', '.join(nets)}): they are shorted", f"{ref}.{pin}"))
    for ref, c in d["_refs"].items():
        if c["kind"] == "mcu":
            pin = _ground_pin(MCUS[c["part"]])
            if (ref,pin) not in pn:
                issues.append(_issue("error", "mcu-ground-unwired", f"{ref}.{pin} has no ground connection", f"{ref}.{pin}"))
        if c["kind"] in ("resistor", "capacitor", "ntc", "led", "regulator", "source"):
            for pin in component_pins(c):
                if (ref, pin) not in pn:
                    issues.append(_issue("error", "unconnected-pin", f"{ref} pin {pin} is not connected", f"{ref}.{pin}"))
    try:
        ground_net(d)
    except ValueError:
        issues.append(_issue("error", "no-ground", "no ground net (name it GND or connect a supply '-')"))
        return issues
    for name in floating_nets(d):
        members = d["nets"][name]
        if any(d["_refs"].get(r, {}).get("kind") in ("resistor", "ntc", "capacitor") for r, _ in members):
            issues.append(_issue("warning", "floating-net", f"net {name} has no DC path to ground or a supply: its voltage is undefined", name))
    return issues


def electrical(d) -> tuple[list[dict], dict]:
    """Nominal operating point, pin voltage limits, regulators and power budget."""
    from .circuit import board_outputs
    issues, report = [], {}
    pn = pin_net(d)
    net_of = lambda ref, pin: pn.get((ref, pin), [None])[0]
    # Who drives each net: supplies, regulators and boards' own regulators.
    drivers = {}
    for ref, c in d["_refs"].items():
        pin = {"source": "+", "regulator": "OUT"}.get(c["kind"])
        if pin and (ref, pin) in pn:
            drivers.setdefault(net_of(ref, pin), []).append(ref)
    outs = board_outputs(d)
    for ref, pin, _, _ in outs:
        drivers.setdefault(net_of(ref, pin), []).append(f"{ref}.{pin}")
    conflicts = [(net, refs) for net, refs in drivers.items() if len(refs) > 1]
    for net, refs in conflicts:
        issues.append(_issue("error", "rail-conflict", f"net {net} is driven by {', '.join(refs)} at once", net))
    if conflicts:
        return issues, report  # the operating point is undefined with two sources on one rail
    power_order = _power_order(d, outs, pn)
    params = nominal_params(d)
    sensor = d.get("sensor") or {}
    t_nom = 25.0
    volts = {k: float(v[0]) for k, v in solve(d, params, [t_nom]).items()}
    report["operating_point"] = {"temperature": t_nom, "volts": volts}
    active_out = {(r, p) for r, p, _, _ in outs}
    # MCU pin voltages, across the sensor range when there is one.
    temps = np.linspace(*sensor["range"], 15) if sensor.get("range") else np.array([t_nom])
    sweep = solve(d, params, temps)
    for ref, c in _mcus(d):
        board = MCUS[c["part"]]
        board_ground = net_of(ref, _ground_pin(board))
        if board_ground is None:
            issues.append(_issue("error", "mcu-ground-unwired", f"{ref} has no ground connection", ref))
            continue
        for (r, pin), nets in pn.items():
            if r != ref or "power" in board["pins"][pin]["caps"]:
                continue
            v = sweep[nets[0]] - sweep[board_ground]
            if v.max() > board["max_pin_v"] + 1e-6:
                issues.append(_issue("error", "pin-overvoltage",
                                     f"{ref}.{pin} reaches {v.max():.2f} V, above the {board['max_pin_v']} V limit of the {board['label']}", f"{ref}.{pin}"))
            if v.min() < -0.3:
                issues.append(_issue("error", "pin-negative", f"{ref}.{pin} goes to {v.min():.2f} V", f"{ref}.{pin}"))
        for pin, info in board["pins"].items():
            if "power" not in info["caps"] or not info.get("supply") or (ref, pin) not in pn or (ref, pin) in active_out:
                continue
            if pin in board.get("power_in", []):
                continue
            v = volts[net_of(ref, pin)] - volts[board_ground]
            if abs(v - info["supply"]) > 0.1 * info["supply"]:
                issues.append(_issue("error", "supply-mismatch", f"{ref}.{pin} expects {info['supply']} V and gets {v:.2f} V", f"{ref}.{pin}"))
    loads = {}
    # LEDs: the series resistor is the one on the LED's net that is not a rail;
    # the chain runs between the far end of that resistor and the LED's other pin.
    led_rows = []
    gnd = ground_net(d)
    for ref, c in d["_refs"].items():
        if c["kind"] != "led":
            continue
        ends = {p: net_of(ref, p) for p in ("A", "K")}
        series = None
        for side, net in ends.items():
            if net is None or net == gnd or net in drivers:
                continue
            res = [r for r, rc in d["_refs"].items() if rc["kind"] == "resistor" and net in (net_of(r, "1"), net_of(r, "2"))]
            if res:
                series = (side, net, res[0])
                break
        if series is None:
            issues.append(_issue("error", "led-no-resistor", f"LED {ref} has no series resistor", ref))
            continue
        side, mid, r = series
        far = net_of(r, "2") if net_of(r, "1") == mid else net_of(r, "1")
        other = ends["K" if side == "A" else "A"]
        anode_end, cathode_end = (far, other) if side == "A" else (other, far)

        def mcu_on(net):
            for (rr, pin), nets in pn.items():
                if nets[0] == net and d["_refs"].get(rr, {}).get("kind") == "mcu" and "power" not in MCUS[d["_refs"][rr]["part"]]["pins"][pin]["caps"]:
                    return rr, pin
            return None
        drv_a, drv_k = mcu_on(anode_end), mcu_on(cathode_end)
        v_hi = MCUS[d["_refs"][drv_a[0]]["part"]]["logic_v"] if drv_a else volts.get(anode_end, 0.0)
        v_lo = 0.0 if drv_k else volts.get(cathode_end, 0.0)
        i_ma = max(0.0, (v_hi - v_lo - c["vf"]) / d["_refs"][r]["value"] * 1000)
        driver = drv_a or drv_k
        led_rows.append({"led": ref, "resistor": r, "drive": f"{driver[0]}.{driver[1]}" if driver else anode_end, "current_ma": i_ma})
        if driver:
            caps = MCUS[d["_refs"][driver[0]]["part"]]["pins"][driver[1]]["caps"]
            if "out" not in caps:
                issues.append(_issue("error", "pin-cannot-drive", f"LED {ref} is driven from {driver[0]}.{driver[1]}, which is input-only", f"{driver[0]}.{driver[1]}"))
            limit = PIN_CURRENT_MA[d["_refs"][driver[0]]["part"]]
            if i_ma > limit:
                issues.append(_issue("error", "pin-overcurrent", f"LED {ref} draws {i_ma:.1f} mA through {driver[0]}.{driver[1]} (recommended ≤ {limit} mA)", ref))
        rail = _board_rail(d, drv_a[0], pn) if drv_a else (anode_end if anode_end in drivers else None)
        if rail is None and drv_k:
            rail = anode_end if anode_end in drivers else None
        if rail:
            loads.setdefault(rail, []).append((ref, i_ma))
    report["leds"] = led_rows
    # Resistive currents drawn from each driven net (divider currents).
    for net in drivers:
        for ref, c in d["_refs"].items():
            if c["kind"] in ("resistor", "ntc"):
                a, k = net_of(ref, "1"), net_of(ref, "2")
                if net in (a, k) and a and k:
                    rv = c["value"] if c["kind"] == "resistor" else _r_at(c, t_nom)
                    i = abs(volts[a] - volts[k]) / rv * 1000
                    if i > 1e-6:
                        loads.setdefault(net, []).append((ref, i))
    for ref, c in _mcus(d):
        rail = _board_rail(d, ref, pn)
        if rail:
            loads.setdefault(rail, []).append((ref, MCUS[c["part"]]["current_ma"]))
        else:
            issues.append(_issue("error", "mcu-unpowered", f"{ref} has no supply pin connected to a powered net", ref))
    for ref, c in d["_refs"].items():
        if c["kind"] == "generic" and c.get("current_ma") and c.get("rail"):
            loads.setdefault(c["rail"], []).append((ref, float(c["current_ma"])))
    budget = []
    # Finish every downstream converter before computing the load of its parent.
    # This includes on-board regulators and is independent of component order.
    for converter in power_order:
        ref = converter["ref"]
        out_net, in_net = converter["out"], converter["in"]
        if "pin" in converter:
            pin, max_ma = converter["pin"], converter["max_ma"]
            i_out = sum(i for name, i in loads.get(out_net, []) if name != ref)
            budget.append({"regulator": f"{ref}.{pin}", "rail": out_net, "load_ma": i_out, "max_ma": max_ma,
                           "vin": None, "dropout": None, "dissipation_w": None, "loads": list(loads.get(out_net, []))})
            if i_out > max_ma:
                issues.append(_issue("error", "board-regulator-overload", f"{ref}.{pin} supplies {i_out:.0f} mA, above the board's {max_ma:.0f} mA", ref))
            if in_net:
                loads.setdefault(in_net, []).append((f"{ref}.{pin}", i_out))
            continue
        c = d["_refs"][ref]
        i_out = sum(i for _, i in loads.get(out_net, []))
        vin = volts.get(in_net, 0.0)
        headroom = vin - c["vout"]
        diss = max(0.0, headroom) * i_out / 1000
        budget.append({"regulator": ref, "rail": out_net, "load_ma": i_out, "max_ma": c["max_ma"], "vin": vin,
                       "dropout": c["dropout"], "dissipation_w": diss, "loads": list(loads.get(out_net, []))})
        if i_out > c["max_ma"]:
            issues.append(_issue("error", "regulator-overload", f"{ref} supplies {i_out:.0f} mA, above its {c['max_ma']:.0f} mA", ref))
        if headroom < c["dropout"]:
            issues.append(_issue("error", "regulator-dropout", f"{ref} needs {c['vout'] + c['dropout']:.2f} V at its input and gets {vin:.2f} V", ref))
        if diss > 1.0:
            issues.append(_issue("warning", "regulator-heat", f"{ref} dissipates {diss:.2f} W: check its package and cooling", ref))
        loads.setdefault(in_net, []).append((ref, i_out + c.get("quiescent_ma", 0.0)))
    for ref, c in d["_refs"].items():
        if c["kind"] == "source":
            net = net_of(ref, "+")
            i = sum(x for _, x in loads.get(net, []))
            budget.append({"source": ref, "rail": net, "load_ma": i, "max_ma": c.get("max_ma")})
            if c.get("max_ma") and i > c["max_ma"]:
                issues.append(_issue("error", "source-overload", f"supply {ref} must give {i:.0f} mA, more than its {c['max_ma']} mA", ref))
    report["power"] = budget
    return issues, report


def _r_at(c, t):
    from .design import ntc_resistance
    return float(ntc_resistance(c["r25"], c["beta"], t))


def _board_rail(d, ref, pn):
    """The net that powers a board: its power input if fed, else its supply pin."""
    board = MCUS[d["_refs"][ref]["part"]]
    for pin in board.get("power_in", []):
        if (ref, pin) in pn:
            return pn[(ref, pin)][0]
    for pin, info in board["pins"].items():
        if "power" in info["caps"] and info.get("supply") and (ref, pin) in pn:
            return pn[(ref, pin)][0]
    return None


def firmware_checks(d) -> tuple[list[dict], dict]:
    src = (d.get("firmware") or {}).get("source")
    if not src:
        return [], {}
    issues = []
    mcus = _mcus(d)
    if len(mcus) != 1:
        return [_issue("warning", "firmware-board", "firmware checks need exactly one MCU in the design")], {}
    ref, c = mcus[0]
    board = MCUS[c["part"]]
    parsed = fw.parse(src, c["part"])
    pn = pin_net(d)
    sensor = d.get("sensor") or {}
    sensor_pin = sensor.get("pin", "").split(".", 1)[1] if sensor.get("pin", "").startswith(ref + ".") else None
    used = {}
    for u in parsed["uses"]:
        used.setdefault(u["pin"], []).append(u)
        caps = board["pins"][u["pin"]]["caps"]
        wired = (ref, u["pin"]) in pn
        where = f"line {u['line']}"
        if not wired:
            issues.append(_issue("error", "fw-pin-unwired", f"firmware uses {u['pin']} ({u['call']}, {where}) but nothing is connected to {ref}.{u['pin']}", where))
        if u["call"] == "analogRead":
            if "adc" not in caps:
                issues.append(_issue("error", "fw-not-adc", f"analogRead on {u['pin']} ({where}): that pin has no ADC", where))
            elif sensor_pin and u["pin"] != sensor_pin:
                issues.append(_issue("error", "fw-wrong-sensor-pin", f"analogRead reads {u['pin']} ({where}) but the sensor is wired to {sensor_pin}", where))
            if board["pins"][u["pin"]].get("adc_unit") == 2 and parsed["wifi"]:
                issues.append(_issue("error", "fw-adc2-wifi", f"{u['pin']} is on ADC2, which does not work while Wi-Fi is on ({where})", where))
        if u["call"] in ("digitalWrite", "analogWrite", "ledcAttachPin", "ledcAttach") or (u["call"] == "pinMode" and "OUTPUT" in (u.get("mode") or "")):
            if "out" not in caps:
                issues.append(_issue("error", "fw-output-on-input-only", f"{u['call']} drives {u['pin']} ({where}), which is input-only", where))
    if sensor_pin and not any(u["call"] == "analogRead" and u["pin"] == sensor_pin for u in parsed["uses"]):
        issues.append(_issue("error", "fw-sensor-not-read", f"the sensor is wired to {sensor_pin} but the firmware never calls analogRead on it"))
    for (r, pin), nets in pn.items():
        if r == ref and "power" not in board["pins"][pin]["caps"] and pin not in used:
            issues.append(_issue("warning", "fw-pin-unused", f"{ref}.{pin} is wired (net {nets[0]}) but the firmware never uses it"))
    for un in parsed["unresolved"]:
        issues.append(_issue("warning", "fw-unresolved", f"cannot resolve pin '{un['arg']}' in {un['call']} (line {un['line']})"))
    bits = parsed["adc_resolution"] or (board["adc_bits"] if c["part"] != "esp32_devkit_v1" else 12)
    if sensor and parsed["adc_resolution"] and parsed["adc_resolution"] != board["adc_bits"]:
        issues.append(_issue("warning", "fw-adc-bits", f"firmware sets {parsed['adc_resolution']}-bit ADC; the model uses {board['adc_bits']} bits unless told otherwise"))
    return issues, {"parsed": parsed, "adc_bits": bits}


def _adc(d):
    mcus = _mcus(d)
    sensor = d["sensor"]
    ref = sensor["pin"].split(".")[0]
    c = d["_refs"][ref]
    board = MCUS[c["part"]]
    bits = int(sensor.get("adc_bits") or board["adc_bits"])
    vref = float(sensor.get("adc_ref") or board["adc_ref"])
    return bits, vref, float(sensor.get("adc_ref_tolerance", 0.01)), board


def sensor_chain(d, samples=2000, seed=7) -> dict:
    """Transfer from the physical variable to ADC code, tolerance spread,
    resolution, and the firmware table built from the nominal circuit."""
    s = d.get("sensor")
    if not s:
        raise DesignError("the design has no sensor chain", ["Which component senses what, over which range, read by which MCU pin?"])
    pn = pin_net(d)
    ref, pin = s["pin"].split(".", 1)
    if (ref, pin) not in pn:
        raise DesignError(f"sensor pin {s['pin']} is not connected")
    net = pn[(ref, pin)][0]
    bits, vref, vref_tol, board = _adc(d)
    full = 2 ** bits - 1
    mcu_ref = s["pin"].split(".")[0]
    ref_net = None
    if board.get("adc_ref_rail") and not s.get("adc_ref"):
        ref_net = pn.get((mcu_ref, board["adc_ref_rail"]), [None])[0]
        if ref_net:
            vref = float(solve(d, nominal_params(d), [25.0])[ref_net][0])
    lo, hi = s["range"]
    temps = np.arange(lo, hi + 1e-9, s["step"])
    nom = nominal_params(d)
    v_nom = solve(d, nom, temps)[net]
    code_nom = np.clip(np.round(v_nom / vref * full), 0, full)
    ideal_code = np.clip(v_nom / vref * full, 0, full)
    order = np.argsort(ideal_code)
    # Nominal inverse used by the firmware: continuous code -> temperature.
    inv_x, inv_y = ideal_code[order], temps[order]
    monotonic = bool(np.all(np.diff(ideal_code) > 0) or np.all(np.diff(ideal_code) < 0))
    slope = np.gradient(ideal_code, temps)
    resolution = np.where(np.abs(slope) > 1e-12, 1.0 / np.abs(slope), np.inf)
    # Monte Carlo: uniform within each tolerance band, the reference included.
    tol = tolerances(d)
    rng = np.random.default_rng(seed)
    T = np.tile(temps, samples)
    params = {}
    for k, v in nom.items():
        draw = v * (1 + rng.uniform(-1, 1, samples) * tol.get(k, 0.0))
        params[k] = np.repeat(draw, len(temps))
    vref_draw = np.repeat(vref * (1 + rng.uniform(-1, 1, samples) * vref_tol), len(temps))
    sol = solve(d, params, T)
    v = sol[net]
    if ref_net:
        vref_draw = sol[ref_net]  # ratiometric: the ADC reference is the rail that feeds the sensor
    code = np.clip(np.round(v / vref_draw * full), 0, full)
    t_read = np.interp(code, inv_x, inv_y)
    err = (t_read - T).reshape(samples, len(temps))
    codes = code.reshape(samples, len(temps))
    # Worst case: every tolerance at an end (up to 12 parameters).
    keys = [k for k in nom if tol.get(k, 0.0) > 0] + ["adc_ref"]
    worst = None
    if len(keys) <= 12:
        corners = list(itertools.product((-1, 1), repeat=len(keys)))
        Nc = len(corners)
        cp = {k: nom[k] for k in nom}
        sign = np.array(corners, float)
        Tc = np.tile(temps, Nc)
        pc = {}
        for j, k in enumerate(keys[:-1]):
            pc[k] = np.repeat(nom[k] * (1 + sign[:, j] * tol[k]), len(temps))
        for k in nom:
            pc.setdefault(k, cp[k])
        vref_c = np.repeat(vref * (1 + sign[:, -1] * vref_tol), len(temps))
        solc = solve(d, pc, Tc)
        vc = solc[net]
        if ref_net:
            vref_c = solc[ref_net]
        cc = np.clip(np.round(vc / vref_c * full), 0, full)
        ec = (np.interp(cc, inv_x, inv_y) - Tc).reshape(Nc, len(temps))
        worst = np.abs(ec).max(0)
    acc = s.get("accuracy")
    p997 = np.percentile(np.abs(err), 99.7, axis=0)
    rows = []
    for i, t in enumerate(temps):
        row = {"value": float(t), "volts": float(v_nom[i]), "code": int(code_nom[i]),
               "resolution": float(resolution[i]), "code_min": int(codes[:, i].min()), "code_max": int(codes[:, i].max()),
               "error_p997": float(p997[i]), "error_max_mc": float(np.abs(err[:, i]).max())}
        if worst is not None:
            row["error_worst_case"] = float(worst[i])
        if acc is not None:
            budget = row.get("error_worst_case", row["error_max_mc"])
            row["meets_accuracy"] = bool(budget + row["resolution"] / 2 <= acc)
        rows.append(row)
    saturated = [r["value"] for r in rows if r["code"] in (0, full)]
    out = {"net": net, "adc_bits": bits, "adc_ref": vref, "monotonic": monotonic, "rows": rows,
           "samples": samples, "seed": seed, "tolerances": {**tol, "adc_ref": vref_tol},
           "saturated_at": saturated, "unit": s.get("unit", ""), "variable": s.get("variable", "value")}
    if acc is not None:
        ok = [r["value"] for r in rows if r["meets_accuracy"]]
        out["accuracy"] = {"target": acc, "met_from": min(ok) if ok else None, "met_to": max(ok) if ok else None,
                           "met_everywhere": len(ok) == len(rows)}
    # Firmware table: nominal codes at round values, checked by round trip.
    n_pts = int(s.get("table_points", 17))
    t_tab = np.linspace(lo, hi, n_pts)
    c_tab = np.clip(np.round(solve(d, nom, t_tab)[net] / vref * full), 0, full).astype(int)
    keep = np.concatenate([[True], np.diff(c_tab) != 0])
    c_tab, t_tab = c_tab[keep], t_tab[keep]
    header = fw.lookup_header(d["name"] + "_" + out["variable"], c_tab.tolist(), t_tab.tolist(), out["unit"], full)
    rt = np.interp(code_nom, c_tab[np.argsort(c_tab)], t_tab[np.argsort(c_tab)]) - temps
    out["firmware_table"] = {"points": len(c_tab), "header": header,
                             "round_trip_max_error": float(np.abs(rt[(code_nom > 0) & (code_nom < full)]).max()) if np.any((code_nom > 0) & (code_nom < full)) else None}
    return out


def test_plan(d, chain: dict, points=None, noise_lsb: int = 4) -> dict:
    """Acceptance bands for a physical test: expected ADC code range at each
    reference point from the tolerance study, widened by measurement noise."""
    points = points or (d.get("sensor") or {}).get("test_points") or []
    if not points:
        lo, hi = d["sensor"]["range"]
        points = [{"value": v, "how": "reference thermometer"} for v in (lo, (lo + hi) / 2, hi)]
    rows = {r["value"]: r for r in chain["rows"]}
    full = 2 ** chain["adc_bits"] - 1
    lo, hi = min(rows), max(rows)
    plan = []
    for p in points:
        if not lo <= float(p["value"]) <= hi:
            raise DesignError(f"test point {p['value']} is outside the sensor range {lo}..{hi}")
        nearest = min(rows, key=lambda v: abs(v - p["value"]))
        r = rows[nearest]
        plan.append({"value": float(p["value"]), "how": p.get("how", ""), "expected_code": r["code"],
                     "accept_min": max(0, r["code_min"] - noise_lsb), "accept_max": min(full, r["code_max"] + noise_lsb)})
    return {"points": plan, "noise_lsb": noise_lsb,
            "note": "Bands come from the tolerance study of this circuit; a reading outside them points to a wiring, part or reference problem, not to a new calibration."}


def evaluate_measurements(plan: dict, measurements: list[dict], adc_bits: int) -> dict:
    full = 2 ** adc_bits - 1
    by_value = {p["value"]: p for p in plan["points"]}
    out = []
    for m in measurements:
        if m.get("value") is None:
            raise DesignError("every reading needs the reference value it was taken at")
        p = by_value.get(float(m["value"]))
        codes = [int(c) for c in (m.get("codes") or [m.get("code")]) if c is not None]
        if p is None or not codes:
            out.append({"value": m.get("value"), "verdict": "unknown-point"})
            continue
        mean = float(np.mean(codes))
        spread = max(codes) - min(codes)
        if any(c in (0, full) for c in codes):
            verdict = "rail"  # open or shorted sensor, or pin at the rail
        elif spread > 4 * plan["noise_lsb"]:
            verdict = "unstable"
        elif p["accept_min"] <= mean <= p["accept_max"]:
            verdict = "pass"
        else:
            verdict = "fail"
        out.append({"value": p["value"], "mean_code": mean, "spread": spread, "band": [p["accept_min"], p["accept_max"]], "verdict": verdict})
    vals = [r for r in out if "mean_code" in r]
    vals.sort(key=lambda r: r["value"])
    monotonic = len(vals) < 2 or all(np.diff([r["mean_code"] for r in vals]) > 0) or all(np.diff([r["mean_code"] for r in vals]) < 0)
    return {"results": out, "monotonic": bool(monotonic),
            "verdict": "pass" if out and all(r["verdict"] == "pass" for r in out) and monotonic else "fail"}


def enclosure_spec(d, board_mm=None, wall=2.0, clearance=1.5, cable_hole=6.0) -> dict:
    """A Vulcan CAD spec (mm) for an open box that holds the board, with a
    cable hole on one end, plus a matching lid."""
    b = board_mm or d.get("board") or {}
    try:
        W, D, H = float(b["width_mm"]), float(b["depth_mm"]), float(b["height_mm"])
    except (KeyError, TypeError, ValueError):
        raise DesignError("board size missing", ["What are the board's width, depth and tallest component height in mm?"])
    ow, od, oh = W + 2 * (wall + clearance), D + 2 * (wall + clearance), H + wall + clearance
    iw, idp, ih = W + 2 * clearance, D + 2 * clearance, oh  # cavity open at the top
    if cable_hole >= oh - wall:
        raise DesignError("the cable hole does not fit in the wall height")
    body = {
        "name": f"{d['name'][:60]} enclosure", "units": "mm",
        "root": {"type": "difference",
                 "base": {"type": "box", "size": [ow, od, oh]},
                 "cuts": [{"type": "translate", "offset": [0, 0, wall], "child": {"type": "box", "size": [iw, idp, ih]}},
                          {"type": "hole", "diameter": cable_hole, "axis": "x", "side": "max", "depth": wall + clearance,
                           "at": [0, 0, wall + (oh - wall) / 2 - oh / 2]}]},
        "expect": {"bbox": [ow, od, oh], "tolerance": 0.02},
    }
    lid = {"name": f"{d['name'][:60]} lid", "units": "mm",
           "root": {"type": "box", "size": [ow, od, wall]}, "expect": {"bbox": [ow, od, wall], "tolerance": 0.02}}
    return {"enclosure": body, "lid": lid,
            "inner_mm": [iw, idp, oh - wall], "outer_mm": [ow, od, oh],
            "note": "Open box with a floor of one wall thickness and a cable hole in the +X end; build it in Vulcan's Hoard (cad_from_text with spec=). No mounting bosses, vents or sealing."}
