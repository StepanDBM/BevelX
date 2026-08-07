# BX_boundvert.py
#
# Blender-aligned BoundVert ring foundation for BevelX.
#
# This module is intentionally NOT another topology category system.
# It is the compatibility entry point for moving BevelX toward Blender's
# BevVert -> EdgeHalf -> BoundVert -> VMesh boundary model.
#
# Naming is BevelX-readable, but the model must stay Blender-like:
#   - an affected original vertex owns a cyclic ring of incident EdgeHalves
#   - neighboring EdgeHalf pairs define boundary sectors
#   - boundary sectors produce BoundVerts
#   - cap/reconstruction code should consume the resulting BoundVert ring
#
# Do not add CORNER_2 / TRI_CAP / TERMINAL_MULTI / CHAIN_2 / SECTOR_BOUNDARY
# style routing here. Those are compatibility labels in legacy code only.

from __future__ import print_function

from BX_math import BX_math as bxm
from BX_math import BX_offset
from BX_profile import BX_log


BOUNDVERT_SOURCE = "BOUNDVERT"

ROLE_SELECTED_SELECTED_MEET = "SELECTED_SELECTED_MEET"
ROLE_SELECTED_UNSELECTED_MEET = "SELECTED_UNSELECTED_MEET"
ROLE_UNSELECTED_SELECTED_MEET = "UNSELECTED_SELECTED_MEET"
ROLE_ON_EDGE = "ON_EDGE"
ROLE_SUPPORT = "SUPPORT"


class BX_BoundVert(object):
    """
    One boundary vertex around one original bevel vertex.

    This is the BevelX-side equivalent of Blender's BoundVert concept.
    The class deliberately keeps compatibility fields used by the current
    transaction layer, but the semantic fields are Blender-style ownership:

        original_vertex_id
            The source mesh vertex this boundary point belongs to.

        face_id
            Source face/sector that owns this boundary point, if any.

        efirst_id / elast_id
            The edge-half pair / sector that produced this boundvert.

        edge_on_id
            Unselected support edge this point lies on, when applicable.

        role
            Debug role only. Do not route topology by role unless unavoidable.
    """

    def __init__(self,
                 boundary_id,
                 original_vertex_id,
                 co_world,
                 face_id=None,
                 selected_edge_id=None,
                 edge_before_id=None,
                 edge_after_id=None,
                 edge_on_id=None,
                 efirst_id=None,
                 elast_id=None,
                 role=None,
                 source=BOUNDVERT_SOURCE):
        self.id = boundary_id

        self.original_vertex_id = int(original_vertex_id)
        self.co_world = list(co_world)

        self.face_id = int(face_id) if face_id is not None else None
        self.selected_edge_id = int(selected_edge_id) if selected_edge_id is not None else None

        # Legacy-compatible names used by BX_transaction today.
        self.edge_before_id = int(edge_before_id) if edge_before_id is not None else None
        self.edge_after_id = int(edge_after_id) if edge_after_id is not None else None
        self.edge_on_id = int(edge_on_id) if edge_on_id is not None else None
        self.boundary_role = role
        self.source = source

        # Blender-style sector ownership aliases.
        self.efirst_id = int(efirst_id) if efirst_id is not None else self.edge_before_id
        self.elast_id = int(elast_id) if elast_id is not None else self.edge_after_id
        self.role = role

        self.prev = None
        self.next = None

    def __repr__(self):
        prev_id = self.prev.id if self.prev else None
        next_id = self.next.id if self.next else None

        return (
            "BX_BoundVert(id={0}, original_vertex={1}, face={2}, "
            "efirst={3}, elast={4}, edge_on={5}, role={6}, co={7}, "
            "prev={8}, next={9})"
        ).format(
            self.id,
            self.original_vertex_id,
            self.face_id,
            self.efirst_id,
            self.elast_id,
            self.edge_on_id,
            self.role,
            self.co_world,
            prev_id,
            next_id,
        )


# Compatibility alias for code that expects BX_BoundaryVertex-shaped objects.
BX_BoundaryVertex = BX_BoundVert

def link_boundverts_cyclic(boundverts):
    """
    Link BoundVerts as one cyclic ring.
    """

    count = len(boundverts)

    if count == 0:
        return

    for i, boundvert in enumerate(boundverts):
        boundvert.prev = boundverts[(i - 1) % count]
        boundvert.next = boundverts[(i + 1) % count]


