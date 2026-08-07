# BX_bevelx/BX_types.py
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from BX_bevelx.BX_constants import (
    BEVEL_AFFECT_EDGES,
    BEVEL_AMT_OFFSET,
    BEVEL_MITER_SHARP,
    BEVEL_PROFILE_SUPERELLIPSE,
    BEVEL_VMESH_ADJ,
    M_ADJ,
    M_NONE,
    M_POLY,
    PRO_LINE_R,
)
from BX_bevelx.BX_math_utils import copy_v3, vec3


# ---------------------------------------------------------------------------
# Blender NewVert equivalent.
# ---------------------------------------------------------------------------

@dataclass
class NewVert:
    v: Optional[Any] = None
    co: List[float] = field(default_factory=vec3)


# ---------------------------------------------------------------------------
# Blender Profile equivalent.
# ---------------------------------------------------------------------------

@dataclass
class Profile:
    super_r: float = PRO_LINE_R
    height: float = 0.0

    start: List[float] = field(default_factory=vec3)
    middle: List[float] = field(default_factory=vec3)
    end: List[float] = field(default_factory=vec3)

    plane_no: List[float] = field(default_factory=vec3)
    plane_co: List[float] = field(default_factory=vec3)
    proj_dir: List[float] = field(default_factory=vec3)

    prof_co: Optional[List[List[float]]] = None
    prof_co_2: Optional[List[List[float]]] = None

    special_params: bool = False


# ---------------------------------------------------------------------------
# Blender ProfileSpacing equivalent.
# ---------------------------------------------------------------------------

@dataclass
class ProfileSpacing:
    xvals: Optional[List[float]] = None
    yvals: Optional[List[float]] = None

    xvals_2: Optional[List[float]] = None
    yvals_2: Optional[List[float]] = None

    seg_2: int = 0
    fullness: float = 0.0


# ---------------------------------------------------------------------------
# Blender MathLayerInfo equivalent.
# For Maya, this starts as a placeholder. UV component logic belongs later.
# ---------------------------------------------------------------------------

@dataclass
class MathLayerInfo:
    face_component: Optional[Dict[int, int]] = None
    has_math_layers: bool = False


# ---------------------------------------------------------------------------
# Forward-declared concept:
# EdgeHalf references BoundVert and BoundVert references EdgeHalf.
# Python resolves this through Optional fields.
# ---------------------------------------------------------------------------

@dataclass
class EdgeHalf:
    # Other EdgeHalves connected to the same BevVert, in CCW order.
    next: Optional["EdgeHalf"] = None
    prev: Optional["EdgeHalf"] = None

    # Original mesh edge.
    e: Optional[Any] = None

    # Face between this edge and previous, if any.
    fprev: Optional[Any] = None

    # Face between this edge and next, if any.
    fnext: Optional[Any] = None

    # Left and right boundary verts.
    leftv: Optional["BoundVert"] = None
    rightv: Optional["BoundVert"] = None

    # Offset into profile to attach non-beveled edge.
    profile_index: int = 0

    # How many segments for this edge bevel.
    seg: int = 0

    # Offsets for this edge.
    offset_l: float = 0.0
    offset_r: float = 0.0
    offset_l_spec: float = 0.0
    offset_r_spec: float = 0.0

    # Flags.
    is_bev: bool = False
    is_rev: bool = False
    is_seam: bool = False
    visited_rpo: bool = False


# ---------------------------------------------------------------------------
# Blender BoundVert equivalent.
# ---------------------------------------------------------------------------

@dataclass
class BoundVert:
    # In CCW order.
    next: Optional["BoundVert"] = None
    prev: Optional["BoundVert"] = None

    # Constructed vertex.
    nv: NewVert = field(default_factory=NewVert)

    # First and last attached edge-halves.
    efirst: Optional[EdgeHalf] = None
    elast: Optional[EdgeHalf] = None

    # The edge between that this boundvert is on.
    eon: Optional[EdgeHalf] = None

    # Beveled edge whose left side is attached here, if any.
    ebev: Optional[EdgeHalf] = None

    # Used for VMesh indexing.
    index: int = -1

    # Width adjustment.
    sinratio: float = 1.0
    adjchain: Optional["BoundVert"] = None

    # Edge profile between this and next BoundVert.
    profile: Profile = field(default_factory=Profile)

    # Seam/sharp/profile flags.
    any_seam: bool = False
    visited: bool = False
    is_arc_start: bool = False
    is_patch_start: bool = False
    is_profile_start: bool = False

    seam_len: int = 0
    sharp_len: int = 0


# ---------------------------------------------------------------------------
# Blender VMesh equivalent.
# ---------------------------------------------------------------------------

