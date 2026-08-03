# BX_transaction.py
# BevelX bevel transaction model.
#
# Current milestone:
# - Build one F_EDGE bevel face from terminal boundary vertices.
# - Build F_RECON faces for the two affected original faces.
# - Pure data structure, no Maya editing.

from __future__ import print_function

from BX_math import BX_math as bxm


FACE_ORIG = "F_ORIG"
FACE_EDGE = "F_EDGE"
FACE_VERT = "F_VERT"
FACE_CAP = "F_CAP"
FACE_PATCH = "F_PATCH"
FACE_INNER_MITER_PATCH = "F_INNER_MITER_PATCH"
FACE_RECON = "F_RECON"

VERT_ORIGINAL = "ORIGINAL"
VERT_BOUNDARY = "BOUNDARY"
VERT_GENERATED = "GENERATED"

INNER_CAP_NGON = "NGON"
INNER_CAP_FAN = "FAN"
INNER_CAP_ADJ_LITE = "ADJ_LITE"
INNER_CAP_AUTO = "AUTO"

DEFAULT_INNER_CAP_MODE = INNER_CAP_ADJ_LITE

class BX_TransactionVertex(object):
    def __init__(self,
                 vertex_id,
                 co_world,
                 source,
                 original_vertex_id=None,
                 boundary_id=None,
                 selected_edge_id=None,
                 face_id=None):
        self.id = int(vertex_id)

        self.co_world = list(co_world)

        self.source = source

        self.original_vertex_id = original_vertex_id
        self.boundary_id = boundary_id
        self.selected_edge_id = selected_edge_id
        self.face_id = face_id

    def __repr__(self):
        return (
            "BX_TransactionVertex(id={0}, source={1}, orig_v={2}, "
            "boundary={3}, edge={4}, face={5}, co={6})"
        ).format(
            self.id,
            self.source,
            self.original_vertex_id,
            self.boundary_id,
            self.selected_edge_id,
            self.face_id,
            self.co_world
        )


class BX_TransactionFace(object):
    def __init__(self,
                 face_id,
                 vertex_ids,
                 face_kind,
                 source_face_id=None,
                 source_edge_id=None,
                 expected_normal=None):
        self.id = int(face_id)

        self.vertex_ids = list(vertex_ids)

        self.face_kind = face_kind

        self.source_face_id = source_face_id
        self.source_edge_id = source_edge_id

        self.expected_normal = expected_normal

    def __repr__(self):
        return (
            "BX_TransactionFace(id={0}, kind={1}, verts={2}, "
            "source_face={3}, source_edge={4})"
        ).format(
            self.id,
            self.face_kind,
            self.vertex_ids,
            self.source_face_id,
            self.source_edge_id
        )


class BX_BevelTransaction(object):
    def __init__(self):
        self.vertices = []
        self.faces = []

        self.original_vertex_id_to_tx_id = {}
        self.boundary_id_to_tx_id = {}

        self.faces_to_replace = []

    # -------------------------------------------------------------------------
    # Vertex creation
    # -------------------------------------------------------------------------

    def add_original_vertex(self, bm, original_vertex_id):
        """
        Add an existing original mesh vertex as a transaction vertex.

        This lets transaction faces contain both:
            - original mesh verts
            - generated boundary verts
        """

        original_vertex_id = int(original_vertex_id)

        if original_vertex_id in self.original_vertex_id_to_tx_id:
            return self.original_vertex_id_to_tx_id[original_vertex_id]

        bx_vertex = bm.vertices[original_vertex_id]

        tx_id = len(self.vertices)

        tx_vertex = BX_TransactionVertex(
            vertex_id=tx_id,
            co_world=bx_vertex.co_world,
            source=VERT_ORIGINAL,
            original_vertex_id=original_vertex_id
        )

        self.vertices.append(tx_vertex)
        self.original_vertex_id_to_tx_id[original_vertex_id] = tx_id

        return tx_id

    def add_boundary_vertex(self, boundary_vertex):
        """
        Add a BX_BoundaryVertex as a transaction vertex.
        """

        boundary_id = boundary_vertex.id

        if boundary_id in self.boundary_id_to_tx_id:
            return self.boundary_id_to_tx_id[boundary_id]

        tx_id = len(self.vertices)

        tx_vertex = BX_TransactionVertex(
            vertex_id=tx_id,
            co_world=boundary_vertex.co_world,
            source=VERT_BOUNDARY,
            original_vertex_id=boundary_vertex.original_vertex_id,
            boundary_id=boundary_vertex.id,
            selected_edge_id=boundary_vertex.selected_edge_id,
            face_id=boundary_vertex.face_id
        )

        self.vertices.append(tx_vertex)
        self.boundary_id_to_tx_id[boundary_id] = tx_id

        return tx_id

    # -------------------------------------------------------------------------
    # Face creation
    # -------------------------------------------------------------------------
    def add_generated_vertex(self, co_world):
        """
        Add a generated transaction vertex.

        Used for:
            - F_CAP fan centers
            - future F_PATCH center points
            - future VMesh generated vertices
        """

        vertex_id = len(self.vertices)

        vertex = BX_TransactionVertex(
            vertex_id=vertex_id,
            co_world=co_world,
            source=VERT_GENERATED,
            original_vertex_id=None,
            boundary_id=None,
            selected_edge_id=None,
            face_id=None
        )

        self.vertices.append(vertex)

        return vertex_id

    def add_face(self,
                 vertex_ids,
                 face_kind,
                 source_face_id=None,
                 source_edge_id=None,
                 expected_normal=None):
        face_id = len(self.faces)

        face = BX_TransactionFace(
            face_id=face_id,
            vertex_ids=vertex_ids,
            face_kind=face_kind,
            source_face_id=source_face_id,
            source_edge_id=source_edge_id,
            expected_normal=expected_normal
        )

        self.faces.append(face)

        return face

    def get_face_world_points(self, face):
        return [
            self.vertices[vertex_id].co_world
            for vertex_id in face.vertex_ids
        ]

    # -------------------------------------------------------------------------
    # Debug
    # -------------------------------------------------------------------------

    def debug_print(self):
        print("[BevelX] BevelTransaction:")
        print("[BevelX]   transaction vertices: {0}".format(len(self.vertices)))
        print("[BevelX]   transaction faces: {0}".format(len(self.faces)))
        print("[BevelX]   faces to replace: {0}".format(self.faces_to_replace))

        print("[BevelX]   vertices:")

        for vertex in self.vertices:
            print("[BevelX]     {0}".format(vertex))

        print("[BevelX]   faces:")

        for face in self.faces:
            print("[BevelX]     {0}".format(face))