def boundvert_points_are_close(point_a, point_b, epsilon=1.0e-6):
    return bxm.distance(point_a, point_b) <= epsilon


def collapse_boundverts_by_position(boundverts, epsilon=1.0e-6):
    """
    Collapse duplicate/coincident BoundVerts, preserving cyclic order.

    Blender has robust mesh cleanup and merge avoidance lower in BMesh.
    In BevelX/Maya, duplicate point removal must happen explicitly before
    transaction vertices are emitted.
    """

    result = []

    for boundvert in boundverts:
        duplicate = False

        for existing in result:
            if boundvert_points_are_close(
                boundvert.co_world,
                existing.co_world,
                epsilon=epsilon
            ):
                duplicate = True
                break

        if not duplicate:
            result.append(boundvert)

    return result


def get_edge_half_ring(bevel_vertex):
    return list(getattr(bevel_vertex, "edge_halves", []))


def get_selected_edge_ids(bevel_vertex):
    return set(list(getattr(bevel_vertex, "selected_edges", [])))


def mark_beveled_edge_halves(edge_halves, selected_edge_ids):
    for edge_half in edge_halves:
        is_beveled = edge_half.edge_id in selected_edge_ids
        edge_half.is_beveled = is_beveled
        edge_half.is_bev = is_beveled
        edge_half.beveled = is_beveled

def build_terminal_boundvert_ring_for_vertex(bm,
                                             vertex_id,
                                             edge_halves,
                                             selected_half,
                                             edge_data_by_id,
                                             rails_by_edge_id,
                                             settings=None):
    """
    Blender-style terminal selected-edge BoundVert ring.

    This replaces:
        - build_terminal_boundary_for_vertex()
        - build_terminal_multi_edge_boundary_for_vertex()

    One selected edge enters the vertex. The ring walks every adjacent
    EdgeHalf pair and creates BoundVerts using selected/unselected or
    unselected/unselected rules.
    """

    selected_edge_id = selected_half.edge_id

    support_width = estimate_boundvert_width_for_vertex(
        bm=bm,
        vertex_id=vertex_id,
        selected_edge_ids=set([selected_edge_id]),
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id
    )

    if support_width is None:
        support_width = 0.0

    boundverts = []
    count = len(edge_halves)

    for i in range(count):
        previous_half = edge_halves[i]
        current_half = edge_halves[(i + 1) % count]

        previous_is_selected = previous_half.edge_id == selected_edge_id
        current_is_selected = current_half.edge_id == selected_edge_id

        face_id = get_face_between_edge_halves(
            bm=bm,
            edge_half_a=previous_half,
            edge_half_b=current_half
        )

        if face_id is None:
            continue

        if previous_is_selected and current_is_selected:
            boundvert = build_selected_selected_boundvert(
                bm=bm,
                vertex_id=vertex_id,
                previous_half=previous_half,
                current_half=current_half,
                face_id=face_id,
                edge_data_by_id=edge_data_by_id,
                rails_by_edge_id=rails_by_edge_id
            )

        elif previous_is_selected and not current_is_selected:
            point = solve_selected_unselected_meet(
                bm=bm,
                vertex_id=vertex_id,
                selected_edge_id=previous_half.edge_id,
                support_edge_id=current_half.edge_id,
                face_id=face_id,
                edge_data_by_id=edge_data_by_id,
                rails_by_edge_id=rails_by_edge_id
            )

            if point is None:
                continue

            boundvert = BX_BoundVert(
                boundary_id="BV{0}_BNDV_F{1}_E{2}_E{3}".format(
                    vertex_id,
                    face_id,
                    previous_half.edge_id,
                    current_half.edge_id
                ),
                original_vertex_id=vertex_id,
                co_world=point,
                face_id=face_id,
                selected_edge_id=previous_half.edge_id,
                edge_before_id=previous_half.edge_id,
                edge_after_id=current_half.edge_id,
                edge_on_id=current_half.edge_id,
                efirst_id=previous_half.edge_id,
                elast_id=current_half.edge_id,
                role=ROLE_SELECTED_UNSELECTED_MEET
            )
            boundvert.selected_edge_face_ids = {
                current_half.edge_id: face_id
            }

        elif not previous_is_selected and current_is_selected:
            point = solve_selected_unselected_meet(
                bm=bm,
                vertex_id=vertex_id,
                selected_edge_id=current_half.edge_id,
                support_edge_id=previous_half.edge_id,
                face_id=face_id,
                edge_data_by_id=edge_data_by_id,
                rails_by_edge_id=rails_by_edge_id
            )

            if point is None:
                continue

            boundvert = BX_BoundVert(
                boundary_id="BV{0}_BNDV_F{1}_E{2}_E{3}".format(
                    vertex_id,
                    face_id,
                    current_half.edge_id,
                    previous_half.edge_id
                ),
                original_vertex_id=vertex_id,
                co_world=point,
                face_id=face_id,
                selected_edge_id=current_half.edge_id,
                edge_before_id=current_half.edge_id,
                edge_after_id=previous_half.edge_id,
                edge_on_id=previous_half.edge_id,
                efirst_id=current_half.edge_id,
                elast_id=previous_half.edge_id,
                role=ROLE_UNSELECTED_SELECTED_MEET
            )
            boundvert.selected_edge_face_ids = {
                current_half.edge_id: face_id
            }

        else:
            point = slide_point_on_edge_from_vertex(
                bm=bm,
                vertex_id=vertex_id,
                edge_id=current_half.edge_id,
                distance=support_width
            )

            if point is None:
                continue

            boundvert = BX_BoundVert(
                boundary_id="BV{0}_BNDV_F{1}_E{2}_E{3}".format(
                    vertex_id,
                    face_id,
                    previous_half.edge_id,
                    current_half.edge_id
                ),
                original_vertex_id=vertex_id,
                co_world=point,
                face_id=face_id,
                selected_edge_id=None,
                edge_before_id=previous_half.edge_id,
                edge_after_id=current_half.edge_id,
                edge_on_id=current_half.edge_id,
                efirst_id=previous_half.edge_id,
                elast_id=current_half.edge_id,
                role=ROLE_ON_EDGE
            )

        if boundvert is not None:
            boundvert.efirst = previous_half
            boundvert.elast = current_half
            boundvert.eon = getattr(boundvert, "edge_on_id", None)
            boundvert.ebev = selected_half
            boundverts.append(boundvert)

    link_boundverts_cyclic(boundverts)

    BX_log.warn(
        "BOUNDVERT terminal ring built for vertex {0}: incident={1}, selected=1, count={2}".format(
            vertex_id,
            len(edge_halves),
            len(boundverts)
        ),
        channel="summary"
    )

    return boundverts

