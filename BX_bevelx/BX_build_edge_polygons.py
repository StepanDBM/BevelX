# BX_bevelx/BX_build_edge_polygons.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Set

from BX_bevelx.BX_types import (
    BevelParams,
    BevVert,
    BoundVert,
    EdgeHalf,
    NewVert
)
from BX_bevelx.BX_build_bevverts import (
    find_bevvert,
    find_edge_half,
)
from BX_bevelx.BX_math_utils import (
    copy_v3,
    _vec_add,
    _vec_dot,
    _vec_normalize
    )


# ---------------------------------------------------------------------------
# Generated topology records
# ---------------------------------------------------------------------------

@dataclass
class EdgePolygon:
    """
    Polygon generated for one selected/beveled source edge.

    This is not a BevelX transaction face and it is not a Maya face yet.
    It is the Python-side generated topology record for Blender-style edge
    polygon construction. Final mesh emission happens later.
    """

    edge: object
    edge_half_a: EdgeHalf
    edge_half_b: EdgeHalf
    newverts: List[NewVert]
    label: str = "EDGE_POLYGON"


# ---------------------------------------------------------------------------
# EdgeHalf lookup
# ---------------------------------------------------------------------------

def edge_vertices(edge):
    return edge.verts[0], edge.verts[1]


def edge_index(edge):
    return getattr(edge, "index", None)


def vert_index(vert):
    return getattr(vert, "index", None)


def boundvert_index(boundvert: Optional[BoundVert]):
    return getattr(boundvert, "index", None)


def edgehalf_for_edge_at_vert(params: BevelParams, edge, vert) -> Optional[EdgeHalf]:
    """
    Return the EdgeHalf belonging to edge at a specific endpoint vertex.
    """

    bevvert = find_bevvert(params, vert)

    if bevvert is None:
        return None

    return find_edge_half(bevvert, edge)


def selected_edgehalves(params: BevelParams) -> List[EdgeHalf]:
    """
    Return selected EdgeHalves from all BevVerts.

    Each selected source edge appears twice, once at each endpoint.
    """

    result = []

    for vert, bevvert in sorted(
        params.vert_hash.items(),
        key=lambda item: getattr(item[0], "index", -1),
    ):
        for edge_half in bevvert.edges:
            if edge_half.is_bev:
                result.append(edge_half)

    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def edgehalf_has_boundary_pair(edge_half: EdgeHalf) -> bool:
    return edge_half.leftv is not None and edge_half.rightv is not None


def can_build_edge_polygon(edge_half_a: EdgeHalf,
                           edge_half_b: EdgeHalf) -> bool:
    """
    Validate that both endpoint EdgeHalves have left/right BoundVerts.
    """

    if edge_half_a is None or edge_half_b is None:
        return False

    if edge_half_a.e is None or edge_half_b.e is None:
        return False

    if edge_half_a.e is not edge_half_b.e:
        return False

    if not edgehalf_has_boundary_pair(edge_half_a):
        return False

    if not edgehalf_has_boundary_pair(edge_half_b):
        return False

    return True


# ---------------------------------------------------------------------------
# Polygon construction
# ---------------------------------------------------------------------------


def _newell_normal_from_newverts(newverts):
    """
    Compute polygon normal from NewVert list using emitted winding.
    """
    if not newverts or len(newverts) < 3:
        return None

    nx = 0.0
    ny = 0.0
    nz = 0.0

    count = len(newverts)

    for i in range(count):
        current = newverts[i].co
        nxt = newverts[(i + 1) % count].co

        nx += (current[1] - nxt[1]) * (current[2] + nxt[2])
        ny += (current[2] - nxt[2]) * (current[0] + nxt[0])
        nz += (current[0] - nxt[0]) * (current[1] + nxt[1])

    return _vec_normalize([nx, ny, nz])


def _expected_normal_from_source_edge(edge):
    """
    Expected bevel face normal from the selected source edge.

    For a normal manifold edge, this is the normalized average of the two
    adjacent source face normals.

    For boundary/non-manifold cases, use whatever source face normals exist.
    """
    if edge is None:
        return None

    faces = getattr(edge, "link_faces", []) or []
    normal_sum = [0.0, 0.0, 0.0]

    valid_count = 0

    for face in faces:
        normal = getattr(face, "normal", None)

        if normal is None:
            continue

        normal_sum = _vec_add(normal_sum, normal)
        valid_count += 1

    if valid_count == 0:
        return None

    return _vec_normalize(normal_sum)


