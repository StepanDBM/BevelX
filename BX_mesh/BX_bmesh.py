# BX_bmesh.py
# BevelX BMesh-lite topology model.
#
# This is not Blender BMesh.
# This is our own Maya-side topology graph inspired by BMesh:
#
# - BX_Vertex
# - BX_Edge
# - BX_Face
# - BX_Loop
# - BX_BMesh
#
# Current purpose:
# - Read Maya mesh once.
# - Build stable adjacency.
# - Let bevel code work on topology, not cmds strings.

from __future__ import print_function

import maya.cmds as cmds
import maya.api.OpenMaya as om

from BX_profile import BX_log


# -----------------------------------------------------------------------------
# Topology elements
# -----------------------------------------------------------------------------

class BX_Vertex(object):
    def __init__(self, vertex_id, co_local, co_world):
        self.id = int(vertex_id)

        self.co_local = list(co_local)
        self.co_world = list(co_world)

        self.edges = []
        self.faces = []
        self.loops = []

    def __repr__(self):
        return "BX_Vertex(id={0}, edges={1}, faces={2})".format(
            self.id,
            self.edges,
            self.faces
        )


class BX_Edge(object):
    def __init__(self, edge_id, v0, v1):
        self.id = int(edge_id)

        self.v0 = int(v0)
        self.v1 = int(v1)

        self.faces = []
        self.loops = []

        self.selected = False

    def vertices(self):
        return self.v0, self.v1

    def other_vertex(self, vertex_id):
        if vertex_id == self.v0:
            return self.v1

        if vertex_id == self.v1:
            return self.v0

        return None

    def key(self):
        return tuple(sorted((self.v0, self.v1)))

    def __repr__(self):
        return "BX_Edge(id={0}, v0={1}, v1={2}, faces={3}, selected={4})".format(
            self.id,
            self.v0,
            self.v1,
            self.faces,
            self.selected
        )


class BX_Face(object):
    def __init__(self, face_id, vertices, edges, normal_world, center_world):
        self.id = int(face_id)

        self.vertices = list(vertices)
        self.edges = list(edges)

        self.loops = []

        self.normal_world = list(normal_world)
        self.center_world = list(center_world)

        self.selected = False

    def __repr__(self):
        return "BX_Face(id={0}, verts={1}, edges={2})".format(
            self.id,
            self.vertices,
            self.edges
        )


class BX_Loop(object):
    """
    Face-corner loop.

    This is our first BMLoop-equivalent:
        face -> ordered loops
        loop -> vertex
        loop -> edge
        loop -> prev / next loop in same face
    """

    def __init__(self, loop_id, face_id, vertex_id, edge_id):
        self.id = int(loop_id)

        self.face_id = int(face_id)
        self.vertex_id = int(vertex_id)
        self.edge_id = int(edge_id)

        self.prev = None
        self.next = None

    def __repr__(self):
        return "BX_Loop(id={0}, face={1}, vert={2}, edge={3}, prev={4}, next={5})".format(
            self.id,
            self.face_id,
            self.vertex_id,
            self.edge_id,
            self.prev,
            self.next
        )


# -----------------------------------------------------------------------------
# BMesh-lite container
# -----------------------------------------------------------------------------

