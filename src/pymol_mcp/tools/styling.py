"""Visual representation: show/hide, coloring, and settings."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..models import Representation
from ._util import get_session, pymol_errors


def register(mcp: MCPServer) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Show representation",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_show(
        ctx: Context,
        representation: Representation,
        selection: Annotated[str, Field(description="Object or selection to show.")] = "all",
    ) -> str:
        """Turn on a representation (cartoon, sticks, spheres, ...) for a
        selection, in addition to whatever is already shown."""
        session = get_session(ctx)
        async with pymol_errors(context=f"showing {representation.value} on '{selection}'"):
            await session.call("show", representation.value, selection)
        return f"Showing {representation.value} for '{selection}'."

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Hide representation",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_hide(
        ctx: Context,
        representation: Representation,
        selection: Annotated[str, Field(description="Object or selection to hide.")] = "all",
    ) -> str:
        """Turn off a representation for a selection."""
        session = get_session(ctx)
        async with pymol_errors(context=f"hiding {representation.value} on '{selection}'"):
            await session.call("hide", representation.value, selection)
        return f"Hid {representation.value} for '{selection}'."

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Show as (replace all representations)",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_show_as(
        ctx: Context,
        representation: Representation,
        selection: Annotated[str, Field(description="Object or selection.")] = "all",
    ) -> str:
        """Show only this representation for a selection, replacing whatever
        was shown before (e.g. switch a whole object to cartoon)."""
        session = get_session(ctx)
        async with pymol_errors(context=f"show_as {representation.value} on '{selection}'"):
            await session.call("show_as", representation.value, selection)
        return f"'{selection}' now shown as {representation.value} only."

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Color selection",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_color(
        ctx: Context,
        color: Annotated[
            str,
            Field(description="PyMOL color name (e.g. 'red', 'skyblue', 'yellow') or hex RGB (e.g. '0xFF8800')."),
        ],
        selection: Annotated[str, Field(description="Object or selection to color.")] = "all",
    ) -> str:
        """Set a flat color on a selection."""
        session = get_session(ctx)
        async with pymol_errors(context=f"coloring '{selection}'"):
            await session.call("color", color, selection)
        return f"Colored '{selection}' {color}."

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Spectrum color",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_spectrum(
        ctx: Context,
        selection: Annotated[str, Field(description="Object or selection to color.")] = "all",
        expression: Annotated[
            str,
            Field(description="Value to map across the palette: 'b' (b-factor), 'q' (occupancy), 'count', 'resi', 'chain'."),
        ] = "count",
        palette: Annotated[
            str, Field(description="Color palette name, e.g. 'rainbow', 'blue_white_red', 'red_white_blue'.")
        ] = "rainbow",
    ) -> str:
        """Color a selection along a gradient by some per-atom value, such as
        b-factor (useful for visualizing confidence scores like pLDDT) or
        residue index."""
        session = get_session(ctx)
        async with pymol_errors(context=f"spectrum coloring '{selection}'"):
            await session.call("spectrum", expression, palette, selection)
        return f"Applied '{palette}' spectrum over '{expression}' to '{selection}'."

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set background color",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_bg_color(
        ctx: Context,
        color: Annotated[str, Field(description="PyMOL color name or hex RGB.")] = "white",
    ) -> str:
        """Set the viewport/render background color."""
        session = get_session(ctx)
        async with pymol_errors():
            await session.call("bg_color", color)
        return f"Background set to {color}."

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set a PyMOL setting",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_set(
        ctx: Context,
        name: Annotated[str, Field(description="Setting name, e.g. 'cartoon_transparency', 'sphere_scale', 'ray_trace_mode'.")],
        value: Annotated[str, Field(description="Value to assign, as PyMOL would parse it (e.g. '0.5', 'on', '1').")],
        selection: Annotated[
            str | None,
            Field(description="Restrict the setting to this object/selection instead of applying globally."),
        ] = None,
    ) -> str:
        """Change a PyMOL setting, globally or scoped to one object/selection.
        See pymol.org's Setting reference for the full list of names."""
        session = get_session(ctx)
        async with pymol_errors(context=f"setting '{name}'"):
            if selection:
                await session.call("set", name, value, selection)
            else:
                await session.call("set", name, value)
        scope = f" for '{selection}'" if selection else ""
        return f"Set {name} = {value}{scope}."
