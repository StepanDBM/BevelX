# BX_maya/BX_mesh_bridge.py
"""
Bridge helpers between BX_mesh_read.py and BX_mesh_write.py.

Purpose:
    Prove and maintain the Maya read/write loop:

        Maya selection
            -> Python mesh data
            -> New Maya mesh

This module should stay thin.
It should not contain bevel logic.
"""

from __future__ import annotations

from BX_maya.BX_mesh_read import read_selected_mesh_data
from BX_maya.BX_mesh_write import create_mesh_from_pydata


def duplicate_selected_mesh_as_pydata(
    name="BX_duplicate_test",
    world_space=False,
    select_result=True
):
    """
    Read the currently selected Maya mesh and create a duplicate from Python data.

    Args:
        name:
            Name for the new duplicated mesh.

        world_space:
            If False, duplicate uses object/local vertex positions.
            If True, duplicate uses world-space vertex positions.

        select_result:
            If True, BX_mesh_write will leave the created mesh selected.

    Returns:
        dict:
            {
                "source": {
                    "transform": str,
                    "shape": str,
                    "vertices": [...],
                    "faces": [...],
                    "selected_edges": [...],
                    "selected_edge_data": [...],
                },
                "created": {
                    "transform": str,
                    "shape": str,
                    "vertex_count": int,
                    "face_count": int,
                },
            }
    """
    mesh_data = read_selected_mesh_data(
        world_space=world_space,
        include_selected_edges=True
    )

    created = create_mesh_from_pydata(
        vertices=mesh_data["vertices"],
        faces=mesh_data["faces"],
        name=name
    )

    return {
        "source": mesh_data,
        "created": created,
    }


def print_bridge_debug(result):
    """
    Print debug information for duplicate_selected_mesh_as_pydata().
    """
    source = result.get("source", {})
    created = result.get("created", {})

    print("MayaMeshBridge result")

    print("  source_transform={}".format(source.get("transform")))
    print("  source_shape={}".format(source.get("shape")))
    print("  source_vertices={}".format(len(source.get("vertices", []))))
    print("  source_faces={}".format(len(source.get("faces", []))))
    print("  source_selected_edges={}".format(source.get("selected_edges", [])))

    print("  created_transform={}".format(created.get("transform")))
    print("  created_shape={}".format(created.get("shape")))
    print("  created_vertices={}".format(created.get("vertex_count")))
    print("  created_faces={}".format(created.get("face_count")))

    selected_edge_data = source.get("selected_edge_data", [])

    for edge_data in selected_edge_data:
        print("  selected_edge {}".format(edge_data["edge_index"]))
        print("    vertex_ids={}".format(edge_data["vertex_ids"]))
        print("    connected_faces={}".format(edge_data["connected_faces"]))

# ---------------------------------------------------------------------------
# Maya selection -> BevelX pipeline bridge
# ---------------------------------------------------------------------------

def _mesh_data_get(mesh_data, key, default=None):
    """
    Support both dict mesh_data and dataclass-like mesh data.
    """
    if isinstance(mesh_data, dict):
        return mesh_data.get(key, default)

    return getattr(mesh_data, key, default)


def _mesh_data_to_pydata(mesh_data):
    """
    Extract vertices, faces, and selected_edges from Maya read mesh_data.

    Supports:
        - dict returned by read_selected_mesh_data()
        - dataclass returned by read_selected_maya_mesh()
    """
    vertices = _mesh_data_get(mesh_data, "vertices", [])
    faces = _mesh_data_get(mesh_data, "faces", [])
    selected_edges = _mesh_data_get(mesh_data, "selected_edges", [])

    return vertices, faces, selected_edges

def _require_selected_edges(mesh_data):
    selected_edges = _mesh_data_get(mesh_data, "selected_edges", [])

    if not selected_edges:
        raise RuntimeError(
            "BevelX requires selected mesh edges. "
            "Select one or more edges, for example pCube1.e[0]."
        )

    return selected_edges

def debug_selected_mesh_bevel_pipeline(
    world_space=False,
    width=0.1,
    segments=1,
    profile=0.5,
    **param_overrides
):
    """
    Read selected Maya mesh and run the BevelX debug pipeline.

    This does not create a Maya output mesh.
    It prints the existing BevelX pipeline debug summary.

    This is the correct next smoke test because it uses the existing:
        BX_bevelx.BX_mesh_model.BMesh
        BX_bevelx.BX_build_bevverts
        BX_bevelx.BX_build_boundverts
        BX_bevelx.BX_build_vmesh
        BX_bevelx.BX_build_edge_polygons
        BX_bevelx.BX_rebuild_polygons
        BX_bevelx.BX_emit_maya_mesh
    """
    from BX_bevelx.BX_bevel_main import debug_bevel_pydata

    mesh_data = read_selected_mesh_data(world_space=world_space)
    vertices, faces, selected_edges = _mesh_data_to_pydata(mesh_data)
    selected_edges = _require_selected_edges(mesh_data)

    print("-- Source Mesh Normals --")
    face_normals = mesh_data.get("face_normals", [])

    for face_index, normal in enumerate(face_normals):
        print("SourceFace face={} normal={}".format(face_index, normal))

    lines = debug_bevel_pydata(
        vertices=vertices,
        faces=faces,
        selected_edges=selected_edges,
        width=width,
        segments=segments,
        profile=profile,
        **param_overrides
    )

    for line in lines:
        print(line)

    return {
        "mesh_data": mesh_data,
        "debug_lines": lines,
    }


def bevel_selected_mesh_to_new_mesh(
    name="BX_bevel_result",
    world_space=False,
    width=0.1,
    segments=1,
    profile=0.5,
    **param_overrides
):
    """
    Read selected Maya mesh, run the BevelX pydata bevel pipeline,
    and create a new Maya mesh from the result.

    This is the first real Maya -> BevelX -> Maya bridge.

    Returns:
        {
            "source": mesh_data,
            "created": created_mesh_result,
            "output_vertices": [...],
            "output_faces": [...],
        }
    """
    from BX_bevelx.BX_bevel_main import bevel_pydata

    mesh_data = read_selected_mesh_data(world_space=world_space)
    vertices, faces, selected_edges = _mesh_data_to_pydata(mesh_data)
    selected_edges = _require_selected_edges(mesh_data)

    output_vertices, output_faces = bevel_pydata(
        vertices=vertices,
        faces=faces,
        selected_edges=selected_edges,
        width=width,
        segments=segments,
        profile=profile,
        **param_overrides
    )

    created = create_mesh_from_pydata(
        vertices=output_vertices,
        faces=output_faces,
        name=name
    )

    return {
        "source": mesh_data,
        "created": created,
        "output_vertices": output_vertices,
        "output_faces": output_faces,
    }


def print_bevel_bridge_debug(result):
    """
    Print debug info from bevel_selected_mesh_to_new_mesh().
    """
    source = result.get("source")
    created = result.get("created", {})
    output_vertices = result.get("output_vertices", [])
    output_faces = result.get("output_faces", [])

    source_vertices = _mesh_data_get(source, "vertices", [])
    source_faces = _mesh_data_get(source, "faces", [])
    source_selected_edges = _mesh_data_get(source, "selected_edges", [])

    print("MayaBevelBridge result")
    print("  source_vertices={}".format(len(source_vertices)))
    print("  source_faces={}".format(len(source_faces)))
    print("  source_selected_edges={}".format(source_selected_edges))
    print("  output_vertices={}".format(len(output_vertices)))
    print("  output_faces={}".format(len(output_faces)))
    print("  created_transform={}".format(created.get("transform")))
    print("  created_shape={}".format(created.get("shape")))