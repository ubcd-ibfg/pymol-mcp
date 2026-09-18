"""Shared Pydantic input/output models used across tool modules."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Representation(str, Enum):
    CARTOON = "cartoon"
    STICKS = "sticks"
    SPHERES = "spheres"
    SURFACE = "surface"
    MESH = "mesh"
    RIBBON = "ribbon"
    LINES = "lines"
    DOTS = "dots"
    NONBONDED = "nonbonded"
    LABELS = "labels"


class MeasureMode(str, Enum):
    DISTANCE = "distance"
    ANGLE = "angle"
    DIHEDRAL = "dihedral"


class ExportFormat(str, Enum):
    PDB = "pdb"
    CIF = "cif"
    MOL = "mol"
    MOL2 = "mol2"
    SDF = "sdf"


# --- Return models -----------------------------------------------------


class ObjectInfo(BaseModel):
    name: str
    n_atoms: int
    n_states: int
    object_type: str = Field(description="e.g. 'molecule', 'map', 'selection'")


class ObjectList(BaseModel):
    objects: list[ObjectInfo]


class SelectionResult(BaseModel):
    selection_name: str
    n_atoms: int


class AtomRecord(BaseModel):
    model: str
    chain: str
    resi: str
    resn: str
    name: str
    elem: str
    b: float
    q: float
    ss: str


class AtomIteration(BaseModel):
    atoms: list[AtomRecord]
    total: int
    offset: int
    count: int
    has_more: bool


class ViewMatrix(BaseModel):
    """The 18 floats returned by ``cmd.get_view()``: a 3x3 rotation matrix,
    origin, camera position, and clip planes -- opaque but round-trippable
    through ``cmd.set_view()``."""

    matrix: list[float] = Field(min_length=18, max_length=18)


class AlignResult(BaseModel):
    """The 7-tuple returned by ``cmd.align`` / ``cmd.super``, named."""

    rmsd_refined: float
    n_atoms_refined: int
    n_cycles: int
    rmsd_initial: float
    n_atoms_initial: int
    raw_score: float
    n_residues: int


class CealignResult(BaseModel):
    """What ``cmd.cealign`` actually returns: {'RMSD', 'alignment_length',
    'rotation_matrix'}. There is no atom count in the raw result -- only the
    aligned-residue count."""

    rmsd: float
    alignment_length: int


class MeasurementResult(BaseModel):
    mode: MeasureMode
    value: float
    unit: str


class ContactPair(BaseModel):
    atom1: str
    atom2: str
    distance: float


class PolarContactsResult(BaseModel):
    contacts: list[ContactPair]
    count: int


class SasaResult(BaseModel):
    selection: str
    area_A2: float
    mode: str = Field(description="'sasa' (solvent-accessible) or 'molecular'")


class CenterOfMass(BaseModel):
    x: float
    y: float
    z: float


class Extent(BaseModel):
    min: list[float] = Field(min_length=3, max_length=3)
    max: list[float] = Field(min_length=3, max_length=3)


class CommandResult(BaseModel):
    output: str


class ExportResult(BaseModel):
    path: str | None = None
    content: str | None = None
    format: str


class PythonExecResult(BaseModel):
    stdout: str
    value: object | None = None