class BX_BMesh(object):
    def __init__(self):
        self.node = None
        self.shape = None
        self.dag_path = None

        self.vertices = {}
        self.edges = {}
        self.faces = {}
        self.loops = {}

        self.edge_key_to_id = {}

        self.selected_edges = []
        self.selected_vertices = []
        self.selected_faces = []

    # -------------------------------------------------------------------------
    # Construction
    # -------------------------------------------------------------------------

    @classmethod
    def from_selection(cls):
        """
        Build BX_BMesh from the current Maya selection.

        Supports:
            pCube1
            pCube1.e[5]
            pCube1.e[0:3]
            pCube1.vtx[2]
            pCube1.f[1]
        """

        selection = cmds.ls(selection=True, flatten=True) or []

        if not selection:
            raise RuntimeError("Nothing selected.")

        first = selection[0]
        node = first.split(".")[0]

        bm = cls.from_node(node)
        bm.read_component_selection(selection)

        return bm

    @classmethod
    def from_node(cls, node):
        """
        Build BX_BMesh from a Maya transform or mesh shape.
        """

        bm = cls()

        bm.node = get_transform_node(node)
        bm.shape = get_mesh_shape(node)
        bm.dag_path = get_mesh_dag_path(bm.shape)

        mesh_fn = om.MFnMesh(bm.dag_path)

        bm._read_vertices(mesh_fn)
        bm._read_edges(mesh_fn)
        bm._read_faces(mesh_fn)
        bm._build_adjacency()

        return bm

    def _read_vertices(self, mesh_fn):
        local_points = mesh_fn.getPoints(om.MSpace.kObject)
        world_points = mesh_fn.getPoints(om.MSpace.kWorld)

        for vertex_id in range(mesh_fn.numVertices):
            local = local_points[vertex_id]
            world = world_points[vertex_id]

            self.vertices[vertex_id] = BX_Vertex(
                vertex_id=vertex_id,
                co_local=[float(local.x), float(local.y), float(local.z)],
                co_world=[float(world.x), float(world.y), float(world.z)]
            )

    def _read_edges(self, mesh_fn):
        for edge_id in range(mesh_fn.numEdges):
            v0, v1 = mesh_fn.getEdgeVertices(edge_id)

            edge = BX_Edge(
                edge_id=edge_id,
                v0=v0,
                v1=v1
            )

            self.edges[edge_id] = edge
            self.edge_key_to_id[edge.key()] = edge_id

    def _read_faces(self, mesh_fn):
        loop_id = 0

        for face_id in range(mesh_fn.numPolygons):
            face_vertices = list(mesh_fn.getPolygonVertices(face_id))

            normal = mesh_fn.getPolygonNormal(face_id, om.MSpace.kWorld)
            center = calculate_face_center_world(mesh_fn, face_vertices)

            face_edges = []

            count = len(face_vertices)

            for i in range(count):
                v_current = face_vertices[i]
                v_next = face_vertices[(i + 1) % count]

                edge_key = tuple(sorted((v_current, v_next)))
                edge_id = self.edge_key_to_id[edge_key]

                face_edges.append(edge_id)

            face = BX_Face(
                face_id=face_id,
                vertices=face_vertices,
                edges=face_edges,
                normal_world=[float(normal.x), float(normal.y), float(normal.z)],
                center_world=center
            )

            self.faces[face_id] = face

            # Build loops.
            face_loop_ids = []

            for i in range(count):
                vertex_id = face_vertices[i]
                edge_id = face_edges[i]

                loop = BX_Loop(
                    loop_id=loop_id,
                    face_id=face_id,
                    vertex_id=vertex_id,
                    edge_id=edge_id
                )

                self.loops[loop_id] = loop
                face.loops.append(loop_id)
                face_loop_ids.append(loop_id)

                loop_id += 1

            # Link loop cycle.
            for i, current_loop_id in enumerate(face_loop_ids):
                prev_loop_id = face_loop_ids[(i - 1) % count]
                next_loop_id = face_loop_ids[(i + 1) % count]

                self.loops[current_loop_id].prev = prev_loop_id
                self.loops[current_loop_id].next = next_loop_id

    def _build_adjacency(self):
        """
        Fill vertex/edge/face/loop links.
        """

        for face_id, face in self.faces.items():
            for vertex_id in face.vertices:
                self.vertices[vertex_id].faces.append(face_id)

            for edge_id in face.edges:
                if face_id not in self.edges[edge_id].faces:
                    self.edges[edge_id].faces.append(face_id)

        for edge_id, edge in self.edges.items():
            self.vertices[edge.v0].edges.append(edge_id)
            self.vertices[edge.v1].edges.append(edge_id)

        for loop_id, loop in self.loops.items():
            self.vertices[loop.vertex_id].loops.append(loop_id)
            self.edges[loop.edge_id].loops.append(loop_id)

    # -------------------------------------------------------------------------
    # Selection
    # -------------------------------------------------------------------------

    def read_component_selection(self, selection):
        """
        Mark selected mesh components in this BX_BMesh.
        """

        for component in selection:
            if ".e[" in component:
                edge_ids = expand_component_indices(component)

                for edge_id in edge_ids:
                    if edge_id in self.edges:
                        self.edges[edge_id].selected = True
                        self.selected_edges.append(edge_id)

            elif ".vtx[" in component:
                vertex_ids = expand_component_indices(component)

                for vertex_id in vertex_ids:
                    if vertex_id in self.vertices:
                        self.selected_vertices.append(vertex_id)

            elif ".f[" in component:
                face_ids = expand_component_indices(component)

                for face_id in face_ids:
                    if face_id in self.faces:
                        self.faces[face_id].selected = True
                        self.selected_faces.append(face_id)

        self.selected_edges = sorted(list(set(self.selected_edges)))
        self.selected_vertices = sorted(list(set(self.selected_vertices)))
        self.selected_faces = sorted(list(set(self.selected_faces)))

    # -------------------------------------------------------------------------
    # Convenience query
    # -------------------------------------------------------------------------

    def selected_edge_objects(self):
        return [
            self.edges[edge_id]
            for edge_id in self.selected_edges
        ]

    def connected_edges_of_vertex(self, vertex_id):
        return list(self.vertices[vertex_id].edges)

    def connected_faces_of_vertex(self, vertex_id):
        return list(self.vertices[vertex_id].faces)

    def connected_faces_of_edge(self, edge_id):
        return list(self.edges[edge_id].faces)

    def loops_of_face(self, face_id):
        return [
            self.loops[loop_id]
            for loop_id in self.faces[face_id].loops
        ]

    def loops_of_vertex(self, vertex_id):
        return [
            self.loops[loop_id]
            for loop_id in self.vertices[vertex_id].loops
        ]

    def loops_of_edge(self, edge_id):
        return [
            self.loops[loop_id]
            for loop_id in self.edges[edge_id].loops
        ]

    # -------------------------------------------------------------------------
    # Debug
    # -------------------------------------------------------------------------

    def debug_print_summary(self):
        """
        Log BMesh summary diagnostics.
        """
        if not BX_log.is_enabled("DEBUG", "topology"):
            return

        BX_log.debug("BX_BMesh summary:", channel="topology")
        BX_log.debug("  Node: {0}".format(self.node), channel="topology")
        BX_log.debug("  Shape: {0}".format(self.shape), channel="topology")
        BX_log.debug("  Vertices: {0}".format(len(self.vertices)), channel="topology")
        BX_log.debug("  Edges: {0}".format(len(self.edges)), channel="topology")
        BX_log.debug("  Faces: {0}".format(len(self.faces)), channel="topology")
        BX_log.debug("  Loops: {0}".format(len(self.loops)), channel="topology")
        BX_log.debug("  Selected edges: {0}".format(self.selected_edges), channel="topology")
        BX_log.debug("  Selected vertices: {0}".format(self.selected_vertices), channel="topology")
        BX_log.debug("  Selected faces: {0}".format(self.selected_faces), channel="topology")

    def debug_print_selected_edges(self):
        """
        Log selected edge topology diagnostics.
        """
        if not BX_log.is_enabled("DEBUG", "topology"):
            return
        BX_log.debug("Selected edge topology:", channel="topology")
        for edge_id in self.selected_edges:
            edge = self.edges[edge_id]

            BX_log.debug("  Edge {0}: {1} -> {2}".format(
                    edge.id, edge.v0, edge.v1), channel="topology")
            BX_log.debug("    Faces: {0}".format(edge.faces),
                         channel="topology")
            BX_log.trace("    V0 connected edges: {0}".format(
                    self.vertices[edge.v0].edges), channel="topology")
            BX_log.trace("    V1 connected edges: {0}".format(
                    self.vertices[edge.v1].edges), channel="topology")
            BX_log.trace("    V0 faces: {0}".format(
                    self.vertices[edge.v0].faces), channel="topology")
            BX_log.trace("    V1 faces: {0}".format(
                self.vertices[edge.v1].faces),channel="topology")


