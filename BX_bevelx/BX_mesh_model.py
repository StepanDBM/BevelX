# BX_bevelx/BX_mesh_model.py

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from BX_bevelx.BX_constants import BEVEL_EPSILON
from BX_bevelx.BX_math_utils import (
    add_v3v3,
    copy_v3,
    cross_v3v3,
    dot_v3v3,
    len_v3,
    len_v3v3,
    mul_v3_fl,
    normalize_v3,
    normalized_v3,
    sub_v3v3,
    zero_v3,
)


# ---------------------------------------------------------------------------
# Element base
# ---------------------------------------------------------------------------

@dataclass
class BMElem:
    index: int = -1
    tag: bool = False
    select: bool = False
    hide: bool = False
    is_valid: bool = True

    # Blender has typed custom-data layers. This is a Python-side placeholder.
    data: Dict[str, Any] = field(default_factory=dict)

    def select_set(self, value: bool) -> None:
        self.select = bool(value)

    def copy_from(self, other: "BMElem") -> None:
        self.tag = other.tag
        self.select = other.select
        self.hide = other.hide
        self.data = dict(other.data)


# ---------------------------------------------------------------------------
# BMVert
# ---------------------------------------------------------------------------

@dataclass
class BMVert(BMElem):
    co: List[float] = field(default_factory=zero_v3)

    # Blender stores disk cycles. This Python model stores explicit adjacency
    # lists and rebuilds radial loop links deterministically.
    link_edges: List["BMEdge"] = field(default_factory=list)
    link_loops: List["BMLoop"] = field(default_factory=list)

    normal: List[float] = field(default_factory=zero_v3)

    def __hash__(self) -> int:
        return id(self)

    @property
    def is_wire(self) -> bool:
        return bool(self.link_edges) and all(edge.is_wire for edge in self.link_edges)

    @property
    def link_faces(self) -> List["BMFace"]:
        faces: List[BMFace] = []
        seen = set()

        for loop in self.link_loops:
            face = loop.f
            if face is None or not face.is_valid:
                continue

            face_id = id(face)
            if face_id in seen:
                continue

            seen.add(face_id)
            faces.append(face)

        return faces

    def normal_update(self) -> List[float]:
        total = zero_v3()

        for face in self.link_faces:
            total = add_v3v3(total, face.normal)

        _, normal = normalize_v3(total)
        self.normal = normal
        return self.normal

    def calc_shell_factor(self) -> float:
        """
        Equivalent-purpose helper for Blender's BMVert shell factor behavior.

        Blender uses shell factors to keep offset thickness stable around angled
        vertices. This Python model uses linked face normals and returns a
        conservative multiplier.
        """
        faces = self.link_faces

        if len(faces) < 2:
            return 1.0

        normal_sum = zero_v3()

        for face in faces:
            normal_sum = add_v3v3(normal_sum, face.normal)

        _, average_normal = normalize_v3(normal_sum)

        if len_v3(average_normal) <= BEVEL_EPSILON:
            return 1.0

        smallest_dot = 1.0

        for face in faces:
            face_dot = abs(dot_v3v3(average_normal, face.normal))
            if face_dot < smallest_dot:
                smallest_dot = face_dot

        if smallest_dot <= BEVEL_EPSILON:
            return 1.0

        return 1.0 / smallest_dot


# ---------------------------------------------------------------------------
# BMEdge
# ---------------------------------------------------------------------------

