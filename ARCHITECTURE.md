# Architecture

This document covers the internal design: how a tool call turns into a
PyMOL command, and the handful of non-obvious decisions a contributor needs
before touching this code. For install/usage, see `README.md`.

## Module map

```
src/pymol_mcp/
├── __main__.py       CLI: argument parsing, transport selection
├── server.py          Builds the MCPServer, owns the session lifespan
├── session.py          Serializes all PyMOL access onto one worker thread
├── backends/
│   ├── base.py         PymolBackend protocol (call / do / eval_json / close)
│   ├── headless.py     In-process pymol2.PyMOL() session
│   └── attach.py        XML-RPC client for a separately-running PyMOL GUI
├── models.py            Pydantic request/response models shared across tools
├── formatting.py        Pagination helpers (pymol_iterate_atoms)
├── errors.py             PymolBackendError -> actionable ToolError text
└── tools/
    ├── _util.py          get_session(), pymol_errors() context manager
    ├── structures.py     fetch / load / create_object / delete / inspect
    ├── selections.py     select / count_atoms / iterate_atoms
    ├── styling.py         show / hide / color / spectrum / set
    ├── camera.py           orient / zoom / turn / get_view / set_view
    ├── rendering.py         render_image (the inline-PNG tool)
    ├── analysis.py           align / cealign / measure / sasa / ...
    ├── export.py              save_session / export_structure / save_png
    └── raw.py                  run_command, run_python (gated)
```

Each `tools/*.py` file exposes one `register(mcp: MCPServer) -> None`
function that defines and attaches its tools with `@mcp.tool(...)`.
`server.py` imports and calls all of them once, at server construction.

## Request flow

```
MCP client
   │  tools/call "pymol_align" {...}
   ▼
tool function (analysis.py)                    -- validates input via Pydantic
   │  get_session(ctx)                           (from AppContext.lifespan_context)
   ▼
PymolSession.call("align", mobile, target, ...)
   │  loop.run_in_executor(single-thread pool)    -- see "Threading" below
   ▼
backend.call("align", ...)                       -- HeadlessBackend or AttachBackend
   │  getattr(cmd, "align")(*args, **kwargs)
   ▼
pymol.cmd.align(...)                             -- the real PyMOL API
   │  returns a 7-tuple, or raises pymol.CmdException
   ▼
tool function wraps the tuple in AlignResult (models.py) and returns it
```

A tool function never imports `pymol` or touches a backend directly. It
only ever calls `PymolSession.call/do/eval_json`, obtained via
`_util.get_session(ctx)`. That's what makes the same tool code work
unmodified against both backends.

## Threading: why every call goes through one worker thread

PyMOL's C layer is not thread-safe, and a `pymol2.PyMOL()` instance has to
be driven consistently from a single thread. FastMCP/MCPServer tools are
async and the client can call them concurrently, so `PymolSession`
(`session.py`) funnels every backend call through a
`ThreadPoolExecutor(max_workers=1)`, plus an `asyncio.Lock` for good
measure. Skipping this and calling a backend method straight from a tool
coroutine will eventually segfault the headless session under concurrent
tool calls -- don't do it, even for a "quick read-only call."

## The `eval_json` bridge

`PymolBackend.call(fn, *args, **kwargs)` covers most of the API: call a
`cmd.*` function, get back a JSON-safe value (tuple, list, float, dict of
primitives). It breaks down for two common shapes:

- `cmd.iterate(selection, expr, space=some_dict)` doesn't return the data,
  it mutates `some_dict` as a side effect.
- `cmd.get_model()` returns a ChemPy object, not something JSON can carry.

`eval_json(code, **variables)` exists for these: it runs a Python snippet
against the PyMOL session and returns whatever the snippet assigns to a
local variable named `result`. `pymol_iterate_atoms` (`selections.py`) is
the canonical example:

```python
await session.eval_json(
    f"atoms = []\n"
    f"cmd.iterate({selection!r}, {ITERATE_EXPR!r}, space={{'atoms': atoms}})\n"
    f"result = atoms[{offset}:{offset + limit}]"
)
```

**Headless** implements this with a plain `exec(code, namespace)` -- trivial,
since the PyMOL session lives in the same process.

