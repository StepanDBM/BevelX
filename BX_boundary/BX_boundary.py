# BX_boundary.py

from __future__ import print_function

from BX_math import BX_math as bxm
from BX_math import BX_offset
from BX_profile import BX_log

CHAIN_2_MULTI_CAP = "CHAIN_2_MULTI_CAP"
CHAIN_2_MULTI_GAP = "CHAIN_2_MULTI_GAP"
CHAIN_2_MULTI_ON_EDGE = "CHAIN_2_MULTI_ON_EDGE"

class BX_BoundaryVertex(object):
    """
    Boundary vertex around an original bevel vertex.

    This is a simplified BevelX version of Blender's BoundVert.

    For the current terminal-edge case:
        - one original vertex touched by one selected edge
        - one boundary point per adjacent face rail
    """
    def __init__(self,
                 boundary_id,
                 original_vertex_id,
                 selected_edge_id,
                 face_id,
                 co_world,
                 source="TERMINAL",
                 edge_before_id=None,
                 edge_after_id=None,
                 edge_on_id=None,
                 boundary_role=None):
        self.id = boundary_id

        self.original_vertex_id = int(original_vertex_id)
        self.selected_edge_id = int(selected_edge_id) if selected_edge_id is not None else None
        self.face_id = int(face_id) if face_id is not None else None

        self.co_world = list(co_world)

        self.source = source

        # Passive topology metadata.
        self.edge_before_id = edge_before_id
        self.edge_after_id = edge_after_id
        self.edge_on_id = edge_on_id
        self.boundary_role = boundary_role

        self.prev = None
        self.next = None

    def __repr__(self):
        prev_id = self.prev.id if self.prev else None
        next_id = self.next.id if self.next else None

        return (
            "BX_BoundaryVertex(id={0}, original_vertex={1}, "
            "edge={2}, face={3}, co={4}, prev={5}, next={6})"
        ).format(
            self.id,
            self.original_vertex_id,
            self.selected_edge_id,
            self.face_id,
            self.co_world,
            prev_id,
            next_id,
        )

def link_boundary_vertices_cyclic(boundary_vertices):
    """
    Link boundary vertices as a cyclic list.
    """

    count = len(boundary_vertices)

    if count == 0:
        return

    for i, boundary_vertex in enumerate(boundary_vertices):
        boundary_vertex.prev = boundary_vertices[(i - 1) % count]
        boundary_vertex.next = boundary_vertices[(i + 1) % count]


def debug_print_boundaries(vertex_boundaries):
    """
    Log boundary construction diagnostics.
    """
    if not BX_log.is_enabled("DEBUG", "boundary"):
        return
    total = sum(len(items) for items in vertex_boundaries.values())
    BX_log.debug("BoundaryVertex total: {0}".format(total),
        channel="boundary")

    for vertex_id in sorted(vertex_boundaries.keys()):
        boundary_list = vertex_boundaries[vertex_id]

        BX_log.debug("Boundary for BevelVertex {0}: count={1}".format(
                vertex_id,len(boundary_list)),channel="boundary")

        for i, boundary_vertex in enumerate(boundary_list):
            BX_log.trace("  boundary[{0}]: {1}".format(i, boundary_vertex),
                channel="boundary")

# -----------------------------------------------------------------------------
# Multi-edge boundary classification
# -----------------------------------------------------------------------------
def classify_bevel_vertices_topology(bm, bevel_vertices):
    """
    Classify bevel vertices using topology, not only selected edge count.

    Returns:
        {
            vertex_id: {
                "selected_count": int,
                "kind": str
            }
        }

    Kinds:
        TERMINAL
        CORNER_2
        CHAIN_2
        CORNER_3_PLUS
        NONE
    """

    result = {}

    for vertex_id, bevel_vertex in bevel_vertices.items():
        selected_count = bevel_vertex.selected_count

        if selected_count == 0:
            kind = "NONE"

        elif selected_count == 1:
            kind = "TERMINAL"

        elif selected_count == 2:
            if is_corner_2_vertex(bm, bevel_vertex):
                kind = "CORNER_2"
            elif is_chain_2_multi_vertex(bm, bevel_vertex):
                kind = "CHAIN_2_MULTI"
            else:
                kind = "CHAIN_2"

        elif selected_count == 3:
            kind = "CORNER_3_CAP"

        else:
            kind = "CORNER_3_PLUS"

        result[vertex_id] = {
            "selected_count": selected_count,
            "kind": kind,
        }

    return result


def debug_print_bevel_vertex_topology_classification(bm, bevel_vertices):
    """
    Log topology-aware boundary classification.
    """

    classification = classify_bevel_vertices_topology(bm=bm, bevel_vertices=bevel_vertices)

    if not BX_log.is_enabled("DEBUG", "boundary"):
        return classification

    BX_log.debug("Bevel vertex topology classification:",channel="boundary")

    for vertex_id in sorted(classification.keys()):
        data = classification[vertex_id]

        BX_log.debug("  Vertex {0}: kind={1}, selected_count={2}".format(
                vertex_id,data["kind"], data["selected_count"]),
                channel="boundary")

    return classification

def classify_bevel_vertices(bevel_vertices):
    """
    Classify bevel vertices by selected edge count.

    Returns:
        {
            vertex_id: {
                "selected_count": int,
                "kind": str
            }
        }

    Kinds:
        TERMINAL
            One selected edge enters this vertex.

        CORNER_2
            Two selected edges meet at this vertex.
            This needs sharp-corner / miter boundary logic.

        CORNER_3_PLUS
            Three or more selected edges meet.
            This will need VMesh/corner cap logic later.

        NONE
            Should normally not happen for affected bevel vertices.
    """

    result = {}

    for vertex_id, bevel_vertex in bevel_vertices.items():
        selected_count = bevel_vertex.selected_count

        if selected_count == 0:
            kind = "NONE"
        elif selected_count == 1:
            kind = "TERMINAL"
        elif selected_count == 2:
            kind = "CORNER_2"
        else:
            kind = "CORNER_3_PLUS"

        result[vertex_id] = {
            "selected_count": selected_count,
            "kind": kind,
        }

    return result


def debug_print_bevel_vertex_classification(bevel_vertices):
    """
    Log selected-edge count classification for each bevel vertex.
    """
    classification = classify_bevel_vertices(bevel_vertices)

    if not BX_log.is_enabled("DEBUG", "boundary"):
        return classification

    BX_log.debug("Bevel vertex boundary classification:",
        channel="boundary")

    for vertex_id in sorted(classification.keys()):
        data = classification[vertex_id]

        BX_log.debug("  Vertex {0}: kind={1}, selected_count={2}".format(
                vertex_id, data["kind"], data["selected_count"]),
            channel="boundary")

    return classification


def has_unsupported_multi_edge_vertices(bevel_vertices):
    """
    Return True if the current selected edge set requires unsupported
    boundary modes.

    selected_count == 3 is now routed to first M_TRI_CAP.
    """

    for vertex_id, bevel_vertex in bevel_vertices.items():
        if bevel_vertex.selected_count > 3:
            return True

    return False

def is_supported_simple_pole_n(bevel_vertex, vertex_boundaries):
    """
    Return True for the first supported POLE_N case.

    Supported now:
        - selected_count >= 4
        - every incident edge around the vertex is selected / beveled
        - build_pole_n_boundary_for_vertex() already produced a POLE_N ring
    """

    selected_count = getattr(bevel_vertex, "selected_count", 0)

    if selected_count < 4:
        return False

    if vertex_boundaries is None:
        return False

    edge_halves = list(getattr(bevel_vertex, "edge_halves", []))

    if not edge_halves:
        return False

    if selected_count != len(edge_halves):
        return False

    for edge_half in edge_halves:
        is_beveled = getattr(
            edge_half,
            "beveled",
            getattr(edge_half, "is_beveled", False)
        )

        if not is_beveled:
            return False

    vertex_id = getattr(bevel_vertex, "vertex_id", getattr(bevel_vertex, "id", None))

    if vertex_id is None:
        return False

    boundary_list = vertex_boundaries.get(vertex_id, [])

    pole_boundaries = [
        boundary_vertex
        for boundary_vertex in boundary_list
        if getattr(boundary_vertex, "source", None) == "POLE_N"
    ]

    return len(pole_boundaries) == selected_count


def get_unsupported_boundary_reason(bevel_vertices, vertex_boundaries=None):
    """
    Return a readable reason if the current selection contains unsupported
    boundary cases.

    Supported:
        TERMINAL
        CORNER_2
        CHAIN_2
        CORNER_3_CAP, first simple M_TRI_CAP version
        POLE_N, first simple all-incident-edges-selected version

    Still unsupported:
        selected_count > 3 when no supported POLE_N boundary ring exists
    """

    unsupported = []

    for vertex_id in sorted(bevel_vertices.keys()):
        bevel_vertex = bevel_vertices[vertex_id]
        selected_count = getattr(bevel_vertex, "selected_count", 0)

        if selected_count <= 3:
            continue

        if is_supported_simple_pole_n(
            bevel_vertex=bevel_vertex,
            vertex_boundaries=vertex_boundaries
        ):
            BX_log.debug("Boundary validation accepted POLE_N vertex {0}: selected_count={1}".format(
                vertex_id, selected_count), channel="boundary")
            continue

        unsupported.append(
            "vertex {0} has {1} selected edges; full VMesh/corner cap is not implemented yet".format(
                vertex_id,
                selected_count
            )
        )

    if not unsupported:
        return None

    return "; ".join(unsupported)


def requires_selection_transaction(bevel_vertices):
    """
    Return True when the current bevel cannot be represented as a simple
    one-edge terminal transaction.

    Multi-edge selections and CORNER_2 vertices need one shared
    selection-level transaction.
    """

    classification = classify_bevel_vertices(bevel_vertices)

    for vertex_id, data in classification.items():
        if data["kind"] == "CORNER_2":
            return True

        if data["kind"] == "CORNER_3_PLUS":
            return True

    return False

# -----------------------------------------------------------------------------
# CORNER_2 boundary preview
# -----------------------------------------------------------------------------
#temporary
def get_edge_ring_ids(bevel_vertex):
    """
    Return edge ids from bevel_vertex.edge_halves in cyclic order.
    """

    edge_ring = []

    for edge_half in list(getattr(bevel_vertex, "edge_halves", [])):
        edge_id = getattr(edge_half, "edge_id", None)

        if edge_id is not None:
            edge_ring.append(edge_id)

    return edge_ring


def cyclic_gap_between_edges(edge_ring, start_edge_id, end_edge_id):
    """
    Return edge ids encountered after start_edge_id until end_edge_id.

    The result is non-inclusive:
        ring = [112, 114, 172, 119, 146]
        start = 112
        end = 172

        result = [114]
    """

    if not edge_ring:
        return []

    if start_edge_id not in edge_ring:
        return []

    if end_edge_id not in edge_ring:
        return []

    count = len(edge_ring)
    start_index = edge_ring.index(start_edge_id)

    result = []
    cursor = (start_index + 1) % count

    safety = 0

    while edge_ring[cursor] != end_edge_id:
        result.append(edge_ring[cursor])

        cursor = (cursor + 1) % count
        safety += 1

        if safety > count:
            return []

    return result


