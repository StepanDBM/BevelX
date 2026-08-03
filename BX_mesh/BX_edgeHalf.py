# BX_edgeHalf.py
# BevelX EdgeHalf structure.
#
# Inspired by Blender's EdgeHalf concept:
# one edge, viewed from one endpoint vertex.

from __future__ import print_function


class BX_EdgeHalf(object):
    def __init__(self, edge_id, vertex_id, other_vertex_id):
        self.edge_id = int(edge_id)
        self.vertex_id = int(vertex_id)
        self.other_vertex_id = int(other_vertex_id)

        self.is_beveled = False

        self.prev = None
        self.next = None

        self.fprev = None
        self.fnext = None

        self.left_boundary = None
        self.right_boundary = None

        self.offset_left = 0.0
        self.offset_right = 0.0

    def __repr__(self):
        return (
            "BX_EdgeHalf(edge={0}, vertex={1}, other={2}, "
            "beveled={3}, prev={4}, next={5}, fprev={6}, fnext={7})"
        ).format(
            self.edge_id,
            self.vertex_id,
            self.other_vertex_id,
            self.is_beveled,
            self.prev,
            self.next,
            self.fprev,
            self.fnext,
        )