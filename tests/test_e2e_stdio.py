"""End-to-end test: spawns the real `pymol-mcp` server as a subprocess and
drives it over the actual stdio MCP protocol with the official client SDK.
This is the test that matters most -- it exercises the full stack (CLI ->
lifespan -> HeadlessBackend -> pymol2 -> tool -> structured output) exactly
as a real MCP client would.

Requires network access (pymol_fetch hits the RCSB PDB) and a working
headless PyMOL install, same as the server itself.

Note: the client session is opened with a plain ``async with`` inside each
test body rather than a pytest-asyncio fixture. `stdio_client`'s anyio task
group ties its cancel scope to the specific asyncio Task that entered it;
pytest-asyncio's async-generator-fixture teardown can resume in a different
Task, which anyio then rejects ("Attempted to exit cancel scope in a
different task than it was entered in") even though the test itself already
passed. Keeping setup and teardown in the test's own coroutine sidesteps
that entirely -- it's a test-harness wrinkle in the client, not a server bug.
"""

from __future__ import annotations

import sys
import tempfile
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@asynccontextmanager
async def _connected_session():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "pymol_mcp", "--allow-python-exec", "--fetch-dir", tempfile.mkdtemp()],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def test_lists_all_tools_including_python_exec():
    async with _connected_session() as session:
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert "pymol_fetch" in names
        assert "pymol_render_image" in names
        assert "pymol_run_python" in names  # only because --allow-python-exec was passed


async def test_fetch_then_render_scene():
    async with _connected_session() as session:
        r = await session.call_tool("pymol_fetch", {"pdb_id": "1ubq", "type": "pdb"})
        assert not r.is_error, r.content
        assert r.structured_content["n_atoms"] == 660

        r = await session.call_tool("pymol_show_as", {"representation": "cartoon", "selection": "1ubq"})
        assert not r.is_error

        r = await session.call_tool("pymol_spectrum", {"expression": "b", "selection": "1ubq"})
        assert not r.is_error

        r = await session.call_tool("pymol_orient", {"selection": "1ubq"})
        assert not r.is_error

        r = await session.call_tool("pymol_render_image", {"width": 300, "height": 200})
        assert not r.is_error
        images = [c for c in r.content if c.type == "image"]
        assert len(images) == 1
        assert len(images[0].data) > 1000  # a real PNG, not an empty stub


async def test_iterate_atoms_is_paginated():
    async with _connected_session() as session:
        await session.call_tool("pymol_fetch", {"pdb_id": "1ubq", "type": "pdb"})
        r = await session.call_tool("pymol_iterate_atoms", {"selection": "1ubq", "limit": 10})
        assert not r.is_error
        body = r.structured_content
        assert body["count"] == 10
        assert body["total"] == 660
        assert body["has_more"] is True


async def test_align_self_is_a_clean_tool_error():
    async with _connected_session() as session:
        await session.call_tool("pymol_fetch", {"pdb_id": "1ubq", "type": "pdb"})
        r = await session.call_tool("pymol_align", {"mobile": "1ubq", "target": "1ubq", "cycles": 0})
        assert r.is_error
        assert r.content and r.content[0].text  # actionable text reached the client, not swallowed


async def test_unknown_selection_gives_actionable_error():
    async with _connected_session() as session:
        r = await session.call_tool("pymol_count_atoms", {"selection": "totally_bogus_object_xyz"})
        assert r.is_error
        text = r.content[0].text
        assert "pymol_list_objects" in text  # our actionable hint, not the SDK's generic wrapper text


async def test_run_python_captures_stdout_and_value():
    async with _connected_session() as session:
        await session.call_tool("pymol_fetch", {"pdb_id": "1ubq", "type": "pdb"})
        r = await session.call_tool(
            "pymol_run_python",
            {"code": "_result = cmd.count_atoms('1ubq')\nprint('hi')"},
        )
        assert not r.is_error
        assert r.structured_content["value"] == 660
        assert r.structured_content["stdout"].strip() == "hi"


async def test_create_object_then_align_two_chains():
    # A named selection (pymol_select) is just a tag on an existing object's
    # atoms, not an independent object -- cmd.align needs two real objects.
    # This is what pymol_create_object is for; regression-test the pairing.
    async with _connected_session() as session:
        r = await session.call_tool("pymol_fetch", {"pdb_id": "4hhb", "type": "pdb", "object_name": "hhb"})
        assert not r.is_error

        r = await session.call_tool("pymol_create_object", {"name": "a", "selection": "hhb and chain A and polymer"})
        assert not r.is_error
        assert r.structured_content["n_atoms"] == 1069

        r = await session.call_tool("pymol_create_object", {"name": "c", "selection": "hhb and chain C and polymer"})
        assert not r.is_error
        assert r.structured_content["n_atoms"] == 1069

        r = await session.call_tool("pymol_align", {"mobile": "a", "target": "c", "cycles": 0})
        assert not r.is_error, r.content
        assert round(r.structured_content["rmsd_refined"], 2) == 0.62
        assert r.structured_content["n_atoms_refined"] == 1069


async def test_sasa_and_center_of_mass():
    async with _connected_session() as session:
        await session.call_tool("pymol_fetch", {"pdb_id": "1ubq", "type": "pdb"})
        r = await session.call_tool("pymol_sasa", {"selection": "1ubq"})
        assert not r.is_error
        assert r.structured_content["area_A2"] > 0

        r = await session.call_tool("pymol_center_of_mass", {"selection": "1ubq"})
        assert not r.is_error
        assert set(r.structured_content) == {"x", "y", "z"}
