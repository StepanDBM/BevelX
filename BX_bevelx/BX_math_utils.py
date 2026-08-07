# BX_bevelx/BX_math_utils.py
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from BX_bevelx.BX_constants import (
    BEVEL_EPSILON,
    BEVEL_EPSILON_BIG,
    BEVEL_EPSILON_ANG,
    BEVEL_EPSILON_ANG_DOT,
    PRO_LINE_R,
    PRO_CIRCLE_R,
    PRO_SQUARE_R,
    PRO_SQUARE_IN_R,
)


# ---------------------------------------------------------------------------
# Basic vector helpers
# ---------------------------------------------------------------------------

def vec3(value=None) -> List[float]:
    if value is None:
        return [0.0, 0.0, 0.0]

    return [float(value[0]), float(value[1]), float(value[2])]


def copy_v3(v) -> List[float]:
    return [float(v[0]), float(v[1]), float(v[2])]


def zero_v3() -> List[float]:
    return [0.0, 0.0, 0.0]


def add_v3v3(a, b) -> List[float]:
    return [
        a[0] + b[0],
        a[1] + b[1],
        a[2] + b[2],
    ]


def sub_v3v3(a, b) -> List[float]:
    return [
        a[0] - b[0],
        a[1] - b[1],
        a[2] - b[2],
    ]


def mul_v3_fl(a, factor) -> List[float]:
    return [
        a[0] * factor,
        a[1] * factor,
        a[2] * factor,
    ]


def div_v3_fl(a, divisor) -> List[float]:
    if abs(divisor) <= BEVEL_EPSILON:
        return zero_v3()

    inv = 1.0 / divisor
    return mul_v3_fl(a, inv)


def madd_v3_v3fl(a, b, factor) -> List[float]:
    return [
        a[0] + b[0] * factor,
        a[1] + b[1] * factor,
        a[2] + b[2] * factor,
    ]


def mid_v3v3(a, b) -> List[float]:
    return [
        0.5 * (a[0] + b[0]),
        0.5 * (a[1] + b[1]),
        0.5 * (a[2] + b[2]),
    ]


def interp_v3v3(a, b, t) -> List[float]:
    return [
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    ]