# -----------------------------------------------------------------------------
# Transaction construction
# -----------------------------------------------------------------------------
def build_single_edge_transaction(edge_data, vertex_boundaries, bm=None):
    """
    Build a BevelX transaction for one selected edge.

    Current output:
        - F_EDGE bevel strip
        - F_RECON faces for all original faces touching affected endpoint vertices

    This is closer to the real bevel rebuild model:
        selected edge endpoints become affected vertices
        all faces touching those vertices are reconstructed
        old affected faces are replaced after new topology exists
    """

    transaction = BX_BevelTransaction()

    edge_id = edge_data["edge_id"]
    edge_v0, edge_v1 = edge_data["vertex_ids"]

    adjacent_face_ids = [
        face_data["face_id"]
        for face_data in edge_data["faces"]
    ]

    if len(adjacent_face_ids) != 2:
        print("[BevelX] Transaction build requires exactly 2 adjacent selected-edge faces.")
        return transaction

    build_edge_face(
        transaction=transaction,
        edge_data=edge_data,
        vertex_boundaries=vertex_boundaries
    )

    if bm is None:
        transaction.faces_to_replace = list(adjacent_face_ids)

        print("[BevelX] Transaction warning: bm is None, only F_EDGE was built.")
        return transaction

    affected_face_ids = get_affected_face_ids_for_single_edge(
        bm=bm,
        edge_v0=edge_v0,
        edge_v1=edge_v1
    )

    transaction.faces_to_replace = affected_face_ids

    for face_id in affected_face_ids:
        build_reconstructed_face(
            transaction=transaction,
            bm=bm,
            face_id=face_id,
            edge_v0=edge_v0,
            edge_v1=edge_v1,
            vertex_boundaries=vertex_boundaries
        )

    return transaction

def build_selection_edge_faces_transaction(edges_data, vertex_boundaries, bm=None):
    """
    Build a preview transaction for a multi-edge selection.

    Current output:
        - F_EDGE faces for every selected edge.
        - Shared boundary vertices are reused through boundary_id mapping.
        - faces_to_replace is collected for diagnostics.

    This does NOT build F_RECON yet.
    This transaction is preview-only for multi-edge selections.
    """

    transaction = BX_BevelTransaction()

    for edge_data in edges_data:
        build_edge_face(
            transaction=transaction,
            edge_data=edge_data,
            vertex_boundaries=vertex_boundaries
        )

    if bm is not None:
        affected_face_ids = get_affected_face_ids_for_selected_edges(
            bm=bm,
            edges_data=edges_data
        )

        transaction.faces_to_replace = affected_face_ids

    return transaction

def get_affected_face_ids_for_selected_edges(bm, edges_data):
    """
    Return all original faces touched by all selected edge endpoints.
    """

    affected = set()

    for edge_data in edges_data:
        for vertex_id in edge_data["vertex_ids"]:
            for face_id in bm.vertices[vertex_id].faces:
                affected.add(face_id)

    return sorted(affected)

def get_affected_vertex_ids_for_selected_edges(edges_data):
    """
    Return all vertices touched by selected edges.
    """

    affected_vertices = set()

    for edge_data in edges_data:
        edge_v0, edge_v1 = edge_data["vertex_ids"]

        affected_vertices.add(edge_v0)
        affected_vertices.add(edge_v1)

    return sorted(affected_vertices)

def can_build_edge_face_from_boundaries(edge_data, vertex_boundaries):
    """
    Return True if all boundary vertices needed by build_edge_face() exist.

    For an edge with two adjacent faces:
        edge_v0 face_a
        edge_v1 face_a
        edge_v1 face_b
        edge_v0 face_b

    must all exist.
    """

    edge_v0, edge_v1 = edge_data["vertex_ids"]

    face_ids = [
        face_data["face_id"]
        for face_data in edge_data["faces"]
    ]

    if len(face_ids) != 2:
        return False

    face_a_id = face_ids[0]
    face_b_id = face_ids[1]

    required = [
        find_boundary(vertex_boundaries, edge_v0, face_a_id),
        find_boundary(vertex_boundaries, edge_v1, face_a_id),
        find_boundary(vertex_boundaries, edge_v1, face_b_id),
        find_boundary(vertex_boundaries, edge_v0, face_b_id),
    ]

    return None not in required

def build_selection_transaction(edges_data, vertex_boundaries, bm=None, bevel_vertices=None):
    """
    Build a full preview/apply transaction for a selected edge set.

    Current output:
        - F_EDGE faces for all selected edges.
        - F_VERT faces for simple tri caps.
        - F_RECON faces for all affected original faces.
    """

    transaction = BX_BevelTransaction()

    # Validate selected-edge strips first.
    for edge_data in edges_data:
        if not can_build_edge_face_from_boundaries(edge_data, vertex_boundaries):
            print("[BevelX] Selection transaction skipped: missing boundary data for edge {0}.".format(
                edge_data["edge_id"]
            ))
            return transaction

    # 1. Build all selected-edge bevel strip faces.
    for edge_data in edges_data:
        build_edge_face(
            transaction=transaction,
            edge_data=edge_data,
            vertex_boundaries=vertex_boundaries
        )

    # 2. Build vertex cap faces, currently TRI_CAP only.
    build_vertex_cap_faces(
        transaction=transaction,
        vertex_boundaries=vertex_boundaries
    )
    debug_inner_miter_candidates(bevel_vertices=bevel_vertices,
                                 vertex_boundaries=vertex_boundaries,
                                 central_face_id=None)
    if bm is None:
        return transaction

    affected_vertex_ids = get_affected_vertex_ids_for_selected_edges(
        edges_data
    )

    affected_face_ids = get_affected_face_ids_for_selected_edges(
        bm=bm,
        edges_data=edges_data
    )

    transaction.faces_to_replace = affected_face_ids

    # 3. Rebuild every original face touched by affected vertices.
    for face_id in affected_face_ids:
        build_reconstructed_face_for_selection(
            transaction=transaction,
            bm=bm,
            face_id=face_id,
            affected_vertex_ids=affected_vertex_ids,
            vertex_boundaries=vertex_boundaries,
            bevel_vertices=bevel_vertices
        )

    return transaction
    

