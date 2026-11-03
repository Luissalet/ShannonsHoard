import asyncio
import copy
import pathlib
import shutil
import subprocess

import numpy as np
import pytest
from fastapi.testclient import TestClient

from shannon import analysis, examples, firmware, kicad, service
from shannon.circuit import nominal_params, solve
from shannon.design import DesignError, ntc_resistance, parse_value, validate

FIX = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("SHANNON_DATA", str(tmp_path))


def codes(issues):
    return {i["code"] for i in issues}


def all_issues(design):
    d = validate(design)
    return analysis.connectivity(d) + analysis.electrical(d)[0] + analysis.firmware_checks(d)[0]


@pytest.mark.parametrize("text,value", [("10k", 1e4), ("4k7", 4700), ("100n", 1e-7), ("330", 330), ("2M2", 2.2e6), ("1R5", 1.5), (47, 47)])
def test_values(text, value):
    assert parse_value(text) == pytest.approx(value)


def test_divider_matches_hand_calculation():
    d = validate(examples.get())
    v = solve(d, nominal_params(d), [25.0, 0.0])["SENSE"]
    assert v[0] == pytest.approx(3.3 / 2, rel=1e-6)  # NTC = R1 at 25 C (gmin shifts it by ~1e-8)
    rt0 = ntc_resistance(10e3, 3950, 0.0)
    assert v[1] == pytest.approx(3.3 * rt0 / (rt0 + 10e3), rel=1e-6)


def test_example_is_clean_and_broken_variants_are_caught():
    assert all_issues(examples.get()) == []
    assert {"fw-wrong-sensor-pin", "fw-pin-unwired", "fw-sensor-not-read"} <= codes(all_issues(examples.get("wrong_pin")))
    assert "pin-overvoltage" in codes(all_issues(examples.get("five_volt_divider")))
    assert {"pin-cannot-drive", "fw-output-on-input-only"} <= codes(all_issues(examples.get("led_on_input_only")))


def test_connectivity_errors():
    d = examples.get()
    d["nets"]["SENSE"] = d["nets"]["SENSE"] + ["U1.GPIO99"]
    d["nets"]["EXTRA"] = ["R1.2"]
    found = codes(analysis.connectivity(validate(d)))
    assert {"unknown-pin", "short", "dangling-net"} <= found
    d = examples.get()
    d["nets"]["LED_A"] = ["D1.A"]
    assert "unconnected-pin" in codes(analysis.connectivity(validate(d)))


def test_adc2_with_wifi_and_power_problems():
    d = examples.get()
    d["nets"]["SENSE"] = ["R1.2", "RT1.1", "C1.1", "U1.GPIO25", "J2.1"]
    d["sensor"]["pin"] = "U1.GPIO25"
    d["firmware"]["source"] = d["firmware"]["source"].replace("#define SENSOR_PIN 34", "#define SENSOR_PIN 25")
    assert "fw-adc2-wifi" not in codes(all_issues(d))  # WiFi.h included but never started
    d["firmware"]["source"] = d["firmware"]["source"].replace("Serial.begin(115200);", 'Serial.begin(115200);\n  WiFi.begin("plant", "secret");')
    assert "fw-adc2-wifi" in codes(all_issues(d))
    d = examples.get()
    next(c for c in d["components"] if c["ref"] == "PS1")["voltage"] = 4.0
    assert "regulator-dropout" in codes(all_issues(d))
    d = examples.get()
    next(c for c in d["components"] if c["ref"] == "R2")["value"] = 47
    assert "pin-overcurrent" in codes(all_issues(d))


def test_missing_values_become_questions():
    d = examples.get()
    next(c for c in d["components"] if c["ref"] == "RT1").pop("beta")
    with pytest.raises(DesignError) as err:
        validate(d)
    assert any("beta" in q for q in err.value.questions)


def test_sensor_chain_tolerance_and_accuracy():
    ch = analysis.sensor_chain(validate(examples.get()))
    assert ch["monotonic"] and not ch["saturated_at"]
    r25 = next(r for r in ch["rows"] if r["value"] == 25)
    assert r25["code"] == 2048 or r25["code"] == 2047
    for r in ch["rows"]:
        assert r["error_worst_case"] >= r["error_p997"] - 1e-9  # corners bound the Monte Carlo
    assert ch["accuracy"]["met_from"] is not None and not ch["accuracy"]["met_everywhere"]
    # Better parts widen the accurate range.
    d = examples.get()
    for c in d["components"]:
        if c["ref"] in ("R1", "RT1"):
            c["tolerance"] = 0.001
        if c["ref"] == "RT1":
            c["beta_tolerance"] = 0.001
    d["sensor"]["adc_ref_tolerance"] = 0.001
    ch2 = analysis.sensor_chain(validate(d))
    assert ch2["accuracy"]["met_from"] <= ch["accuracy"]["met_from"] and ch2["accuracy"]["met_to"] >= ch["accuracy"]["met_to"]


