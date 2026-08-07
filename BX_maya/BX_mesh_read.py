# BX_maya/BX_mesh_read.py
from __future__ import annotations

"""
Maya mesh read adapter for the clean Blender-style bevel pipeline.

This module is intentionally an input boundary only:
    Maya selection / Maya mesh
        -> plain Python vertices, faces, selected edge ids
        -> optional internal BMesh

The bevel solver itself must not import maya.cmds or maya.api.OpenMaya.
"""

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple


@dataclass
class MayaMeshReadResult:
    """
    Plain Python result from reading a Maya mesh for the bevel solver.

    vertices:
        Object-space vertex coordinates.

    faces:
        Polygon vertex-index loops.

    selected_edges:
        Maya mesh edge ids. These are intended to match the BMesh edge indices
        when BMesh.from_pydata() infers edges from Maya polygon face loops.

    mesh_dag_path:
        Maya DAG path string for debug/use by the write adapter.
    """

    vertices: List[List[float]]
    faces: List[List[int]]
    selected_edges: List[int]
    mesh_dag_path: str
    transform_path: Optional[str] = None
    shape_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Maya import boundary
# ---------------------------------------------------------------------------

def _maya_api():
    try:
        import maya.api.OpenMaya as om
        return om
    except Exception as exc:
        raise RuntimeError(
            "BX_maya.BX_mesh_read requires Maya Python API 2.0. "
            "Run this inside Maya's Python environment."
        ) from exc

# ---------------------------------------------------------------------------
# Selection helpers
# ---------------------------------------------------------------------------

def get_active_selection_list():
    """
    Return Maya's active selection list.
    """

    om = _maya_api()
    return om.MGlobal.getActiveSelectionList()


def dag_path_to_string(dag_path) -> str:
    try:
        return dag_path.fullPathName()
    except Exception:
        return str(dag_path)


def get_mesh_dag_from_selection_item(selection_list, index=0):
    """
    Return mesh shape MDagPath for one selection item.

    Handles either a transform or a mesh shape selection.
    """

    om = _maya_api()

    dag_path, component = selection_list.getComponent(index)

    # If a transform is selected, extend to its shape.
    if dag_path.apiType() == om.MFn.kTransform:
        dag_path.extendToShape()

    # If this is already a mesh shape, keep it.
    if not dag_path.hasFn(om.MFn.kMesh):
        raise RuntimeError(
            "Selected item is not a mesh or mesh transform: {0}".format(
                dag_path_to_string(dag_path)
            )
        )

    return dag_path, component


def get_first_selected_mesh_dag_path():
    """
    Return first selected mesh shape dag path and its selected component.
    """

    selection_list = get_active_selection_list()

    if selection_list.length() == 0:
        raise RuntimeError("No Maya mesh selection found.")

    for index in range(selection_list.length()):
        try:
            return get_mesh_dag_from_selection_item(selection_list, index=index)
        except RuntimeError:
            continue

    raise RuntimeError("No selected Maya mesh found in active selection.")


def get_transform_path_from_shape(shape_dag_path) -> Optional[str]:
    """
    Return parent transform full path for a mesh shape dag path when possible.
    """

    om = _maya_api()

    try:
        dag_copy = om.MDagPath(shape_dag_path)
        dag_copy.pop()
        return dag_copy.fullPathName()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Edge component extraction
# ---------------------------------------------------------------------------

def edge_indices_from_component(component) -> List[int]:
    """
    Extract selected edge component ids from an MObject component.
    """

    om = _maya_api()

    if component is None or component.isNull():
        return []

    if component.apiType() != om.MFn.kMeshEdgeComponent:
        return []

    edge_fn = om.MFnSingleIndexedComponent(component)
    return sorted([int(edge_index) for edge_index in edge_fn.getElements()])


def selected_edge_indices_from_active_selection(mesh_dag_path=None) -> List[int]:
    """
    Return selected edge ids for the active selected mesh.

    If mesh_dag_path is provided, only components belonging to that mesh are
    collected.
    """

    selection_list = get_active_selection_list()
    edge_ids = set()

    target_path = None
    if mesh_dag_path is not None:
        target_path = dag_path_to_string(mesh_dag_path)

    for index in range(selection_list.length()):
        try:
            dag_path, component = get_mesh_dag_from_selection_item(selection_list, index=index)
        except RuntimeError:
            continue

        if target_path is not None and dag_path_to_string(dag_path) != target_path:
            continue

        for edge_id in edge_indices_from_component(component):
            edge_ids.add(edge_id)

    return sorted(edge_ids)


# ---------------------------------------------------------------------------
# Mesh pydata extraction
# ---------------------------------------------------------------------------

