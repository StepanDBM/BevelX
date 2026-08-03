# BX_vmesh.py
# BevelX simple vertex-mesh / corner cap builders.
#
# Current milestone:
#   - M_TRI_CAP for selected_count == 3
#   - segments = 1
#   - cube-like / manifold corner
#
# This is the first real equivalent of Blender-style VMesh/corner handling.
# It is intentionally small:
#   selected_count == 3 -> three cap boundary points -> F_VERT triangle later.

from __future__ import print_function

from BX_math import BX_math as bxm


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
        print("[BevelX] TRI_CAP failed at vertex {0}: expected 3 selected edges, got {1}.".format(
            vertex_id,
            len(selected_edge_ids)
        ))
        return []

    cap_face_ids = get_cap_faces_for_three_edges(
        bm=bm,
        vertex_id=vertex_id,
        selected_edge_ids=selected_edge_ids
    )

    if len(cap_face_ids) != 3:
        print("[BevelX] TRI_CAP failed at vertex {0}: expected 3 cap faces, got {1}: {2}".format(
            vertex_id,
            len(cap_face_ids),
            cap_face_ids
        ))
        return []

    boundary_vertices = []

    for face_id in cap_face_ids:
        edge_ids_for_face = get_selected_edges_using_face(
            bm=bm,
            selected_edge_ids=selected_edge_ids,
            face_id=face_id
        )

        if len(edge_ids_for_face) != 2:
            print("[BevelX] TRI_CAP failed at vertex {0}: face {1} has selected edges {2}.".format(
                vertex_id,
                face_id,
                edge_ids_for_face
            ))
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
            print("[BevelX] TRI_CAP failed at vertex {0}: missing rail for face {1}.".format(
                vertex_id,
                face_id
            ))
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