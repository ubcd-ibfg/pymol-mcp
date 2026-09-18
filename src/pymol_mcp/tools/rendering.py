"""Ray-traced rendering. This is the tool that makes the server worth using:
it lets the agent actually *see* the molecular scene it has built, as an
inline PNG.

Implementation note: both backends render to a real file path rather than
trying to marshal raw PNG bytes back through ``call``/``eval_json``. Headless
mode could return bytes directly (``cmd.png('')`` supports that), but attach
mode cannot -- XML-RPC only carries primitives, and bytes aren't one. Since
attach mode is documented as same-machine-only (the client and the PyMOL GUI
share a filesystem), writing to a temp path and reading it back locally works
identically for both backends and avoids a second code path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver import Context, Image, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ._util import get_session, pymol_errors

MAX_DIMENSION = 2400


def register(mcp: MCPServer) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Render an image of the current scene",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_render_image(
        ctx: Context,
        width: Annotated[int, Field(description="Image width in pixels.", ge=50, le=MAX_DIMENSION)] = 1000,
        height: Annotated[int, Field(description="Image height in pixels.", ge=50, le=MAX_DIMENSION)] = 750,
        dpi: Annotated[int, Field(description="Resolution in dots per inch.", ge=50, le=600)] = 150,
        ray_trace: Annotated[
            bool, Field(description="Ray-trace for publication quality (slower). If false, uses the faster rasterizer.")
        ] = True,
    ) -> Image:
        """Ray-trace the current scene and return it as a viewable PNG image.
        Use pymol_orient/pymol_zoom first to frame the shot, and
        pymol_show_as/pymol_color to set up the representation. For a
        permanent file instead of an inline image, use pymol_save_png."""
        session = get_session(ctx)
        with tempfile.TemporaryDirectory(prefix="pymol_mcp_render_") as tmp_dir:
            path = Path(tmp_dir) / "render.png"
            async with pymol_errors(context="rendering image"):
                await session.call(
                    "png",
                    str(path),
                    width=width,
                    height=height,
                    dpi=dpi,
                    ray=int(ray_trace),
                    quiet=1,
                )
            data = path.read_bytes()
        return Image(data=data, format="png")