def mesh_vertices_to_pydata(mesh_fn, world_space=False) -> List[List[float]]:
    """
    Read mesh vertex coordinates.

    Default is object space because the solver should stay independent from Maya
    transform state. The write adapter can decide where/how to emit output.
    """

    om = _maya_api()
    space = om.MSpace.kWorld if world_space else om.MSpace.kObject
    points = mesh_fn.getPoints(space)

    return [[float(point.x), float(point.y), float(point.z)] for point in points]


def mesh_faces_to_pydata(mesh_fn) -> List[List[int]]:
    """
    Read mesh polygon vertex loops.
    """

    faces = []
    polygon_count = mesh_fn.numPolygons

    for polygon_index in range(polygon_count):
        vertices = mesh_fn.getPolygonVertices(polygon_index)
        faces.append([int(vertex_index) for vertex_index in vertices])

    return faces


def read_mesh_pydata(mesh_dag_path, world_space=False) -> Tuple[List[List[float]], List[List[int]]]:
    """
    Read a Maya mesh shape dag path into vertices/faces pydata.
    """

    om = _maya_api()
    mesh_fn = om.MFnMesh(mesh_dag_path)

    vertices = mesh_vertices_to_pydata(mesh_fn, world_space=world_space)
    faces = mesh_faces_to_pydata(mesh_fn)

    return vertices, faces


def read_selected_maya_mesh(world_space=False) -> MayaMeshReadResult:
    """
    Read the first selected Maya mesh plus selected edge ids.

    Selection should usually be edge component selection, e.g.:
        pCube1.e[0]

    Returns plain pydata for BX_bevelx.BX_bevel_main.bevel_pydata().
    """

    mesh_dag_path, component = get_first_selected_mesh_dag_path()
    vertices, faces = read_mesh_pydata(mesh_dag_path, world_space=world_space)

    selected_edges = edge_indices_from_component(component)

    # If first item is only transform/object selection, check entire active
    # selection for edge components on this mesh.
    if not selected_edges:
        selected_edges = selected_edge_indices_from_active_selection(mesh_dag_path)

    return MayaMeshReadResult(
        vertices=vertices,
        faces=faces,
        selected_edges=selected_edges,
        mesh_dag_path=dag_path_to_string(mesh_dag_path),
        transform_path=get_transform_path_from_shape(mesh_dag_path),
        shape_path=dag_path_to_string(mesh_dag_path),
    )


# ---------------------------------------------------------------------------
# Optional BMesh construction boundary
# ---------------------------------------------------------------------------

def read_selected_maya_mesh_as_bmesh(world_space=False):
    """
    Read selected Maya mesh and return:
        result, bm

    This function imports BX_bevelx only at this boundary so the core solver
    remains Maya-independent.
    """

    from BX_bevelx.BX_mesh_model import BMesh

    result = read_selected_maya_mesh(world_space=world_space)
    bm = BMesh.from_pydata(
        vertices=result.vertices,
        faces=result.faces,
    )

    return result, bm


# ---------------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------------

def debug_read_result(result: MayaMeshReadResult) -> List[str]:
    lines = []

    lines.append("MayaMeshRead mesh={0}".format(result.mesh_dag_path))
    lines.append("  transform={0}".format(result.transform_path))
    lines.append("  shape={0}".format(result.shape_path))
    lines.append("  vertices={0}".format(len(result.vertices)))
    lines.append("  faces={0}".format(len(result.faces)))
    lines.append("  selected_edges={0}".format(result.selected_edges))

    return lines


def print_selected_mesh_debug(world_space=False):
    result = read_selected_maya_mesh(world_space=world_space)
    for line in debug_read_result(result):
        print(line)
    return result


# ---------------------------------------------------------------------------
# Mesh data extraction API
# ---------------------------------------------------------------------------

import re

import maya.cmds as cmds
import maya.api.OpenMaya as om


def _get_selected_mesh_shape_path():
    """
    Return the selected mesh shape long path.

    Works when selecting:
        - transform
        - mesh shape
        - mesh components, like pCube1.e[0]

    Returns:
        str: long path to mesh shape
    """
    selection = cmds.ls(selection=True, long=True) or []

    if not selection:
        raise RuntimeError("No Maya selection found.")

    first = selection[0]

    # If component selection, strip component part:
    # |pCube1|pCubeShape1.e[0] -> |pCube1|pCubeShape1
    # |pCube1.e[0]             -> |pCube1
    node = first.split(".")[0]

    if not cmds.objExists(node):
        raise RuntimeError("Selected node does not exist: {}".format(node))

    node_type = cmds.nodeType(node)

    if node_type == "mesh":
        return cmds.ls(node, long=True)[0]

    if node_type == "transform":
        shapes = cmds.listRelatives(
            node,
            shapes=True,
            fullPath=True,
            noIntermediate=True
        ) or []

        mesh_shapes = [
            shape for shape in shapes
            if cmds.nodeType(shape) == "mesh"
        ]

        if not mesh_shapes:
            raise RuntimeError("Selected transform has no mesh shape: {}".format(node))

        return mesh_shapes[0]

    # Fallback: maybe selected object is not transform/shape but has a mesh shape below.
    shapes = cmds.listRelatives(
        node,
        shapes=True,
        fullPath=True,
        noIntermediate=True
    ) or []

    mesh_shapes = [
        shape for shape in shapes
        if cmds.nodeType(shape) == "mesh"
    ]

    if mesh_shapes:
        return mesh_shapes[0]

    raise RuntimeError("Selection is not a mesh or mesh component: {}".format(first))


