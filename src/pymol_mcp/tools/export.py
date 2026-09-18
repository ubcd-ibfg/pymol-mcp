"""Saving sessions and exporting structures/images to disk or inline text."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..errors import require
from ..models import ExportFormat, ExportResult
from ._util import get_session, pymol_errors

MAX_INLINE_CHARS = 200_000  # ~200KB of structure text before we insist on a path=


def register(mcp: MCPServer) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Save session file",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_save_session(
        ctx: Context,
        path: Annotated[str, Field(description="Output path for the PyMOL session (.pse).")],
    ) -> str:
        """Save the entire session (all objects, views, representations,
        colors) as a .pse file that can be reopened in PyMOL's GUI later."""
        session = get_session(ctx)
        if not path.endswith(".pse"):
            path += ".pse"
        async with pymol_errors(context=f"saving session to '{path}'"):
            await session.call("save", path)
        return path

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Export structure",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_export_structure(
        ctx: Context,
        selection: Annotated[str, Field(description="Object or selection to export.")],
        format: ExportFormat,
        path: Annotated[
            str | None,
            Field(description="Output file path. If omitted, the content is returned inline (small structures only)."),
        ] = None,
    ) -> ExportResult:
        """Export a structure to a file, or return its content inline as
        text when no path is given (refused for large structures -- pass a
        path instead)."""
        session = get_session(ctx)
        suffix = format.value
        if path:
            async with pymol_errors(context=f"exporting '{selection}' to '{path}'"):
                await session.call("save", path, selection)
            return ExportResult(path=path, format=suffix)

        with tempfile.TemporaryDirectory(prefix="pymol_mcp_export_") as tmp_dir:
            tmp_path = Path(tmp_dir) / f"export.{suffix}"
            async with pymol_errors(context=f"exporting '{selection}'"):
                await session.call("save", str(tmp_path), selection)
            content = tmp_path.read_text()
        require(
            len(content) <= MAX_INLINE_CHARS,
            f"Exported {suffix.upper()} content is {len(content)} characters, too large to return inline "
            f"(limit {MAX_INLINE_CHARS}). Pass a path= to write it to disk instead.",
        )
        return ExportResult(content=content, format=suffix)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Save a rendered image to disk",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_save_png(
        ctx: Context,
        path: Annotated[str, Field(description="Output path for the PNG file.")],
        width: Annotated[int, Field(description="Image width in pixels.", ge=50, le=4800)] = 1500,
        height: Annotated[int, Field(description="Image height in pixels.", ge=50, le=4800)] = 1125,
        dpi: Annotated[int, Field(description="Resolution in dots per inch.", ge=50, le=1200)] = 300,
    ) -> str:
        """Ray-trace the current scene and save it as a PNG file on disk (for
        a permanent output rather than an inline preview, use this instead
        of pymol_render_image; higher resolution ceilings are allowed here
        since the result isn't shipped back through the protocol)."""
        session = get_session(ctx)
        if not path.endswith(".png"):
            path += ".png"
        async with pymol_errors(context=f"saving image to '{path}'"):
            await session.call("png", path, width=width, height=height, dpi=dpi, ray=1, quiet=1)
        return path
