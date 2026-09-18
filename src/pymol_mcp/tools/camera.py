"""Camera/view control."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..models import ViewMatrix
from ._util import get_session, pymol_errors


def register(mcp: MCPServer) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Orient camera to selection",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_orient(
        ctx: Context,
        selection: Annotated[str, Field(description="Object or selection to orient the camera around.")] = "all",
    ) -> str:
        """Reorient the camera along the principal axes of a selection --
        PyMOL's standard 'best fit' view for a structure."""
        session = get_session(ctx)
        async with pymol_errors(context=f"orienting to '{selection}'"):
            await session.call("orient", selection)
        return f"Oriented camera to '{selection}'."

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Zoom to selection",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_zoom(
        ctx: Context,
        selection: Annotated[str, Field(description="Object or selection to zoom to.")] = "all",
        buffer: Annotated[float, Field(description="Extra margin (Angstroms) around the selection.", ge=0)] = 3.0,
    ) -> str:
        """Zoom the camera to fit a selection, without changing its
        orientation."""
        session = get_session(ctx)
        async with pymol_errors(context=f"zooming to '{selection}'"):
            await session.call("zoom", selection, buffer)
        return f"Zoomed to '{selection}' (buffer={buffer})."

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Center view on selection",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_center(
        ctx: Context,
        selection: Annotated[str, Field(description="Object or selection to center on.")] = "all",
    ) -> str:
        """Center the camera on a selection without changing zoom level."""
        session = get_session(ctx)
        async with pymol_errors(context=f"centering on '{selection}'"):
            await session.call("center", selection)
        return f"Centered on '{selection}'."

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Turn camera",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_turn(
        ctx: Context,
        axis: Annotated[str, Field(description="Axis to rotate around: 'x', 'y', or 'z'.", pattern="^[xyzXYZ]$")],
        angle: Annotated[float, Field(description="Degrees to rotate.")],
    ) -> str:
        """Rotate the camera around an axis by a number of degrees."""
        session = get_session(ctx)
        async with pymol_errors():
            await session.call("turn", axis.lower(), angle)
        return f"Turned {angle} degrees around {axis.lower()}."

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get current view",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_get_view(ctx: Context) -> ViewMatrix:
        """Get the current camera view as an 18-float matrix. Save this
        before exploring so you can return to it exactly with
        pymol_set_view."""
        session = get_session(ctx)
        async with pymol_errors():
            matrix = await session.call("get_view")
        return ViewMatrix(matrix=list(matrix))

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set view",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_set_view(
        ctx: Context,
        matrix: Annotated[
            list[float],
            Field(description="18-float view matrix as returned by pymol_get_view.", min_length=18, max_length=18),
        ],
    ) -> str:
        """Restore a camera view previously captured with pymol_get_view."""
        session = get_session(ctx)
        async with pymol_errors():
            await session.call("set_view", tuple(matrix))
        return "View restored."
