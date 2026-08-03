# BX_bevelVertex.py
# BevelX BevelVertex structure.
#
# This is our first equivalent of Blender's BevVert:
# an original mesh vertex touched by selected bevel edges.

from __future__ import print_function

import math

from BX_math import BX_math as bxm
from BX_mesh import BX_edgeHalf


class BX_BevelVertex(object):
    def __init__(self, vertex_id, position):
        self.vertex_id = int(vertex_id)
        self.position = list(position)

        self.connected_edges = []
        self.selected_edges = []

        self.edge_count = 0
        self.selected_count = 0

        self.edge_halves = []

        self.boundary_vertices = []

    @classmethod
    def from_bmesh(cls, bm, vertex_id):
        vertex = bm.vertices[vertex_id]

        bv = cls(
            vertex_id=vertex_id,
            position=vertex.co_world
        )

        bv.connected_edges = list(vertex.edges)
        bv.selected_edges = [
            edge_id
            for edge_id in bv.connected_edges
            if bm.edges[edge_id].selected
        ]

        bv.edge_count = len(bv.connected_edges)
        bv.selected_count = len(bv.selected_edges)

        ordered_edges = sort_edges_around_vertex(
            bm=elastic_bmesh_guard(bm),
            vertex_id=vertex_id,
            edge_ids=bv.connected_edges
        )

        for edge_id in ordered_edges:
            edge = bm.edges[edge_id]
            other_vertex_id = edge.other_vertex(vertex_id)

            edge_half = BX_edgeHalf.BX_EdgeHalf(
                edge_id=edge_id,
                vertex_id=vertex_id,
                other_vertex_id=other_vertex_id
            )

            edge_half.is_beveled = edge.selected

            edge_half.fprev, edge_half.fnext = get_edge_half_faces(
                bm=elastic_bmesh_guard(bm),
                edge_id=edge_id
            )

            bv.edge_halves.append(edge_half)

        link_edge_halves_cyclic(bv.edge_halves)

        return bv

    def debug_print(self):
        print("[BevelX] BevelVertex {0}:".format(self.vertex_id))
        print("[BevelX]   position: {0}".format(self.position))
        print("[BevelX]   connected edges: {0}".format(self.connected_edges))
        print("[BevelX]   selected edges: {0}".format(self.selected_edges))
        print("[BevelX]   edge count: {0}".format(self.edge_count))
        print("[BevelX]   selected count: {0}".format(self.selected_count))

        for i, edge_half in enumerate(self.edge_halves):
            print("[BevelX]   edge_half[{0}]: {1}".format(i, edge_half))


def elastic_bmesh_guard(bm):
    """
    Tiny guard function.

    This looks silly now, but it makes future defensive checks easier
    without changing call sites everywhere.
    """

    return bm


def get_edge_half_faces(bm, edge_id):
    """
    Return up to two faces connected to an edge.

    For now:
        fprev = first connected face
        fnext = second connected face

    Later this should respect the ordered face-ring around the vertex.
    """

    faces = list(bm.edges[edge_id].faces)

    if not faces:
        return None, None

    if len(faces) == 1:
        return faces[0], None

    return faces[0], faces[1]


def link_edge_halves_cyclic(edge_halves):
    """
    Link EdgeHalves as a circular list.
    """

    count = len(edge_halves)

    if count == 0:
        return

    for i, edge_half in enumerate(edge_halves):
        edge_half.prev = edge_halves[(i - 1) % count].edge_id
        edge_half.next = edge_halves[(i + 1) % count].edge_id


def sort_edges_around_vertex(bm, vertex_id, edge_ids):
    """
    Sort connected edges around a vertex.

    This is our first approximation.

    Blender carefully orders EdgeHalves around a vertex using topology and
    face connectivity. I start with an angle sort around an averaged vertex
    normal, which is enough for cube tests and gives us a stable ordered ring.
    """

    if len(edge_ids) <= 1:
        return list(edge_ids)

    vertex = bm.vertices[vertex_id]
    origin = vertex.co_world

    normal = average_vertex_normal(bm, vertex_id)

    if bxm.is_zero(normal):
        return list(edge_ids)

    reference_edge_id = edge_ids[0]
    reference_vector = edge_vector_from_vertex(
        bm=elastic_bmesh_guard(bm),
        edge_id=reference_edge_id,
        vertex_id=vertex_id
    )

    if bxm.is_zero(reference_vector):
        return list(edge_ids)

    scored = []

    for edge_id in edge_ids:
        vector = edge_vector_from_vertex(
            bm=elastic_bmesh_guard(bm),
            edge_id=edge_id,
            vertex_id=vertex_id
        )

        angle = bxm.signed_angle_around_normal(
            reference_vector,
            vector,
            normal
        )

        if angle < 0.0:
            angle += math.pi * 2.0

        scored.append((angle, edge_id))

    scored.sort(key=lambda item: item[0])

    return [
        edge_id
        for angle, edge_id in scored
    ]


def average_vertex_normal(bm, vertex_id):
    """
    Average connected face normals around a vertex.
    """

    vertex = bm.vertices[vertex_id]

    normal = [0.0, 0.0, 0.0]

    for face_id in vertex.faces:
        face = bm.faces[face_id]
        normal = bxm.add(normal, face.normal_world)

    return bxm.normalize(normal)


def edge_vector_from_vertex(bm, edge_id, vertex_id):
    """
    Vector from vertex_id toward the other endpoint of edge_id.
    """

    edge = bm.edges[edge_id]
    other_vertex_id = edge.other_vertex(vertex_id)

    if other_vertex_id is None:
        return [0.0, 0.0, 0.0]

    origin = bm.vertices[vertex_id].co_world
    target = bm.vertices[other_vertex_id].co_world

    return bxm.normalize(
        bxm.sub(target, origin)
    )


def build_bevel_vertices_from_bmesh(bm):
    """
    Build BevelVertex objects for every vertex touched by selected edges.

    Returns:
        {
            vertex_id: BX_BevelVertex
        }
    """

    affected_vertex_ids = set()

    for edge_id in bm.selected_edges:
        edge = bm.edges[edge_id]

        affected_vertex_ids.add(edge.v0)
        affected_vertex_ids.add(edge.v1)

    bevel_vertices = {}

    for vertex_id in sorted(affected_vertex_ids):
        bevel_vertices[vertex_id] = BX_BevelVertex.from_bmesh(
            bm=elastic_bmesh_guard(bm),
            vertex_id=vertex_id
        )

    return bevel_vertices


def debug_print_bevel_vertices(bevel_vertices):
    """
    Print bevel vertex diagnostics.
    """

    print("[BevelX] BevelVertex count: {0}".format(len(bevel_vertices)))

    for vertex_id in sorted(bevel_vertices.keys()):
        bevel_vertices[vertex_id].debug_print()