# BX_bevelx/BX_build_bevverts.py
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

from BX_bevelx.BX_mesh_model import BMesh, BMEdge, BMFace, BMLoop, BMVert
from BX_bevelx.BX_types import BevVert, BevelParams, EdgeHalf


SelectedEdgeInput = Union[BMEdge, int]


def normalize_selected_edges(bm, selected_edges):
    """
    Convert selected edge inputs into BMEdge objects.

    Maya adapter rule:
        selected int ids are Maya source edge ids.
        Prefer bm.source_edge_id_to_edge over bm.edges[index].

    Internal test rule:
        if source map is not available, fall back to bm.edges[index].
    """
    result = set()

    source_map = getattr(bm, "source_edge_id_to_edge", {})

    for edge_input in selected_edges:
        # Already a BMEdge-like object.
        if hasattr(edge_input, "verts"):
            result.add(edge_input)
            continue

        edge_id = int(edge_input)

        if edge_id in source_map:
            result.add(source_map[edge_id])
            continue

        if 0 <= edge_id < len(bm.edges):
            result.add(bm.edges[edge_id])
            continue

        raise IndexError(
            "Selected edge id {} is not available in source map or bm.edges.".format(
                edge_id
            )
        )

    return result

def find_bevvert(bp: BevelParams,
                 vert: BMVert) -> Optional[BevVert]:
    """
    Blender-equivalent lookup for the BevVert associated with a BMVert.
    """

    return bp.vert_hash.get(vert)


def ensure_bevvert(bp: BevelParams,
                   vert: BMVert) -> BevVert:
    """
    Create or return the BevVert for a BMVert.
    """

    bv = find_bevvert(bp, vert)

    if bv is not None:
        return bv

    bv = BevVert()
    bv.v = vert
    bv.offset = bp.offset
    bv.visited = False
    bv.any_seam = False
    bv.edgecount = 0
    bv.selcount = 0
    bv.wirecount = 0
    bv.edges = []
    bv.wire_edges = []
    bv.vmesh.seg = bp.seg

    bp.vert_hash[vert] = bv

    return bv


def edge_is_beveled(edge: BMEdge,
                    selected_edges: Set[BMEdge]) -> bool:
    return edge in selected_edges


def loops_at_vert_using_edge(vert: BMVert,
                             edge: BMEdge) -> List[BMLoop]:
    """
    Return loops whose corner vertex is vert and whose outgoing edge is edge.
    """

    result = []

    for loop in vert.link_loops:
        if not loop.is_valid:
            continue

        if loop.f is None or not loop.f.is_valid:
            continue

        if loop.e is edge:
            result.append(loop)

    return result


def loops_at_vert_with_prev_edge(vert: BMVert,
                                 edge: BMEdge) -> List[BMLoop]:
    """
    Return loops whose corner vertex is vert and whose incoming previous edge is edge.
    """

    result = []

    for loop in vert.link_loops:
        if not loop.is_valid:
            continue

        if loop.f is None or not loop.f.is_valid:
            continue

        if loop.prev is not None and loop.prev.e is edge:
            result.append(loop)

    return result


def edges_face_connected_at_vert(edge_a: BMEdge,
                                 edge_b: BMEdge,
                                 vert: BMVert) -> Optional[BMFace]:
    """
    Blender-equivalent question:
        Are two edges connected by a face at this vertex?

    Return one face that contains both edges at the vertex, or None.
    """

    for loop in vert.link_loops:
        if not loop.is_valid:
            continue

        if loop.f is None or not loop.f.is_valid:
            continue

        if loop.prev is None:
            continue

        prev_edge = loop.prev.e
        next_edge = loop.e

        if (prev_edge is edge_a and next_edge is edge_b) or (
            prev_edge is edge_b and next_edge is edge_a
        ):
            return loop.f

    return None


def build_edge_adjacency_at_vert(vert: BMVert) -> Dict[BMEdge, List[BMEdge]]:
    """
    Build a face-corner adjacency graph between edges incident to vert.

    Each face corner contributes an adjacency pair:
        loop.prev.e <-> loop.e

    This is a Python substitute for walking BMesh disk/radial cycles when
    constructing the ordered EdgeHalf ring around a BevVert.
    """

    adjacency = {}

    for edge in vert.link_edges:
        if edge.is_valid:
            adjacency.setdefault(edge, [])

    for loop in vert.link_loops:
        if not loop.is_valid:
            continue

        if loop.f is None or not loop.f.is_valid:
            continue

        if loop.prev is None:
            continue

        edge_prev = loop.prev.e
        edge_next = loop.e

        if edge_prev is None or edge_next is None:
            continue

        if not edge_prev.is_valid or not edge_next.is_valid:
            continue

        if edge_prev not in adjacency:
            adjacency[edge_prev] = []

        if edge_next not in adjacency:
            adjacency[edge_next] = []

        if edge_next not in adjacency[edge_prev]:
            adjacency[edge_prev].append(edge_next)

        if edge_prev not in adjacency[edge_next]:
            adjacency[edge_next].append(edge_prev)

    return adjacency