def is_chain_2_multi_vertex(bm, bevel_vertex):
    """
    Return True only for selected_count == 2 high-valence pass-through vertices.

    Important:
        This must NOT catch CORNER_2 vertices.

    CHAIN_2_MULTI:
        - exactly two selected edges
        - selected edges do not share a face
        - cyclic ring has extra edges
        - both cyclic gaps between selected edges are non-empty

    CORNER_2 / high-valence CORNER_2:
        - exactly two selected edges
        - selected edges share a face
        - or one cyclic gap is empty
    """

    selected_edges = list(getattr(bevel_vertex, "selected_edges", []))
    edge_ring = get_edge_ring_ids(bevel_vertex)

    vertex_id = getattr(
        bevel_vertex,
        "vertex_id",
        getattr(bevel_vertex, "id", None)
    )

    if len(selected_edges) != 2:
        return False

    if len(edge_ring) <= 2:
        return False

    # Core safety check:
    # If the selected edges share a face, this is CORNER_2.
    common_faces = get_common_faces_between_selected_edges(bm=bm, selected_edge_ids=selected_edges)

    if common_faces:
        BX_log.warn(
            "CHAIN_2_MULTI gate rejected vertex {0}: selected edges share face(s) {1}; route to CORNER_2. selected={2}, ring={3}".format(
                vertex_id, common_faces, selected_edges, edge_ring), channel="summary")
        return False

    edge_a_id = selected_edges[0]
    edge_b_id = selected_edges[1]

    gap_ab = cyclic_gap_between_edges(
        edge_ring=edge_ring,
        start_edge_id=edge_a_id,
        end_edge_id=edge_b_id
    )

    gap_ba = cyclic_gap_between_edges(
        edge_ring=edge_ring,
        start_edge_id=edge_b_id,
        end_edge_id=edge_a_id
    )

    # If either side is empty, the selected edges are adjacent in the ring.
    # That is not pass-through CHAIN_2_MULTI.
    if not gap_ab or not gap_ba:
        BX_log.warn(
            "CHAIN_2_MULTI gate rejected vertex {0}: adjacent selected edges; route to CORNER_2/fallback. selected={1}, ring={2}, gap_ab={3}, gap_ba={4}".format(
                vertex_id, selected_edges, edge_ring, gap_ab, gap_ba), channel="summary")
        return False

    return True

def average_chain_2_multi_points(points):
    """
    Average a list of world-space points.
    """

    clean_points = [
        point
        for point in points
        if point is not None
    ]

    if not clean_points:
        return None

    result = [0.0, 0.0, 0.0]

    for point in clean_points:
        result = bxm.add(result, point)

    return bxm.div(result, float(len(clean_points)))

def solve_chain_2_multi_gap_point(boundary_list,
                                  bm,
                                  vertex_id,
                                  edge_start_id,
                                  edge_end_id,
                                  gap_edge_ids,
                                  gap_role):
    """
    Solve one shared CHAIN_2_MULTI gap/junction point.

    Blender-like intent:
        All non-selected edges between two selected edges attach to one
        BoundVert-style juncture.

    This is not a cap point.
    This is the shared boundary point for the whole gap sector.
    """

    if not gap_edge_ids:
        return None, None, None

    first_gap_edge_id = gap_edge_ids[0]
    last_gap_edge_id = gap_edge_ids[-1]

    face_start = get_face_between_ordered_edges(
        bm=bm,
        edge_a_id=edge_start_id,
        edge_b_id=first_gap_edge_id
    )

    face_end = get_face_between_ordered_edges(
        bm=bm,
        edge_a_id=last_gap_edge_id,
        edge_b_id=edge_end_id
    )

    start_anchor = find_existing_selected_boundary_for_gap_side(
        boundary_list=boundary_list,
        edge_id=edge_start_id,
        face_id=face_start
    )

    end_anchor = find_existing_selected_boundary_for_gap_side(
        boundary_list=boundary_list,
        edge_id=edge_end_id,
        face_id=face_end
    )

    if start_anchor is None or end_anchor is None:
        BX_log.warn(
            "CHAIN_2_MULTI gap solve skipped at vertex {0}, role={1}: missing anchors start={2}/{3}, end={4}/{5}".format(
                vertex_id,
                gap_role,
                edge_start_id,
                face_start,
                edge_end_id,
                face_end
            ),
            channel="summary"
        )
        return None, start_anchor, end_anchor

    vertex_point = bm.vertices[vertex_id].co_world

    width_start = bxm.distance(vertex_point, start_anchor.co_world)
    width_end = bxm.distance(vertex_point, end_anchor.co_world)
    width = 0.5 * (width_start + width_end)

    candidate_points = [
        start_anchor.co_world,
        end_anchor.co_world
    ]

    # Add slide probes on every middle edge. These are not separate final
    # boundary vertices. They only help locate the shared gap point.
    for middle_edge_id in gap_edge_ids:
        slide_point = slide_boundary_point_on_edge(
            bm=bm,
            vertex_id=vertex_id,
            edge_id=middle_edge_id,
            distance=width
        )

        if slide_point is not None:
            candidate_points.append(slide_point)

    # If exactly one middle edge exists, add Blender-style offset_on_edge_between
    # as one more candidate. But it is still averaged into the single gap point.
    if len(gap_edge_ids) == 1:
        middle_edge_id = gap_edge_ids[0]

        edge_start_other = get_other_vertex_point_on_edge(
            bm=bm,
            edge_id=edge_start_id,
            vertex_id=vertex_id
        )

        middle_other = get_other_vertex_point_on_edge(
            bm=bm,
            edge_id=middle_edge_id,
            vertex_id=vertex_id
        )

        edge_end_other = get_other_vertex_point_on_edge(
            bm=bm,
            edge_id=edge_end_id,
            vertex_id=vertex_id
        )

        vertex_normal = average_terminal_multi_vertex_normal(
            bm=bm,
            vertex_id=vertex_id
        )

        solve = BX_offset.offset_on_edge_between(
            vertex_position=vertex_point,
            edge_a_other_position=edge_start_other,
            middle_edge_other_position=middle_other,
            edge_b_other_position=edge_end_other,
            offset_a_right=width_start,
            offset_b_left=width_end,
            vertex_normal=vertex_normal
        )

        solve_point = solve.get("point")

        if solve_point is not None and middle_other is not None:
            solve_point = bxm.closest_point_on_segment(
                solve_point,
                vertex_point,
                middle_other
            )

            candidate_points.append(solve_point)

    gap_point = average_chain_2_multi_points(candidate_points)

    BX_log.warn(
        "CHAIN_2_MULTI gap solved at vertex {0}, role={1}: start={2}, middles={3}, end={4}, point={5}, candidates={6}".format(
            vertex_id,
            gap_role,
            getattr(start_anchor, "id", None),
            gap_edge_ids,
            getattr(end_anchor, "id", None),
            gap_point,
            len(candidate_points)
        ),
        channel="summary"
    )

    return gap_point, start_anchor, end_anchor

def build_chain_2_multi_gap_alias_boundaries(boundary_list,
                                             bm,
                                             vertex_id,
                                             edge_start_id,
                                             edge_end_id,
                                             gap_edge_ids,
                                             gap_role):
    """
    Build aliases for one CHAIN_2_MULTI gap.

    Critical rule:
        Every alias in this gap shares the same boundary_id.

    That means:
        - selected edge side A
        - selected edge side B
        - all intermediate non-selected edges

    all become the same transaction vertex, like one Blender BoundVert.
    """

    if not gap_edge_ids:
        return []

    gap_point, start_anchor, end_anchor = solve_chain_2_multi_gap_point(
        boundary_list=boundary_list,
        bm=bm,
        vertex_id=vertex_id,
        edge_start_id=edge_start_id,
        edge_end_id=edge_end_id,
        gap_edge_ids=gap_edge_ids,
        gap_role=gap_role
    )

    if gap_point is None or start_anchor is None or end_anchor is None:
        return []

    gap_boundary_id = "BV{0}_CHAIN2_MULTI_GAP_{1}".format(
        vertex_id,
        gap_role
    )

    aliases = []

    # Selected start side alias.
    aliases.append(
        BX_BoundaryVertex(
            boundary_id=gap_boundary_id,
            original_vertex_id=vertex_id,
            selected_edge_id=edge_start_id,
            face_id=start_anchor.face_id,
            co_world=gap_point,
            source=CHAIN_2_MULTI_GAP,
            edge_before_id=edge_start_id,
            edge_after_id=gap_edge_ids[0],
            edge_on_id=edge_start_id,
            boundary_role=gap_role
        )
    )

    # Middle non-selected edges. Same id. Same point.
    for middle_edge_id in gap_edge_ids:
        aliases.append(
            BX_BoundaryVertex(
                boundary_id=gap_boundary_id,
                original_vertex_id=vertex_id,
                selected_edge_id=None,
                face_id=None,
                co_world=gap_point,
                source=CHAIN_2_MULTI_GAP,
                edge_before_id=edge_start_id,
                edge_after_id=edge_end_id,
                edge_on_id=middle_edge_id,
                boundary_role=gap_role
            )
        )

    # Selected end side alias.
    aliases.append(
        BX_BoundaryVertex(
            boundary_id=gap_boundary_id,
            original_vertex_id=vertex_id,
            selected_edge_id=edge_end_id,
            face_id=end_anchor.face_id,
            co_world=gap_point,
            source=CHAIN_2_MULTI_GAP,
            edge_before_id=gap_edge_ids[-1],
            edge_after_id=edge_end_id,
            edge_on_id=edge_end_id,
            boundary_role=gap_role
        )
    )

    BX_log.warn(
        "CHAIN_2_MULTI gap aliases built at vertex {0}, role={1}: id={2}, aliases={3}, edges={4}".format(
            vertex_id,
            gap_role,
            gap_boundary_id,
            len(aliases),
            [edge_start_id] + list(gap_edge_ids) + [edge_end_id]
        ),
        channel="summary"
    )

    return aliases


def debug_chain_2_multi_vertex(bm, bevel_vertex):
    """
    Log the cyclic gaps for a CHAIN_2_MULTI candidate.

    This is diagnostic only. It should not alter boundary construction.
    """

    if not is_chain_2_multi_vertex(
        bm=bm,
        bevel_vertex=bevel_vertex
    ):
        return

    vertex_id = getattr(
        bevel_vertex,
        "vertex_id",
        getattr(bevel_vertex, "id", None)
    )

    selected_edges = list(getattr(bevel_vertex, "selected_edges", []))
    edge_ring = get_edge_ring_ids(bevel_vertex)

    edge_a_id = selected_edges[0]
    edge_b_id = selected_edges[1]

    gap_ab = cyclic_gap_between_edges(
        edge_ring=edge_ring,
        start_edge_id=edge_a_id,
        end_edge_id=edge_b_id
    )

    gap_ba = cyclic_gap_between_edges(
        edge_ring=edge_ring,
        start_edge_id=edge_b_id,
        end_edge_id=edge_a_id
    )

    BX_log.warn(
        "CHAIN_2_MULTI candidate vertex {0}: selected={1}, ring={2}, gap_ab={3}, gap_ba={4}".format(
            vertex_id,
            selected_edges,
            edge_ring,
            gap_ab,
            gap_ba
        ),
        channel="summary"
    )

