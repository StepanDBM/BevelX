# BX_debug.py
# BevelX debug drawing helpers.
#
# Current job:
# - Draw offset rails in Maya viewport.
# - Clean old BevelX debug objects.

from __future__ import print_function

import maya.cmds as cmds
from BX_math import BX_math as bxm

DEBUG_GROUP = "BX_DEBUG_GRP"


def ensure_debug_group():
    """Create or return the BevelX debug group."""

    if cmds.objExists(DEBUG_GROUP):
        return DEBUG_GROUP

    return cmds.group(empty=True, name=DEBUG_GROUP)


def clear_debug():
    """Delete all BevelX debug objects."""

    if cmds.objExists(DEBUG_GROUP):
        cmds.delete(DEBUG_GROUP)


# -----------------------------------------------------------------------------
# Viewport color helpers
# -----------------------------------------------------------------------------

def set_viewport_color(node, color):
    """
    Set viewport override color on a transform and its shapes.

    Args:
        node: Transform node.
        color: RGB tuple/list, values from 0.0 to 1.0.
    """

    targets = [node]

    shapes = cmds.listRelatives(
        node,
        shapes=True,
        fullPath=True
    ) or []

    targets.extend(shapes)

    for target in targets:
        if not cmds.objExists(target):
            continue

        if cmds.attributeQuery("overrideEnabled", node=target, exists=True):
            cmds.setAttr(target + ".overrideEnabled", 1)

        if cmds.attributeQuery("overrideRGBColors", node=target, exists=True):
            cmds.setAttr(target + ".overrideRGBColors", 1)

        if cmds.attributeQuery("overrideColorRGB", node=target, exists=True):
            cmds.setAttr(
                target + ".overrideColorRGB",
                color[0],
                color[1],
                color[2],
                type="double3"
            )


def set_curve_width(curve, width):
    """
    Set curve line width if supported.
    """

    shapes = cmds.listRelatives(
        curve,
        shapes=True,
        fullPath=True
    ) or []

    for shape in shapes:
        if cmds.attributeQuery("lineWidth", node=shape, exists=True):
            cmds.setAttr(shape + ".lineWidth", width)


# -----------------------------------------------------------------------------
# Optional mesh material helpers
# -----------------------------------------------------------------------------

def make_material(name, color):
    """
    Create or reuse a simple lambert material.
    Used only for mesh debug objects, not curves.
    """

    if cmds.objExists(name):
        return name

    mat = cmds.shadingNode(
        "lambert",
        asShader=True,
        name=name
    )

    cmds.setAttr(
        mat + ".color",
        color[0],
        color[1],
        color[2],
        type="double3"
    )

    return mat


def assign_material(obj, material):
    """
    Assign material to mesh debug objects.

    Do not use this for curves. Curves use viewport override colors.
    """

    sg = material + "SG"

    if not cmds.objExists(sg):
        sg = cmds.sets(
            renderable=True,
            noSurfaceShader=True,
            empty=True,
            name=sg
        )

        cmds.connectAttr(
            material + ".outColor",
            sg + ".surfaceShader",
            force=True
        )

    cmds.sets(
        obj,
        edit=True,
        forceElement=sg
    )


# -----------------------------------------------------------------------------
# Draw helpers
# -----------------------------------------------------------------------------

def draw_curve_line(name, p0, p1, color=(0.0, 1.0, 1.0), width=3.0):
    """
    Draw a straight debug curve between two points.

    Curves are colored through viewport override, not shader assignment.
    This avoids Maya shadingEngine warnings.
    """

    ensure_debug_group()

    curve = cmds.curve(
        degree=1,
        point=[p0, p1],
        name=name
    )

    set_curve_width(curve, width)
    set_viewport_color(curve, color)

    cmds.parent(curve, DEBUG_GROUP)

    return curve


def draw_point(name, point, color=(1.0, 0.0, 0.0), size=0.035):
    """
    Draw a small sphere as a debug point.
    """

    ensure_debug_group()

    sphere = cmds.polySphere(
        radius=size,
        subdivisionsX=8,
        subdivisionsY=4,
        name=name
    )[0]

    cmds.xform(
        sphere,
        worldSpace=True,
        translation=point
    )

    mat_name = name + "_MAT"
    mat = make_material(mat_name, color)
    assign_material(sphere, mat)

    set_viewport_color(sphere, color)

    cmds.parent(sphere, DEBUG_GROUP)

    return sphere


def draw_vector(name, origin, vector, color=(1.0, 1.0, 0.0), scale=0.25, width=2.0):
    """
    Draw a vector from origin.
    """

    end = [
        origin[0] + vector[0] * scale,
        origin[1] + vector[1] * scale,
        origin[2] + vector[2] * scale,
    ]

    return draw_curve_line(
        name,
        origin,
        end,
        color=color,
        width=width
    )


def draw_edge_debug(edge_data):
    """
    Draw selected edge and face normals.
    """

    p0, p1 = edge_data["vertex_positions"]

    draw_curve_line(
        "BX_selected_edge_{0}".format(edge_data["edge_id"]),
        p0,
        p1,
        color=(0.0, 1.0, 1.0),
        width=4.0
    )

    center = [
        (p0[0] + p1[0]) * 0.5,
        (p0[1] + p1[1]) * 0.5,
        (p0[2] + p1[2]) * 0.5,
    ]

    for face_data in edge_data["faces"]:
        draw_vector(
            "BX_face_normal_{0}_{1}".format(
                edge_data["edge_id"],
                face_data["face_id"]
            ),
            center,
            face_data["normal"],
            color=(1.0, 1.0, 0.0),
            scale=0.25,
            width=2.0
        )