def dot_v3v3(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross_v3v3(a, b) -> List[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def len_squared_v3(a) -> float:
    return dot_v3v3(a, a)


def len_v3(a) -> float:
    return math.sqrt(len_squared_v3(a))


def len_squared_v3v3(a, b) -> float:
    return len_squared_v3(sub_v3v3(a, b))


def len_v3v3(a, b) -> float:
    return math.sqrt(len_squared_v3v3(a, b))


def normalize_v3(a) -> Tuple[float, List[float]]:
    length = len_v3(a)

    if length <= 0.0:
        return 0.0, [0.0, 0.0, 0.0]

    inv = 1.0 / length

    return length, [
        a[0] * inv,
        a[1] * inv,
        a[2] * inv,
    ]


def normalized_v3(a) -> List[float]:
    return normalize_v3(a)[1]


def negate_v3(a) -> List[float]:
    return [-a[0], -a[1], -a[2]]


def compare_ff(a, b, epsilon) -> bool:
    return abs(a - b) <= epsilon


def compare_v3v3(a, b, epsilon) -> bool:
    return (
        abs(a[0] - b[0]) <= epsilon and
        abs(a[1] - b[1]) <= epsilon and
        abs(a[2] - b[2]) <= epsilon
    )


def is_zero_v3(a, epsilon=BEVEL_EPSILON) -> bool:
    return len_squared_v3(a) <= epsilon * epsilon


# ---------------------------------------------------------------------------
# Angle helpers
# ---------------------------------------------------------------------------

def angle_normalized_v3v3(a, b) -> float:
    value = max(-1.0, min(1.0, dot_v3v3(a, b)))
    return math.acos(value)


def angle_v3v3(a, b) -> float:
    _, an = normalize_v3(a)
    _, bn = normalize_v3(b)
    return angle_normalized_v3v3(an, bn)


def angle_v3v3v3(a, b, c) -> float:
    return angle_v3v3(sub_v3v3(a, b), sub_v3v3(c, b))


def nearly_parallel(d1, d2) -> bool:
    angle = angle_v3v3(d1, d2)
    return abs(angle) < BEVEL_EPSILON_ANG or abs(angle - math.pi) < BEVEL_EPSILON_ANG


def nearly_parallel_normalized(d1, d2) -> bool:
    direction_dot = dot_v3v3(d1, d2)
    return compare_ff(abs(direction_dot), 1.0, BEVEL_EPSILON_ANG_DOT)


def determinant_v3v3v3(a, b, c) -> float:
    return (
        a[0] * b[1] * c[2]
        + a[1] * b[2] * c[0]
        + a[2] * b[0] * c[1]
        - a[0] * b[2] * c[1]
        - a[1] * b[0] * c[2]
        - a[2] * b[1] * c[0]
    )


# ---------------------------------------------------------------------------
# Projection and geometric intersection helpers
# ---------------------------------------------------------------------------

def project_point_to_plane(point, plane_co, plane_no) -> List[float]:
    delta = sub_v3v3(point, plane_co)
    distance = dot_v3v3(delta, plane_no)
    return sub_v3v3(point, mul_v3_fl(plane_no, distance))


def closest_point_on_segment(point, a, b) -> List[float]:
    ab = sub_v3v3(b, a)
    ab_len_sq = len_squared_v3(ab)

    if ab_len_sq <= BEVEL_EPSILON * BEVEL_EPSILON:
        return copy_v3(a)

    t = dot_v3v3(sub_v3v3(point, a), ab) / ab_len_sq
    t = max(0.0, min(1.0, t))

    return interp_v3v3(a, b, t)


def dist_squared_to_line_segment(point, a, b) -> float:
    closest = closest_point_on_segment(point, a, b)
    return len_squared_v3v3(point, closest)


def line_plane_intersection(p0, p1, plane_co, plane_no) -> Tuple[bool, List[float]]:
    direction = sub_v3v3(p1, p0)
    denom = dot_v3v3(plane_no, direction)

    if abs(denom) <= BEVEL_EPSILON:
        return False, copy_v3(p0)

    t = dot_v3v3(plane_no, sub_v3v3(plane_co, p0)) / denom

    return True, madd_v3_v3fl(p0, direction, t)


def line_line_closest_points(p1, p2, p3, p4) -> Tuple[int, List[float], List[float]]:
    """
    Closest points of two 3D lines.

    Return:
        kind, pa, pb

    kind:
        0 = no stable solution, usually degenerate or parallel
        1 = intersection or near intersection
        2 = skew closest points
    """

    p13 = sub_v3v3(p1, p3)
    p43 = sub_v3v3(p4, p3)
    p21 = sub_v3v3(p2, p1)

    if len_squared_v3(p43) <= BEVEL_EPSILON * BEVEL_EPSILON:
        return 0, copy_v3(p1), copy_v3(p3)

    if len_squared_v3(p21) <= BEVEL_EPSILON * BEVEL_EPSILON:
        return 0, copy_v3(p1), copy_v3(p3)

    d1343 = dot_v3v3(p13, p43)
    d4321 = dot_v3v3(p43, p21)
    d1321 = dot_v3v3(p13, p21)
    d4343 = dot_v3v3(p43, p43)
    d2121 = dot_v3v3(p21, p21)

    denom = d2121 * d4343 - d4321 * d4321

    if abs(denom) <= BEVEL_EPSILON:
        return 0, copy_v3(p1), copy_v3(p3)

    numer = d1343 * d4321 - d1321 * d4343

    mua = numer / denom
    mub = (d1343 + d4321 * mua) / d4343

    pa = madd_v3_v3fl(p1, p21, mua)
    pb = madd_v3_v3fl(p3, p43, mub)

    if len_squared_v3v3(pa, pb) <= BEVEL_EPSILON_BIG * BEVEL_EPSILON_BIG:
        return 1, pa, pb

    return 2, pa, pb


def line_line_intersection_midpoint(p1, p2, p3, p4) -> Optional[List[float]]:
    kind, pa, pb = line_line_closest_points(p1, p2, p3, p4)

    if kind == 0:
        return None

    return mid_v3v3(pa, pb)


# ---------------------------------------------------------------------------
# Local 2D frame helpers for face-plane bevel math
# ---------------------------------------------------------------------------

def make_plane_frame(normal) -> Tuple[List[float], List[float], List[float]]:
    """
    Create an orthonormal 2D frame on a plane with the given normal.
    """

    _, n = normalize_v3(normal)

    if is_zero_v3(n):
        n = [0.0, 0.0, 1.0]

    if abs(n[2]) < 0.9:
        axis = [0.0, 0.0, 1.0]
    else:
        axis = [0.0, 1.0, 0.0]

    u = normalized_v3(cross_v3v3(axis, n))
    v = normalized_v3(cross_v3v3(n, u))

    return u, v, n


def to_plane_2d(point, origin, axis_u, axis_v) -> Tuple[float, float]:
    delta = sub_v3v3(point, origin)
    return dot_v3v3(delta, axis_u), dot_v3v3(delta, axis_v)


def from_plane_2d(x, y, origin, axis_u, axis_v) -> List[float]:
    return add_v3v3(
        origin,
        add_v3v3(
            mul_v3_fl(axis_u, x),
            mul_v3_fl(axis_v, y),
        ),
    )


def cross_2d(a, b) -> float:
    return a[0] * b[1] - a[1] * b[0]


def add_2d(a, b) -> Tuple[float, float]:
    return a[0] + b[0], a[1] + b[1]


def sub_2d(a, b) -> Tuple[float, float]:
    return a[0] - b[0], a[1] - b[1]


def mul_2d(a, factor) -> Tuple[float, float]:
    return a[0] * factor, a[1] * factor


def len_2d(a) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1])