def boundary_points_are_close(point_a, point_b, epsilon=1.0e-6):
    return bxm.distance(point_a, point_b) <= epsilon


def collapse_boundary_vertices_by_position(boundary_vertices,
                                            epsilon=1.0e-6):
    """
    Collapse duplicate boundary vertices before they become transaction vertices.
    Preserve order.
    """

    result = []

    for boundary_vertex in boundary_vertices:
        duplicate = False

        for existing in result:
            if boundary_points_are_close(
                boundary_vertex.co_world,
                existing.co_world,
                epsilon=epsilon
            ):
                duplicate = True
                break

        if not duplicate:
            result.append(boundary_vertex)

    return result

def build_chain_2_multi_boundary_for_vertex(bm,
                                            bevel_vertex,
                                            edge_data_by_id,
                                            rails_by_edge_id):
    """
    CHAIN_2_MULTI high-valence selected_count == 2 vertex.

    Blender-like stage:
        - build fallback only as raw anchor input
        - collapse each cyclic gap into one BoundVert-style point
        - return aliases that make selected-edge strips and F_RECON share
          the same gap vertices
        - do not build caps yet
    """

    debug_chain_2_multi_vertex(
        bm=bm,
        bevel_vertex=bevel_vertex
    )

    vertex_id = bevel_vertex.vertex_id
    selected_edges = list(getattr(bevel_vertex, "selected_edges", []))
    edge_ring = get_edge_ring_ids(bevel_vertex)

    fallback_boundaries = build_selected_count_2_fallback_boundary_for_vertex(
        bm=bm,
        bevel_vertex=bevel_vertex,
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id
    )

    if fallback_boundaries is None:
        fallback_boundaries = []

    debug_chain_2_multi_probe_points(
        boundary_list=fallback_boundaries,
        bm=bm,
        bevel_vertex=bevel_vertex,
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id
    )

    if len(selected_edges) != 2:
        return fallback_boundaries

    if len(edge_ring) <= 2:
        return fallback_boundaries

    edge_a_id = selected_edges[0]
    edge_b_id = selected_edges[1]

    gap_ab = cyclic_gap_between_edges(
        edge_ring=edge_ring,
        start_edge_id=edge_a_id,
        end_edge_id=edge_b_id
    )

    gap_ba = cyclic_gap_between_edges(
        edge_ring=edge_ring,
        start_edge_id=edge_b_id,
        end_edge_id=edge_a_id
    )

    boundary_list = []

    boundary_list.extend(
        build_chain_2_multi_gap_alias_boundaries(
            boundary_list=fallback_boundaries,
            bm=bm,
            vertex_id=vertex_id,
            edge_start_id=edge_a_id,
            edge_end_id=edge_b_id,
            gap_edge_ids=gap_ab,
            gap_role="AB"
        )
    )

    boundary_list.extend(
        build_chain_2_multi_gap_alias_boundaries(
            boundary_list=fallback_boundaries,
            bm=bm,
            vertex_id=vertex_id,
            edge_start_id=edge_b_id,
            edge_end_id=edge_a_id,
            gap_edge_ids=gap_ba,
            gap_role="BA"
        )
    )

    if not boundary_list:
        BX_log.warn(
            "CHAIN_2_MULTI gap aliases empty at vertex {0}; falling back to old selected boundaries.".format(
                vertex_id
            ),
            channel="summary"
        )
        return fallback_boundaries

    link_boundary_vertices_cyclic(boundary_list)

    BX_log.warn(
        "CHAIN_2_MULTI boundary built for vertex {0}: gap_aliases={1}, total={2}".format(
            vertex_id,
            len(boundary_list),
            len(boundary_list)
        ),
        channel="summary"
    )

    return boundary_list

def build_chain_2_multi_single_gap_cap_boundaries(boundary_list,
                                                  bm,
                                                  vertex_id,
                                                  edge_start_id,
                                                  edge_end_id,
                                                  gap_edge_ids,
                                                  gap_role):
    """
    Build CHAIN_2_MULTI cap boundaries only for a single-middle-edge gap.

    For:
        selected_start -> middle_edge -> selected_end

    Build triangle:
        existing start boundary alias
        solved middle point on middle_edge
        existing end boundary alias

    Multi-edge gaps are intentionally skipped because support reconstruction
    already handles those sectors.
    """

    if not gap_edge_ids:
        BX_log.warn(
            "CHAIN_2_MULTI cap skipped at vertex {0}, role={1}: adjacent selected edges.".format(
                vertex_id,
                gap_role
            ),
            channel="summary"
        )
        return []

    if len(gap_edge_ids) != 1:
        BX_log.warn(
            "CHAIN_2_MULTI cap skipped at vertex {0}, role={1}: multi-edge gap handled by support reconstruction, gap={2}".format(
                vertex_id,
                gap_role,
                gap_edge_ids
            ),
            channel="summary"
        )
        return []

    middle_edge_id = gap_edge_ids[0]

    face_start = get_face_between_ordered_edges(
        bm=bm,edge_a_id=edge_start_id,edge_b_id=middle_edge_id)
    face_end = get_face_between_ordered_edges(
        bm=bm,edge_a_id=middle_edge_id,edge_b_id=edge_end_id)
    start_anchor = find_existing_selected_boundary_for_gap_side(
        boundary_list=boundary_list,edge_id=edge_start_id,face_id=face_start)
    end_anchor = find_existing_selected_boundary_for_gap_side(
        boundary_list=boundary_list,edge_id=edge_end_id,face_id=face_end)

    if start_anchor is None or end_anchor is None:
        BX_log.warn(
            "CHAIN_2_MULTI single-gap cap skipped at vertex {0}, role={1}: missing anchors. start_edge={2}, face_start={3}, end_edge={4}, face_end={5}, start_anchor={6}, end_anchor={7}".format(
                vertex_id,
                gap_role,
                edge_start_id,
                face_start,
                edge_end_id,
                face_end,
                getattr(start_anchor, "id", None),
                getattr(end_anchor, "id", None)
            ),
            channel="summary"
        )
        return []

    vertex_point = bm.vertices[vertex_id].co_world

    width_start = bxm.distance(vertex_point,start_anchor.co_world)
    width_end = bxm.distance(vertex_point,end_anchor.co_world)

    edge_start_other = get_other_vertex_point_on_edge(
        bm=bm,
        edge_id=edge_start_id,
        vertex_id=vertex_id
    )

    middle_other = get_other_vertex_point_on_edge(
        bm=bm,
        edge_id=middle_edge_id,
        vertex_id=vertex_id
    )

    edge_end_other = get_other_vertex_point_on_edge(
        bm=bm,
        edge_id=edge_end_id,
        vertex_id=vertex_id
    )

    vertex_normal = average_terminal_multi_vertex_normal(
        bm=bm,
        vertex_id=vertex_id
    )

    solve = BX_offset.offset_on_edge_between(
        vertex_position=vertex_point,
        edge_a_other_position=edge_start_other,
        middle_edge_other_position=middle_other,
        edge_b_other_position=edge_end_other,
        offset_a_right=width_start,
        offset_b_left=width_end,
        vertex_normal=vertex_normal
    )

    solve_point = solve.get("point")

    if solve_point is not None:
        solve_point = bxm.closest_point_on_segment(
            solve_point,
            vertex_point,
            middle_other
        )

    slide_point = slide_boundary_point_on_edge(
        bm=bm,
        vertex_id=vertex_id,
        edge_id=middle_edge_id,
        distance=0.5 * (width_start + width_end)
    )

    middle_point = choose_chain_2_multi_middle_point(
        vertex_point=vertex_point,
        start_point=start_anchor.co_world,
        end_point=end_anchor.co_world,
        solve_point=solve_point,
        slide_point=slide_point,
        width=0.5 * (width_start + width_end),
        vertex_id=vertex_id,
        gap_role=gap_role,
        middle_edge_id=middle_edge_id
    )

    if middle_point is None:
        return []

    cap_boundaries = []

    start_alias = make_chain_2_multi_cap_alias(
        source_boundary=start_anchor,
        boundary_role=gap_role
    )

    if start_alias is not None:
        cap_boundaries.append(start_alias)

    middle_boundary = make_chain_2_multi_middle_boundary(
        vertex_id=vertex_id,
        selected_edge_id=edge_start_id,
        edge_before_id=edge_start_id,
        edge_after_id=edge_end_id,
        edge_on_id=middle_edge_id,
        point=middle_point,
        boundary_role=gap_role,
        label="MID"
    )

    if middle_boundary is not None:
        cap_boundaries.append(middle_boundary)

    end_alias = make_chain_2_multi_cap_alias(
        source_boundary=end_anchor,
        boundary_role=gap_role
    )

    if end_alias is not None:
        cap_boundaries.append(end_alias)

    cap_boundaries = collapse_boundary_vertices_by_position(
        cap_boundaries
    )

    if len(cap_boundaries) < 3:
        BX_log.warn(
            "CHAIN_2_MULTI single-gap cap skipped at vertex {0}, role={1}: only {2} unique points.".format(
                vertex_id,
                gap_role,
                len(cap_boundaries)
            ),
            channel="summary"
        )
        return []

    BX_log.warn(
        "CHAIN_2_MULTI single-gap cap built at vertex {0}, role={1}: start={2}, middle={3}, end={4}, source={5}, count={6}".format(
            vertex_id,
            gap_role,
            getattr(start_anchor, "id", None),
            middle_edge_id,
            getattr(end_anchor, "id", None),
            solve.get("source", "offset_on_edge_between"),
            len(cap_boundaries)
        ),
        channel="summary"
    )

    return cap_boundaries

def debug_chain_2_multi_probe_points(boundary_list,
                                     bm,
                                     bevel_vertex,
                                     edge_data_by_id,
                                     rails_by_edge_id):
    """
    Probe CHAIN_2_MULTI cap/middle points without adding any geometry.

    Blender-like debugging sequence:
        - inspect selected-edge anchors
        - inspect gap layout
        - compute candidate middle points
        - do not add cap boundaries yet
    """

    vertex_id = bevel_vertex.vertex_id
    selected_edges = list(getattr(bevel_vertex, "selected_edges", []))
    edge_ring = get_edge_ring_ids(bevel_vertex)

    if len(selected_edges) != 2:
        return

    if len(edge_ring) <= 2:
        return

    edge_a_id = selected_edges[0]
    edge_b_id = selected_edges[1]

    gap_ab = cyclic_gap_between_edges(
        edge_ring=edge_ring,
        start_edge_id=edge_a_id,
        end_edge_id=edge_b_id
    )

    gap_ba = cyclic_gap_between_edges(
        edge_ring=edge_ring,
        start_edge_id=edge_b_id,
        end_edge_id=edge_a_id
    )

    debug_chain_2_multi_probe_gap(
        boundary_list=boundary_list,
        bm=bm,
        vertex_id=vertex_id,
        edge_start_id=edge_a_id,
        edge_end_id=edge_b_id,
        gap_edge_ids=gap_ab,
        gap_label="AB"
    )

    debug_chain_2_multi_probe_gap(
        boundary_list=boundary_list,
        bm=bm,
        vertex_id=vertex_id,
        edge_start_id=edge_b_id,
        edge_end_id=edge_a_id,
        gap_edge_ids=gap_ba,
        gap_label="BA"
    )

