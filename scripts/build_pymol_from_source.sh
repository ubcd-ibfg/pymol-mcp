#!/usr/bin/env bash
# Build PyMOL open-source from source directly into this project's `uv`
# virtualenv (.venv). Use this on platforms without a `pymol-open-source-whl`
# wheel -- notably Linux aarch64 (Jetson, Graviton, Ampere/Grace ARM
# servers) -- where `uv sync --extra headless` alone can't install PyMOL.
#
# Run from the repo root: ./scripts/build_pymol_from_source.sh
#
# Prerequisites (Debian/Ubuntu package names; adjust for your distro):
#   sudo apt install libglew-dev libgl1-mesa-dev libxml2-dev \
#       libmsgpack-dev libnetcdf-dev libglm-dev libfreetype-dev libpng-dev \
#       cmake g++
#
# What this does:
#   1. Fetches mmtf-cpp (header-only; not packaged by apt, and PyMOL's
#      build fails with "fatal error: mmtf.hpp: No such file or directory"
#      without it) into a scratch directory.
#   2. Runs `uv pip install` against the upstream pymol-open-source repo
#      (a normal PEP 517 / CMake build), with PREFIX_PATH pointed at that
#      scratch directory so the build finds mmtf.hpp.
#   3. Cleans up the scratch directory. The compiled `pymol`/`pymol2`
#      packages remain installed in .venv.
#
# This takes several minutes -- it compiles PyMOL's full C++ core.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -d .venv ]; then
    echo "No .venv found -- run 'uv sync' first." >&2
    exit 1
fi

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

echo "Fetching mmtf-cpp headers..."
git clone --depth 1 --quiet https://github.com/rcsb/mmtf-cpp.git "$scratch/mmtf-cpp"

echo "Building pymol-open-source from source into .venv (this takes a while)..."
PREFIX_PATH="$scratch/mmtf-cpp" uv pip install \
    "pymol @ git+https://github.com/schrodinger/pymol-open-source.git"

echo
echo "Done. Verifying:"
uv run python -c "import pymol2; p = pymol2.PyMOL(); p.start(); print('pymol2 OK, version:', p.cmd.get_version()[0]); p.stop()"
