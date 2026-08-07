# BX_session.py
# BevelX bevel session state.
#
# This module owns the current interactive bevel session.
#
# Important idea:
#   The source mesh / selection is captured once.
#   Parameter changes rebuild the transaction from that captured source.
#   Apply commits the latest transaction once.
#
# This prevents:
#   width 0.1 -> bevel mesh
#   width 0.2 -> bevel already-beveled mesh
#   width 0.3 -> bevel twice-beveled mesh
#
# Instead:
#   original source + current settings -> transaction

from __future__ import print_function

import maya.cmds as cmds

from BX_core import BX_settings
from BX_mesh import BX_mesh
from BX_boundary import BX_boundary
from BX_boundary import BX_boundvert
from BX_build import BX_transaction
from BX_profile import BX_audit
from BX_profile import BX_log
from BX_mesh import BX_selection



class BX_BevelSession(object):
    """
    Current BevelX interactive session.

    Holds:
        - source selection
        - source BMesh
        - settings
        - bevel vertices
        - boundary vertices
        - transaction

    This object does not directly edit Maya geometry.
    """

    def __init__(self):
        self.active = False

        self.source_selection = []
        self.source_node = None

        self.settings = None

        self.bm = None
        self.edges_data = []

        self.bevel_vertices = None
        self.rails_by_edge_id = {}
        self.boundaries_by_edge_id = {}
        self.transactions_by_edge_id = {}
        self.selection_transaction = None

        self.audit_report = None

        self.last_error = None

        self.selection_signature = None

    def clear(self):
        self.active = False

        self.source_selection = []
        self.source_node = None

        self.settings = None

        self.bm = None
        self.edges_data = []

        self.bevel_vertices = None
        self.rails_by_edge_id = {}
        self.boundaries_by_edge_id = {}
        self.transactions_by_edge_id = {}
        self.selection_transaction = None

        self.audit_report = None

        self.last_error = None

        self.selection_signature = None

    def has_transaction(self):
        """
        Return True if this session has a transaction.
        """

        if self.selection_transaction is not None:
            return True

        return bool(self.transactions_by_edge_id)

    def get_single_transaction(self):
        """
        Return the current transaction.

        Current Apply path still only commits supported single-edge transactions.
        """

        if self.selection_transaction is not None:
            return self.selection_transaction

        if not self.transactions_by_edge_id:
            return None

        keys = sorted(self.transactions_by_edge_id.keys())

        return self.transactions_by_edge_id[keys[0]]

    def debug_print(self):
        if not BX_log.is_enabled("DEBUG", "transaction"):
            return

        BX_log.debug("Session:", channel="transaction")
        BX_log.debug("  active: {0}".format(self.active), channel="transaction")
        BX_log.debug("  source node: {0}".format(self.source_node), channel="transaction")
        BX_log.debug("  source selection: {0}".format(self.source_selection), channel="transaction")
        BX_log.debug("  edge count: {0}".format(len(self.edges_data or [])), channel="transaction")
        BX_log.debug("  selection transaction: {0}".format(self.selection_transaction is not None), channel="transaction")


CURRENT_SESSION = BX_BevelSession()


# -----------------------------------------------------------------------------
# Session lifecycle
# -----------------------------------------------------------------------------

def get_current_selection_signature():
    """
    Return a normalized signature of the current selected Maya edges.

    Uses:
        BX_selection.get_selected_edge_components()
        BX_selection.parse_edge_component()
        BX_selection.get_mesh_shape()

    Signature format:
        (
            ("|pCube1|pCubeShape1", 102),
            ("|pCube1|pCubeShape1", 106),
            ...
        )

    This is stable against selection order and prevents stale BevelX sessions
    from being reused after the user changes selected edges.
    """

    edge_components = BX_selection.get_selected_edge_components()

    signature = []

    for edge_component in edge_components:
        parsed = BX_selection.parse_edge_component(edge_component)

        node = parsed["node"]
        edge_id = parsed["index"]

        shape = BX_selection.get_mesh_shape(node)

        signature.append(
            (
                shape,
                int(edge_id)
            )
        )

    return tuple(sorted(signature))

