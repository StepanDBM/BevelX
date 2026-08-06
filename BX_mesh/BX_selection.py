# BX_selection.py
# BevelX Maya selection helpers.
#
# First milestone:
#   - Read selected polygon edges.
#   - Resolve mesh transform / shape.
#   - Extract edge index.
#   - Extract edge vertex IDs.
#   - Extract vertex world positions.
#   - Extract connected faces.
#   - Extract world-space face normals.

from __future__ import print_function

import re

import maya.cmds as cmds
import maya.api.OpenMaya as om

from BX_profile import BX_log


EDGE_RE = re.compile(r"^(?P<node>.+)\.e\[(?P<index>\d+)\]$")
VERT_RE = re.compile(r"^(?P<node>.+)\.vtx\[(?P<index>\d+)\]$")
FACE_RE = re.compile(r"^(?P<node>.+)\.f\[(?P<index>\d+)\]$")


# -----------------------------------------------------------------------------
# Basic component parsing
# -----------------------------------------------------------------------------

def parse_edge_component(edge_component):
    """
    Parse a Maya edge component string.

    Example:
        pCube1.e[4]

    Returns:
        {
            "node": "pCube1",
            "index": 4
        }
    """

    match = EDGE_RE.match(edge_component)

    if not match:
        raise ValueError("Not an edge component: {0}".format(edge_component))

    return {
        "node": match.group("node"),
        "index": int(match.group("index")),
    }


def parse_face_component(face_component):
    """
    Parse a Maya face component string.

    Example:
        pCube1.f[2]
    """

    match = FACE_RE.match(face_component)

    if not match:
        raise ValueError("Not a face component: {0}".format(face_component))

    return {
        "node": match.group("node"),
        "index": int(match.group("index")),
    }


def parse_vertex_component(vertex_component):
    """
    Parse a Maya vertex component string.

    Example:
        pCube1.vtx[8]
    """

    match = VERT_RE.match(vertex_component)

    if not match:
        raise ValueError("Not a vertex component: {0}".format(vertex_component))

    return {
        "node": match.group("node"),
        "index": int(match.group("index")),
    }


# -----------------------------------------------------------------------------
# Mesh resolving
# -----------------------------------------------------------------------------

def get_mesh_shape(node):
    """
    Given a transform or shape node, return the non-intermediate mesh shape.

    Args:
        node: Transform or mesh shape.

    Returns:
        Mesh shape name, preferably long path.
    """

    if not cmds.objExists(node):
        raise RuntimeError("Node does not exist: {0}".format(node))

    node_type = cmds.nodeType(node)

    if node_type == "mesh":
        return node

    shapes = cmds.listRelatives(
        node,
        shapes=True,
        noIntermediate=True,
        fullPath=True
    ) or []

    mesh_shapes = [
        shape for shape in shapes
        if cmds.nodeType(shape) == "mesh"
    ]

    if not mesh_shapes:
        raise RuntimeError("No mesh shape found under: {0}".format(node))

    return mesh_shapes[0]


def get_mesh_dag_path(node):
    """
    Return Maya API dag path for a mesh transform or shape.
    """

    shape = get_mesh_shape(node)

    selection = om.MSelectionList()
    selection.add(shape)

    return selection.getDagPath(0)


# -----------------------------------------------------------------------------
# Edge data extraction
# -----------------------------------------------------------------------------

def get_selected_edge_components():
    """
    Return current selected edges as flattened Maya component strings.

    Returns:
        ["pCube1.e[0]", "pCube1.e[1]", ...]
    """

    selection = cmds.ls(selection=True, flatten=True) or []

    if not selection:
        return []

    edges = cmds.filterExpand(selection, selectionMask=32, expand=True) or []

    return edges


def get_edge_vertex_ids(edge_component):
    """
    Return the two vertex IDs of an edge component.

    Uses maya.cmds.polyInfo because it is simple and reliable for this step.
    """

    info = cmds.polyInfo(edge_component, edgeToVertex=True)

    if not info:
        raise RuntimeError("Could not query edge vertices: {0}".format(edge_component))

    # Example line:
    #   EDGE    0:      0      1
    numbers = [int(value) for value in re.findall(r"\d+", info[0])]

    if len(numbers) < 3:
        raise RuntimeError("Unexpected polyInfo edge format: {0}".format(info[0]))

    # First number is edge index. Next two are vertex IDs.
    return numbers[1], numbers[2]


def get_vertex_world_position(node, vertex_id):
    """
    Return world-space vertex position.

    Args:
        node: Mesh transform or shape.
        vertex_id: Integer vertex index.

    Returns:
        [x, y, z]
    """

    vertex_component = "{0}.vtx[{1}]".format(node, vertex_id)

    position = cmds.xform(
        vertex_component,
        query=True,
        worldSpace=True,
        translation=True
    )

    return [float(position[0]), float(position[1]), float(position[2])]