def debug_chain_2_multi_probe_gap(boundary_list,
                                  bm,
                                  vertex_id,
                                  edge_start_id,
                                  edge_end_id,
                                  gap_edge_ids,
                                  gap_label):
    """
    Probe one cyclic gap.

    No boundary vertices are created here.
    """

    if not gap_edge_ids:
        BX_log.warn(
            "CHAIN_2_MULTI probe vertex {0}, gap={1}: adjacent selected edges, no middle gap.".format(
                vertex_id,
                gap_label
            ),
            channel="summary"
        )
        return

    first_gap_edge_id = gap_edge_ids[0]
    last_gap_edge_id = gap_edge_ids[-1]

    face_start = get_face_between_ordered_edges(
        bm=bm,
        edge_a_id=edge_start_id,
        edge_b_id=first_gap_edge_id
    )

    face_end = get_face_between_ordered_edges(
        bm=bm,
        edge_a_id=last_gap_edge_id,
        edge_b_id=edge_end_id
    )

    start_anchor = find_existing_selected_boundary_for_gap_side(
        boundary_list=boundary_list,
        edge_id=edge_start_id,
        face_id=face_start
    )

    end_anchor = find_existing_selected_boundary_for_gap_side(
        boundary_list=boundary_list,
        edge_id=edge_end_id,
        face_id=face_end
    )

    BX_log.warn(
        "CHAIN_2_MULTI probe vertex {0}, gap={1}: start_edge={2}, end_edge={3}, middles={4}, face_start={5}, face_end={6}, start_anchor={7}, end_anchor={8}".format(
            vertex_id,
            gap_label,
            edge_start_id,
            edge_end_id,
            gap_edge_ids,
            face_start,
            face_end,
            getattr(start_anchor, "id", None),
            getattr(end_anchor, "id", None)
        ),
        channel="summary"
    )

    if start_anchor is None or end_anchor is None:
        return

    vertex_point = bm.vertices[vertex_id].co_world

    width_start = bxm.distance(vertex_point, start_anchor.co_world)
    width_end = bxm.distance(vertex_point, end_anchor.co_world)
    width = 0.5 * (width_start + width_end)

    BX_log.warn(
        "CHAIN_2_MULTI probe vertex {0}, gap={1}: width_start={2}, width_end={3}, width_avg={4}".format(
            vertex_id,
            gap_label,
            width_start,
            width_end,
            width
        ),
        channel="summary"
    )

    # One middle edge: use offset_on_edge_between probe.
    if len(gap_edge_ids) == 1:
        middle_edge_id = gap_edge_ids[0]

        edge_start_other = get_other_vertex_point_on_edge(
            bm=bm,
            edge_id=edge_start_id,
            vertex_id=vertex_id
        )

        middle_other = get_other_vertex_point_on_edge(
            bm=bm,
            edge_id=middle_edge_id,
            vertex_id=vertex_id
        )

        edge_end_other = get_other_vertex_point_on_edge(
            bm=bm,
            edge_id=edge_end_id,
            vertex_id=vertex_id
        )

        vertex_normal = average_terminal_multi_vertex_normal(
            bm=bm,
            vertex_id=vertex_id
        )

        solve = BX_offset.offset_on_edge_between(
            vertex_position=vertex_point,
            edge_a_other_position=edge_start_other,
            middle_edge_other_position=middle_other,
            edge_b_other_position=edge_end_other,
            offset_a_right=width_start,
            offset_b_left=width_end,
            vertex_normal=vertex_normal
        )

        middle_point = solve.get("point")

        if middle_point is not None:
            middle_point = bxm.closest_point_on_segment(
                middle_point,
                vertex_point,
                middle_other
            )

        BX_log.warn(
            "CHAIN_2_MULTI probe vertex {0}, gap={1}: single_middle edge={2}, source={3}, point={4}".format(
                vertex_id,
                gap_label,
                middle_edge_id,
                solve.get("source", "offset_on_edge_between"),
                middle_point
            ),
            channel="summary"
        )

        return

    # Multiple middle edges: for now only print slide probes.
    for middle_edge_id in gap_edge_ids:
        middle_point = slide_boundary_point_on_edge(
            bm=bm,
            vertex_id=vertex_id,
            edge_id=middle_edge_id,
            distance=width
        )

        BX_log.warn(
            "CHAIN_2_MULTI probe vertex {0}, gap={1}: multi_middle edge={2}, slide_point={3}".format(
                vertex_id,
                gap_label,
                middle_edge_id,
                middle_point
            ),
            channel="summary"
        )

def find_existing_selected_boundary_for_gap_side(boundary_list,
                                                 edge_id,
                                                 face_id):
    """
    Find an existing selected-edge boundary for edge_id on face_id.

    This is used by CHAIN_2_MULTI probes/caps to reuse the same
    boundary anchor that the bevel strip already uses.

    Important:
        Do not create a new selected-side point here.
        We want the cap endpoint to share the existing boundary id.
    """

    for boundary_vertex in boundary_list:
        if getattr(boundary_vertex, "selected_edge_id", None) != edge_id:
            continue

        if getattr(boundary_vertex, "face_id", None) != face_id:
            continue

        return boundary_vertex

    return None

def make_chain_2_multi_cap_alias(source_boundary,
                                 boundary_role):
    """
    Make a cap-only alias of an existing selected boundary.

    Critical:
        Reuse source_boundary.id.

    Because BX_BevelTransaction.add_boundary_vertex() deduplicates by
    boundary_id, this makes the cap share the same transaction vertex as
    the bevel strip / fallback boundary.
    """

    if source_boundary is None:
        return None

    return BX_BoundaryVertex(
        boundary_id=source_boundary.id,
        original_vertex_id=source_boundary.original_vertex_id,
        selected_edge_id=source_boundary.selected_edge_id,
        face_id=source_boundary.face_id,
        co_world=source_boundary.co_world,
        source=CHAIN_2_MULTI_CAP,
        edge_before_id=getattr(source_boundary, "edge_before_id", None),
        edge_after_id=getattr(source_boundary, "edge_after_id", None),
        edge_on_id=getattr(source_boundary, "edge_on_id", None),
        boundary_role=boundary_role
    )

def make_chain_2_multi_middle_boundary(vertex_id,
                                       selected_edge_id,
                                       edge_before_id,
                                       edge_after_id,
                                       edge_on_id,
                                       point,
                                       boundary_role,
                                       label):
    """
    Create a new middle/on-edge cap boundary for CHAIN_2_MULTI.

    This is the only new point in the single-middle-edge cap.
    """

    if point is None:
        return None

    return BX_BoundaryVertex(
        boundary_id="BV{0}_CHAIN2_MULTI_{1}_{2}_E{3}".format(
            vertex_id,
            boundary_role,
            label,
            edge_on_id
        ),
        original_vertex_id=vertex_id,
        selected_edge_id=selected_edge_id,
        face_id=None,
        co_world=point,
        source=CHAIN_2_MULTI_CAP,
        edge_before_id=edge_before_id,
        edge_after_id=edge_after_id,
        edge_on_id=edge_on_id,
        boundary_role=boundary_role
    )

def build_chain_2_multi_on_edge_boundaries(bm,
                                           bevel_vertex,
                                           boundary_list):
    """
    Build ON_EDGE boundary points for every non-selected incident edge
    around a selected_count == 2 high-valence vertex.

    These are not caps.

    They are face-reconstruction anchors:
        face sector prev_edge -> vertex -> next_edge
        becomes:
        point on prev_edge -> point on next_edge
    """

    vertex_id = bevel_vertex.vertex_id
    selected_edges = set(getattr(bevel_vertex, "selected_edges", []))
    edge_halves = list(getattr(bevel_vertex, "edge_halves", []))

    if not edge_halves:
        return []

    vertex_point = bm.vertices[vertex_id].co_world

    widths = []

    for boundary_vertex in boundary_list:
        if getattr(boundary_vertex, "original_vertex_id", None) != vertex_id:
            continue

        if getattr(boundary_vertex, "selected_edge_id", None) not in selected_edges:
            continue

        if getattr(boundary_vertex, "face_id", None) is None:
            continue

        widths.append(
            bxm.distance(
                vertex_point,
                boundary_vertex.co_world
            )
        )

    if widths:
        width = sum(widths) / float(len(widths))
    else:
        width = 0.0

    on_edge_boundaries = []

    count = len(edge_halves)

    for i, edge_half in enumerate(edge_halves):
        edge_id = edge_half.edge_id

        if edge_id in selected_edges:
            continue

        point = slide_boundary_point_on_edge(
            bm=bm,
            vertex_id=vertex_id,
            edge_id=edge_id,
            distance=width
        )

        if point is None:
            continue

        prev_edge_id = edge_halves[(i - 1) % count].edge_id
        next_edge_id = edge_halves[(i + 1) % count].edge_id

        boundary_vertex = BX_BoundaryVertex(
            boundary_id="BV{0}_CHAIN2_MULTI_ON_E{1}".format(
                vertex_id,
                edge_id
            ),
            original_vertex_id=vertex_id,
            selected_edge_id=None,
            face_id=None,
            co_world=point,
            source=CHAIN_2_MULTI_ON_EDGE,
            edge_before_id=prev_edge_id,
            edge_after_id=next_edge_id,
            edge_on_id=edge_id,
            boundary_role="ON_EDGE"
        )

        on_edge_boundaries.append(boundary_vertex)

    BX_log.warn(
        "CHAIN_2_MULTI ON_EDGE boundaries built for vertex {0}: edges={1}, count={2}".format(
            vertex_id,
            [
                getattr(boundary_vertex, "edge_on_id", None)
                for boundary_vertex in on_edge_boundaries
            ],
            len(on_edge_boundaries)
        ),
        channel="summary"
    )

    return on_edge_boundaries

