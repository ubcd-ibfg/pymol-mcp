"""Escape hatches for the long tail of PyMOL's ~500 commands that don't have
a dedicated typed tool.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..models import CommandResult, PythonExecResult
from ._util import get_session, pymol_errors

_PYTHON_EXEC_WRAPPER = """\
import io, contextlib
_buf = io.StringIO()
_result = None
with contextlib.redirect_stdout(_buf):
{body}
result = {{"stdout": _buf.getvalue(), "value": _result}}
"""


def register(mcp: MCPServer, *, allow_python_exec: bool) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Run a raw PyMOL command",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    async def pymol_run_command(
        ctx: Context,
        command: Annotated[
            str,
            Field(
                description="Any PyMOL command line, exactly as typed at the PyMOL prompt, e.g. "
                "'isosurface surf1, map1, 1.0' or 'dss' or 'remove solvent'."
            ),
        ],
    ) -> CommandResult:
        """Run any PyMOL command not covered by a dedicated tool. Covers the
        long tail of PyMOL's command set (map operations, dss, sculpting,
        symmetry, etc.). Prefer a dedicated tool when one exists -- it gives
        you validated inputs and structured output instead of raw text."""
        session = get_session(ctx)
        async with pymol_errors(context=f"running '{command}'"):
            output = await session.do(command)
        return CommandResult(output=output)

    if not allow_python_exec:
        return

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Run arbitrary Python in the PyMOL session",
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    async def pymol_run_python(
        ctx: Context,
        code: Annotated[
            str,
            Field(
                description="Python code executed inside the PyMOL session, with `cmd` bound. "
                "Assign a JSON-serializable value to `_result` to return it. Printed output is "
                "captured and returned too."
            ),
        ],
    ) -> PythonExecResult:
        """Execute arbitrary Python code inside the PyMOL session -- `cmd` is
        bound, so this can do anything the typed tools can plus custom
        numpy/iterate logic. ONLY REGISTERED because the server was started
        with --allow-python-exec: this is full code execution on the host
        machine as the user running the server, not sandboxed."""
        session = get_session(ctx)
        indented = "\n".join(f"    {line}" for line in code.splitlines()) or "    pass"
        wrapped = _PYTHON_EXEC_WRAPPER.format(body=indented)
        async with pymol_errors(context="running python code"):
            result = await session.eval_json(wrapped)
        return PythonExecResult(**result)