# -----------------------------------------------------------------------------
# F_CAP / inner face cap helpers
# -----------------------------------------------------------------------------
def is_chain2_inner_miter_candidate(bevel_vertex,
                                    vertex_boundaries,
                                    central_face_id=None):
    """
    Return True if this bevel vertex is a first-pass candidate for
    INNER_MITER_PATCH.

    Boundary data lives in vertex_boundaries, not on BX_BevelVertex.
    """

    vertex_id = getattr(bevel_vertex, "vertex_id", None)

    if vertex_id is None:
        return False

    kind = getattr(bevel_vertex, "kind", None)
    selected_count = getattr(bevel_vertex, "selected_count", None)

    if kind != "CHAIN_2":
        return False

    if selected_count != 2:
        return False

    boundary_vertices = vertex_boundaries.get(vertex_id, [])

    if len(boundary_vertices) < 4:
        return False

    if central_face_id is None:
        return True

    # Important: CHAIN_2 boundary verts are usually on neighboring support faces,
    # not necessarily directly on central face 1. So do not require face 1 here
    # unless you specifically want that filter.
    return True

def get_bevel_vertex_selected_edges(bevel_vertex):
    """
    Return selected / beveled edge ids from a BX_BevelVertex.

    This avoids relying on a stored selected_count field.
    """

    selected_edges = getattr(bevel_vertex, "selected_edges", None)

    if selected_edges is not None:
        return list(selected_edges)

    edge_halves = getattr(bevel_vertex, "edge_halves", None)

    if not edge_halves:
        return []

    result = []

    for edge_half in edge_halves:
        if getattr(edge_half, "beveled", False):
            edge_id = getattr(edge_half, "edge_id", getattr(edge_half, "edge", None))

            if edge_id is not None:
                result.append(edge_id)

    return result


def debug_inner_miter_candidates(bevel_vertices,
                                 vertex_boundaries,
                                 central_face_id=None):
    """
    Print likely INNER_MITER_PATCH candidates.

    For the current BevelX data model:
        - topology kind may not be stored on BX_BevelVertex
        - selected_count may not be stored on BX_BevelVertex
        - boundary data lives in vertex_boundaries

    First-pass candidate rule:
        - exactly 2 selected/beveled edges
        - exactly 4 boundary vertices

    This catches current CHAIN_2 vertices:
        40, 41, 42, 43
    and excludes current CORNER_2 vertices:
        46, 47, 50, 51, 54, 55, 58, 59
    """

    if bevel_vertices is None:
        print("[BevelX] INNER_MITER debug skipped: bevel_vertices is None.")
        return

    if vertex_boundaries is None:
        print("[BevelX] INNER_MITER debug skipped: vertex_boundaries is None.")
        return

    if hasattr(bevel_vertices, "items"):
        iterator = bevel_vertices.items()
    else:
        iterator = []

        for bevel_vertex in bevel_vertices:
            vertex_id = getattr(
                bevel_vertex,
                "vertex_id",
                getattr(bevel_vertex, "id", None)
            )

            iterator.append((vertex_id, bevel_vertex))

    found = 0

    for vertex_id, bevel_vertex in iterator:
        if vertex_id is None:
            continue

        selected_edges = get_bevel_vertex_selected_edges(bevel_vertex)
        boundary_vertices = vertex_boundaries.get(vertex_id, [])

        selected_count = len(selected_edges)
        boundary_count = len(boundary_vertices)

        print("[BevelX] INNER_MITER inspect vertex {0}: selected_edges={1}, boundary_count={2}".format(
            vertex_id,
            selected_edges,
            boundary_count
        ))

        if selected_count != 2:
            continue

        if boundary_count != 4:
            continue

        found += 1

        boundary_debug = []

        for boundary_vertex in boundary_vertices:
            boundary_debug.append(
                "{0}: face={1}, edge={2}".format(
                    getattr(boundary_vertex, "id", "?"),
                    boundary_vertex_face_id(boundary_vertex),
                    getattr(boundary_vertex, "edge", getattr(boundary_vertex, "edge_id", "?"))
                )
            )

        print("[BevelX] INNER_MITER candidate vertex {0}:".format(vertex_id))
        print("[BevelX]   selected_edges={0}, boundary_count={1}".format(
            selected_edges,
            boundary_count
        ))
        print("[BevelX]   boundaries: {0}".format(boundary_debug))

    print("[BevelX] INNER_MITER candidate debug found {0} candidates.".format(
        found
    ))

#######################################################
# just for now, I really am unsure of this values. debug print shows BX_BoundaryVertex(... face=44 ...), so...
#######################################################
def boundary_vertex_face_id(boundary_vertex):
    """
    Return face id from a BX_BoundaryVertex, tolerating naming differences.
    """

    if hasattr(boundary_vertex, "face_id"):
        return boundary_vertex.face_id

    if hasattr(boundary_vertex, "face"):
        return boundary_vertex.face

    return None

def should_build_inner_cap_face(transaction, face_indices):
    """
    Return True if a rebuilt source face should become an inner cap.

    First conservative rule:
        - rebuilt face has 6 or more vertices
        - all rebuilt vertices are boundary vertices

    This avoids changing normal outer support faces that still contain
    original corner vertices.
    """

    if len(face_indices) < 6:
        return False

    for tx_id in face_indices:
        tx_vertex = transaction.vertices[tx_id]

        if tx_vertex.source != VERT_BOUNDARY:
            return False

    return True


def build_inner_cap_face(transaction, bm, face_id, face_indices):
    """
    Build a simple F_CAP polygon for a complex all-boundary reconstructed face.

    This is the first INNER_CAP_NONE / M_POLY_CAP behavior:
        - collect all boundary vertices from the rebuilt face
        - sort them around the original source face center
        - orient to the original source face normal
        - add one F_CAP polygon

    This is intentionally simple and predictable. Later Auto mode can
    replace this with rail-intersection patching.
    """

    face = bm.faces[face_id]

    expected_normal = list(face.normal_world)
    face_center = list(face.center_world)

    sorted_indices = sort_transaction_vertices_on_face(
        transaction=transaction,
        vertex_ids=face_indices,
        face_center=face_center,
        face_normal=expected_normal
    )

    sorted_indices = orient_transaction_face_indices_to_normal(
        transaction=transaction,
        face_indices=sorted_indices,
        expected_normal=expected_normal
    )

    return transaction.add_face(
        vertex_ids=sorted_indices,
        face_kind=FACE_CAP,
        source_face_id=face_id,
        expected_normal=expected_normal
    )


def sort_transaction_vertices_on_face(transaction,
                                      vertex_ids,
                                      face_center,
                                      face_normal):
    """
    Sort transaction vertices around face_center in the face plane.

    This gives F_CAP a stable winding order for ngon cap faces.
    """

    import math

    normal = bxm.normalize(face_normal)

    if not vertex_ids:
        return []

    first_point = transaction.vertices[vertex_ids[0]].co_world

    tangent = bxm.sub(first_point, face_center)

    # Remove normal component from tangent.
    tangent_normal_amount = bxm.dot(tangent, normal)
    tangent = bxm.sub(
        tangent,
        bxm.mul(normal, tangent_normal_amount)
    )

    tangent = bxm.normalize(tangent)

    if bxm.is_zero(tangent):
        tangent = make_fallback_tangent(normal)

    bitangent = bxm.normalize(
        bxm.cross(normal, tangent)
    )

    def angle_for_id(tx_id):
        point = transaction.vertices[tx_id].co_world
        vector = bxm.sub(point, face_center)

        x = bxm.dot(vector, tangent)
        y = bxm.dot(vector, bitangent)

        return math.atan2(y, x)

    return sorted(vertex_ids, key=angle_for_id)


