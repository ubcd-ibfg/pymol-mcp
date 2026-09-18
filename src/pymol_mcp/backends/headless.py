"""In-process PyMOL session via ``pymol2.PyMOL()``.

This is the default backend: it needs no display, no GUI, and no separate
process to manage. ``pymol`` is imported lazily inside ``start()`` so that
importing this module (and thus the whole ``pymol_mcp`` package) never
requires PyMOL to be installed -- only actually using headless mode does.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

from .base import PymolBackendError

# Settings applied once at startup so headless rendering behaves predictably
# with no display attached and no GUI chrome to strip out of screenshots.
_BASELINE_SETTINGS: dict[str, Any] = {
    "internal_gui": 0,
    "internal_feedback": 0,
    "ray_opaque_background": 0,
    "assembly": "",
}


class HeadlessBackend:
    """Owns one ``pymol2.PyMOL()`` instance for the lifetime of the server."""

    def __init__(self, fetch_dir: str | None = None) -> None:
        self._pymol: Any = None
        self._fetch_dir = fetch_dir

    def start(self) -> None:
        try:
            import pymol2
        except ImportError as exc:  # pragma: no cover - exercised via message, not import
            raise PymolBackendError(
                "PyMOL is not installed in this Python environment. Headless mode "
                "requires the 'pymol' / 'pymol2' package (install via "
                "`conda install -c conda-forge pymol-open-source`, or "
                "`pip install pymol-open-source-whl`). Alternatively, run with "
                "--attach to drive a separately-running PyMOL GUI instead."
            ) from exc

        self._pymol = pymol2.PyMOL()
        self._pymol.start()
        cmd = self._pymol.cmd
        for name, value in _BASELINE_SETTINGS.items():
            cmd.set(name, value)
        if self._fetch_dir:
            Path(self._fetch_dir).mkdir(parents=True, exist_ok=True)
            cmd.set("fetch_path", self._fetch_dir)

    def _require_started(self) -> Any:
        if self._pymol is None:
            raise PymolBackendError("Headless PyMOL session was not started.")
        return self._pymol.cmd

    def call(self, fn: str, *args: Any, **kwargs: Any) -> Any:
        cmd = self._require_started()
        target = getattr(cmd, fn, None)
        if target is None or not callable(target):
            raise PymolBackendError(f"cmd.{fn} does not exist.")
        try:
            return target(*args, **kwargs)
        except Exception as exc:
            raise PymolBackendError(str(exc)) from exc

    def do(self, command: str) -> str:
        cmd = self._require_started()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                cmd.do(command, echo=0)
        except Exception as exc:
            raise PymolBackendError(str(exc)) from exc
        return buf.getvalue().strip()

    def eval_json(self, code: str, **variables: Any) -> Any:
        cmd = self._require_started()
        namespace: dict[str, Any] = {"cmd": cmd, **variables}
        try:
            exec(code, namespace)  # noqa: S102 - trusted, server-authored snippets only
        except Exception as exc:
            raise PymolBackendError(str(exc)) from exc
        if "result" not in namespace:
            raise PymolBackendError(
                "Internal error: eval_json snippet did not assign to 'result'."
            )
        try:
            return json.loads(json.dumps(namespace["result"], default=_json_default))
        except (TypeError, ValueError) as exc:
            raise PymolBackendError(f"Result is not JSON-serializable: {exc}") from exc

    def close(self) -> None:
        if self._pymol is not None:
            with contextlib.suppress(Exception):
                self._pymol.stop()
            self._pymol = None


def _json_default(obj: Any) -> Any:
    # numpy scalars/arrays show up in some cmd.get_* results depending on
    # PyMOL build; coerce them to plain Python without importing numpy
    # unconditionally.
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if hasattr(obj, "item"):
        return obj.item()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