def choose_gap_edge_on_for_point(bm,
                                 vertex_id,
                                 gap_halves,
                                 point):
    """
    Pick the gap EdgeHalf whose source edge segment is closest to point.

    This is used by a multi-edge gap BoundVert to decide which unbeveled
    support edge should become edge_on_id / eon.
    """

    if bm is None:
        return None

    if point is None:
        return None

    if not gap_halves:
        return None

    if vertex_id not in bm.vertices:
        return None

    vertex_point = bm.vertices[vertex_id].co_world

    best_half = None
    best_distance = None

    for gap_half in gap_halves:
        edge_id = getattr(gap_half, "edge_id", None)

        if edge_id is None:
            continue

        if edge_id not in bm.edges:
            continue

        other_point = get_other_vertex_point_on_edge(
            bm=bm,
            edge_id=edge_id,
            vertex_id=vertex_id
        )

        if other_point is None:
            continue

        closest_point = bxm.closest_point_on_segment(
            point,
            vertex_point,
            other_point
        )

        distance = bxm.distance(point, closest_point)

        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_half = gap_half

    return best_half

def build_selected_gap_selected_boundvert_for_run(bm,
                                                  vertex_id,
                                                  left_selected_half,
                                                  gap_halves,
                                                  right_selected_half,
                                                  edge_data_by_id,
                                                  rails_by_edge_id,
                                                  settings=None):
    """
    Blender-style non-adjacent selected-edge gap BoundVert.

    For now:
        - solve the first and last selected/unselected meets
        - add slide probes on middle gap edges
        - average them
        - attach edge_on_id to the middle gap edge nearest the averaged point

    This replaces legacy SECTOR_BOUNDARY gap aliases.
    """

    if not gap_halves:
        return None

    first_gap_half = gap_halves[0]
    last_gap_half = gap_halves[-1]

    left_face_id = get_face_between_edge_halves(
        bm=bm,
        edge_half_a=left_selected_half,
        edge_half_b=first_gap_half
    )

    right_face_id = get_face_between_edge_halves(
        bm=bm,
        edge_half_a=last_gap_half,
        edge_half_b=right_selected_half
    )

    selected_edge_ids = set([
        left_selected_half.edge_id,
        right_selected_half.edge_id
    ])

    width = estimate_boundvert_width_for_vertex(
        bm=bm,
        vertex_id=vertex_id,
        selected_edge_ids=selected_edge_ids,
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id
    )

    if width is None:
        width = 0.0

    candidates = []

    left_point = solve_selected_unselected_meet(
        bm=bm,
        vertex_id=vertex_id,
        selected_edge_id=left_selected_half.edge_id,
        support_edge_id=first_gap_half.edge_id,
        face_id=left_face_id,
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id
    )

    if left_point is not None:
        candidates.append(left_point)

    right_point = solve_selected_unselected_meet(
        bm=bm,
        vertex_id=vertex_id,
        selected_edge_id=right_selected_half.edge_id,
        support_edge_id=last_gap_half.edge_id,
        face_id=right_face_id,
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id
    )

    if right_point is not None:
        candidates.append(right_point)

    for gap_half in gap_halves:
        slide_point = slide_point_on_edge_from_vertex(
            bm=bm,
            vertex_id=vertex_id,
            edge_id=gap_half.edge_id,
            distance=width
        )

        if slide_point is not None:
            candidates.append(slide_point)

    if not candidates:
        return None

    point = [0.0, 0.0, 0.0]

    for candidate in candidates:
        point = bxm.add(point, candidate)

    point = bxm.div(point, float(len(candidates)))

    edge_on_half = choose_gap_edge_on_for_point(
        bm=bm,
        vertex_id=vertex_id,
        gap_halves=gap_halves,
        point=point
    )

    if edge_on_half is not None:
        point = clamp_point_to_edge_from_vertex(
            bm=bm,
            vertex_id=vertex_id,
            edge_id=edge_on_half.edge_id,
            point=point
        )
        edge_on_id = edge_on_half.edge_id
    else:
        edge_on_id = first_gap_half.edge_id

    boundvert = BX_BoundVert(
        boundary_id="BV{0}_BNDV_GAP_E{1}_RUN{2}_E{3}".format(
            vertex_id,
            left_selected_half.edge_id,
            "_".join(str(gap_half.edge_id) for gap_half in gap_halves),
            right_selected_half.edge_id
        ),
        original_vertex_id=vertex_id,
        co_world=point,
        face_id=left_face_id,
        selected_edge_id=None,
        edge_before_id=left_selected_half.edge_id,
        edge_after_id=right_selected_half.edge_id,
        edge_on_id=edge_on_id,
        efirst_id=left_selected_half.edge_id,
        elast_id=right_selected_half.edge_id,
        role=ROLE_SUPPORT
    )

    boundvert.efirst = left_selected_half
    boundvert.elast = right_selected_half
    boundvert.eon = edge_on_half
    boundvert.ebev = None

    boundvert.selected_edge_face_ids = {
        left_selected_half.edge_id: left_face_id,
        right_selected_half.edge_id: right_face_id
    }

    return boundvert

