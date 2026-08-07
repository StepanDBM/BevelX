# BX_bevelx/BX_emit_maya_mesh.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from BX_bevelx.BX_math_utils import copy_v3


# ---------------------------------------------------------------------------
# Generated mesh output records
# ---------------------------------------------------------------------------

@dataclass
class EmitMeshData:
    """
    Plain Python mesh output from the Blender-shaped bevel pipeline.

    This is the solver/output boundary:
        - vertices: list of xyz coordinates
        - faces: list of vertex-index polygons

    It is intentionally independent from Maya. Maya writing is a separate
    adapter at the bottom of this file.
    """

    vertices: List[List[float]] = field(default_factory=list)
    faces: List[List[int]] = field(default_factory=list)

    # Debug provenance, parallel to faces.
    face_sources: List[Dict[str, Any]] = field(default_factory=list)

    def to_pydata(self):
        return self.vertices, self.faces


# ---------------------------------------------------------------------------
# Generic generated-polygon access
# ---------------------------------------------------------------------------

def _record_get(record, name, default=None):
    if isinstance(record, dict):
        return record.get(name, default)

    return getattr(record, name, default)


def _as_coordinate(vertex_like):
    """
    Convert a generated bevel vertex-like object to a coordinate.

    Accepted Blender-port shapes:
        NewVert.co
        BoundVert.nv.co
        object.co
        [x, y, z]
        (x, y, z)
    """

    if vertex_like is None:
        return None

    if isinstance(vertex_like, (list, tuple)) and len(vertex_like) >= 3:
        return [float(vertex_like[0]), float(vertex_like[1]), float(vertex_like[2])]

    nv = getattr(vertex_like, "nv", None)
    if nv is not None:
        co = getattr(nv, "co", None)
        if co is not None:
            return copy_v3(co)

    co = getattr(vertex_like, "co", None)
    if co is not None:
        return copy_v3(co)

    return None


def _polygon_vertices(record):
    """
    Extract vertex-like values from generated polygon record.

    Current expected records from the fresh Blender port use .verts, but this
    function remains confined to the emit boundary so the solver modules do not
    depend on output serialization details.
    """

    verts = _record_get(record, "verts", None)
    if verts is not None:
        return list(verts)

    verts = _record_get(record, "vertices", None)
    if verts is not None:
        return list(verts)

    verts = _record_get(record, "newverts", None)
    if verts is not None:
        return list(verts)

    return []


def _polygon_source(record, fallback_kind):
    return {
        "kind": _record_get(record, "kind", fallback_kind),
        "source_edge": _record_get(record, "source_edge", None),
        "source_face": _record_get(record, "source_face", None),
        "record": record,
    }


# ---------------------------------------------------------------------------
# Coordinate deduplication
# ---------------------------------------------------------------------------

def quantize_coordinate(co, epsilon=1.0e-9):
    return (
        int(round(co[0] / epsilon)),
        int(round(co[1] / epsilon)),
        int(round(co[2] / epsilon)),
    )


class VertexIndexBuilder(object):
    def __init__(self, epsilon=1.0e-9):
        self.epsilon = epsilon
        self.vertices = []
        self._index_by_key = {}

    def add(self, co):
        key = quantize_coordinate(co, self.epsilon)

        if key in self._index_by_key:
            return self._index_by_key[key]

        index = len(self.vertices)
        self.vertices.append(copy_v3(co))
        self._index_by_key[key] = index

        return index


def collapse_adjacent_face_indices(face_indices):
    result = []

    for index in face_indices:
        if result and result[-1] == index:
            continue
        result.append(index)

    if len(result) > 1 and result[0] == result[-1]:
        result.pop()

    return result


# ---------------------------------------------------------------------------
# Record collection from BevelParams
# ---------------------------------------------------------------------------

def get_edge_polygon_records(params):
    """
    Return generated bevel edge polygons from the Blender-port params object.

    Current producer:
        BX_build_edge_polygons.build_edge_polygons()
            -> params.generated_edge_polygons

    Older/alternate expected name is also accepted at the emit boundary only:
        params.edge_polygons
    """

    records = getattr(params, "generated_edge_polygons", None)
    if records is not None:
        return list(records)

    records = getattr(params, "edge_polygons", None)
    if records is not None:
        return list(records)

    return []