@dataclass
class BMEdge(BMElem):
    verts: Tuple[BMVert, BMVert] = field(default_factory=tuple)

    # Radial loop list around this edge.
    link_loops: List["BMLoop"] = field(default_factory=list)

    seam: bool = False
    smooth: bool = False

    def __hash__(self) -> int:
        return id(self)

    @property
    def v1(self) -> BMVert:
        return self.verts[0]

    @property
    def v2(self) -> BMVert:
        return self.verts[1]

    @property
    def link_faces(self) -> List["BMFace"]:
        faces: List[BMFace] = []
        seen = set()

        for loop in self.link_loops:
            face = loop.f
            if face is None or not face.is_valid:
                continue

            face_id = id(face)
            if face_id in seen:
                continue

            seen.add(face_id)
            faces.append(face)

        return faces

    @property
    def is_wire(self) -> bool:
        return len(self.link_faces) == 0

    @property
    def is_boundary(self) -> bool:
        return len(self.link_faces) == 1

    @property
    def is_manifold(self) -> bool:
        return len(self.link_faces) == 2

    def other_vert(self, vert: BMVert) -> Optional[BMVert]:
        if vert is self.verts[0]:
            return self.verts[1]

        if vert is self.verts[1]:
            return self.verts[0]

        return None

    def calc_length(self) -> float:
        return len_v3v3(self.verts[0].co, self.verts[1].co)

    def calc_face_angle(self) -> Optional[float]:
        faces = self.link_faces

        if len(faces) != 2:
            return None

        n0 = faces[0].normal
        n1 = faces[1].normal
        dot_value = max(-1.0, min(1.0, dot_v3v3(n0, n1)))
        return math.acos(dot_value)

    def normal_update(self) -> None:
        self.verts[0].normal_update()
        self.verts[1].normal_update()


# ---------------------------------------------------------------------------
# BMLoop
# ---------------------------------------------------------------------------

@dataclass
class BMLoop(BMElem):
    # Start vertex of this face corner.
    v: Optional[BMVert] = None

    # Edge from this loop's vertex to next loop's vertex.
    e: Optional[BMEdge] = None

    # Owning face.
    f: Optional["BMFace"] = None

    # Face loop links.
    link_loop_next: Optional["BMLoop"] = None
    link_loop_prev: Optional["BMLoop"] = None

    # Radial links around edge.
    link_loop_radial_next: Optional["BMLoop"] = None
    link_loop_radial_prev: Optional["BMLoop"] = None

    def __hash__(self) -> int:
        return id(self)

    @property
    def next(self) -> Optional["BMLoop"]:
        return self.link_loop_next

    @property
    def prev(self) -> Optional["BMLoop"]:
        return self.link_loop_prev

    @property
    def radial_next(self) -> Optional["BMLoop"]:
        return self.link_loop_radial_next

    @property
    def radial_prev(self) -> Optional["BMLoop"]:
        return self.link_loop_radial_prev

    def calc_angle(self) -> float:
        """Angle at this loop vertex inside the owning face."""
        if self.prev is None or self.next is None or self.v is None:
            return 0.0

        a = self.prev.v.co
        b = self.v.co
        c = self.next.v.co

        ba = normalized_v3(sub_v3v3(a, b))
        bc = normalized_v3(sub_v3v3(c, b))

        dot_value = max(-1.0, min(1.0, dot_v3v3(ba, bc)))
        return math.acos(dot_value)

    def calc_tangent(self) -> List[float]:
        """Tangent along this loop edge from loop.v to loop.next.v."""
        if self.next is None or self.v is None:
            return zero_v3()

        return normalized_v3(sub_v3v3(self.next.v.co, self.v.co))


# ---------------------------------------------------------------------------
# BMFace
# ---------------------------------------------------------------------------