def choose_chain_2_multi_middle_point(vertex_point,
                                      start_point,
                                      end_point,
                                      solve_point,
                                      slide_point,
                                      width,
                                      vertex_id,
                                      gap_role,
                                      middle_edge_id):
    """
    Choose a usable middle point for a CHAIN_2_MULTI single-gap cap.

    The offset solve can return a point extremely close to one cap anchor.
    That creates a skinny/degenerate triangle that looks like a flipped or
    unmerged face.

    Prefer the offset solve only if it forms a real triangle.
    Otherwise use the slide point.
    Otherwise skip.
    """

    min_anchor_distance = max(1.0e-5, width * 0.20)

    candidates = []

    if solve_point is not None:
        candidates.append(("offset_on_edge_between", solve_point))

    if slide_point is not None:
        candidates.append(("slide_distance_on_edge", slide_point))

    best_name = None
    best_point = None
    best_score = -1.0

    for name, point in candidates:
        distance_to_start = bxm.distance(point, start_point)
        distance_to_end = bxm.distance(point, end_point)
        distance_to_vertex = bxm.distance(point, vertex_point)

        BX_log.warn(
            "CHAIN_2_MULTI middle candidate vertex {0}, role={1}, edge={2}: source={3}, d_start={4}, d_end={5}, d_vertex={6}, point={7}".format(
                vertex_id,
                gap_role,
                middle_edge_id,
                name,
                distance_to_start,
                distance_to_end,
                distance_to_vertex,
                point
            ),
            channel="summary"
        )

        if distance_to_start < min_anchor_distance:
            continue

        if distance_to_end < min_anchor_distance:
            continue

        score = min(distance_to_start, distance_to_end)

        if score > best_score:
            best_score = score
            best_name = name
            best_point = point

    if best_point is None:
        BX_log.warn(
            "CHAIN_2_MULTI middle rejected at vertex {0}, role={1}, edge={2}: no candidate produced a stable triangle.".format(
                vertex_id,
                gap_role,
                middle_edge_id
            ),
            channel="summary"
        )
        return None

    BX_log.warn(
        "CHAIN_2_MULTI middle selected at vertex {0}, role={1}, edge={2}: source={3}, point={4}".format(
            vertex_id,
            gap_role,
            middle_edge_id,
            best_name,
            best_point
        ),
        channel="summary"
    )

    return best_point

#temporary
def build_selected_count_2_fallback_boundary_for_vertex(bm,
                                                        bevel_vertex,
                                                        edge_data_by_id,
                                                        rails_by_edge_id):
    """
    Existing selected_count == 2 behavior.

    Used as the fallback while CHAIN_2_MULTI is only diagnostic.
    """

    if is_corner_2_vertex(bm, bevel_vertex):
        return build_corner_2_boundary_for_vertex(
            bm=bm,
            bevel_vertex=bevel_vertex,
            edge_data_by_id=edge_data_by_id,
            rails_by_edge_id=rails_by_edge_id
        )

    return build_chain_2_boundary_for_vertex(
        bm=bm,
        bevel_vertex=bevel_vertex,
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id
    )


def build_boundaries_for_selection(bm, edges_data, rails_by_edge_id, bevel_vertices):
    """
    Build boundary vertices for the current selected edge set.

    Current support:
        - TERMINAL vertices
        - CORNER_2 vertices, preview/debug only

    Returns:
        {
            vertex_id: [BX_BoundaryVertex, ...]
        }
    """

    vertex_boundaries = {}

    edge_data_by_id = {
        edge_data["edge_id"]: edge_data
        for edge_data in edges_data
    }

    for vertex_id, bevel_vertex in bevel_vertices.items():
        if bevel_vertex.selected_count == 1:
            selected_edge_id = bevel_vertex.selected_edges[0]

            if should_use_terminal_multi_boundary(
                bm=bm,
                bevel_vertex=bevel_vertex,
                edges_data=edges_data
            ):
                boundary_list = build_terminal_multi_edge_boundary_for_vertex(
                    bm=bm,
                    bevel_vertex=bevel_vertex,
                    edge_data_by_id=edge_data_by_id,
                    rails_by_edge_id=rails_by_edge_id
                )

                if not boundary_list:
                    BX_log.warn(
                        "TERMINAL_MULTI returned empty at vertex {0}. Falling back to TERMINAL.".format(
                            vertex_id
                        ),
                        channel="summary"
                    )

                    edge_data = edge_data_by_id[selected_edge_id]
                    rails = rails_by_edge_id[selected_edge_id]

                    boundary_list = build_terminal_boundary_for_vertex(
                        edge_data=edge_data,
                        rails=rails,
                        vertex_id=vertex_id
                    )

            else:
                edge_data = edge_data_by_id[selected_edge_id]
                rails = rails_by_edge_id[selected_edge_id]

                boundary_list = build_terminal_boundary_for_vertex(
                    edge_data=edge_data,
                    rails=rails,
                    vertex_id=vertex_id
                )

            vertex_boundaries[vertex_id] = boundary_list

        elif bevel_vertex.selected_count == 2:
            # ------------------------------------------------------------
            # CORNER_2 must be checked before CHAIN_2_MULTI.
            #
            # High-valence adjacent selected edges are still CORNER_2.
            # CHAIN_2_MULTI is only for pass-through cases where selected
            # edges are separated on both sides by non-selected gaps.
            # ------------------------------------------------------------
            if is_corner_2_vertex(
                bm=bm,
                bevel_vertex=bevel_vertex
            ):
                boundary_list = build_corner_2_boundary_for_vertex(
                    bm=bm,
                    bevel_vertex=bevel_vertex,
                    edge_data_by_id=edge_data_by_id,
                    rails_by_edge_id=rails_by_edge_id
                )

            elif is_chain_2_multi_vertex(
                bm=bm,
                bevel_vertex=bevel_vertex
            ):
                boundary_list = build_chain_2_multi_boundary_for_vertex(
                    bm=bm,
                    bevel_vertex=bevel_vertex,
                    edge_data_by_id=edge_data_by_id,
                    rails_by_edge_id=rails_by_edge_id
                )

                if not boundary_list:
                    BX_log.warn(
                        "CHAIN_2_MULTI returned empty at vertex {0}; falling back.".format(
                            vertex_id
                        ),
                        channel="summary"
                    )

                    boundary_list = build_selected_count_2_fallback_boundary_for_vertex(
                        bm=bm,
                        bevel_vertex=bevel_vertex,
                        edge_data_by_id=edge_data_by_id,
                        rails_by_edge_id=rails_by_edge_id
                    )

            else:
                boundary_list = build_selected_count_2_fallback_boundary_for_vertex(
                    bm=bm,
                    bevel_vertex=bevel_vertex,
                    edge_data_by_id=edge_data_by_id,
                    rails_by_edge_id=rails_by_edge_id
                )

            vertex_boundaries[vertex_id] = boundary_list

        elif bevel_vertex.selected_count == 3:
            from BX_boundary import BX_vmesh

            boundary_list = BX_vmesh.build_corner_3_tri_cap_boundary_for_vertex(
                bm=bm,
                bevel_vertex=bevel_vertex,
                edge_data_by_id=edge_data_by_id,
                rails_by_edge_id=rails_by_edge_id,
                boundary_class=BX_BoundaryVertex,
                link_function=link_boundary_vertices_cyclic
            )

            vertex_boundaries[vertex_id] = boundary_list

        # In BX_boundary.py, inside build_boundaries_for_selection(), replace the final
        # unsupported else branch with this selected_count >= 4 branch plus fallback.
        elif bevel_vertex.selected_count >= 4:
            from BX_boundary import BX_vmesh

            boundary_list = BX_vmesh.build_pole_n_boundary_for_vertex(
                bm=bm,
                bevel_vertex=bevel_vertex,
                edge_data_by_id=edge_data_by_id,
                rails_by_edge_id=rails_by_edge_id,
                boundary_class=BX_BoundaryVertex,
                link_function=link_boundary_vertices_cyclic
            )

            vertex_boundaries[vertex_id] = boundary_list

        else:
            vertex_boundaries[vertex_id] = []

    return vertex_boundaries


def build_terminal_boundary_for_vertex(edge_data, rails, vertex_id):
    """
    Build terminal boundary vertices for only one endpoint of one selected edge.
    """

    edge_id = edge_data["edge_id"]
    edge_v0, edge_v1 = edge_data["vertex_ids"]

    if vertex_id not in (edge_v0, edge_v1):
        return []

    boundary_list = []

    for rail_data in rails:
        face_id = rail_data["face_id"]
        rail_p0, rail_p1 = rail_data["rail"]

        if vertex_id == edge_v0:
            point = rail_p0
        else:
            point = rail_p1

        boundary_vertex = BX_BoundaryVertex(
            boundary_id="BV{0}_E{1}_F{2}".format(vertex_id, edge_id, face_id),
            original_vertex_id=vertex_id,
            selected_edge_id=edge_id,
            face_id=face_id,
            co_world=point,
            source="TERMINAL"
        )

        boundary_list.append(boundary_vertex)

    link_boundary_vertices_cyclic(boundary_list)

    return boundary_list

# -----------------------------------------------------------------------------
# Single edge into a vertex that has multiple out-edges. Helpers.
# -----------------------------------------------------------------------------

def get_face_between_ordered_edges(bm, edge_a_id, edge_b_id):
    """
    Return one face shared by two incident edges, if any.

    The name says ordered, but this first version only needs the shared face.
    Later we can make this winding-aware if needed.
    """

    if edge_a_id is None or edge_b_id is None:
        return None

    faces_a = set(bm.edges[edge_a_id].faces)
    faces_b = set(bm.edges[edge_b_id].faces)

    common = sorted(list(faces_a.intersection(faces_b)))

    if not common:
        return None

    return common[0]


def get_rail_endpoint_for_edge_face(edge_data_by_id,
                                    rails_by_edge_id,
                                    edge_id,
                                    face_id,
                                    vertex_id):
    """
    Return selected-edge rail endpoint for vertex_id on face_id.
    """

    edge_data = edge_data_by_id.get(edge_id)
    rails = rails_by_edge_id.get(edge_id, [])

    if edge_data is None:
        return None

    return get_rail_endpoint_for_vertex(
        edge_data=edge_data,
        rails=rails,
        face_id=face_id,
        vertex_id=vertex_id
    )


def slide_boundary_point_on_edge(bm, vertex_id, edge_id, distance):
    """
    Create an ON_EDGE boundary point by sliding from vertex_id along edge_id.
    """

    edge = bm.edges[edge_id]
    other_vertex_id = edge.other_vertex(vertex_id)

    if other_vertex_id is None:
        return None

    vertex_point = bm.vertices[vertex_id].co_world
    other_point = bm.vertices[other_vertex_id].co_world

    return BX_offset.slide_distance_on_edge(
        vertex_position=vertex_point,
        other_vertex_position=other_point,
        distance=distance
    )



def get_other_vertex_id_on_edge(bm, edge_id, vertex_id):
    """
    Return the other endpoint of edge_id from vertex_id.
    """

    edge = bm.edges[edge_id]
    return edge.other_vertex(vertex_id)


def get_other_vertex_point_on_edge(bm, edge_id, vertex_id):
    """
    Return the world point of the other endpoint of edge_id from vertex_id.
    """

    other_vertex_id = get_other_vertex_id_on_edge(
        bm=bm,
        edge_id=edge_id,
        vertex_id=vertex_id
    )

    if other_vertex_id is None:
        return None

    return bm.vertices[other_vertex_id].co_world


def average_terminal_multi_vertex_normal(bm, vertex_id):
    """
    Average connected face normals around a vertex.

    Used by BX_offset.offset_meet_edge() for the reflex-angle test.
    """

    normal = [0.0, 0.0, 0.0]

    for face_id in bm.vertices[vertex_id].faces:
        normal = bxm.add(
            normal,
            bm.faces[face_id].normal_world
        )

    normal = bxm.normalize(normal)

    if bxm.is_zero(normal):
        return [0.0, 0.0, 0.0]

    return normal


