# BX_bevelx/BX_rebuild_polygons.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Set

from BX_bevelx.BX_math_utils import copy_v3, len_v3v3
from BX_bevelx.BX_types import BevelParams, BevVert, BoundVert, NewVert

@dataclass(init=False)
class RebuiltPolygon:
    """
    Polygon record produced by Blender-style source face rebuild.

    Standard field:
        newverts

    Notes:
        The solver should use .newverts everywhere.
        The .verts alias only exists so older internal callers do not crash
        while this file is being normalized.
    """

    face: object
    newverts: List[NewVert]
    kind: str

    def __init__(self,
                 face=None,
                 newverts=None,
                 verts=None,
                 kind="REBUILT"):
        self.face = face

        if newverts is None:
            newverts = verts

        if newverts is None:
            newverts = []

        self.newverts = list(newverts)
        self.kind = kind

    @property
    def verts(self):
        return self.newverts

    @verts.setter
    def verts(self, value):
        self.newverts = list(value) if value is not None else []


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


def original_face_polygon(face):
    """
    Carry an untouched original face into the emitted mesh.

    Blender leaves untouched faces in the BMesh.
    BevelX currently emits a full pydata mesh, so untouched faces must be
    represented explicitly for now.
    """

    if face is None:
        return None

    newverts = []

    for loop in getattr(face, "loops", []) or []:
        vert = getattr(loop, "v", None)

        if vert is None:
            continue

        newverts.append(original_vert_newvert(vert))

    newverts = collapse_adjacent_duplicate_newverts(newverts)

    if not rebuilt_polygon_is_valid(newverts):
        return None

    return RebuiltPolygon(
        face=face,
        newverts=newverts,
        kind="ORIG",
    )

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
        terminal_replacement = terminal_support_face_replacement(
            params=params,
            loop=loop
        )

        if terminal_replacement:
            newverts.extend(terminal_replacement)
            continue
        
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
        face=face,
        verts=newverts,
    )

def original_face_polygon(face):
    """
    Carry an untouched original face into the emitted mesh.

    Blender leaves untouched faces in the BMesh. Since BevelX currently emits
    a full pydata mesh, untouched faces must be represented explicitly.
    """
    if face is None:
        return None

    newverts = []

    for loop in getattr(face, "loops", []) or []:
        vert = getattr(loop, "v", None)
        if vert is None:
            continue

        newverts.append(original_vert_newvert(vert))

    newverts = collapse_adjacent_duplicate_newverts(newverts)

    if not rebuilt_polygon_is_valid(newverts):
        return None

    polygon = RebuiltPolygon(
        face=face,
        newverts=newverts,
    )

    setattr(polygon, "kind", "ORIG")

    return polygon

def get_edge_index(edge):
    if edge is None:
        return None

    return getattr(edge, "index", None)


def get_edgehalf_edge_index(edge_half):
    if edge_half is None:
        return None

    edge = getattr(edge_half, "e", None)
    return get_edge_index(edge)


def iter_vmesh_boundverts(vmesh):
    """
    Iterate BoundVerts in a VMesh ring.
    """

    if vmesh is None:
        return

    if hasattr(vmesh, "iter_boundverts"):
        for boundvert in vmesh.iter_boundverts() or []:
            yield boundvert
        return

    start = getattr(vmesh, "boundstart", None)

    if start is None:
        return

    current = start

    while True:
        yield current
        current = current.next

        if current is start:
            break


def get_bevvert_for_original_vert(params, vert):
    """
    Return BevVert for a BMVert from params.vert_hash.
    """

    vert_hash = getattr(params, "vert_hash", {})

    if vert in vert_hash:
        return vert_hash[vert]

    return None


def terminal_boundvert_by_eon(bevvert, edge):
    """
    Find a terminal BoundVert whose eon edge matches edge.
    """

    edge_id = get_edge_index(edge)

    if edge_id is None:
        return None

    for boundvert in iter_vmesh_boundverts(getattr(bevvert, "vmesh", None)):
        eon = getattr(boundvert, "eon", None)
        eon_edge_id = get_edgehalf_edge_index(eon)

        if eon_edge_id == edge_id:
            return boundvert

    return None


def terminal_support_face_replacement(params, loop):
    """
    Blender-style terminal support-face corner replacement.

    Case:
        - loop.v is an affected bevel vertex
        - that BevVert has selcount == 1
        - this face corner is between the two non-selected support edges

    Then replace the original corner vertex with the two terminal BoundVerts.

    Original side face corner:
        previous_edge -> original_vertex -> next_edge

    Rebuilt side face corner:
        previous_boundvert -> next_boundvert
    """

    if loop is None:
        return []

    vert = getattr(loop, "v", None)

    if vert is None:
        return []

    bevvert = get_bevvert_for_original_vert(params, vert)

    if bevvert is None:
        return []

    if getattr(bevvert, "selcount", None) != 1:
        return []

    previous_loop = getattr(loop, "prev", None)

    if previous_loop is None:
        previous_loop = getattr(loop, "link_loop_prev", None)

    previous_edge = getattr(previous_loop, "e", None)
    next_edge = getattr(loop, "e", None)

    if previous_edge is None or next_edge is None:
        return []

    previous_boundvert = terminal_boundvert_by_eon(
        bevvert=bevvert,
        edge=previous_edge
    )

    next_boundvert = terminal_boundvert_by_eon(
        bevvert=bevvert,
        edge=next_edge
    )

    if previous_boundvert is None or next_boundvert is None:
        return []

    if previous_boundvert is next_boundvert:
        return [previous_boundvert.nv]

    return [
        previous_boundvert.nv,
        next_boundvert.nv,
    ]

def rebuild_polygons(params: BevelParams,
                     faces: Optional[Iterable[object]] = None) -> BevelParams:
    """
    Rebuild/carry source polygons after boundary, vmesh, and edge polygon phases.

    Blender behavior:
        affected faces are rebuilt
        untouched faces remain

    Current BevelX pydata behavior:
        affected faces are rebuilt
        untouched faces are carried forward explicitly
    """

    clear_rebuilt_polygons(params)

    selected_edges = selected_edges_from_params(params)

    if faces is None:
        bm = getattr(params, "bm", None)
        faces = getattr(bm, "faces", []) if bm is not None else []

    for face in faces:
        if face_is_affected(face, selected_edges, params):
            polygon = rebuild_face_polygon(
                params=params,
                face=face,
                selected_edges=selected_edges,
            )

            if polygon is not None:
                polygon.kind = "REBUILT"
        else:
            polygon = original_face_polygon(face)

        if polygon is None:
            continue

        polygon.newverts = collapse_adjacent_duplicate_newverts(polygon.newverts)

        if not rebuilt_polygon_is_valid(polygon.newverts):
            continue

        params.rebuilt_polygons.append(polygon)

    return params

# ---------------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------------

def debug_rebuilt_polygon_summary(params: BevelParams) -> List[str]:
    lines = []

    for polygon in get_rebuilt_polygons(params):
        face = getattr(polygon, "face", None)
        face_id = face_index(face)
        kind = getattr(polygon, "kind", "REBUILT")

        verts = [
            copy_v3(newvert.co)
            for newvert in polygon.newverts
        ]

        lines.append(
            "RebuiltPolygon kind={} face={} verts={}".format(
                kind,
                face_id,
                verts
            )
        )

    return lines