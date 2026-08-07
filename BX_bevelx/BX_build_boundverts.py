# BX_bevelx/BX_build_boundverts.py
from __future__ import annotations

from typing import Iterable, List, Optional

from BX_bevelx.BX_constants import (
    M_ADJ,
    M_NONE,
    M_POLY,
)
from BX_bevelx.BX_math_utils import (
    copy_v3,
    solve_offset_meet_for_edgehalves,
)
from BX_bevelx.BX_types import (
    BevelParams,
    BevVert,
    BoundVert,
    EdgeHalf,
    Profile,
    VMesh,
)


# ---------------------------------------------------------------------------
# Blender-shaped EdgeHalf / BoundVert topology helpers
# ---------------------------------------------------------------------------

def iter_edgehalf_ring(bevvert: BevVert):
    """
    Iterate the EdgeHalf ring of one BevVert in stored CCW order.

    The ring itself is already linked by EdgeHalf.next / EdgeHalf.prev during
    BevVert construction. This helper intentionally returns the stored list
    order so tests are deterministic.
    """

    for edge_half in bevvert.edges:
        yield edge_half


def count_beveled_edgehalves(bevvert: BevVert) -> int:
    return len([edge_half for edge_half in bevvert.edges if edge_half.is_bev])


def new_boundvert_on_vmesh(bevvert: BevVert, co) -> BoundVert:
    """
    Add a BoundVert to the BevVert VMesh boundary ring.

    Blender equivalent:
        add_new_bound_vert(vm, co)
    """

    if bevvert.vmesh is None:
        bevvert.vmesh = VMesh()

    return bevvert.vmesh.add_new_bound_vert(co)


def initialize_boundvert_profile(boundvert: BoundVert, params: BevelParams) -> Profile:
    """
    Initialize the Profile stored on this BoundVert.

    Blender stores a profile on each BoundVert for the boundary edge from this
    BoundVert to the next BoundVert.
    """

    boundvert.profile = Profile()
    boundvert.profile.super_r = params.pro_super_r

    return boundvert.profile


def assign_boundvert_to_edgehalves(boundvert: BoundVert,
                                   previous_half: EdgeHalf,
                                   current_half: EdgeHalf):
    """
    Assign BoundVert ownership to the two neighboring EdgeHalves.

    Sector convention:
        previous_half -> boundvert -> current_half

    Blender EdgeHalf ownership convention:
        previous beveled edge receives this as rightv.
        current beveled edge receives this as leftv.
    """

    boundvert.efirst = previous_half
    boundvert.elast = current_half

    if previous_half.is_bev:
        previous_half.rightv = boundvert
        boundvert.ebev = previous_half

    if current_half.is_bev:
        current_half.leftv = boundvert
        if boundvert.ebev is None:
            boundvert.ebev = current_half


# ---------------------------------------------------------------------------
# BoundVert construction
# ---------------------------------------------------------------------------

def build_sector_boundvert(params: BevelParams,
                           bevvert: BevVert,
                           previous_half: EdgeHalf,
                           current_half: EdgeHalf) -> Optional[BoundVert]:
    """
    Build one BoundVert for the sector between two neighboring EdgeHalves.

    This is Blender-shaped topology:
        neighboring EdgeHalves define one boundary sector.

    Geometry is delegated to BX_math_utils.solve_offset_meet_for_edgehalves().
    This module owns only BoundVert topology and EdgeHalf ownership.
    """

    previous_is_bev = previous_half.is_bev
    current_is_bev = current_half.is_bev

    if not previous_is_bev and not current_is_bev:
        return None

    co = solve_offset_meet_for_edgehalves(
        params=params,
        bevvert=bevvert,
        previous_half=previous_half,
        current_half=current_half,
    )

    if co is None:
        return None

    boundvert = new_boundvert_on_vmesh(
        bevvert=bevvert,
        co=co,
    )

    # eon is the unbeveled/support EdgeHalf when this BoundVert lies on one.
    if previous_is_bev and not current_is_bev:
        boundvert.eon = current_half
    elif current_is_bev and not previous_is_bev:
        boundvert.eon = previous_half
    else:
        boundvert.eon = None

    initialize_boundvert_profile(
        boundvert=boundvert,
        params=params,
    )

    assign_boundvert_to_edgehalves(
        boundvert=boundvert,
        previous_half=previous_half,
        current_half=current_half,
    )

    return boundvert


def clear_existing_boundverts(bevvert: BevVert, params: BevelParams):
    """
    Reset BoundVert and VMesh state before rebuilding.
    """

    bevvert.vmesh = VMesh()
    bevvert.vmesh.seg = max(1, int(params.seg))

    for edge_half in bevvert.edges:
        edge_half.leftv = None
        edge_half.rightv = None