def normalize_2d(a) -> Tuple[float, Tuple[float, float]]:
    length = len_2d(a)

    if length <= BEVEL_EPSILON:
        return 0.0, (0.0, 0.0)

    inv = 1.0 / length
    return length, (a[0] * inv, a[1] * inv)


def perp_left_2d(a) -> Tuple[float, float]:
    return -a[1], a[0]


def perp_right_2d(a) -> Tuple[float, float]:
    return a[1], -a[0]


def line_intersection_2d(p, r, q, s) -> Optional[Tuple[float, float]]:
    """
    Infinite 2D line intersection:
        p + t*r
        q + u*s
    """

    denom = cross_2d(r, s)

    if abs(denom) <= BEVEL_EPSILON:
        return None

    qp = sub_2d(q, p)
    t = cross_2d(qp, s) / denom

    return add_2d(p, mul_2d(r, t))


def offset_line_2d(point_a, point_b, distance, normal_side=1.0):
    """
    Offset a 2D line by distance along a perpendicular.

    normal_side > 0 uses left perpendicular.
    normal_side < 0 uses right perpendicular.
    """

    direction = sub_2d(point_b, point_a)
    _, direction = normalize_2d(direction)

    if normal_side >= 0.0:
        side = perp_left_2d(direction)
    else:
        side = perp_right_2d(direction)

    offset = mul_2d(side, distance)

    return add_2d(point_a, offset), direction


# ---------------------------------------------------------------------------
# Bevel offset / meet helpers
# ---------------------------------------------------------------------------

def edge_other_vert(edge, vert):
    if hasattr(edge, "other_vert"):
        return edge.other_vert(vert)

    if edge.verts[0] is vert:
        return edge.verts[1]

    if edge.verts[1] is vert:
        return edge.verts[0]

    return None


def edge_direction_from_vert(edge, vert) -> List[float]:
    other = edge_other_vert(edge, vert)

    if other is None:
        return zero_v3()

    return normalized_v3(sub_v3v3(other.co, vert.co))


def point_on_edge_from_vert(edge, vert, distance) -> List[float]:
    direction = edge_direction_from_vert(edge, vert)
    return add_v3v3(vert.co, mul_v3_fl(direction, distance))


def clamp_distance_to_edge(edge, distance) -> float:
    if hasattr(edge, "calc_length"):
        length = edge.calc_length()
    else:
        length = len_v3v3(edge.verts[0].co, edge.verts[1].co)

    if length <= BEVEL_EPSILON:
        return 0.0

    return max(0.0, min(float(distance), length))