def test_firmware_header_round_trip_and_compiles(tmp_path):
    ch = analysis.sensor_chain(validate(examples.get()))
    assert ch["firmware_table"]["round_trip_max_error"] < 1.0
    gcc = shutil.which("gcc") or shutil.which("cc")
    if not gcc:
        pytest.skip("no C compiler")
    (tmp_path / "t.h").write_text(ch["firmware_table"]["header"])
    (tmp_path / "t.c").write_text('#include <stdio.h>\n#include "t.h"\nint main(void){printf("%.1f %.1f",'
                                  'machine_temperature_node_temperature_from_code(3156),machine_temperature_node_temperature_from_code(2047));return 0;}\n')
    subprocess.run([gcc, "-std=c99", "-Wall", "-Werror", "t.c", "-o", "t"], cwd=tmp_path, check=True)
    out = subprocess.run([str(tmp_path / "t")], capture_output=True, text=True, check=True).stdout.split()
    assert abs(float(out[0]) - 0) < 0.5 and abs(float(out[1]) - 25) < 0.5


def test_firmware_parser_resolves_symbols():
    src = "#define A (PIN_X)\nconst int PIN_X = 26;\nvoid loop(){ analogRead(A); /* analogRead(99); */ }\n// digitalWrite(5, 1);"
    p = firmware.parse(src, "rpi_pico")
    assert [u["pin"] for u in p["uses"]] == ["GP26"]
    assert firmware.pin_name("A1", "arduino_uno") == "A1" and firmware.pin_name(15, "arduino_uno") == "A1"
    with pytest.raises(ValueError):
        firmware.pin_name(40, "esp32_devkit_v1")


def test_measurements_verdicts():
    d = validate(examples.get())
    ch = analysis.sensor_chain(d)
    plan = analysis.test_plan(d, ch)
    ok = [{"value": p["value"], "codes": [p["expected_code"], p["expected_code"] + 1]} for p in plan["points"]]
    assert analysis.evaluate_measurements(plan, ok, 12)["verdict"] == "pass"
    bad = copy.deepcopy(ok)
    bad[2]["codes"] = [4095]
    res = analysis.evaluate_measurements(plan, bad, 12)
    assert res["verdict"] == "fail" and res["results"][2]["verdict"] == "rail"
    drift = copy.deepcopy(ok)
    drift[1]["codes"] = [plan["points"][1]["accept_max"] + 50]
    assert analysis.evaluate_measurements(plan, drift, 12)["results"][1]["verdict"] == "fail"


def test_kicad_import_matches_hand_written_design():
    out = kicad.to_design((FIX / "machine-node.net").read_text(), supplies=[{"net": "+5V", "voltage": 5.0, "max_ma": 500}])
    assert out["questions"] == []
    d = out["design"]
    assert d["nets"]["SENSE"] == ["R1.2", "RT1.1", "C1.1", "U1.GPIO34", "J2.1"]
    rt = next(c for c in d["components"] if c["ref"] == "RT1")
    assert rt["r25"] == 10e3 and rt["beta"] == 3950
    d["sensor"] = examples.get()["sensor"]
    d["firmware"] = examples.get()["firmware"]
    assert all_issues(d) == []
    a = analysis.sensor_chain(validate(d), 300)
    b = analysis.sensor_chain(validate(examples.get()), 300)
    assert [r["code"] for r in a["rows"]] == [r["code"] for r in b["rows"]]


def test_kicad_import_without_supply_asks():
    out = kicad.to_design((FIX / "machine-node.net").read_text())
    assert any("supply" in q for q in out["questions"])
    with pytest.raises(DesignError):
        kicad.to_design("(nothing)")


def test_enclosure_spec_shape():
    out = analysis.enclosure_spec(validate(examples.get()))
    assert out["outer_mm"] == [62.0, 35.0, 17.5]
    root = out["enclosure"]["root"]
    assert root["type"] == "difference" and root["cuts"][1]["type"] == "hole"
    with pytest.raises(DesignError):
        d = examples.get()
        d.pop("board")
        analysis.enclosure_spec(validate(d))


