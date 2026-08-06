# BX_transaction.py

from __future__ import print_function

from BX_math import BX_math as bxm
from BX_profile import BX_log


FACE_ORIG = "F_ORIG"
FACE_EDGE = "F_EDGE"
FACE_VERT = "F_VERT"
FACE_RECON = "F_RECON"

ALLOWED_BEVEL_FACE_KINDS = set([
    FACE_EDGE,
    FACE_VERT,
    FACE_RECON,
])

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
                 face_id=None,
                 edge_before_id=None,
                 edge_after_id=None,
                 edge_on_id=None,
                 boundary_role=None):
        self.id = int(vertex_id)

        self.co_world = list(co_world)

        self.source = source

        self.original_vertex_id = original_vertex_id
        self.boundary_id = boundary_id
        self.selected_edge_id = selected_edge_id
        self.face_id = face_id

        # Passive metadata only.
        # Do not make reconstruction decisions from these yet.
        self.edge_before_id = edge_before_id
        self.edge_after_id = edge_after_id
        self.edge_on_id = edge_on_id
        self.boundary_role = boundary_role

    def __repr__(self):
        return (
            "BX_TransactionVertex(id={0}, source={1}, orig_v={2}, "
            "boundary={3}, edge={4}, face={5}, before={6}, after={7}, "
            "on={8}, role={9}, co={10})"
        ).format(
            self.id,
            self.source,
            self.original_vertex_id,
            self.boundary_id,
            self.selected_edge_id,
            self.face_id,
            self.edge_before_id,
            self.edge_after_id,
            self.edge_on_id,
            self.boundary_role,
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

        self.faces_to_replace = set()

        self.inner_miter_local_cap_keys = set()

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
            face_id=boundary_vertex.face_id,
            edge_before_id=getattr(boundary_vertex, "edge_before_id", None),
            edge_after_id=getattr(boundary_vertex, "edge_after_id", None),
            edge_on_id=getattr(boundary_vertex, "edge_on_id", None),
            boundary_role=getattr(boundary_vertex, "boundary_role", None)
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

    def add_face_to_replace(self, face_id):
        """
        Mark one original Maya source face for deletion/replacement.
        """

        if face_id is None:
            return

        self.faces_to_replace.add(int(face_id))


    def add_faces_to_replace(self, face_ids):
        """
        Mark many original Maya source faces for deletion/replacement.
        """

        for face_id in face_ids or []:
            self.add_face_to_replace(face_id)

    # -------------------------------------------------------------------------
    # Debug
    # -------------------------------------------------------------------------

    def debug_print(self):
        if BX_log.is_enabled("DEBUG", "transaction_dump"):
            BX_log.debug("BevelTransaction:", channel="transaction_dump")
            BX_log.debug("  transaction vertices: {0}".format(len(self.vertices)), channel="transaction_dump")
            BX_log.debug("  transaction faces: {0}".format(len(self.faces)), channel="transaction_dump")
            BX_log.debug("  faces to replace: {0}".format(self.faces_to_replace), channel="transaction_dump")

            BX_log.debug("  vertices:", channel="transaction_dump")
            for vertex in self.vertices:
                BX_log.debug("    {0}".format(vertex), channel="transaction_dump")

            BX_log.debug("  faces:", channel="transaction_dump")
            for face in self.faces:
                BX_log.debug("    {0}".format(face), channel="transaction_dump")

            return

        if BX_log.is_enabled("DEBUG", "transaction"):
            BX_log.debug(
                "BevelTransaction summary: vertices={0}, faces={1}, replace={2}".format(
                    len(self.vertices),
                    len(self.faces),
                    len(self.faces_to_replace)
                ),
                channel="transaction"
            )
        BX_log.debug("BevelTransaction:", channel="transaction_dump")
        BX_log.debug("  transaction vertices: {0}".format(len(self.vertices)), channel="transaction_dump")
        BX_log.debug("  transaction faces: {0}".format(len(self.faces)), channel="transaction_dump")
        BX_log.debug("  faces to replace: {0}".format(self.faces_to_replace), channel="transaction_dump")

        BX_log.debug("  vertices:", channel="transaction_dump")
        for vertex in self.vertices:
            BX_log.debug("    {0}".format(vertex), channel="transaction_dump")

        BX_log.debug("  faces:", channel="transaction_dump")
        for face in self.faces:
            BX_log.debug("    {0}".format(face), channel="transaction_dump")


# -----------------------------------------------------------------------------
# Transaction construction
# -----------------------------------------------------------------------------
def add_bevel_face(transaction,
                   vertex_ids,
                   face_kind,
                   source_face_id=None,
                   source_edge_id=None,
                   expected_normal=None,
                   debug_label=None):
    """
    Blender-style face creation gate for BevelX.

    All generated bevel topology should go through this helper.

    Allowed output kinds:
        F_EDGE   -> bevel strip along one selected edge
        F_VERT   -> vertex / VMesh region
        F_RECON  -> reconstructed original source face

    Do not generate F_CAP / F_PATCH / INNER_MITER_PATCH here.
    """

    if face_kind not in ALLOWED_BEVEL_FACE_KINDS:
        raise RuntimeError(
            "Non-Blender bevel face kind blocked: {0}, label={1}, verts={2}".format(
                face_kind,
                debug_label,
                vertex_ids
            )
        )

    if not vertex_ids or len(vertex_ids) < 3:
        BX_log.warn(
            "add_bevel_face skipped: fewer than 3 verts, kind={0}, label={1}, verts={2}".format(
                face_kind,
                debug_label,
                vertex_ids
            ),
            channel="summary"
        )
        return None

    if face_kind == FACE_RECON and source_face_id is None:
        raise RuntimeError(
            "F_RECON must carry source_face_id, label={0}, verts={1}".format(
                debug_label,
                vertex_ids
            )
        )

    face_id = transaction.add_face(
        vertex_ids=vertex_ids,
        face_kind=face_kind,
        source_face_id=source_face_id,
        source_edge_id=source_edge_id,
        expected_normal=expected_normal
    )

    # Maya-side equivalent of Blender replacing affected original topology.
    # This is safe even if affected faces are already marked earlier.
    if face_kind == FACE_RECON and source_face_id is not None:
        if hasattr(transaction, "add_face_to_replace"):
            transaction.add_face_to_replace(source_face_id)

    return face_id

# -----------------------------------------------------------------------------
# Transaction construction
# -----------------------------------------------------------------------------
def transaction_has_terminal_multi_boundaries(vertex_boundaries):
    """
    Return True if any original vertex has TERMINAL_MULTI boundary data.
    """

    for boundary_list in vertex_boundaries.values():
        for boundary_vertex in boundary_list:
            if getattr(boundary_vertex, "source", None) == "TERMINAL_MULTI":
                return True

    return False


def vertex_has_terminal_multi_boundaries(vertex_boundaries, vertex_id):
    """
    Return True if this original vertex has TERMINAL_MULTI boundary data.
    """

    boundary_list = vertex_boundaries.get(vertex_id, [])

    for boundary_vertex in boundary_list:
        if getattr(boundary_vertex, "source", None) == "TERMINAL_MULTI":
            return True

    return False

def get_selected_edge_ids_from_edges_data(edges_data):
    return set(
        edge_data["edge_id"]
        for edge_data in edges_data
    )

def face_edges_are_all_selected(bm, face_id, selected_edge_ids):
    """
    Return True when every edge of source face face_id is selected.
    """

    face_edges = list(bm.faces[face_id].edges)

    if not face_edges:
        return False

    for edge_id in face_edges:
        if edge_id not in selected_edge_ids:
            return False

    return True

def build_single_edge_transaction(edge_data,
                                  vertex_boundaries,
                                  bm=None,
                                  bevel_vertices=None,
                                  settings=None):
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

    if transaction_has_terminal_multi_boundaries(vertex_boundaries):
        BX_log.warn(
            "Single-edge transaction using selection path because TERMINAL_MULTI boundaries exist.",
            channel="summary"
        )

        return build_selection_transaction(
            edges_data=[edge_data],
            vertex_boundaries=vertex_boundaries,
            bm=bm,
            bevel_vertices=bevel_vertices,
            settings=settings
        )

    transaction = BX_BevelTransaction()

    edge_id = edge_data["edge_id"]
    edge_v0, edge_v1 = edge_data["vertex_ids"]

    adjacent_face_ids = [
        face_data["face_id"]
        for face_data in edge_data["faces"]
    ]

    if len(adjacent_face_ids) != 2:
        BX_log.warn("Transaction build requires exactly 2 adjacent selected-edge faces.",
                    channel="transaction")
        return transaction

    build_edge_face(
        transaction=transaction,
        edge_data=edge_data,
        vertex_boundaries=vertex_boundaries
    )

    if bm is None:
        transaction.add_faces_to_replace(adjacent_face_ids)

        BX_log.warn("Transaction warning: bm is None, only F_EDGE was built.",
                    channel="transaction")
        return transaction

    affected_face_ids = get_affected_face_ids_for_single_edge(
        bm=bm,
        edge_v0=edge_v0,
        edge_v1=edge_v1
    )

    transaction.add_faces_to_replace(affected_face_ids)

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

def build_selection_transaction(edges_data,
                                vertex_boundaries,
                                bm=None,
                                bevel_vertices=None,
                                settings=None):
    """
    Build a full preview/apply transaction for a selected edge set.

    Current output:
        - F_EDGE faces for all selected edges.
        - F_VERT faces for simple tri caps.
        - F_RECON faces for all affected original faces.
    """

    transaction = BX_BevelTransaction()
    if settings is None:
        settings = {}

    # Validate selected-edge strips first.
    for edge_data in edges_data:
        if not can_build_edge_face_from_boundaries(edge_data, vertex_boundaries):
            BX_log.warn("Selection transaction skipped: missing boundary data for edge {0}.".format(
                    edge_data["edge_id"]), channel="transaction")
            return transaction

    # 1. Build all selected-edge bevel strip faces.
    for edge_data in edges_data:
        build_edge_face(
            transaction=transaction,
            edge_data=edge_data,
            vertex_boundaries=vertex_boundaries
        )

    # 2. Build vertex cap faces.
    build_vertex_cap_faces(
        transaction=transaction,
        vertex_boundaries=vertex_boundaries,
        bm=bm
    )

    debug_inner_miter_candidates(
        bevel_vertices=bevel_vertices,
        vertex_boundaries=vertex_boundaries,
        central_face_id=None
    )
    if bm is None:
        return transaction

    affected_face_ids = get_affected_face_ids_for_selected_edges(bm=bm, edges_data=edges_data)

    transaction.add_faces_to_replace(affected_face_ids)
    BX_log.warn("SOURCE faces marked for replacement: count={0}, faces={1}".format(
            len(affected_face_ids), sorted(list(affected_face_ids))), channel="summary")
    
    affected_vertex_ids = get_affected_vertex_ids_for_selected_edges(edges_data)

    for face_id in sorted(affected_face_ids):
        build_reconstructed_face_for_selection(
            transaction=transaction,
            bm=bm,
            face_id=face_id,
            affected_vertex_ids=affected_vertex_ids,
            vertex_boundaries=vertex_boundaries,
            bevel_vertices=bevel_vertices,
            settings=settings
        )

    return transaction
    

# -----------------------------------------------------------------------------
# F_CAP / inner face cap helpers
# -----------------------------------------------------------------------------
def get_edge_ring_ids_from_bevel_vertex(bevel_vertex):
    """
    Return edge ids from bevel_vertex.edge_halves in cyclic order.
    """

    edge_ring = []

    for edge_half in list(getattr(bevel_vertex, "edge_halves", [])):
        edge_id = getattr(edge_half, "edge_id", None)

        if edge_id is not None:
            edge_ring.append(edge_id)

    return edge_ring


def cyclic_gap_between_edge_ids(edge_ring, start_edge_id, end_edge_id):
    """
    Return edge ids encountered after start_edge_id until end_edge_id.
    Non-inclusive.
    """

    if not edge_ring:
        return []

    if start_edge_id not in edge_ring:
        return []

    if end_edge_id not in edge_ring:
        return []

    count = len(edge_ring)
    start_index = edge_ring.index(start_edge_id)

    result = []
    cursor = (start_index + 1) % count
    safety = 0

    while edge_ring[cursor] != end_edge_id:
        result.append(edge_ring[cursor])

        cursor = (cursor + 1) % count
        safety += 1

        if safety > count:
            return []

    return result


def is_uneven_high_valence_chain_2_vertex(bevel_vertex):
    """
    Return True for selected_count == 2 vertices whose cyclic gaps are not
    the ordinary clean CHAIN_2 case.

    Clean old CHAIN_2 case:
        two selected edges
        exactly one non-selected middle edge on each side

    Uneven high-valence case:
        two selected edges
        one side has 0, 2, 3, ... middle edges
        or the edge ring has more complicated topology

    These must NOT use old INNER_MITER local triangle logic.
    """

    selected_edges = get_bevel_vertex_selected_edges(bevel_vertex)

    if len(selected_edges) != 2:
        return False

    edge_ring = get_edge_ring_ids_from_bevel_vertex(bevel_vertex)

    if len(edge_ring) <= 2:
        return False

    edge_a_id = selected_edges[0]
    edge_b_id = selected_edges[1]

    gap_ab = cyclic_gap_between_edge_ids(
        edge_ring=edge_ring,
        start_edge_id=edge_a_id,
        end_edge_id=edge_b_id
    )

    gap_ba = cyclic_gap_between_edge_ids(
        edge_ring=edge_ring,
        start_edge_id=edge_b_id,
        end_edge_id=edge_a_id
    )

    # Adjacent selected edges are CORNER_2 territory.
    # Do not classify them as uneven CHAIN_2.
    if not gap_ab or not gap_ba:
        return False

    # Old CHAIN_2 inner-miter is safe only for balanced one-middle each side.
    if len(gap_ab) == 1 and len(gap_ba) == 1:
        return False

    BX_log.warn(
        "INNER_MITER skipped uneven high-valence CHAIN_2 vertex {0}: selected={1}, ring={2}, gap_ab={3}, gap_ba={4}".format(
            getattr(bevel_vertex, "vertex_id", getattr(bevel_vertex, "id", None)),
            selected_edges,
            edge_ring,
            gap_ab,
            gap_ba
        ),
        channel="summary"
    )

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
    Log likely INNER_MITER_PATCH candidates.

    For the current BevelX data model:
        - topology kind may not be stored on BX_BevelVertex
        - selected_count may not be stored on BX_BevelVertex
        - boundary data lives in vertex_boundaries

    First-pass candidate rule:
        - exactly 2 selected/beveled edges
        - exactly 4 boundary vertices

    This catches current CHAIN_2 vertices and excludes current CORNER_2
    vertices.

    Logging behavior:
        - completely silent unless the "miter" channel is enabled
        - per-vertex inspection is TRACE
        - candidate summaries are DEBUG
        - skip messages are DEBUG
    """

    if not BX_log.is_enabled("DEBUG", "miter"):
        return

    if bevel_vertices is None:
        BX_log.debug(
            "INNER_MITER debug skipped: bevel_vertices is None.",
            channel="miter"
        )
        return

    if vertex_boundaries is None:
        BX_log.debug(
            "INNER_MITER debug skipped: vertex_boundaries is None.",
            channel="miter"
        )
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

        BX_log.trace(
            "INNER_MITER inspect vertex {0}: selected_edges={1}, boundary_count={2}".format(
                vertex_id,
                selected_edges,
                boundary_count
            ),
            channel="miter"
        )

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
                    getattr(
                        boundary_vertex,
                        "edge",
                        getattr(boundary_vertex, "edge_id", "?")
                    )
                )
            )

        BX_log.debug(
            "INNER_MITER candidate vertex {0}: selected_edges={1}, boundary_count={2}".format(
                vertex_id,
                selected_edges,
                boundary_count
            ),
            channel="miter"
        )

        BX_log.debug(
            "  boundaries: {0}".format(boundary_debug),
            channel="miter"
        )

    BX_log.debug(
        "INNER_MITER candidate debug found {0} candidates.".format(found),
        channel="miter"
    )
#######################################################
# Sector / CHAIN_2_MULTI gap boundary helpers
#######################################################
def is_sector_boundary_vertex(boundary_vertex):
    return getattr(boundary_vertex, "source", None) in (
        "SECTOR_BOUNDARY",
    )

def vertex_has_sector_boundaries(vertex_boundaries, vertex_id):
    boundary_list = vertex_boundaries.get(vertex_id, [])

    for boundary_vertex in boundary_list:
        if is_sector_boundary_vertex(boundary_vertex):
            return True

    return False

def find_sector_boundary_for_face_edge(vertex_boundaries,
                                       vertex_id,
                                       edge_id,
                                       face_id):
    """
    Find sector boundary for one incident edge at one original vertex.

    Works for:
        selected edge side aliases:
            selected_edge_id == edge_id and face_id == face_id

        middle edge aliases:
            edge_on_id == edge_id
    """

    boundary_list = vertex_boundaries.get(vertex_id, [])

    for boundary_vertex in boundary_list:
        if not is_sector_boundary_vertex(boundary_vertex):
            continue

        if getattr(boundary_vertex, "selected_edge_id", None) == edge_id:
            if getattr(boundary_vertex, "face_id", None) == face_id:
                return boundary_vertex

    for boundary_vertex in boundary_list:
        if not is_sector_boundary_vertex(boundary_vertex):
            continue

        if getattr(boundary_vertex, "edge_on_id", None) == edge_id:
            return boundary_vertex

    return None

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

def build_sector_face_vertex_replacement(transaction,
                                         bm,
                                         face_id,
                                         face_vertices,
                                         vertex_index,
                                         vertex_id,
                                         vertex_boundaries):
    """
    Replace one affected original vertex in one F_RECON source face using
    sector / BoundVert-style boundaries.

    Blender-style idea:
        Source face contains:
            prev_v -> vertex_id -> next_v

        Replacement uses:
            sector boundary attached to edge(prev_v, vertex_id)
            sector boundary attached to edge(vertex_id, next_v)

    If both incident face edges map to the same sector boundary, the result
    collapses to one tx vertex. That is expected for support faces inside
    one sector.
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

    if prev_edge_id is None or next_edge_id is None:
        BX_log.warn(
            "SECTOR replacement failed at vertex {0} on face {1}: missing incident edge, prev_v={2}, next_v={3}, prev_edge={4}, next_edge={5}".format(
                vertex_id,
                face_id,
                prev_v,
                next_v,
                prev_edge_id,
                next_edge_id
            ),
            channel="summary"
        )
        return None

    boundary_prev = find_sector_boundary_for_face_edge(
        vertex_boundaries=vertex_boundaries,
        vertex_id=vertex_id,
        edge_id=prev_edge_id,
        face_id=face_id
    )

    boundary_next = find_sector_boundary_for_face_edge(
        vertex_boundaries=vertex_boundaries,
        vertex_id=vertex_id,
        edge_id=next_edge_id,
        face_id=face_id
    )

    if boundary_prev is None or boundary_next is None:
        BX_log.warn(
            "SECTOR replacement failed at vertex {0} on face {1}: prev_edge={2}, next_edge={3}, boundary_prev={4}, boundary_next={5}".format(
                vertex_id,
                face_id,
                prev_edge_id,
                next_edge_id,
                getattr(boundary_prev, "id", None),
                getattr(boundary_next, "id", None)
            ),
            channel="summary"
        )
        return None

    boundary_prev, boundary_next = order_support_boundary_pair(
        bm=bm,
        face_vertices=face_vertices,
        vertex_index=vertex_index,
        vertex_id=vertex_id,
        boundary_a=boundary_prev,
        boundary_b=boundary_next
    )

    tx_prev = transaction.add_boundary_vertex(boundary_prev)
    tx_next = transaction.add_boundary_vertex(boundary_next)

    tx_ids = collapse_transaction_ids_by_position(
        transaction=transaction,
        tx_ids=[tx_prev, tx_next]
    )

    if not tx_ids:
        BX_log.warn(
            "SECTOR replacement failed at vertex {0} on face {1}: collapsed to no vertices.".format(
                vertex_id,
                face_id
            ),
            channel="summary"
        )
        return None

    BX_log.warn(
        "SECTOR replacement at vertex {0} on face {1}: prev_edge={2}, next_edge={3}, boundary_prev={4}, boundary_next={5}, tx={6}".format(
            vertex_id,
            face_id,
            prev_edge_id,
            next_edge_id,
            getattr(boundary_prev, "id", None),
            getattr(boundary_next, "id", None),
            tx_ids
        ),
        channel="summary"
    )

    return tx_ids

def build_direct_face_loop_reconstruction(transaction,
                                          bm,
                                          face_id,
                                          vertex_boundaries):
    """
    Blender-style source-face rebuild.

    If every vertex of the original face has a boundary vertex for this
    source face, rebuild the source face directly in original face-loop order.

    """

    face_vertices = list(bm.faces[face_id].vertices)

    tx_ids = []

    for vertex_id in face_vertices:
        boundary_vertex = find_boundary(
            vertex_boundaries=vertex_boundaries,
            vertex_id=vertex_id,
            face_id=face_id
        )

        if boundary_vertex is None:
            return False

        tx_ids.append(
            transaction.add_boundary_vertex(boundary_vertex)
        )

    tx_ids = collapse_transaction_ids_by_position(
        transaction=transaction,
        tx_ids=tx_ids
    )

    if len(tx_ids) < 3:
        return False

    expected_normal = bm.faces[face_id].normal_world

    tx_ids = orient_transaction_face_indices_to_normal(
        transaction=transaction,
        face_indices=tx_ids,
        expected_normal=expected_normal
    )

    if is_degenerate_transaction_polygon(
        transaction=transaction,
        vertex_ids=tx_ids
    ):
        return False

    add_bevel_face(
        transaction=transaction,
        vertex_ids=tx_ids,
        face_kind=FACE_RECON,
        source_face_id=face_id,
        source_edge_id=None,
        expected_normal=expected_normal,
        debug_label="DIRECT_FACE_RECON face {0}".format(face_id)
    )

    BX_log.warn(
        "DIRECT_FACE_RECON built for face {0}: verts={1}".format(
            face_id,
            tx_ids
        ),
        channel="summary"
    )

    return True

def build_reconstructed_face_for_selection(transaction,
                                           bm,
                                           face_id,
                                           affected_vertex_ids,
                                           vertex_boundaries,
                                           bevel_vertices=None,
                                           settings=None):
    """
    Build F_RECON for a face affected by a selected edge set.

    Blender-style rule:
        First try to rebuild the original source face directly from
        face-owned boundary vertices in original face-loop order.

    If that does not work:
        Rebuild the source face by walking the original face loop and replacing
        affected vertices with the appropriate boundary/sector/terminal support
        vertices.

    No F_CAP / F_PATCH / ADJ_LITE ownership should happen here.
    """

    # ------------------------------------------------------------
    # Blender-style direct face-loop reconstruction.
    #
    # If every loop vertex has a face-owned boundary for this face,
    # the whole original face can be rebuilt directly as F_RECON.
    #
    # ------------------------------------------------------------
    if build_direct_face_loop_reconstruction(
        transaction=transaction,
        bm=bm,
        face_id=face_id,
        vertex_boundaries=vertex_boundaries
    ):
        return True

    face = bm.faces[face_id]
    face_vertices = list(face.vertices)

    rebuilt_tx_ids = []

    for i, current_v in enumerate(face_vertices):
        # ------------------------------------------------------------
        # Untouched original vertex.
        # ------------------------------------------------------------
        if current_v not in affected_vertex_ids:
            rebuilt_tx_ids.append(
                transaction.add_original_vertex(
                    bm=bm,
                    original_vertex_id=current_v
                )
            )
            continue

        # ------------------------------------------------------------
        # Case A:
        # Direct face-owned boundary.
        #
        # This MUST remain first.
        # Faces that directly own boundary points should consume those
        # boundary points before terminal/sector support replacement runs.
        # ------------------------------------------------------------
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

        # ------------------------------------------------------------
        # Case B:
        # Sector / BoundVert replacement.
        # ------------------------------------------------------------
        if vertex_has_sector_boundaries(
            vertex_boundaries=vertex_boundaries,
            vertex_id=current_v
        ):
            replacement_ids = build_sector_face_vertex_replacement(
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
                continue

        # ------------------------------------------------------------
        # Case C:
        # TERMINAL_MULTI support-face replacement.
        # ------------------------------------------------------------
        if vertex_has_terminal_multi_boundaries(
            vertex_boundaries=vertex_boundaries,
            vertex_id=current_v
        ):
            replacement_ids = build_terminal_multi_face_vertex_replacement(
                transaction=transaction,
                bm=bm,
                face_vertices=face_vertices,
                vertex_index=i,
                vertex_id=current_v,
                vertex_boundaries=vertex_boundaries
            )

            if replacement_ids:
                rebuilt_tx_ids.extend(replacement_ids)
                continue

            BX_log.warn(
                "TERMINAL_MULTI support replacement failed at vertex {0} on face {1}; falling back to legacy support replacement.".format(
                    current_v,
                    face_id
                ),
                channel="summary"
            )

        # ------------------------------------------------------------
        # Case D:
        # Legacy support-face replacement.
        #
        # Keep temporarily until all support replacement is folded into
        # direct F_RECON / sector replacement.
        # ------------------------------------------------------------
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
            continue

        # ------------------------------------------------------------
        # Final conservative fallback.
        # ------------------------------------------------------------
        rebuilt_tx_ids.append(
            transaction.add_original_vertex(
                bm=bm,
                original_vertex_id=current_v
            )
        )

    # ------------------------------------------------------------
    # Clean and validate final reconstructed polygon.
    # ------------------------------------------------------------
    rebuilt_tx_ids = collapse_transaction_ids_by_position(
        transaction=transaction,
        tx_ids=rebuilt_tx_ids
    )

    if len(rebuilt_tx_ids) < 3:
        BX_log.warn(
            "F_RECON skipped for face {0}: fewer than 3 verts after collapse, verts={1}.".format(
                face_id,
                rebuilt_tx_ids
            ),
            channel="summary"
        )
        return False

    expected_normal = list(face.normal_world)

    rebuilt_tx_ids = orient_transaction_face_indices_to_normal(
        transaction=transaction,
        face_indices=rebuilt_tx_ids,
        expected_normal=expected_normal
    )

    if is_degenerate_transaction_polygon(
        transaction=transaction,
        vertex_ids=rebuilt_tx_ids
    ):
        BX_log.warn(
            "F_RECON skipped for face {0}: degenerate polygon verts={1}.".format(
                face_id,
                rebuilt_tx_ids
            ),
            channel="summary"
        )
        return False

    face = add_bevel_face(
        transaction=transaction,
        vertex_ids=rebuilt_tx_ids,
        face_kind=FACE_RECON,
        source_face_id=face_id,
        source_edge_id=None,
        expected_normal=expected_normal,
        debug_label="F_RECON face {0}".format(face_id)
    )

    if face is not None:
        BX_log.warn(
            "F_RECON built for face {0}: verts={1}".format(
                face_id,
                rebuilt_tx_ids
            ),
            channel="summary"
        )
        return True

    return False

def distance_point_to_segment(point, segment_a, segment_b):
    """
    Distance from point to segment AB.
    """

    closest = bxm.closest_point_on_segment(
        point,
        segment_a,
        segment_b
    )

    return bxm.distance(point, closest)


def boundary_distance_to_segment(boundary_vertex, segment_a, segment_b):
    """
    Distance from a boundary vertex point to a segment.
    """

    return distance_point_to_segment(
        boundary_vertex.co_world,
        segment_a,
        segment_b
    )


def order_support_boundary_pair(bm,
                                face_vertices,
                                vertex_index,
                                vertex_id,
                                boundary_a,
                                boundary_b):
    """
    Order two boundary vertices for replacing one original vertex in a support face.

    The face loop contains:
        prev_v -> vertex_id -> next_v

    The correct replacement order is:
        boundary closest to prev edge
        boundary closest to next edge
    """

    count = len(face_vertices)

    prev_v = face_vertices[(vertex_index - 1) % count]
    next_v = face_vertices[(vertex_index + 1) % count]

    vertex_point = bm.vertices[vertex_id].co_world
    prev_point = bm.vertices[prev_v].co_world
    next_point = bm.vertices[next_v].co_world

    # Original local face path:
    #     prev_v -> vertex_id -> next_v
    #
    # So replacement order should be:
    #     boundary near prev edge, boundary near next edge
    score_as_given = (
        boundary_distance_to_segment(boundary_a, prev_point, vertex_point) +
        boundary_distance_to_segment(boundary_b, vertex_point, next_point)
    )

    score_swapped = (
        boundary_distance_to_segment(boundary_b, prev_point, vertex_point) +
        boundary_distance_to_segment(boundary_a, vertex_point, next_point)
    )

    if score_swapped < score_as_given:
        return boundary_b, boundary_a

    return boundary_a, boundary_b

######################################################################
# Build Replacement and Helpers.
######################################################################

def build_terminal_multi_face_vertex_replacement(transaction,
                                                 bm,
                                                 face_vertices,
                                                 vertex_index,
                                                 vertex_id,
                                                 vertex_boundaries):
    """
    Replace a TERMINAL_MULTI original vertex inside one source face.

    This deliberately avoids role-specific logic.

    For the original face loop:

        prev_v -> vertex_id -> next_v

    choose:
        - boundary closest to prev_v -> vertex_id
        - boundary closest to vertex_id -> next_v

    This keeps the replacement in local face-loop order and avoids the previous
    A/B swapped sector problems.
    """

    boundary_list = [
        boundary_vertex
        for boundary_vertex in vertex_boundaries.get(vertex_id, [])
        if getattr(boundary_vertex, "source", None) == "TERMINAL_MULTI"
    ]

    if len(boundary_list) < 2:
        return None

    count = len(face_vertices)

    prev_v = face_vertices[(vertex_index - 1) % count]
    next_v = face_vertices[(vertex_index + 1) % count]

    vertex_point = bm.vertices[vertex_id].co_world
    prev_point = bm.vertices[prev_v].co_world
    next_point = bm.vertices[next_v].co_world

    unique_boundaries = []

    for boundary_vertex in boundary_list:
        exists = False

        for existing_boundary in unique_boundaries:
            if transaction_points_are_close(
                boundary_vertex.co_world,
                existing_boundary.co_world
            ):
                exists = True
                break

        if not exists:
            unique_boundaries.append(boundary_vertex)

    if len(unique_boundaries) < 2:
        return None

    boundary_prev = min(
        unique_boundaries,
        key=lambda boundary_vertex: boundary_distance_to_segment(
            boundary_vertex,
            prev_point,
            vertex_point
        )
    )

    remaining = [
        boundary_vertex
        for boundary_vertex in unique_boundaries
        if boundary_vertex is not boundary_prev
    ]

    if not remaining:
        return None

    boundary_next = min(
        remaining,
        key=lambda boundary_vertex: boundary_distance_to_segment(
            boundary_vertex,
            vertex_point,
            next_point
        )
    )

    boundary_prev, boundary_next = order_support_boundary_pair(
        bm=bm,
        face_vertices=face_vertices,
        vertex_index=vertex_index,
        vertex_id=vertex_id,
        boundary_a=boundary_prev,
        boundary_b=boundary_next
    )

    tx_ids = [
        transaction.add_boundary_vertex(boundary_prev),
        transaction.add_boundary_vertex(boundary_next)
    ]

    tx_ids = collapse_transaction_ids_by_position(
        transaction=transaction,
        tx_ids=tx_ids
    )

    if len(tx_ids) < 2:
        return None

    BX_log.warn(
        "TERMINAL_MULTI face replacement at vertex {0}: verts={1}".format(
            vertex_id,
            tx_ids
        ),
        channel="summary"
    )

    return tx_ids

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

    prev_edge_id = get_edge_id_between_vertices(bm=bm, vertex_a=prev_v, vertex_b=vertex_id)
    next_edge_id = get_edge_id_between_vertices(bm=bm, vertex_a=vertex_id,vertex_b=next_v)
    prev_other_face = get_other_face_on_edge(bm=bm, edge_id=prev_edge_id, current_face_id=face_id)
    next_other_face = get_other_face_on_edge(bm=bm, edge_id=next_edge_id, current_face_id=face_id)

    if vertex_id == 64:
        BX_log.warn(
            "SUPPORT inspect vertex 64 on face {0}: prev_v={1}, next_v={2}, prev_edge={3}, next_edge={4}, prev_other_face={5}, next_other_face={6}".format(
                face_id,
                prev_v,
                next_v,
                prev_edge_id,
                next_edge_id,
                prev_other_face,
                next_other_face
            ),
            channel="summary"
        )

    if prev_other_face is None or next_other_face is None:
        BX_log.debug("Support replacement failed at vertex {0} on face {1}: could not find neighboring faces.".format(
                vertex_id, face_id), channel="support")
        return None

    boundary_prev = find_boundary(vertex_boundaries, vertex_id, prev_other_face)
    boundary_next = find_boundary(vertex_boundaries, vertex_id, next_other_face)

    if boundary_prev is None or boundary_next is None:
        fallback_ids = build_support_replacement_from_available_boundaries(
            transaction=transaction,
            bm=bm,
            face_id=face_id,
            face_vertices=face_vertices,
            vertex_index=vertex_index,
            vertex_id=vertex_id,
            vertex_boundaries=vertex_boundaries
        )
        if fallback_ids:
            BX_log.debug("Support replacement fallback used at vertex {0} on face {1}: verts={2}".format(
                    vertex_id,
                    face_id,
                    fallback_ids
                ),channel="support"
            )
            return fallback_ids
        BX_log.debug(
            "Support replacement failed at vertex {0} on face {1}: missing boundaries for neighboring faces {2}, {3}.".format(
                vertex_id, face_id, prev_other_face, next_other_face), channel="support")
        return None

    boundary_prev, boundary_next = order_support_boundary_pair(
        bm=bm,
        face_vertices=face_vertices,
        vertex_index=vertex_index,
        vertex_id=vertex_id,
        boundary_a=boundary_prev,
        boundary_b=boundary_next
    )

    tx_prev = transaction.add_boundary_vertex(boundary_prev)
    tx_next = transaction.add_boundary_vertex(boundary_next)

    if vertex_id == 64:
        BX_log.warn(
            "SUPPORT replacement vertex 64 on face {0}: boundary_prev={1}, boundary_next={2}, tx=[{3}, {4}]".format(
                face_id,
                getattr(boundary_prev, "id", None),
                getattr(boundary_next, "id", None),
                tx_prev,
                tx_next
            ),
            channel="summary"
        )

    return [tx_prev, tx_next]

def build_support_replacement_from_available_boundaries(transaction,
                                                        bm,
                                                        face_id,
                                                        face_vertices,
                                                        vertex_index,
                                                        vertex_id,
                                                        vertex_boundaries):
    """
    Fallback support-face replacement.

    Important:
        This must not blindly insert every boundary around the vertex.

    For the current support face, replace the original vertex with exactly two
    boundary vertices:
        - one closest to the previous face edge
        - one closest to the next face edge

    This preserves the local original face order:
        prev_v -> vertex_id -> next_v
    """

    boundary_list = vertex_boundaries.get(vertex_id, [])

    if not boundary_list:
        return None

    count = len(face_vertices)

    prev_v = face_vertices[(vertex_index - 1) % count]
    next_v = face_vertices[(vertex_index + 1) % count]

    vertex_point = bm.vertices[vertex_id].co_world
    prev_point = bm.vertices[prev_v].co_world
    next_point = bm.vertices[next_v].co_world

    unique_boundaries = []

    for boundary_vertex in boundary_list:
        exists = False

        for existing_boundary in unique_boundaries:
            if transaction_points_are_close(
                boundary_vertex.co_world,
                existing_boundary.co_world
            ):
                exists = True
                break

        if not exists:
            unique_boundaries.append(boundary_vertex)

    if len(unique_boundaries) < 2:
        return None

    boundary_prev = min(
        unique_boundaries,
        key=lambda boundary_vertex: boundary_distance_to_segment(
            boundary_vertex,
            prev_point,
            vertex_point
        )
    )

    remaining = [
        boundary_vertex
        for boundary_vertex in unique_boundaries
        if boundary_vertex is not boundary_prev
    ]

    if not remaining:
        return None

    boundary_next = min(
        remaining,
        key=lambda boundary_vertex: boundary_distance_to_segment(
            boundary_vertex,
            vertex_point,
            next_point
        )
    )

    boundary_prev, boundary_next = order_support_boundary_pair(
        bm=bm,
        face_vertices=face_vertices,
        vertex_index=vertex_index,
        vertex_id=vertex_id,
        boundary_a=boundary_prev,
        boundary_b=boundary_next
    )

    tx_ids = [
        transaction.add_boundary_vertex(boundary_prev),
        transaction.add_boundary_vertex(boundary_next),
    ]

    tx_ids = collapse_transaction_ids_by_position(
        transaction=transaction,
        tx_ids=tx_ids
    )

    if len(tx_ids) < 2:
        return None

    return tx_ids

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

    Exclusion:
        - uneven high-valence CHAIN_2 vertices must not use old local
          inner-miter triangles.
    """

    bevel_vertex = get_bevel_vertex_by_id(
        bevel_vertices=bevel_vertices,
        vertex_id=vertex_id
    )

    if bevel_vertex is None:
        return False

    if is_uneven_high_valence_chain_2_vertex(bevel_vertex):
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

def transaction_points_are_close(point_a, point_b, epsilon=1.0e-6):
    """
    Return True if two world-space points are nearly identical.
    """

    return bxm.length(
        bxm.sub(point_a, point_b)
    ) <= epsilon


def collapse_transaction_ids_by_position(transaction,
                                         tx_ids,
                                         epsilon=1.0e-6):
    """
    Collapse repeated/coincident transaction vertices while preserving order.

    This is important for CHAIN_2 inner miter caps:
        4 boundary verts often collapse to 3 unique positions,
        producing exactly the missing triangle.
    """

    collapsed = []

    for tx_id in tx_ids:
        point = transaction.vertices[tx_id].co_world

        already_exists = False

        for existing_tx_id in collapsed:
            existing_point = transaction.vertices[existing_tx_id].co_world

            if transaction_points_are_close(
                point,
                existing_point,
                epsilon=epsilon
            ):
                already_exists = True
                break

        if not already_exists:
            collapsed.append(tx_id)

    return collapsed

def average_original_vertex_normal(bm, vertex_id):
    """
    Return averaged normal from original faces touching vertex_id.
    """

    normal = [0.0, 0.0, 0.0]

    for face_id in bm.vertices[vertex_id].faces:
        normal = bxm.add(
            normal,
            bm.faces[face_id].normal_world
        )

    normal = bxm.normalize(normal)

    if bxm.is_zero(normal):
        return [0.0, 0.0, 0.0]

    return normal

def is_corner2_boundary_vertex(boundary_vertex):
    """
    Return True if this boundary vertex belongs to the current CORNER2 system.

    Current code may expose this either through:
        - boundary_vertex.source
        - boundary_vertex.id text, for example BV7_CORNER2_F7
    """

    source = getattr(boundary_vertex, "source", "")
    boundary_id = getattr(boundary_vertex, "id", "")

    if "CORNER2" in str(source):
        return True

    if "CORNER_2" in str(source):
        return True

    if "CORNER2" in str(boundary_id):
        return True

    if "CORNER_2" in str(boundary_id):
        return True

    return False


def build_corner2_miter_faces(transaction,
                              vertex_boundaries,
                              bm=None,
                              bevel_vertices=None):
    """
    Build small triangular CORNER2 miter faces.

    This handles the C/U-shaped segments=1 case where a bend vertex has:
        - exactly 2 selected edges
        - exactly 3 CORNER2 boundary vertices

    Example from the log:
        vertex 7: selected_edges=[9, 12], boundary_count=3
        vertex 8: selected_edges=[12, 16], boundary_count=3

    These triangles are different from CHAIN_2 inner-miter local caps:
        - CHAIN_2 through usually has 4 boundaries
        - CORNER2 bend has 3 boundaries
    """

    if vertex_boundaries is None:
        return []

    created_faces = []

    for vertex_id in sorted(vertex_boundaries.keys()):
        boundary_list = vertex_boundaries.get(vertex_id, [])

        corner_boundaries = [
            boundary_vertex
            for boundary_vertex in boundary_list
            if is_corner2_boundary_vertex(boundary_vertex)
        ]

        if len(corner_boundaries) != 3:
            continue

        if bevel_vertices is not None:
            bevel_vertex = get_bevel_vertex_by_id(
                bevel_vertices=bevel_vertices,
                vertex_id=vertex_id
            )

            if bevel_vertex is not None:
                selected_edges = get_bevel_vertex_selected_edges(bevel_vertex)

                if len(selected_edges) != 2:
                    continue

        tx_vertex_ids = [
            transaction.add_boundary_vertex(boundary_vertex)
            for boundary_vertex in corner_boundaries
        ]

        tx_vertex_ids = collapse_transaction_ids_by_position(
            transaction=transaction,
            tx_ids=tx_vertex_ids
        )

        if len(tx_vertex_ids) != 3:
            BX_log.debug("CORNER2 miter skipped for vertex {0}: expected 3 unique verts, got {1}".format(
                    vertex_id,
                    tx_vertex_ids
                ),channel="caps"
            )
            continue

        expected_normal = [0.0, 0.0, 0.0]
        face_center = None

        if bm is not None:
            expected_normal = average_original_vertex_normal(
                bm=bm,
                vertex_id=vertex_id
            )
            face_center = list(bm.vertices[vertex_id].co_world)

        if bxm.is_zero(expected_normal):
            points = [
                transaction.vertices[tx_id].co_world
                for tx_id in tx_vertex_ids
            ]
            expected_normal = calculate_polygon_normal(points)

        if face_center is not None:
            tx_vertex_ids = sort_transaction_vertices_on_face(
                transaction=transaction,
                vertex_ids=tx_vertex_ids,
                face_center=face_center,
                face_normal=expected_normal
            )

        tx_vertex_ids = orient_transaction_face_indices_to_normal(
            transaction=transaction,
            face_indices=tx_vertex_ids,
            expected_normal=expected_normal
        )

        if is_degenerate_transaction_polygon(
            transaction=transaction,
            vertex_ids=tx_vertex_ids
        ):
            BX_log.debug("CORNER2 miter skipped degenerate triangle for vertex {0}: verts={1}".format(
                    vertex_id,
                    tx_vertex_ids
                ),channel="caps"
            )
            continue

        face = add_bevel_face(
            transaction=transaction,
            vertex_ids=tx_vertex_ids,
            face_kind=FACE_VERT,
            source_face_id=None,
            source_edge_id=None,
            expected_normal=expected_normal,
            debug_label="CORNER2 F_VERT vertex {0}".format(vertex_id)
        )

        created_faces.append(face)

        BX_log.debug("F_VERT CORNER2 miter triangle built for vertex {0}: verts={1}, expected_normal={2}".format(
                vertex_id,
                tx_vertex_ids,
                expected_normal
            ),channel="caps"
        )

    return created_faces

def is_terminal_multi_boundary_vertex(boundary_vertex):
    """
    Return True if boundary_vertex belongs to the TERMINAL_MULTI system.
    """

    return getattr(boundary_vertex, "source", None) == "TERMINAL_MULTI"

def debug_sector_cap_ring(vertex_boundaries, vertex_id):
    """
    Log the unique sector cap ring for one original vertex.
    """

    boundary_list = vertex_boundaries.get(vertex_id, [])

    sector_boundaries = get_unique_sector_cap_boundaries(
        boundary_list
    )

    if not sector_boundaries:
        return

    BX_log.warn(
        "SECTOR CAP RING vertex {0}: count={1}, ids={2}, roles={3}".format(
            vertex_id,
            len(sector_boundaries),
            [
                getattr(boundary_vertex, "id", None)
                for boundary_vertex in sector_boundaries
            ],
            [
                getattr(boundary_vertex, "boundary_role", None)
                for boundary_vertex in sector_boundaries
            ]
        ),
        channel="summary"
    )

def get_unique_sector_cap_boundaries(boundary_list):
    """
    Return one boundary vertex per SECTOR_BOUNDARY id.

    Sector boundaries have multiple aliases:
        - selected-edge aliases for F_EDGE
        - edge_on aliases for F_RECON

    The cap must use only one representative per sector id.
    """

    result = []
    seen = set()

    for boundary_vertex in boundary_list:
        if not is_sector_boundary_vertex(boundary_vertex):
            continue

        boundary_id = getattr(boundary_vertex, "id", None)

        if boundary_id in seen:
            continue

        seen.add(boundary_id)
        result.append(boundary_vertex)

    return result

def get_terminal_multi_cap_boundaries(boundary_list):
    """
    Return TERMINAL_MULTI boundaries in the stored boundary-ring order.

    Important:
        BX_boundary.build_terminal_multi_edge_boundary_for_vertex() now builds
        the ring in Blender-like order:

            SELECTED_LEFT
            SELECTED_RIGHT
            ON_EDGE...
        
        So we preserve that order here instead of sorting or reversing.
    """

    return [
        boundary_vertex
        for boundary_vertex in boundary_list
        if is_terminal_multi_boundary_vertex(boundary_vertex)
    ]

def build_sector_cap_faces(transaction,
                           vertex_boundaries,
                           bm=None):
    """
    Build simple segments == 1 F_VERT caps from unique sector boundaries.

    This is the first BevelX equivalent of Blender's VMesh boundary cap:
        BoundVert ring -> F_VERT polygon

    Important:
        Do not use every alias.
        Use one unique boundary per sector id.
    """

    if bm is None:
        return

    for vertex_id in sorted(vertex_boundaries.keys()):
        boundary_list = vertex_boundaries.get(vertex_id, [])

        sector_boundaries = get_unique_sector_cap_boundaries(boundary_list)
        debug_sector_cap_ring(vertex_boundaries=vertex_boundaries, vertex_id=vertex_id)

        if len(sector_boundaries) < 3:
            continue

        tx_ids = []

        for boundary_vertex in sector_boundaries:
            tx_id = transaction.add_boundary_vertex(boundary_vertex)
            tx_ids.append(tx_id)

        tx_ids = collapse_transaction_ids_by_position(
            transaction=transaction,
            tx_ids=tx_ids
        )

        if len(tx_ids) < 3:
            BX_log.warn(
                "SECTOR F_VERT cap skipped for vertex {0}: collapsed count={1}".format(
                    vertex_id,
                    len(tx_ids)
                ),
                channel="summary"
            )
            continue

        expected_normal = average_original_vertex_normal(
            bm=bm,
            vertex_id=vertex_id
        )

        tx_ids = orient_transaction_face_indices_to_normal(
            transaction=transaction,
            face_indices=tx_ids,
            expected_normal=expected_normal
        )

        if is_degenerate_transaction_polygon(
            transaction=transaction,
            vertex_ids=tx_ids
        ):
            BX_log.warn(
                "SECTOR F_VERT cap skipped for vertex {0}: degenerate polygon ids={1}".format(
                    vertex_id,
                    tx_ids
                ),
                channel="summary"
            )
            continue

        add_bevel_face(
            transaction=transaction,
            vertex_ids=tx_ids,
            face_kind=FACE_VERT,
            source_face_id=None,
            source_edge_id=None,
            expected_normal=expected_normal,
            debug_label="F_VERT vertex {0}".format(vertex_id)
        )

        BX_log.warn(
            "SECTOR F_VERT cap built for vertex {0}: count={1}, verts={2}".format(
                vertex_id,
                len(tx_ids),
                tx_ids
            ),
            channel="summary"
        )

def build_terminal_multi_cap_faces(transaction,
                                   vertex_boundaries,
                                   bm=None):
    """
    Build F_VERT cap faces for TERMINAL_MULTI vertices.

    This closes the terminal vertex hole created by one selected edge entering
    a vertex with multiple other incident edges.

    Boundary count:
        3     -> triangle cap
        4+    -> ngon cap

    Assumption:
        TERMINAL_MULTI boundary vertices are already stored in cyclic
        boundary-ring order by BX_boundary.py.
    """

    created_faces = []

    for vertex_id in sorted(vertex_boundaries.keys()):
        boundary_list = vertex_boundaries.get(vertex_id, [])

        cap_boundaries = get_terminal_multi_cap_boundaries(
            boundary_list=boundary_list
        )

        if not cap_boundaries:
            continue

        if len(cap_boundaries) < 3:
            BX_log.warn(
                "TERMINAL_MULTI F_VERT skipped for vertex {0}: expected 3+ boundaries, got {1}.".format(
                    vertex_id,
                    len(cap_boundaries)
                ),
                channel="caps"
            )
            continue

        tx_vertex_ids = [
            transaction.add_boundary_vertex(boundary_vertex)
            for boundary_vertex in cap_boundaries
        ]

        tx_vertex_ids = collapse_transaction_ids_by_position(
            transaction=transaction,
            tx_ids=tx_vertex_ids
        )

        if len(tx_vertex_ids) < 3:
            BX_log.warn(
                "TERMINAL_MULTI F_VERT skipped for vertex {0}: fewer than 3 unique cap points, verts={1}.".format(
                    vertex_id,
                    tx_vertex_ids
                ),
                channel="caps"
            )
            continue

        expected_normal = [0.0, 0.0, 0.0]

        if bm is not None:
            expected_normal = average_original_vertex_normal(
                bm=bm,
                vertex_id=vertex_id
            )

        if bxm.is_zero(expected_normal):
            points = [
                transaction.vertices[tx_id].co_world
                for tx_id in tx_vertex_ids
            ]

            expected_normal = calculate_polygon_normal(points)

        tx_vertex_ids = orient_transaction_face_indices_to_normal(
            transaction=transaction,
            face_indices=tx_vertex_ids,
            expected_normal=expected_normal
        )

        if is_degenerate_transaction_polygon(
            transaction=transaction,
            vertex_ids=tx_vertex_ids
        ):
            BX_log.warn(
                "TERMINAL_MULTI F_VERT skipped degenerate cap for vertex {0}: verts={1}.".format(
                    vertex_id,
                    tx_vertex_ids
                ),
                channel="caps"
            )
            continue

        face = add_bevel_face(
            transaction=transaction,
            vertex_ids=tx_vertex_ids,
            face_kind=FACE_VERT,
            source_face_id=None,
            source_edge_id=None,
            expected_normal=expected_normal,
            debug_label="F_VERT vertex {0}".format(vertex_id)
        )

        created_faces.append(face)

        BX_log.warn(
            "TERMINAL_MULTI F_VERT cap built for vertex {0}: verts={1}".format(
                vertex_id,
                tx_vertex_ids
            ),
            channel="summary"
        )

    return created_faces


###################################################################
# Repid fix on n-Edge Pole Cap creation on high-valence vertices.
###################################################################

def is_pole_n_boundary_vertex(boundary_vertex):
    return getattr(boundary_vertex, "source", None) == "POLE_N"

def get_pole_n_cap_boundaries(boundary_list):
    return [
        boundary_vertex
        for boundary_vertex in boundary_list
        if is_pole_n_boundary_vertex(boundary_vertex)
    ]

def build_pole_n_cap_faces(transaction,
                           vertex_boundaries,
                           bm=None):
    """
    Build simple F_VERT caps for POLE_N boundaries.
    """

    if bm is None:
        return

    for vertex_id in sorted(vertex_boundaries.keys()):
        boundary_list = vertex_boundaries.get(vertex_id, [])

        cap_boundaries = get_pole_n_cap_boundaries(
            boundary_list
        )

        if len(cap_boundaries) < 3:
            continue

        tx_ids = []

        for boundary_vertex in cap_boundaries:
            tx_ids.append(
                transaction.add_boundary_vertex(boundary_vertex)
            )

        tx_ids = collapse_transaction_ids_by_position(
            transaction=transaction,
            tx_ids=tx_ids
        )

        if len(tx_ids) < 3:
            continue

        expected_normal = average_original_vertex_normal(
            bm=bm,
            vertex_id=vertex_id
        )

        tx_ids = orient_transaction_face_indices_to_normal(
            transaction=transaction,
            face_indices=tx_ids,
            expected_normal=expected_normal
        )

        if is_degenerate_transaction_polygon(
            transaction=transaction,
            vertex_ids=tx_ids
        ):
            BX_log.warn(
                "POLE_N F_VERT cap skipped for vertex {0}: degenerate ids={1}".format(
                    vertex_id,
                    tx_ids
                ),
                channel="summary"
            )
            continue

        add_bevel_face(
            transaction=transaction,
            vertex_ids=tx_ids,
            face_kind=FACE_VERT,
            source_face_id=None,
            source_edge_id=None,
            expected_normal=expected_normal,
            debug_label="F_VERT vertex {0}".format(vertex_id)
        )

        BX_log.warn(
            "POLE_N F_VERT cap built for vertex {0}: count={1}, verts={2}".format(
                vertex_id,
                len(tx_ids),
                tx_ids
            ),
            channel="summary"
        )

def build_vertex_cap_faces(transaction,
                           vertex_boundaries,
                           bm=None):
    """
    Build F_VERT cap faces from vertex-cap boundary vertices.

    Current support:
        - TRI_CAP: exactly 3 boundary vertices
        - POLE_N: 4 or more boundary vertices, first simple pole cap

    Important:
        POLE_N caps must orient against the original source vertex normal,
        not against their own calculated polygon normal. If the polygon normal
        is used as expected_normal, flipped POLE_N ngons can never be corrected.
    """
    
    build_corner2_miter_faces(transaction=transaction, vertex_boundaries=vertex_boundaries, bm=bm)
    build_terminal_multi_cap_faces(transaction=transaction, vertex_boundaries=vertex_boundaries, bm=bm)
    build_sector_cap_faces(transaction=transaction, vertex_boundaries=vertex_boundaries, bm=bm)
    build_pole_n_cap_faces(transaction=transaction, vertex_boundaries=vertex_boundaries, bm=bm)

    for vertex_id in sorted(vertex_boundaries.keys()):
        boundary_list = vertex_boundaries.get(vertex_id, [])

        cap_boundaries = [
            boundary_vertex
            for boundary_vertex in boundary_list
            if getattr(boundary_vertex, "source", None) == "TRI_CAP"
        ]

        if not cap_boundaries:
            continue

        source = getattr(cap_boundaries[0], "source", None)

        if source == "TRI_CAP" and len(cap_boundaries) != 3:
            BX_log.warn("F_VERT skipped for vertex {0}: expected 3 TRI_CAP boundaries, got {1}.".format(
                vertex_id,
                len(cap_boundaries)
            ), channel="caps")
            continue

        tx_vertex_ids = [
            transaction.add_boundary_vertex(boundary_vertex)
            for boundary_vertex in cap_boundaries
        ]

        tx_vertex_ids = collapse_transaction_ids_by_position(
            transaction=transaction,
            tx_ids=tx_vertex_ids
        )

        if len(tx_vertex_ids) < 3:
            BX_log.warn("F_VERT skipped for vertex {0}: fewer than 3 unique cap points, verts={1}.".format(
                    vertex_id, tx_vertex_ids), channel="caps")
            continue

        if is_degenerate_transaction_polygon(
            transaction=transaction,
            vertex_ids=tx_vertex_ids
        ):
            BX_log.debug("F_VERT skipped degenerate cap for vertex {0}: verts={1}.".format(
                    vertex_id, tx_vertex_ids), channel="caps")
            continue

        points = [
            transaction.vertices[tx_id].co_world
            for tx_id in tx_vertex_ids
        ]

        expected_normal = [0.0, 0.0, 0.0]

        if bm is not None:
            expected_normal = average_original_vertex_normal(
                bm=bm,
                vertex_id=vertex_id
            )

        if bxm.is_zero(expected_normal):
            expected_normal = calculate_polygon_normal(points)

        tx_vertex_ids = orient_transaction_face_indices_to_normal(
            transaction=transaction,
            face_indices=tx_vertex_ids,
            expected_normal=expected_normal
        )

        add_bevel_face(
            transaction=transaction,
            vertex_ids=tx_vertex_ids,
            face_kind=FACE_VERT,
            source_face_id=None,
            source_edge_id=None,
            expected_normal=expected_normal,
            debug_label="F_VERT vertex {0}".format(vertex_id)
        )

        BX_log.debug("F_VERT cap built for vertex {0}: source={1}, verts={2}, expected_normal={3}".format(
                vertex_id,
                source,
                tx_vertex_ids,
                expected_normal
            ),channel="caps"
        )


# -----------------------------------------------------------------------------
# F_EDGE face
# -----------------------------------------------------------------------------
#temporary
def debug_vertex_boundary_inventory(vertex_boundaries, vertex_id):
    boundary_list = vertex_boundaries.get(vertex_id, [])

    BX_log.warn(
        "BOUNDARY INVENTORY vertex {0}: count={1}".format(
            vertex_id,
            len(boundary_list)
        ),
        channel="summary"
    )

    for boundary_vertex in boundary_list:
        BX_log.warn(
            "  id={0}, source={1}, edge={2}, face={3}, role={4}, on={5}, co={6}".format(
                getattr(boundary_vertex, "id", None),
                getattr(boundary_vertex, "source", None),
                getattr(boundary_vertex, "selected_edge_id", None),
                getattr(boundary_vertex, "face_id", None),
                getattr(boundary_vertex, "boundary_role", None),
                getattr(boundary_vertex, "edge_on_id", None),
                getattr(boundary_vertex, "co_world", None)
            ),
            channel="summary"
        )
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
    BX_log.warn(
    "F_EDGE anchor edge {0}: v0_fa={1}, v1_fa={2}, v1_fb={3}, v0_fb={4}".format(
        edge_id,
        getattr(bv_v0_fa, "id", None),
        getattr(bv_v1_fa, "id", None),
        getattr(bv_v1_fb, "id", None),
        getattr(bv_v0_fb, "id", None)),
        channel="summary")
    debug_vertex_boundary_inventory(vertex_boundaries, 64)
    if None in (bv_v0_fa, bv_v1_fa, bv_v1_fb, bv_v0_fb):
        BX_log.warn("F_EDGE build failed for edge {0}: missing boundary vertex.".format(edge_id),
                    channel="transaction")
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

    return add_bevel_face(
        transaction=transaction,
        vertex_ids=face_indices,
        face_kind=FACE_EDGE,
        source_face_id=None,
        source_edge_id=edge_data["edge_id"],
        expected_normal=expected_normal,
        debug_label="F_EDGE edge {0}".format(edge_data["edge_id"])
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
                BX_log.warn("F_RECON failed: missing direct boundary for face {0}".format(face_id),
                            channel="transaction")
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
                BX_log.warn("F_RECON failed: missing reverse boundary for face {0}".format(face_id),
                            channel="transaction")
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

    return add_bevel_face(
        transaction=transaction,
        vertex_ids=rebuilt_tx_ids,
        face_kind=FACE_RECON,
        source_face_id=face_id,
        source_edge_id=None,
        expected_normal=expected_normal,
        debug_label="F_RECON face {0}".format(face_id)
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
        BX_log.debug("Terminal replacement failed at vertex {0} on face {1}: could not find neighboring faces.".format(
                vertex_id, face_id), channel="support")
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
        BX_log.debug("Terminal replacement failed at vertex {0} on face {1}: missing boundary for neighboring faces {2}, {3}.".format(
                vertex_id, face_id, prev_other_face, next_other_face), channel="support")
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