@dataclass
class BMFace(BMElem):
    loops: List[BMLoop] = field(default_factory=list)
    normal: List[float] = field(default_factory=zero_v3)
    smooth: bool = False
    material_index: int = 0

    def __hash__(self) -> int:
        return id(self)

    @property
    def verts(self) -> List[BMVert]:
        return [loop.v for loop in self.loops]

    @property
    def edges(self) -> List[BMEdge]:
        return [loop.e for loop in self.loops]

    @property
    def len(self) -> int:
        return len(self.loops)

    def calc_center_median(self) -> List[float]:
        if not self.loops:
            return zero_v3()

        total = zero_v3()

        for loop in self.loops:
            total = add_v3v3(total, loop.v.co)

        return mul_v3_fl(total, 1.0 / float(len(self.loops)))

    def calc_area(self) -> float:
        """Polygon area computed by fan triangulation around vertex 0."""
        verts = self.verts

        if len(verts) < 3:
            return 0.0

        origin = verts[0].co
        area = 0.0

        for i in range(1, len(verts) - 1):
            a = sub_v3v3(verts[i].co, origin)
            b = sub_v3v3(verts[i + 1].co, origin)
            area += 0.5 * len_v3(cross_v3v3(a, b))

        return area

    def calc_normal(self) -> List[float]:
        """
        Newell-style polygon normal. Works for ngons better than only using the
        first three vertices.
        """
        verts = self.verts

        if len(verts) < 3:
            self.normal = zero_v3()
            return self.normal

        nx = 0.0
        ny = 0.0
        nz = 0.0
        count = len(verts)

        for i in range(count):
            current = verts[i].co
            nxt = verts[(i + 1) % count].co

            nx += (current[1] - nxt[1]) * (current[2] + nxt[2])
            ny += (current[2] - nxt[2]) * (current[0] + nxt[0])
            nz += (current[0] - nxt[0]) * (current[1] + nxt[1])

        _, normal = normalize_v3([nx, ny, nz])
        self.normal = normal
        return self.normal

    def normal_update(self) -> List[float]:
        return self.calc_normal()

    def normal_flip(self) -> None:
        """Reverse face winding and restore loop links."""
        self.loops.reverse()

        for i, loop in enumerate(self.loops):
            loop.link_loop_prev = self.loops[(i - 1) % len(self.loops)]
            loop.link_loop_next = self.loops[(i + 1) % len(self.loops)]

        self.calc_normal()


# ---------------------------------------------------------------------------
# Element sequence helpers
# ---------------------------------------------------------------------------

class BMElemSeq(list):
    def index_update(self) -> None:
        for index, element in enumerate(self):
            element.index = index

    def ensure_lookup_table(self) -> None:
        # Blender API compatibility no-op.
        return None


class BMVertSeq(BMElemSeq):
    pass


class BMEdgeSeq(BMElemSeq):
    def get(self, verts, fallback=None):
        if len(verts) != 2:
            return fallback

        v1, v2 = verts

        for edge in self:
            if not edge.is_valid:
                continue

            if (edge.verts[0] is v1 and edge.verts[1] is v2) or (
                edge.verts[0] is v2 and edge.verts[1] is v1
            ):
                return edge

        return fallback


class BMFaceSeq(BMElemSeq):
    def get(self, verts, fallback=None):
        target = set(verts)

        for face in self:
            if not face.is_valid:
                continue

            if set(face.verts) == target:
                return face

        return fallback


class BMLoopSeq(BMElemSeq):
    pass


# ---------------------------------------------------------------------------
# BMesh
# ---------------------------------------------------------------------------