def test_http_api(tmp_path):
    from shannon.app import app
    c = TestClient(app)
    assert c.get("/api/health").json()["service"] == "shannon-hoard"
    assert "Shannon" in c.get("/").text
    d = c.get("/api/examples/machine_sensor").json()
    r = c.post("/api/check", json={"design": d}).json()
    assert r["verdict"] == "clean" and c.get(f"/api/records/{r['record_id']}").json()["design"] == d
    bad = c.get("/api/examples/machine_sensor:five_volt_divider").json()
    assert c.post("/api/check", json={"design": bad}).json()["verdict"] == "errors"
    s = c.post("/api/sensor", json={"design": d, "samples": 300}).json()
    assert s["test_plan"]["points"]
    h = c.post("/api/firmware/header", json={"design": d})
    assert h.status_code == 200 and "#pragma once" in h.text
    e = c.post("/api/enclosure", json={"design": d}).json()
    assert e["enclosure"]["root"]["type"] == "difference"
    k = c.post("/api/import/kicad", json={"netlist": (FIX / "machine-node.net").read_text(), "supplies": [{"net": "+5V", "voltage": 5}]}).json()
    assert k["status"] == "imported"
    q = copy.deepcopy(d)
    q["components"][4].pop("value")
    resp = c.post("/api/check", json={"design": q})
    assert resp.status_code == 422 and resp.json()["detail"]["questions"]
    assert c.get("/api/records/..%2F..").status_code == 404


def test_mcp_lists_tools_without_writing(tmp_path):
    from shannon.mcp_server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"shannon_check", "shannon_sensor_study", "shannon_firmware_header", "shannon_evaluate_measurements",
            "shannon_enclosure", "shannon_import_kicad", "shannon_records", "shannon_examples", "shannon_parts"} <= names
    assert service.records() == []


# ---- regressions from the independent review

def test_parallel_supplies_are_a_conflict_not_a_crash():
    d = examples.get()
    d["components"].append({"ref": "PS2", "kind": "source", "voltage": 5.0})
    d["nets"]["+5V"].append("PS2.+")
    d["nets"]["GND"].append("PS2.-")
    r = service.check(d, save=False)
    assert r["status"] == "checked" and "rail-conflict" in codes(r["issues"])


def test_led_on_a_rail_with_low_side_resistor():
    d = examples.get()
    d["nets"]["LED_DRIVE"] = ["U1.GPIO2"]
    d["nets"]["+5V"].append("D1.A")
    d["nets"]["GND"].remove("D1.K")
    d["nets"]["GND"].append("R2.1")
    d["nets"]["LED_A"] = ["R2.2", "D1.K"]
    d.pop("firmware")
    r = service.check(d, save=False)
    led = r["leds"][0]
    assert led["resistor"] == "R2" and led["current_ma"] == pytest.approx((5.0 - 2.0) / 330 * 1000)
    assert "pin-cannot-drive" not in codes(r["issues"])


def test_divider_flipped_does_not_confuse_the_led():
    d = examples.get()
    d["nets"]["+3V3"] = ["U2.OUT", "U1.3V3", "RT1.2"]
    d["nets"]["GND"] = [m for m in d["nets"]["GND"] if m != "RT1.2"] + ["R1.1"]
    d["nets"]["SENSE"] = ["R1.2", "RT1.1", "C1.1", "U1.GPIO34", "J2.1"]
    r = service.check(d, save=False)
    assert r["leds"][0]["resistor"] == "R2" and r["leds"][0]["drive"] == "U1.GPIO2"
    assert "pin-cannot-drive" not in codes(r["issues"])


def test_board_powered_on_vin_drives_its_own_3v3():
    d = examples.get()
    d["components"] = [c for c in d["components"] if c["ref"] != "U2"]
    d["nets"]["+5V"] = ["PS1.+", "J1.1", "U1.VIN"]
    d["nets"]["GND"] = [m for m in d["nets"]["GND"] if m != "U2.GND"]
    d["nets"]["+3V3"] = ["U1.3V3", "R1.1"]
    r = service.check(d, save=False)
    assert "supply-mismatch" not in codes(r["issues"]) and r["errors"] == 0
    assert r["operating_point"]["volts"]["SENSE"] == pytest.approx(1.65, rel=1e-6)
    assert any(p.get("regulator") == "U1.3V3" for p in r["power"])


def test_uno_analogread_number_means_analog_pin():
    p = firmware.parse("void loop(){ analogRead(0); digitalWrite(13, 1); }", "arduino_uno")
    assert [u["pin"] for u in p["uses"]] == ["A0", "D13"]