def draw_offset_rails(edge_data, rails):
    """
    Draw offset rails generated from selected edge data.
    """

    for rail_data in rails:
        p0, p1 = rail_data["rail"]
        face_id = rail_data["face_id"]

        draw_curve_line(
            "BX_offset_rail_edge{0}_face{1}".format(
                edge_data["edge_id"],
                face_id
            ),
            p0,
            p1,
            color=(0.0, 1.0, 0.0),
            width=3.0
        )

        draw_point(
            "BX_offset_rail_A_edge{0}_face{1}".format(
                edge_data["edge_id"],
                face_id
            ),
            p0,
            color=(1.0, 0.0, 0.0),
            size=0.025
        )

        draw_point(
            "BX_offset_rail_B_edge{0}_face{1}".format(
                edge_data["edge_id"],
                face_id
            ),
            p1,
            color=(1.0, 0.0, 0.0),
            size=0.025
        )

#==================================================================
# Quad Preview
#==================================================================
def draw_debug_quad(name, points, color=(1.0, 0.45, 0.0), expected_normal=None):
    """
    Draw a temporary debug quad mesh.

    Args:
        name:
            Mesh name.

        points:
            Four world-space points in order.

        color:
            RGB color.

        expected_normal:
            Optional world-space normal. If provided, the quad winding will be
            flipped when the generated face normal points opposite this normal.

    Returns:
        Mesh transform.
    """

    ensure_debug_group()

    points = list(points)

    if expected_normal is not None:
        points = orient_points_to_normal(points, expected_normal)

    mesh = cmds.polyCreateFacet(
        point=points,
        name=name
    )[0]

    mat_name = name + "_MAT"
    mat = make_material(mat_name, color)
    assign_material(mesh, mat)

    set_viewport_color(mesh, color)

    cmds.parent(mesh, DEBUG_GROUP)

    return mesh

def calculate_polygon_normal(points):
    """
    Calculate a simple polygon normal from the first three non-collinear points.

    Args:
        points:
            List of world-space points.

    Returns:
        Normalized normal vector.
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


def orient_points_to_normal(points, expected_normal):
    """
    Flip polygon winding if the polygon normal points opposite expected_normal.

    Args:
        points:
            Polygon points.

        expected_normal:
            Desired direction.

    Returns:
        Reordered points.
    """

    current_normal = calculate_polygon_normal(points)
    expected_normal = bxm.normalize(expected_normal)

    if bxm.is_zero(current_normal) or bxm.is_zero(expected_normal):
        return points

    if bxm.dot(current_normal, expected_normal) < 0.0:
        # Keep the first point stable and reverse the rest.
        return [points[0]] + list(reversed(points[1:]))

    return points

def draw_preview_bevel_face(edge_data, rails, color=(1.0, 0.45, 0.0)):
    """
    Draw a temporary preview bevel face between two offset rails.

    This is debug visualization only.
    It does not modify the source mesh.
    """

    if len(rails) != 2:
        print(
            "[BevelX] Bevel face preview requires exactly 2 rails. Got: {0}".format(
                len(rails)
            )
        )
        return None

    rail_a = rails[0]["rail"]
    rail_b = rails[1]["rail"]

    a0, a1 = rail_a
    b0, b1 = rail_b

    points = [
        a0,
        a1,
        b1,
        b0,
    ]

    expected_normal = get_expected_bevel_face_normal(rails)

    return draw_debug_quad(
        "BX_preview_bevel_face_edge{0}".format(edge_data["edge_id"]),
        points,
        color=color,
        expected_normal=expected_normal
    )
def get_expected_bevel_face_normal(rails):
    """
    Estimate the expected bevel face normal from the adjacent face normals.

    For a simple one-edge bevel, the bevel face normal should generally point
    between the two adjacent face normals.
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

def draw_boundary_vertices(vertex_boundaries, color=(1.0, 0.0, 1.0), size=0.035):
    """
    Draw boundary vertices as magenta debug points.

    Args:
        vertex_boundaries:
            {
                vertex_id: [BX_BoundaryVertex, ...]
            }
    """

    for vertex_id, boundary_list in vertex_boundaries.items():
        for index, boundary_vertex in enumerate(boundary_list):
            draw_point(
                "BX_boundary_v{0}_{1}".format(vertex_id, index),
                boundary_vertex.co_world,
                color=color,
                size=size
            )

def draw_transaction_faces(transaction):
    """
    Draw transaction faces.

    Currently draws:
        F_EDGE as orange debug quads.
    """

    color_by_kind = {
        "F_EDGE": (1.0, 0.45, 0.0),
        "F_VERT": (0.8, 0.2, 1.0),
        "F_RECON": (0.2, 0.8, 1.0),
        "F_ORIG": (0.5, 0.5, 0.5),
    }

    for face in transaction.faces:
        points = transaction.get_face_world_points(face)

        color = color_by_kind.get(
            face.face_kind,
            (1.0, 1.0, 1.0)
        )

        draw_debug_quad(
            "BX_tx_face_{0}_{1}".format(face.face_kind, face.id),
            points,
            color=color,
            expected_normal=face.expected_normal
        )