"""Wiring and power-budget regressions found by independent review."""
import copy

import pytest

from shannon import examples, service


def cascade():
    d = examples.get()
    for c in d["components"]:
        if c["ref"] == "U2": c["max_ma"] = 100
        if c["ref"] == "PS1": c["max_ma"] = 2000
    d["components"].extend([
        {"ref":"U3","kind":"regulator","vout":1.8,"dropout":0.2,"max_ma":1000,"quiescent_ma":0},
        {"ref":"LOAD","kind":"generic","pins":["VCC","GND"],"current_ma":500,"rail":"+1V8"}])
    d["nets"]["+3V3"].append("U3.IN")
    d["nets"]["GND"].extend(["U3.GND","LOAD.GND"])
    d["nets"]["+1V8"] = ["U3.OUT","LOAD.VCC"]
    return d


def test_mcu_missing_ground_is_a_wiring_error_without_an_invented_operating_point():
    d = examples.get()
    d["nets"]["GND"].remove("U1.GND")
    result = service.check(d,save=False)
    assert result["verdict"] == "errors"
    assert any(i["code"] == "mcu-ground-unwired" for i in result["issues"])
    assert result["operating_point"] is None


def test_mcu_supply_and_pin_voltages_are_relative_to_its_own_ground():
    d = examples.get()
    d["nets"]["GND"].remove("U1.GND")
    d["nets"]["+3V3"].append("U1.GND")
    result = service.check(d,save=False)
    assert result["verdict"] == "errors"
    assert any(i["code"] == "supply-mismatch" for i in result["issues"])


@pytest.mark.parametrize("reverse",[False,True])
def test_regulator_current_includes_downstream_regulators_in_any_component_order(reverse):
    d = cascade()
    if reverse: d["components"].reverse()
    result = service.check(d,save=False)
    assert any(i["code"] == "regulator-overload" and i.get("where") == "U2" for i in result["issues"])
    up = next(x for x in result["power"] if x.get("regulator") == "U2")
    source = next(x for x in result["power"] if x.get("source") == "PS1")
    assert up["load_ma"] == pytest.approx(584.10439394)
    assert source["load_ma"] == pytest.approx(up["load_ma"]+5)
    assert up["load_ma"] == pytest.approx(sum(i for _,i in up["loads"]))


def test_board_regulator_also_receives_downstream_external_regulator_loads():
    d = cascade()
    d["components"] = [c for c in d["components"] if c["ref"] != "U2"]
    d["nets"]["+5V"].remove("U2.IN")
    d["nets"]["+5V"].append("U1.VIN")
    d["nets"]["+3V3"].remove("U2.OUT")
    d["nets"]["GND"].remove("U2.GND")
    result = service.check(d,save=False)
    assert any(i["code"] == "board-regulator-overload" for i in result["issues"])
    board = next(x for x in result["power"] if x.get("regulator") == "U1.3V3")
    assert board["load_ma"] > 500


def test_converter_cycle_is_reported_without_circulating_free_power():
    d = cascade()
    d["nets"]["+5V"].remove("U2.IN")
    d["nets"]["+1V8"].append("U2.IN")
    result = service.check(d,save=False)
    assert result["status"] == "invalid" and "cycle" in result["error"].lower()


def test_different_measurements_in_one_second_do_not_overwrite_a_saved_result(tmp_path,monkeypatch):
    import datetime
    fixed = datetime.datetime(2026,11,3,tzinfo=datetime.timezone.utc)
    class Clock(datetime.datetime):
        @classmethod
        def now(cls,tz=None): return fixed
    monkeypatch.setenv("SHANNON_DATA",str(tmp_path))
    monkeypatch.setattr(service.dt,"datetime",Clock)
    d = examples.get()
    first = service.measurements(d,[{"value":25,"code":2048}])
    original = service.record(first["record_id"])
    second = service.measurements(d,[{"value":25,"code":4095}])
    assert first["verdict"] == "pass" and second["verdict"] == "fail"
    assert first["record_id"] != second["record_id"]
    assert service.record(first["record_id"]) == original
    assert len(service.records()) == 2


@pytest.fixture
def anyio_backend(): return "asyncio"


@pytest.mark.anyio
async def test_ground_and_cascade_checks_through_real_mcp(tmp_path):
    import json, os, sys
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    root = tmp_path / "mcp"
    params = StdioServerParameters(command=sys.executable,args=["-m","shannon.mcp_server"],
        env={**os.environ,"SHANNON_DATA":str(root)})
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            assert len((await session.list_tools()).tools) == 9
            assert not root.exists()
            design = examples.get()
            design["nets"]["GND"].remove("U1.GND")
            result = await session.call_tool("shannon_check",{"design":design})
            assert not result.is_error
            answer = json.loads(next(b.text for b in result.content if b.type=="text"))
            assert answer["verdict"] == "errors" and answer["operating_point"] is None
            result = await session.call_tool("shannon_check",{"design":cascade()})
            assert not result.is_error
            answer = json.loads(next(b.text for b in result.content if b.type=="text"))
            assert any(i["code"]=="regulator-overload" for i in answer["issues"])
