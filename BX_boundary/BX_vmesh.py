# BX_vmesh.py

from __future__ import print_function

from BX_math import BX_math as bxm
from BX_profile import BX_log


def build_corner_3_tri_cap_boundary_for_vertex(bm,
                                                bevel_vertex,
                                                edge_data_by_id,
                                                rails_by_edge_id,
                                                boundary_class,
                                                link_function):
    """
    Build a simple triangular cap boundary for a vertex touched by exactly
    three selected edges.

    Args:
        bm:
            BX_BMesh.

        bevel_vertex:
            BX_BevelVertex with selected_count == 3.

        edge_data_by_id:
            Dict edge_id -> edge_data.

        rails_by_edge_id:
            Dict edge_id -> rails.

        boundary_class:
            Usually BX_BoundaryVertex.

        link_function:
            Usually link_boundary_vertices_cyclic.

    Returns:
        [BX_BoundaryVertex, ...]

    Strategy:
        At a cube-like selected corner, each cap face is shared by exactly
        two selected edges.

        Example selected edges around vertex 3:
            e1 faces: [0, 1]
            e5 faces: [0, 4]
            e7 faces: [1, 4]

        Cap faces:
            face 0 -> intersection of e1 rail on face 0 and e5 rail on face 0
            face 1 -> intersection of e1 rail on face 1 and e7 rail on face 1
            face 4 -> intersection of e5 rail on face 4 and e7 rail on face 4

        These three points become the F_VERT triangular cap.
    """

    vertex_id = bevel_vertex.vertex_id
    selected_edge_ids = list(bevel_vertex.selected_edges)

    if len(selected_edge_ids) != 3:
        BX_log.warn("TRI_CAP failed at vertex {0}: expected 3 selected edges, got {1}.".format(
                vertex_id, len(selected_edge_ids)), channel="caps")
        return []

    cap_face_ids = get_cap_faces_for_three_edges(
        bm=bm,
        vertex_id=vertex_id,
        selected_edge_ids=selected_edge_ids
    )

    if len(cap_face_ids) != 3:
        BX_log.warn("TRI_CAP failed at vertex {0}: expected 3 cap faces, got {1}: {2}".format(
                vertex_id, len(cap_face_ids), cap_face_ids), channel="caps")
        return []

    boundary_vertices = []

    for face_id in cap_face_ids:
        edge_ids_for_face = get_selected_edges_using_face(
            bm=bm,
            selected_edge_ids=selected_edge_ids,
            face_id=face_id
        )

        if len(edge_ids_for_face) != 2:
            BX_log.warn("TRI_CAP failed at vertex {0}: face {1} has selected edges {2}.".format(
                    vertex_id, face_id, edge_ids_for_face), channel="caps")
            return []

        edge_a_id = edge_ids_for_face[0]
        edge_b_id = edge_ids_for_face[1]

        rail_a = get_rail_for_face(
            rails=rails_by_edge_id.get(edge_a_id, []),
            face_id=face_id
        )

        rail_b = get_rail_for_face(
            rails=rails_by_edge_id.get(edge_b_id, []),
            face_id=face_id
        )

        if rail_a is None or rail_b is None:
            BX_log.warn("TRI_CAP failed at vertex {0}: missing rail for face {1}.".format(
                    vertex_id, face_id), channel="caps")
            return []

        point = bxm.line_line_intersection_midpoint(
            rail_a[0],
            rail_a[1],
            rail_b[0],
            rail_b[1]
        )

        boundary_vertex = boundary_class(
            boundary_id="BV{0}_TRICAP_F{1}".format(vertex_id, face_id),
            original_vertex_id=vertex_id,
            selected_edge_id=edge_a_id,
            face_id=face_id,
            co_world=point,
            source="TRI_CAP"
        )

        boundary_vertices.append(boundary_vertex)

    boundary_vertices = orient_tri_cap_boundaries(
        bm=bm,
        boundary_vertices=boundary_vertices,
        vertex_id=vertex_id
    )

    link_function(boundary_vertices)

    return boundary_vertices


