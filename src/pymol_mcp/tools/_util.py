"""Shared helpers used by every tool module: pulling the PymolSession out of
the request's lifespan context, and turning backend failures into
actionable tool errors.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from mcp.server.mcpserver import Context

from ..backends.base import PymolBackendError
from ..errors import PymolToolError, backend_error_message
from ..session import PymolSession

if TYPE_CHECKING:
    from ..server import AppContext


def get_session(ctx: Context) -> PymolSession:
    app: AppContext = ctx.request_context.lifespan_context
    return app.session


@contextlib.asynccontextmanager
async def pymol_errors(context: str = "") -> AsyncIterator[None]:
    """Wrap a block of backend calls, re-raising ``PymolBackendError`` as a
    ``PymolToolError`` with an actionable message. The MCP server turns any
    exception raised from a tool into an ``is_error`` tool result carrying
    ``str(exc)``, so this is the only error-handling tools need to do."""
    try:
        yield
    except PymolBackendError as exc:
        raise PymolToolError(backend_error_message(exc, context=context)) from exc