def make_fallback_tangent(normal):
    """
    Build a stable tangent perpendicular to normal.
    """

    world_x = [1.0, 0.0, 0.0]
    world_y = [0.0, 1.0, 0.0]

    tangent = bxm.cross(normal, world_x)

    if bxm.is_zero(tangent):
        tangent = bxm.cross(normal, world_y)

    return bxm.normalize(tangent)

def build_reconstructed_face_for_selection(transaction,
                                           bm,
                                           face_id,
                                           affected_vertex_ids,
                                           vertex_boundaries,
                                           bevel_vertices=None):
    """
    Build F_RECON for a face affected by a selected edge set.

    This handles:
        - faces directly containing selected edges
        - support faces touching only one affected endpoint
        - simple CORNER_2 boundaries

    Rule:
        If an affected vertex has a boundary vertex for this face, use it.
        Otherwise, replace the vertex with the two boundary vertices from
        neighboring faces across the previous/next face edges.
    """

    face = bm.faces[face_id]
    face_vertices = list(face.vertices)

    rebuilt_tx_ids = []

    count = len(face_vertices)

    for i, current_v in enumerate(face_vertices):
        if current_v not in affected_vertex_ids:
            rebuilt_tx_ids.append(
                transaction.add_original_vertex(
                    bm=bm,
                    original_vertex_id=current_v
                )
            )
            continue

        # Case A:
        # This affected vertex has a boundary point directly associated
        # with this face. This is the common case for faces containing
        # selected edges or corner miter faces.
        direct_boundary = find_boundary(
            vertex_boundaries,
            current_v,
            face_id
        )

        if direct_boundary is not None:
            rebuilt_tx_ids.append(
                transaction.add_boundary_vertex(direct_boundary)
            )
            continue

        # Case B:
        # This face touches the affected vertex but does not directly own
        # a boundary vertex for that face. This is a support face.
        replacement_ids = build_support_face_vertex_replacement(
            transaction=transaction,
            bm=bm,
            face_id=face_id,
            face_vertices=face_vertices,
            vertex_index=i,
            vertex_id=current_v,
            vertex_boundaries=vertex_boundaries
        )

        if replacement_ids:
            rebuilt_tx_ids.extend(replacement_ids)
        else:
            # Conservative fallback.
            rebuilt_tx_ids.append(
                transaction.add_original_vertex(
                    bm=bm,
                    original_vertex_id=current_v
                )
            )

    expected_normal = list(face.normal_world)

    rebuilt_tx_ids = orient_transaction_face_indices_to_normal(
        transaction=transaction,
        face_indices=rebuilt_tx_ids,
        expected_normal=expected_normal
    )

    # Avoid degenerate faces.
    if len(rebuilt_tx_ids) < 3:
        print("[BevelX] F_RECON skipped for face {0}: fewer than 3 verts.".format(face_id))
        return None

    # Inner cap mode:
    # If the rebuilt face is a large all-boundary polygon, turn it into
    # an explicit cap instead of a normal reconstructed face.
    if should_build_inner_cap_face(transaction=transaction, face_indices=rebuilt_tx_ids):
        build_inner_cap_auto(
            transaction=transaction,
            bm=bm,
            face_id=face_id,
            face_indices=rebuilt_tx_ids,
            bevel_vertices=bevel_vertices,
            vertex_boundaries=vertex_boundaries
        )

        return None

    return transaction.add_face(
        vertex_ids=rebuilt_tx_ids,
        face_kind=FACE_RECON,
        source_face_id=face_id,
        expected_normal=expected_normal
    )

def build_support_face_vertex_replacement(transaction,
                                          bm,
                                          face_id,
                                          face_vertices,
                                          vertex_index,
                                          vertex_id,
                                          vertex_boundaries):
    """
    Replace an affected vertex on a support face.

    A support face touches the original affected vertex but does not have
    its own face-specific boundary point.

    I find the neighboring faces across the previous and next edges in
    this face, then use the boundary vertices from those neighboring faces.
    """

    count = len(face_vertices)

    prev_v = face_vertices[(vertex_index - 1) % count]
    next_v = face_vertices[(vertex_index + 1) % count]

    prev_edge_id = get_edge_id_between_vertices(
        bm=bm,
        vertex_a=prev_v,
        vertex_b=vertex_id
    )

    next_edge_id = get_edge_id_between_vertices(
        bm=bm,
        vertex_a=vertex_id,
        vertex_b=next_v
    )

    prev_other_face = get_other_face_on_edge(
        bm=bm,
        edge_id=prev_edge_id,
        current_face_id=face_id
    )

    next_other_face = get_other_face_on_edge(
        bm=bm,
        edge_id=next_edge_id,
        current_face_id=face_id
    )

    if prev_other_face is None or next_other_face is None:
        print(
            "[BevelX] Support replacement failed at vertex {0} on face {1}: "
            "could not find neighboring faces.".format(vertex_id, face_id)
        )
        return None

    boundary_prev = find_boundary(
        vertex_boundaries,
        vertex_id,
        prev_other_face
    )

    boundary_next = find_boundary(
        vertex_boundaries,
        vertex_id,
        next_other_face
    )

    if boundary_prev is None or boundary_next is None:
        print(
            "[BevelX] Support replacement failed at vertex {0} on face {1}: "
            "missing boundaries for neighboring faces {2}, {3}.".format(
                vertex_id,
                face_id,
                prev_other_face,
                next_other_face
            )
        )
        return None

    return [
        transaction.add_boundary_vertex(boundary_prev),
        transaction.add_boundary_vertex(boundary_next),
    ]