def point_on_edge_offset(edge, vert, distance) -> List[float]:
    distance = clamp_distance_to_edge(edge, distance)
    return point_on_edge_from_vert(edge, vert, distance)


def offset_meet_in_face(vertex_co,
                        edge_a_other_co,
                        edge_b_other_co,
                        face_normal,
                        offset_a,
                        offset_b,
                        side_a=1.0,
                        side_b=-1.0) -> Optional[List[float]]:
    """
    Intersect two offset lines in the plane of a face.

    This is intentionally low-level. The caller decides which side each edge is
    offset to. That mirrors Blender's approach where EdgeHalf orientation and
    face ownership determine the correct side.
    """

    axis_u, axis_v, _ = make_plane_frame(face_normal)

    va = to_plane_2d(vertex_co, vertex_co, axis_u, axis_v)
    ea = to_plane_2d(edge_a_other_co, vertex_co, axis_u, axis_v)
    eb = to_plane_2d(edge_b_other_co, vertex_co, axis_u, axis_v)

    line_a_point, line_a_dir = offset_line_2d(
        va,
        ea,
        offset_a,
        normal_side=side_a,
    )

    line_b_point, line_b_dir = offset_line_2d(
        va,
        eb,
        offset_b,
        normal_side=side_b,
    )

    intersection = line_intersection_2d(
        line_a_point,
        line_a_dir,
        line_b_point,
        line_b_dir,
    )

    if intersection is None:
        return None

    return from_plane_2d(
        intersection[0],
        intersection[1],
        vertex_co,
        axis_u,
        axis_v,
    )


def face_normal_or_vertex_normal(face, fallback_normal=None) -> List[float]:
    if face is not None:
        normal = getattr(face, "normal", None)
        if normal is not None and not is_zero_v3(normal):
            return copy_v3(normal)

    if fallback_normal is not None and not is_zero_v3(fallback_normal):
        return copy_v3(fallback_normal)

    return [0.0, 0.0, 1.0]


def average_face_normal(faces) -> List[float]:
    total = zero_v3()
    count = 0

    for face in faces:
        normal = getattr(face, "normal", None)
        if normal is None:
            continue
        total = add_v3v3(total, normal)
        count += 1

    if count == 0:
        return [0.0, 0.0, 1.0]

    _, normal = normalize_v3(total)

    if is_zero_v3(normal):
        return [0.0, 0.0, 1.0]

    return normal


def _edge_other_vert(edge, vert):
    if hasattr(edge, "other_vert"):
        return edge.other_vert(vert)

    if edge.verts[0] is vert:
        return edge.verts[1]

    if edge.verts[1] is vert:
        return edge.verts[0]

    return None


def _edge_length(edge):
    if hasattr(edge, "calc_length"):
        return edge.calc_length()

    return len_v3v3(edge.verts[0].co, edge.verts[1].co)


def _clamp_offset_to_edge(edge, offset):
    length = _edge_length(edge)

    if length <= BEVEL_EPSILON:
        return 0.0

    if offset < 0.0:
        return 0.0

    if offset > length:
        return length

    return offset


def _edge_direction_from_vert(edge, vert):
    other = _edge_other_vert(edge, vert)

    if other is None:
        return [0.0, 0.0, 0.0]

    return normalized_v3(
        sub_v3v3(
            other.co,
            vert.co
        )
    )


def point_on_edgehalf_from_bevvert(params,
                                   bevvert,
                                   edge_half):
    """
    Return a point on edge_half.e, offset from bevvert.v.

    This is the low-level edge slide used by the first BoundVert construction
    pass. The more exact Blender line/line offset solve can replace this later
    without changing BoundVert ownership.
    """

    offset = getattr(edge_half, "offset_l_spec", 0.0)

    if offset <= 0.0:
        offset = getattr(edge_half, "offset_l", 0.0)

    if offset <= 0.0:
        offset = params.offset

    offset = _clamp_offset_to_edge(
        edge=edge_half.e,
        offset=offset
    )

    direction = _edge_direction_from_vert(
        edge=edge_half.e,
        vert=bevvert.v
    )

    return add_v3v3(
        bevvert.v.co,
        mul_v3_fl(direction, offset)
    )