def set_vmesh_kind_for_bevvert(bevvert: BevVert, params: BevelParams) -> str:
    """
    Assign the initial VMesh kind.

    This mirrors the important Blender cases needed at this stage:
        - no boundary verts -> M_NONE
        - selcount == 2 and count == 2 -> weld/no-vmesh -> M_NONE
        - count >= 3 and seg == 1 -> M_POLY
        - count >= 3 and seg > 1 -> M_ADJ
    """

    vm = bevvert.vmesh
    vm.seg = max(1, int(params.seg))

    if vm.count == 0:
        vm.mesh_kind = M_NONE
        return vm.mesh_kind

    if bevvert.selcount == 2 and vm.count == 2:
        vm.mesh_kind = M_NONE
        return vm.mesh_kind

    if vm.count >= 3 and vm.seg == 1:
        vm.mesh_kind = M_POLY
        return vm.mesh_kind

    if vm.count >= 3:
        vm.mesh_kind = M_ADJ
        return vm.mesh_kind

    vm.mesh_kind = M_NONE
    return vm.mesh_kind


def build_boundverts_for_bevvert(params: BevelParams, bevvert: BevVert) -> VMesh:
    """
    Build the circular BoundVert ring for one BevVert.

    Blender-shaped phase:
        BevVert EdgeHalf ring -> VMesh.boundstart circular BoundVert ring
    """

    clear_existing_boundverts(
        bevvert=bevvert,
        params=params,
    )

    if not bevvert.edges:
        set_vmesh_kind_for_bevvert(bevvert, params)
        return bevvert.vmesh

    edge_count = len(bevvert.edges)

    for index in range(edge_count):
        previous_half = bevvert.edges[index]
        current_half = bevvert.edges[(index + 1) % edge_count]

        build_sector_boundvert(
            params=params,
            bevvert=bevvert,
            previous_half=previous_half,
            current_half=current_half,
        )

    set_vmesh_kind_for_bevvert(
        bevvert=bevvert,
        params=params,
    )

    return bevvert.vmesh


def build_boundverts(params: BevelParams,
                     bevverts: Optional[Iterable[BevVert]] = None) -> BevelParams:
    """
    Build BoundVert rings for all BevVerts.

    If bevverts is None, use params.vert_hash.values().
    """

    params.normalize()

    if bevverts is None:
        bevverts = params.vert_hash.values()

    for bevvert in bevverts:
        build_boundverts_for_bevvert(
            params=params,
            bevvert=bevvert,
        )

    return params


# ---------------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------------

def edge_index(edge):
    return getattr(edge, "index", None)


def vert_index(vert):
    return getattr(vert, "index", None)


def edgehalf_index(edge_half: Optional[EdgeHalf]):
    if edge_half is None:
        return None

    if edge_half.e is None:
        return None

    return edge_index(edge_half.e)


def boundvert_debug_record(boundvert: BoundVert):
    return {
        "index": boundvert.index,
        "co": copy_v3(boundvert.nv.co),
        "efirst": edgehalf_index(boundvert.efirst),
        "elast": edgehalf_index(boundvert.elast),
        "eon": edgehalf_index(boundvert.eon),
        "ebev": edgehalf_index(boundvert.ebev),
    }


def debug_boundvert_summary(params: BevelParams) -> List[str]:
    """
    Human-readable BoundVert summary for smoke tests.
    """

    lines = []

    for vert, bevvert in sorted(
        params.vert_hash.items(),
        key=lambda item: getattr(item[0], "index", -1),
    ):
        vm = bevvert.vmesh
        records = []

        if vm.boundstart is not None:
            for boundvert in vm.iter_boundverts():
                records.append(boundvert_debug_record(boundvert))

        lines.append(
            "BevVert vert={0} selcount={1} edgecount={2} vmesh_count={3} mesh_kind={4} boundverts={5}".format(
                vert_index(bevvert.v),
                bevvert.selcount,
                bevvert.edgecount,
                vm.count,
                vm.mesh_kind,
                records,
            )
        )

    return lines


def debug_edgehalf_boundverts(params: BevelParams) -> List[str]:
    """
    Debug selected EdgeHalf left/right assignments.
    """

    lines = []

    for vert, bevvert in sorted(
        params.vert_hash.items(),
        key=lambda item: getattr(item[0], "index", -1),
    ):
        for edge_half in bevvert.edges:
            if not edge_half.is_bev:
                continue

            lines.append(
                "EdgeHalf vert={0} edge={1} leftv={2} rightv={3}".format(
                    vert_index(bevvert.v),
                    edge_index(edge_half.e),
                    getattr(edge_half.leftv, "index", None),
                    getattr(edge_half.rightv, "index", None),
                )
            )

    return lines
