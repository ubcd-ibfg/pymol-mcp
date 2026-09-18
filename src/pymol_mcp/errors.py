"""Turns a ``PymolBackendError`` (or PyMOL's own quiet return-code failures)
into an actionable message for the agent. PyMOL mostly signals failure by
returning ``None``/``-1``/``0`` or printing to stderr rather than raising, so
most of these checks are pattern-matches on the message text or on the
result value, not exception types.
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError

from .backends.base import PymolBackendError

__all__ = ["PymolToolError", "backend_error_message", "known_objects_hint", "require"]


class PymolToolError(ToolError):
    """Raised by tool code with a message that is already agent-actionable.

    Must subclass the SDK's ``ToolError`` (not a plain ``Exception``): the
    server only forwards an anticipated failure's own message to the client
    when it's a ``ToolError``. Anything else is treated as a crash and
    replaced with a generic "Error executing tool <name>" -- silently
    swallowing whatever actionable text we worked out in errors.py. See
    ``mcp.server.mcpserver.exceptions.ToolError``'s docstring.
    """


def backend_error_message(exc: PymolBackendError, *, context: str = "") -> str:
    text = str(exc)
    lower = text.lower()

    if "connection refused" in lower or "could not reach" in lower:
        return text  # AttachBackend already writes the actionable message

    if "invalid selection" in lower or "selector" in lower and "error" in lower:
        return (
            f"{text}\n"
            "The selection expression could not be parsed. PyMOL selection "
            "syntax examples: 'chain A', 'resi 10-20', 'resn ALA+GLY', "
            "'name CA', 'polymer and not solvent'. Use pymol_list_objects "
            "to see what objects currently exist."
        )

    if "does not exist" in lower or "invalid object" in lower or "not found" in lower:
        suffix = f" ({context})" if context else ""
        return (
            f"{text}{suffix}\n"
            "Use pymol_list_objects to see the objects currently loaded in "
            "this session."
        )

    return text


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PymolToolError(message)


def known_objects_hint(objects: list[str]) -> str:
    if not objects:
        return "No objects are currently loaded. Use pymol_fetch or pymol_load first."
    return f"Currently loaded objects: {', '.join(objects)}."
