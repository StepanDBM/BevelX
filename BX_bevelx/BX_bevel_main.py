# BX_bevelx/BX_bevel_main.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from BX_bevelx.BX_mesh_model import BMesh
from BX_bevelx.BX_types import BevelParams
from BX_bevelx.BX_build_bevverts import bevel_vert_construct, debug_bevvert_summary
from BX_bevelx.BX_build_boundverts import build_boundverts, debug_boundvert_summary, debug_edgehalf_boundverts
from BX_bevelx.BX_build_vmesh import build_vmeshes, debug_vmesh_summary
from BX_bevelx.BX_build_edge_polygons import build_edge_polygons, debug_edge_polygon_summary
from BX_bevelx.BX_rebuild_polygons import rebuild_polygons, debug_rebuilt_polygon_summary
from BX_bevelx.BX_emit_maya_mesh import emit_vertices_faces, debug_emit_summary


@dataclass
class BevelPipelineResult:
    """
    Result of running the Blender-style Python bevel pipeline.

    This is solver output data, not a Maya transaction and not a legacy BevelX
    compatibility layer.
    """

    params: BevelParams
    bm: BMesh
    vertices: List[List[float]]
    faces: List[List[int]]


# ---------------------------------------------------------------------------
# Input normalization
# ---------------------------------------------------------------------------

def normalize_selected_edge_indices(bm: BMesh,
                                    selected_edges: Iterable[Any]) -> List[int]:
    """
    Normalize selected edges to BMesh edge indices.

    Accepts:
        - BMEdge objects
        - integer edge indices
    """

    result = []
    seen = set()

    for item in selected_edges:
        if hasattr(item, "index") and hasattr(item, "verts"):
            edge_index = int(item.index)
        else:
            edge_index = int(item)

        if edge_index < 0 or edge_index >= len(bm.edges):
            raise ValueError(
                "Selected edge index {0} is outside BMesh edge range 0..{1}".format(
                    edge_index,
                    len(bm.edges) - 1
                )
            )

        edge = bm.edges[edge_index]

        if not edge.is_valid:
            raise ValueError("Selected edge index {0} is not valid".format(edge_index))

        if edge_index in seen:
            continue

        seen.add(edge_index)
        result.append(edge_index)

    return result


def make_bevel_params(bm: BMesh,
                      width: float = 0.1,
                      segments: int = 1,
                      profile: float = 0.5,
                      **kwargs) -> BevelParams:
    """
    Create BevelParams using Blender-shaped names while keeping the current
    Python dataclass fields.
    """

    params = BevelParams(
        bm=bm,
        offset=float(width),
        seg=int(segments),
        profile=float(profile),
    )

    for key, value in kwargs.items():
        if not hasattr(params, key):
            raise AttributeError("BevelParams has no field named {0}".format(key))

        setattr(params, key, value)

    params.normalize()

    return params


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_bevel_pipeline_on_bmesh(bm: BMesh,
                                selected_edges: Iterable[Any],
                                params: Optional[BevelParams] = None,
                                width: float = 0.1,
                                segments: int = 1,
                                profile: float = 0.5,
                                **param_overrides) -> BevelPipelineResult:
    """
    Run the current Blender-style bevel pipeline on an internal BMesh.

    Pipeline:
        BMesh + selected edges
            -> BevVerts / EdgeHalves
            -> BoundVerts
            -> VMeshes
            -> selected-edge polygons
            -> rebuilt original polygons
            -> emitted vertices/faces
    """

    if bm is None:
        raise ValueError("run_bevel_pipeline_on_bmesh requires a BMesh")

    bm.normal_update()
    bm.index_update()

    selected_edge_indices = normalize_selected_edge_indices(
        bm=bm,
        selected_edges=selected_edges
    )

    if params is None:
        params = make_bevel_params(
            bm=bm,
            width=width,
            segments=segments,
            profile=profile,
            **param_overrides
        )
    else:
        params.bm = bm
        params.normalize()

    # Clear runtime containers so repeated calls with the same params are stable.
    params.vert_hash.clear()

    if hasattr(params, "generated_edge_polygons"):
        params.generated_edge_polygons = []

    if hasattr(params, "rebuilt_polygons"):
        params.rebuilt_polygons = []

    bevel_vert_construct(
        bm=bm,
        selected_edges=selected_edge_indices,
        params=params
    )

    build_boundverts(params)
    build_vmeshes(params)
    build_edge_polygons(params)
    rebuild_polygons(params)

    vertices, faces = emit_vertices_faces(params)

    return BevelPipelineResult(
        params=params,
        bm=bm,
        vertices=vertices,
        faces=faces
    )


