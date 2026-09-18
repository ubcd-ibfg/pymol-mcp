"""Bridge to a separately-running PyMOL GUI via its built-in XML-RPC server
(``pymol -R``, default port 9123 -- see ``pymol.rpc.launch_XMLRPC``). No
plugin install needed: the RPC server ships with PyMOL itself and exposes
``cmd`` directly (``server.register_instance(cmd)``), so any ``cmd.<fn>``
call is already a remote method.

XML-RPC can only marshal primitives (str/int/float/bool/list/dict/None), so
two things need a workaround, both solved the same way -- writing a small
Python script to a local temp file and having the remote PyMOL ``run`` it:

* ``call()`` with non-primitive results (e.g. ``cmd.get_model()``).
* ``eval_json()`` in general (``cmd.iterate(..., space=...)`` writes into a
  dict rather than returning one; that dict has to be captured and shipped
  back some other way).

Because both processes are on the same machine, the filesystem is a valid
side channel: the remote script writes its JSON result to a file, and we
read that file back locally once ``run`` returns.
"""

from __future__ import annotations

import json
import tempfile
import time
import uuid
import xmlrpc.client
from pathlib import Path
from typing import Any

from .base import PymolBackendError

DEFAULT_PORT = 9123
_RESULT_POLL_INTERVAL = 0.05
_RESULT_POLL_TIMEOUT = 60.0

_REMOTE_SCRIPT_TEMPLATE = """\
import contextlib, io, json

def _default(o):
    if hasattr(o, "tolist"):
        return o.tolist()
    if hasattr(o, "item"):
        return o.item()
    return str(o)

_buf = io.StringIO()
_payload = {{"ok": True, "result": None, "stdout": ""}}
try:
    with contextlib.redirect_stdout(_buf), contextlib.redirect_stderr(_buf):
{body}
    _payload["result"] = result if "result" in dir() else None
except Exception as _exc:  # noqa: BLE001
    _payload = {{"ok": False, "error": str(_exc), "stdout": _buf.getvalue()}}
else:
    _payload["stdout"] = _buf.getvalue()

with open({out_path!r}, "w") as _f:
    json.dump(_payload, _f, default=_default)
with open({done_path!r}, "w") as _f:
    _f.write("1")
"""


class AttachBackend:
    """Talks to a live PyMOL GUI over XML-RPC instead of owning a session."""

    def __init__(self, host: str = "localhost", port: int = DEFAULT_PORT) -> None:
        self._host = host
        self._port = port
        self._srv: xmlrpc.client.ServerProxy | None = None
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="pymol_mcp_attach_"))

    def start(self) -> None:
        url = f"http://{self._host}:{self._port}"
        self._srv = xmlrpc.client.ServerProxy(url, allow_none=True)
        try:
            self._srv.get_version()
        except (ConnectionRefusedError, OSError, xmlrpc.client.Fault) as exc:
            raise PymolBackendError(
                f"Could not reach a PyMOL XML-RPC server at {url}. Start PyMOL "
                "with the RPC server enabled first: run `pymol -R` (this "
                "launches the normal PyMOL GUI with remote control turned "
                "on; it must stay running). If you're using a different "
                "host/port, pass --attach-host / --attach-port."
            ) from exc

    def _require_started(self) -> xmlrpc.client.ServerProxy:
        if self._srv is None:
            raise PymolBackendError("Attach backend was not started.")
        return self._srv

    def call(self, fn: str, *args: Any, **kwargs: Any) -> Any:
        arg_src = ", ".join(repr(a) for a in args)
        kwarg_src = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
        call_args = ", ".join(p for p in (arg_src, kwarg_src) if p)
        body = f"        result = cmd.{fn}({call_args})"
        payload = self._run_remote(body)
        return payload["result"]

    def do(self, command: str) -> str:
        body = f"        result = cmd.do({command!r}, echo=0)"
        payload = self._run_remote(body)
        return (payload.get("stdout") or "").strip()

    def eval_json(self, code: str, **variables: Any) -> Any:
        assign_lines = "\n".join(f"        {k} = {v!r}" for k, v in variables.items())
        indented_code = "\n".join(f"        {line}" for line in code.splitlines())
        body = f"{assign_lines}\n{indented_code}" if assign_lines else indented_code
        payload = self._run_remote(body)
        return payload["result"]

    def _run_remote(self, body: str) -> dict[str, Any]:
        srv = self._require_started()
        req_id = uuid.uuid4().hex
        script_path = self._tmp_dir / f"{req_id}.py"
        out_path = self._tmp_dir / f"{req_id}.out.json"
        done_path = self._tmp_dir / f"{req_id}.done"

        script = _REMOTE_SCRIPT_TEMPLATE.format(
            body=body, out_path=str(out_path), done_path=str(done_path)
        )
        script_path.write_text(script)

        try:
            # xmlrpc.client methods are positional-only over the wire (no
            # kwargs), unlike calling cmd.do() in-process -- so this can't
            # pass echo=0 the way the generated script's own cmd.do() calls
            # do a few lines down (those run locally once `run` has already
            # started the remote script, not through the RPC proxy).
            srv.do(f"run {script_path}")
        except (ConnectionRefusedError, OSError, xmlrpc.client.Fault) as exc:
            raise PymolBackendError(f"Lost connection to PyMOL RPC server: {exc}") from exc

        deadline = time.monotonic() + _RESULT_POLL_TIMEOUT
        while not done_path.exists():
            if time.monotonic() > deadline:
                raise PymolBackendError(
                    "Timed out waiting for PyMOL to finish executing a remote command."
                )
            time.sleep(_RESULT_POLL_INTERVAL)

        try:
            payload = json.loads(out_path.read_text())
        finally:
            for p in (script_path, out_path, done_path):
                p.unlink(missing_ok=True)

        if not payload.get("ok", False):
            raise PymolBackendError(payload.get("error", "Unknown remote error"))
        return payload

    def close(self) -> None:
        self._srv = None
        for p in self._tmp_dir.glob("*"):
            p.unlink(missing_ok=True)
        try:
            self._tmp_dir.rmdir()
        except OSError:
            pass