def _get_dag_path(node):
    """
    Convert a Maya node path into an MDagPath.

    Args:
        node: Maya node path

    Returns:
        om.MDagPath
    """
    selection_list = om.MSelectionList()
    selection_list.add(node)
    return selection_list.getDagPath(0)


def _get_selected_edge_indices():
    """
    Return selected edge indices from current Maya selection.

    Returns:
        list[int]
    """
    edges = cmds.filterExpand(
        cmds.ls(selection=True, flatten=True) or [],
        selectionMask=32
    ) or []

    result = []

    for edge in edges:
        match = re.search(r"\.e\[(\d+)\]$", edge)
        if match:
            result.append(int(match.group(1)))

    return result


def _get_edge_data(dag_path, edge_index):
    """
    Return vertex IDs and connected faces for one edge.

    Args:
        dag_path: mesh MDagPath
        edge_index: edge ID

    Returns:
        dict
    """
    edge_it = om.MItMeshEdge(dag_path)
    edge_it.setIndex(edge_index)

    return {
        "edge_index": int(edge_index),
        "vertex_ids": [
            int(edge_it.vertexId(0)),
            int(edge_it.vertexId(1)),
        ],
        "connected_faces": [
            int(face_id) for face_id in edge_it.getConnectedFaces()
        ],
    }


def read_selected_mesh_data(world_space=False, include_selected_edges=True):
    """
    Read selected Maya mesh as simple Python mesh data.

    This is the main bridge-format function.

    Args:
        world_space:
            If True, returns vertex positions in world space.
            If False, returns vertex positions in object/local space.

        include_selected_edges:
            If True, includes selected edge IDs and edge data.

    Returns:
        dict:
            {
                "transform": str,
                "shape": str,
                "vertices": [(x, y, z), ...],
                "faces": [[v0, v1, v2, ...], ...],
                "selected_edges": [int, ...],
                "selected_edge_data": [
                    {
                        "edge_index": int,
                        "vertex_ids": [int, int],
                        "connected_faces": [int, ...],
                    },
                    ...
                ],
            }
    """
    shape = _get_selected_mesh_shape_path()
    transform_list = cmds.listRelatives(shape, parent=True, fullPath=True) or []
    transform = transform_list[0] if transform_list else None

    dag_path = _get_dag_path(shape)
    mesh_fn = om.MFnMesh(dag_path)

    space = om.MSpace.kWorld if world_space else om.MSpace.kObject

    points = mesh_fn.getPoints(space)
    vertices = [
        (float(point.x), float(point.y), float(point.z))
        for point in points
    ]

    faces = []
    face_normals = []

    for face_index in range(mesh_fn.numPolygons):
        face_vertices = mesh_fn.getPolygonVertices(face_index)
        faces.append([int(vertex_id) for vertex_id in face_vertices])

        normal = mesh_fn.getPolygonNormal(face_index, space)
        face_normals.append([
            float(normal.x),
            float(normal.y),
            float(normal.z),
        ])

    selected_edges = []
    selected_edge_data = []

    if include_selected_edges:
        selected_edges = _get_selected_edge_indices()
        selected_edge_data = [
            _get_edge_data(dag_path, edge_index)
            for edge_index in selected_edges
        ]

    return {
        "transform": transform,
        "shape": shape,
        "vertices": vertices,
        "faces": faces,
        "face_normals": face_normals,
        "selected_edges": selected_edges,
        "selected_edge_data": selected_edge_data,
    }


def print_mesh_data_debug(mesh_data):
    """
    Print mesh data returned by read_selected_mesh_data().
    """
    print("MayaMeshData")
    print("  transform={}".format(mesh_data.get("transform")))
    print("  shape={}".format(mesh_data.get("shape")))
    print("  vertices={}".format(len(mesh_data.get("vertices", []))))
    print("  faces={}".format(len(mesh_data.get("faces", []))))
    print("  face_normals={}".format(len(mesh_data.get("face_normals", []))))
    print("  selected_edges={}".format(mesh_data.get("selected_edges", [])))

    selected_edge_data = mesh_data.get("selected_edge_data", [])

    for edge_data in selected_edge_data:
        print("  edge {}".format(edge_data["edge_index"]))
        print("    vertex_ids={}".format(edge_data["vertex_ids"]))
        print("    connected_faces={}".format(edge_data["connected_faces"]))