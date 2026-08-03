# BX_math.py
# BevelX math helpers.
#
# This module must stay Maya-independent.
# It should work with plain tuples/lists: (x, y, z).

from __future__ import print_function

import math


EPSILON = 1.0e-6
EPSILON_SQ = 1.0e-12
EPSILON_BIG = 1.0e-4
EPSILON_ANGLE = math.radians(2.0)
SMALL_ANGLE = math.radians(10.0)


# -----------------------------------------------------------------------------
# Basic vector operations
# -----------------------------------------------------------------------------

def vec3(x=0.0, y=0.0, z=0.0):
    return [float(x), float(y), float(z)]


def add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def mul(a, scalar):
    return [a[0] * scalar, a[1] * scalar, a[2] * scalar]


def div(a, scalar):
    if abs(scalar) < EPSILON:
        return [0.0, 0.0, 0.0]
    return [a[0] / scalar, a[1] / scalar, a[2] / scalar]


def dot(a, b):
    return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])


def cross(a, b):
    return [
        (a[1] * b[2]) - (a[2] * b[1]),
        (a[2] * b[0]) - (a[0] * b[2]),
        (a[0] * b[1]) - (a[1] * b[0]),
    ]


def length_sq(a):
    return dot(a, a)


def length(a):
    return math.sqrt(length_sq(a))


def normalize(a):
    l = length(a)
    if l < EPSILON:
        return [0.0, 0.0, 0.0]
    return div(a, l)


def distance(a, b):
    return length(sub(a, b))


def distance_sq(a, b):
    return length_sq(sub(a, b))


def lerp(a, b, t):
    return [
        a[0] + ((b[0] - a[0]) * t),
        a[1] + ((b[1] - a[1]) * t),
        a[2] + ((b[2] - a[2]) * t),
    ]


def midpoint(a, b):
    return lerp(a, b, 0.5)


def is_zero(a, eps=EPSILON):
    return length_sq(a) <= eps * eps


def almost_equal(a, b, eps=EPSILON):
    return abs(a - b) <= eps


def clamp(value, low, high):
    return max(low, min(high, value))


# -----------------------------------------------------------------------------
# Angles
# -----------------------------------------------------------------------------

def angle_between(a, b):
    """
    Unsigned angle between vectors in radians.
    Returns a value in [0, pi].
    """

    an = normalize(a)
    bn = normalize(b)

    if is_zero(an) or is_zero(bn):
        return 0.0

    d = clamp(dot(an, bn), -1.0, 1.0)
    return math.acos(d)


def nearly_parallel(a, b, angle_eps=EPSILON_ANGLE):
    """
    True if vectors are almost parallel or anti-parallel.
    Mirrors Blender's near-parallel idea.
    """

    ang = angle_between(a, b)
    return abs(ang) < angle_eps or abs(ang - math.pi) < angle_eps


def signed_angle_around_normal(a, b, normal):
    """
    Signed angle from vector a to vector b around normal.
    Positive means cross(a, b) points along normal.
    """

    an = normalize(a)
    bn = normalize(b)
    nn = normalize(normal)

    unsigned = angle_between(an, bn)
    c = cross(an, bn)

    if dot(c, nn) < 0.0:
        return -unsigned

    return unsigned


def angle_kind(a, b, normal):
    """
    Classify angle from a to b around normal.

    Returns:
        -1 = smaller than 180
         0 = straight
         1 = larger than 180 / reflex
    """

    an = normalize(a)
    bn = normalize(b)

    if nearly_parallel(an, bn):
        return 0

    c = cross(an, bn)

    if dot(c, normal) < 0.0:
        return 1

    return -1


# -----------------------------------------------------------------------------
# Projection / closest point helpers
# -----------------------------------------------------------------------------

def closest_point_on_segment(point, a, b):
    ab = sub(b, a)
    ab_len_sq = length_sq(ab)

    if ab_len_sq < EPSILON_SQ:
        return list(a)

    t = dot(sub(point, a), ab) / ab_len_sq
    t = clamp(t, 0.0, 1.0)

    return lerp(a, b, t)


def closest_point_on_line(point, a, b):
    ab = sub(b, a)
    ab_len_sq = length_sq(ab)

    if ab_len_sq < EPSILON_SQ:
        return list(a)

    t = dot(sub(point, a), ab) / ab_len_sq
    return lerp(a, b, t)


def line_plane_intersection(line_a, line_b, plane_point, plane_normal):
    """
    Intersect infinite line AB with plane.

    Returns:
        point or None
    """

    line_dir = sub(line_b, line_a)
    denom = dot(plane_normal, line_dir)

    if abs(denom) < EPSILON:
        return None

    t = dot(plane_normal, sub(plane_point, line_a)) / denom
    return add(line_a, mul(line_dir, t))


def line_line_closest_points(a1, a2, b1, b2):
    """
    Closest points between two infinite 3D lines.

    Returns:
        (point_on_a, point_on_b, success)

    If lines are nearly parallel, success is False.
    """

    p = a1
    q = b1
    d1 = sub(a2, a1)
    d2 = sub(b2, b1)
    r = sub(p, q)

    a = dot(d1, d1)
    e = dot(d2, d2)
    f = dot(d2, r)

    if a <= EPSILON_SQ or e <= EPSILON_SQ:
        return list(a1), list(b1), False

    b = dot(d1, d2)
    c = dot(d1, r)

    denom = (a * e) - (b * b)

    if abs(denom) <= EPSILON_SQ:
        return list(a1), closest_point_on_line(a1, b1, b2), False

    s = ((b * f) - (c * e)) / denom
    t = ((a * f) - (b * c)) / denom

    point_a = add(p, mul(d1, s))
    point_b = add(q, mul(d2, t))

    return point_a, point_b, True


def line_line_intersection_midpoint(a1, a2, b1, b2):
    """
    Return midpoint between closest points of two infinite 3D lines.

    For coplanar intersecting lines, this is the actual intersection.
    For skew lines, this is the midpoint between nearest points.
    """

    pa, pb, success = line_line_closest_points(a1, a2, b1, b2)

    if not success:
        return None

    return midpoint(pa, pb)


# -----------------------------------------------------------------------------
# Misc geometric helpers
# -----------------------------------------------------------------------------

def determinant_3x3(a, b, c):
    """
    dot(a, cross(b, c))
    Equivalent to Blender's determinant_v3v3v3 helper.
    """

    return dot(a, cross(b, c))


def project_point_to_plane(point, plane_point, plane_normal):
    """
    Orthogonally project point onto plane.
    """

    n = normalize(plane_normal)
    d = dot(sub(point, plane_point), n)
    return sub(point, mul(n, d))


def safe_normal_from_points(a, b, c):
    """
    Normal of triangle ABC.
    """

    ab = sub(b, a)
    ac = sub(c, a)
    n = cross(ab, ac)

    if is_zero(n):
        return [0.0, 0.0, 0.0]

    return normalize(n)