def orient_edge_polygon_newverts_to_source_edge(newverts, edge):
    """
    Orient generated edge polygon winding to match the selected source edge.

    This fixes cases where the same left/right construction order creates an
    inward bevel face for some edges depending on source edge orientation.
    """
    expected_normal = _expected_normal_from_source_edge(edge)

    if expected_normal is None:
        return newverts

    actual_normal = _newell_normal_from_newverts(newverts)

    if actual_normal is None:
        return newverts

    if _vec_dot(actual_normal, expected_normal) < 0.0:
        newverts.reverse()

    return newverts

def edge_polygon_newverts(edge_half_a: EdgeHalf,
                          edge_half_b: EdgeHalf) -> List[NewVert]:
    """
    Build the four NewVerts for a selected edge polygon.

    Endpoint order follows the source edge direction:
        A = edge.verts[0]
        B = edge.verts[1]

    Polygon order:
        A.leftv
        B.leftv
        B.rightv
        A.rightv

    For the single-edge quad smoke test this gives:
        [0.1, 0.0, 0.0]
        [0.9, 0.0, 0.0]
        [1.0, 0.1, 0.0]
        [0.0, 0.1, 0.0]
    """

    return [
        edge_half_a.leftv.nv,
        edge_half_b.leftv.nv,
        edge_half_b.rightv.nv,
        edge_half_a.rightv.nv,
    ]


def build_edge_polygon_for_edge(params: BevelParams, edge) -> Optional[EdgePolygon]:
    """
    Build one edge polygon for one selected source edge.
    """

    vert_a, vert_b = edge_vertices(edge)

    edge_half_a = edgehalf_for_edge_at_vert(
        params=params,
        edge=edge,
        vert=vert_a,
    )

    edge_half_b = edgehalf_for_edge_at_vert(
        params=params,
        edge=edge,
        vert=vert_b,
    )

    if not can_build_edge_polygon(edge_half_a, edge_half_b):
        return None

    newverts = edge_polygon_newverts(
        edge_half_a=edge_half_a,
        edge_half_b=edge_half_b,
    )
    newverts = orient_edge_polygon_newverts_to_source_edge(
        newverts=newverts,
        edge=edge,
    )
    return EdgePolygon(
        edge=edge,
        edge_half_a=edge_half_a,
        edge_half_b=edge_half_b,
        newverts=newverts,
    )


def build_edge_polygons(params: BevelParams) -> BevelParams:
    """
    Build generated edge polygons for all selected source edges.

    Inputs expected to exist:
        - params.vert_hash with BevVerts
        - each BevVert has EdgeHalves
        - build_boundverts() has assigned leftv/rightv on selected EdgeHalves

    Output:
        - params.generated_edge_polygons
    """

    seen_edges: Set[object] = set()
    polygons: List[EdgePolygon] = []

    for edge_half in selected_edgehalves(params):
        edge = edge_half.e

        if edge in seen_edges:
            continue

        seen_edges.add(edge)

        polygon = build_edge_polygon_for_edge(
            params=params,
            edge=edge,
        )

        if polygon is not None:
            polygons.append(polygon)

    params.generated_edge_polygons = polygons

    return params


# ---------------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------------

def newvert_co(newvert: NewVert):
    return copy_v3(newvert.co)


def edge_polygon_debug_record(polygon: EdgePolygon):
    return {
        "edge": edge_index(polygon.edge),
        "verts": [newvert_co(newvert) for newvert in polygon.newverts],
        "a_left": boundvert_index(polygon.edge_half_a.leftv),
        "a_right": boundvert_index(polygon.edge_half_a.rightv),
        "b_left": boundvert_index(polygon.edge_half_b.leftv),
        "b_right": boundvert_index(polygon.edge_half_b.rightv),
    }


def debug_edge_polygon_summary(params: BevelParams) -> List[str]:
    """
    Human-readable edge polygon summary for smoke tests.
    """

    polygons = getattr(params, "generated_edge_polygons", [])
    lines = []

    for polygon in polygons:
        record = edge_polygon_debug_record(polygon)
        lines.append(
            "EdgePolygon edge={0} verts={1} a_left={2} a_right={3} b_left={4} b_right={5}".format(
                record["edge"],
                record["verts"],
                record["a_left"],
                record["a_right"],
                record["b_left"],
                record["b_right"],
            )
        )

    if not lines:
        lines.append("EdgePolygon none")

    return lines
