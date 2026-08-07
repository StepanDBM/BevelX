# BX_boundary/BX_vmesh_runtime.py

from __future__ import print_function

M_NONE = "M_NONE"
M_WELD = "M_WELD"
M_POLY = "M_POLY"
M_ADJ = "M_ADJ"

BOUNDVERT_SOURCE = "BOUNDVERT"


class BX_VMeshState(object):
    def __init__(self,
                 vertex_id,
                 selected_count,
                 edge_count,
                 boundary_count,
                 mesh_kind,
                 boundverts):
        self.vertex_id = int(vertex_id)
        self.selected_count = int(selected_count)
        self.edge_count = int(edge_count)
        self.boundary_count = int(boundary_count)
        self.mesh_kind = mesh_kind
        self.boundverts = list(boundverts)


def get_boundvert_list(vertex_boundaries, vertex_id):
    return [
        boundary
        for boundary in vertex_boundaries.get(vertex_id, [])
        if getattr(boundary, "source", None) == BOUNDVERT_SOURCE
    ]


def get_bevel_vertex(bevel_vertices, vertex_id):
    if bevel_vertices is None:
        return None

    if isinstance(bevel_vertices, dict):
        return bevel_vertices.get(vertex_id)

    for bevel_vertex in bevel_vertices:
        if getattr(bevel_vertex, "vertex_id", None) == vertex_id:
            return bevel_vertex

    return None


def get_selected_count(bevel_vertex):
    if bevel_vertex is None:
        return 0

    selected_edges = getattr(bevel_vertex, "selected_edges", None)
    if selected_edges is not None:
        return len(selected_edges)

    edge_halves = getattr(bevel_vertex, "edge_halves", [])
    return len([
        edge_half
        for edge_half in edge_halves
        if getattr(edge_half, "is_beveled", False)
        or getattr(edge_half, "is_bev", False)
        or getattr(edge_half, "beveled", False)
    ])


def classify_vmesh_kind(bevel_vertex, boundverts, settings=None):
    selected_count = get_selected_count(bevel_vertex)
    boundary_count = len(boundverts)
    segments = 1

    if settings:
        segments = int(settings.get("segments", 1))

    # Blender weld case:
    # const bool weld = (bv->selcount == 2) && (vm->count == 2);
    if selected_count == 2 and boundary_count == 2:
        return M_WELD

    if boundary_count < 3:
        return M_NONE

    if segments == 1:
        return M_POLY

    return M_ADJ


def build_vmesh_states(bevel_vertices, vertex_boundaries, settings=None):
    states = {}

    for vertex_id in sorted(vertex_boundaries.keys()):
        bevel_vertex = get_bevel_vertex(bevel_vertices, vertex_id)
        boundverts = get_boundvert_list(vertex_boundaries, vertex_id)

        if bevel_vertex is not None:
            edge_count = len(getattr(bevel_vertex, "edge_halves", []))
            selected_count = get_selected_count(bevel_vertex)
        else:
            edge_count = 0
            selected_count = 0

        mesh_kind = classify_vmesh_kind(
            bevel_vertex=bevel_vertex,
            boundverts=boundverts,
            settings=settings
        )

        states[vertex_id] = BX_VMeshState(
            vertex_id=vertex_id,
            selected_count=selected_count,
            edge_count=edge_count,
            boundary_count=len(boundverts),
            mesh_kind=mesh_kind,
            boundverts=boundverts
        )

    return states