def get_cap_faces_for_three_edges(bm, vertex_id, selected_edge_ids):
    """
    Get faces around vertex_id that are used by exactly two selected edges.

    For a cube corner with three selected edges, this should return three faces.
    """

    candidate_faces = list(bm.vertices[vertex_id].faces)
    cap_faces = []

    for face_id in candidate_faces:
        edge_ids_for_face = get_selected_edges_using_face(
            bm=bm,
            selected_edge_ids=selected_edge_ids,
            face_id=face_id
        )

        if len(edge_ids_for_face) == 2:
            cap_faces.append(face_id)

    return sorted(cap_faces)


def get_selected_edges_using_face(bm, selected_edge_ids, face_id):
    """
    Return selected edges that use face_id.
    """

    result = []

    for edge_id in selected_edge_ids:
        if face_id in bm.edges[edge_id].faces:
            result.append(edge_id)

    return result

def get_boundvert_point_from_two_face_rails(prev_rail,
                                            current_rail,
                                            fallback_prev_point,
                                            fallback_current_point):
    """
    Return the BoundVert point between two beveled edges on one shared face.

    Blender-lane behavior:
        The boundary point between two beveled edges is the meet/intersection
        of the two offset rails on the shared face.

    Do not average the rail endpoints as the primary behavior.
    Averaging pulls the BoundVert inward and causes connected F_EDGE faces
    to look non-straight.
    """

    if prev_rail is None or current_rail is None:
        return bxm.midpoint(
            fallback_prev_point,
            fallback_current_point
        )

    point = bxm.line_line_intersection_midpoint(
        prev_rail[0],
        prev_rail[1],
        current_rail[0],
        current_rail[1]
    )

    if point is None:
        return bxm.midpoint(
            fallback_prev_point,
            fallback_current_point
        )

    return point

def get_rail_for_face(rails, face_id):
    """
    Return rail tuple for face_id.
    """

    for rail_data in rails:
        if rail_data["face_id"] == face_id:
            return rail_data["rail"]

    return None

def orient_tri_cap_boundaries(bm, boundary_vertices, vertex_id):
    """
    Return tri-cap boundary vertices in an orientation roughly matching
    the average normal of the original faces around the bevel vertex.

    This helps F_VERT draw/apply with stable winding.
    """

    if len(boundary_vertices) != 3:
        return boundary_vertices

    expected_normal = average_face_normal_for_boundaries(
        bm=bm,
        boundary_vertices=boundary_vertices
    )

    points = [
        boundary_vertices[0].co_world,
        boundary_vertices[1].co_world,
        boundary_vertices[2].co_world
    ]

    normal = bxm.safe_normal_from_points(
        points[0],
        points[1],
        points[2]
    )

    if bxm.dot(normal, expected_normal) < 0.0:
        boundary_vertices = [
            boundary_vertices[0],
            boundary_vertices[2],
            boundary_vertices[1]
        ]

    return boundary_vertices


def average_face_normal_for_boundaries(bm, boundary_vertices):
    """
    Average normals of faces associated with boundary vertices.
    """

    normal = [0.0, 0.0, 0.0]

    for boundary_vertex in boundary_vertices:
        face_id = boundary_vertex.face_id
        face_normal = bm.faces[face_id].normal_world

        normal = bxm.add(normal, face_normal)

    return bxm.normalize(normal)