def get_vmesh_polygon_records(params):
    """
    Return generated vertex-mesh polygons, if BX_build_vmesh.py produced any.

    Current producer:
        BX_build_vmesh.build_vmesh_for_bevvert()
            -> bevvert.vmesh.generated_polygons

    Optional aggregate name is also accepted at the emit boundary only:
        params.vmesh_polygons
    """

    records = getattr(params, "vmesh_polygons", None)
    if records is not None:
        return list(records)

    result = []

    for bevvert in getattr(params, "vert_hash", {}).values():
        vm = getattr(bevvert, "vmesh", None)
        if vm is None:
            continue

        records = getattr(vm, "generated_polygons", None)
        if records:
            result.extend(records)

    return result


def get_rebuilt_polygon_records(params):
    """
    Return rebuilt original source polygons from BX_rebuild_polygons.py.

    The canonical current attribute is expected to be params.rebuilt_polygons.
    """

    records = getattr(params, "rebuilt_polygons", None)
    if records is not None:
        return list(records)

    return []


# ---------------------------------------------------------------------------
# Public pydata emit
# ---------------------------------------------------------------------------

def emit_pydata(params, epsilon=1.0e-9, include_sources=False):
    """
    Convert generated bevel records into plain Python mesh data.

    Collection order follows Blender's conceptual output order:
        1. VMesh polygons
        2. selected-edge bevel polygons
        3. rebuilt original polygons

    Returns:
        EmitMeshData by default.

    If include_sources is False, the returned object still carries face_sources
    internally, but callers may simply use:
        vertices, faces = emit_pydata(params).to_pydata()
    """

    builder = VertexIndexBuilder(epsilon=epsilon)
    output = EmitMeshData()

    groups = [
        (get_vmesh_polygon_records(params), "VMESH"),
        (get_edge_polygon_records(params), "EDGE"),
        (get_rebuilt_polygon_records(params), "REBUILT"),
    ]

    for records, fallback_kind in groups:
        for record in records:
            vertex_likes = _polygon_vertices(record)

            face_indices = []

            for vertex_like in vertex_likes:
                co = _as_coordinate(vertex_like)
                if co is None:
                    continue

                face_indices.append(builder.add(co))

            face_indices = collapse_adjacent_face_indices(face_indices)

            if len(face_indices) < 3:
                continue

            output.faces.append(face_indices)
            output.face_sources.append(_polygon_source(record, fallback_kind))

    output.vertices = builder.vertices

    return output


def emit_vertices_faces(params, epsilon=1.0e-9):
    """
    Convenience wrapper returning exactly:
        vertices, faces
    """

    return emit_pydata(params, epsilon=epsilon).to_pydata()


# ---------------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------------

def debug_emit_summary(params, epsilon=1.0e-9):
    output = emit_pydata(params, epsilon=epsilon)

    lines = []
    lines.append(
        "EmitMesh vertices={0} faces={1}".format(
            len(output.vertices),
            len(output.faces),
        )
    )

    for index, face in enumerate(output.faces):
        source = output.face_sources[index] if index < len(output.face_sources) else {}
        coords = [output.vertices[i] for i in face]

        lines.append(
            "EmitFace index={0} kind={1} verts={2} coords={3}".format(
                index,
                source.get("kind"),
                face,
                coords,
            )
        )

    return lines


# ---------------------------------------------------------------------------
# Maya adapter boundary
# ---------------------------------------------------------------------------

def emit_to_maya_mesh(params,
                      mesh_name="BevelX_BlenderBevel_Output",
                      epsilon=1.0e-9,
                      parent=None):
    """
    Create a Maya mesh from emitted bevel pydata using Maya Python API 2.0.

    This function is intentionally kept at the output boundary. The bevel solver
    itself does not import Maya.

    Returns:
        Maya MObject of the created mesh when running inside Maya.
    """

    output = emit_pydata(params, epsilon=epsilon)
    vertices = output.vertices
    faces = output.faces

    if not vertices or not faces:
        raise RuntimeError("emit_to_maya_mesh received empty bevel output")

    try:
        import maya.api.OpenMaya as om
    except Exception as exc:
        raise RuntimeError(
            "emit_to_maya_mesh requires Maya Python API 2.0. Use emit_pydata() outside Maya."
        ) from exc

    points = om.MPointArray()
    for co in vertices:
        points.append(om.MPoint(co[0], co[1], co[2]))

    face_counts = om.MIntArray()
    face_connects = om.MIntArray()

    for face in faces:
        face_counts.append(len(face))
        for index in face:
            face_connects.append(int(index))

    mesh_fn = om.MFnMesh()

    if parent is None:
        mesh_object = mesh_fn.create(points, face_counts, face_connects)
    else:
        mesh_object = mesh_fn.create(points, face_counts, face_connects, parent)

    # Assign name when possible.
    try:
        dep_fn = om.MFnDependencyNode(mesh_object)
        dep_fn.setName(mesh_name)
    except Exception:
        pass

    return mesh_object