def find_boundary_start_edge(vert: BMVert,
                             adjacency: Dict[BMEdge, List[BMEdge]],
                             selected_edges: Set[BMEdge]) -> Optional[BMEdge]:
    """
    Pick a stable start edge for the edge ring.

    Preference:
        1. boundary edge with one adjacency
        2. selected edge
        3. lowest-index incident edge
    """

    incident_edges = [edge for edge in vert.link_edges if edge.is_valid]

    if not incident_edges:
        return None

    boundary_candidates = [
        edge for edge in incident_edges
        if len(adjacency.get(edge, [])) <= 1
    ]

    if boundary_candidates:
        return sorted(boundary_candidates, key=lambda edge: edge.index)[0]

    selected_candidates = [
        edge for edge in incident_edges
        if edge in selected_edges
    ]

    if selected_candidates:
        return sorted(selected_candidates, key=lambda edge: edge.index)[0]

    return sorted(incident_edges, key=lambda edge: edge.index)[0]


def order_edges_around_vert(vert: BMVert,
                            selected_edges: Set[BMEdge]) -> List[BMEdge]:
    """
    Return incident edges in deterministic face-connected order around vert.

    Blender uses BMesh disk/radial structure directly. Our internal BMesh model
    stores explicit loop references, so this constructs an equivalent ordering
    from face corner adjacency.
    """

    incident_edges = [edge for edge in vert.link_edges if edge.is_valid]

    if len(incident_edges) <= 1:
        return incident_edges

    adjacency = build_edge_adjacency_at_vert(vert)
    start_edge = find_boundary_start_edge(vert, adjacency, selected_edges)

    if start_edge is None:
        return []

    ordered = [start_edge]
    used = set([start_edge])
    previous = None
    current = start_edge

    while True:
        neighbors = sorted(
            adjacency.get(current, []),
            key=lambda edge: edge.index,
        )

        next_edge = None

        for candidate in neighbors:
            if candidate is previous:
                continue

            if candidate in used:
                continue

            next_edge = candidate
            break

        if next_edge is None:
            break

        ordered.append(next_edge)
        used.add(next_edge)
        previous = current
        current = next_edge

        if len(ordered) == len(incident_edges):
            break

    # If the graph is non-manifold or disconnected, append missing edges in
    # stable index order rather than silently dropping them.
    for edge in sorted(incident_edges, key=lambda item: item.index):
        if edge not in used:
            ordered.append(edge)
            used.add(edge)

    return ordered


def face_between_ordered_edges_at_vert(vert: BMVert,
                                       edge_prev: BMEdge,
                                       edge_next: BMEdge) -> Optional[BMFace]:
    """
    Return the face that lies between ordered edge_prev -> edge_next at vert.
    """

    for loop in vert.link_loops:
        if not loop.is_valid:
            continue

        if loop.f is None or not loop.f.is_valid:
            continue

        if loop.prev is None:
            continue

        if loop.prev.e is edge_prev and loop.e is edge_next:
            return loop.f

    return None


def new_edgehalf_for_edge(vert: BMVert,
                          edge: BMEdge,
                          selected_edges: Set[BMEdge],
                          params: BevelParams) -> EdgeHalf:
    """
    Create a Blender-style EdgeHalf wrapper for an edge incident to vert.
    """

    edge_half = EdgeHalf()
    edge_half.e = edge
    edge_half.is_bev = edge in selected_edges
    edge_half.is_seam = bool(getattr(edge, "seam", False))
    edge_half.seg = int(params.seg)
    edge_half.offset_l = params.offset
    edge_half.offset_r = params.offset
    edge_half.offset_l_spec = params.offset
    edge_half.offset_r_spec = params.offset
    edge_half.profile_index = 0
    edge_half.visited_rpo = False
    edge_half.is_rev = False

    return edge_half


def find_edge_half(bv: BevVert,
                   edge: BMEdge) -> Optional[EdgeHalf]:
    """
    Find the EdgeHalf for an original BMEdge in a BevVert.
    """

    for edge_half in bv.edges:
        if edge_half.e is edge:
            return edge_half

    return None


def find_other_end_edge_half(bp: BevelParams,
                             edge_half: EdgeHalf,
                             current_bv: BevVert) -> Optional[EdgeHalf]:
    """
    Return the EdgeHalf at the other endpoint of edge_half.e.
    """

    edge = edge_half.e

    if edge is None or current_bv.v is None:
        return None

    other_vert = edge.other_vert(current_bv.v)

    if other_vert is None:
        return None

    other_bv = find_bevvert(bp, other_vert)

    if other_bv is None:
        return None

    return find_edge_half(other_bv, edge)


def count_ccw_edges_between(edge_a: EdgeHalf,
                            edge_b: EdgeHalf) -> int:
    """
    Count EdgeHalves walking next links from edge_a to edge_b.

    Returns -1 if the ring is malformed.
    """

    if edge_a is edge_b:
        return 0

    count = 0
    current = edge_a

    while True:
        current = current.next
        count += 1

        if current is None:
            return -1

        if current is edge_b:
            return count

        if current is edge_a:
            return -1