def build_pole_n_boundary_for_vertex(bm,
                                     bevel_vertex,
                                     edge_data_by_id,
                                     rails_by_edge_id,
                                     boundary_class,
                                     link_function):
    """
    Build a first simple POLE_N boundary for selected_count >= 4.

    First target:
        - segments == 1
        - all selected edges around the pole are adjacent in the edge ring
        - one boundary vertex per face sector between consecutive selected edges

    This gives the transaction layer a clean ordered boundary ring that can be
    turned into one F_VERT polygon.
    """

    vertex_id = bevel_vertex.vertex_id
    selected_edges = list(bevel_vertex.selected_edges)
    selected_edge_set = set(selected_edges)
    edge_halves = list(getattr(bevel_vertex, "edge_halves", []))

    if len(selected_edges) < 4:
        return []

    if not edge_halves:
        BX_log.warn("POLE_N skipped at vertex {0}: missing edge_half order.".format(
                vertex_id), channel="caps")
        return []

    ordered_selected_halves = []

    for edge_half in edge_halves:
        if edge_half.edge_id in selected_edge_set:
            ordered_selected_halves.append(edge_half)
        else:
            # First simple pole version: all edges around the pole must be selected.
            BX_log.debug("POLE_N skipped at vertex {0}: found unselected incident edge {1}.".format(
                    vertex_id, edge_half.edge_id), channel="caps")
            return []

    if len(ordered_selected_halves) != len(edge_halves):
        BX_log.debug("POLE_N skipped at vertex {0}: selected/incident mismatch.".format(
                vertex_id), channel="caps")
        return []

    boundary_list = []
    count = len(ordered_selected_halves)

    for i in range(count):
        prev_half = ordered_selected_halves[(i - 1) % count]
        current_half = ordered_selected_halves[i]

        prev_edge_id = prev_half.edge_id
        current_edge_id = current_half.edge_id

        prev_edge = bm.edges[prev_edge_id]
        current_edge = bm.edges[current_edge_id]

        common_faces = sorted(list(set(prev_edge.faces).intersection(set(current_edge.faces))))

        if not common_faces:
            BX_log.warn("POLE_N skipped at vertex {0}: edges {1}, {2} share no face.".format(
                    vertex_id, prev_edge_id, current_edge_id), channel="caps")
            return []

        face_id = common_faces[0]

        # Existing get_rail_for_face() returns the rail tuple itself:
        #     (rail_p0, rail_p1)
        # not the rail_data dictionary.
        prev_rail = get_rail_for_face(
            rails=rails_by_edge_id.get(prev_edge_id, []),
            face_id=face_id
        )

        current_rail = get_rail_for_face(
            rails=rails_by_edge_id.get(current_edge_id, []),
            face_id=face_id
        )

        if prev_rail is None or current_rail is None:
            BX_log.warn("POLE_N skipped at vertex {0}: missing rails for face {1}.".format(
                    vertex_id, face_id), channel="caps")
            return []

        prev_point = get_rail_endpoint_for_pole_vertex(
            edge_data=edge_data_by_id.get(prev_edge_id),
            rail=prev_rail,
            vertex_id=vertex_id,
            bm=bm
        )

        current_point = get_rail_endpoint_for_pole_vertex(
            edge_data=edge_data_by_id.get(current_edge_id),
            rail=current_rail,
            vertex_id=vertex_id,
            bm=bm
        )

        if prev_point is None or current_point is None:
            BX_log.warn("POLE_N skipped at vertex {0}: missing rail endpoints on face {1}.".format(
                    vertex_id, face_id), channel="caps")
            return []

        # Blender's BoundVert point:
        # use the intersection / meet of the two offset rails on the shared face.
        # Used to average endpoint but that pulls the pole point inward because for offset 0.1.
        # POLE_N midpoint method takes the two rail endpoints near the original vertex:
        # (0.1, 0.0) and (0.0, 0.1) => (0.05, 0.05) which is inside the original corner.
        point = get_boundvert_point_from_two_face_rails(
            prev_rail=prev_rail,
            current_rail=current_rail,
            fallback_prev_point=prev_point,
            fallback_current_point=current_point
        )

        boundary_vertex = boundary_class(
            boundary_id="BV{0}_POLE_N_F{1}".format(vertex_id, face_id),
            original_vertex_id=vertex_id,
            selected_edge_id=current_edge_id,
            face_id=face_id,
            co_world=point,
            source="POLE_N"
        )

        boundary_list.append(boundary_vertex)

    link_function(boundary_list)

    BX_log.debug("POLE_N boundary built for vertex {0}: count={1}".format(
            vertex_id, len(boundary_list)), channel="caps")

    return boundary_list

def get_rail_endpoint_for_pole_vertex(edge_data, rail, vertex_id, bm=None):
    """
    Return the endpoint of a rail tuple that corresponds to vertex_id.

    Prefer distance to the original vertex when bm is available.
    This avoids relying on Maya edge/rail endpoint ordering.
    """

    if rail is None:
        return None

    rail_p0, rail_p1 = rail

    if bm is not None:
        vertex_point = bm.vertices[vertex_id].co_world

        d0 = bxm.distance_sq(vertex_point, rail_p0)
        d1 = bxm.distance_sq(vertex_point, rail_p1)

        if d0 <= d1:
            return rail_p0

        return rail_p1

    if edge_data is None:
        return None

    edge_v0, edge_v1 = edge_data["vertex_ids"]

    if vertex_id == edge_v0:
        return rail_p0

    if vertex_id == edge_v1:
        return rail_p1

    return None