def get_face_between_edge_halves(bm, edge_half_a, edge_half_b):
    """
    Return the source face between two neighboring EdgeHalves.

    Prefer fprev/fnext ownership stored on EdgeHalf. Fall back to edge-face
    intersection only when explicit ownership is unavailable.
    """

    edge_a_id = edge_half_a.edge_id
    edge_b_id = edge_half_b.edge_id

    owned_faces = []

    for face_id in (
        getattr(edge_half_a, "fprev", None),
        getattr(edge_half_a, "fnext", None),
        getattr(edge_half_b, "fprev", None),
        getattr(edge_half_b, "fnext", None),
    ):
        if face_id is None:
            continue

        if face_id in bm.edges[edge_a_id].faces and face_id in bm.edges[edge_b_id].faces:
            if face_id not in owned_faces:
                owned_faces.append(face_id)

    if owned_faces:
        return owned_faces[0]

    common_faces = sorted(
        list(
            set(bm.edges[edge_a_id].faces).intersection(
                set(bm.edges[edge_b_id].faces)
            )
        )
    )

    if common_faces:
        return common_faces[0]

    return None


def get_rail_for_face(rails, face_id):
    for rail_data in rails:
        if rail_data.get("face_id") == face_id:
            return rail_data.get("rail")

    return None


