# pymol-mcp

An MCP (Model Context Protocol) server that drives [PyMOL open-source](https://github.com/schrodinger/pymol-open-source)
for molecular visualization and structural analysis. It lets an MCP client
(Claude Code, Claude Desktop, or any other MCP-compatible agent) load
structures, style and render them, and run structural analysis -- and
actually *see* the resulting scene as a rendered PNG.

## Install

### Headless mode (default, recommended)

Requires PyMOL's Python bindings (`pymol2`) in the same environment as this
server. Using [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra headless
```

This installs `pymol-mcp` plus `pymol-open-source-whl` (prebuilt PyPI wheels
for headless PyMOL) into a managed virtualenv. Run the server with
`uv run pymol-mcp`.

If you already have PyMOL installed some other way (see *Installing PyMOL
open-source* below, e.g. a conda environment), just sync without the extra:

```bash
uv sync
```

<details>
<summary>Without uv (pip / conda)</summary>

```bash
pip install -e ".[headless]"
```

Or, with PyMOL provided by a conda environment:

```bash
conda env create -f environment.yml
conda activate pymol-mcp
pip install -e .
```

</details>

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

## Installing PyMOL open-source

Only needed if you want PyMOL itself outside of the `uv sync --extra headless`
path above -- e.g. to run `pymol -R` for attach mode, or to provide the
`pymol2` bindings via conda instead of PyPI wheels.

- **PyPI wheels** (headless, no GUI toolkit required): `uv pip install pymol-open-source-whl`
- **conda-forge** (headless or full GUI): `conda install -c conda-forge pymol-open-source`
- **Linux system package** (full GUI, e.g. Debian/Ubuntu): `sudo apt install pymol`
- **From source**: see the [pymol-open-source](https://github.com/schrodinger/pymol-open-source) repo

## Run

```bash
# Headless (default): owns an in-process PyMOL session
uv run pymol-mcp

# Attach to a GUI you started with `pymol -R`
uv run pymol-mcp --attach

# Enable arbitrary Python execution inside the session (off by default --
# see Security below)
uv run pymol-mcp --allow-python-exec
```

(Drop `uv run` and call `pymol-mcp` directly if you installed with plain pip
or conda instead.)

### MCP client configuration

For Claude Code / Claude Desktop, add to your MCP server config:

```json
{
  "mcpServers": {
    "pymol": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/pymol_mcp", "pymol-mcp"]
    }
  }
}
```

(Or `"command": "pymol-mcp", "args": []` if it's installed with plain pip or
conda into an already-active environment.)

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
uv sync --extra dev --extra headless
uv run pytest tests/
npx @modelcontextprotocol/inspector uv run pymol-mcp   # interactive tool inspection
```

See `evaluation/pymol_mcp_eval.xml` for end-to-end evaluation questions and
`ARCHITECTURE.md` for how the code is put together (module map, request
flow, and the non-obvious decisions -- thread serialization, the
`eval_json` marshalling bridge, why tool errors have to subclass the SDK's
`ToolError`).

## License

MIT for this server. PyMOL open-source itself is BSD-like licensed by
Schrödinger, LLC.