def test_uno_ratiometric_reference_cancels_supply_tolerance():
    d = {"name": "uno node", "components": [
        {"ref": "PS1", "kind": "source", "voltage": 5.0, "tolerance": 0.05},
        {"ref": "U1", "kind": "mcu", "part": "arduino_uno"},
        {"ref": "R1", "kind": "resistor", "value": "10k", "tolerance": 0.0},
        {"ref": "RT1", "kind": "ntc", "r25": "10k", "beta": 3950, "tolerance": 0.0, "beta_tolerance": 0.0}],
        "nets": {"+5V": ["PS1.+", "U1.5V", "R1.1"], "GND": ["PS1.-", "U1.GND", "RT1.2"], "SENSE": ["R1.2", "RT1.1", "U1.A0"]},
        "sensor": {"element": "RT1", "range": [0, 80], "step": 1.0, "pin": "U1.A0"}}
    ch = analysis.sensor_chain(validate(d), 300)
    # Only quantisation remains when the divider and the ADC share the rail.
    assert max(r["error_worst_case"] for r in ch["rows"]) <= max(r["resolution"] for r in ch["rows"])


def test_kicad_picoblade_connector_and_uno_pins():
    net = """(export (components
      (comp (ref "J1") (value "Conn_01x02") (footprint "Connector_Molex:Molex_PicoBlade_53047-0210") (libsource (lib "Connector_Generic") (part "Conn_01x02")))
      (comp (ref "U1") (value "Arduino_UNO_R3") (libsource (lib "MCU_Module") (part "Arduino_UNO_R3")))
      (comp (ref "R1") (value "") (libsource (lib "Device") (part "R"))))
      (nets (net (code "1") (name "+5V") (node (ref "J1") (pin "1")) (node (ref "U1") (pin "5") (pinfunction "+5V")))
            (net (code "2") (name "GND") (node (ref "J1") (pin "2")) (node (ref "U1") (pin "29") (pinfunction "GND")))
            (net (code "3") (name "RAW") (node (ref "U1") (pin "28") (pinfunction "VIN")) (node (ref "R1") (pin "1")))))"""
    out = kicad.to_design(net)
    kinds = {c["ref"]: (c["kind"], c.get("part")) for c in out["design"]["components"]}
    assert kinds["J1"] == ("connector", None) and kinds["U1"] == ("mcu", "arduino_uno")
    assert out["design"]["nets"]["+5V"] == ["J1.1", "U1.5V"] and out["design"]["nets"]["RAW"] == ["U1.VIN", "R1.1"]
    assert any("R1" in q for q in out["questions"])


def test_sensor_step_and_pin_validation():
    for bad in ({"step": 0}, {"step": -1}, {"step": 1e-6}, {"pin": "R1.2"}):
        d = examples.get()
        d["sensor"].update(bad)
        with pytest.raises(DesignError):
            validate(d)


def test_header_with_leading_digit_name_compiles_and_flags_rails(tmp_path):
    d = examples.get()
    d["name"] = "2nd floor node"
    ch = analysis.sensor_chain(validate(d), 200)
    gcc = shutil.which("gcc") or shutil.which("cc")
    if not gcc:
        pytest.skip("no C compiler")
    (tmp_path / "t.h").write_text(ch["firmware_table"]["header"])
    (tmp_path / "t.c").write_text('#include <stdio.h>\n#include "t.h"\nint main(void){printf("%d %d %.1f",'
                                  'isnan(s_2ND_FLOOR_NODE_TEMPERATURE_from_code(0)) ? 1 : 0, isnan(s_2nd_floor_node_temperature_from_code(4095)) ? 1 : 0,'
                                  's_2nd_floor_node_temperature_from_code(2047));return 0;}\n'.replace("s_2ND_FLOOR_NODE_TEMPERATURE_from_code", "s_2nd_floor_node_temperature_from_code"))
    subprocess.run([gcc, "-std=c99", "-Wall", "-Werror", "t.c", "-o", "t", "-lm"], cwd=tmp_path, check=True)
    out = subprocess.run([str(tmp_path / "t")], capture_output=True, text=True, check=True).stdout.split()
    assert out[0] == "1" and out[1] == "1" and abs(float(out[2]) - 25) < 0.5


def test_test_points_outside_range_and_readings_without_value():
    d = validate(examples.get())
    ch = analysis.sensor_chain(d, 200)
    with pytest.raises(DesignError):
        analysis.test_plan(d, ch, [{"value": 150}])
    plan = analysis.test_plan(d, ch)
    with pytest.raises(DesignError):
        analysis.evaluate_measurements(plan, [{"codes": [100]}], 12)


def test_firmware_line_numbers_survive_block_comments():
    src = "/* a\nb\nc */\nvoid setup(){\n}\nvoid loop(){ analogRead(34); }\n"
    assert firmware.parse(src, "esp32_devkit_v1")["uses"][0]["line"] == 6
