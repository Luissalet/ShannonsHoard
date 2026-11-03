"""Examples, parts and generated in-memory artifacts leave no app data."""
import json
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_readonly_helpers_are_declared_and_create_no_data(tmp_path):
    data = tmp_path / 'data'
    params = StdioServerParameters(command=sys.executable, args=['-m', 'shannon.mcp_server'],
        env={**os.environ, 'SHANNON_DATA': str(data)})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            for name in ('shannon_examples', 'shannon_parts', 'shannon_firmware_header', 'shannon_enclosure'):
                assert tools[name].annotations.model_dump(by_alias=True)['readOnlyHint'] is True
            for name in ('shannon_check', 'shannon_sensor_study', 'shannon_evaluate_measurements'):
                ann = tools[name].annotations
                assert ann is None or ann.model_dump(by_alias=True).get('readOnlyHint') is not True
            async def call(name, arguments):
                result = await session.call_tool(name, arguments)
                assert not result.is_error
                return json.loads(next(block.text for block in result.content if block.type == 'text'))
            design = await call('shannon_examples', {'example_id': 'machine_sensor'})
            assert await call('shannon_parts', {})
            assert (await call('shannon_firmware_header', {'design': design}))['status'] == 'ok'
            assert (await call('shannon_enclosure', {'design': design}))['status'] == 'ok'
    assert not data.exists(), 'Readonly helpers unexpectedly created app data'
