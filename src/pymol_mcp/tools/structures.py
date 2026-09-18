"""Loading, unloading, and inspecting structures."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..errors import require
from ..models import ObjectInfo, ObjectList
from ._util import get_session, pymol_errors

# cmd.read_pdbstr / cmd.read_molstr / cmd.read_mmodstr are PyMOL's inline
# (no-temp-file) loaders. They don't show up in dir(cmd) -- verified against
# a live pymol2 session -- but are callable regardless.
_INLINE_READERS = {
    "pdb": "read_pdbstr",
    "mol": "read_molstr",
    "sdf": "read_molstr",  # read_molstr auto-detects MOL vs. SDF content
    "mmod": "read_mmodstr",
}


def register(mcp: MCPServer) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Fetch structure from the PDB",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=True,
        )
    )
    async def pymol_fetch(
        ctx: Context,
        pdb_id: Annotated[str, Field(description="4-character PDB ID, e.g. '1ubq', '4hhb'.")],
        object_name: Annotated[
            str | None,
            Field(description="Name to load the structure as (default: the PDB ID)."),
        ] = None,
        type: Annotated[
            str,
            Field(description="File type to fetch: 'pdb', 'cif', or 'pdb1'/'cif1' for the first bioassembly."),
        ] = "cif",
    ) -> ObjectInfo:
        """Download and load a structure from the RCSB PDB by its 4-character
        ID. Requires network access. Use pymol_load instead for a local file."""
        session = get_session(ctx)
        name = object_name or pdb_id.lower()
        async with pymol_errors(context=f"fetching '{pdb_id}'"):
            await session.call("fetch", pdb_id, name=name, type=type)
        return await _object_info(session, name)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Load a local structure file",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_load(
        ctx: Context,
        path: Annotated[str, Field(description="Path to a structure file (.pdb, .cif, .sdf, .mol2, .xyz, .pse, ...).")],
        object_name: Annotated[
            str | None, Field(description="Name to load the structure as (default: derived from the filename).")
        ] = None,
    ) -> ObjectInfo:
        """Load a structure from a local file on disk."""
        session = get_session(ctx)
        async with pymol_errors(context=f"loading '{path}'"):
            if object_name:
                await session.call("load", path, object=object_name)
            else:
                await session.call("load", path)
        name = object_name or await _last_loaded_name(session)
        return await _object_info(session, name)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Load structure text (PDB/MOL/SDF block)",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_load_string(
        ctx: Context,
        content: Annotated[str, Field(description="Raw structure file content, e.g. a PDB or MOL block.")],
        object_name: Annotated[str, Field(description="Name to load the structure as.")],
        format: Annotated[str, Field(description="Format of `content`: 'pdb', 'mol', 'sdf', or 'mmod'. For mol2, write to a temp file and use pymol_load instead.")] = "pdb",
    ) -> ObjectInfo:
        """Load a structure from an inline text block rather than a file path
        -- useful for small molecules generated on the fly."""
        session = get_session(ctx)
        reader = _INLINE_READERS.get(format.lower())
        require(
            reader is not None,
            f"Unsupported inline format '{format}'. Supported: {', '.join(sorted(_INLINE_READERS))}.",
        )
        async with pymol_errors(context=f"loading inline '{format}' content"):
            await session.call(reader, content, object_name)
        return await _object_info(session, object_name)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create a new object from a selection",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_create_object(
        ctx: Context,
        name: Annotated[str, Field(description="Name for the new object.")],
        selection: Annotated[
            str, Field(description="Selection to copy into the new object, e.g. 'myprotein and chain A'.")
        ],
    ) -> ObjectInfo:
        """Create an independent new object by copying a selection out of
        an existing one, with its own coordinates. Use this (not
        pymol_select) whenever you need to treat part of a structure as its
        own object -- e.g. isolating one chain before pymol_align or
        pymol_cealign, which need two distinct objects to compare, not two
        selections within the same object."""
        session = get_session(ctx)
        async with pymol_errors(context=f"creating '{name}' from '{selection}'"):
            await session.call("create", name, selection)
        return await _object_info(session, name)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Delete object(s)",
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_delete(
        ctx: Context,
        name: Annotated[
            str, Field(description="Object or selection name to delete. Use 'all' to clear the whole session.")
        ],
    ) -> str:
        """Delete an object (or 'all' to clear the entire session)."""
        session = get_session(ctx)
        async with pymol_errors(context=f"deleting '{name}'"):
            await session.call("delete", name)
        return f"Deleted '{name}'."

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Reinitialize session",
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_reinitialize(ctx: Context) -> str:
        """Reset the entire PyMOL session to a clean state, discarding all
        loaded objects and settings."""
        session = get_session(ctx)
        async with pymol_errors():
            await session.call("reinitialize")
        return "Session reinitialized."

    @mcp.tool(
        annotations=ToolAnnotations(
            title="List loaded objects",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_list_objects(ctx: Context) -> ObjectList:
        """List every object currently loaded in the session, with atom and
        state counts. Call this first when you're not sure what's loaded."""
        session = get_session(ctx)
        async with pymol_errors():
            names = await session.call("get_names", "objects")
            infos = [await _object_info(session, n) for n in names]
        return ObjectList(objects=infos)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get chain IDs",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_get_chains(
        ctx: Context,
        selection: Annotated[str, Field(description="Object or selection name.")],
    ) -> list[str]:
        """List the chain IDs present in an object/selection."""
        session = get_session(ctx)
        async with pymol_errors(context=f"getting chains for '{selection}'"):
            return await session.call("get_chains", selection)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get sequence (FASTA)",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_get_sequence(
        ctx: Context,
        selection: Annotated[str, Field(description="Object or selection name, e.g. 'myprotein and chain A'.")],
    ) -> str:
        """Get the sequence of a selection as FASTA text."""
        session = get_session(ctx)
        async with pymol_errors(context=f"getting sequence for '{selection}'"):
            return await session.call("get_fastastr", selection)


async def _last_loaded_name(session) -> str:
    names = await session.call("get_names", "objects")
    require(bool(names), "Load succeeded but no object was found afterwards.")
    return names[-1]


async def _object_info(session, name: str) -> ObjectInfo:
    n_atoms = await session.call("count_atoms", name)
    n_states = await session.call("count_states", name)
    return ObjectInfo(name=name, n_atoms=n_atoms, n_states=n_states, object_type="molecule")