def get_rail_endpoint_for_vertex(edge_data, rail, vertex_id, bm=None):
    """
    Return the rail endpoint corresponding to vertex_id.

    Prefer distance to the original vertex when bm is available. This avoids
    silently relying on Maya edge endpoint ordering when a rail was created by
    face-local logic.
    """

    if edge_data is None or rail is None:
        return None

    rail_p0, rail_p1 = rail

    if bm is not None:
        vertex_point = bm.vertices[vertex_id].co_world

        d0 = bxm.distance_sq(vertex_point, rail_p0)
        d1 = bxm.distance_sq(vertex_point, rail_p1)

        if d0 <= d1:
            return rail_p0

        return rail_p1

    edge_v0, edge_v1 = edge_data["vertex_ids"]

    if vertex_id == edge_v0:
        return rail_p0

    if vertex_id == edge_v1:
        return rail_p1

    return None


def get_rail_endpoint_for_edge_face(edge_data_by_id,
                                    rails_by_edge_id,
                                    edge_id,
                                    face_id,
                                    vertex_id,
                                    bm=None):
    edge_data = edge_data_by_id.get(edge_id)
    rail = get_rail_for_face(
        rails=rails_by_edge_id.get(edge_id, []),
        face_id=face_id
    )

    return get_rail_endpoint_for_vertex(
        edge_data=edge_data,
        rail=rail,
        vertex_id=vertex_id,
        bm=bm
    )


def get_other_vertex_point_on_edge(bm, edge_id, vertex_id):
    edge = bm.edges[edge_id]
    other_vertex_id = edge.other_vertex(vertex_id)

    if other_vertex_id is None:
        return None

    return bm.vertices[other_vertex_id].co_world


def slide_point_on_edge_from_vertex(bm, vertex_id, edge_id, distance):
    other_point = get_other_vertex_point_on_edge(
        bm=bm,
        edge_id=edge_id,
        vertex_id=vertex_id
    )

    if other_point is None:
        return None

    return BX_offset.slide_distance_on_edge(
        vertex_position=bm.vertices[vertex_id].co_world,
        other_vertex_position=other_point,
        distance=distance
    )


def solve_selected_selected_meet(bm,
                                  vertex_id,
                                  previous_edge_id,
                                  current_edge_id,
                                  face_id,
                                  edge_data_by_id,
                                  rails_by_edge_id):
    """
    Build the BoundVert between two beveled EdgeHalves on the same face.

    This is the generalized version of all former selected-selected miter
    points. It uses the two offset rails on the shared face.
    """

    previous_rail = get_rail_for_face(
        rails=rails_by_edge_id.get(previous_edge_id, []),
        face_id=face_id
    )

    current_rail = get_rail_for_face(
        rails=rails_by_edge_id.get(current_edge_id, []),
        face_id=face_id
    )

    if previous_rail is None or current_rail is None:
        return None

    return bxm.line_line_intersection_midpoint(
        previous_rail[0],
        previous_rail[1],
        current_rail[0],
        current_rail[1]
    )


def solve_selected_unselected_meet(bm,
                                    vertex_id,
                                    selected_edge_id,
                                    support_edge_id,
                                    face_id,
                                    edge_data_by_id,
                                    rails_by_edge_id):
    """
    Build the BoundVert between a beveled EdgeHalf and an unbeveled support
    EdgeHalf.

    This is the BoundVert-ring replacement for terminal-side special cases.
    It uses the concrete source face normal, not an averaged vertex normal.
    """

    selected_point = get_rail_endpoint_for_edge_face(
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id,
        edge_id=selected_edge_id,
        face_id=face_id,
        vertex_id=vertex_id,
        bm=bm
    )

    if selected_point is None:
        return None

    vertex_point = bm.vertices[vertex_id].co_world
    selected_other = get_other_vertex_point_on_edge(
        bm=bm,
        edge_id=selected_edge_id,
        vertex_id=vertex_id
    )
    support_other = get_other_vertex_point_on_edge(
        bm=bm,
        edge_id=support_edge_id,
        vertex_id=vertex_id
    )

    if selected_other is None or support_other is None:
        return selected_point

    width = bxm.distance(vertex_point, selected_point)
    if face_id is None or face_id not in bm.faces:
        return selected_point

    face_normal = bm.faces[face_id].normal_world

    # Try the direct Blender-like meet on the concrete face first.
    result = BX_offset.offset_meet_edge(
        vertex_position=vertex_point,
        edge_a_other_position=support_other,
        edge_b_other_position=selected_other,
        offset_a_right=0.0,
        offset_b_left=width,
        vertex_normal=face_normal
    )

    if result.get("ok", False) and result.get("point") is not None:
        return result.get("point")

    # Fall back to the selected rail endpoint. Do not invent topology behavior
    # here; failure means the caller still gets a stable BoundVert on the rail.
    return selected_point