def build_inner_cap_fan(transaction, bm, face_id, face_indices):
    """
    Build an explicit triangle fan for a complex inner cap.

    This is the next version of INNER_CAP_NONE:
        - sort boundary vertices around the source face center
        - create one generated center vertex
        - create F_PATCH triangles from center to each boundary edge

    This avoids relying on Maya's internal triangulation of a large ngon.
    """

    face = bm.faces[face_id]

    expected_normal = list(face.normal_world)
    face_center = list(face.center_world)

    sorted_indices = sort_transaction_vertices_on_face(
        transaction=transaction,
        vertex_ids=face_indices,
        face_center=face_center,
        face_normal=expected_normal
    )

    sorted_indices = orient_transaction_face_indices_to_normal(
        transaction=transaction,
        face_indices=sorted_indices,
        expected_normal=expected_normal
    )

    center = calculate_transaction_polygon_center(
        transaction=transaction,
        vertex_ids=sorted_indices
    )

    center_id = transaction.add_generated_vertex(center)

    count = len(sorted_indices)

    patch_faces = []

    for i in range(count):
        a = sorted_indices[i]
        b = sorted_indices[(i + 1) % count]

        tri_ids = [center_id, a, b]

        tri_ids = orient_transaction_face_indices_to_normal(
            transaction=transaction,
            face_indices=tri_ids,
            expected_normal=expected_normal
        )

        if len(tri_ids) != 3:
            print("[BevelX] F_PATCH skipped non-triangle fan face on face {0}: verts={1}".format(
                face_id,
                tri_ids
            ))
            continue

        area = transaction_triangle_area(
            transaction=transaction,
            vertex_ids=tri_ids
        )

        if is_degenerate_transaction_triangle(
            transaction=transaction,
            vertex_ids=tri_ids
        ):
            print("[BevelX] F_PATCH skipped degenerate fan triangle on face {0}: verts={1}, area={2}".format(
                face_id,
                tri_ids,
                area
            ))
            continue

        patch_face = transaction.add_face(
            vertex_ids=tri_ids,
            face_kind=FACE_PATCH,
            source_face_id=face_id,
            expected_normal=expected_normal
        )

        patch_faces.append(patch_face)

    if len(patch_faces) != count:
        print("[BevelX] F_PATCH fan warning on face {0}: built {1}/{2} triangles.".format(
            face_id,
            len(patch_faces),
            count
        ))

    return patch_faces

def build_inner_cap_adj_lite(transaction,
                             bm,
                             face_id,
                             face_indices,
                             inner_scale=0.45,
                             bevel_vertices=None,
                             vertex_boundaries=None):
    """
    Build first M_ADJ-lite inner cap.

    This replaces one big ngon or one triangle fan with:
        - generated inner ring
        - F_PATCH quad ring
        - F_CAP center polygon

    It is not full Blender M_ADJ yet. It is a stable, readable,
    segments=1 patch that avoids fan spokes across the whole cap.
    """
    print("[BevelX] Inner cap ADJ_LITE entered on face {0}: outer verts={1}".format(
        face_id,
        face_indices
    ))


    face = bm.faces[face_id]

    expected_normal = list(face.normal_world)
    face_center = list(face.center_world)

    sorted_outer_ids = sort_transaction_vertices_on_face(
        transaction=transaction,
        vertex_ids=face_indices,
        face_center=face_center,
        face_normal=expected_normal
    )

    sorted_outer_ids = orient_transaction_face_indices_to_normal(
        transaction=transaction,
        face_indices=sorted_outer_ids,
        expected_normal=expected_normal
    )

    if len(sorted_outer_ids) < 3:
        print("[BevelX] F_PATCH ADJ_LITE skipped for face {0}: fewer than 3 boundary verts.".format(
            face_id
        ))
        return []

    center = calculate_transaction_polygon_center(
        transaction=transaction,
        vertex_ids=sorted_outer_ids
    )

    inner_ids = []

    for outer_id in sorted_outer_ids:
        outer_point = transaction.vertices[outer_id].co_world

        inner_point = bxm.lerp(
            outer_point,
            center,
            inner_scale
        )

        inner_id = transaction.add_generated_vertex(inner_point)
        inner_ids.append(inner_id)

    created_faces = []
    count = len(sorted_outer_ids)
    
    # 1. Build quad ring.
    for i in range(count):
        outer_a = sorted_outer_ids[i]
        outer_b = sorted_outer_ids[(i + 1) % count]
        inner_b = inner_ids[(i + 1) % count]
        inner_a = inner_ids[i]

        quad_ids = [
            outer_a,
            outer_b,
            inner_b,
            inner_a
        ]

        quad_ids = orient_transaction_face_indices_to_normal(
            transaction=transaction,
            face_indices=quad_ids,
            expected_normal=expected_normal
        )

        area = transaction_polygon_area(
            transaction=transaction,
            vertex_ids=quad_ids
        )

        if is_degenerate_transaction_polygon(
            transaction=transaction,
            vertex_ids=quad_ids
        ):
            print("[BevelX] F_PATCH ADJ_LITE skipped degenerate quad on face {0}: verts={1}, area={2}".format(
                face_id,
                quad_ids,
                area
            ))
            continue

        orig_a = get_transaction_vertex_original_id(transaction, outer_a)
        orig_b = get_transaction_vertex_original_id(transaction, outer_b)

        print("[BevelX] ADJ_LITE segment inspect: outer=({0},{1}) orig=({2},{3})".format(
            outer_a,
            outer_b,
            orig_a,
            orig_b
        ))

        face_kind = FACE_PATCH

        if bevel_vertices is not None and vertex_boundaries is not None:
            if should_use_inner_miter_patch_for_outer_pair(
                transaction=transaction,
                outer_a_id=outer_a,
                outer_b_id=outer_b,
                bevel_vertices=bevel_vertices,
                vertex_boundaries=vertex_boundaries
            ):
                face_kind = FACE_INNER_MITER_PATCH

        patch_face = transaction.add_face(
            vertex_ids=[outer_a, outer_b, inner_b, inner_a],
            face_kind=face_kind,
            source_face_id=face_id
        )

        if face_kind == FACE_INNER_MITER_PATCH:
            orig_id = get_transaction_vertex_original_id(
                transaction=transaction,
                tx_id=outer_a
            )

            print("[BevelX] INNER_MITER_PATCH classified on face {0}, vertex {1}: verts={2}".format(
                face_id,
                orig_id,
                [outer_a, outer_b, inner_b, inner_a]
            ))

        created_faces.append(patch_face)

    # 2. Build center cap polygon.
    center_cap_ids = orient_transaction_face_indices_to_normal(
        transaction=transaction,
        face_indices=inner_ids,
        expected_normal=expected_normal
    )

    center_area = transaction_polygon_area(
        transaction=transaction,
        vertex_ids=center_cap_ids
    )

    if is_degenerate_transaction_polygon(
        transaction=transaction,
        vertex_ids=center_cap_ids
    ):
        print("[BevelX] F_CAP ADJ_LITE skipped degenerate center cap on face {0}: verts={1}, area={2}".format(
            face_id,
            center_cap_ids,
            center_area
        ))
    else:
        center_face = transaction.add_face(
            vertex_ids=center_cap_ids,
            face_kind=FACE_CAP,
            source_face_id=face_id,
            expected_normal=expected_normal
        )

        created_faces.append(center_face)

    if len(created_faces) == 0:
        print("[BevelX] F_PATCH ADJ_LITE failed on face {0}: no patch faces built.".format(
            face_id
        ))
    print("[BevelX] Inner cap ADJ_LITE built on face {0}: inner verts={1}, faces={2}".format(
        face_id,
        inner_ids,
        len(created_faces)
    ))

    return created_faces