def clamp_point_to_edge_from_vertex(bm, vertex_id, edge_id, point):
    """
    Clamp a solved point onto the segment from vertex_id to the other endpoint
    of edge_id.

    Blender can work with full BMesh topology and later cleanup. In BevelX's
    current local Maya edit path, clamping keeps the early implementation safer.
    """

    other_point = get_other_vertex_point_on_edge(
        bm=bm,
        edge_id=edge_id,
        vertex_id=vertex_id
    )

    if other_point is None:
        return point

    vertex_point = bm.vertices[vertex_id].co_world

    edge_vec = bxm.sub(other_point, vertex_point)
    edge_len = bxm.length(edge_vec)

    if edge_len <= bxm.EPSILON:
        return list(vertex_point)

    edge_dir = bxm.div(edge_vec, edge_len)

    t = bxm.dot(
        bxm.sub(point, vertex_point),
        edge_dir
    )

    t = bxm.clamp(t, 0.0, max(0.0, edge_len - (50.0 * bxm.EPSILON)))

    return bxm.add(
        vertex_point,
        bxm.mul(edge_dir, t)
    )

def build_terminal_multi_offset_meet_point(bm,
                                           vertex_id,
                                           selected_edge_id,
                                           adjacent_edge_id,
                                           width,
                                           fallback_point=None,
                                           debug_label=""):
    """
    Build a TERMINAL_MULTI selected-side point on adjacent_edge_id.

    Blender's build_boundary_terminal_edge() assumes the EdgeHalf order is
    already oriented for the local vertex. In BevelX/Maya, the local cyclic
    order can effectively come in reversed at the other endpoint.

    So this helper tries both normal signs and both equivalent argument orders.

    Goal:
        solve a point on adjacent_edge_id using the selected edge offset width.

    Candidate forms:
        A:
            edge_a = adjacent edge
            edge_b = selected edge
            offset_a_right = 0
            offset_b_left = width
            result lies on edge_a

        B:
            edge_a = selected edge
            edge_b = adjacent edge
            offset_a_right = width
            offset_b_left = 0
            result lies on edge_b

    Both are equivalent geometrically, but one may pass the reflex/orientation
    test while the other fails depending on local edge order.
    """

    vertex_point = bm.vertices[vertex_id].co_world

    selected_other = get_other_vertex_point_on_edge(
        bm=bm,
        edge_id=selected_edge_id,
        vertex_id=vertex_id
    )

    adjacent_other = get_other_vertex_point_on_edge(
        bm=bm,
        edge_id=adjacent_edge_id,
        vertex_id=vertex_id
    )

    if selected_other is None or adjacent_other is None:
        return fallback_point

    vertex_normal = average_terminal_multi_vertex_normal(
        bm=bm,
        vertex_id=vertex_id
    )

    if bxm.is_zero(vertex_normal):
        vertex_normal = [0.0, 1.0, 0.0]

    candidate_specs = [
        {
            "name": "adjacent_selected_normal",
            "edge_a_other": adjacent_other,
            "edge_b_other": selected_other,
            "offset_a_right": 0.0,
            "offset_b_left": width,
            "normal": vertex_normal,
        },
        {
            "name": "adjacent_selected_flipped_normal",
            "edge_a_other": adjacent_other,
            "edge_b_other": selected_other,
            "offset_a_right": 0.0,
            "offset_b_left": width,
            "normal": bxm.mul(vertex_normal, -1.0),
        },
        {
            "name": "selected_adjacent_normal",
            "edge_a_other": selected_other,
            "edge_b_other": adjacent_other,
            "offset_a_right": width,
            "offset_b_left": 0.0,
            "normal": vertex_normal,
        },
        {
            "name": "selected_adjacent_flipped_normal",
            "edge_a_other": selected_other,
            "edge_b_other": adjacent_other,
            "offset_a_right": width,
            "offset_b_left": 0.0,
            "normal": bxm.mul(vertex_normal, -1.0),
        },
    ]

    valid_candidates = []

    for spec in candidate_specs:
        result = BX_offset.offset_meet_edge(
            vertex_position=vertex_point,
            edge_a_other_position=spec["edge_a_other"],
            edge_b_other_position=spec["edge_b_other"],
            offset_a_right=spec["offset_a_right"],
            offset_b_left=spec["offset_b_left"],
            vertex_normal=spec["normal"]
        )

        if not result.get("ok", False):
            continue

        point = result.get("point")

        if point is None:
            continue

        clamped_point = clamp_point_to_edge_from_vertex(
            bm=bm,
            vertex_id=vertex_id,
            edge_id=adjacent_edge_id,
            point=point
        )

        distance_from_vertex = bxm.distance(
            vertex_point,
            clamped_point
        )

        # Reject tiny/no-op candidates.
        if distance_from_vertex <= bxm.EPSILON:
            continue

        valid_candidates.append(
            {
                "name": spec["name"],
                "point": clamped_point,
                "distance": distance_from_vertex,
                "angle": result.get("angle", 0.0),
            }
        )

    if not valid_candidates:
        if fallback_point is not None:
            BX_log.warn(
                "TERMINAL_MULTI meet fallback used at vertex {0}, side={1}, selected_edge={2}, adjacent_edge={3}".format(
                    vertex_id,
                    debug_label,
                    selected_edge_id,
                    adjacent_edge_id
                ),
                channel="summary"
            )

        return fallback_point

    # Prefer the candidate whose distance along the adjacent edge is closest
    # to the requested width, but still allows angle compensation.
    #
    # This avoids choosing a huge overhanging solve when the opposite orientation
    # also gives a sane local point.
    best = min(
        valid_candidates,
        key=lambda item: abs(item["distance"] - width)
    )

    BX_log.warn(
        "TERMINAL_MULTI meet used at vertex {0}, side={1}, selected_edge={2}, adjacent_edge={3}, method={4}, distance={5}".format(
            vertex_id,
            debug_label,
            selected_edge_id,
            adjacent_edge_id,
            best["name"],
            best["distance"]
        ),
        channel="summary"
    )

    return best["point"]

def build_terminal_multi_edge_boundary_for_vertex(bm,
                                                  bevel_vertex,
                                                  edge_data_by_id,
                                                  rails_by_edge_id):
    """
    Experimental TERMINAL_MULTI boundary.

    Case:
        one selected edge enters a vertex with more than two incident edges.

    Boundary output:
        - SELECTED_LEFT: selected-edge rail endpoint on previous selected face
        - SELECTED_RIGHT: selected-edge rail endpoint on next selected face
        - ON_EDGE points: one slid point on every other incident edge

    Important:
        ON_EDGE face_id is intentionally None for now.
        ON_EDGE points are not face-owned direct replacements.
    """

    vertex_id = bevel_vertex.vertex_id
    selected_edges = list(bevel_vertex.selected_edges)

    if len(selected_edges) != 1:
        return []

    selected_edge_id = selected_edges[0]

    edge_halves = list(getattr(bevel_vertex, "edge_halves", []))

    if not edge_halves:
        return build_terminal_boundary_for_vertex(
            edge_data=edge_data_by_id[selected_edge_id],
            rails=rails_by_edge_id[selected_edge_id],
            vertex_id=vertex_id
        )

    selected_index = None

    for i, edge_half in enumerate(edge_halves):
        if edge_half.edge_id == selected_edge_id:
            selected_index = i
            break

    if selected_index is None:
        return []

    count = len(edge_halves)

    prev_half = edge_halves[(selected_index - 1) % count]
    next_half = edge_halves[(selected_index + 1) % count]

    prev_edge_id = prev_half.edge_id
    next_edge_id = next_half.edge_id

    face_prev_selected = get_face_between_ordered_edges(
        bm=bm,
        edge_a_id=prev_edge_id,
        edge_b_id=selected_edge_id
    )

    face_selected_next = get_face_between_ordered_edges(
        bm=bm,
        edge_a_id=selected_edge_id,
        edge_b_id=next_edge_id
    )

    boundary_list = []

    rail_point_left = get_rail_endpoint_for_edge_face(
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id,
        edge_id=selected_edge_id,
        face_id=face_prev_selected,
        vertex_id=vertex_id
    )

    rail_point_right = get_rail_endpoint_for_edge_face(
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id,
        edge_id=selected_edge_id,
        face_id=face_selected_next,
        vertex_id=vertex_id
    )

    width = 0.0

    if rail_point_left is not None:
        width = bxm.distance(
            bm.vertices[vertex_id].co_world,
            rail_point_left
        )
    elif rail_point_right is not None:
        width = bxm.distance(
            bm.vertices[vertex_id].co_world,
            rail_point_right
        )

    # ------------------------------------------------------------
    # Selected-edge side A.
    # ------------------------------------------------------------
    point_left = build_terminal_multi_offset_meet_point(
        bm=bm,
        vertex_id=vertex_id,
        selected_edge_id=selected_edge_id,
        adjacent_edge_id=prev_edge_id,
        width=width,
        fallback_point=rail_point_left,
        debug_label="LEFT"
    )

    if point_left is not None:
        boundary_list.append(
            BX_BoundaryVertex(
                boundary_id="BV{0}_TERM_MULTI_SEL_L_E{1}_F{2}".format(
                    vertex_id,
                    selected_edge_id,
                    face_prev_selected
                ),
                original_vertex_id=vertex_id,
                selected_edge_id=selected_edge_id,
                face_id=face_prev_selected,
                co_world=point_left,
                source="TERMINAL_MULTI",
                edge_before_id=prev_edge_id,
                edge_after_id=selected_edge_id,
                edge_on_id=prev_edge_id,
                boundary_role="SELECTED_LEFT"
            )
        )

    # ------------------------------------------------------------
    # Selected-edge side B.
    # ------------------------------------------------------------
    point_right = build_terminal_multi_offset_meet_point(
        bm=bm,
        vertex_id=vertex_id,
        selected_edge_id=selected_edge_id,
        adjacent_edge_id=next_edge_id,
        width=width,
        fallback_point=rail_point_right,
        debug_label="RIGHT"
    )

    if point_right is not None:
        boundary_list.append(
            BX_BoundaryVertex(
                boundary_id="BV{0}_TERM_MULTI_SEL_R_E{1}_F{2}".format(
                    vertex_id,
                    selected_edge_id,
                    face_selected_next
                ),
                original_vertex_id=vertex_id,
                selected_edge_id=selected_edge_id,
                face_id=face_selected_next,
                co_world=point_right,
                source="TERMINAL_MULTI",
                edge_before_id=selected_edge_id,
                edge_after_id=next_edge_id,
                edge_on_id=next_edge_id,
                boundary_role="SELECTED_RIGHT"
            )
        )

    # ------------------------------------------------------------
    # Estimate slide width from selected rail endpoint.
    # ------------------------------------------------------------
    width = 0.0

    if point_left is not None:
        width = bxm.distance(
            bm.vertices[vertex_id].co_world,
            point_left
        )
    elif point_right is not None:
        width = bxm.distance(
            bm.vertices[vertex_id].co_world,
            point_right
        )

    # ------------------------------------------------------------
    # ON_EDGE points for non-selected incident edges.
    # Walk from next side around to previous side.
    # ------------------------------------------------------------
    cursor = (selected_index + 2) % count
    stop_index = (selected_index - 1) % count

    while cursor != stop_index:
        edge_half = edge_halves[cursor]
        edge_id = edge_half.edge_id

        if edge_id != selected_edge_id:
            point = slide_boundary_point_on_edge(
                bm=bm,
                vertex_id=vertex_id,
                edge_id=edge_id,
                distance=width
            )

            if point is not None:
                prev_i = (cursor - 1) % count
                next_i = (cursor + 1) % count

                edge_before_id = edge_halves[prev_i].edge_id
                edge_after_id = edge_halves[next_i].edge_id

                boundary_list.append(
                    BX_BoundaryVertex(
                        boundary_id="BV{0}_TERM_MULTI_ON_E{1}".format(
                            vertex_id,
                            edge_id
                        ),
                        original_vertex_id=vertex_id,
                        selected_edge_id=selected_edge_id,
                        face_id=None,
                        co_world=point,
                        source="TERMINAL_MULTI",
                        edge_before_id=edge_before_id,
                        edge_after_id=edge_after_id,
                        edge_on_id=edge_id,
                        boundary_role="ON_EDGE"
                    )
                )

        cursor = (cursor + 1) % count

    link_boundary_vertices_cyclic(boundary_list)

    BX_log.warn(
        "TERMINAL_MULTI boundary built for vertex {0}: selected_edge={1}, count={2}".format(
            vertex_id,
            selected_edge_id,
            len(boundary_list)
        ),
        channel="summary"
    )

    return boundary_list

