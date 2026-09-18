"""CLI entry point: `pymol-mcp [--attach] [--allow-python-exec] ...`"""

from __future__ import annotations

import argparse
import logging
import sys

from .server import ServerOptions, create_server


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pymol-mcp",
        description="MCP server that drives PyMOL (open-source) for molecular "
        "visualization and structural analysis.",
    )
    parser.add_argument(
        "--attach",
        action="store_true",
        help="Attach to a live PyMOL GUI over XML-RPC instead of starting a "
        "headless in-process session. Requires PyMOL to already be running "
        "with `pymol -R`.",
    )
    parser.add_argument(
        "--attach-host",
        default="localhost",
        help="Host for --attach mode (default: localhost).",
    )
    parser.add_argument(
        "--attach-port",
        type=int,
        default=9123,
        help="Port for --attach mode (default: 9123, PyMOL's default RPC port).",
    )
    parser.add_argument(
        "--fetch-dir",
        default=None,
        help="Headless mode only: directory to cache structures fetched via "
        "pymol_fetch (default: PyMOL's own default cache location).",
    )
    parser.add_argument(
        "--allow-python-exec",
        action="store_true",
        help="Register the pymol_run_python tool, which executes arbitrary "
        "Python code inside the PyMOL session. OFF BY DEFAULT: this is "
        "equivalent to giving any connected MCP client full code execution "
        "on this machine (as this user). Only pass this flag when you trust "
        "the MCP client.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="MCP transport (default: stdio, for local clients like Claude "
        "Desktop/Code).",
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=8000,
        help="Port to listen on when --transport streamable-http (default: 8000).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    options = ServerOptions(
        mode="attach" if args.attach else "headless",
        attach_host=args.attach_host,
        attach_port=args.attach_port,
        fetch_dir=args.fetch_dir,
        allow_python_exec=args.allow_python_exec,
    )
    mcp = create_server(options)

    if args.transport == "streamable-http":
        mcp.run(transport="streamable-http", port=args.http_port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