def build_inner_cap_auto(transaction,
                         bm,
                         face_id,
                         face_indices,
                         bevel_vertices=None,
                         vertex_boundaries=None):
    """
    First Auto mode.

    Current strategy:
        1. Try ADJ_LITE.
        2. Fallback to FAN.
        3. Fallback to NGON.
    """

    print("[BevelX] Inner cap AUTO entered on face {0}: verts={1}".format(
        face_id,
        face_indices
    ))

    faces = build_inner_cap_adj_lite(
        transaction=transaction,
        bm=bm,
        face_id=face_id,
        face_indices=face_indices,
        bevel_vertices=bevel_vertices,
        vertex_boundaries=vertex_boundaries
    )

    if faces:
        print("[BevelX] Inner cap AUTO used ADJ_LITE on face {0}: built {1} faces.".format(
            face_id,
            len(faces)
        ))
        return faces

    print("[BevelX] Inner cap AUTO ADJ_LITE failed on face {0}; falling back to FAN.".format(
        face_id
    ))

    faces = build_inner_cap_fan(
        transaction=transaction,
        bm=bm,
        face_id=face_id,
        face_indices=face_indices
    )

    if faces:
        print("[BevelX] Inner cap AUTO fallback used FAN on face {0}: built {1} faces.".format(
            face_id,
            len(faces)
        ))
        return faces

    print("[BevelX] Inner cap AUTO FAN failed on face {0}; falling back to NGON.".format(
        face_id
    ))

    face = build_inner_cap_face(
        transaction=transaction,
        bm=bm,
        face_id=face_id,
        face_indices=face_indices
    )

    if face:
        print("[BevelX] Inner cap AUTO fallback used NGON on face {0}.".format(
            face_id
        ))
        return [face]

    print("[BevelX] Inner cap AUTO failed on face {0}.".format(
        face_id
    ))

    return []


def get_transaction_vertex_original_id(transaction, tx_id):
    """
    Return original vertex id from a transaction vertex.
    """

    tx_vertex = transaction.vertices[tx_id]

    if hasattr(tx_vertex, "original_vertex_id"):
        return tx_vertex.original_vertex_id

    if hasattr(tx_vertex, "orig_v"):
        return tx_vertex.orig_v

    return None


def get_bevel_vertex_by_id(bevel_vertices, vertex_id):
    """
    Return BX_BevelVertex by id from dict or list storage.
    """

    if bevel_vertices is None:
        return None

    if hasattr(bevel_vertices, "get"):
        return bevel_vertices.get(vertex_id)

    for bevel_vertex in bevel_vertices:
        if getattr(bevel_vertex, "vertex_id", None) == vertex_id:
            return bevel_vertex

    return None


def is_inner_miter_candidate_vertex_id(vertex_id,
                                       bevel_vertices,
                                       vertex_boundaries):
    """
    First real INNER_MITER candidate test.

    Current rule:
        - bevel vertex exists
        - exactly two selected/beveled edges
        - exactly four boundary vertices

    This catches current CHAIN_2 candidates and excludes current CORNER_2.
    """

    bevel_vertex = get_bevel_vertex_by_id(
        bevel_vertices=bevel_vertices,
        vertex_id=vertex_id
    )

    if bevel_vertex is None:
        return False

    selected_edges = get_bevel_vertex_selected_edges(bevel_vertex)
    boundaries = vertex_boundaries.get(vertex_id, [])

    if len(selected_edges) != 2:
        return False

    if len(boundaries) != 4:
        return False

    return True


def should_use_inner_miter_patch_for_outer_pair(transaction,
                                                outer_a_id,
                                                outer_b_id,
                                                bevel_vertices,
                                                vertex_boundaries):
    """
    Return True when an ADJ-lite outer segment belongs to one CHAIN_2
    original vertex.

    In the central loop, a CHAIN_2 miter segment appears as two adjacent
    boundary tx verts with the same original vertex id.
    """

    orig_a = get_transaction_vertex_original_id(
        transaction=transaction,
        tx_id=outer_a_id
    )

    orig_b = get_transaction_vertex_original_id(
        transaction=transaction,
        tx_id=outer_b_id
    )

    if orig_a is None or orig_b is None:
        return False

    if orig_a != orig_b:
        return False

    return is_inner_miter_candidate_vertex_id(
        vertex_id=orig_a,
        bevel_vertices=bevel_vertices,
        vertex_boundaries=vertex_boundaries
    )

def calculate_transaction_polygon_center(transaction, vertex_ids):
    """
    Average center of transaction vertices.
    """

    if not vertex_ids:
        return [0.0, 0.0, 0.0]

    center = [0.0, 0.0, 0.0]

    for tx_id in vertex_ids:
        center = bxm.add(
            center,
            transaction.vertices[tx_id].co_world
        )

    return bxm.div(center, float(len(vertex_ids)))

# -----------------------------------------------------------------------------
# F_VERT faces
# -----------------------------------------------------------------------------

def build_vertex_cap_faces(transaction, vertex_boundaries):
    """
    Build F_VERT cap faces from TRI_CAP boundary vertices.

    Current support:
        - one F_VERT triangle per original bevel vertex that has
          exactly three TRI_CAP boundaries.
    """

    for vertex_id in sorted(vertex_boundaries.keys()):
        boundary_list = vertex_boundaries.get(vertex_id, [])

        cap_boundaries = [
            boundary_vertex
            for boundary_vertex in boundary_list
            if getattr(boundary_vertex, "source", None) == "TRI_CAP"
        ]

        if not cap_boundaries:
            continue

        if len(cap_boundaries) != 3:
            print("[BevelX] F_VERT skipped for vertex {0}: expected 3 TRI_CAP boundaries, got {1}.".format(
                vertex_id,
                len(cap_boundaries)
            ))
            continue

        tx_vertex_ids = [
            transaction.add_boundary_vertex(boundary_vertex)
            for boundary_vertex in cap_boundaries
        ]

        points = [
            transaction.vertices[tx_id].co_world
            for tx_id in tx_vertex_ids
        ]

        expected_normal = calculate_polygon_normal(points)

        transaction.add_face(
            vertex_ids=tx_vertex_ids,
            face_kind=FACE_VERT,
            source_face_id=None,
            expected_normal=expected_normal
        )

