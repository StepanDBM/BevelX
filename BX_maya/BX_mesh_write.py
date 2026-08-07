# BX_maya/BX_mesh_write.py
"""
Maya mesh writing helpers for BevelX.

Goal:
    Provide Blender-like mesh creation utilities.

Blender equivalent idea:
    mesh.from_pydata(vertices, edges, faces)
    mesh.update()

Maya version:
    create_mesh_from_pydata(vertices, faces, name="BX_mesh")

Notes:
    - Edges are currently inferred from faces by Maya.
    - This module should not contain bevel logic.
    - This module should only create, replace, or modify Maya mesh objects.
"""

from __future__ import annotations

import maya.cmds as cmds
import maya.api.OpenMaya as om


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _as_point_array(vertices):
    """
    Convert Python vertex tuples/lists into an OpenMaya MPointArray.

    Args:
        vertices: iterable of (x, y, z)

    Returns:
        om.MPointArray
    """
    points = om.MPointArray()

    for v in vertices:
        if len(v) != 3:
            raise ValueError("Each vertex must be a 3-value tuple/list: (x, y, z)")

        points.append(om.MPoint(float(v[0]), float(v[1]), float(v[2])))

    return points


def _flatten_faces(faces):
    """
    Convert face lists into polygon counts and flat connectivity.

    Example:
        faces = [
            [0, 1, 2, 3],
            [4, 5, 6, 7],
        ]

    Becomes:
        polygon_counts = [4, 4]
        polygon_connects = [0, 1, 2, 3, 4, 5, 6, 7]

    Args:
        faces: iterable of face index lists

    Returns:
        tuple[list[int], list[int]]
    """
    polygon_counts = []
    polygon_connects = []

    for face in faces:
        if len(face) < 3:
            raise ValueError("Each face must have at least 3 vertex indices.")

        polygon_counts.append(len(face))

        for index in face:
            polygon_connects.append(int(index))

    return polygon_counts, polygon_connects

def _sub_v3(a, b):
    return [
        a[0] - b[0],
        a[1] - b[1],
        a[2] - b[2],
    ]