def solve_offset_meet_for_edgehalves(params,
                                     bevvert,
                                     previous_half,
                                     current_half):
    """
    Solve the initial BoundVert coordinate for the sector:

        previous_half -> current_half

    Blender-shaped ownership rules for the first port pass:

        selected + unselected
            BoundVert lies on the unselected support edge.

        unselected + selected
            BoundVert lies on the selected edge.

        selected + selected
            BoundVert lies at the initial miter approximation between both
            offset edge points.

    This function intentionally returns geometry only. BoundVert ownership
    remains in BX_build_boundverts.py.
    """

    previous_is_bev = bool(getattr(previous_half, "is_bev", False))
    current_is_bev = bool(getattr(current_half, "is_bev", False))

    if not previous_is_bev and not current_is_bev:
        return None

    if previous_is_bev and current_is_bev:
        previous_point = point_on_edgehalf_from_bevvert(
            params=params,
            bevvert=bevvert,
            edge_half=previous_half
        )

        current_point = point_on_edgehalf_from_bevvert(
            params=params,
            bevvert=bevvert,
            edge_half=current_half
        )

        return mul_v3_fl(
            add_v3v3(previous_point, current_point),
            0.5
        )

    if previous_is_bev and not current_is_bev:
        return point_on_edgehalf_from_bevvert(
            params=params,
            bevvert=bevvert,
            edge_half=current_half
        )

    return point_on_edgehalf_from_bevvert(
        params=params,
        bevvert=bevvert,
        edge_half=current_half
    )

# ---------------------------------------------------------------------------
# Superellipse / profile spacing helpers
# ---------------------------------------------------------------------------

def superellipse_co(x, r, rbig) -> float:
    if r <= 0.0:
        raise ValueError("superellipse exponent must be positive")

    if rbig:
        return pow(1.0 - pow(x, r), 1.0 / r)

    return 1.0 - pow(1.0 - pow(1.0 - x, r), 1.0 / r)


def find_superellipse_chord_endpoint(x0, dtarget, r, rbig) -> float:
    y0 = superellipse_co(x0, r, rbig)
    tol = 1.0e-13
    maxiter = 10

    xmin = x0 + math.sqrt(2.0) / 2.0 * dtarget
    xmin = min(xmin, 1.0)

    xmax = x0 + dtarget
    xmax = min(xmax, 1.0)

    ymin = superellipse_co(xmin, r, rbig)
    ymax = superellipse_co(xmax, r, rbig)

    dmaxerr = math.sqrt((xmax - x0) ** 2 + (ymax - y0) ** 2) - dtarget
    dminerr = math.sqrt((xmin - x0) ** 2 + (ymin - y0) ** 2) - dtarget

    if abs(dmaxerr - dminerr) <= tol:
        return xmax

    xnew = xmax - dmaxerr * (xmax - xmin) / (dmaxerr - dminerr)
    lastupdated_upper = True

    for _ in range(maxiter):
        ynew = superellipse_co(xnew, r, rbig)
        dnewerr = math.sqrt((xnew - x0) ** 2 + (ynew - y0) ** 2) - dtarget

        if abs(dnewerr) < tol:
            break

        if dnewerr < 0.0:
            xmin = xnew
            ymin = ynew
            dminerr = dnewerr

            if not lastupdated_upper:
                xnew = (dmaxerr / 2.0 * xmin - dminerr * xmax) / (dmaxerr / 2.0 - dminerr)
            else:
                xnew = xmax - dmaxerr * (xmax - xmin) / (dmaxerr - dminerr)

            lastupdated_upper = False
        else:
            xmax = xnew
            ymax = ynew
            dmaxerr = dnewerr

            if lastupdated_upper:
                xnew = (dmaxerr * xmin - dminerr / 2.0 * xmax) / (dmaxerr - dminerr / 2.0)
            else:
                xnew = xmax - dmaxerr * (xmax - xmin) / (dmaxerr - dminerr)

            lastupdated_upper = True

    return xnew