def bevel_pydata(vertices: Sequence[Sequence[float]],
                 faces: Sequence[Sequence[int]],
                 selected_edges: Iterable[Any],
                 width: float = 0.1,
                 segments: int = 1,
                 profile: float = 0.5,
                 edges: Optional[Sequence[Sequence[int]]] = None,
                 **param_overrides) -> Tuple[List[List[float]], List[List[int]]]:
    """
    Convenience entry point for tests and non-Maya usage.

    Args:
        vertices: Input vertex coordinates.
        faces: Input polygon vertex indices.
        selected_edges: BMesh edge indices after from_pydata construction.
        width: Bevel offset amount.
        segments: Segment count.
        profile: Blender-style profile value.
        edges: Optional explicit edge list. If omitted, edges are inferred from faces.

    Returns:
        (output_vertices, output_faces)
    """

    bm = BMesh.from_pydata(
        vertices=vertices,
        edges=edges,
        faces=faces
    )

    result = run_bevel_pipeline_on_bmesh(
        bm=bm,
        selected_edges=selected_edges,
        width=width,
        segments=segments,
        profile=profile,
        **param_overrides
    )

    return result.vertices, result.faces


def bevel_pydata_result(vertices: Sequence[Sequence[float]],
                         faces: Sequence[Sequence[int]],
                         selected_edges: Iterable[Any],
                         width: float = 0.1,
                         segments: int = 1,
                         profile: float = 0.5,
                         edges: Optional[Sequence[Sequence[int]]] = None,
                         **param_overrides) -> BevelPipelineResult:
    """
    Same as bevel_pydata(), but returns BevelPipelineResult with params/debug data.
    """

    bm = BMesh.from_pydata(
        vertices=vertices,
        edges=edges,
        faces=faces
    )

    return run_bevel_pipeline_on_bmesh(
        bm=bm,
        selected_edges=selected_edges,
        width=width,
        segments=segments,
        profile=profile,
        **param_overrides
    )


# ---------------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------------

def debug_pipeline_summary(params: BevelParams) -> List[str]:
    """
    Collect debug summaries from each current pipeline phase.
    """

    lines = []

    lines.append("-- BevVerts --")
    lines.extend(debug_bevvert_summary(params))

    lines.append("-- BoundVerts --")
    lines.extend(debug_boundvert_summary(params))

    lines.append("-- EdgeHalf BoundVerts --")
    lines.extend(debug_edgehalf_boundverts(params))

    lines.append("-- VMeshes --")
    lines.extend(debug_vmesh_summary(params))

    lines.append("-- Edge Polygons --")
    lines.extend(debug_edge_polygon_summary(params))

    lines.append("-- Rebuilt Polygons --")
    lines.extend(debug_rebuilt_polygon_summary(params))

    lines.append("-- Emitted Mesh --")
    lines.extend(debug_emit_summary(params))

    return lines


def debug_bevel_pydata(vertices: Sequence[Sequence[float]],
                       faces: Sequence[Sequence[int]],
                       selected_edges: Iterable[Any],
                       width: float = 0.1,
                       segments: int = 1,
                       profile: float = 0.5,
                       edges: Optional[Sequence[Sequence[int]]] = None,
                       **param_overrides) -> List[str]:
    """
    Run bevel_pydata_result() and return full debug summary lines.
    """

    result = bevel_pydata_result(
        vertices=vertices,
        edges=edges,
        faces=faces,
        selected_edges=selected_edges,
        width=width,
        segments=segments,
        profile=profile,
        **param_overrides
    )

    return debug_pipeline_summary(result.params)