def build_selected_selected_boundvert(bm,
                                      vertex_id,
                                      previous_half,
                                      current_half,
                                      face_id,
                                      edge_data_by_id,
                                      rails_by_edge_id):
    point = solve_selected_selected_meet(
        bm=bm,
        vertex_id=vertex_id,
        previous_edge_id=previous_half.edge_id,
        current_edge_id=current_half.edge_id,
        face_id=face_id,
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id
    )

    if point is None:
        return None

    boundvert = BX_BoundVert(
        boundary_id="BV{0}_BNDV_F{1}_E{2}_E{3}".format(
            vertex_id,
            face_id,
            previous_half.edge_id,
            current_half.edge_id
        ),
        original_vertex_id=vertex_id,
        selected_edge_id=current_half.edge_id,
        face_id=face_id,
        co_world=point,
        edge_before_id=previous_half.edge_id,
        edge_after_id=current_half.edge_id,
        efirst_id=previous_half.edge_id,
        elast_id=current_half.edge_id,
        role=ROLE_SELECTED_SELECTED_MEET
    )

    boundvert.efirst = previous_half
    boundvert.elast = current_half
    boundvert.eon = None
    boundvert.ebev = current_half

    boundvert.selected_edge_face_ids = {
        previous_half.edge_id: face_id,
        current_half.edge_id: face_id
    }

    return boundvert

def estimate_boundvert_width_for_vertex(bm,
                                        vertex_id,
                                        selected_edge_ids,
                                        edge_data_by_id,
                                        rails_by_edge_id):
    """
    Estimate the bevel width at one source vertex from selected-edge rail
    endpoints.

    Blender stores offsets on EdgeHalves. BevelX currently has offset rails,
    so this is the bridge equivalent until offsets are promoted onto EdgeHalf.
    """

    vertex_point = bm.vertices[vertex_id].co_world
    distances = []

    for edge_id in selected_edge_ids:
        edge_data = edge_data_by_id.get(edge_id)

        for rail_data in rails_by_edge_id.get(edge_id, []):
            point = get_rail_endpoint_for_vertex(
                edge_data=edge_data,
                rail=rail_data.get("rail"),
                vertex_id=vertex_id,
                bm=bm
            )

            if point is None:
                continue

            distance = bxm.distance(vertex_point, point)

            if distance > bxm.EPSILON:
                distances.append(distance)

    if not distances:
        return None

    return sum(distances) / float(len(distances))

def build_selected_gap_selected_boundvert_on_edge(bm,
                                                  vertex_id,
                                                  left_selected_half,
                                                  middle_unselected_half,
                                                  right_selected_half,
                                                  edge_data_by_id,
                                                  rails_by_edge_id,
                                                  settings=None):
    """
    Blender-style eon BoundVert.

    This replaces the bad pattern where BevelX creates two different
    BoundVerts on the same support edge, one per adjacent face sector.
    """

    left_face_id = get_face_between_edge_halves(
        bm=bm,
        edge_half_a=left_selected_half,
        edge_half_b=middle_unselected_half
    )

    right_face_id = get_face_between_edge_halves(
        bm=bm,
        edge_half_a=middle_unselected_half,
        edge_half_b=right_selected_half
    )

    width = estimate_boundvert_width_for_vertex(
        bm=bm,
        vertex_id=vertex_id,
        selected_edge_ids=set([
            left_selected_half.edge_id,
            right_selected_half.edge_id
        ]),
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id
    )

    point = solve_selected_gap_selected_on_edge(
        bm=bm,
        vertex_id=vertex_id,
        left_selected_half=left_selected_half,
        middle_unselected_half=middle_unselected_half,
        right_selected_half=right_selected_half,
        left_face_id=left_face_id,
        right_face_id=right_face_id,
        width=width,
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id
    )
    if point is None:
        return None

    boundvert = BX_BoundVert(
        boundary_id="BV{0}_BNDV_GAP_E{1}_ON{2}_E{3}".format(
            vertex_id,
            left_selected_half.edge_id,
            middle_unselected_half.edge_id,
            right_selected_half.edge_id
        ),
        original_vertex_id=vertex_id,
        co_world=point,
        face_id=left_face_id,
        selected_edge_id=None,
        edge_before_id=left_selected_half.edge_id,
        edge_after_id=right_selected_half.edge_id,
        edge_on_id=middle_unselected_half.edge_id,
        efirst_id=left_selected_half.edge_id,
        elast_id=right_selected_half.edge_id,
        role=ROLE_SUPPORT
    )
    # Compatibility / Blender-equivalent ownership fields.
    boundvert.efirst = left_selected_half
    boundvert.elast = right_selected_half
    boundvert.eon = middle_unselected_half
    boundvert.ebev = None
    boundvert.selected_edge_face_ids = {
        left_selected_half.edge_id: left_face_id,
        right_selected_half.edge_id: right_face_id
    }


    return boundvert

