# BX_bevelx/BX_rebuild_polygons.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Set

from BX_bevelx.BX_math_utils import copy_v3, len_v3v3
from BX_bevelx.BX_types import BevelParams, BevVert, BoundVert, NewVert


@dataclass
class RebuiltPolygon:
    """
    Blender-shaped rebuilt source polygon record.

    This is not a transaction face. It is the Python port's generated polygon
    record for the phase equivalent to Blender's existing polygon rebuild.
    """

    source_face: object = None
    verts: List[NewVert] = field(default_factory=list)

    @property
    def coords(self):
        return [copy_v3(nv.co) for nv in self.verts]


# ---------------------------------------------------------------------------
# Small access helpers
# ---------------------------------------------------------------------------

def edge_index(edge):
    return getattr(edge, "index", None)


def vert_index(vert):
    return getattr(vert, "index", None)


def face_index(face):
    return getattr(face, "index", None)


def get_rebuilt_polygons(params: BevelParams) -> List[RebuiltPolygon]:
    if not hasattr(params, "rebuilt_polygons"):
        params.rebuilt_polygons = []
    return params.rebuilt_polygons


def clear_rebuilt_polygons(params: BevelParams):
    params.rebuilt_polygons = []


def original_vert_newvert(vert) -> NewVert:
    return NewVert(v=vert, co=copy_v3(vert.co))


def get_bevvert_for_vert(params: BevelParams, vert) -> Optional[BevVert]:
    return params.vert_hash.get(vert)


def selected_edges_from_params(params: BevelParams) -> Set[object]:
    selected = set()

    for bevvert in params.vert_hash.values():
        for edge_half in bevvert.edges:
            if edge_half.is_bev:
                selected.add(edge_half.e)

    return selected


def is_selected_edge(edge, selected_edges: Set[object]) -> bool:
    return edge in selected_edges


# ---------------------------------------------------------------------------
# BoundVert lookup helpers
# ---------------------------------------------------------------------------

def boundverts_for_bevvert(bevvert: BevVert) -> List[BoundVert]:
    vm = bevvert.vmesh

    if vm is None or vm.boundstart is None:
        return []

    return list(vm.iter_boundverts())


def find_edgehalf_for_edge(bevvert: BevVert, edge) -> Optional[object]:
    for edge_half in bevvert.edges:
        if edge_half.e is edge:
            return edge_half
    return None


def find_boundvert_exact_sector(bevvert: BevVert,
                                previous_edge,
                                current_edge) -> Optional[BoundVert]:
    """
    Find BoundVert whose sector is exactly previous_edge -> current_edge.
    """

    for boundvert in boundverts_for_bevvert(bevvert):
        if boundvert.efirst is None or boundvert.elast is None:
            continue

        if boundvert.efirst.e is previous_edge and boundvert.elast.e is current_edge:
            return boundvert

    return None


def find_boundvert_on_support_for_selected_corner(bevvert: BevVert,
                                                   selected_edge,
                                                   support_edge) -> Optional[BoundVert]:
    """
    For a face corner touched by one selected edge and one unselected edge,
    Blender's rebuilt source polygon needs the boundary point lying on the
    unselected support edge.

    This finds the BoundVert with:
        eon == support edge
        ebev == selected edge
    """

    for boundvert in boundverts_for_bevvert(bevvert):
        if boundvert.eon is None:
            continue

        if boundvert.eon.e is not support_edge:
            continue

        if boundvert.ebev is not None and boundvert.ebev.e is selected_edge:
            return boundvert

    # Fallback: eon support edge alone.
    for boundvert in boundverts_for_bevvert(bevvert):
        if boundvert.eon is not None and boundvert.eon.e is support_edge:
            return boundvert

    return None


def find_boundvert_for_selected_selected_corner(bevvert: BevVert,
                                                previous_edge,
                                                current_edge) -> Optional[BoundVert]:
    """
    For a corner where both incident source-face edges are selected, use the
    selected/selected BoundVert for that sector if present.
    """

    exact = find_boundvert_exact_sector(
        bevvert=bevvert,
        previous_edge=previous_edge,
        current_edge=current_edge,
    )

    if exact is not None:
        return exact

    reverse = find_boundvert_exact_sector(
        bevvert=bevvert,
        previous_edge=current_edge,
        current_edge=previous_edge,
    )

    return reverse


# ---------------------------------------------------------------------------
# Face corner replacement
# ---------------------------------------------------------------------------