# -----------------------------------------------------------------------------
# F_EDGE face
# -----------------------------------------------------------------------------

def build_edge_face(transaction, edge_data, vertex_boundaries):
    """
    Build F_EDGE bevel strip from boundary vertices.
    """

    edge_id = edge_data["edge_id"]
    edge_v0, edge_v1 = edge_data["vertex_ids"]

    face_ids = [
        face_data["face_id"]
        for face_data in edge_data["faces"]
    ]

    face_a_id = face_ids[0]
    face_b_id = face_ids[1]

    bv_v0_fa = find_boundary(vertex_boundaries, edge_v0, face_a_id)
    bv_v1_fa = find_boundary(vertex_boundaries, edge_v1, face_a_id)
    bv_v1_fb = find_boundary(vertex_boundaries, edge_v1, face_b_id)
    bv_v0_fb = find_boundary(vertex_boundaries, edge_v0, face_b_id)

    if None in (bv_v0_fa, bv_v1_fa, bv_v1_fb, bv_v0_fb):
        print("[BevelX] F_EDGE build failed: missing boundary vertex.")
        return None

    tx_v0_fa = transaction.add_boundary_vertex(bv_v0_fa)
    tx_v1_fa = transaction.add_boundary_vertex(bv_v1_fa)
    tx_v1_fb = transaction.add_boundary_vertex(bv_v1_fb)
    tx_v0_fb = transaction.add_boundary_vertex(bv_v0_fb)

    face_indices = [
        tx_v0_fa,
        tx_v1_fa,
        tx_v1_fb,
        tx_v0_fb,
    ]

    expected_normal = get_expected_bevel_face_normal(edge_data)

    face_indices = orient_transaction_face_indices_to_normal(
        transaction=transaction,
        face_indices=face_indices,
        expected_normal=expected_normal
    )

    return transaction.add_face(
        vertex_ids=face_indices,
        face_kind=FACE_EDGE,
        source_edge_id=edge_id,
        expected_normal=expected_normal
    )

# -----------------------------------------------------------------------------
# Degenerate face checks
# -----------------------------------------------------------------------------

def triangle_area_from_points(a, b, c):
    """
    Return triangle area from three world-space points.
    """

    ab = bxm.sub(b, a)
    ac = bxm.sub(c, a)

    cross_value = bxm.cross(ab, ac)

    return 0.5 * bxm.length(cross_value)


def transaction_triangle_area(transaction, vertex_ids):
    """
    Return area for a transaction triangle.

    If vertex_ids is not a triangle, return 0.0.
    """

    if len(vertex_ids) != 3:
        return 0.0

    points = [
        transaction.vertices[tx_id].co_world
        for tx_id in vertex_ids
    ]

    return triangle_area_from_points(
        points[0],
        points[1],
        points[2]
    )

def transaction_polygon_area(transaction, vertex_ids):
    """
    Approximate polygon area by triangulating from the first vertex.

    Works well enough for degenerate checks on mostly planar patch faces.
    """

    if len(vertex_ids) < 3:
        return 0.0

    first = transaction.vertices[vertex_ids[0]].co_world
    area = 0.0

    for i in range(1, len(vertex_ids) - 1):
        a = first
        b = transaction.vertices[vertex_ids[i]].co_world
        c = transaction.vertices[vertex_ids[i + 1]].co_world

        area += triangle_area_from_points(a, b, c)

    return area


def is_degenerate_transaction_polygon(transaction,
                                      vertex_ids,
                                      area_epsilon=1.0e-8):
    """
    Return True if polygon has near-zero area.
    """

    area = transaction_polygon_area(
        transaction=transaction,
        vertex_ids=vertex_ids
    )

    return area <= area_epsilon

def is_degenerate_transaction_triangle(transaction,
                                       vertex_ids,
                                       area_epsilon=1.0e-8):
    """
    Return True if triangle has near-zero area.
    """

    area = transaction_triangle_area(
        transaction=transaction,
        vertex_ids=vertex_ids
    )

    return area <= area_epsilon

# -----------------------------------------------------------------------------
# F_RECON faces
# -----------------------------------------------------------------------------
def build_reconstructed_face(transaction,
                             bm,
                             face_id,
                             edge_v0,
                             edge_v1,
                             vertex_boundaries):
    """
    Build F_RECON face.

    Cases handled:
        1. Face contains selected edge:
            replace edge_v0-edge_v1 segment with matching boundary vertices
            for this face.

        2. Face touches only one selected-edge endpoint:
            replace that original endpoint vertex with the two boundary vertices
            that border this face.

    This avoids overlapping old untouched support faces.
    """

    face = bm.faces[face_id]
    face_vertices = list(face.vertices)

    rebuilt_tx_ids = []

    count = len(face_vertices)
    i = 0

    while i < count:
        current_v = face_vertices[i]
        next_v = face_vertices[(i + 1) % count]

        # ------------------------------------------------------------
        # Case A: selected edge appears as edge_v0 -> edge_v1
        # ------------------------------------------------------------

        if current_v == edge_v0 and next_v == edge_v1:
            boundary_a = find_boundary(vertex_boundaries, edge_v0, face_id)
            boundary_b = find_boundary(vertex_boundaries, edge_v1, face_id)

            if boundary_a is None or boundary_b is None:
                print("[BevelX] F_RECON failed: missing direct boundary for face {0}".format(face_id))
                return None

            rebuilt_tx_ids.append(transaction.add_boundary_vertex(boundary_a))
            rebuilt_tx_ids.append(transaction.add_boundary_vertex(boundary_b))

            i += 2
            continue

        # ------------------------------------------------------------
        # Case B: selected edge appears as edge_v1 -> edge_v0
        # ------------------------------------------------------------

        if current_v == edge_v1 and next_v == edge_v0:
            boundary_a = find_boundary(vertex_boundaries, edge_v1, face_id)
            boundary_b = find_boundary(vertex_boundaries, edge_v0, face_id)

            if boundary_a is None or boundary_b is None:
                print("[BevelX] F_RECON failed: missing reverse boundary for face {0}".format(face_id))
                return None

            rebuilt_tx_ids.append(transaction.add_boundary_vertex(boundary_a))
            rebuilt_tx_ids.append(transaction.add_boundary_vertex(boundary_b))

            i += 2
            continue

        # ------------------------------------------------------------
        # Case C: this face touches one affected endpoint vertex only
        # ------------------------------------------------------------

        if current_v == edge_v0 or current_v == edge_v1:
            replacement_ids = build_terminal_vertex_replacement_for_face(
                transaction=transaction,
                bm=bm,
                face_id=face_id,
                face_vertices=face_vertices,
                vertex_index=i,
                vertex_id=current_v,
                vertex_boundaries=vertex_boundaries
            )

            if replacement_ids:
                rebuilt_tx_ids.extend(replacement_ids)
            else:
                # Fallback: keep original if something unexpected happens.
                rebuilt_tx_ids.append(
                    transaction.add_original_vertex(
                        bm=bm,
                        original_vertex_id=current_v
                    )
                )

            i += 1
            continue

        # ------------------------------------------------------------
        # Normal untouched original vertex
        # ------------------------------------------------------------

        rebuilt_tx_ids.append(
            transaction.add_original_vertex(
                bm=bm,
                original_vertex_id=current_v
            )
        )

        i += 1

    expected_normal = list(face.normal_world)

    rebuilt_tx_ids = orient_transaction_face_indices_to_normal(
        transaction=transaction,
        face_indices=rebuilt_tx_ids,
        expected_normal=expected_normal
    )

    return transaction.add_face(
        vertex_ids=rebuilt_tx_ids,
        face_kind=FACE_RECON,
        source_face_id=face_id,
        expected_normal=expected_normal
    )