def solve_selected_gap_selected_on_edge(bm,
                                        vertex_id,
                                        left_selected_half,
                                        middle_unselected_half,
                                        right_selected_half,
                                        left_face_id,
                                        right_face_id,
                                        width,
                                        edge_data_by_id,
                                        rails_by_edge_id):
    """
    Approximate Blender's offset_on_edge_between for segments == 1.

    The result is one point on middle_unselected_half.edge_id.
    """

    vertex_point = bm.vertices[vertex_id].co_world

    left_meet = solve_selected_unselected_meet(
        bm=bm,
        vertex_id=vertex_id,
        selected_edge_id=left_selected_half.edge_id,
        support_edge_id=middle_unselected_half.edge_id,
        face_id=left_face_id,
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id
    )

    right_meet = solve_selected_unselected_meet(
        bm=bm,
        vertex_id=vertex_id,
        selected_edge_id=right_selected_half.edge_id,
        support_edge_id=middle_unselected_half.edge_id,
        face_id=right_face_id,
        edge_data_by_id=edge_data_by_id,
        rails_by_edge_id=rails_by_edge_id
    )

    if left_meet is not None and right_meet is not None:
        point = bxm.midpoint(left_meet, right_meet)

    elif left_meet is not None:
        point = left_meet

    elif right_meet is not None:
        point = right_meet

    else:
        if width is None:
            width = 0.0

        point = slide_point_on_edge_from_vertex(
            bm=bm,
            vertex_id=vertex_id,
            edge_id=middle_unselected_half.edge_id,
            distance=width
        )

    if point is None:
        return None

    return clamp_point_to_edge_from_vertex(
        bm=bm,
        vertex_id=vertex_id,
        edge_id=middle_unselected_half.edge_id,
        point=point
    )

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