@dataclass
class VMesh:
    # Allocated array. Stored as flat list matching Blender's mesh_vert indexing.
    mesh: List[NewVert] = field(default_factory=list)

    # Start of circular BoundVert list.
    boundstart: Optional[BoundVert] = None

    # Number of vertices in boundary.
    count: int = 0

    # Common segment count.
    seg: int = 1

    # Mesh kind.
    mesh_kind: str = M_NONE

    def allocate_mesh(self):
        """
        Blender allocates:
            count * (1 + seg / 2) * (1 + seg)

        Python keeps the same flat indexing.
        """
        nj = (self.seg // 2) + 1
        nk = self.seg + 1
        total = self.count * nj * nk
        self.mesh = [NewVert() for _ in range(total)]

    def mesh_vert(self, i: int, j: int, k: int) -> NewVert:
        """
        Blender mesh_vert(vm, i, j, k):
            nj = seg / 2 + 1
            nk = seg + 1
            &vm->mesh[i * nk * nj + j * nk + k]
        """
        nj = (self.seg // 2) + 1
        nk = self.seg + 1
        index = i * nk * nj + j * nk + k
        return self.mesh[index]

    def add_new_bound_vert(self, co) -> BoundVert:
        """
        Blender add_new_bound_vert:
            - creates BoundVert
            - inserts it at end of circular list
            - assigns index
            - initializes profile and flags
            - increments vm.count
        """
        ans = BoundVert()
        ans.nv.co = copy_v3(co)
        ans.profile.super_r = PRO_LINE_R
        ans.adjchain = None
        ans.sinratio = 1.0
        ans.visited = False
        ans.any_seam = False
        ans.is_arc_start = False
        ans.is_patch_start = False
        ans.is_profile_start = False

        if self.boundstart is None:
            ans.index = 0
            self.boundstart = ans
            ans.next = ans
            ans.prev = ans
        else:
            tail = self.boundstart.prev
            ans.index = tail.index + 1
            ans.prev = tail
            ans.next = self.boundstart
            tail.next = ans
            self.boundstart.prev = ans

        self.count += 1
        return ans

    def iter_boundverts(self):
        if self.boundstart is None:
            return

        start = self.boundstart
        current = start

        while True:
            yield current
            current = current.next
            if current is start:
                break


# ---------------------------------------------------------------------------
# Blender BevVert equivalent.
# ---------------------------------------------------------------------------

@dataclass
class BevVert:
    # Original mesh vertex.
    v: Optional[Any] = None

    # Edge counts.
    edgecount: int = 0
    selcount: int = 0
    wirecount: int = 0

    # Offset for vertex-only bevel.
    offset: float = 0.0

    # Flags.
    any_seam: bool = False
    visited: bool = False

    # EdgeHalf array in CCW order.
    edges: List[EdgeHalf] = field(default_factory=list)

    # Wire edges.
    wire_edges: List[Any] = field(default_factory=list)

    # Mesh replacing this vertex.
    vmesh: VMesh = field(default_factory=VMesh)


# ---------------------------------------------------------------------------
# Blender BevelParams equivalent.
# ---------------------------------------------------------------------------

@dataclass
class BevelParams:
    # Blender stores BMesh pointer here. Maya adapter will provide internal mesh.
    bm: Optional[Any] = None

    # Core parameters.
    offset: float = 0.1
    offset_type: str = BEVEL_AMT_OFFSET
    profile_type: str = BEVEL_PROFILE_SUPERELLIPSE
    affect_type: str = BEVEL_AFFECT_EDGES

    seg: int = 1
    profile: float = 0.5

    # Blender converts profile to superellipse exponent:
    #     -log(2) / log(sqrt(profile))
    pro_super_r: float = 2.0

    use_weights: bool = False
    loop_slide: bool = True
    limit_offset: bool = False
    offset_adjust: bool = True

    mark_seam: bool = False
    mark_sharp: bool = False
    harden_normals: bool = False

    mat_nr: int = -1
    face_strength_mode: int = 0

    miter_outer: str = BEVEL_MITER_SHARP
    miter_inner: str = BEVEL_MITER_SHARP
    vmesh_method: str = BEVEL_VMESH_ADJ

    spread: float = 0.1
    smoothresh: float = 0.0

    # Runtime stores.
    vert_hash: Dict[Any, BevVert] = field(default_factory=dict)
    face_hash: Dict[Any, str] = field(default_factory=dict)

    pro_spacing: ProfileSpacing = field(default_factory=ProfileSpacing)
    pro_spacing_miter: ProfileSpacing = field(default_factory=ProfileSpacing)
    math_layer_info: MathLayerInfo = field(default_factory=MathLayerInfo)

    custom_profile: Optional[Any] = None
    dvert: Optional[Any] = None
    vertex_group: int = -1

    def normalize(self):
        self.seg = max(int(self.seg), 1)

        if self.profile <= 0.0:
            self.pro_super_r = 0.0
        elif self.profile >= 0.950:
            # Blender snaps this to square-out behavior.
            from BX_bevelx.BX_constants import PRO_SQUARE_R
            self.pro_super_r = PRO_SQUARE_R
        else:
            self.pro_super_r = -math.log(2.0) / math.log(math.sqrt(self.profile))

        self.offset_adjust = (
            self.affect_type != "VERTICES" and
            self.offset_type not in ("PERCENT", "ABSOLUTE")
        )