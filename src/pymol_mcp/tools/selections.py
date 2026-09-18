"""Selections and per-atom introspection."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..formatting import clamp_limit
from ..models import AtomIteration, AtomRecord, SelectionResult
from ._util import get_session, pymol_errors

# Fields pulled per-atom. Namespace variables come from PyMOL's iterate
# expression language (see pymolwiki.org/index.php/Iterate). Kept minimal on
# purpose -- more fields per atom means more tokens per row when a large
# selection is iterated.
_ITERATE_EXPR = (
    "atoms.append({'model': model, 'chain': chain, 'resi': resi, 'resn': resn,"
    " 'name': name, 'elem': elem, 'b': b, 'q': q, 'ss': ss})"
)


def register(mcp: MCPServer) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create a named selection",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_select(
        ctx: Context,
        name: Annotated[str, Field(description="Name for the new selection.")],
        selection: Annotated[
            str,
            Field(
                description="PyMOL selection expression, e.g. 'chain A and polymer', "
                "'resi 10-20', 'byres (resn HEM around 5)'."
            ),
        ],
    ) -> SelectionResult:
        """Create a named selection from a PyMOL selection expression. The
        name can then be used anywhere a selection argument is expected.
        Note: a selection is just a tag on atoms within their existing
        object(s), not an independent object -- it cannot be used as one
        side of pymol_align/pymol_cealign/pymol_super. Use
        pymol_create_object instead when you need a standalone copy."""
        session = get_session(ctx)
        async with pymol_errors(context=f"selecting '{selection}'"):
            n_atoms = await session.call("select", name, selection)
        return SelectionResult(selection_name=name, n_atoms=n_atoms)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Count atoms",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_count_atoms(
        ctx: Context,
        selection: Annotated[str, Field(description="Object or selection expression.")] = "all",
    ) -> int:
        """Count atoms matching a selection expression."""
        session = get_session(ctx)
        async with pymol_errors(context=f"counting atoms in '{selection}'"):
            return await session.call("count_atoms", selection)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Iterate atoms (paginated)",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_iterate_atoms(
        ctx: Context,
        selection: Annotated[str, Field(description="Object or selection expression to iterate over.")],
        limit: Annotated[
            int, Field(description="Max atoms to return in this call (default 500, hard cap 5000).", ge=1)
        ] = 500,
        offset: Annotated[int, Field(description="Number of matching atoms to skip before returning.", ge=0)] = 0,
    ) -> AtomIteration:
        """Get per-atom data (chain, residue, name, element, b-factor,
        occupancy, secondary structure) for a selection. Paginated -- for a
        large structure, narrow the selection first (e.g. one chain) rather
        than raising the limit, since each atom row costs context tokens."""
        session = get_session(ctx)
        limit = clamp_limit(limit)
        async with pymol_errors(context=f"iterating '{selection}'"):
            total = await session.call("count_atoms", selection)
            rows = await session.eval_json(
                f"atoms = []\n"
                f"cmd.iterate({selection!r}, {_ITERATE_EXPR!r}, space={{'atoms': atoms}})\n"
                f"result = atoms[{offset}:{offset + limit}]"
            )
        atoms = [AtomRecord(**row) for row in rows]
        return AtomIteration(
            atoms=atoms,
            total=total,
            offset=offset,
            count=len(atoms),
            has_more=offset + len(atoms) < total,
        )