def should_use_terminal_multi_boundary(bm, bevel_vertex, edges_data):
    """
    Return True for TERMINAL_MULTI endpoint cases.

    Supported case:
        - exactly one selected edge touches this vertex
        - original vertex has more than two incident edges
        - selected edge exists in the cyclic edge-half ring
    """

    selected_edges = list(getattr(bevel_vertex, "selected_edges", []))
    selected_count = len(selected_edges)

    edge_halves = list(getattr(bevel_vertex, "edge_halves", []))

    if edge_halves:
        incident_edge_count = len(edge_halves)
    else:
        incident_edge_count = getattr(bevel_vertex, "edge_count", 0)

    vertex_id = getattr(bevel_vertex, "vertex_id", getattr(bevel_vertex, "id", None))

    if selected_count != 1:
        debug_terminal_multi_gate(
            bm=bm,
            bevel_vertex=bevel_vertex,
            edges_data=edges_data,
            reason="selected_count_not_1"
        )
        return False

    if incident_edge_count <= 2:
        debug_terminal_multi_gate(
            bm=bm,
            bevel_vertex=bevel_vertex,
            edges_data=edges_data,
            reason="incident_edge_count_not_gt_2"
        )
        return False

    if not edge_halves:
        debug_terminal_multi_gate(
            bm=bm,
            bevel_vertex=bevel_vertex,
            edges_data=edges_data,
            reason="no_edge_halves"
        )
        return False

    selected_edge_id = selected_edges[0]

    for edge_half in edge_halves:
        if getattr(edge_half, "edge_id", None) == selected_edge_id:
            BX_log.warn(
                "TERMINAL_MULTI gate accepted vertex {0}: selected_edge={1}, incident_count={2}".format(
                    vertex_id,
                    selected_edge_id,
                    incident_edge_count
                ),
                channel="summary"
            )
            return True

    debug_terminal_multi_gate(
        bm=bm,
        bevel_vertex=bevel_vertex,
        edges_data=edges_data,
        reason="selected_edge_not_in_edge_halves"
    )

    return False

def debug_terminal_multi_gate(bm, bevel_vertex, edges_data, reason):
    """
    Temporary summary log for TERMINAL_MULTI gate decisions.
    """

    vertex_id = getattr(bevel_vertex, "vertex_id", getattr(bevel_vertex, "id", None))
    selected_edges = list(getattr(bevel_vertex, "selected_edges", []))
    edge_halves = list(getattr(bevel_vertex, "edge_halves", []))

    edge_half_ids = [
        getattr(edge_half, "edge_id", None)
        for edge_half in edge_halves
    ]

    BX_log.warn(
        "TERMINAL_MULTI gate vertex {0}: reason={1}, selected_edges={2}, selected_count_attr={3}, edge_count_attr={4}, edge_halves={5}, selection_edge_count={6}".format(
            vertex_id,
            reason,
            selected_edges,
            getattr(bevel_vertex, "selected_count", None),
            getattr(bevel_vertex, "edge_count", None),
            edge_half_ids,
            len(edges_data) if edges_data is not None else None
        ),
        channel="summary"
    )

# -----------------------------------------------------------------------------
# CHAIN_2 helpers
# -----------------------------------------------------------------------------

def get_common_faces_between_selected_edges(bm, selected_edge_ids):
    """
    Return common faces shared by two selected edges.

    Args:
        bm:
            BX_BMesh.

        selected_edge_ids:
            Exactly two selected edge ids.

    Returns:
        Sorted list of common face ids.
    """

    if len(selected_edge_ids) != 2:
        return []

    edge_a = bm.edges[selected_edge_ids[0]]
    edge_b = bm.edges[selected_edge_ids[1]]

    return sorted(list(set(edge_a.faces).intersection(set(edge_b.faces))))


def is_chain_2_vertex(bm, bevel_vertex):
    """
    Return True when a bevel vertex has two selected edges but those
    selected edges do not share a face.

    This is a through-chain case, not a miter/corner case.
    """

    if bevel_vertex.selected_count != 2:
        return False

    common_faces = get_common_faces_between_selected_edges(
        bm=bm,
        selected_edge_ids=list(bevel_vertex.selected_edges)
    )

    return not common_faces


def is_corner_2_vertex(bm, bevel_vertex):
    """
    Return True when a bevel vertex has two selected edges and those
    selected edges share a face.

    This is the sharp miter/corner case.
    """

    if bevel_vertex.selected_count != 2:
        return False

    common_faces = get_common_faces_between_selected_edges(bm=bm,
        selected_edge_ids=list(bevel_vertex.selected_edges))

    return bool(common_faces)


def log_chain2_solve(vertex_id, gap_index, middle_edge_id, face_a_id, face_b_id, source, point):
    """
    Trace-only CHAIN_2 solve log.
    """

    BX_log.trace("CHAIN_2 through solve vertex {0}, gap {1}: middle_edge={2}, faces=({3}, {4}), source={5}, point={6}".format(
            vertex_id, gap_index, middle_edge_id, face_a_id, face_b_id, source, point), channel="boundary")


def log_chain2_fallback(vertex_id, reason):
    """
    Debug-only CHAIN_2 fallback log.
    """

    BX_log.debug("CHAIN_2 through solve fallback at vertex {0}: {1}".format(
            vertex_id, reason), channel="boundary")

