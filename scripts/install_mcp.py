#!/usr/bin/env python3
"""Register pymol-mcp with Claude Code, Codex, and/or OpenCode.

Usage:
    ./scripts/install_mcp.py                     # install into every client found on PATH
    ./scripts/install_mcp.py --clients claude     # only Claude Code
    ./scripts/install_mcp.py --attach             # configure attach mode instead of headless
    ./scripts/install_mcp.py --dry-run            # show what would happen, change nothing
    ./scripts/install_mcp.py --force              # replace an existing registration

Each client is launched the same way: `uv run --directory <this repo> pymol-mcp`,
matching the default install method in README.md. Run this script from a
checkout that already has `uv sync --extra headless` (or `uv sync` for attach
mode) done -- it registers the server, it doesn't install pymol-mcp's own
dependencies.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_NAME = "pymol"
ALL_CLIENTS = ("claude", "codex", "opencode")


def have(binary: str) -> bool:
    return shutil.which(binary) is not None


def server_command(args: argparse.Namespace) -> list[str]:
    cmd = ["uv", "run", "--directory", str(REPO_ROOT), "pymol-mcp"]
    if args.attach:
        cmd.append("--attach")
    if args.allow_python_exec:
        cmd.append("--allow-python-exec")
    return cmd


def report(label: str, name: str, result: subprocess.CompletedProcess) -> None:
    output = (result.stderr or "") + (result.stdout or "")
    if result.returncode == 0:
        print(f"  [{label}] installed '{name}'.")
    elif "already exists" in output.lower():
        print(f"  [{label}] '{name}' is already registered -- re-run with --force to replace it.")
    else:
        print(f"  [{label}] failed:\n{output.strip()}")


def install_claude(cmd: list[str], args: argparse.Namespace) -> None:
    if not have("claude"):
        print("  [claude] CLI not found on PATH, skipping.")
        return
    if args.dry_run:
        print(f"  [claude] would run: claude mcp add --scope {args.scope} {args.name} -- {' '.join(cmd)}")
        return
    if args.force:
        subprocess.run(
            ["claude", "mcp", "remove", args.name, "--scope", args.scope],
            capture_output=True, text=True,
        )
    result = subprocess.run(
        ["claude", "mcp", "add", "--scope", args.scope, args.name, "--", *cmd],
        capture_output=True, text=True,
    )
    report("claude", args.name, result)


def install_codex(cmd: list[str], args: argparse.Namespace) -> None:
    if not have("codex"):
        print("  [codex] CLI not found on PATH, skipping.")
        return
    if args.dry_run:
        print(f"  [codex] would run: codex mcp add {args.name} -- {' '.join(cmd)}")
        return
    if args.force:
        subprocess.run(["codex", "mcp", "remove", args.name], capture_output=True, text=True)
    result = subprocess.run(
        ["codex", "mcp", "add", args.name, "--", *cmd],
        capture_output=True, text=True,
    )
    report("codex", args.name, result)


def install_opencode(cmd: list[str], args: argparse.Namespace) -> None:
    if not have("opencode") and "opencode" not in args.clients_explicit:
        print("  [opencode] CLI not found on PATH, skipping (pass --clients opencode to force).")
        return
    config_dir = Path.home() / ".config" / "opencode"
    config_path = config_dir / "opencode.json"
    jsonc_path = config_dir / "opencode.jsonc"
    if config_path.exists():
        data = json.loads(config_path.read_text() or "{}")
    else:
        data = {"$schema": "https://opencode.ai/config.json"}

    # opencode deep-merges opencode.json and opencode.jsonc, with .jsonc winning
    # on conflicting keys -- if the user already hand-defines this server there,
    # writing it into opencode.json here would be silently shadowed.
    if jsonc_path.exists() and f'"{args.name}"' in jsonc_path.read_text():
        print(
            f"  [opencode] {jsonc_path} appears to already define '{args.name}' -- "
            "it takes precedence over opencode.json, so edit it there instead."
        )
        return

    existing = data.get("mcp", {}).get(args.name)
    if existing is not None and not args.force:
        print(f"  [opencode] '{args.name}' is already registered in {config_path} -- re-run with --force to replace it.")
        return

    entry = {"type": "local", "command": cmd, "enabled": True}
    if args.dry_run:
        print(f"  [opencode] would write {config_path}: mcp.{args.name} = {json.dumps(entry)}")
        return

    data.setdefault("mcp", {})[args.name] = entry
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  [opencode] wrote {config_path}")


INSTALLERS = {
    "claude": install_claude,
    "codex": install_codex,
    "opencode": install_opencode,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--clients", default="all",
        help=f"comma-separated subset of {ALL_CLIENTS} (default: all)",
    )
    parser.add_argument("--name", default=SERVER_NAME, help=f"server name to register (default: {SERVER_NAME})")
    parser.add_argument(
        "--scope", default="user", choices=["user", "project", "local"],
        help="Claude Code registration scope (default: user, i.e. available in every project)",
    )
    parser.add_argument("--attach", action="store_true", help="configure attach mode (pymol-mcp --attach) instead of headless")
    parser.add_argument("--allow-python-exec", action="store_true", help="also pass --allow-python-exec (see Security in README.md)")
    parser.add_argument("--force", action="store_true", help="replace an existing registration instead of skipping it")
    parser.add_argument("--dry-run", action="store_true", help="print what would happen without changing anything")
    args = parser.parse_args()

    if args.clients == "all":
        args.clients_explicit = []
        clients = list(ALL_CLIENTS)
    else:
        clients = [c.strip() for c in args.clients.split(",") if c.strip()]
        args.clients_explicit = list(clients)
        unknown = set(clients) - set(ALL_CLIENTS)
        if unknown:
            parser.error(f"unknown client(s): {', '.join(sorted(unknown))} (choose from {ALL_CLIENTS})")
    args.clients = clients
    return args


def main() -> int:
    args = parse_args()
    cmd = server_command(args)
    print(f"Registering '{args.name}' as: {' '.join(cmd)}")
    for client in args.clients:
        INSTALLERS[client](cmd, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