def link_edgehalf_ring(bv: BevVert,
                       edge_halves: Sequence[EdgeHalf]):
    """
    Link edge halves into a cyclic ordered ring.
    """

    count = len(edge_halves)

    if count == 0:
        return

    for i, edge_half in enumerate(edge_halves):
        edge_half.prev = edge_halves[(i - 1) % count]
        edge_half.next = edge_halves[(i + 1) % count]

        edge_prev = edge_half.prev.e
        edge_next = edge_half.next.e

        edge_half.fprev = face_between_ordered_edges_at_vert(
            vert=bv.v,
            edge_prev=edge_prev,
            edge_next=edge_half.e,
        )

        edge_half.fnext = face_between_ordered_edges_at_vert(
            vert=bv.v,
            edge_prev=edge_half.e,
            edge_next=edge_next,
        )


def find_bevel_edge_order(bm: BMesh,
                          bv: BevVert,
                          selected_edges: Set[BMEdge],
                          params: BevelParams) -> List[EdgeHalf]:
    """
    Build ordered EdgeHalves around a BevVert.

    This is the Python entry point corresponding to Blender's edge-order work
    before BoundVert construction.
    """

    ordered_edges = order_edges_around_vert(bv.v, selected_edges)
    edge_halves = []

    for edge in ordered_edges:
        edge_half = new_edgehalf_for_edge(
            vert=bv.v,
            edge=edge,
            selected_edges=selected_edges,
            params=params,
        )

        edge_halves.append(edge_half)

    link_edgehalf_ring(bv, edge_halves)

    bv.edges = edge_halves
    bv.edgecount = len(edge_halves)
    bv.selcount = len([edge_half for edge_half in edge_halves if edge_half.is_bev])
    bv.wire_edges = [edge_half.e for edge_half in edge_halves if edge_half.e.is_wire]
    bv.wirecount = len(bv.wire_edges)
    bv.any_seam = any(edge_half.is_seam for edge_half in edge_halves)

    return edge_halves


def bevel_vert_construct(bm: BMesh,
                         selected_edges: Iterable[SelectedEdgeInput],
                         params: BevelParams) -> Dict[BMVert, BevVert]:
    """
    Construct BevVerts for every endpoint of every selected edge.

    This is the first solver construction phase:
        selected BMEdges -> affected BMVerts -> BevVert + ordered EdgeHalf rings.
    """

    params.bm = bm
    params.normalize()
    params.vert_hash.clear()

    selected_edges = normalize_selected_edges(bm, selected_edges)

    params.selected_edges = selected_edges

    for edge in selected_edges:
        ensure_bevvert(params, edge.v1)
        ensure_bevvert(params, edge.v2)

    for vert, bv in list(params.vert_hash.items()):
        find_bevel_edge_order(
            bm=bm,
            bv=bv,
            selected_edges=selected_edges,
            params=params,
        )

    return params.vert_hash


def iter_bevverts(params: BevelParams):
    for vert in sorted(params.vert_hash.keys(), key=lambda item: item.index):
        yield params.vert_hash[vert]

def debug_edgehalf_ring_detailed(params: BevelParams) -> List[str]:
    """
    Detailed EdgeHalf ring debug.

    Use this before touching normals or winding code.
    """
    lines = []
    lines.append("-- EdgeHalf Rings Detailed --")

    for vert in sorted(params.vert_hash.keys(), key=lambda item: item.index):
        bevvert = params.vert_hash[vert]

        lines.append(
            "BevVert vert={} co={} edgecount={} selcount={}".format(
                getattr(vert, "index", None),
                getattr(vert, "co", None),
                bevvert.edgecount,
                bevvert.selcount,
            )
        )

        for i, edge_half in enumerate(bevvert.edges):
            edge = edge_half.e
            other = edge.other_vert(vert) if hasattr(edge, "other_vert") else None

            fprev = edge_half.fprev
            fnext = edge_half.fnext

            lines.append(
                "  EH {} edge={} other={} is_bev={} prev={} next={} "
                "fprev={} fprev_no={} fnext={} fnext_no={}".format(
                    i,
                    getattr(edge, "index", None),
                    getattr(other, "index", None),
                    edge_half.is_bev,
                    getattr(getattr(edge_half, "prev", None), "e", None).index
                    if getattr(edge_half, "prev", None) is not None else None,
                    getattr(getattr(edge_half, "next", None), "e", None).index
                    if getattr(edge_half, "next", None) is not None else None,
                    getattr(fprev, "index", None),
                    getattr(fprev, "normal", None),
                    getattr(fnext, "index", None),
                    getattr(fnext, "normal", None),
                )
            )

    return lines

def debug_bevvert_summary(params: BevelParams) -> List[str]:
    lines = []

    for bv in iter_bevverts(params):
        edge_indices = [edge_half.e.index for edge_half in bv.edges]
        selected_indices = [edge_half.e.index for edge_half in bv.edges if edge_half.is_bev]

        lines.append(
            "BevVert vert={0} edgecount={1} selcount={2} edges={3} selected={4}".format(
                bv.v.index,
                bv.edgecount,
                bv.selcount,
                edge_indices,
                selected_indices,
            )
        )

    return lines