def build_terminal_vertex_replacement_for_face(transaction,
                                               bm,
                                               face_id,
                                               face_vertices,
                                               vertex_index,
                                               vertex_id,
                                               vertex_boundaries):
    """
    Replace an affected endpoint vertex in a face that does not contain the
    selected edge directly.

    Example:
        selected edge is 7
        affected vertex is 3
        support face is 0

        face 0 still contains old vertex 3, but should be rebuilt to use:
            boundary for the side before vertex 3
            boundary for the side after vertex 3

    The boundary face IDs are found through the neighboring edges around the
    vertex inside this face.
    """

    count = len(face_vertices)

    prev_v = face_vertices[(vertex_index - 1) % count]
    next_v = face_vertices[(vertex_index + 1) % count]

    prev_edge_id = get_edge_id_between_vertices(
        bm=bm,
        vertex_a=prev_v,
        vertex_b=vertex_id
    )

    next_edge_id = get_edge_id_between_vertices(
        bm=bm,
        vertex_a=vertex_id,
        vertex_b=next_v
    )

    prev_other_face = get_other_face_on_edge(
        bm=bm,
        edge_id=prev_edge_id,
        current_face_id=face_id
    )

    next_other_face = get_other_face_on_edge(
        bm=bm,
        edge_id=next_edge_id,
        current_face_id=face_id
    )

    if prev_other_face is None or next_other_face is None:
        print(
            "[BevelX] Terminal replacement failed at vertex {0} on face {1}: "
            "could not find neighboring faces.".format(vertex_id, face_id)
        )
        return None

    boundary_prev = find_boundary(
        vertex_boundaries,
        vertex_id,
        prev_other_face
    )

    boundary_next = find_boundary(
        vertex_boundaries,
        vertex_id,
        next_other_face
    )

    if boundary_prev is None or boundary_next is None:
        print(
            "[BevelX] Terminal replacement failed at vertex {0} on face {1}: "
            "missing boundary for neighboring faces {2}, {3}.".format(
                vertex_id,
                face_id,
                prev_other_face,
                next_other_face
            )
        )
        return None

    return [
        transaction.add_boundary_vertex(boundary_prev),
        transaction.add_boundary_vertex(boundary_next),
    ]

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def find_boundary(vertex_boundaries, vertex_id, face_id):
    boundary_list = vertex_boundaries.get(vertex_id, [])

    for boundary_vertex in boundary_list:
        if boundary_vertex.face_id == face_id:
            return boundary_vertex

    return None


def get_expected_bevel_face_normal(edge_data):
    normal = [0.0, 0.0, 0.0]

    for face_data in edge_data.get("faces", []):
        normal = bxm.add(normal, face_data["normal"])

    if bxm.is_zero(normal):
        return [0.0, 0.0, 0.0]

    return bxm.normalize(normal)


def orient_transaction_face_indices_to_normal(transaction,
                                              face_indices,
                                              expected_normal):
    expected_normal = bxm.normalize(expected_normal)

    if bxm.is_zero(expected_normal):
        return face_indices

    points = [
        transaction.vertices[index].co_world
        for index in face_indices
    ]

    current_normal = calculate_polygon_normal(points)

    if bxm.is_zero(current_normal):
        return face_indices

    if bxm.dot(current_normal, expected_normal) < 0.0:
        return [face_indices[0]] + list(reversed(face_indices[1:]))

    return face_indices


def calculate_polygon_normal(points):
    if len(points) < 3:
        return [0.0, 0.0, 0.0]

    p0 = points[0]

    for i in range(1, len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]

        edge_a = bxm.sub(p1, p0)
        edge_b = bxm.sub(p2, p0)

        normal = bxm.cross(edge_a, edge_b)

        if not bxm.is_zero(normal):
            return bxm.normalize(normal)

    return [0.0, 0.0, 0.0]

def get_affected_face_ids_for_single_edge(bm, edge_v0, edge_v1):
    """
    Return all original faces touched by the selected edge endpoints.

    For a terminal single-edge bevel, this is broader than only the two
    faces adjacent to the selected edge.

    Example cube edge:
        edge endpoints 3 and 5

        vertex 3 faces: [0, 1, 4]
        vertex 5 faces: [1, 2, 4]

        result: [0, 1, 2, 4]
    """

    affected = set()

    for face_id in bm.vertices[edge_v0].faces:
        affected.add(face_id)

    for face_id in bm.vertices[edge_v1].faces:
        affected.add(face_id)

    return sorted(affected)


def face_contains_selected_edge_pair(face_vertices, edge_v0, edge_v1):
    """
    Return True if a face contains the selected edge as a consecutive pair.
    """

    count = len(face_vertices)

    for i in range(count):
        current_v = face_vertices[i]
        next_v = face_vertices[(i + 1) % count]

        if current_v == edge_v0 and next_v == edge_v1:
            return True

        if current_v == edge_v1 and next_v == edge_v0:
            return True

    return False


def get_edge_id_between_vertices(bm, vertex_a, vertex_b):
    """
    Return edge ID connecting two vertices.
    """

    key = tuple(sorted((vertex_a, vertex_b)))
    return bm.edge_key_to_id.get(key)


def get_other_face_on_edge(bm, edge_id, current_face_id):
    """
    Given an edge and one face using it, return the other face using the edge.
    """

    if edge_id is None:
        return None

    for face_id in bm.edges[edge_id].faces:
        if face_id != current_face_id:
            return face_id

    return None