**Attach** implements it by writing the snippet to a local temp `.py` file,
telling the remote PyMOL to `run` it (`srv.do("run <path>")`, PyMOL's own
`run` command, which binds `cmd` in the script's globals), and reading a
second temp file back once the remote process signals completion. This
works because attach mode is same-machine-only: the client and the PyMOL
GUI share a filesystem, so it's a valid side channel even though it never
touches the network. `pymol_render_image` uses the same trick for PNG bytes,
which XML-RPC can't carry at all.

See `backends/attach.py` for the exact script template, and
`tests/test_backends.py` for a protocol-level test of the whole round trip
against a mock XML-RPC server (no real PyMOL GUI needed).

## Raising errors an agent can act on

PyMOL mostly signals failure by returning `None`/`-1` or printing to stderr,
not by raising. `errors.py` centralizes turning that into text such as
"Use pymol_list_objects to see what objects currently exist" instead of a
bare traceback.

One detail that isn't obvious from the SDK's docs: **the tool-level
exception has to subclass `mcp.server.mcpserver.exceptions.ToolError`**, not
plain `Exception`. `MCPServer`'s tool runner treats a `ToolError` as an
anticipated failure and forwards its message to the client; anything else
is treated as a crash and replaced with a generic `"Error executing tool
<name>"`, with the real message discarded and only logged server-side. All
of the careful error text in `errors.py` would be silently thrown away
without this. `PymolToolError` (in `errors.py`) subclasses `ToolError` for
exactly this reason -- raise it (or `errors.require(...)`, which raises it
for you), never a bare `Exception` or `ValueError`, from tool code.

## `pymol_select` vs `pymol_create_object`

A PyMOL selection is a named tag on atoms within their existing object; it
is not a standalone object with its own coordinates. `cmd.align`,
`cmd.cealign`, and `cmd.super` all need two distinct *objects* to compare,
so aligning two selections of the same parent object fails with
`"invalid selections for alignment"`. `pymol_create_object` (wrapping
`cmd.create`) is what makes an independent copy. This tripped up the first
draft of the evaluation questions (see `evaluation/pymol_mcp_eval.xml` and
the git log) before the tool existed -- `tools/selections.py`'s
`pymol_select` docstring now cross-references it, and
`tests/test_e2e_stdio.py::test_create_object_then_align_two_chains` pins
the exact workflow.

## MCP SDK version

This targets `mcp>=2.0.0`, which renamed `mcp.server.fastmcp.FastMCP` to
`mcp.server.mcpserver.MCPServer` and moved several things around. A lot of
MCP server examples and tutorials in the wild still reference the 1.x
`FastMCP` name -- if you're porting a pattern from one of those, expect the
import path and a few method names to differ; check `server.py` for the
current shape.

## Adding a tool

1. Pick the right `tools/*.py` file by category (or add a new one and wire
   it into `server.py:_register_all_tools`).
2. Write a Pydantic model in `models.py` if the return value has real
   structure; a bare `str`/`int`/`bool` is fine for simple confirmations.
3. Call through `session.call(fn, ...)` for anything that maps to a single
   `cmd.*` function; use `session.eval_json(...)` only when you actually
   need to touch a non-primitive result (see above -- most tools don't).
4. Wrap the backend call in `async with pymol_errors(context="..."):` from
   `tools/_util.py` so failures come back as actionable `PymolToolError`s.
5. Give it `ToolAnnotations` (`read_only_hint`, `destructive_hint`,
   `idempotent_hint`, `open_world_hint`) -- these are what a client uses to
   decide whether a call needs confirmation.
6. Add it to the table in `README.md`.

## Testing

- `tests/test_backends.py` -- unit-level, against a real headless PyMOL
  session and a mock XML-RPC server. Fast, no network.
- `tests/test_e2e_stdio.py` -- spawns the actual `pymol-mcp` process and
  drives it over the real stdio MCP protocol with the official client SDK.
  Requires network access (fetches real PDB structures) and a working
  PyMOL install. This is the suite that catches wiring bugs the unit tests
  can't see, such as a tool's exception type getting swallowed by the SDK.
- `evaluation/pymol_mcp_eval.xml` -- ten read-only questions for evaluating
  whether an LLM can actually use this server to get correct answers, not
  whether the code runs. Every answer was solved by calling the real
  server, not computed by hand.
