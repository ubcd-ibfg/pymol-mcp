"""Backend tests.

HeadlessBackend is tested against a real ``pymol2`` session (this test suite
assumes PyMOL is installed in the running environment, same as the server
itself needs for headless mode).

AttachBackend is tested against a minimal fake XML-RPC server that emulates
just enough of PyMOL's ``rpc.py`` (``register_instance(cmd)`` exposing
``cmd``'s methods directly, plus a ``do("run <path>")`` command that executes
a script with ``cmd`` bound) to exercise the real wire protocol -- the
temp-file script generation, remote execution trigger, and JSON result
round-trip -- without needing a live PyMOL GUI.
"""

from __future__ import annotations

import threading
from xmlrpc.server import SimpleXMLRPCServer

import pytest

from pymol_mcp.backends.attach import AttachBackend
from pymol_mcp.backends.base import PymolBackendError
from pymol_mcp.backends.headless import HeadlessBackend

# --- Headless ------------------------------------------------------------


@pytest.fixture
def headless():
    backend = HeadlessBackend()
    backend.start()
    yield backend
    backend.close()


def test_headless_call(headless):
    headless.call("fragment", "ala")
    assert headless.call("count_atoms", "ala") == 10


def test_headless_call_unknown_function_raises(headless):
    with pytest.raises(PymolBackendError):
        headless.call("this_function_does_not_exist")


def test_headless_do_captures_output(headless):
    headless.call("fragment", "ala")
    # `print` (via the "python" command block) is captured, not a normal
    # PyMOL command's own feedback -- do() only guarantees *some* text comes
    # back for commands that print.
    out = headless.do("print(cmd.count_atoms('ala'))")
    assert "10" in out


def test_headless_eval_json_iterate_with_space(headless):
    headless.call("fragment", "ala")
    names = headless.eval_json(
        "names = []\n"
        "cmd.iterate('ala', 'names.append(name)', space={'names': names})\n"
        "result = names"
    )
    assert names_contains_ca(names)


def names_contains_ca(names: list[str]) -> bool:
    return "CA" in names


def test_headless_eval_json_missing_result_raises(headless):
    with pytest.raises(PymolBackendError, match="did not assign to 'result'"):
        headless.eval_json("x = 1")


def test_headless_eval_json_error_propagates(headless):
    with pytest.raises(PymolBackendError):
        headless.eval_json("result = 1 / 0")


def test_headless_close_is_idempotent():
    backend = HeadlessBackend()
    backend.start()
    backend.close()
    backend.close()  # must not raise


# --- Attach (against a fake RPC server) -----------------------------------


class _FakeCmd:
    """Emulates just enough of PyMOL's cmd surface for the wire protocol."""

    def get_version(self):
        return ("FakePyMOL", 3.1, 0, 0, "", "")

    def count_atoms(self, selection):
        return {"all": 42, "ala": 10}.get(selection, 0)

    def broken(self):
        raise RuntimeError("boom")

    def do(self, command, echo=0):
        command = (command or "").strip()
        if command.startswith("run "):
            path = command[len("run ") :].strip()
            with open(path) as f:
                code = f.read()
            exec(code, {"cmd": self})


@pytest.fixture
def fake_rpc_server():
    server = SimpleXMLRPCServer(("localhost", 0), logRequests=False, allow_none=True)
    server.register_instance(_FakeCmd())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield port
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def attach(fake_rpc_server):
    backend = AttachBackend(host="localhost", port=fake_rpc_server)
    backend.start()
    yield backend
    backend.close()


def test_attach_start_fails_with_actionable_message_when_nothing_listening():
    backend = AttachBackend(host="localhost", port=1)  # nothing listens on port 1
    with pytest.raises(PymolBackendError, match="pymol -R"):
        backend.start()


def test_attach_call_round_trips_through_temp_files(attach):
    assert attach.call("count_atoms", "all") == 42
    assert attach.call("count_atoms", "ala") == 10


def test_attach_call_error_propagates(attach):
    with pytest.raises(PymolBackendError, match="boom"):
        attach.call("broken")


def test_attach_eval_json_round_trips(attach):
    result = attach.eval_json("result = cmd.count_atoms('all') * 2")
    assert result == 84


def test_attach_cleans_up_temp_files(attach, fake_rpc_server):
    attach.call("count_atoms", "all")
    leftover = list(attach._tmp_dir.glob("*"))
    assert leftover == [], f"expected no leftover temp files, found {leftover}"
