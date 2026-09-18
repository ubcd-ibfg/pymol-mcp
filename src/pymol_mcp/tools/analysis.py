"""Structural analysis: alignment, measurement, surface area, geometry."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..errors import PymolToolError
from ..models import (
    AlignResult,
    CealignResult,
    CenterOfMass,
    Extent,
    MeasurementResult,
    MeasureMode,
    PolarContactsResult,
    SasaResult,
)
from ._util import get_session, pymol_errors

# Server-side snippet for pymol_polar_contacts: find_pairs() gives atom-index
# pairs, not distances or readable identifiers, so both have to be resolved
# per-pair inside a single eval_json round trip rather than one call per pair.
_POLAR_CONTACTS_SNIPPET = """\
pairs = cmd.find_pairs({sel1!r}, {sel2!r}, mode=1, cutoff={cutoff})
contacts = []
for (m1, i1), (m2, i2) in pairs:
    a = f"{{m1}}`{{i1}}"
    b = f"{{m2}}`{{i2}}"
    dist = cmd.get_distance(a, b)
    labels = []
    for s in (a, b):
        rec = {{}}
        cmd.iterate(s, "rec.update(chain=chain, resi=resi, resn=resn, name=name)", space={{"rec": rec}})
        labels.append(f"{{rec['chain']}}/{{rec['resn']}}{{rec['resi']}}/{{rec['name']}}")
    contacts.append({{"atom1": labels[0], "atom2": labels[1], "distance": round(dist, 2)}})