def _cross_v3(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _normalize_v3(v):
    length = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5

    if length <= 1.0e-12:
        return [0.0, 0.0, 1.0]

    return [
        v[0] / length,
        v[1] / length,
        v[2] / length,
    ]


def _face_normal_from_vertices(vertices, face):
    """
    Compute polygon normal using Newell's method.

    This matches the polygon winding we emit.
    """
    if len(face) < 3:
        return [0.0, 0.0, 1.0]

    nx = 0.0
    ny = 0.0
    nz = 0.0

    for i, vertex_index in enumerate(face):
        current = vertices[vertex_index]
        nxt = vertices[face[(i + 1) % len(face)]]

        nx += (current[1] - nxt[1]) * (current[2] + nxt[2])
        ny += (current[2] - nxt[2]) * (current[0] + nxt[0])
        nz += (current[0] - nxt[0]) * (current[1] + nxt[1])

    return _normalize_v3([nx, ny, nz])


def _set_hard_face_vertex_normals(mesh_mobject, vertices, faces):
    """
    Set one explicit normal per face-vertex.

    This prevents Maya from averaging normals across shared vertices.
    Blender equivalent idea:
        split/loop normals on sharp edges.
    """
    mesh_fn = om.MFnMesh(mesh_mobject)

    normals = om.MVectorArray()
    face_ids = om.MIntArray()
    vertex_ids = om.MIntArray()

    for face_index, face in enumerate(faces):
        normal = _face_normal_from_vertices(vertices, face)
        maya_normal = om.MVector(normal[0], normal[1], normal[2])

        for vertex_index in face:
            normals.append(maya_normal)
            face_ids.append(int(face_index))
            vertex_ids.append(int(vertex_index))

    mesh_fn.setFaceVertexNormals(
        normals,
        face_ids,
        vertex_ids,
        om.MSpace.kObject
    )

def _validate_mesh_data(vertices, faces):
    """
    Basic validation before sending data to Maya.

    Args:
        vertices: list of vertex positions
        faces: list of face index lists
    """
    if not vertices:
        raise ValueError("Cannot create mesh: vertices list is empty.")

    if not faces:
        raise ValueError("Cannot create mesh: faces list is empty.")

    vertex_count = len(vertices)

    for face_id, face in enumerate(faces):
        if len(face) < 3:
            raise ValueError(
                "Invalid face {}: faces must have at least 3 vertices.".format(face_id)
            )

        for index in face:
            if index < 0 or index >= vertex_count:
                raise ValueError(
                    "Invalid vertex index {} in face {}. "
                    "Vertex count is {}.".format(index, face_id, vertex_count)
                )

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def create_mesh_from_pydata(vertices, faces, name="BX_mesh"):
    """
    Create a Maya polygon mesh from Python vertex and face data.

    Blender-style conceptual equivalent:
        mesh.from_pydata(vertices, [], faces)

    Args:
        vertices:
            List of vertex positions:
                [
                    (x, y, z),
                    (x, y, z),
                    ...
                ]

        faces:
            List of polygon faces using vertex indices:
                [
                    [0, 1, 2, 3],
                    [4, 5, 6, 7],
                    ...
                ]

        name:
            Desired transform name for the created mesh.

    Returns:
        dict:
            {
                "transform": str,
                "shape": str,
                "vertex_count": int,
                "face_count": int,
            }
    """
    vertices = list(vertices)
    faces = [list(face) for face in faces]

    _validate_mesh_data(vertices, faces)

    points = _as_point_array(vertices)
    polygon_counts, polygon_connects = _flatten_faces(faces)

    # Create the transform explicitly.
    transform = cmds.createNode("transform", name=name)

    # Get the transform MObject.
    selection_list = om.MSelectionList()
    selection_list.add(transform)
    transform_mobject = selection_list.getDependNode(0)

    # IMPORTANT:
    # Use parent= explicitly.
    # If transform_mobject is passed positionally, Maya thinks it is uValues.
    mesh_fn = om.MFnMesh()
    mesh_mobject = mesh_fn.create(
        points,
        polygon_counts,
        polygon_connects,
        parent=transform_mobject
    )
    _set_hard_face_vertex_normals(
        mesh_mobject=mesh_mobject,
        vertices=vertices,
        faces=faces,
    )

    # Rename the generated shape.
    shape_path = om.MDagPath.getAPathTo(mesh_mobject).fullPathName()

    short_transform_name = transform.split("|")[-1]
    shape = cmds.rename(shape_path, "{}Shape".format(short_transform_name))

    # Return long names.
    transform = cmds.ls(transform, long=True)[0]
    shape = cmds.ls(shape, long=True)[0]

    # Clean Maya mesh state.
    cmds.select(transform, replace=True)

    if cmds.objExists(transform):
        # Do NOT run polyNormal here.
        # The BevelX emitter already controls face winding.
        # Maya should derive normals from the polygon winding created by MFnMesh.
        cmds.delete(transform, constructionHistory=True)

        # Ensure the created mesh has a visible default material assignment.
        try:
            cmds.sets(transform, edit=True, forceElement="initialShadingGroup")
        except Exception:
            pass

    return {
        "transform": transform,
        "shape": shape,
        "vertex_count": len(vertices),
        "face_count": len(faces),
    }


def create_debug_cube(name="BX_debug_cube", size=1.0):
    """
    Create a simple cube using create_mesh_from_pydata.

    Useful for testing BX_mesh_write.py without depending on mesh read logic.

    Args:
        name: created mesh name
        size: cube size

    Returns:
        dict from create_mesh_from_pydata
    """
    h = float(size) * 0.5

    vertices = [
        (-h, -h, -h),  # 0
        ( h, -h, -h),  # 1
        ( h,  h, -h),  # 2
        (-h,  h, -h),  # 3
        (-h, -h,  h),  # 4
        ( h, -h,  h),  # 5
        ( h,  h,  h),  # 6
        (-h,  h,  h),  # 7
    ]

    faces = [
        [0, 1, 2, 3],  # back
        [4, 7, 6, 5],  # front
        [0, 4, 5, 1],  # bottom
        [1, 5, 6, 2],  # right
        [2, 6, 7, 3],  # top
        [3, 7, 4, 0],  # left
    ]

    return create_mesh_from_pydata(vertices, faces, name=name)

def _get_transform_shapes(transform):
    """
    Return non-intermediate mesh shapes under a transform.
    """
    shapes = cmds.listRelatives(
        transform,
        shapes=True,
        fullPath=True,
        noIntermediate=True
    ) or []

    return [
        shape for shape in shapes
        if cmds.nodeType(shape) == "mesh"
    ]


def replace_transform_mesh_from_pydata(transform, vertices, faces, shape_name=None):
    """
    Replace the mesh shape under an existing transform using Python mesh data.

    This is the first BevelX local-edit output mode.

    It keeps:
        - the original transform node
        - transform position / rotation / scale
        - object name

    It replaces:
        - the mesh shape topology

    Args:
        transform:
            Maya transform path or name.

        vertices:
            List of vertex positions in object/local space.

        faces:
            List of polygon faces using vertex indices.

        shape_name:
            Optional shape name. If None, uses '<transform>Shape'.

    Returns:
        dict:
            {
                "transform": str,
                "shape": str,
                "vertex_count": int,
                "face_count": int,
            }
    """
    if not transform or not cmds.objExists(transform):
        raise RuntimeError("Transform does not exist: {}".format(transform))

    transform = cmds.ls(transform, long=True)[0]

    vertices = list(vertices)
    faces = [list(face) for face in faces]

    _validate_mesh_data(vertices, faces)

    old_shapes = _get_transform_shapes(transform)

    # Delete old mesh shapes under the transform.
    for shape in old_shapes:
        try:
            cmds.delete(shape)
        except Exception:
            pass

    points = _as_point_array(vertices)
    polygon_counts, polygon_connects = _flatten_faces(faces)

    selection_list = om.MSelectionList()
    selection_list.add(transform)
    transform_mobject = selection_list.getDependNode(0)

    mesh_fn = om.MFnMesh()
    mesh_mobject = mesh_fn.create(
        points,
        polygon_counts,
        polygon_connects,
        parent=transform_mobject
    )

    # Apply hard face-vertex normals.
    _set_hard_face_vertex_normals(
        mesh_mobject=mesh_mobject,
        vertices=vertices,
        faces=faces,
    )

    shape_path = om.MDagPath.getAPathTo(mesh_mobject).fullPathName()

    short_transform_name = transform.split("|")[-1]

    if shape_name is None:
        shape_name = "{}Shape".format(short_transform_name)

    shape = cmds.rename(shape_path, shape_name)

    transform = cmds.ls(transform, long=True)[0]
    shape = cmds.ls(shape, long=True)[0]

    # Assign default material for now.
    try:
        cmds.sets(transform, edit=True, forceElement="initialShadingGroup")
    except Exception:
        pass

    cmds.select(transform, replace=True)

    return {
        "transform": transform,
        "shape": shape,
        "vertex_count": len(vertices),
        "face_count": len(faces),
    }

def delete_mesh(transform):
    """
    Delete a mesh transform if it exists.

    Args:
        transform: transform name or path

    Returns:
        bool: True if deleted, False if not found
    """
    if not transform or not cmds.objExists(transform):
        return False

    cmds.delete(transform)
    return True


def replace_mesh_from_pydata(target_transform, vertices, faces, name=None):
    """
    Replace an existing mesh object with a newly created mesh.

    This is intentionally simple for now:
        1. Delete target transform.
        2. Create new mesh from vertices/faces.
        3. Reuse target name unless name is provided.

    Args:
        target_transform: existing Maya transform to replace
        vertices: vertex position list
        faces: face index list
        name: optional new name

    Returns:
        dict from create_mesh_from_pydata
    """
    if not target_transform:
        raise ValueError("target_transform is required.")

    final_name = name or target_transform.split("|")[-1]

    if cmds.objExists(target_transform):
        cmds.delete(target_transform)

    return create_mesh_from_pydata(vertices, faces, name=final_name)


def print_created_mesh_debug(result):
    """
    Print simple creation result information.

    Args:
        result: dict returned by create_mesh_from_pydata
    """
    print("MayaMeshWrite result")
    print("  transform={}".format(result.get("transform")))
    print("  shape={}".format(result.get("shape")))
    print("  vertices={}".format(result.get("vertex_count")))
    print("  faces={}".format(result.get("face_count")))