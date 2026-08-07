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

from BX_maya.BX_undo import undo_chunk


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
    Extract vertices, edges, faces, and selected_edges.

    Critical:
        edges must be Maya edge-index order.
    """
    vertices = _mesh_data_get(mesh_data, "vertices", [])
    edges = _mesh_data_get(mesh_data, "edges", None)
    faces = _mesh_data_get(mesh_data, "faces", [])
    selected_edges = _mesh_data_get(mesh_data, "selected_edges", [])

    return vertices, edges, faces, selected_edges

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
    vertices, edges, faces, selected_edges = _mesh_data_to_pydata(mesh_data)
    selected_edges = _require_selected_edges(mesh_data)

    print("-- Source Mesh Normals --")
    face_normals = mesh_data.get("face_normals", [])

    for face_index, normal in enumerate(face_normals):
        print("SourceFace face={} normal={}".format(face_index, normal))

    lines = debug_bevel_pydata(
        vertices=vertices,
        edges=edges,
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

@undo_chunk("BevelX Apply Local")
def bevel_selected_mesh_in_place(
    world_space=False,
    width=0.1,
    segments=1,
    profile=0.5,
    **param_overrides
):
    """
    Read selected Maya mesh edges, run BevelX, and replace the original mesh
    shape under the same transform.

    This is closer to Blender's in-place BMesh bevel behavior than creating
    a separate result transform.
    """
    from BX_bevelx.BX_bevel_main import bevel_pydata
    from BX_maya.BX_mesh_write import replace_transform_mesh_from_pydata

    mesh_data = read_selected_mesh_data(world_space=world_space)

    selected_edges = _require_selected_edges(mesh_data)

    vertices, edges, faces, selected_edges = _mesh_data_to_pydata(mesh_data)

    output_vertices, output_faces = bevel_pydata(
        vertices=vertices,
        edges=edges,
        faces=faces,
        selected_edges=selected_edges,
        width=width,
        segments=segments,
        profile=profile,
        **param_overrides
    )

    transform = _mesh_data_get(mesh_data, "transform", None)

    if not transform:
        raise RuntimeError("Could not resolve selected mesh transform.")

    created = replace_transform_mesh_from_pydata(
        transform=transform,
        vertices=output_vertices,
        faces=output_faces,
    )

    return {
        "source": mesh_data,
        "created": created,
        "output_vertices": output_vertices,
        "output_faces": output_faces,
    }


def print_in_place_bevel_debug(result):
    """
    Print debug info for bevel_selected_mesh_in_place().
    """
    source = result.get("source")
    created = result.get("created", {})
    output_vertices = result.get("output_vertices", [])
    output_faces = result.get("output_faces", [])

    print("MayaInPlaceBevel result")
    print("  source_transform={}".format(_mesh_data_get(source, "transform", None)))
    print("  source_shape={}".format(_mesh_data_get(source, "shape", None)))
    print("  source_selected_edges={}".format(_mesh_data_get(source, "selected_edges", [])))
    print("  output_vertices={}".format(len(output_vertices)))
    print("  output_faces={}".format(len(output_faces)))
    print("  replaced_transform={}".format(created.get("transform")))
    print("  replaced_shape={}".format(created.get("shape")))