# -----------------------------------------------------------------------------
# Maya helpers
# -----------------------------------------------------------------------------

def get_mesh_shape(node):
    """
    Given a transform or shape node, return the non-intermediate mesh shape.
    """

    if not cmds.objExists(node):
        raise RuntimeError("Node does not exist: {0}".format(node))

    node_type = cmds.nodeType(node)

    if node_type == "mesh":
        return node

    shapes = cmds.listRelatives(
        node,
        shapes=True,
        noIntermediate=True,
        fullPath=True
    ) or []

    mesh_shapes = [
        shape for shape in shapes
        if cmds.nodeType(shape) == "mesh"
    ]

    if not mesh_shapes:
        raise RuntimeError("No mesh shape found under: {0}".format(node))

    return mesh_shapes[0]


def get_transform_node(node):
    """
    Return transform node for a transform or shape.
    """

    if cmds.nodeType(node) == "mesh":
        parents = cmds.listRelatives(
            node,
            parent=True,
            fullPath=False
        ) or []

        if not parents:
            raise RuntimeError("Mesh shape has no transform parent: {0}".format(node))

        return parents[0]

    return node


def get_mesh_dag_path(node):
    """
    Return Maya API dag path for a mesh shape.
    """

    shape = get_mesh_shape(node)

    selection = om.MSelectionList()
    selection.add(shape)

    return selection.getDagPath(0)


def calculate_face_center_world(mesh_fn, vertex_ids):
    """
    Calculate world-space face center from polygon vertices.
    """

    points = mesh_fn.getPoints(om.MSpace.kWorld)

    center = [0.0, 0.0, 0.0]

    if not vertex_ids:
        return center

    for vertex_id in vertex_ids:
        point = points[vertex_id]

        center[0] += float(point.x)
        center[1] += float(point.y)
        center[2] += float(point.z)

    count = float(len(vertex_ids))

    return [
        center[0] / count,
        center[1] / count,
        center[2] / count,
    ]


def expand_component_indices(component):
    """
    Expand a simple Maya component string into integer indices.

    Supports:
        pCube1.e[5]
        pCube1.e[0:11]
        pCube1.vtx[3]
        pCube1.f[2:4]
    """

    if "[" not in component or "]" not in component:
        return []

    inside = component.split("[")[-1].split("]")[0]

    if ":" in inside:
        start, end = inside.split(":")
        start = int(start)
        end = int(end)

        return list(range(start, end + 1))

    return [int(inside)]