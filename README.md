# pymol-mcp

An MCP (Model Context Protocol) server that drives [PyMOL open-source](https://github.com/schrodinger/pymol-open-source)
for molecular visualization and structural analysis. It lets an MCP client
(Claude Code, Claude Desktop, or any other MCP-compatible agent) load
structures, style and render them, and run structural analysis -- and
actually *see* the resulting scene as a rendered PNG.

## Why this works

PyMOL open-source is a Python application, not just a GUI with a scripting
bolt-on. `pymol.cmd` is the same ~500-function API surface the GUI itself
calls, `pymol2.PyMOL()` gives you fully embeddable sessions, and the ray
tracer is pure CPU -- so headless rendering needs no display, X server, or
GPU. This server runs PyMOL in-process by default, with no setup beyond
installing PyMOL itself.

## Install

### Headless mode (default, recommended)

Requires PyMOL's Python bindings (`pymol2`) in the same environment as this
server.

```bash
conda env create -f environment.yml
conda activate pymol-mcp
pip install -e .
```

Or, if you already have `pymol-open-source` installed some other way (e.g.
PyPI wheels via `pip install pymol-open-source-whl`), just:

```bash
pip install -e .
```

### Attach mode (drive a live PyMOL GUI instead)

No local PyMOL install needed for the server itself -- attach mode only
needs the standard library (`xmlrpc.client`). Start PyMOL yourself first with
its RPC server enabled:

```bash
pymol -R
```

This launches the normal PyMOL GUI with remote control turned on (XML-RPC on
port 9123 by default). Leave it running, then start the server with
`--attach`. **Attach mode assumes the server and the PyMOL GUI run on the
same machine** -- image rendering and Python execution both round-trip
through local temp files, not the network.

> Note: attach mode has been implemented and exercised at the protocol level
> (see `tests/test_backends.py`, which runs it against a mock XML-RPC
> server) but not against a live PyMOL GUI in this repo's dev environment,
> which has no display. If `pymol -R` doesn't behave as documented on your
> PyMOL build, please file an issue.

## Run

```bash
# Headless (default): owns an in-process PyMOL session
pymol-mcp

# Attach to a GUI you started with `pymol -R`
pymol-mcp --attach

# Enable arbitrary Python execution inside the session (off by default --
# see Security below)
pymol-mcp --allow-python-exec
```

### MCP client configuration

For Claude Code / Claude Desktop, add to your MCP server config:

```json
{
  "mcpServers": {
    "pymol": {
      "command": "pymol-mcp",
      "args": []
    }
  }
}
```

## Tools

| Category | Tools |
|---|---|
| Structures | `pymol_fetch`, `pymol_load`, `pymol_load_string`, `pymol_create_object`, `pymol_delete`, `pymol_reinitialize`, `pymol_list_objects`, `pymol_get_chains`, `pymol_get_sequence` |
| Selections | `pymol_select`, `pymol_count_atoms`, `pymol_iterate_atoms` |
| Styling | `pymol_show`, `pymol_hide`, `pymol_show_as`, `pymol_color`, `pymol_spectrum`, `pymol_bg_color`, `pymol_set` |
| Camera | `pymol_orient`, `pymol_zoom`, `pymol_center`, `pymol_turn`, `pymol_get_view`, `pymol_set_view` |
| Rendering | `pymol_render_image` (returns an inline PNG) |
| Analysis | `pymol_align`, `pymol_super`, `pymol_cealign`, `pymol_rms_cur`, `pymol_measure`, `pymol_polar_contacts`, `pymol_sasa`, `pymol_center_of_mass`, `pymol_get_extent` |
| Export | `pymol_save_session`, `pymol_export_structure`, `pymol_save_png` |
| Escape hatch | `pymol_run_command` (any raw PyMOL command line) |
| Escape hatch (opt-in) | `pymol_run_python` (only registered with `--allow-python-exec`) |

A typical session: `pymol_fetch("1ubq")` -> `pymol_show_as("cartoon")` ->
`pymol_spectrum(expression="b")` -> `pymol_orient()` ->
`pymol_render_image()`.

## Security

- **`pymol_run_python` is off by default.** Pass `--allow-python-exec` to
  register it. It executes arbitrary Python inside the PyMOL process, i.e.
  full code execution on the host machine as whichever user is running the
  server. Only enable this for a client you trust.
- Attach mode connects to whatever is listening on `--attach-host`:`--attach-port`
  (default `localhost:9123`) with no authentication -- this matches PyMOL's
  own `-R` flag, which has none either. Don't expose that port beyond
  localhost.
- `pymol_fetch` makes outbound network requests to the RCSB PDB.

## Development

```bash
pip install -e ".[dev]"
pytest tests/
npx @modelcontextprotocol/inspector pymol-mcp   # interactive tool inspection
```

See `evaluation/pymol_mcp_eval.xml` for end-to-end evaluation questions.

## License

MIT for this server. PyMOL open-source itself is BSD-like licensed by
Schrödinger, LLC.