def get_source_selection_signature(source_selection):
    """
    Return a normalized signature for a stored Maya edge selection list.

    This is like get_current_selection_signature(), but works from
    session.source_selection instead of current Maya selection.
    """

    if not source_selection:
        return tuple()

    signature = []

    edges = cmds.filterExpand(
        source_selection,
        selectionMask=32,
        expand=True
    ) or []

    for edge_component in edges:
        parsed = BX_selection.parse_edge_component(edge_component)

        node = parsed["node"]
        edge_id = parsed["index"]

        shape = BX_selection.get_mesh_shape(node)

        signature.append(
            (
                shape,
                int(edge_id)
            )
        )

    return tuple(sorted(signature))

def selection_changed_from_session():
    """
    Return True if current Maya selected edges differ from the current
    session's captured source selection.
    """

    session = CURRENT_SESSION

    current_signature = get_current_selection_signature()
    session_signature = getattr(session, "selection_signature", None)

    if session_signature is None:
        session_signature = get_source_selection_signature(
            session.source_selection
        )

    return current_signature != session_signature

def get_current_session():
    return CURRENT_SESSION


def clear_session():
    """
    Clear current BevelX session state.

    Does not delete debug objects.
    BX_debug.clear_debug() should be called by the caller if needed.
    """

    CURRENT_SESSION.clear()

    BX_log.warn(
        "BevelX session cleared.",
        channel="summary"
    )

    return CURRENT_SESSION