def build_chain_2_boundary_for_vertex(bm, bevel_vertex, edge_data_by_id, rails_by_edge_id):
    """
    Build boundary vertices for a CHAIN_2 through vertex.

    First-pass through solver:
        - exactly 2 selected edges
        - selected edges do not share a face
        - each side between selected edges has exactly one unselected middle edge

    For straight grids this behaves like the old endpoint version.
    For curved grids this solves a shared point on the middle edge so the bevel
    can shrink on concave turns and widen on convex turns without gaps/overlaps.
    """

    vertex_id = bevel_vertex.vertex_id
    vertex_position = bevel_vertex.position
    selected_edges = list(bevel_vertex.selected_edges)

    if len(selected_edges) != 2:
        return []

    edge_halves = list(getattr(bevel_vertex, "edge_halves", []))

    # If the cyclic edge-half data is missing, fall back to the old simple behavior.
    if not edge_halves:
        boundary_list = []

        for edge_id in selected_edges:
            edge_data = edge_data_by_id.get(edge_id)
            rails = rails_by_edge_id.get(edge_id, [])

            if edge_data is None:
                continue

            for rail_data in rails:
                face_id = rail_data["face_id"]

                point = get_rail_endpoint_for_vertex(
                    edge_data=edge_data,
                    rails=rails,
                    face_id=face_id,
                    vertex_id=vertex_id
                )

                if point is None:
                    continue

                boundary_list.append(
                    BX_BoundaryVertex(
                        boundary_id="BV{0}_CHAIN_E{1}_F{2}".format(vertex_id, edge_id, face_id),
                        original_vertex_id=vertex_id,
                        selected_edge_id=edge_id,
                        face_id=face_id,
                        co_world=point,
                        source="CHAIN_2"
                    )
                )

        link_boundary_vertices_cyclic(boundary_list)
        return boundary_list

    selected_indices = []

    for i, edge_half in enumerate(edge_halves):
        if edge_half.edge_id in selected_edges:
            selected_indices.append(i)

    if len(selected_indices) != 2:
        log_chain2_fallback(vertex_id=vertex_id,
            reason="expected 2 selected edge halves, got {0}".format(len(selected_indices))
        )

        boundary_list = []

        for edge_id in selected_edges:
            edge_data = edge_data_by_id.get(edge_id)
            rails = rails_by_edge_id.get(edge_id, [])

            if edge_data is None:
                continue

            for rail_data in rails:
                face_id = rail_data["face_id"]

                point = get_rail_endpoint_for_vertex(
                    edge_data=edge_data,
                    rails=rails,
                    face_id=face_id,
                    vertex_id=vertex_id
                )

                if point is None:
                    continue

                boundary_list.append(
                    BX_BoundaryVertex(
                        boundary_id="BV{0}_CHAIN_E{1}_F{2}".format(vertex_id, edge_id, face_id),
                        original_vertex_id=vertex_id,
                        selected_edge_id=edge_id,
                        face_id=face_id,
                        co_world=point,
                        source="CHAIN_2"
                    )
                )

        link_boundary_vertices_cyclic(boundary_list)
        return boundary_list

    count = len(edge_halves)
    first_selected_index = selected_indices[0]
    second_selected_index = selected_indices[1]

    # Two cyclic gaps:
    #   selected A -> ... -> selected B
    #   selected B -> ... -> selected A
    gap_specs = [
        (first_selected_index, second_selected_index),
        (second_selected_index, first_selected_index),
    ]

    vertex_normal = None

    if bm is not None and vertex_id in bm.vertices:
        normal = [0.0, 0.0, 0.0]

        for face_id in bm.vertices[vertex_id].faces:
            normal = bxm.add(normal, bm.faces[face_id].normal_world)

        vertex_normal = bxm.normalize(normal)

    if vertex_normal is None or bxm.is_zero(vertex_normal):
        vertex_normal = [0.0, 1.0, 0.0]

    boundary_list = []
    solved_all_gaps = True

    for gap_index, gap_spec in enumerate(gap_specs):
        selected_a_index, selected_b_index = gap_spec

        middle_indices = []
        cursor = (selected_a_index + 1) % count

        while cursor != selected_b_index:
            middle_indices.append(cursor)
            cursor = (cursor + 1) % count

        # First pass: only solve clean quad-grid case with exactly one middle edge.
        if len(middle_indices) != 1:
            solved_all_gaps = False
            log_chain2_fallback(
                vertex_id=vertex_id,
                reason="unsupported gap layout"
            )
            break

        selected_a_half = edge_halves[selected_a_index]
        middle_half = edge_halves[middle_indices[0]]
        selected_b_half = edge_halves[selected_b_index]

        edge_a_id = selected_a_half.edge_id
        edge_b_id = selected_b_half.edge_id
        middle_edge_id = middle_half.edge_id

        edge_a = bm.edges[edge_a_id]
        edge_b = bm.edges[edge_b_id]
        middle_edge = bm.edges[middle_edge_id]

        face_a_candidates = sorted(list(set(edge_a.faces).intersection(set(middle_edge.faces))))
        face_b_candidates = sorted(list(set(edge_b.faces).intersection(set(middle_edge.faces))))

        if not face_a_candidates or not face_b_candidates:
            solved_all_gaps = False
            log_chain2_fallback(
                vertex_id=vertex_id,
                reason="missing face candidates around middle edge"
            )
            break

        face_a_id = face_a_candidates[0]
        face_b_id = face_b_candidates[0]

        edge_a_data = edge_data_by_id.get(edge_a_id)
        edge_b_data = edge_data_by_id.get(edge_b_id)

        rails_a = rails_by_edge_id.get(edge_a_id, [])
        rails_b = rails_by_edge_id.get(edge_b_id, [])

        if edge_a_data is None or edge_b_data is None:
            solved_all_gaps = False
            log_chain2_fallback(
                vertex_id=vertex_id,
                reason="missing edge data"
            )
            break

        point_a = get_rail_endpoint_for_vertex(
            edge_data=edge_a_data,
            rails=rails_a,
            face_id=face_a_id,
            vertex_id=vertex_id
        )

        point_b = get_rail_endpoint_for_vertex(
            edge_data=edge_b_data,
            rails=rails_b,
            face_id=face_b_id,
            vertex_id=vertex_id
        )

        if point_a is None or point_b is None:
            solved_all_gaps = False
            log_chain2_fallback(
                vertex_id=vertex_id,
                reason="missing rail endpoint"
            )
            break

        offset_a = bxm.distance(vertex_position, point_a)
        offset_b = bxm.distance(vertex_position, point_b)

        edge_a_other_position = bm.vertices[selected_a_half.other_vertex_id].co_world
        middle_edge_other_position = bm.vertices[middle_half.other_vertex_id].co_world
        edge_b_other_position = bm.vertices[selected_b_half.other_vertex_id].co_world

        solve = BX_offset.offset_on_edge_between(
            vertex_position=vertex_position,
            edge_a_other_position=edge_a_other_position,
            middle_edge_other_position=middle_edge_other_position,
            edge_b_other_position=edge_b_other_position,
            offset_a_right=offset_a,
            offset_b_left=offset_b,
            vertex_normal=vertex_normal
        )

        meet_point = solve["point"]

        # Clamp meet point to the actual middle edge segment.
        meet_point = bxm.closest_point_on_segment(
            meet_point,
            vertex_position,
            middle_edge_other_position
        )

        boundary_list.append(
            BX_BoundaryVertex(
                boundary_id="BV{0}_CHAIN_THROUGH_E{1}_F{2}".format(vertex_id, edge_a_id, face_a_id),
                original_vertex_id=vertex_id,
                selected_edge_id=edge_a_id,
                face_id=face_a_id,
                co_world=meet_point,
                source="CHAIN_2_THROUGH"
            )
        )

        boundary_list.append(
            BX_BoundaryVertex(
                boundary_id="BV{0}_CHAIN_THROUGH_E{1}_F{2}".format(vertex_id, edge_b_id, face_b_id),
                original_vertex_id=vertex_id,
                selected_edge_id=edge_b_id,
                face_id=face_b_id,
                co_world=meet_point,
                source="CHAIN_2_THROUGH"
            )
        )

        solve_source = solve.get("source", "offset_on_edge_between")
        log_chain2_solve(
            vertex_id=vertex_id,
            gap_index=gap_index,
            middle_edge_id=middle_edge_id,
            face_a_id=face_a_id,
            face_b_id=face_b_id,
            source=solve_source,
            point=meet_point
        )

    if solved_all_gaps and len(boundary_list) == 4:
        link_boundary_vertices_cyclic(boundary_list)
        return boundary_list

    # Conservative fallback to the old behavior.
    BX_log.debug("CHAIN_2 fallback to endpoint boundaries at vertex {0}.".format(
            vertex_id), channel="boundary")

    boundary_list = []

    for edge_id in selected_edges:
        edge_data = edge_data_by_id.get(edge_id)
        rails = rails_by_edge_id.get(edge_id, [])

        if edge_data is None:
            BX_log.warn("CHAIN_2 failed at vertex {0}: missing edge_data for edge {1}.".format(
                    vertex_id, edge_id), channel="summary")
            continue

        for rail_data in rails:
            face_id = rail_data["face_id"]

            point = get_rail_endpoint_for_vertex(
                edge_data=edge_data,
                rails=rails,
                face_id=face_id,
                vertex_id=vertex_id
            )

            if point is None:
                BX_log.warn("CHAIN_2 failed at vertex {0}: missing rail endpoint for edge {1}, face {2}.".format(
                        vertex_id, edge_id, face_id), channel="boundary")
                continue

            boundary_vertex = BX_BoundaryVertex(
                boundary_id="BV{0}_CHAIN_E{1}_F{2}".format(
                    vertex_id,
                    edge_id,
                    face_id
                ),
                original_vertex_id=vertex_id,
                selected_edge_id=edge_id,
                face_id=face_id,
                co_world=point,
                source="CHAIN_2"
            )

            boundary_list.append(boundary_vertex)

    link_boundary_vertices_cyclic(boundary_list)

    return boundary_list

def build_corner_2_boundary_for_vertex(bm,
                                       bevel_vertex,
                                       edge_data_by_id,
                                       rails_by_edge_id):
    """
    Build first sharp CORNER_2 boundary for a vertex touched by two selected edges.

    Current strategy:
        - Find the common face shared by both selected edges.
        - Find the non-common face on each selected edge.
        - Use rail endpoint on each non-common face.
        - Use line/line midpoint intersection of both rails on the common face.

    This is the first miter-style boundary for two connected selected edges.
    """

    vertex_id = bevel_vertex.vertex_id
    selected_edges = list(bevel_vertex.selected_edges)

    if len(selected_edges) != 2:
        return []

    edge_a_id = selected_edges[0]
    edge_b_id = selected_edges[1]

    edge_a = bm.edges[edge_a_id]
    edge_b = bm.edges[edge_b_id]

    common_faces = sorted(list(set(edge_a.faces).intersection(set(edge_b.faces))))

    if not common_faces:
        BX_log.warn("CORNER_2 failed at vertex {0}: no common face.".format(vertex_id),
                    channel="boundary")
        return []

    common_face_id = common_faces[0]

    outer_face_a = get_non_common_face(edge_a.faces, common_face_id)
    outer_face_b = get_non_common_face(edge_b.faces, common_face_id)

    if outer_face_a is None or outer_face_b is None:
        BX_log.warn("CORNER_2 failed at vertex {0}: missing outer faces.".format(vertex_id),
                    channel="boundary")
        return []

    edge_a_data = edge_data_by_id[edge_a_id]
    edge_b_data = edge_data_by_id[edge_b_id]

    rails_a = rails_by_edge_id[edge_a_id]
    rails_b = rails_by_edge_id[edge_b_id]

    point_outer_a = get_rail_endpoint_for_vertex(
        edge_data=edge_a_data,
        rails=rails_a,
        face_id=outer_face_a,
        vertex_id=vertex_id
    )

    point_outer_b = get_rail_endpoint_for_vertex(
        edge_data=edge_b_data,
        rails=rails_b,
        face_id=outer_face_b,
        vertex_id=vertex_id
    )

    point_common = get_common_face_miter_point(
        edge_a_data=edge_a_data,
        rails_a=rails_a,
        edge_b_data=edge_b_data,
        rails_b=rails_b,
        common_face_id=common_face_id
    )

    if point_outer_a is None or point_outer_b is None or point_common is None:
        BX_log.warn("CORNER_2 failed at vertex {0}: missing miter points.".format(vertex_id),
                    channel="summary")
        return []

    boundary_list = [
        BX_BoundaryVertex(
            boundary_id="BV{0}_CORNER2_E{1}_F{2}".format(vertex_id, edge_a_id, outer_face_a),
            original_vertex_id=vertex_id,
            selected_edge_id=edge_a_id,
            face_id=outer_face_a,
            co_world=point_outer_a,
            source="CORNER_2"
        ),

        BX_BoundaryVertex(
            boundary_id="BV{0}_CORNER2_F{1}".format(vertex_id, common_face_id),
            original_vertex_id=vertex_id,
            selected_edge_id=edge_a_id,
            face_id=common_face_id,
            co_world=point_common,
            source="CORNER_2"
        ),

        BX_BoundaryVertex(
            boundary_id="BV{0}_CORNER2_E{1}_F{2}".format(vertex_id, edge_b_id, outer_face_b),
            original_vertex_id=vertex_id,
            selected_edge_id=edge_b_id,
            face_id=outer_face_b,
            co_world=point_outer_b,
            source="CORNER_2"
        ),
    ]

    link_boundary_vertices_cyclic(boundary_list)

    return boundary_list


def get_non_common_face(face_ids, common_face_id):
    """
    Return first face in face_ids that is not common_face_id.
    """

    for face_id in face_ids:
        if face_id != common_face_id:
            return face_id

    return None


def get_rail_endpoint_for_vertex(edge_data, rails, face_id, vertex_id):
    """
    Return the rail endpoint corresponding to vertex_id on face_id.
    """

    edge_v0, edge_v1 = edge_data["vertex_ids"]

    for rail_data in rails:
        if rail_data["face_id"] != face_id:
            continue

        rail_p0, rail_p1 = rail_data["rail"]

        if vertex_id == edge_v0:
            return rail_p0

        if vertex_id == edge_v1:
            return rail_p1

    return None


def get_rail_for_face(rails, face_id):
    """
    Return rail tuple for face_id.
    """

    for rail_data in rails:
        if rail_data["face_id"] == face_id:
            return rail_data["rail"]

    return None


def get_common_face_miter_point(edge_a_data,
                                rails_a,
                                edge_b_data,
                                rails_b,
                                common_face_id):
    """
    Return miter point on the common face between two selected edges.

    Uses closest point midpoint between the two common-face offset rails.
    """

    rail_a = get_rail_for_face(rails_a, common_face_id)
    rail_b = get_rail_for_face(rails_b, common_face_id)

    if rail_a is None or rail_b is None:
        return None

    a0, a1 = rail_a
    b0, b1 = rail_b

    return bxm.line_line_intersection_midpoint(
        a0,
        a1,
        b0,
        b1
    )