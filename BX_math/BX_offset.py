# BX_offset.py
# BevelX offset math.
#
# This module is Maya-independent.
# It works with points/vectors only.
#
# The first target is not full bevel solving.
# The first target is:
#
#   selected edge
#   adjacent face plane
#   offset points / rails
#
# Once this works, BX_boundary can consume it.

from __future__ import print_function

import math

from BX_math import BX_math as bxm


# -----------------------------------------------------------------------------
# Basic sliding
# -----------------------------------------------------------------------------

def slide_distance_on_edge(vertex_position, other_vertex_position, distance):
    """
    Move from vertex_position toward other_vertex_position by distance.

    Equivalent idea to Blender's slide_dist():
        - compute direction from v to other
        - clamp distance if longer than edge
        - return v + direction * distance
    """

    direction = bxm.sub(other_vertex_position, vertex_position)
    edge_length = bxm.length(direction)

    if edge_length < bxm.EPSILON:
        return list(vertex_position)

    if distance > edge_length:
        distance = max(0.0, edge_length - (50.0 * bxm.EPSILON))

    direction = bxm.div(direction, edge_length)
    return bxm.add(vertex_position, bxm.mul(direction, distance))


def slide_percent_on_edge(vertex_position, other_vertex_position, percent):
    """
    Move from vertex_position toward other_vertex_position by percent.

    percent:
        0.0   = original vertex
        50.0  = halfway
        100.0 = other endpoint
    """

    t = percent / 100.0
    t = bxm.clamp(t, 0.0, 1.0)
    return bxm.lerp(vertex_position, other_vertex_position, t)


# -----------------------------------------------------------------------------
# Plane offset
# -----------------------------------------------------------------------------

def offset_in_plane(vertex_position,
                    other_vertex_position,
                    plane_normal,
                    offset_distance,
                    left=True):
    """
    Offset a point from an edge inside a plane.

    Args:
        vertex_position:
            The original vertex.

        other_vertex_position:
            The other endpoint of the edge.

        plane_normal:
            The plane normal.

        offset_distance:
            Offset amount.

        left:
            If True, use cross(edge_dir, plane_normal).
            If False, use cross(plane_normal, edge_dir).

    This mirrors Blender's offset_in_plane() behavior.
    """

    edge_dir = bxm.sub(other_vertex_position, vertex_position)
    edge_dir = bxm.normalize(edge_dir)

    if bxm.is_zero(edge_dir):
        return list(vertex_position)

    normal = bxm.normalize(plane_normal)

    if bxm.is_zero(normal):
        # Fallback plane normal if no plane exists.
        # Pick an axis that is not too aligned with edge_dir.
        if abs(edge_dir[0]) < abs(edge_dir[1]):
            normal = [1.0, 0.0, 0.0]
        else:
            normal = [0.0, 1.0, 0.0]

    if left:
        offset_dir = bxm.cross(edge_dir, normal)
    else:
        offset_dir = bxm.cross(normal, edge_dir)

    offset_dir = bxm.normalize(offset_dir)

    if bxm.is_zero(offset_dir):
        return list(vertex_position)

    return bxm.add(vertex_position, bxm.mul(offset_dir, offset_distance))


# -----------------------------------------------------------------------------
# Offset meet helpers
# -----------------------------------------------------------------------------

def offset_meet_edge(vertex_position,
                     edge_a_other_position,
                     edge_b_other_position,
                     offset_a_right,
                     offset_b_left,
                     vertex_normal):
    """
    Calculate meeting point between two edges when one side may have zero offset.

    This is the simplified BevelX equivalent of Blender's offset_meet_edge().

    Returns:
        {
            "ok": bool,
            "point": [x, y, z] or None,
            "angle": radians
        }

    Notes:
        - edge A and edge B meet at vertex_position.
        - edge direction A is vertex -> edge_a_other_position.
        - edge direction B is vertex -> edge_b_other_position.
        - If the angle is reflex or close to 0/180, return ok False.
    """

    dir_a = bxm.normalize(bxm.sub(edge_a_other_position, vertex_position))
    dir_b = bxm.normalize(bxm.sub(edge_b_other_position, vertex_position))

    if bxm.is_zero(dir_a) or bxm.is_zero(dir_b):
        return {
            "ok": False,
            "point": None,
            "angle": 0.0,
        }

    angle = bxm.angle_between(dir_a, dir_b)

    if abs(angle) < bxm.EPSILON:
        return {
            "ok": False,
            "point": None,
            "angle": 0.0,
        }

    cross_ab = bxm.cross(dir_a, dir_b)

    # Reflex angle test, same conceptual test as Blender:
    # if cross(dir_a, dir_b) points away from vertex normal, angle is reflex.
    if bxm.dot(cross_ab, vertex_normal) < 0.0:
        angle = (2.0 * math.pi) - angle
        return {
            "ok": False,
            "point": None,
            "angle": angle,
        }

    if abs(angle - math.pi) < bxm.EPSILON:
        return {
            "ok": False,
            "point": None,
            "angle": angle,
        }

    sin_angle = math.sin(angle)

    if abs(sin_angle) < bxm.EPSILON:
        return {
            "ok": False,
            "point": None,
            "angle": angle,
        }

    if abs(offset_a_right) <= bxm.EPSILON:
        point = bxm.add(vertex_position, bxm.mul(dir_a, offset_b_left / sin_angle))
    else:
        point = bxm.add(vertex_position, bxm.mul(dir_b, offset_a_right / sin_angle))

    return {
        "ok": True,
        "point": point,
        "angle": angle,
    }