class BMesh:
    """
    Blender-shaped internal mesh model.

    This is not a Maya transaction object.
    This is the topology model the Blender-style bevel solver will run on.

    BMesh stores:
        - verts
        - edges
        - faces
        - loops

    Loops define face boundaries and radial edge ownership.
    """

    def __init__(self):
        self.verts = BMVertSeq()
        self.edges = BMEdgeSeq()
        self.faces = BMFaceSeq()
        self.loops = BMLoopSeq()

        self.select_mode = {"VERT", "EDGE", "FACE"}
        self.select_history = []

        self.is_valid = True
        self.is_wrapped = False

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def verts_new(self, co=(0.0, 0.0, 0.0), example: Optional[BMVert] = None) -> BMVert:
        vert = BMVert(co=copy_v3(co))

        if example is not None:
            vert.copy_from(example)

        vert.index = len(self.verts)
        self.verts.append(vert)
        return vert

    def edges_new(self, verts: Sequence[BMVert], example: Optional[BMEdge] = None) -> BMEdge:
        if len(verts) != 2:
            raise ValueError("BMEdge requires exactly two verts")

        v1, v2 = verts
        existing = self.edges.get((v1, v2), None)

        if existing is not None:
            return existing

        edge = BMEdge(verts=(v1, v2))

        if example is not None:
            edge.copy_from(example)
            edge.seam = example.seam
            edge.smooth = example.smooth

        edge.index = len(self.edges)
        self.edges.append(edge)

        v1.link_edges.append(edge)
        v2.link_edges.append(edge)
        return edge

    def faces_new(self, verts: Sequence[BMVert], example: Optional[BMFace] = None) -> BMFace:
        if len(verts) < 3:
            raise ValueError("BMFace requires at least three verts")

        face = BMFace()

        if example is not None:
            face.copy_from(example)
            face.smooth = example.smooth
            face.material_index = example.material_index

        face.index = len(self.faces)
        self.faces.append(face)

        count = len(verts)
        face_loops: List[BMLoop] = []

        for i in range(count):
            v_current = verts[i]
            v_next = verts[(i + 1) % count]
            edge = self.edges_new((v_current, v_next))

            loop = BMLoop(v=v_current, e=edge, f=face)
            loop.index = len(self.loops)
            self.loops.append(loop)
            face_loops.append(loop)

            v_current.link_loops.append(loop)
            edge.link_loops.append(loop)

        for i, loop in enumerate(face_loops):
            loop.link_loop_prev = face_loops[(i - 1) % count]
            loop.link_loop_next = face_loops[(i + 1) % count]

        face.loops = face_loops
        face.calc_normal()
        self.rebuild_radial_cycles_for_edges([loop.e for loop in face_loops])
        return face

    # Blender-like aliases.
    def vert_new(self, co=(0.0, 0.0, 0.0), example: Optional[BMVert] = None) -> BMVert:
        return self.verts_new(co=co, example=example)

    def edge_new(self, verts: Sequence[BMVert], example: Optional[BMEdge] = None) -> BMEdge:
        return self.edges_new(verts=verts, example=example)

    def face_new(self, verts: Sequence[BMVert], example: Optional[BMFace] = None) -> BMFace:
        return self.faces_new(verts=verts, example=example)

    # ------------------------------------------------------------------
    # Radial cycles
    # ------------------------------------------------------------------

    def rebuild_radial_cycles(self) -> None:
        for edge in self.edges:
            self.rebuild_radial_cycle(edge)

    def rebuild_radial_cycles_for_edges(self, edges: Iterable[BMEdge]) -> None:
        seen = set()

        for edge in edges:
            edge_id = id(edge)
            if edge_id in seen:
                continue

            seen.add(edge_id)
            self.rebuild_radial_cycle(edge)

    def rebuild_radial_cycle(self, edge: BMEdge) -> None:
        loops = [loop for loop in edge.link_loops if loop.is_valid and loop.f is not None and loop.f.is_valid]
        edge.link_loops = loops

        if not loops:
            return

        count = len(loops)

        for i, loop in enumerate(loops):
            loop.link_loop_radial_prev = loops[(i - 1) % count]
            loop.link_loop_radial_next = loops[(i + 1) % count]

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def edge_between(self, v1: BMVert, v2: BMVert) -> Optional[BMEdge]:
        return self.edges.get((v1, v2), None)

    def face_from_verts(self, verts: Sequence[BMVert]) -> Optional[BMFace]:
        return self.faces.get(verts, None)

    def loop_for_face_vert(self, face: BMFace, vert: BMVert) -> Optional[BMLoop]:
        for loop in face.loops:
            if loop.v is vert:
                return loop
        return None

    def loops_of_vert(self, vert: BMVert) -> List[BMLoop]:
        return [loop for loop in vert.link_loops if loop.is_valid and loop.f is not None and loop.f.is_valid]

    def edges_of_vert(self, vert: BMVert) -> List[BMEdge]:
        return [edge for edge in vert.link_edges if edge.is_valid]

    def faces_of_vert(self, vert: BMVert) -> List[BMFace]:
        return vert.link_faces

    def common_faces_of_edges(self, edge_a: BMEdge, edge_b: BMEdge) -> List[BMFace]:
        faces_a = set(edge_a.link_faces)
        faces_b = set(edge_b.link_faces)
        return [face for face in self.faces if face in faces_a and face in faces_b and face.is_valid]

    def face_between_edges_at_vert(self, vert: BMVert, edge_a: BMEdge, edge_b: BMEdge) -> Optional[BMFace]:
        """Return a face that uses both edges at the given vertex."""
        for face in vert.link_faces:
            uses_a = False
            uses_b = False

            for loop in face.loops:
                if loop.e is edge_a:
                    uses_a = True
                if loop.e is edge_b:
                    uses_b = True

            if uses_a and uses_b:
                return face

        return None

    def loop_between_edges_at_vert(self, vert: BMVert, edge_prev: BMEdge, edge_next: BMEdge) -> Optional[BMLoop]:
        """
        Return the loop whose corner vertex is vert and whose previous and next
        edges match the provided pair.
        """
        for loop in self.loops_of_vert(vert):
            if loop.prev is None or loop.next is None:
                continue

            if loop.prev.e is edge_prev and loop.e is edge_next:
                return loop

        return None

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------

    def remove_face(self, face: BMFace) -> None:
        if not face.is_valid:
            return

        affected_edges: List[BMEdge] = []

        for loop in list(face.loops):
            if loop.v is not None and loop in loop.v.link_loops:
                loop.v.link_loops.remove(loop)

            if loop.e is not None:
                affected_edges.append(loop.e)
                if loop in loop.e.link_loops:
                    loop.e.link_loops.remove(loop)

            loop.is_valid = False

        face.is_valid = False
        self.rebuild_radial_cycles_for_edges(affected_edges)

    def remove_edge(self, edge: BMEdge) -> None:
        if not edge.is_valid:
            return

        for loop in list(edge.link_loops):
            if loop.f is not None and loop.f.is_valid:
                self.remove_face(loop.f)

        for vert in edge.verts:
            if edge in vert.link_edges:
                vert.link_edges.remove(edge)

        edge.is_valid = False

    def remove_vert(self, vert: BMVert) -> None:
        if not vert.is_valid:
            return

        for edge in list(vert.link_edges):
            self.remove_edge(edge)

        vert.is_valid = False

    # ------------------------------------------------------------------
    # Normal / selection / index maintenance
    # ------------------------------------------------------------------

    def normal_update(self) -> None:
        for face in self.faces:
            if face.is_valid:
                face.normal_update()

        for vert in self.verts:
            if vert.is_valid:
                vert.normal_update()

    def index_update(self) -> None:
        self.verts.index_update()
        self.edges.index_update()
        self.faces.index_update()
        self.loops.index_update()

    def select_flush(self, select: bool) -> None:
        for vert in self.verts:
            if vert.is_valid:
                vert.select_set(select)

        for edge in self.edges:
            if edge.is_valid:
                edge.select_set(select)

        for face in self.faces:
            if face.is_valid:
                face.select_set(select)

    def select_flush_mode(self, flush_down: bool = False) -> None:
        """
        Minimal Blender API-compatible selection flush.

        If a face is selected, select its edges and verts.
        If an edge is selected, select its verts.
        """
        if not flush_down:
            return

        for face in self.faces:
            if not face.is_valid or not face.select:
                continue

            for loop in face.loops:
                loop.e.select = True
                loop.v.select = True

        for edge in self.edges:
            if not edge.is_valid or not edge.select:
                continue

            edge.verts[0].select = True
            edge.verts[1].select = True

    # ------------------------------------------------------------------
    # Mesh-wide utilities
    # ------------------------------------------------------------------

    def calc_loop_triangles(self) -> List[Tuple[BMLoop, BMLoop, BMLoop]]:
        """Simple fan tessellation. Enough for debug and area checks."""
        triangles: List[Tuple[BMLoop, BMLoop, BMLoop]] = []

        for face in self.faces:
            if not face.is_valid or len(face.loops) < 3:
                continue

            root = face.loops[0]

            for i in range(1, len(face.loops) - 1):
                triangles.append((root, face.loops[i], face.loops[i + 1]))

        return triangles

    def calc_volume(self, signed: bool = False) -> float:
        """Signed volume by triangulated tetrahedra against origin."""
        volume = 0.0

        for tri in self.calc_loop_triangles():
            a = tri[0].v.co
            b = tri[1].v.co
            c = tri[2].v.co
            volume += dot_v3v3(a, cross_v3v3(b, c)) / 6.0

        if signed:
            return volume

        return abs(volume)

    def transform(self, matrix, filter=None) -> None:
        """
        Apply a 4x4 matrix-like object/list to vertices.

        matrix can be:
            - nested list matrix[row][col]
            - object supporting matrix @ [x, y, z, 1]
        """
        for vert in self.verts:
            if not vert.is_valid:
                continue

            if filter is not None:
                if "SELECT" in filter and not vert.select:
                    continue
                if "HIDE" in filter and not vert.hide:
                    continue
                if "TAG" in filter and not vert.tag:
                    continue

            x, y, z = vert.co

            if hasattr(matrix, "__matmul__"):
                result = matrix @ [x, y, z, 1.0]
                vert.co = [result[0], result[1], result[2]]
            else:
                vert.co = [
                    matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
                    matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
                    matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
                ]

        self.normal_update()

    def clear(self) -> None:
        for vert in self.verts:
            vert.is_valid = False

        for edge in self.edges:
            edge.is_valid = False

        for loop in self.loops:
            loop.is_valid = False

        for face in self.faces:
            face.is_valid = False

        self.verts[:] = []
        self.edges[:] = []
        self.loops[:] = []
        self.faces[:] = []

    def free(self) -> None:
        self.clear()
        self.is_valid = False

    def copy(self) -> "BMesh":
        """Deep topology copy preserving vertex/edge/face order."""
        new_bm = BMesh()
        vert_map: Dict[BMVert, BMVert] = {}

        for vert in self.verts:
            if not vert.is_valid:
                continue

            new_vert = new_bm.verts_new(vert.co)
            new_vert.copy_from(vert)
            new_vert.normal = copy_v3(vert.normal)
            vert_map[vert] = new_vert

        for face in self.faces:
            if not face.is_valid:
                continue

            new_face_verts = [vert_map[vert] for vert in face.verts]
            new_face = new_bm.faces_new(new_face_verts)
            new_face.copy_from(face)
            new_face.smooth = face.smooth
            new_face.material_index = face.material_index

        new_bm.normal_update()
        new_bm.index_update()
        return new_bm

    # ------------------------------------------------------------------
    # Construction from raw arrays
    # ------------------------------------------------------------------

    @classmethod
    def from_pydata(
        cls,
        vertices: Sequence[Sequence[float]],
        edges: Optional[Sequence[Sequence[int]]] = None,
        faces: Optional[Sequence[Sequence[int]]] = None,
    ) -> "BMesh":
        bm = cls()
        bm_verts = [bm.verts_new(co) for co in vertices]

        if edges:
            for edge_indices in edges:
                bm.edges_new((bm_verts[edge_indices[0]], bm_verts[edge_indices[1]]))

        if faces:
            for face_indices in faces:
                bm.faces_new([bm_verts[index] for index in face_indices])

        bm.normal_update()
        bm.index_update()
        return bm

    def to_pydata(self):
        vert_indices: Dict[BMVert, int] = {}
        vertices: List[List[float]] = []

        for vert in self.verts:
            if not vert.is_valid:
                continue

            vert_indices[vert] = len(vertices)
            vertices.append(copy_v3(vert.co))

        edges: List[List[int]] = []

        for edge in self.edges:
            if not edge.is_valid:
                continue

            if edge.verts[0] not in vert_indices or edge.verts[1] not in vert_indices:
                continue

            edges.append([
                vert_indices[edge.verts[0]],
                vert_indices[edge.verts[1]],
            ])

        faces: List[List[int]] = []

        for face in self.faces:
            if not face.is_valid:
                continue

            face_indices: List[int] = []

            for vert in face.verts:
                if vert not in vert_indices:
                    continue

                face_indices.append(vert_indices[vert])

            if len(face_indices) >= 3:
                faces.append(face_indices)

        return vertices, edges, faces