def find_even_superellipse_chords_general(seg, r) -> Tuple[List[float], List[float]]:
    smoothitermax = 10
    error_tol = 1.0e-7

    xvals = [0.0] * (seg + 1)
    yvals = [0.0] * (seg + 1)

    imax = (seg + 1) // 2 - 1
    seg_odd = bool(seg % 2)

    if r > 1.0:
        rbig = True
        mx = pow(0.5, 1.0 / r)
    else:
        rbig = False
        mx = 1.0 - pow(0.5, 1.0 / r)

    for i in range(imax + 1):
        xvals[i] = i * mx / seg * 2.0
        yvals[i] = superellipse_co(xvals[i], r, rbig)

    yvals[0] = 1.0

    for _ in range(smoothitermax):
        total = 0.0
        dmin = 2.0
        dmax = 0.0

        for i in range(imax):
            d = math.sqrt((xvals[i + 1] - xvals[i]) ** 2 + (yvals[i + 1] - yvals[i]) ** 2)
            total += d
            dmax = max(dmax, d)
            dmin = min(dmin, d)

        if seg_odd:
            total += math.sqrt(2.0) / 2.0 * (yvals[imax] - xvals[imax])
            davg = total / (imax + 0.5)
        else:
            total += math.sqrt((xvals[imax] - mx) ** 2 + (yvals[imax] - mx) ** 2)
            davg = total / (imax + 1.0)

        precision_reached = True

        if dmax - davg > error_tol:
            precision_reached = False

        if dmin - davg < -error_tol:
            precision_reached = False

        if precision_reached:
            break

        xvals[0] = 0.0
        yvals[0] = 1.0
        dtarget = davg

        for i in range(1, imax + 1):
            xnew = find_superellipse_chord_endpoint(
                xvals[i - 1],
                dtarget,
                r,
                rbig,
            )
            xvals[i] = xnew
            yvals[i] = superellipse_co(xnew, r, rbig)

    if not seg_odd:
        xvals[imax + 1] = mx
        yvals[imax + 1] = mx

    for i in range(imax + 1, seg + 1):
        yvals[i] = xvals[seg - i]
        xvals[i] = yvals[seg - i]

    if not rbig:
        for i in range(seg + 1):
            temp = xvals[i]
            xvals[i] = 1.0 - yvals[i]
            yvals[i] = 1.0 - temp

    return xvals, yvals


def find_even_superellipse_chords(n, r) -> Tuple[List[float], List[float]]:
    xvals = [0.0] * (n + 1)
    yvals = [0.0] * (n + 1)

    seg_odd = bool(n % 2)
    n2 = n // 2

    if r == PRO_LINE_R:
        for i in range(n + 1):
            xvals[i] = float(i) / float(n)
            yvals[i] = 1.0 - float(i) / float(n)
        return xvals, yvals

    if r == PRO_CIRCLE_R:
        step = math.pi * 0.5 / float(n)
        for i in range(n + 1):
            xvals[i] = math.sin(i * step)
            yvals[i] = math.cos(i * step)
        return xvals, yvals

    if r == PRO_SQUARE_IN_R:
        if not seg_odd:
            for i in range(n2 + 1):
                xvals[i] = 0.0
                yvals[i] = 1.0 - float(i) / float(n2)
                xvals[n - i] = yvals[i]
                yvals[n - i] = xvals[i]
        else:
            step = 1.0 / (n2 + math.sqrt(2.0) / 2.0)
            for i in range(n2 + 1):
                xvals[i] = 0.0
                yvals[i] = 1.0 - float(i) * step
                xvals[n - i] = yvals[i]
                yvals[n - i] = xvals[i]
        return xvals, yvals

    if r == PRO_SQUARE_R:
        if not seg_odd:
            for i in range(n2 + 1):
                xvals[i] = float(i) / float(n2)
                yvals[i] = 1.0
                xvals[n - i] = yvals[i]
                yvals[n - i] = xvals[i]
        else:
            step = 1.0 / (n2 + math.sqrt(2.0) / 2.0)
            for i in range(n2 + 1):
                xvals[i] = float(i) * step
                yvals[i] = 1.0
                xvals[n - i] = yvals[i]
                yvals[n - i] = xvals[i]
        return xvals, yvals

    return find_even_superellipse_chords_general(n, r)