def build_boundvert_ring_for_vertex(bm,
                                    bevel_vertex,
                                    edge_data_by_id,
                                    rails_by_edge_id,
                                    settings=None):
    """
    Blender-aligned BoundVert ring builder.

    Important:
        For selected_count > 1, do not create one BoundVert per neighboring
        EdgeHalf face sector. Walk from beveled edge to next beveled edge and
        build one BoundVert per beveled-edge gap.

    Implementation note:
        Do not use edge_half.next here. In BevelX, .next may not be a linked
        EdgeHalf object yet. Use the ordered edge_halves list directly.
    """

    vertex_id = bevel_vertex.vertex_id
    edge_halves = get_edge_half_ring(bevel_vertex)
    selected_edge_ids = get_selected_edge_ids(bevel_vertex)

    if not edge_halves:
        return []

    mark_beveled_edge_halves(
        edge_halves=edge_halves,
        selected_edge_ids=selected_edge_ids
    )

    selected_indices = [
        index
        for index, edge_half in enumerate(edge_halves)
        if getattr(edge_half, "is_bev", False)
    ]

    if not selected_indices:
        return []

    # Blender terminal-edge special case.
    if len(selected_indices) == 1:
        selected_half = edge_halves[selected_indices[0]]

        return build_terminal_boundvert_ring_for_vertex(
            bm=bm,
            vertex_id=vertex_id,
            edge_halves=edge_halves,
            selected_half=selected_half,
            edge_data_by_id=edge_data_by_id,
            rails_by_edge_id=rails_by_edge_id,
            settings=settings
        )

    boundverts = []
    count = len(edge_halves)

    # Multi-selected case:
    # Build one BoundVert per beveled-edge gap, not one per adjacent face sector.
    start_index = selected_indices[0]
    current_index = start_index

    safety = 0

    while True:
        current_selected = edge_halves[current_index]

        gap_halves = []
        walk_index = (current_index + 1) % count

        while not getattr(edge_halves[walk_index], "is_bev", False):
            gap_halves.append(edge_halves[walk_index])
            walk_index = (walk_index + 1) % count

            safety += 1

            if safety > count * 3:
                BX_log.warn(
                    "BOUNDVERT ring build aborted at vertex {0}: cyclic walk safety hit, current_edge={1}, ring={2}".format(
                        vertex_id,
                        getattr(current_selected, "edge_id", None),
                        [
                            getattr(edge_half, "edge_id", None)
                            for edge_half in edge_halves
                        ]
                    ),
                    channel="summary"
                )
                break

        next_index = walk_index
        next_selected = edge_halves[next_index]

        if len(gap_halves) == 0:
            face_id = get_face_between_edge_halves(
                bm=bm,
                edge_half_a=current_selected,
                edge_half_b=next_selected
            )

            boundvert = build_selected_selected_boundvert(
                bm=bm,
                vertex_id=vertex_id,
                previous_half=current_selected,
                current_half=next_selected,
                face_id=face_id,
                edge_data_by_id=edge_data_by_id,
                rails_by_edge_id=rails_by_edge_id
            )

        elif len(gap_halves) == 1:
            middle_half = gap_halves[0]

            boundvert = build_selected_gap_selected_boundvert_on_edge(
                bm=bm,
                vertex_id=vertex_id,
                left_selected_half=current_selected,
                middle_unselected_half=middle_half,
                right_selected_half=next_selected,
                edge_data_by_id=edge_data_by_id,
                rails_by_edge_id=rails_by_edge_id,
                settings=settings
            )

        else:
            boundvert = build_selected_gap_selected_boundvert_for_run(
                bm=bm,
                vertex_id=vertex_id,
                left_selected_half=current_selected,
                gap_halves=gap_halves,
                right_selected_half=next_selected,
                edge_data_by_id=edge_data_by_id,
                rails_by_edge_id=rails_by_edge_id,
                settings=settings
            )

        if boundvert is not None:
            boundverts.append(boundvert)

        current_index = next_index

        if current_index == start_index:
            break

    link_boundverts_cyclic(boundverts)

    BX_log.warn(
        "BOUNDVERT ring built for vertex {0}: incident={1}, selected={2}, count={3}, ring={4}".format(
            vertex_id,
            len(edge_halves),
            len(selected_indices),
            len(boundverts),
            [
                getattr(edge_half, "edge_id", None)
                for edge_half in edge_halves
            ]
        ),
        channel="summary"
    )

    return boundverts

def build_boundvert_rings_for_selection(bm,
                                        edges_data,
                                        rails_by_edge_id,
                                        bevel_vertices,
                                        settings=None):
    """
    Build BoundVert rings for all affected vertices in the current selection.

    This is the new subsystem entry point. Keep it parallel to the legacy
    build_boundaries_for_selection() until transaction support is migrated.
    """

    edge_data_by_id = {
        edge_data["edge_id"]: edge_data
        for edge_data in edges_data
    }

    boundverts_by_vertex = {}

    for vertex_id, bevel_vertex in bevel_vertices.items():
        boundverts_by_vertex[vertex_id] = build_boundvert_ring_for_vertex(
            bm=bm,
            bevel_vertex=bevel_vertex,
            edge_data_by_id=edge_data_by_id,
            rails_by_edge_id=rails_by_edge_id,
            settings=settings
        )

    return boundverts_by_vertex


def build_boundaries_for_selection(bm,
                                   edges_data,
                                   rails_by_edge_id,
                                   bevel_vertices,
                                   settings=None):
    """
    Compatibility entry point replacing BX_boundary.build_boundaries_for_selection.

    This must only return BOUNDVERT objects.
    """
    return build_boundvert_rings_for_selection(
        bm=bm,
        edges_data=edges_data,
        rails_by_edge_id=rails_by_edge_id,
        bevel_vertices=bevel_vertices,
        settings=settings
    )