# BX_rebuild.py

from __future__ import print_function

from BX_math import BX_math as bxm


# -----------------------------------------------------------------------------
# Affected face rebuilding
# -----------------------------------------------------------------------------

def rotate_face_so_edge_is_not_wrapped(face_vertices, edge_v0, edge_v1):
    """
    Rotate face vertex order so the selected edge appears as a normal pair.

    This avoids special cases where the selected edge is between the last and
    first vertices of the polygon list.
    """

    count = len(face_vertices)

    for i in range(count):
        current_v = face_vertices[i]
        next_v = face_vertices[(i + 1) % count]

        matches_forward = current_v == edge_v0 and next_v == edge_v1
        matches_reverse = current_v == edge_v1 and next_v == edge_v0

        if matches_forward or matches_reverse:
            if i == count - 1:
                return face_vertices[i:] + face_vertices[:i]

            return list(face_vertices)

    return None


# -----------------------------------------------------------------------------
# Bevel face construction
# -----------------------------------------------------------------------------
def get_expected_bevel_normal(rails):
    """
    Estimate expected bevel face normal from adjacent face normals.

    For a simple edge bevel, the new bevel face should point between the two
    adjacent face normals.
    """

    normal = [0.0, 0.0, 0.0]

    for rail_data in rails:
        rail_normal = rail_data.get("normal")

        if rail_normal is None:
            continue

        normal = bxm.add(normal, rail_normal)

    if bxm.is_zero(normal):
        return [0.0, 0.0, 0.0]

    return bxm.normalize(normal)


def orient_face_indices_to_normal(face_indices, points, expected_normal):
    """
    Flip face winding if face normal points opposite expected_normal.
    """

    if not face_indices or len(face_indices) < 3:
        return face_indices

    expected_normal = bxm.normalize(expected_normal)

    if bxm.is_zero(expected_normal):
        return face_indices

    face_points = [
        points[index]
        for index in face_indices
    ]

    current_normal = calculate_polygon_normal(face_points)

    if bxm.is_zero(current_normal):
        return face_indices

    if bxm.dot(current_normal, expected_normal) < 0.0:
        return [face_indices[0]] + list(reversed(face_indices[1:]))

    return face_indices


def calculate_polygon_normal(points):
    """
    Calculate polygon normal from the first non-collinear triangle.
    """

    if len(points) < 3:
        return [0.0, 0.0, 0.0]

    p0 = points[0]

    for i in range(1, len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]

        edge_a = bxm.sub(p1, p0)
        edge_b = bxm.sub(p2, p0)

        normal = bxm.cross(edge_a, edge_b)

        if not bxm.is_zero(normal):
            return bxm.normalize(normal)

    return [0.0, 0.0, 0.0]