"""Backend protocol: the interface every PyMOL driver (headless or attach)
implements. Tools are written against this interface, never against
``pymol.cmd`` or an ``xmlrpc.client.ServerProxy`` directly, so the same tool
code works whether PyMOL is running in-process or as a separate GUI attached
over RPC.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class PymolBackendError(Exception):
    """Raised when a PyMOL call fails. Carries the raw PyMOL-side message so
    ``errors.py`` can turn it into an actionable message for the agent."""


@runtime_checkable
class PymolBackend(Protocol):
    """Synchronous backend interface. Callers on the MCP server side always
    go through ``session.py``, which runs these methods on the single
    PyMOL-owning worker thread -- implementations here do not need to be
    thread-safe themselves, only *consistent* about which thread they use
    internally (headless mode pins itself to whichever thread starts it;
    attach mode is a plain network client and thread-agnostic)."""

    def start(self) -> None:
        """Establish the session (start the embedded PyMOL instance, or
        connect to and verify a remote RPC server). Called once by
        ``PymolSession.start()``."""
        ...

    def call(self, fn: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke ``cmd.<fn>(*args, **kwargs)`` and return its result.

        Only JSON-marshalable arguments/return values are guaranteed to
        survive attach mode (XML-RPC). For anything else (dicts populated by
        ``space=``, ChemPy model objects, numpy arrays, ...) use
        ``eval_json`` instead.
        """
        ...

    def do(self, command: str) -> str:
        """Run a raw PyMOL command line (as typed at the PyMOL prompt) and
        return any captured text output."""
        ...

    def eval_json(self, code: str, **variables: Any) -> Any:
        """Execute a Python snippet inside the PyMOL session and return a
        JSON-decoded value.

        The snippet must assign to a local variable named ``result``.
        ``variables`` are made available as locals inside the snippet (only
        JSON-marshalable values -- they cross the same boundary attach mode
        would need to cross).

        This is the primitive that makes ``cmd.iterate(space=...)`` and
        ``cmd.get_model()`` usable from both backends: headless just execs
        the snippet locally, attach mode ships it to the remote process,
        writes the JSON-encoded result to a local temp file, and reads that
        file back -- because XML-RPC itself cannot marshal a ChemPy object
        or a dict populated by side effect.
        """
        ...

    def close(self) -> None:
        """Release any resources (stop the embedded session / drop the RPC
        connection). Idempotent."""
        ...
