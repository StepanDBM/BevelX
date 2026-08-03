# BX_build.py
# BevelX geometry application layer.
#
# Current milestone:
# - Apply BX_BevelTransaction to the current Maya mesh.
# - Local edit, not full mesh replacement.
# - One selected manifold edge supported.
# - Segments = 1 supported.

from __future__ import print_function

import maya.cmds as cmds
import maya.api.OpenMaya as om

from BX_build import BX_rebuild
# -----------------------------------------------------------------------------
# Maya mesh extraction
# -----------------------------------------------------------------------------

def get_mesh_dag_path(node):
    """
    Return Maya API dag path for a mesh transform or shape.
    """

    selection = om.MSelectionList()
    selection.add(node)

    return selection.getDagPath(0)
# -----------------------------------------------------------------------------
# Mesh creation
# -----------------------------------------------------------------------------

def world_point_to_object(point, world_to_object_matrix):
    """
    Convert a world-space point list to object-space point list.
    """

    maya_point = om.MPoint(
        point[0],
        point[1],
        point[2]
    )

    local_point = maya_point * world_to_object_matrix

    return [
        float(local_point.x),
        float(local_point.y),
        float(local_point.z),
    ]

# -----------------------------------------------------------------------------
# Transaction local edit apply
# -----------------------------------------------------------------------------
def apply_transaction_local_edit(bm, transaction, settings=None):
    """
    Apply a BX_BevelTransaction directly to the current Maya mesh.

    This does NOT rebuild the whole mesh.
    """

    if settings is None:
        settings = {}

    if transaction is None:
        print("[BevelX] Transaction apply failed: no transaction.")
        return None

    if not transaction.faces:
        print("[BevelX] Transaction apply failed: transaction has no faces.")
        return None

    source_node = bm.node

    cmds.undoInfo(openChunk=True, chunkName="BevelX Apply")

    try:
        # tx vertex id -> Maya vertex id
        tx_to_maya_vertex = {}

        # Existing original vertices already exist in the mesh.
        for tx_vertex in transaction.vertices:
            if tx_vertex.source == "ORIGINAL":
                tx_to_maya_vertex[tx_vertex.id] = tx_vertex.original_vertex_id

        world_to_object_matrix = bm.dag_path.inclusiveMatrixInverse()

        ordered_faces = get_transaction_faces_in_apply_order(transaction)

        cmds.select(source_node, replace=True)

        for face in ordered_faces:
            append_transaction_face(
                source_node=source_node,
                transaction=transaction,
                face=face,
                tx_to_maya_vertex=tx_to_maya_vertex,
                world_to_object_matrix=world_to_object_matrix
            )

        old_face_components = [
            "{0}.f[{1}]".format(source_node, face_id)
            for face_id in transaction.faces_to_replace
        ]

        if old_face_components:
            cmds.delete(old_face_components)

        try:
            cmds.polyMergeVertex(
                source_node,
                distance=0.000001,
                constructionHistory=False
            )
        except Exception:
            pass

        try:
            cmds.polySoftEdge(
                source_node,
                angle=30,
                constructionHistory=False
            )
        except Exception:
            pass

        cmds.select(source_node, replace=True)

        print("[BevelX] Transaction local edit applied to: {0}".format(source_node))

        print_post_apply_topology(source_node)

        return source_node

    finally:
        cmds.undoInfo(closeChunk=True)

def print_post_apply_topology(source_node):
    """
    Print mesh topology after transaction apply.
    """

    try:
        vertex_count = cmds.polyEvaluate(source_node, vertex=True)
        edge_count = cmds.polyEvaluate(source_node, edge=True)
        face_count = cmds.polyEvaluate(source_node, face=True)

        print("[BevelX] Mesh after transaction:")
        print("[BevelX]   vertices: {0}".format(vertex_count))
        print("[BevelX]   edges: {0}".format(edge_count))
        print("[BevelX]   faces: {0}".format(face_count))
        print_unused_vertices(source_node=source_node)
    except Exception as exc:
        print("[BevelX] Could not evaluate post-apply topology: {0}".format(exc))

def print_unused_vertices(source_node):
    """
    Debug helper to print isolated / unused vertices.
    """

    try:
        vertex_count = cmds.polyEvaluate(source_node, vertex=True)
        unused = []

        for vertex_id in range(vertex_count):
            connected_edges = cmds.polyListComponentConversion(
                "{0}.vtx[{1}]".format(source_node, vertex_id),
                fromVertex=True,
                toEdge=True
            ) or []

            connected_edges = cmds.ls(connected_edges, flatten=True) or []

            if not connected_edges:
                unused.append(vertex_id)

        print("[BevelX]   unused vertices: {0}".format(unused))

    except Exception as exc:
        print("[BevelX] Could not inspect unused vertices: {0}".format(exc))

def get_transaction_faces_in_apply_order(transaction):
    """
    Return transaction faces in the order needed for local application.
    """

    order = {
        "F_EDGE": 0,
        "F_VERT": 1,
        "F_RECON": 2,
    }

    return sorted(
        transaction.faces,
        key=lambda face: order.get(getattr(face, "kind", getattr(face, "face_kind", None)), 99)
    )


def append_transaction_face(source_node,
                            transaction,
                            face,
                            tx_to_maya_vertex,
                            world_to_object_matrix):
    """
    Append one transaction face to the Maya mesh.

    For each transaction vertex:
        - ORIGINAL source -> use existing Maya vertex ID.
        - BOUNDARY source -> if already created, use existing Maya vertex ID.
        - BOUNDARY source -> if not created yet, pass local-space coordinate tuple.
    """

    append_items = []
    new_tx_vertex_ids = []

    for tx_vertex_id in face.vertex_ids:
        if tx_vertex_id in tx_to_maya_vertex:
            append_items.append(int(tx_to_maya_vertex[tx_vertex_id]))
            continue

        tx_vertex = transaction.vertices[tx_vertex_id]

        local_point = world_point_to_object(
            tx_vertex.co_world,
            world_to_object_matrix
        )

        append_items.append(tuple(local_point))
        new_tx_vertex_ids.append(tx_vertex_id)

    new_maya_vertex_ids = append_face_and_return_new_vertices(
        source_node=source_node,
        append_items=append_items
    )

    if len(new_maya_vertex_ids) != len(new_tx_vertex_ids):
        raise RuntimeError(
            "Transaction apply failed: new vertex count mismatch. "
            "Expected {0}, got {1}".format(
                len(new_tx_vertex_ids),
                len(new_maya_vertex_ids)
            )
        )

    for tx_vertex_id, maya_vertex_id in zip(new_tx_vertex_ids, new_maya_vertex_ids):
        tx_to_maya_vertex[tx_vertex_id] = maya_vertex_id

    print("[BevelX]   Appended {0}: {1}".format(face.face_kind, face.vertex_ids))


def append_face_and_return_new_vertices(source_node, append_items):
    """
    Append a face to source_node using polyAppendVertex.

    append_items can contain:
        - existing vertex IDs as ints
        - new local-space points as tuples

    Returns:
        List of newly created Maya vertex IDs.
    """

    cmds.select(source_node, replace=True)

    old_vertex_count = cmds.polyEvaluate(
        source_node,
        vertex=True
    )

    cmds.polyAppendVertex(
        append=append_items,
        constructionHistory=False,
        texture=0
    )

    new_vertex_count = cmds.polyEvaluate(
        source_node,
        vertex=True
    )

    if new_vertex_count <= old_vertex_count:
        return []

    return list(range(old_vertex_count, new_vertex_count))