def offset_on_edge_between(vertex_position,
                           edge_a_other_position,
                           middle_edge_other_position,
                           edge_b_other_position,
                           offset_a_right,
                           offset_b_left,
                           vertex_normal):
    """
    Calculate a compromise point on an unselected middle edge between two beveled edges.

    This is our first simplified version of Blender's offset_on_edge_between().
    """

    meet_a = offset_meet_edge(
        vertex_position,
        edge_a_other_position,
        middle_edge_other_position,
        offset_a_right,
        0.0,
        vertex_normal,
    )

    meet_b = offset_meet_edge(
        vertex_position,
        middle_edge_other_position,
        edge_b_other_position,
        0.0,
        offset_b_left,
        vertex_normal,
    )

    if meet_a["ok"] and meet_b["ok"]:
        return {
            "ok": True,
            "point": bxm.midpoint(meet_a["point"], meet_b["point"]),
            "source": "average",
        }

    if meet_a["ok"]:
        return {
            "ok": True,
            "point": meet_a["point"],
            "source": "left",
        }

    if meet_b["ok"]:
        return {
            "ok": True,
            "point": meet_b["point"],
            "source": "right",
        }

    # Fallback: slide along middle edge by average offset.
    fallback_distance = 0.5 * (offset_a_right + offset_b_left)
    point = slide_distance_on_edge(
        vertex_position,
        middle_edge_other_position,
        fallback_distance,
    )

    return {
        "ok": False,
        "point": point,
        "source": "fallback_slide",
    }


def offset_rail_on_face(edge_start,
                        edge_end,
                        face_normal,
                        offset_distance,
                        left=True):
    """
    Return two points representing one offset rail for an edge on a face plane.
    """

    p0 = offset_in_plane(edge_start, edge_end, face_normal, offset_distance, left=left)
    p1 = offset_in_plane(edge_end, edge_start, face_normal, offset_distance, left=not left)

    return p0, p1

def offset_rail_on_face_towards_point(edge_start,
                                      edge_end,
                                      face_normal,
                                      offset_distance,
                                      target_point):
    """
    Return the offset rail that points toward target_point.

    Usually target_point should be the face center.
    This chooses between left=True and left=False automatically.
    """

    rail_left = offset_rail_on_face(
        edge_start,
        edge_end,
        face_normal,
        offset_distance,
        left=True
    )

    rail_right = offset_rail_on_face(
        edge_start,
        edge_end,
        face_normal,
        offset_distance,
        left=False
    )

    edge_mid = bxm.midpoint(edge_start, edge_end)
    left_mid = bxm.midpoint(rail_left[0], rail_left[1])
    right_mid = bxm.midpoint(rail_right[0], rail_right[1])

    target_dir = bxm.sub(target_point, edge_mid)
    left_dir = bxm.sub(left_mid, edge_mid)
    right_dir = bxm.sub(right_mid, edge_mid)

    left_score = bxm.dot(bxm.normalize(left_dir), bxm.normalize(target_dir))
    right_score = bxm.dot(bxm.normalize(right_dir), bxm.normalize(target_dir))

    if left_score >= right_score:
        return {
            "rail": rail_left,
            "side": "LEFT",
            "score": left_score,
        }

    return {
        "rail": rail_right,
        "side": "RIGHT",
        "score": right_score,
    }