def start_or_rebuild_session(settings=None, rail_builder=None):
    """
    Start or rebuild the current bevel session.

    Args:
        settings:
            BevelX settings dictionary.

        rail_builder:
            Function used to build rails for one edge_data.
            Expected signature:
                rail_builder(edge_data, settings) -> rails

            This is passed in from BX_core to avoid circular imports.

    Returns:
        BX_BevelSession
    """

    if settings is None:
        settings = BX_settings.copy_defaults()

    BX_log.configure(settings)

    if rail_builder is None:
        raise RuntimeError("BX_session requires a rail_builder function.")

    session = CURRENT_SESSION

    # Start from a clean session capture.
    session.clear()

    session.settings = dict(settings)
    session.source_selection = cmds.ls(selection=True, flatten=True) or []
    session.selection_signature = get_current_selection_signature()

    if not session.source_selection:
        session.last_error = "Nothing selected."
        session.active = False
        return session

    try:
        # ---------------------------------------------------------------------
        # Capture source mesh / selection.
        # ---------------------------------------------------------------------
        session.bm = BX_mesh.get_selected_bmesh()
        session.source_node = session.bm.node

        session.edges_data = BX_mesh.get_selected_edge_data()

        if not session.edges_data:
            session.last_error = "No selected polygon edges."
            session.active = False
            return session

        # ---------------------------------------------------------------------
        # Build bevel topology data.
        # ---------------------------------------------------------------------
        session.bevel_vertices = BX_mesh.build_bevel_vertices_from_bmesh(
            session.bm
        )

        requires_selection_transaction = BX_boundary.requires_selection_transaction(
            session.bevel_vertices
        )

        # ---------------------------------------------------------------------
        # Build rails for every selected edge.
        # ---------------------------------------------------------------------
        for edge_data in session.edges_data:
            edge_id = edge_data["edge_id"]

            rails = rail_builder(
                edge_data,
                session.settings
            )

            session.rails_by_edge_id[edge_id] = rails

        # ---------------------------------------------------------------------
        # Build shared boundary data for the whole selection.
        # ---------------------------------------------------------------------
        selection_boundaries = BX_boundvert.build_boundaries_for_selection(
            bm=session.bm,
            edges_data=session.edges_data,
            rails_by_edge_id=session.rails_by_edge_id,
            bevel_vertices=session.bevel_vertices
        )

        unsupported_reason = BX_boundary.get_unsupported_boundary_reason(
            session.bevel_vertices,
            vertex_boundaries=selection_boundaries
        )

        # Store a per-edge view for drawing/debug convenience.
        for edge_data in session.edges_data:
            edge_id = edge_data["edge_id"]
            session.boundaries_by_edge_id[edge_id] = selection_boundaries

        # ---------------------------------------------------------------------
        # Unsupported topology.
        # ---------------------------------------------------------------------
        if not BX_transaction.boundaries_are_all_boundvert(selection_boundaries):
            reason = BX_boundary.get_unsupported_boundary_reason(
                selection_boundaries,
                vertex_boundaries=selection_boundaries
            )
            if reason:
                raise RuntimeError(reason)

        # ---------------------------------------------------------------------
        # Multi-edge / shared selection transaction path.
        # ---------------------------------------------------------------------
        if requires_selection_transaction or len(session.edges_data) > 1:
            session.selection_transaction = BX_transaction.build_selection_transaction(
                edges_data=session.edges_data,
                vertex_boundaries=selection_boundaries,
                bm=session.bm,
                bevel_vertices=session.bevel_vertices,
                settings=session.settings
            )

            affected_vertex_ids = BX_transaction.get_affected_vertex_ids_for_selected_edges(
                session.edges_data
            )

            affected_face_ids = BX_transaction.get_affected_face_ids_for_selected_edges(
                bm=session.bm,
                edges_data=session.edges_data
            )

            BX_log.configure(session.settings)

            session.audit_report = BX_audit.audit_selection_transaction(
                transaction=session.selection_transaction,
                bm=session.bm,
                edges_data=session.edges_data,
                vertex_boundaries=selection_boundaries,
                bevel_vertices=session.bevel_vertices,
                affected_vertex_ids=affected_vertex_ids,
                affected_face_ids=affected_face_ids,
                label="selection transaction"
            )

            BX_log.info(
                "Transaction built: edges={0}, tx_vertices={1}, tx_faces={2}, replace_faces={3}".format(
                    len(session.edges_data),
                    len(session.selection_transaction.vertices),
                    len(session.selection_transaction.faces),
                    len(session.selection_transaction.faces_to_replace)
                ),
                channel="summary"
            )

            if not session.selection_transaction.faces:
                session.last_error = "Could not build selection transaction: missing boundary data."
                session.active = True
                return session

            session.last_error = None
            session.active = True

            return session

        # ---------------------------------------------------------------------
        # Single-edge transaction path.
        # ---------------------------------------------------------------------
        for edge_data in session.edges_data:
            edge_id = edge_data["edge_id"]

            transaction = BX_transaction.build_single_edge_transaction(
                edge_data=edge_data,
                vertex_boundaries=selection_boundaries,
                bm=session.bm,
                bevel_vertices=session.bevel_vertices,
                settings=session.settings
            )

            session.boundaries_by_edge_id[edge_id] = selection_boundaries
            session.transactions_by_edge_id[edge_id] = transaction
            session.selection_transaction = transaction

        session.last_error = None
        session.active = True

        return session

    except Exception as exc:
        session.last_error = str(exc)
        session.active = False

        BX_log.warn(
            "BevelX session build failed: {0}".format(exc),
            channel="summary"
        )

        return session

def rebuild_session(settings=None, rail_builder=None):
    """
    Rebuild current session from the original source selection.

    This is used for live UI slider updates.

    Important:
        If the user has changed the Maya edge selection, do NOT restore the
        old session.source_selection. Clear the session and start from the
        current Maya selection instead.

    This prevents stale failed sessions from poisoning later valid bevels.
    """

    session = CURRENT_SESSION

    current_signature = get_current_selection_signature()

    if not session.source_selection:
        return start_or_rebuild_session(
            settings=settings,
            rail_builder=rail_builder
        )

    session_signature = getattr(session, "selection_signature", None)

    if session_signature is None:
        session_signature = get_source_selection_signature(
            session.source_selection
        )

    if current_signature != session_signature:
        BX_log.warn(
            "BevelX rebuild detected selection change. Clearing stale session. old={0}, new={1}".format(
                session_signature,
                current_signature
            ),
            channel="summary"
        )

        clear_session()

        return start_or_rebuild_session(
            settings=settings,
            rail_builder=rail_builder
        )

    # Selection has not changed, so it is safe to restore the captured source
    # selection and rebuild from it.
    try:
        cmds.select(session.source_selection, replace=True)
    except Exception:
        pass

    if settings is None:
        settings = session.settings

    return start_or_rebuild_session(
        settings=settings,
        rail_builder=rail_builder
    )