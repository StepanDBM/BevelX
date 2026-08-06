# BX_bevelVertex.py
# BevelX BevelVertex structure.
#
# This is our first equivalent of Blender's BevVert:
# an original mesh vertex touched by selected bevel edges.

from __future__ import print_function

import math

from BX_math import BX_math as bxm
from BX_mesh import BX_edgeHalf
from BX_profile import BX_log


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
        """
        Log BevelVertex diagnostics.
        """

        if not BX_log.is_enabled("DEBUG", "selection"):
            return

        BX_log.debug("BevelVertex {0}:".format(self.vertex_id), channel="selection")
        BX_log.debug("  position: {0}".format(self.position), channel="selection")
        BX_log.debug("  connected edges: {0}".format(self.connected_edges), channel="selection")
        BX_log.debug("  selected edges: {0}".format(self.selected_edges), channel="selection")
        BX_log.debug("  edge count: {0}".format(self.edge_count), channel="selection")
        BX_log.debug("  selected count: {0}".format(self.selected_count), channel="selection")

        for i, edge_half in enumerate(self.edge_halves):
            BX_log.trace("  edge_half[{0}]: {1}".format(i, edge_half),
                channel="selection")


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
    Sort connected edges around a vertex using face topology first.

    Topology sort:
        - For every face touching vertex_id, find the two incident edges from edge_ids.
        - Those two edges are adjacent around the vertex.
        - Build a 2-neighbor ring from that adjacency.

    Fallback:
        If topology does not form a clean manifold ring, use the old angle-based sort.
    """

    if len(edge_ids) <= 1:
        return list(edge_ids)

    edge_ids = list(edge_ids)
    edge_set = set(edge_ids)
    vertex = bm.vertices[vertex_id]

    # -------------------------------------------------------------------------
    # 1. Build topology adjacency between incident edges.
    # -------------------------------------------------------------------------

    adjacency = {}

    for edge_id in edge_ids:
        adjacency[edge_id] = []

    for face_id in vertex.faces:
        face = bm.faces[face_id]
        incident_face_edges = []

        for face_edge_id in face.edges:
            if face_edge_id not in edge_set:
                continue

            edge = bm.edges[face_edge_id]

            if edge.other_vertex(vertex_id) is None:
                continue

            incident_face_edges.append(face_edge_id)

        if len(incident_face_edges) != 2:
            continue

        edge_a = incident_face_edges[0]
        edge_b = incident_face_edges[1]

        if edge_b not in adjacency[edge_a]:
            adjacency[edge_a].append(edge_b)

        if edge_a not in adjacency[edge_b]:
            adjacency[edge_b].append(edge_a)

    # -------------------------------------------------------------------------
    # 2. Try to walk a clean manifold ring.
    # -------------------------------------------------------------------------

    can_topology_sort = True

    for edge_id in edge_ids:
        if len(adjacency.get(edge_id, [])) != 2:
            can_topology_sort = False
            break

    if can_topology_sort:
        start_edge = edge_ids[0]
        ordered = None

        # Either neighbor can be the next edge depending on winding direction.
        # Try both and accept the first clean closed ring.
        for first_neighbor in adjacency[start_edge]:
            trial_order = [
                start_edge,
                first_neighbor
            ]

            previous_edge = start_edge
            current_edge = first_neighbor
            valid_walk = True

            while len(trial_order) < len(edge_ids):
                next_edge = None

                for candidate_edge in adjacency[current_edge]:
                    if candidate_edge != previous_edge:
                        next_edge = candidate_edge
                        break

                if next_edge is None:
                    valid_walk = False
                    break

                if next_edge in trial_order:
                    valid_walk = False
                    break

                trial_order.append(next_edge)

                previous_edge = current_edge
                current_edge = next_edge

            if not valid_walk:
                continue

            last_edge = trial_order[-1]

            if start_edge not in adjacency[last_edge]:
                continue

            ordered = trial_order
            break

        if ordered is not None:
            return ordered

    # -------------------------------------------------------------------------
    # 3. Fallback: old angle sort.
    # -------------------------------------------------------------------------

    normal = average_vertex_normal(
        bm=bm,
        vertex_id=vertex_id
    )

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


    # -------------------------------------------------------------------------
    # 3. Fallback: old angle sort.
    # -------------------------------------------------------------------------

    normal = average_vertex_normal(
        bm=bm,
        vertex_id=vertex_id
    )

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
    Log bevel vertex diagnostics.
    """
    if not BX_log.is_enabled("DEBUG", "selection"):
        return

    BX_log.debug("BevelVertex count: {0}".format(len(bevel_vertices)),
        channel="selection")

    for vertex_id in sorted(bevel_vertices.keys()):
        bevel_vertices[vertex_id].debug_print()