def get_connected_face_components(edge_component):
    """
    Return faces connected to an edge.

    Returns:
        ["pCube1.f[0]", "pCube1.f[1]"]
    """

    faces = cmds.polyListComponentConversion(edge_component, toFace=True)
    faces = cmds.filterExpand(faces, selectionMask=34, expand=True) or []

    return faces


def get_face_world_normal(node, face_id):
    """
    Return world-space polygon normal using Maya API 2.0.
    """

    dag_path = get_mesh_dag_path(node)
    mesh_fn = om.MFnMesh(dag_path)

    normal = mesh_fn.getPolygonNormal(face_id, om.MSpace.kWorld)

    return [float(normal.x), float(normal.y), float(normal.z)]


def get_edge_data(edge_component):
    """
    Return all useful debug data for one selected edge.

    Returns:
        {
            "component": "pCube1.e[0]",
            "node": "pCube1",
            "shape": "|pCube1|pCubeShape1",
            "edge_id": 0,
            "vertex_ids": [0, 1],
            "vertex_positions": [[x,y,z], [x,y,z]],
            "faces": [
                {
                    "component": "pCube1.f[0]",
                    "face_id": 0,
                    "normal": [x,y,z]
                }
            ]
        }
    """

    parsed = parse_edge_component(edge_component)

    node = parsed["node"]
    edge_id = parsed["index"]

    shape = get_mesh_shape(node)

    v0_id, v1_id = get_edge_vertex_ids(edge_component)

    v0_pos = get_vertex_world_position(node, v0_id)
    v1_pos = get_vertex_world_position(node, v1_id)

    face_components = get_connected_face_components(edge_component)

    faces = []

    for face_component in face_components:
        face_parsed = parse_face_component(face_component)
        face_id = face_parsed["index"]

        faces.append({
            "component": face_component,
            "face_id": face_id,
            "normal": get_face_world_normal(node, face_id),
            "center": get_face_world_center(node, face_id),
        })

    return {
        "component": edge_component,
        "node": node,
        "shape": shape,
        "edge_id": edge_id,
        "vertex_ids": [v0_id, v1_id],
        "vertex_positions": [v0_pos, v1_pos],
        "faces": faces,
    }


def get_selected_edges_data():
    """
    Return full data for all selected edges.
    """

    edge_components = get_selected_edge_components()

    return [
        get_edge_data(edge_component)
        for edge_component in edge_components
    ]

def print_selected_edges_debug():
    """
    Convenience manual test.
    Run with polygon edges selected.

    Logging:
        - summary count at DEBUG / selection
        - edge-level data at DEBUG / selection
        - face-level data at TRACE / selection
    """
    edges_data = get_selected_edges_data()

    if not BX_log.is_enabled("DEBUG", "selection"):
        return edges_data

    if not edges_data:
        BX_log.debug("No selected polygon edges.",
            channel="selection")
        return []

    BX_log.debug("Selected edge count: {0}".format(len(edges_data)),
        channel="selection")

    for edge_data in edges_data:
        BX_log.debug("Edge: {0}".format(edge_data["component"]),
            channel="selection")
        BX_log.debug("  Mesh node: {0}".format(edge_data["node"]),
            channel="selection")
        BX_log.debug("  Shape: {0}".format(edge_data["shape"]),
            channel="selection")
        BX_log.debug("  Edge ID: {0}".format(edge_data["edge_id"]),
            channel="selection")
        BX_log.debug("  Vertex IDs: {0}".format(edge_data["vertex_ids"]),
            channel="selection")
        BX_log.debug("  Vertex positions:",
            channel="selection")
        BX_log.debug("    {0}".format(edge_data["vertex_positions"][0]),
            channel="selection")
        BX_log.debug("    {0}".format(edge_data["vertex_positions"][1]),
            channel="selection")
        BX_log.debug("  Connected faces: {0}".format(len(edge_data["faces"])),
            channel="selection")

        for face_data in edge_data["faces"]:
            BX_log.trace("    Face: {0}".format(face_data["component"]),
                channel="selection")
            BX_log.trace("      Face ID: {0}".format(face_data["face_id"]),
                channel="selection")
            BX_log.trace("      Normal: {0}".format(face_data["normal"]),
                channel="selection")
            if "center" in face_data:
                BX_log.trace("      Center: {0}".format(face_data["center"]),
                    channel="selection")
    return edges_data

def get_face_world_center(node, face_id):
    """
    Return world-space polygon center using Maya API 2.0.
    """

    dag_path = get_mesh_dag_path(node)
    mesh_fn = om.MFnMesh(dag_path)

    vertex_ids = mesh_fn.getPolygonVertices(face_id)
    points = mesh_fn.getPoints(om.MSpace.kWorld)

    center = [0.0, 0.0, 0.0]

    for vertex_id in vertex_ids:
        point = points[vertex_id]
        center[0] += point.x
        center[1] += point.y
        center[2] += point.z

    count = float(len(vertex_ids))

    if count == 0.0:
        return center

    return [
        center[0] / count,
        center[1] / count,
        center[2] / count,
    ]