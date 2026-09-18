"""Builds the MCPServer instance: backend selection, session lifespan, and
tool registration. Entry point is ``__main__.py``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.mcpserver import MCPServer

from .backends import AttachBackend, HeadlessBackend
from .backends.base import PymolBackend, PymolBackendError
from .session import PymolSession

logger = logging.getLogger("pymol_mcp")


@dataclass
class AppContext:
    session: PymolSession
    allow_python_exec: bool


@dataclass
class ServerOptions:
    mode: str = "headless"  # "headless" | "attach"
    attach_host: str = "localhost"
    attach_port: int = 9123
    fetch_dir: str | None = None
    allow_python_exec: bool = False


def _make_backend(options: ServerOptions) -> PymolBackend:
    if options.mode == "attach":
        return AttachBackend(host=options.attach_host, port=options.attach_port)
    return HeadlessBackend(fetch_dir=options.fetch_dir)


def create_server(options: ServerOptions) -> MCPServer:
    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[AppContext]:
        backend = _make_backend(options)
        session = PymolSession(backend)
        logger.info("Starting PyMOL session (mode=%s)...", options.mode)
        try:
            await session.start()
        except PymolBackendError as exc:
            logger.error("Failed to start PyMOL session: %s", exc)
            raise
        logger.info("PyMOL session ready.")
        try:
            yield AppContext(session=session, allow_python_exec=options.allow_python_exec)
        finally:
            await session.close()
            logger.info("PyMOL session closed.")

    mcp = MCPServer(
        "pymol_mcp",
        instructions=(
            "Drives a PyMOL molecular visualization/analysis session. "
            "Start by loading a structure with pymol_fetch (PDB ID) or "
            "pymol_load (local file), then use pymol_list_objects to see "
            "what is loaded. pymol_render_image returns a viewable PNG so "
            "you can see the current scene. Use pymol_run_command for any "
            "PyMOL command not covered by a dedicated tool."
        ),
        lifespan=lifespan,
    )

    _register_all_tools(mcp, options)
    return mcp


def _register_all_tools(mcp: MCPServer, options: ServerOptions) -> None:
    from .tools import (
        analysis,
        camera,
        export,
        raw,
        rendering,
        selections,
        structures,
        styling,
    )

    structures.register(mcp)
    selections.register(mcp)
    styling.register(mcp)
    camera.register(mcp)
    rendering.register(mcp)
    analysis.register(mcp)
    export.register(mcp)
    raw.register(mcp, allow_python_exec=options.allow_python_exec)