def replacement_newverts_for_face_corner(params: BevelParams,
                                         face,
                                         loop,
                                         selected_edges: Set[object]) -> List[NewVert]:
    """
    Replacement for one source-face corner.

    This corresponds to the local behavior inside Blender's existing polygon
    rebuild phase: when a face loop reaches an affected original vertex, it
    replaces that vertex with the BoundVert/NewVert that belongs to that face
    side.
    """

    vert = loop.v
    bevvert = get_bevvert_for_vert(params, vert)

    if bevvert is None:
        return [original_vert_newvert(vert)]

    previous_edge = loop.prev.e
    current_edge = loop.e

    previous_selected = is_selected_edge(previous_edge, selected_edges)
    current_selected = is_selected_edge(current_edge, selected_edges)

    # No selected edge at this face corner. Use exact ring sector when the
    # vertex is affected by neighboring selected geometry; otherwise keep the
    # original vertex.
    if not previous_selected and not current_selected:
        exact = find_boundvert_exact_sector(
            bevvert=bevvert,
            previous_edge=previous_edge,
            current_edge=current_edge,
        )
        if exact is not None:
            return [exact.nv]
        return [original_vert_newvert(vert)]

    # Both incident edges selected: use selected/selected sector.
    if previous_selected and current_selected:
        boundvert = find_boundvert_for_selected_selected_corner(
            bevvert=bevvert,
            previous_edge=previous_edge,
            current_edge=current_edge,
        )
        if boundvert is not None:
            return [boundvert.nv]
        return []

    # One selected, one support. Rebuilt source face takes the boundary point
    # on the support edge, not the point on the selected edge. The selected-edge
    # side is owned by the bevel edge polygon phase.
    if previous_selected and not current_selected:
        boundvert = find_boundvert_on_support_for_selected_corner(
            bevvert=bevvert,
            selected_edge=previous_edge,
            support_edge=current_edge,
        )
        if boundvert is not None:
            return [boundvert.nv]
        return []

    # not previous_selected and current_selected
    boundvert = find_boundvert_on_support_for_selected_corner(
        bevvert=bevvert,
        selected_edge=current_edge,
        support_edge=previous_edge,
    )
    if boundvert is not None:
        return [boundvert.nv]

    return []


# ---------------------------------------------------------------------------
# Polygon cleanup and orientation
# ---------------------------------------------------------------------------

def newverts_are_same(a: NewVert, b: NewVert, epsilon=1.0e-9) -> bool:
    if a is b:
        return True

    return len_v3v3(a.co, b.co) <= epsilon


def collapse_adjacent_duplicate_newverts(newverts: Sequence[NewVert]) -> List[NewVert]:
    result = []

    for newvert in newverts:
        if result and newverts_are_same(result[-1], newvert):
            continue
        result.append(newvert)

    if len(result) > 1 and newverts_are_same(result[0], result[-1]):
        result.pop()

    return result


def rebuilt_polygon_is_valid(newverts: Sequence[NewVert]) -> bool:
    if len(newverts) < 3:
        return False

    # Need at least three distinct coordinate positions.
    unique = []
    for newvert in newverts:
        if not any(newverts_are_same(newvert, existing) for existing in unique):
            unique.append(newvert)

    return len(unique) >= 3


# ---------------------------------------------------------------------------
# Rebuild phase
# ---------------------------------------------------------------------------

def face_is_affected(face, selected_edges: Set[object], params: BevelParams) -> bool:
    """
    A face is affected if it touches a selected edge or an affected BevVert.
    """

    for edge in face.edges:
        if edge in selected_edges:
            return True

    for vert in face.verts:
        if vert in params.vert_hash:
            return True

    return False


def rebuild_face_polygon(params: BevelParams,
                         face,
                         selected_edges: Set[object]) -> Optional[RebuiltPolygon]:
    newverts = []

    for loop in face.loops:
        replacements = replacement_newverts_for_face_corner(
            params=params,
            face=face,
            loop=loop,
            selected_edges=selected_edges,
        )
        newverts.extend(replacements)

    newverts = collapse_adjacent_duplicate_newverts(newverts)

    if not rebuilt_polygon_is_valid(newverts):
        return None

    return RebuiltPolygon(
        source_face=face,
        verts=newverts,
    )


def rebuild_polygons(params: BevelParams,
                     faces: Optional[Iterable[object]] = None) -> BevelParams:
    """
    Rebuild existing source polygons after BoundVert and edge-polygon phases.

    This is the Python port's current equivalent of Blender's existing polygon
    rebuild phase. It produces RebuiltPolygon records on params.rebuilt_polygons.
    """

    clear_rebuilt_polygons(params)

    selected_edges = selected_edges_from_params(params)

    if faces is None:
        if params.bm is None:
            faces = []
        else:
            faces = params.bm.faces

    output = get_rebuilt_polygons(params)

    for face in faces:
        if not getattr(face, "is_valid", True):
            continue

        if not face_is_affected(face, selected_edges, params):
            continue

        rebuilt = rebuild_face_polygon(
            params=params,
            face=face,
            selected_edges=selected_edges,
        )

        if rebuilt is None:
            continue

        output.append(rebuilt)

    return params


# ---------------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------------

def debug_rebuilt_polygon_summary(params: BevelParams) -> List[str]:
    lines = []

    for polygon in get_rebuilt_polygons(params):
        lines.append(
            "RebuiltPolygon face={0} verts={1}".format(
                face_index(polygon.source_face),
                polygon.coords,
            )
        )

    return lines