result = contacts
"""


def register(mcp: MCPServer) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Align two structures (sequence-based)",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_align(
        ctx: Context,
        mobile: Annotated[str, Field(description="Selection to move/fit (e.g. an object name or 'obj1 and chain A').")],
        target: Annotated[str, Field(description="Selection to align to (stays fixed).")],
        cycles: Annotated[
            int,
            Field(
                description="Outlier-rejection refinement cycles. 0 disables rejection, giving an "
                "all-atom RMSD over the whole aligned region (useful for comparing near-identical chains).",
                ge=0,
            ),
        ] = 5,
        object_name: Annotated[
            str | None,
            Field(description="If given, create an alignment object with this name (sequence viewer + pair lines)."),
        ] = None,
    ) -> AlignResult:
        """Sequence-based structural alignment (cmd.align): builds a
        sequence alignment first, then superposes on the paired atoms with
        outlier rejection. Use pymol_super instead for structures with low
        sequence identity, or pymol_cealign for a topology-based alignment."""
        session = get_session(ctx)
        kwargs = {"cycles": cycles}
        if object_name:
            kwargs["object"] = object_name
        async with pymol_errors(context=f"aligning '{mobile}' to '{target}'"):
            r = await session.call("align", mobile, target, **kwargs)
        return AlignResult(
            rmsd_refined=r[0],
            n_atoms_refined=r[1],
            n_cycles=r[2],
            rmsd_initial=r[3],
            n_atoms_initial=r[4],
            raw_score=r[5],
            n_residues=r[6],
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Align two structures (structure-based)",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_super(
        ctx: Context,
        mobile: Annotated[str, Field(description="Selection to move/fit.")],
        target: Annotated[str, Field(description="Selection to align to (stays fixed).")],
        cycles: Annotated[int, Field(description="Outlier-rejection refinement cycles.", ge=0)] = 5,
    ) -> AlignResult:
        """Structure-based superposition (cmd.super): aligns using a
        sequence-independent structural comparison, more robust than
        pymol_align when the two structures share little sequence identity."""
        session = get_session(ctx)
        async with pymol_errors(context=f"superposing '{mobile}' onto '{target}'"):
            r = await session.call("super", mobile, target, cycles=cycles)
        return AlignResult(
            rmsd_refined=r[0],
            n_atoms_refined=r[1],
            n_cycles=r[2],
            rmsd_initial=r[3],
            n_atoms_initial=r[4],
            raw_score=r[5],
            n_residues=r[6],
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="CE-align two structures",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_cealign(
        ctx: Context,
        target: Annotated[str, Field(description="Selection to align to (stays fixed).")],
        mobile: Annotated[str, Field(description="Selection to move/fit.")],
    ) -> CealignResult:
        """Combinatorial Extension (CE) structural alignment: compares
        backbone topology directly, without a sequence alignment step.
        Requires both selections to span a reasonable number of residues
        (very short fragments will fail with a CEalign error)."""
        session = get_session(ctx)
        async with pymol_errors(context=f"CE-aligning '{mobile}' onto '{target}'"):
            r = await session.call("cealign", target, mobile)
        return CealignResult(rmsd=r["RMSD"], alignment_length=r["alignment_length"])

    @mcp.tool(
        annotations=ToolAnnotations(
            title="RMSD of already-superposed atoms",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_rms_cur(
        ctx: Context,
        mobile: Annotated[str, Field(description="First selection (same atom count/order as target).")],
        target: Annotated[str, Field(description="Second selection.")],
    ) -> float:
        """RMSD between two selections' current coordinates, with no fitting
        applied first -- use this to check how close two objects are after
        you've already aligned them, or to compare states of the same object."""
        session = get_session(ctx)
        async with pymol_errors(context=f"computing RMSD between '{mobile}' and '{target}'"):
            return await session.call("rms_cur", mobile, target)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Measure distance/angle/dihedral",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_measure(
        ctx: Context,
        mode: MeasureMode,
        atom1: Annotated[str, Field(description="First atom selection, e.g. 'obj and resi 10 and name CA'.")],
        atom2: Annotated[str, Field(description="Second atom selection.")],
        atom3: Annotated[str | None, Field(description="Third atom selection (required for angle/dihedral).")] = None,
        atom4: Annotated[str | None, Field(description="Fourth atom selection (required for dihedral).")] = None,
    ) -> MeasurementResult:
        """Measure a geometric quantity between specific atoms: a distance
        (2 atoms), a bond angle (3 atoms), or a dihedral/torsion angle
        (4 atoms). Each selection must resolve to exactly one atom."""
        session = get_session(ctx)
        async with pymol_errors(context=f"measuring {mode.value}"):
            if mode == MeasureMode.DISTANCE:
                value = await session.call("get_distance", atom1, atom2)
                unit = "Angstrom"
            elif mode == MeasureMode.ANGLE:
                if atom3 is None:
                    raise PymolToolError("mode='angle' requires atom3.")
                value = await session.call("get_angle", atom1, atom2, atom3)
                unit = "degrees"
            else:
                if atom3 is None or atom4 is None:
                    raise PymolToolError("mode='dihedral' requires atom3 and atom4.")
                value = await session.call("get_dihedral", atom1, atom2, atom3, atom4)
                unit = "degrees"
        return MeasurementResult(mode=mode, value=value, unit=unit)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Find polar contacts between two selections",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_polar_contacts(
        ctx: Context,
        selection1: Annotated[str, Field(description="First selection, e.g. a ligand.")],
        selection2: Annotated[str, Field(description="Second selection, e.g. the surrounding protein.")],
        cutoff: Annotated[float, Field(description="Max donor-acceptor distance in Angstroms.", gt=0)] = 3.6,
    ) -> PolarContactsResult:
        """Find likely polar contacts (hydrogen bonds / donor-acceptor pairs
        within cutoff) between two selections, e.g. a ligand and its binding
        pocket. Equivalent to PyMOL's GUI 'Find > Polar Contacts'."""
        session = get_session(ctx)
        snippet = _POLAR_CONTACTS_SNIPPET.format(sel1=selection1, sel2=selection2, cutoff=cutoff)
        async with pymol_errors(context="finding polar contacts"):
            contacts = await session.eval_json(snippet)
        return PolarContactsResult(contacts=contacts, count=len(contacts))

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Compute solvent-accessible surface area",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_sasa(
        ctx: Context,
        selection: Annotated[str, Field(description="Object or selection to compute surface area for.")],
        solvent_accessible: Annotated[
            bool,
            Field(description="True: solvent-accessible surface area (SASA, probe-expanded). False: molecular surface."),
        ] = True,
        dot_density: Annotated[int, Field(description="Sampling density 1-4; higher is slower but more accurate.", ge=1, le=4)] = 3,
    ) -> SasaResult:
        """Compute the surface area of a selection in square Angstroms.
        Temporarily sets dot_solvent/dot_density, computes the area, then
        restores the prior settings."""
        session = get_session(ctx)
        async with pymol_errors(context=f"computing surface area of '{selection}'"):
            prev_solvent = await session.call("get", "dot_solvent")
            prev_density = await session.call("get", "dot_density")
            try:
                await session.call("set", "dot_solvent", 1 if solvent_accessible else 0)
                await session.call("set", "dot_density", dot_density)
                area = await session.call("get_area", selection)
            finally:
                await session.call("set", "dot_solvent", prev_solvent)
                await session.call("set", "dot_density", prev_density)
        return SasaResult(
            selection=selection, area_A2=area, mode="sasa" if solvent_accessible else "molecular"
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Compute center of mass",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_center_of_mass(
        ctx: Context,
        selection: Annotated[str, Field(description="Object or selection.")],
    ) -> CenterOfMass:
        """Compute the center of mass of a selection."""
        session = get_session(ctx)
        async with pymol_errors(context=f"computing center of mass of '{selection}'"):
            x, y, z = await session.call("centerofmass", selection)
        return CenterOfMass(x=x, y=y, z=z)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get bounding box",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def pymol_get_extent(
        ctx: Context,
        selection: Annotated[str, Field(description="Object or selection.")],
    ) -> Extent:
        """Get the axis-aligned bounding box (min/max XYZ corners) of a
        selection."""
        session = get_session(ctx)
        async with pymol_errors(context=f"computing extent of '{selection}'"):
            mn, mx = await session.call("get_extent", selection)
        return Extent(min=list(mn), max=list(mx))
